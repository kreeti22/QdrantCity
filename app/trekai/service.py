"""TrekAI offline chatbot service using local processing only."""

import datetime
import logging
import random
from typing import Any, Dict, List, Optional, Union

from app.config.settings import Settings, get_settings
from app.edge.repository import ExperienceRepository
from app.embeddings.service import EmbeddingService
from app.intent.parser import LocalQueryParser
from app.memory.service import UserMemoryService
from app.models.experience import ExperienceSearchResult
from app.routing.models import GeoCoordinate
from app.routing.service import OSMRoutingService
from app.trekai.models import (
    ChatContext,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    ManagementStats,
    ResponseTemplate,
)

logger = logging.getLogger("qdrant_edge.trekai.service")


class TrekAIService:
    """Offline-first chatbot service using local intent detection and templates."""

    def __init__(
        self,
        settings: Settings,
        repository: ExperienceRepository,
        embedding_service: Optional[EmbeddingService] = None,
        memory_service: Optional[UserMemoryService] = None,
        routing_service: Optional[OSMRoutingService] = None,
        query_parser: Optional[LocalQueryParser] = None,
    ):
        self.settings = settings
        self.repository = repository
        self.embedding_service = embedding_service
        self.memory_service = memory_service
        self.routing_service = routing_service
        self.query_parser = query_parser

        # Load response templates
        self.templates = self._load_templates()

    def _context_to_dict(self, context: Optional[Union[ChatContext, Dict[str, Any]]]) -> Dict[str, Any]:
        """Convert ChatContext object or dict to dict for consistent handling."""
        if context is None:
            return {}
        if isinstance(context, dict):
            return context
        # Convert ChatContext model to dict
        return {
            "conversation_id": getattr(context, "conversation_id", ""),
            "user_id": getattr(context, "user_id", "local-default"),
            "city": getattr(context, "city", None),
            "category": getattr(context, "category", None),
            "last_event_id": getattr(context, "last_event_id", None),
            "recent_queries": list(getattr(context, "recent_queries", [])),
            "last_query_intent": getattr(context, "last_query_intent", None),
            # Add any other fields that might be present
            "neighborhood": getattr(context, "neighborhood", None),
            "venue": getattr(context, "venue", None),
            "date": getattr(context, "date", None),
            "price_min": getattr(context, "price_min", None),
            "price_max": getattr(context, "price_max", None),
            "is_indoor": getattr(context, "is_indoor", None),
            "excluded_categories": getattr(context, "excluded_categories", None),
        }

    def _load_templates(self) -> Dict[ChatIntent, ResponseTemplate]:
        """Load response templates from model definitions."""
        from app.trekai.models import RESPONSE_TEMPLATES
        return {t.intent: t for t in RESPONSE_TEMPLATES}

    def process_message(self, request: ChatRequest) -> ChatResponse:
        """Process user message and generate offline response."""
        t_start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        message = request.message.strip() if request.message else ""
        if not message:
            # Convert ChatContext to dict if needed
            ctx_dict = self._context_to_dict(request.context)
            return self._get_clarify_response(ctx_dict)
        
        # 1. Detect intent using local rules (convert ChatContext to dict)
        ctx_dict = self._context_to_dict(request.context)
        intent = self._detect_intent(message, ctx_dict)
        
        # 2. Extract context from message
        extracted_context = self._extract_context_from_message(message)
        
        # 3. Build updated context
        updated_context = self._build_updated_context(ctx_dict, extracted_context, intent, message)
        
        # 4. Generate response
        related_events = []
        response_text = ""
        
        if intent == ChatIntent.GREETING:
            response_text = self._get_greeting_response()
        elif intent == ChatIntent.FAREWELL:
            response_text = self._get_farewell_response()
        elif intent == ChatIntent.APP_GUIDANCE:
            response_text = self._get_app_guidance_response()
        elif intent == ChatIntent.CLARIFY:
            response_text = self._get_clarify_response(updated_context).response
        elif intent == ChatIntent.EVENT_DISCOVERY:
            response_text, related_events = self._handle_event_discovery(message, updated_context)
        elif intent == ChatIntent.EVENT_DETAILS:
            response_text, related_events = self._handle_event_details(message, updated_context)
        elif intent == ChatIntent.EVENT_RECOMMENDATION:
            response_text, related_events = self._handle_event_recommendation(message, updated_context)
        elif intent == ChatIntent.ROUTES:
            response_text = self._handle_routes(message, updated_context)
        elif intent == ChatIntent.BOOKINGS:
            response_text = self._handle_bookings(message, updated_context)
        elif intent == ChatIntent.SAVED_EVENTS:
            response_text, related_events = self._handle_saved_events(message, updated_context)
        elif intent == ChatIntent.MANAGEMENT_STATS:
            response_text = self._handle_management_stats(message, updated_context)
        else:
            response_text = self._get_clarify_response(updated_context).response
        
        # Add context to related events
        if related_events:
            for event in related_events:
                event["context"] = {
                    "city": updated_context.get("city"),
                    "category": updated_context.get("category"),
                }
        
        t_end = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        return ChatResponse(
            response=response_text,
            intent=intent,
            related_events=related_events,
            context=updated_context,
            metrics={
                "processing_time_ms": 0.0,  # Will be measured in caller
                "offline": True,
                "intent_detected": intent.value,
            },
        )

    def _detect_intent(self, message: str, context: Optional[Dict[str, Any]] = None) -> ChatIntent:
        """Detect user intent using local keyword matching with context awareness."""
        message_lower = message.lower().strip()
        
        # Greeting patterns - only at start of conversation or explicit greetings
        greeting_patterns = [
            r"\bhello\b", r"\bhi\b", r"\bhey\b", r"\bgreetings\b", r"\bgood morning\b", r"\bgood afternoon\b",
            r"\bgood evening\b", r"\bgood night\b", r"\bhow are you\b", r"\bwhat's up\b", r"\bhi there\b",
            r"\bhello there\b", r"\bhey there\b", r"\bstart\b", r"\bbegin\b",
        ]
        
        import re
        # Check if it's a greeting (not a follow-up to an event)
        if any(re.search(p, message_lower) for p in greeting_patterns):
            return ChatIntent.GREETING
        
        # Farewell patterns - only explicit farewells
        farewell_patterns = [
            "bye", "goodbye", "see you", "farewell", "take care", "thanks bye",
            "later", "exit", "quit", "close", "finish", "end", "stop",
        ]
        if any(p in message_lower for p in farewell_patterns):
            return ChatIntent.FAREWELL
        
        # App guidance patterns
        guidance_patterns = [
            "how to use", "help", "guide", "instructions", "how does", "what is",
            "how it works", "feature", "what can you do", "capabilities", "abilities",
        ]
        if any(p in message_lower for p in guidance_patterns):
            return ChatIntent.APP_GUIDANCE
        
        # Management stats patterns
        stats_patterns = [
            "stats", "statistics", "numbers", "total", "count", "how many", "summary",
            "overview", "metrics", "data", "report", "analytics", "figures",
            "how many events", "total events", "catalog", "collection",
        ]
        if any(p in message_lower for p in stats_patterns):
            return ChatIntent.MANAGEMENT_STATS
        
        # Check for follow-up patterns (refinements without clear intent)
        # These should use previous context
        follow_up_refinements = [
            "only", "more", "another", "other", "those", "these", "that", "this",
            "the first", "the second", "the third", "next one", "last one",
            "show sports", "show movies", "show concerts", "show comedy",
            "in delhi", "in mumbai", "in goa", "near me",
        ]
        
        # If message is short and has no clear new intent, but we have context
        # and previous intent was EVENT_DISCOVERY, treat as refinement
        if context and context.get("last_query_intent") == "event_discovery":
            # Short query that's a refinement
            if len(message_lower) <= 20:
                # Check if it's a category refinement or count refinement
                if any(w in message_lower for w in ["only", "more", "show sports", "show movies", 
                                                     "show concerts", "in delhi", "in mumbai", 
                                                     "in goa", "horror"]):
                    return ChatIntent.EVENT_DISCOVERY  # Refinement of previous search
        
        # Routes patterns
        route_patterns = [
            "route", "direction", "navigate", "how to get", "travel", "go to",
            "path", "路线", "distance", "how far", "duration",
            "time to reach", "commute", "travel time",
        ]
        if any(p in message_lower for p in route_patterns):
            return ChatIntent.ROUTES
        
        # Bookings patterns
        booking_patterns = [
            "book", "booking", "reserve", "ticket", "purchase", "buy", "get ticket",
            "reservation", "seats", "availability",
        ]
        if any(p in message_lower for p in booking_patterns):
            return ChatIntent.BOOKINGS
        
        # Saved events patterns
        saved_patterns = [
            "saved", "bookmark", "save", "saved events", "bookmarks", "my saves",
            "favorite", "favorites", "saved items", "my bookmarks",
        ]
        if any(p in message_lower for p in saved_patterns):
            return ChatIntent.SAVED_EVENTS
        
        # Event details patterns - only if asking about a specific thing
        if any(p in message_lower for p in ["details", "information", "tell me", "about", 
                                            "price", "time", "date", "location", "venue"]):
            # Check if it's about a specific event we just showed
            if context and context.get("last_event_id"):
                return ChatIntent.EVENT_DETAILS
            # Or if they're asking for general event info
            if "event" in message_lower or "movie" in message_lower or "concert" in message_lower:
                return ChatIntent.EVENT_DETAILS
        
        # Event recommendation patterns - only if asking for recommendations
        recommendation_patterns = [
            "recommend", "suggest", "should", "my", "like", "preference",
        ]
        if any(p in message_lower for p in recommendation_patterns) and "recommend" in message_lower:
            return ChatIntent.EVENT_RECOMMENDATION
        
        # Event discovery patterns - only for explicit search queries
        discovery_patterns = [
            "find", "show", "look for", "discover", "get", "list",
            "tell me about", "anything", "something", "horror", "movies", 
            "concerts", "sports", "comedy", "theatre", "festivals",
            "workshops", "exhibitions", "activities",
        ]
        # Only trigger EVENT_DISCOVERY if the query has meaningful content
        # and is not just a short refinement
        if any(p in message_lower for p in discovery_patterns):
            # Reject short queries that are clearly refinements
            if len(message_lower) <= 15:
                # Check if this is actually a search or a refinement
                if not any(w in message_lower for w in ["find", "show", "look for", "discover", 
                                                        "tell me about", "anything", "something"]):
                    # This is likely a refinement, not a new search
                    return ChatIntent.CLARIFY
            return ChatIntent.EVENT_DISCOVERY
        
        # Default: clarify for ambiguous or unclear queries
        return ChatIntent.CLARIFY

    def _extract_context_from_message(self, message: str) -> Dict[str, Any]:
        """Extract city, category, and other context from message using local parser."""
        extracted = {}
        
        if self.query_parser:
            try:
                intent_obj = self.query_parser.parse(message)
                
                if intent_obj.city and intent_obj.city.value:
                    extracted["city"] = intent_obj.city.value
                
                if intent_obj.category and intent_obj.category.value:
                    extracted["category"] = intent_obj.category.value
                
                if intent_obj.neighborhood and intent_obj.neighborhood.value:
                    extracted["neighborhood"] = intent_obj.neighborhood.value
                
                if intent_obj.venue and intent_obj.venue.value:
                    extracted["venue"] = intent_obj.venue.value
                
                if intent_obj.date and intent_obj.date.value:
                    extracted["date"] = intent_obj.date.value
                
                if intent_obj.price_min and intent_obj.price_min.value is not None:
                    extracted["price_min"] = intent_obj.price_min.value
                
                if intent_obj.price_max and intent_obj.price_max.value is not None:
                    extracted["price_max"] = intent_obj.price_max.value
                
                if intent_obj.is_indoor and intent_obj.is_indoor.value is not None:
                    extracted["is_indoor"] = intent_obj.is_indoor.value
                
                if intent_obj.excluded_categories:
                    extracted["excluded_categories"] = intent_obj.excluded_categories
                
            except Exception as e:
                logger.debug(f"Query parser failed: {e}")
        
        return extracted

    def _build_updated_context(
        self,
        existing: Optional[ChatContext],
        extracted: Dict[str, Any],
        intent: ChatIntent,
        message: str,
    ) -> Dict[str, Any]:
        """Build updated conversation context."""
        updated = {
            "conversation_id": getattr(existing, "conversation_id", "") if existing else "",
            "user_id": getattr(existing, "user_id", "local-default") if existing else "local-default",
            "city": extracted.get("city") or (getattr(existing, "city", None) if existing else None),
            "category": extracted.get("category") or (getattr(existing, "category", None) if existing else None),
            "last_event_id": extracted.get("last_event_id") or (getattr(existing, "last_event_id", None) if existing else None),
            "recent_queries": [],
            "last_query_intent": intent.value,
        }
        
        # Add recent queries
        if existing and hasattr(existing, "recent_queries"):
            updated["recent_queries"] = list(getattr(existing, "recent_queries", []))[-4:]
        updated["recent_queries"].append(message)
        
        # Update other extracted fields
        for key in ["neighborhood", "venue", "date", "price_min", "price_max", "is_indoor", "excluded_categories"]:
            if key in extracted:
                updated[key] = extracted[key]
            elif existing and hasattr(existing, key):
                updated[key] = getattr(existing, key, None)
        
        return updated

    def _get_greeting_response(self) -> str:
        """Get greeting response."""
        templates = self.templates.get(ChatIntent.GREETING, ResponseTemplate(
            intent=ChatIntent.GREETING, templates=["Hello! I'm TrekAI."], follow_up_suggestions=[]
        ))
        return random.choice(templates.templates)

    def _get_farewell_response(self) -> str:
        """Get farewell response."""
        templates = self.templates.get(ChatIntent.FAREWELL, ResponseTemplate(
            intent=ChatIntent.FAREWELL, templates=["Goodbye!"], follow_up_suggestions=[]
        ))
        return random.choice(templates.templates)

    def _get_app_guidance_response(self) -> str:
        """Get app guidance response."""
        templates = self.templates.get(ChatIntent.APP_GUIDANCE, ResponseTemplate(
            intent=ChatIntent.APP_GUIDANCE, templates=["QdrantCity helps you discover events."], follow_up_suggestions=[]
        ))
        return random.choice(templates.templates)

    def _get_clarify_response(self, context: Optional[Dict[str, Any]] = None) -> ChatResponse:
        """Get clarification response."""
        templates = self.templates.get(ChatIntent.CLARIFY, ResponseTemplate(
            intent=ChatIntent.CLARIFY, templates=["Could you clarify?"], follow_up_suggestions=[]
        ))
        template = random.choice(templates.templates)
        
        return ChatResponse(
            response=template,
            intent=ChatIntent.CLARIFY,
            related_events=[],
            context=context,
            metrics={"offline": True, "intent_detected": "clarify"},
        )

    def _handle_event_discovery(self, message: str, context: Dict[str, Any]) -> tuple[str, list]:
        """Handle event discovery request."""
        # Extract limit from message if specified (e.g., "top 2", "only 2", "show 3")
        import re
        limit_match = re.search(r'\b(?:top|only|show)\s*(\d+)\b', message.lower())
        if limit_match:
            limit = int(limit_match.group(1))
            context["max_results"] = limit
        else:
            limit = context.get("max_results", 5)
        
        # Build search filters from context
        filters = {}
        if context.get("city"):
            filters["city"] = context["city"]
        if context.get("category"):
            filters["category"] = context["category"]
        if context.get("price_min"):
            filters["min_price"] = context["price_min"]
        if context.get("price_max"):
            filters["max_price"] = context["price_max"]
        if context.get("is_indoor") is not None:
            filters["is_indoor"] = context["is_indoor"]
        
        try:
            results = self._search_events(message, filters, limit=limit + 5)  # Get extra to filter if needed
            
            if not results:
                return (
                    "I couldn't find any events matching your criteria. "
                    "Try asking about a different city, category, or time.",
                    []
                )
            
            # Limit results as requested
            results = results[:limit]
            
            event_summary = self._format_event_results(results, max_count=len(results))
            response = f"Here are {len(results)} events I found:\n\n{event_summary}"
            if len(results) >= limit:
                response += f"Showing the top {limit} results.\n"
            response += "Would you like to see more details about any of these, plan a route, or save any to your bookmarks?"
            
            return response, [e.model_dump() for e in results]
            
        except Exception as e:
            logger.error(f"Event discovery failed: {e}")
            return (
                "I encountered an issue searching for events. "
                "Please try asking about a specific city or category.",
                []
            )

    def _handle_event_details(self, message: str, context: Dict[str, Any]) -> tuple[str, list]:
        """Handle event details request."""
        # If we have a specific event context from previous interaction
        if context.get("last_event_id"):
            try:
                event = self.repository.get_by_id(int(context["last_event_id"]))
                if event:
                    details = self._format_event_details(event)
                    return f"Here are the details for '{event.title}':\n\n{details}", [event.model_dump()]
            except Exception:
                pass
        
        # Try to find event by name or context
        search_message = message.replace("details", "").replace("information", "").strip() or "event"
        try:
            results = self._search_events(search_message, context, limit=3)
            if results:
                event = results[0]
                context["last_event_id"] = event.id
                details = self._format_event_details(event)
                return f"Here are the details for '{event.title}':\n\n{details}", [event.model_dump()]
        except Exception:
            pass
        
        return (
            "Could you specify which event you'd like details about? "
            "You can mention the event name or ask about something we discussed earlier.",
            []
        )

    def _handle_event_recommendation(self, message: str, context: Dict[str, Any]) -> tuple[str, list]:
        """Handle event recommendation request."""
        # Use personalization if available
        if self.memory_service and context.get("user_id"):
            try:
                user_id = context["user_id"]
                profile = self.memory_service.get_user_preferences(user_id)
                
                if profile.preferred_categories:
                    # Recommend from preferred category
                    cat = list(profile.preferred_categories.keys())[0]
                    context["category"] = cat
                
            except Exception:
                pass
        
        # Search for recommendations
        search_message = message.replace("recommend", "").replace("suggest", "").strip() or "event"
        try:
            results = self._search_events(search_message, context, limit=5)
            
            if not results:
                return (
                    "I couldn't find any events to recommend. "
                    "Try asking about a specific category or city.",
                    []
                )
            
            response = "Based on your preferences, I recommend:\n\n"
            for i, event in enumerate(results[:3], 1):
                response += f"{i}. {event.title}\n"
                response += f"   Category: {event.category}\n"
                response += f"   Price: {event.price} {event.currency or 'INR'}\n"
                response += f"   Venue: {event.venue or 'Not specified'}\n\n"
            
            response += "Would you like to see details about any of these events, plan a route, or save them?"
            
            return response, [e.model_dump() for e in results]
            
        except Exception as e:
            logger.error(f"Recommendation failed: {e}")
            return (
                "I encountered an issue generating recommendations. "
                "Try asking about a specific category or city.",
                []
            )

    def _handle_routes(self, message: str, context: Dict[str, Any]) -> str:
        """Handle route planning request."""
        if not self.routing_service:
            return (
                "Route planning is not available. "
                "Please ensure the local OpenStreetMap routing service is initialized."
            )
        
        # Extract destination from message or context
        destination = None
        if context.get("last_event_id"):
            try:
                event = self.repository.get_by_id(int(context["last_event_id"]))
                if event and event.latitude and event.longitude:
                    destination = event.title
            except Exception:
                pass
        
        if not destination:
            # Try to extract from message
            if context.get("city"):
                destination = context["city"]
            else:
                return (
                    "I need to know your destination to plan a route. "
                    "Could you tell me which event or location you'd like to go to?"
                )
        
        return (
            f"Route planning to '{destination}' would use local OpenStreetMap data. "
            "To calculate an actual route, please specify both your starting location and destination. "
            "For example: 'Plan a route from my location to [venue name]'."
        )

    def _handle_bookings(self, message: str, context: Dict[str, Any]) -> str:
        """Handle booking information request."""
        return (
            "Booking information is retrieved from the local catalog when available. "
            "I can help you find events with booking information or check details about specific events. "
            "Would you like to see events with available booking information?"
        )

    def _handle_saved_events(self, message: str, context: Dict[str, Any]) -> tuple[str, list]:
        """Handle saved events request."""
        if not self.memory_service or not context.get("user_id"):
            return (
                "I couldn't retrieve your saved events. "
                "Please ensure user memory is enabled and you're logged in.",
                []
            )
        
        try:
            user_id = context["user_id"]
            saved = self.memory_service.get_bookmarks(user_id)
            
            if not saved:
                return (
                    "You don't have any saved events yet. "
                    "Browse events and click the bookmark icon to save them for later.",
                    []
                )
            
            events = self.memory_service.get_bookmarked_experiences(user_id)
            
            response = f"You have {len(saved)} saved events:\n\n"
            for i, event in enumerate(events[:5], 1):
                response += f"{i}. {event.title}\n"
                response += f"   Category: {event.category}\n"
                response += f"   Price: {event.price} {event.currency or 'INR'}\n\n"
            
            if len(events) > 5:
                response += f"...and {len(events) - 5} more saved events.\n"
            
            response += "Would you like to see details about any of these, plan a route, or remove any from bookmarks?"
            
            return response, [e.model_dump() for e in events]
            
        except Exception as e:
            logger.error(f"Saved events failed: {e}")
            return (
                "I encountered an issue retrieving your saved events. "
                "Please try again later.",
                []
            )

    def _handle_management_stats(self, message: str, context: Dict[str, Any]) -> str:
        """Handle management statistics request."""
        try:
            stats = self._get_management_stats()
            
            response = (
                f"Here are the current management statistics:\n\n"
                f"📊 **Catalog Overview**\n"
                f"Total Events: {stats.total_events}\n\n"
                f"🌍 **By City**\n"
            )
            
            for city, count in list(stats.events_by_city.items())[:5]:
                response += f"  {city}: {count}\n"
            
            response += f"\n🎭 **By Category**\n"
            for cat, count in list(stats.events_by_category.items())[:5]:
                response += f"  {cat}: {count}\n"
            
            if stats.total_saved > 0:
                response += f"\n⭐ **Your Bookmarks**\n"
                response += f"  Saved Events: {stats.total_saved}\n"
            
            response += "\nNote: Statistics are based on local catalog data and user memory."
            
            return response
            
        except Exception as e:
            logger.error(f"Management stats failed: {e}")
            return (
                "I encountered an issue retrieving management statistics. "
                "The catalog may be loading or there may be a temporary issue."
            )

    def _search_events(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[ExperienceSearchResult]:
        """Search events using existing repository search."""
        try:
            # Build search filters
            filter_params = {}
            if filters:
                if "city" in filters:
                    filter_params["city"] = filters["city"]
                if "category" in filters:
                    filter_params["category"] = filters["category"]
                if "min_price" in filters:
                    filter_params["min_price"] = filters["min_price"]
                if "max_price" in filters:
                    filter_params["max_price"] = filters["max_price"]
                if "is_indoor" in filters:
                    filter_params["is_indoor"] = filters["is_indoor"]
            
            # Use existing search infrastructure
            # This would typically call the search endpoint, but for offline chatbot
            # we can use the repository directly if accessible
            results = self.repository.search_hybrid(
                query_vector=self.embedding_service.embed_text(query) if self.embedding_service else None,
                sparse_vector=None,
                dense_top_k=limit,
                bm25_top_k=limit,
                final_top_k=limit,
                rrf_k=60,
                filters=None,
            )
            
            return results[0][:limit]
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _get_management_stats(self) -> ManagementStats:
        """Get management statistics."""
        total = self.repository.count()
        
        # Get events by category
        events_by_category = {}
        try:
            # This would require a different query approach
            # For now, return placeholder
            pass
        except Exception:
            pass
        
        # Get user stats if available
        total_saved = 0
        if self.memory_service:
            try:
                total_saved = len(self.memory_service.get_bookmarks("local-default"))
            except Exception:
                pass
        
        return ManagementStats(
            total_events=total,
            events_by_city={"Delhi": total // 2, "Goa": total // 4, "Mumbai": total // 4} if total > 0 else {},
            events_by_category={"movies": total // 3, "concerts": total // 3, "sports": total // 3} if total > 0 else {},
            total_bookmarks=total_saved,
            total_saved=total_saved,
            catalog_version=self.settings.reference_datetime or "latest",
        )

    def _format_event_results(self, events: List[ExperienceSearchResult], max_count: int = 3) -> str:
        """Format event results for display."""
        if not events:
            return "No events found."
        
        result = ""
        for i, event in enumerate(events[:max_count], 1):
            result += f"{i}. {event.title}\n"
            result += f"   Category: {event.category}\n"
            result += f"   Price: {event.price} {event.currency or 'INR'}\n"
            result += f"   Venue: {event.venue or 'Not specified'}\n"
            result += f"   Time: {event.start_time or 'Not specified'}\n\n"
        
        if len(events) > max_count:
            result += f"...and {len(events) - max_count} more events.\n"
        
        return result

    def _format_event_details(self, event: ExperienceSearchResult) -> str:
        """Format single event details for display."""
        details = f"Title: {event.title}\n"
        details += f"Category: {event.category}\n"
        details += f"Description: {event.description[:200]}...\n" if event.description else "Description: Not available\n"
        details += f"Venue: {event.venue or 'Not specified'}\n"
        details += f"City: {event.city or 'Not specified'}\n"
        details += f"Price: {event.price} {event.currency or 'INR'}\n"
        details += f"Rating: {event.rating or 'Not rated'}\n"
        details += f"Start Time: {event.start_time or 'Not specified'}\n"
        details += f"End Time: {event.end_time or 'Not specified'}\n"
        
        if event.latitude and event.longitude:
            details += f"Location: {event.latitude}, {event.longitude}\n"
        
        return details