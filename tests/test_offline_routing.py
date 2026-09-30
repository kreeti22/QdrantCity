"""
Tests for Offline Event & Movie Location Locator & Local OSM Routing.
Validates:
- Coordinates and type field in models and search results
- Local OSM road graph loading and diagnostics
- Offline route calculation (Dijkstra on NetworkX graph)
- Nearest node snapping, distance, duration, and GeoJSON LineString coordinates
- OpenStreetMap attribution compliance
- Fallback routing behavior (offline fallback / out-of-bounds)
"""
import pytest
from fastapi.testclient import TestClient
from app.config.settings import Settings
from app.main import create_app
from app.routing.service import OSMRoutingService
from app.routing.models import GeoCoordinate, RouteRequest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    edge_dir = tmp_path_factory.mktemp("routing_edge")
    mem_dir = tmp_path_factory.mktemp("routing_mem")
    s = Settings(
        edge_storage_path=edge_dir,
        sqlite_db_path=str(mem_dir / "user_memory.db"),
        collection_name="routing_experiences",
        auto_seed_on_startup=True,
        sync_enabled=False,
    )
    app = create_app(settings=s)
    with TestClient(app) as c:
        yield c


def test_1_routing_service_direct():
    """Verify OSMRoutingService directly loads local Delhi graph and computes route."""
    service = OSMRoutingService(osm_file_path="data/osm/delhi_roads.json")
    assert service.is_loaded is True
    assert service.node_count > 10000
    assert service.edge_count > 10000

    # Connaught Place (28.6315, 77.2167) to India Gate (28.6129, 77.2295)
    start = GeoCoordinate(latitude=28.6315, longitude=77.2167)
    dest = GeoCoordinate(latitude=28.6129, longitude=77.2295)
    req = RouteRequest(start=start, destination=dest)

    res = service.calculate_route(req)
    assert res.source == "local_osm"
    assert res.distance_km > 1.0
    assert res.distance_km < 10.0
    assert res.duration_minutes > 1.0
    assert len(res.geometry.coordinates) > 10
    assert "OpenStreetMap" in res.attribution
    assert res.start_snapped is not None
    assert res.destination_snapped is not None


def test_2_api_routing_status(client):
    """GET /api/routing/status returns graph diagnostics."""
    r = client.get("/api/routing/status")
    assert r.status_code == 200
    data = r.json()
    assert data["is_loaded"] is True
    assert data["node_count"] > 10000
    assert data["edge_count"] > 10000
    assert "bbox" in data
    assert data["bbox"]["min_lat"] <= 28.55
    assert data["bbox"]["max_lat"] >= 28.70


def test_3_search_results_contain_coordinates_and_type(client):
    """Qdrant Edge search returns coordinates (latitude, longitude) and type."""
    r = client.post("/api/experiences/search", json={"query": "PVR movie Delhi", "mode": "hybrid"})
    assert r.status_code == 200
    data = r.json()
    assert data["total_returned"] >= 1
    hit = data["results"][0]
    assert "latitude" in hit
    assert "longitude" in hit
    assert "type" in hit
    assert hit["type"] in ("movie", "event")
    assert hit["latitude"] is not None
    assert hit["longitude"] is not None
    assert 28.0 <= hit["latitude"] <= 29.0
    assert 76.5 <= hit["longitude"] <= 77.5


def test_4_post_route_endpoint(client):
    """POST /route calculates route using local OSM graph."""
    # Connaught Place to PVR Plaza CP
    body = {
        "start": {"latitude": 28.6315, "longitude": 77.2167},
        "destination": {"latitude": 28.6330, "longitude": 77.2185}
    }
    r = client.post("/route", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "local_osm"
    assert data["distance_km"] > 0
    assert data["duration_minutes"] > 0
    assert len(data["geometry"]["coordinates"]) >= 2
    assert "OpenStreetMap" in data["attribution"]


def test_5_post_api_route_endpoint_alias(client):
    """POST /api/route acts as an alias to /route."""
    body = {
        "start": {"latitude": 28.6315, "longitude": 77.2167},
        "destination": {"latitude": 28.6129, "longitude": 77.2295}
    }
    r = client.post("/api/route", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "local_osm"
    assert data["distance_km"] > 0.5


def test_6_offline_routing_no_network_needed():
    """Verify routing works in an isolated service instance without any network."""
    service = OSMRoutingService(osm_file_path="data/osm/delhi_roads.json")
    
    # Intentionally test two valid points within Delhi
    # Saket (28.5244, 77.2066) to Hauz Khas (28.5494, 77.2001)
    req = RouteRequest(
        start=GeoCoordinate(latitude=28.5244, longitude=77.2066),
        destination=GeoCoordinate(latitude=28.5494, longitude=77.2001)
    )
    result = service.calculate_route(req)
    assert result.source == "local_osm"
    assert 2.0 <= result.distance_km <= 10.0
    assert len(result.geometry.coordinates) > 5


def test_7_out_of_bounds_fallback():
    """When coordinates are outside Delhi OSM bbox and offline, direct fallback is returned."""
    service = OSMRoutingService(osm_file_path="data/osm/delhi_roads.json")
    # Coordinates in Mumbai (outside Delhi graph)
    req = RouteRequest(
        start=GeoCoordinate(latitude=19.0760, longitude=72.8777),
        destination=GeoCoordinate(latitude=18.9220, longitude=72.8347)
    )
    # Online OSRM might succeed if connected, or fallback to fallback_direct if offline
    result = service.calculate_route(req)
    assert result.source in ("online_osrm", "fallback_direct")
    assert result.distance_km > 0
    assert len(result.geometry.coordinates) >= 2


def test_8_leaflet_vendor_assets_served(client):
    """Verify local Leaflet 1.9.4 CSS and JS are served offline."""
    r_css = client.get("/ui/vendor/leaflet/leaflet.css")
    assert r_css.status_code == 200
    assert "leaflet" in r_css.text.lower()

    r_js = client.get("/ui/vendor/leaflet/leaflet.js")
    assert r_js.status_code == 200
    assert "leaflet" in r_js.text.lower()
