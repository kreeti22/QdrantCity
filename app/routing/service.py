"""
Local OpenStreetMap road network routing engine with online OSRM fallback.
"""

import json
import logging
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

import networkx as nx
import numpy as np

from app.routing.models import GeoCoordinate, RouteGeometry, RouteRequest, RouteResponse

logger = logging.getLogger("qdrant_edge.routing")

DELHI_BBOX_BUFFERED = (28.25, 76.85, 28.95, 77.55)  # Lat min, Lon min, Lat max, Lon max


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates spherical geodesic distance between two coordinates in meters."""
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2.0) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2)
    return R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


class OSMRoutingService:
    """Offline-first routing service using local OpenStreetMap road graphs with online OSRM fallback."""

    def __init__(
        self,
        osm_path: Optional[Path] = None,
        osm_file_path: Optional[str] = None,
        load_local: bool = True,
    ):
        raw_path = osm_path or osm_file_path or "data/osm/delhi_roads.json"
        self.osm_path = Path(raw_path) if not isinstance(raw_path, Path) else raw_path
        self.graph: Optional[nx.DiGraph] = None
        self.undirected_graph: Optional[nx.Graph] = None
        self._node_coords: Optional[np.ndarray] = None
        self._node_ids: Optional[np.ndarray] = None
        self._is_loaded: bool = False
        self.metadata: dict = {}
        self.init_duration_ms: float = 0.0

        if load_local:
            self._load_local_graph()
        else:
            logger.info("Local OSM graph disabled; routing will use OSRM/direct fallback.")

    @property
    def node_count(self) -> int:
        """Returns total number of road intersections in loaded graph."""
        return self.graph.number_of_nodes() if self.graph else 0

    @property
    def edge_count(self) -> int:
        """Returns total number of directed road segments in loaded graph."""
        return self.graph.number_of_edges() if self.graph else 0

    @property
    def is_loaded(self) -> bool:
        """Returns whether local OSM road graph is loaded and available."""
        return self.is_available()

    def calculate_route(self, request: RouteRequest) -> RouteResponse:
        """Convenience method taking a RouteRequest and returning RouteResponse."""
        return self.route(request.start, request.destination)

    def _load_local_graph(self) -> None:
        """Loads local Delhi OSM road network into NetworkX graph and NumPy spatial index."""
        if not self.osm_path.exists():
            logger.warning(f"Local OSM road graph not found at {self.osm_path}. Local routing disabled until downloaded.")
            return

        t0 = time.perf_counter()
        try:
            with open(self.osm_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.metadata = data.get("metadata", {})
            nodes = data.get("nodes", {})
            edges = data.get("edges", [])

            g = nx.DiGraph()
            node_ids_list = []
            lats_list = []
            lons_list = []

            for nid_str, pos in nodes.items():
                nid = int(nid_str)
                lat = float(pos["lat"])
                lon = float(pos["lon"])
                node_ids_list.append(nid)
                lats_list.append(lat)
                lons_list.append(lon)
                g.add_node(nid, lat=lat, lon=lon)

            for e in edges:
                g.add_edge(int(e["u"]), int(e["v"]), weight=float(e["weight"]))

            self.graph = g
            self.undirected_graph = g.to_undirected()
            self._node_coords = np.column_stack([lats_list, lons_list])
            self._node_ids = np.array(node_ids_list, dtype=np.int64)
            self._is_loaded = True
            self.init_duration_ms = (time.perf_counter() - t0) * 1000.0

            logger.info(
                f"Successfully loaded local OSM road graph in {self.init_duration_ms:.1f}ms: "
                f"{self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges."
            )
        except Exception as e:
            logger.error(f"Failed to load local OSM road graph: {e}", exc_info=True)
            self._is_loaded = False

    def is_available(self) -> bool:
        """Returns True if local OSM road graph is loaded and ready for offline queries."""
        return self._is_loaded and self.graph is not None and self.graph.number_of_nodes() > 0

    def get_diagnostics(self) -> dict:
        """Returns runtime diagnostics for routing service."""
        return {
            "is_loaded": self.is_available(),
            "source_file": str(self.osm_path),
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "bbox": {
                "min_lat": DELHI_BBOX_BUFFERED[0],
                "min_lon": DELHI_BBOX_BUFFERED[1],
                "max_lat": DELHI_BBOX_BUFFERED[2],
                "max_lon": DELHI_BBOX_BUFFERED[3],
            },
            "region": self.metadata.get("region", "Delhi NCR, India"),
            "attribution": self.metadata.get("attribution", "Map data © OpenStreetMap contributors"),
            "load_time_ms": round(self.init_duration_ms, 2)
        }

    def find_nearest_node(self, lat: float, lon: float) -> Tuple[int, float]:
        """Finds closest OSM road node to given coordinate using fast NumPy vectorization."""
        if not self.is_available() or self._node_coords is None:
            raise RuntimeError("Local OSM road network is not initialized")

        diff = self._node_coords - np.array([lat, lon])
        sq_dist = diff[:, 0] ** 2 + diff[:, 1] ** 2
        idx = int(np.argmin(sq_dist))
        nearest_id = int(self._node_ids[idx])
        nearest_lat = float(self._node_coords[idx, 0])
        nearest_lon = float(self._node_coords[idx, 1])
        dist_m = haversine_distance_m(lat, lon, nearest_lat, nearest_lon)
        return nearest_id, dist_m

    def is_in_local_area(self, lat: float, lon: float) -> bool:
        """Determines whether a coordinate is located within the covered Delhi OSM road graph."""
        lat_min, lon_min, lat_max, lon_max = DELHI_BBOX_BUFFERED
        return (lat_min <= lat <= lat_max) and (lon_min <= lon <= lon_max)

    def route_local(self, start: GeoCoordinate, destination: GeoCoordinate) -> Optional[RouteResponse]:
        """Calculates shortest path on local Delhi OSM road network using Dijkstra / A*."""
        if not self.is_available():
            return None

        # Check if coordinates are within the local OSM region
        if not (self.is_in_local_area(start.latitude, start.longitude) and
                self.is_in_local_area(destination.latitude, destination.longitude)):
            logger.info("Coordinates outside local Delhi OSM bounding box; deferring to online fallback.")
            return None

        try:
            u_start, start_snap_m = self.find_nearest_node(start.latitude, start.longitude)
            u_dest, dest_snap_m = self.find_nearest_node(destination.latitude, destination.longitude)

            start_snapped = GeoCoordinate(
                latitude=float(self.graph.nodes[u_start]["lat"]),
                longitude=float(self.graph.nodes[u_start]["lon"])
            )
            dest_snapped = GeoCoordinate(
                latitude=float(self.graph.nodes[u_dest]["lat"]),
                longitude=float(self.graph.nodes[u_dest]["lon"])
            )

            # If snapped to same road node, direct segment
            if u_start == u_dest:
                direct_m = haversine_distance_m(
                    start.latitude, start.longitude, destination.latitude, destination.longitude
                )
                coords = [
                    [start.longitude, start.latitude],
                    [destination.longitude, destination.latitude]
                ]
                return RouteResponse(
                    source="local_osm",
                    distance_m=round(direct_m, 1),
                    duration_s=round(max(30.0, direct_m / 8.33), 1),
                    geometry=RouteGeometry(coordinates=coords),
                    start=start,
                    destination=destination,
                    start_snapped=start_snapped,
                    destination_snapped=dest_snapped,
                    is_offline=True
                )

            # Find shortest path on directed graph first, fallback to undirected
            path = None
            try:
                path = nx.shortest_path(self.graph, u_start, u_dest, weight="weight")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                if self.undirected_graph is not None:
                    try:
                        path = nx.shortest_path(self.undirected_graph, u_start, u_dest, weight="weight")
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        path = None

            if not path or len(path) == 0:
                logger.warning(f"No local graph path found between node {u_start} and {u_dest}")
                return None

            # Reconstruct GeoJSON coordinates sequence [[lon, lat], ...]
            coords = [[start.longitude, start.latitude]]
            total_distance = start_snap_m

            for i, nid in enumerate(path):
                node_data = self.graph.nodes[nid]
                n_lat = node_data["lat"]
                n_lon = node_data["lon"]
                coords.append([n_lon, n_lat])
                if i > 0:
                    prev_nid = path[i - 1]
                    # Use edge weight if available, else haversine
                    edge_w = self.graph.get_edge_data(prev_nid, nid, {}).get("weight")
                    if edge_w is not None:
                        total_distance += edge_w
                    else:
                        prev_data = self.graph.nodes[prev_nid]
                        total_distance += haversine_distance_m(prev_data["lat"], prev_data["lon"], n_lat, n_lon)

            coords.append([destination.longitude, destination.latitude])
            total_distance += dest_snap_m

            # Average Delhi urban speed ~30 km/h = 8.33 m/s
            duration_s = max(60.0, total_distance / 8.33)

            return RouteResponse(
                source="local_osm",
                distance_m=round(total_distance, 1),
                duration_s=round(duration_s, 1),
                geometry=RouteGeometry(coordinates=coords),
                start=start,
                destination=destination,
                start_snapped=start_snapped,
                destination_snapped=dest_snapped,
                is_offline=True
            )
        except Exception as e:
            logger.error(f"Error calculating local OSM route: {e}", exc_info=True)
            return None

    def route_online(self, start: GeoCoordinate, destination: GeoCoordinate) -> Optional[RouteResponse]:
        """Online fallback routing using public OSRM service."""
        try:
            url = (
                f"https://router.project-osrm.org/route/v1/driving/"
                f"{start.longitude:.6f},{start.latitude:.6f};{destination.longitude:.6f},{destination.latitude:.6f}"
                f"?overview=full&geometries=geojson"
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "QdrantCinema/1.0 (offline-locator-fallback)"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            routes = data.get("routes", [])
            if not routes:
                return None

            primary = routes[0]
            distance_m = float(primary.get("distance", 0.0))
            duration_s = float(primary.get("duration", distance_m / 8.33))
            geom_coords = primary.get("geometry", {}).get("coordinates", [])

            if not geom_coords:
                geom_coords = [
                    [start.longitude, start.latitude],
                    [destination.longitude, destination.latitude]
                ]

            return RouteResponse(
                source="online_osrm",
                distance_m=round(distance_m, 1),
                duration_s=round(duration_s, 1),
                geometry=RouteGeometry(coordinates=geom_coords),
                start=start,
                destination=destination,
                is_offline=False
            )
        except Exception as e:
            logger.warning(f"Online OSRM routing failed or internet disconnected: {e}")
            return None

    def route_fallback_direct(self, start: GeoCoordinate, destination: GeoCoordinate) -> RouteResponse:
        """Deterministic offline straight-line geodesic fallback ensuring zero route failures."""
        dist = haversine_distance_m(start.latitude, start.longitude, destination.latitude, destination.longitude)
        road_estimate_dist = dist * 1.35  # Approximate city street curvature factor

        # Generate 5-point interpolated trajectory
        lats = np.linspace(start.latitude, destination.latitude, 5)
        lons = np.linspace(start.longitude, destination.longitude, 5)
        coords = [[round(float(lo), 6), round(float(la), 6)] for la, lo in zip(lats, lons)]

        return RouteResponse(
            source="fallback_direct",
            distance_m=round(road_estimate_dist, 1),
            duration_s=round(road_estimate_dist / 8.33, 1),
            geometry=RouteGeometry(coordinates=coords),
            start=start,
            destination=destination,
            is_offline=True
        )

    def route(self, start: GeoCoordinate, destination: GeoCoordinate) -> RouteResponse:
        """Top-level route resolver with strict priority: LOCAL OSM -> ONLINE OSRM -> DIRECT FALLBACK."""
        # 1. Primary: Local OSM road network
        local_result = self.route_local(start, destination)
        if local_result is not None:
            return local_result

        # 2. Secondary: Online OSRM fallback if network is active
        online_result = self.route_online(start, destination)
        if online_result is not None:
            return online_result

        # 3. Tertiary: Local direct geodesic fallback
        logger.info("Using local direct fallback trajectory for route.")
        return self.route_fallback_direct(start, destination)


# Singleton factory
_routing_service: Optional[OSMRoutingService] = None


def get_routing_service(
    osm_path: Optional[Path] = None,
    load_local: bool = True,
) -> OSMRoutingService:
    """Dependency provider / singleton accessor for OSMRoutingService."""
    global _routing_service
    if _routing_service is None:
        _routing_service = OSMRoutingService(osm_path=osm_path, load_local=load_local)
    return _routing_service
