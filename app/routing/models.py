"""
Models for offline & online routing service in QdrantCinema.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class GeoCoordinate(BaseModel):
    """Geographic coordinate representation."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")


class RouteRequest(BaseModel):
    """Route calculation request between origin and destination."""
    start: GeoCoordinate = Field(..., description="Origin start coordinate")
    destination: GeoCoordinate = Field(..., description="Destination coordinate")
    preference: Optional[str] = Field(default="fastest", description="Routing preference")


class RouteGeometry(BaseModel):
    """GeoJSON-compatible LineString geometry representation."""
    type: Literal["LineString"] = "LineString"
    coordinates: List[List[float]] = Field(
        ...,
        description="List of [longitude, latitude] coordinate pairs conforming to GeoJSON standards"
    )


class RouteResponse(BaseModel):
    """Route calculation response with geometry and source telemetry."""
    source: str = Field(..., description="Routing source: 'local_osm', 'online_osrm', or 'fallback_direct'")
    distance_m: float = Field(..., ge=0.0, description="Total route distance in meters")
    duration_s: Optional[float] = Field(default=None, description="Estimated traversal duration in seconds")
    distance_km: Optional[float] = Field(default=None, description="Total route distance in kilometers")
    duration_minutes: Optional[float] = Field(default=None, description="Estimated traversal duration in minutes")
    geometry: RouteGeometry = Field(..., description="Route polyline geometry")
    start: GeoCoordinate = Field(..., description="Origin coordinate")
    destination: GeoCoordinate = Field(..., description="Destination coordinate")
    start_snapped: Optional[GeoCoordinate] = Field(default=None, description="Origin snapped to closest road node")
    destination_snapped: Optional[GeoCoordinate] = Field(default=None, description="Destination snapped to closest road node")
    attribution: str = Field(
        default="Map data © OpenStreetMap contributors",
        description="Required OpenStreetMap copyright attribution"
    )
    is_offline: bool = Field(default=True, description="Whether route was generated completely offline")

    @model_validator(mode="after")
    def populate_units(self):
        if self.distance_km is None and self.distance_m is not None:
            self.distance_km = round(self.distance_m / 1000.0, 2)
        if self.duration_minutes is None and self.duration_s is not None:
            self.duration_minutes = round(self.duration_s / 60.0, 1)
        return self
