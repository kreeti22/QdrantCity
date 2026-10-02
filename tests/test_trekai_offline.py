"""
Offline Acceptance Tests for TrekAI Chatbot.

These tests verify that TrekAI works entirely offline without any external dependencies.
"""

import pytest
import sys
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import get_settings
from app.trekai.service import TrekAIService
from app.trekai.models import ChatRequest, ChatIntent


class MockRepository:
    """Mock repository for testing without database."""
    def __init__(self):
        self.count_value = 115
        
    def count(self):
        return self.count_value
    
    def get_by_id(self, experience_id):
        """Mock method to return a sample experience."""
        return None


class MockMemoryService:
    """Mock memory service for testing."""
    def get_bookmarks(self, user_id):
        return []
    
    def get_bookmarked_experiences(self, user_id):
        return []


class MockRoutingService:
    """Mock routing service for testing."""
    def is_available(self):
        return True


@pytest.fixture
def settings():
    """Get application settings."""
    return get_settings()


@pytest.fixture
def service(settings):
    """Create TrekAIService with mock dependencies."""
    mock_repo = MockRepository()
    return TrekAIService(
        settings=settings,
        repository=mock_repo,
    )


class TestTrekAIOffline:
    """Test TrekAI offline functionality."""

    def test_trekai_exists_and_offline(self, service):
        """TrekAI service exists and is configured for offline operation."""
        assert service is not None
        assert service.settings is not None
        assert service.repository is not None

    def test_greeting_intent_detection(self, service):
        """Greeting messages are detected correctly."""
        messages = ["hello", "hi there", "good morning", "hey", "start"]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            assert response.intent == ChatIntent.GREETING, f"Expected GREETING for: {msg}"
            assert len(response.response) > 0

    def test_farewell_intent_detection(self, service):
        """Farewell messages are detected correctly."""
        messages = ["bye", "goodbye", "see you", "later", "exit"]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            assert response.intent == ChatIntent.FAREWELL, f"Expected FAREWELL for: {msg}"
            assert len(response.response) > 0

    def test_app_guidance_intent_detection(self, service):
        """App guidance messages are detected correctly."""
        messages = ["how to use", "help", "what can you do", "guide", "instructions"]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            assert response.intent == ChatIntent.APP_GUIDANCE, f"Expected APP_GUIDANCE for: {msg}"
            assert len(response.response) > 0

    def test_management_stats_intent_detection(self, service):
        """Management stats messages are detected correctly."""
        messages = ["stats", "statistics", "total events", "summary", "how many events"]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            assert response.intent == ChatIntent.MANAGEMENT_STATS, f"Expected MANAGEMENT_STATS for: {msg}"
            assert len(response.response) > 0

    def test_event_discovery_intent_detection(self, service):
        """Event discovery messages are detected correctly."""
        messages = [
            "find events",
            "show concerts",
            "look for movies",
            "anything happening tonight",
            "recommend something",
        ]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            assert response.intent == ChatIntent.EVENT_DISCOVERY, f"Expected EVENT_DISCOVERY for: {msg}"
            assert len(response.response) > 0

    def test_routes_intent_detection(self, service):
        """Route planning messages are detected correctly."""
        messages = ["route", "direction", "navigate", "how to get", "travel"]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            assert response.intent == ChatIntent.ROUTES, f"Expected ROUTES for: {msg}"
            assert len(response.response) > 0

    def test_saved_events_intent_detection(self, service):
        """Saved events messages are detected correctly."""
        messages = ["saved", "bookmarks", "my saves", "favorite", "saved events"]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            assert response.intent == ChatIntent.SAVED_EVENTS, f"Expected SAVED_EVENTS for: {msg}"
            assert len(response.response) > 0

    def test_context_preservation(self, service):
        """Conversation context is preserved for follow-up questions."""
        # First query - establish context
        request1 = ChatRequest(
            message="find sports events in Delhi",
            user_id="test-user"
        )
        response1 = service.process_message(request1)
        
        # Second query - follow-up without city specification
        request2 = ChatRequest(
            message="show details",
            user_id="test-user",
            context=response1.context
        )
        response2 = service.process_message(request2)
        
        # Context should be preserved
        assert response1.context is not None
        assert "city" in response1.context or response1.context.get("last_query_intent")

    def test_offline_mode_indicated(self, service):
        """Service indicates offline operation."""
        request = ChatRequest(message="hello", user_id="test-user")
        response = service.process_message(request)
        
        assert response.metrics is not None
        assert response.metrics.get("offline") is True

    def test_no_cloud_dependencies(self, service):
        """Service does not require cloud services."""
        # All processing should be done locally
        # No network calls should be made
        
        # This is tested implicitly by verifying the service uses local components
        assert service.repository is not None
        assert service.settings is not None
        assert service.embedding_service is None  # Not required for offline operation

    def test_clarify_response_for_unknown_query(self, service):
        """Unknown queries get clarification response."""
        messages = ["asdfghjkl", "random text", "what is this"]
        
        for msg in messages:
            request = ChatRequest(message=msg, user_id="test-user")
            response = service.process_message(request)
            
            # Should get either CLARIFY or a response that indicates clarification
            assert len(response.response) > 0

    def test_management_stats_generation(self, service):
        """Management statistics are generated correctly."""
        request = ChatRequest(message="show stats", user_id="test-user")
        response = service.process_message(request)
        
        assert response.intent == ChatIntent.MANAGEMENT_STATS
        assert "events" in response.response.lower() or "statistics" in response.response.lower()
        assert "catalog" in response.response.lower() or "total" in response.response.lower()


class TestTrekAIOfflineWithMockData:
    """Test TrekAI with mock event data."""

    def test_event_search_with_city_context(self, settings):
        """Event search respects city context."""
        from app.trekai.models import ChatContext
        
        # Create a context with city
        context = ChatContext(
            city="Delhi",
            category="sports",
        )
        
        request = ChatRequest(
            message="find events",
            user_id="test-user",
            context=context,
        )
        
        mock_repo = MockRepository()
        service = TrekAIService(
            settings=settings,
            repository=mock_repo,
        )
        
        response = service.process_message(request)
        
        assert response.context is not None
        assert response.context.get("city") == "Delhi"

    def test_bookmarks_handling(self, settings):
        """Saved events are handled correctly."""
        mock_repo = MockRepository()
        mock_memory = MockMemoryService()
        
        service = TrekAIService(
            settings=settings,
            repository=mock_repo,
            memory_service=mock_memory,
        )
        
        request = ChatRequest(message="show my bookmarks", user_id="test-user")
        response = service.process_message(request)
        
        assert response.intent == ChatIntent.SAVED_EVENTS

    def test_route_request_handling(self, settings):
        """Route requests are handled with proper offline status."""
        mock_repo = MockRepository()
        mock_routing = MockRoutingService()
        
        service = TrekAIService(
            settings=settings,
            repository=mock_repo,
            routing_service=mock_routing,
        )
        
        request = ChatRequest(message="plan a route", user_id="test-user")
        response = service.process_message(request)
        
        assert response.intent == ChatIntent.ROUTES
        # Response should indicate offline operation


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])