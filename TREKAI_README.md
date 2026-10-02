# TrekAI - Offline Chatbot for QdrantCity

**TrekAI** is a fully offline chatbot integrated into QdrantCity that helps you discover events, plan routes, check management statistics, and get guidance on using the app - all without internet access.

## Features

### Offline-First Design
- **100% Local Processing**: All chatbot logic runs on your device using local intent detection and templates
- **No Cloud Dependencies**: No external APIs, cloud LLMs, or online services required
- **Web Speech API Support**: Browser-based offline voice input when available
- **Private by Design**: Your conversations and preferences stay on your device

### Capabilities

#### Event Discovery
- Find events by category (movies, concerts, sports, festivals, workshops, etc.)
- Natural language queries: "find sports events in Delhi"
- Context-aware follow-up questions
- Event recommendations based on preferences

#### Event Details
- Get detailed information about specific events
- Venue, time, price, and description
- Location coordinates

#### Route Planning
- Calculate offline routes using local OSM data
- Distance and duration estimates
- Offline operation (no live traffic data)

#### Management Statistics
- Total events in catalog
- Events by city and category
- Your saved items count

#### App Guidance
- How to use QdrantCity
- Feature explanations
- Clarification for unclear queries

## Architecture

### Backend Components

```
TrekAI/
├── models.py          # Intent definitions and response templates
├── service.py         # Offline NLP engine with local intent detection
└── api/
    └── trekai_routes.py  # FastAPI endpoints
```

### Key Design Decisions

1. **Intent Detection**: Rule-based local parsing (no external models)
2. **Response Generation**: Template-based with event data grounding
3. **No LLM Requirement**: Works without local LLM (uses templates)
4. **Context Preservation**: Conversation history maintained client-side
5. **Offline First**: No network fallbacks to external services

## API Endpoints

### POST `/api/chat`
Process a chat message and return response.

**Request:**
```json
{
  "message": "find sports events in Delhi",
  "user_id": "local-default",
  "context": {}
}
```

**Response:**
```json
{
  "response": "Here are some events I found...",
  "intent": "event_discovery",
  "related_events": [...],
  "context": {"city": "Delhi", "category": "sports"},
  "metrics": {"offline": true, "processing_time_ms": 15.2}
}
```

### GET `/api/chat/status`
Get TrekAI service status.

### GET `/api/chat/intents`
List supported chat intents.

## Usage

### Starting the Chatbot
1. Open QdrantCity
2. Click the TrekAI floating icon (bottom-right)
3. Start asking questions!

### Supported Queries

| Query Type | Examples |
|------------|----------|
| Greeting | "hello", "hi there" |
| Event Search | "find sports events", "show movies tonight" |
| Event Details | "tell me about Dune", "event details" |
| Routes | "plan route", "how to get there" |
| Statistics | "show stats", "how many events" |
| Saved Events | "my bookmarks", "saved events" |
| Guidance | "how to use", "what can you do" |

### Voice Input
Click the microphone button in the chat panel or search bar to use voice input.

**Requirements:**
- Browser must support Web Speech API (Chrome, Edge, Safari)
- Microphone permissions granted
- Offline operation uses browser's speech recognition

## Integration with QdrantCity

TrekAI integrates with existing QdrantCity components:

- **Qdrant Edge**: Local event retrieval engine
- **Intent Parser**: Query understanding for event discovery
- **Memory Service**: User preferences and bookmarks
- **Routing Service**: Offline route calculation

## Testing

Run the offline acceptance tests:

```bash
pytest tests/test_trekai_offline.py -v
```

### Test Coverage
1. TrekAI opens and responds with internet disconnected
2. Local event discovery works through Qdrant Edge
3. NLP intent detection works without external services
4. Replies are grounded in local event records
5. Follow-up questions preserve event and city context
6. Preferences and personalization work from local memory
7. Route requests use locally available OSM data
8. Management statistics match actual database counts
9. Sports filtering returns matching records when present
10. Network-disabled tests confirm no cloud LLM requests

## Configuration

### Environment Variables
No special configuration required. TrekAI uses existing QdrantCity settings.

### Browser Requirements
- Chrome/Edge: Full Web Speech API support
- Firefox: Partial support (may need flags enabled)
- Safari: Support with privacy settings
- Other browsers: Falls back to text input with informative message

## Limitations

1. **Voice Input**: Requires browser support for Web Speech API
2. **Response Generation**: Template-based (not generative AI)
3. **Language**: Currently English-only intent detection
4. **Offline Routes**: Uses local OSM data, may not cover all regions

## File Changes Summary

### Backend
- `app/api/trekai_routes.py` - New: Chatbot API endpoints
- `app/trekai/models.py` - New: Models and templates
- `app/trekai/service.py` - New: Offline NLP engine
- `app/trekai/__init__.py` - New: Module initialization
- `app/main.py` - Modified: Added TrekAI router
- `app/retrieval/filter_builder.py` - Modified: Added debug logging

### Frontend
- `frontend/components/TrekAIChatIcon.js` - New: Floating chat icon
- `frontend/components/TrekAIChat.js` - New: Chat panel
- `frontend/pages/DiscoveryPage.js` - Modified: Integrated TrekAI
- `frontend/components/SearchBar.js` - Modified: Added voice input
- `frontend/services/client.js` - Modified: Added TrekAI API methods

### Tests
- `tests/test_trekai_offline.py` - New: Offline acceptance tests

## Development

### Adding New Intents
1. Add intent to `ChatIntent` enum in `models.py`
2. Add detection logic in `TrekAIService._detect_intent()`
3. Add handler method in `TrekAIService`
4. Update templates as needed

### Adding New Response Templates
Edit `RESPONSE_TEMPLATES` in `models.py`:

```python
ResponseTemplate(
    intent=ChatIntent.NEW_INTENT,
    templates=[
        "Template 1",
        "Template 2",
    ],
    follow_up_suggestions=["Suggestion 1", "Suggestion 2"],
)
```

## License
Same as QdrantCity - offline-first city experiences platform.