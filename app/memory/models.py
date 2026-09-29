import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.experience import ExperienceSearchResult


class InteractionType(str, Enum):
    """Types of tracked user interactions."""
    SEARCH = "search"
    VIEW = "view"
    BOOKMARK = "bookmark"
    UNBOOKMARK = "unbookmark"


class InteractionEvent(BaseModel):
    """An individual local interaction event."""
    id: Optional[int] = None
    user_id: str
    event_type: str
    experience_id: Optional[Any] = None
    query: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class UserPreferenceProfile(BaseModel):
    """Inferred local user preference profile derived from interactions."""
    user_id: str
    preferred_categories: Dict[str, float] = Field(
        default_factory=dict,
        description="Category affinities normalized between 0.0 and 1.0 (e.g. {'comedy': 0.8, 'movies': 0.3})",
    )
    category_affinities: Dict[str, float] = Field(
        default_factory=dict,
        description="Alias for preferred_categories for backward compatibility and test convenience",
    )
    preferred_subcategories: Dict[str, float] = Field(
        default_factory=dict,
        description="Subcategory/format affinities normalized between 0.0 and 1.0",
    )
    preferred_price_min: Optional[float] = None
    preferred_price_max: Optional[float] = None
    preferred_price_avg: Optional[float] = None
    preferred_indoor: Optional[bool] = None
    preferred_languages: Dict[str, float] = Field(default_factory=dict)
    total_interactions: int = 0
    total_bookmarks: int = 0
    saved_experience_count: int = 0
    updated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class PersonalizationMetadata(BaseModel):
    """Telemetry describing how personalization influenced search results."""
    enabled: bool = False
    applied: bool = False
    signals_used: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None


class BookmarkItem(BaseModel):
    """A bookmarked experience record."""
    user_id: str
    experience_id: Any
    title: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    created_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class BookmarksListResponse(BaseModel):
    """Response containing list of bookmarked experience IDs and full cards."""
    user_id: str
    total: int = 0
    count: int = 0
    bookmarks: List[Any] = Field(default_factory=list)
    experiences: List[ExperienceSearchResult] = Field(default_factory=list)


class InteractionRecordRequest(BaseModel):
    """Request payload to record an interaction event."""
    event_type: Optional[str] = Field(None, description="Interaction type: 'view', 'search', etc.")
    interaction_type: Optional[str] = Field(None, description="Alias for event_type")
    experience_id: Optional[Any] = None
    query: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    is_indoor: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

    def get_event_type(self) -> str:
        return self.event_type or self.interaction_type or "view"
