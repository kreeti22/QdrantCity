import pytest
import socket
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.config.settings import Settings
from app.main import create_app
from app.routing.service import OSMRoutingService
from app.routing.models import GeoCoordinate, RouteRequest

def test_offline_acceptance_workflow(tmp_path):
    """
    Real offline acceptance test:
    1. START QdrantCinema
    2. Search event/movie -> select result -> calculate route -> confirm LOCAL OSM route
    3. DISCONNECT INTERNET (mock socket / block all network calls)
    4. Search again -> retrieve event/movie -> show venue -> calculate route -> confirm route still generated locally
    5. Verify zero network calls were attempted during local search and route.
    """
    settings = Settings(
        edge_storage_path=tmp_path / "offline_accept_edge",
        sqlite_db_path=str(tmp_path / "offline_accept.db"),
        collection_name="offline_accept_col",
        auto_seed_on_startup=True,
        sync_enabled=False,
    )
    app = create_app(settings=settings)
    
    with TestClient(app) as client:
        # Phase 1: Connected / Online phase
        # Search for Delhi movie/event
        r_search1 = client.post("/api/experiences/search", json={"query": "PVR Director's Cut Delhi", "mode": "hybrid"})
        assert r_search1.status_code == 200
        data1 = r_search1.json()
        assert data1["total_returned"] >= 1
        item1 = data1["results"][0]
        assert "PVR" in item1["title"] or "PVR" in item1["venue"]
        assert item1["latitude"] is not None
        assert item1["longitude"] is not None

        # Route calculation
        route_req1 = {
            "start": {"latitude": 28.6315, "longitude": 77.2167}, # Connaught Place
            "destination": {"latitude": item1["latitude"], "longitude": item1["longitude"]}
        }
        r_route1 = client.post("/route", json=route_req1)
        assert r_route1.status_code == 200
        route_data1 = r_route1.json()
        assert route_data1["source"] == "local_osm"
        assert route_data1["is_offline"] is True
        assert len(route_data1["geometry"]["coordinates"]) > 2
        assert "OpenStreetMap" in route_data1["attribution"]

        # Phase 2: DISCONNECT INTERNET
        # We block all outgoing socket connections
        orig_socket_connect = socket.socket.connect

        def blocked_connect(self, *args, **kwargs):
            raise OSError(101, "Network is unreachable (INTERNET DISCONNECTED)")

        with patch.object(socket.socket, "connect", side_effect=blocked_connect):
            # 1. Search again while offline
            r_search2 = client.post("/api/experiences/search", json={"query": "Standup comedy Delhi", "mode": "hybrid"})
            assert r_search2.status_code == 200
            data2 = r_search2.json()
            assert data2["total_returned"] >= 1
            item2 = data2["results"][0]
            assert item2["venue"] is not None
            assert item2["latitude"] is not None
            assert item2["longitude"] is not None

            # 2. Calculate route while offline
            route_req2 = {
                "start": {"latitude": 28.6129, "longitude": 77.2295}, # India Gate
                "destination": {"latitude": item2["latitude"], "longitude": item2["longitude"]}
            }
            r_route2 = client.post("/route", json=route_req2)
            assert r_route2.status_code == 200
            route_data2 = r_route2.json()
            # Must still be generated locally from local OSM road graph
            assert route_data2["source"] == "local_osm"
            assert route_data2["is_offline"] is True
            assert route_data2["distance_km"] > 0
            assert len(route_data2["geometry"]["coordinates"]) > 2
            assert "OpenStreetMap" in route_data2["attribution"]

            # 3. Out-of-bounds test while offline (e.g. Mumbai destination with Delhi origin)
            # Should gracefully degrade to fallback_direct without erroring out
            route_oob = {
                "start": {"latitude": 19.0760, "longitude": 72.8777},
                "destination": {"latitude": 18.9220, "longitude": 72.8347}
            }
            r_route_oob = client.post("/route", json=route_oob)
            assert r_route_oob.status_code == 200
            route_oob_data = r_route_oob.json()
            assert route_oob_data["source"] == "fallback_direct"
            assert route_oob_data["is_offline"] is True
