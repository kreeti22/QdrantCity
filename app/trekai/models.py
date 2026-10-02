"""TrekAI models for offline chatbot responses and intents."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatIntent(str, Enum):
    """Supported TrekAI chat intents."""
    GREETING = "greeting"
    FAREWELL = "farewell"
    EVENT_DISCOVERY = "event_discovery"
    EVENT_DETAILS = "event_details"
    EVENT_RECOMMENDATION = "event_recommendation"
    ROUTES = "routes"
    BOOKINGS = "bookings"
    SAVED_EVENTS = "saved_events"
    MANAGEMENT_STATS = "management_stats"
    APP_GUIDANCE = "app_guidance"
    CLARIFY = "clarify"
    UNKNOWN = "unknown"


class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(default_factory=lambda: "", description="ISO timestamp")
    related_events: List[Dict[str, Any]] = Field(default_factory=list, description="Related events for grounding")


class ChatContext(BaseModel):
    """Conversation context for follow-up questions."""
    conversation_id: str = Field(default_factory=lambda: "", description="Unique conversation ID")
    user_id: str = Field(default="local-default", description="User ID")
    city: Optional[str] = Field(default=None, description="Current city context")
    category: Optional[str] = Field(default=None, description="Current category context")
    last_event_id: Optional[int] = Field(default=None, description="Last viewed event ID")
    recent_queries: List[str] = Field(default_factory=list, description="Recent user queries")
    last_query_intent: Optional[ChatIntent] = Field(default=None, description="Last detected intent")


class ChatRequest(BaseModel):
    """Request for TrekAI chatbot."""
    message: str = Field(..., description="User message")
    user_id: str = Field(default="local-default", description="User ID")
    context: Optional[ChatContext] = Field(default=None, description="Conversation context")


class ChatResponse(BaseModel):
    """Response from TrekAI chatbot."""
    response: str = Field(..., description="AI response message")
    intent: ChatIntent = Field(..., description="Detected intent")
    related_events: List[Dict[str, Any]] = Field(default_factory=list, description="Related events")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Updated context")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Processing metrics")


class ManagementStats(BaseModel):
    """Management statistics response."""
    total_events: int = Field(..., description="Total events in catalog")
    events_by_city: Dict[str, int] = Field(default_factory=dict, description="Events grouped by city")
    events_by_category: Dict[str, int] = Field(default_factory=dict, description="Events grouped by category")
    total_bookmarks: int = Field(default=0, description="Total bookmarks for user")
    total_saved: int = Field(default=0, description="Total saved events")
    catalog_version: Optional[str] = Field(default=None, description="Catalog version string")


class RouteResponse(BaseModel):
    """Route information response."""
    origin: str = Field(..., description="Origin location")
    destination: str = Field(..., description="Destination location")
    distance_km: float = Field(..., description="Distance in kilometers")
    duration_min: int = Field(..., description="Estimated duration in minutes")
    start_coord: Dict[str, float] = Field(default_factory=dict, description="Start coordinates")
    end_coord: Dict[str, float] = Field(default_factory=dict, description="End coordinates")
    is_offline: bool = Field(default=True, description="Whether route is computed offline")


class ResponseTemplate(BaseModel):
    """Template for response generation."""
    intent: ChatIntent = Field(..., description="Target intent")
    templates: List[str] = Field(..., description="Response templates")
    follow_up_suggestions: List[str] = Field(default_factory=list, description="Suggested follow-up questions")


# Common response templates
RESPONSE_TEMPLATES = [
    ResponseTemplate(
        intent=ChatIntent.GREETING,
        templates=[
            "Hello! I'm TrekAI, your offline city assistant. I can help you discover events, find routes, check management stats, or answer questions about QdrantCity.",
            "Hi there! I'm TrekAI. How can I assist you with finding events, planning routes, or exploring what's available in QdrantCity today?",
            "Greetings! I'm your local offline assistant. Ask me about events, routes, saved items, or how to use QdrantCity.",
        ],
        follow_up_suggestions=[
            "What events are happening tonight?",
            "Show me sports events in Delhi",
            "What's the weather like?",
            "How do I use the app?",
        ],
    ),
    ResponseTemplate(
        intent=ChatIntent.FAREWELL,
        templates=[
            "Enjoy your day! Feel free to ask if you need anything else about events, routes, or QdrantCity.",
            "Take care! If you need help finding events, planning routes, or understanding QdrantCity, just ask.",
            "Goodbye! Have a great time exploring events, discovering routes, or enjoying QdrantCity.",
            "See you later! Remember, I'm here if you need help with events, routes, or any questions about QdrantCity.",
        ],
        follow_up_suggestions=[
            "Tell me about upcoming concerts",
            "Plan a route to the cinema",
            "What events have I saved?",
        ],
    ),
    ResponseTemplate(
        intent=ChatIntent.APP_GUIDANCE,
        templates=[
            "QdrantCity helps you discover movies, concerts, plays, sports, festivals, workshops, exhibitions, and activities. Use the search bar, filters, or ask me anything offline. I can also help plan routes and show your saved events.",
            "QdrantCity is an offline-first city experiences platform. You can search for events, filter by category or city, save favorites to bookmarks, view detailed information, plan offline routes, and get management statistics. Ask me to find something specific or explain any feature.",
            "QdrantCity lets you discover and plan city experiences entirely offline. Try searching for 'movies tonight', 'sports in Delhi', 'events under ₹1000', or ask me to show your saved events and plan a route.",
        ],
        follow_up_suggestions=[
            "How do I save events?",
            "Can I plan routes offline?",
            "What categories are available?",
            "How does search work?",
        ],
    ),
    ResponseTemplate(
        intent=ChatIntent.MANAGEMENT_STATS,
        templates=[
            "I can help with management statistics. The catalog contains events, bookmarks, and saved items.",
            "For management statistics, I can provide counts by city, category, or your personal bookmarks and saved events.",
            "Management stats include total events in the catalog, breakdowns by city and category, and your personal saved items count.",
        ],
        follow_up_suggestions=[
            "How many events are in Delhi?",
            "Show me total bookmarks",
            "What's in the catalog?",
        ],
    ),
    ResponseTemplate(
        intent=ChatIntent.CLARIFY,
        templates=[
            "Could you clarify what you're looking for? For example, do you want to find events, plan a route, check saved items, or get management statistics?",
            "I want to help! Could you specify whether you'd like to discover events, get route information, view your saved events, or check management stats?",
            "Let me make sure I understand. Are you asking about events, routes, your bookmarks, or something else?",
        ],
        follow_up_suggestions=[
            "Show me events in Mumbai",
            "Plan a route to the theatre",
            "What events have I saved?",
            "Give me management statistics",
        ],
    ),
]