"""
Download and build local Delhi OSM road network for offline routing.
Fetches bounded Delhi road network from OpenStreetMap Overpass API,
extracts connected road graph, and saves as data/osm/delhi_roads.json.
"""

import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path

# Bounding box for Delhi demo area:
# South: 28.50 (Mehrauli/Saket)
# North: 28.72 (Civil Lines/Ridge)
# West: 77.10 (Vasant Kunj/Airport road)
# East: 77.30 (Mayur Vihar/Noida border)
BBOX = (28.50, 77.10, 28.72, 77.30)

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two points on Earth in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def fetch_osm_delhi() -> dict:
    query = """
    [out:json][timeout:45];
    (
      way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified"](28.50,77.10,28.72,77.30);
    );
    out body;
    >;
    out skel qt;
    """
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "QdrantCinemaOfflineRouter/1.0 (hackathon-demo)"}
    )
    print("Fetching Delhi road network from OpenStreetMap Overpass API...")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def process_osm_data(osm_raw: dict) -> dict:
    nodes = {}
    edges = []
    
    # 1. Index all nodes
    for el in osm_raw.get("elements", []):
        if el.get("type") == "node":
            nodes[el["id"]] = {
                "lat": el["lat"],
                "lon": el["lon"]
            }
            
    # 2. Extract edges from ways
    ways_count = 0
    for el in osm_raw.get("elements", []):
        if el.get("type") == "way":
            way_nodes = el.get("nodes", [])
            highway = el.get("tags", {}).get("highway", "road")
            name = el.get("tags", {}).get("name", "")
            oneway = el.get("tags", {}).get("oneway") == "yes"
            
            for i in range(len(way_nodes) - 1):
                u, v = way_nodes[i], way_nodes[i + 1]
                if u in nodes and v in nodes:
                    u_pos = nodes[u]
                    v_pos = nodes[v]
                    dist = haversine_m(u_pos["lat"], u_pos["lon"], v_pos["lat"], v_pos["lon"])
                    edge_data = {
                        "u": u,
                        "v": v,
                        "weight": round(dist, 2),
                        "highway": highway,
                        "name": name
                    }
                    edges.append(edge_data)
                    # If not oneway, allow reverse traversal
                    if not oneway:
                        edges.append({
                            "u": v,
                            "v": u,
                            "weight": round(dist, 2),
                            "highway": highway,
                            "name": name
                        })
            ways_count += 1
            
    print(f"Extracted {len(nodes)} OSM nodes and {len(edges)} directed road edges from {ways_count} ways.")
    
    # Filter nodes to only those that appear in at least one edge
    used_node_ids = set()
    for e in edges:
        used_node_ids.add(e["u"])
        used_node_ids.add(e["v"])
        
    filtered_nodes = {nid: nodes[nid] for nid in used_node_ids}
    print(f"Graph contains {len(filtered_nodes)} connected road nodes.")
    
    return {
        "metadata": {
            "source": "OpenStreetMap",
            "attribution": "Map data © OpenStreetMap contributors",
            "bbox": BBOX,
            "region": "Delhi NCR, India",
            "node_count": len(filtered_nodes),
            "edge_count": len(edges)
        },
        "nodes": filtered_nodes,
        "edges": edges
    }


def main():
    out_dir = Path("data/osm")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "delhi_roads.json"
    
    raw = fetch_osm_delhi()
    graph_data = process_osm_data(raw)
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(graph_data, f)
        
    size_mb = os.path.getsize(out_file) / (1024 * 1024)
    print(f"Successfully saved Delhi OSM road graph to {out_file} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
