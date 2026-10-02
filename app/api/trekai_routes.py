"""TrekAI chatbot API routes."""

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config.settings import get_settings
from app.edge.repository import ExperienceRepository
from app.embeddings.service import EmbeddingService
from app.intent.parser import LocalQueryParser
from app.memory.service import UserMemoryService
from app.routing.service import OSMRoutingService
from app.trekai.models import ChatContext, ChatRequest, ChatResponse
from app.trekai.service import TrekAIService

logger = logging.getLogger("qdrant_edge.trekai.routes")

router = APIRouter()


def get_trekai_service(request: Request) -> TrekAIService:
    """Dependency provider for TrekAIService."""
    settings = getattr(request.app.state, "settings", get_settings())
    repository = getattr(request.app.state, "repository", None)
    embedding_service = getattr(request.app.state, "embedding_service", None)
    memory_service = getattr(request.app.state, "memory_service", None)
    routing_service = getattr(request.app.state, "routing_service", None)
    query_parser = getattr(request.app.state, "query_parser", None)
    
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Experience repository is not initialized",
        )
    
    return TrekAIService(
        settings=settings,
        repository=repository,
        embedding_service=embedding_service,
        memory_service=memory_service,
        routing_service=routing_service,
        query_parser=query_parser,
    )


class ChatRequestModel(BaseModel):
    """Request model for chat endpoint."""
    message: str
    user_id: str = "local-default"
    context: Optional[Dict[str, Any]] = None


class ChatResponseModel(BaseModel):
    """Response model for chat endpoint."""
    response: str
    intent: str
    related_events: list = []
    context: Optional[Dict[str, Any]] = None
    metrics: Dict[str, Any] = {}


@router.post(
    "/chat",
    response_model=ChatResponseModel,
    tags=["TrekAI"],
)
def chat(
    request: ChatRequestModel,
    trekai_service: TrekAIService = Depends(get_trekai_service),
) -> ChatResponseModel:
    """Process chat message and return offline-generated response."""
    t_start = time.perf_counter()
    
    try:
        # Build context
        context = None
        if request.context:
            context = ChatContext(**request.context)
        
        # Process message
        response = trekai_service.process_message(
            ChatRequest(
                message=request.message,
                user_id=request.user_id,
                context=context,
            )
        )
        
        # Calculate processing time
        processing_time = (time.perf_counter() - t_start) * 1000
        
        return ChatResponseModel(
            response=response.response,
            intent=response.intent.value,
            related_events=response.related_events,
            context=response.context,
            metrics={
                **response.metrics,
                "processing_time_ms": round(processing_time, 2),
            },
        )
        
    except Exception as e:
        logger.error(f"Chat processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {str(e)}",
        )


@router.get(
    "/chat/status",
    response_model=Dict[str, Any],
    tags=["TrekAI"],
)
def chat_status(
    request: Request,
) -> Dict[str, Any]:
    """Get TrekAI service status."""
    trekai_service = get_trekai_service(request)
    
    return {
        "status": "ready",
        "offline": True,
        "service": "TrekAI",
        "version": "1.0.0",
        "capabilities": [
            "event_discovery",
            "event_details",
            "event_recommendation",
            "routes",
            "bookings",
            "saved_events",
            "management_stats",
            "app_guidance",
        ],
    }


@router.get(
    "/chat/intents",
    response_model=Dict[str, list],
    tags=["TrekAI"],
)
def get_intents() -> Dict[str, list]:
    """Get list of supported chat intents."""
    from app.trekai.models import ChatIntent
    
    return {
        "intents": [intent.value for intent in ChatIntent],
        "offline": True,
        "description": "All intent detection is performed locally without external services.",
    }