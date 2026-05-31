"""
API routes for AI Chat Assistant.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.api.v1.ai_chat.websocket_handler import handle_websocket, connection_manager
from app.api.v1.ai_chat.schemas import (
    ChatHistoryRequest,
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    SessionInfo,
    ErrorMessage,
    MessageType
)
from app.api.v1.ai_chat.state import state_manager
from app.core.database import get_db
from app.api.v1.auth.dependencies import get_current_user
from app.models.user import User
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-chat", tags=["AI Chat"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for AI Chat Assistant.
    
    Connect with: ws://localhost:8000/api/v1/ai-chat/ws?token=<access_token>
    """
    await handle_websocket(websocket, token)


@router.get("/history")
async def get_chat_history(
    request: ChatHistoryRequest = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get chat history for the current user.
    """
    try:
        # Get user's sessions
        sessions = state_manager.get_user_sessions(current_user.id)
        
        # Filter by session_id if provided
        if request.session_id:
            sessions = [s for s in sessions if s.session_id == request.session_id]
        
        # Get messages from sessions
        all_messages = []
        for session in sessions:
            all_messages.extend(session.messages)
        
        # Sort by timestamp
        all_messages.sort(key=lambda x: x.get("timestamp", ""))
        
        # Paginate
        total = len(all_messages)
        messages = all_messages[request.offset:request.offset + request.limit]
        
        return ChatHistoryResponse(
            messages=messages,
            total=total,
            limit=request.limit,
            offset=request.offset
        )
    
    except Exception as e:
        logger.error(f"Error getting chat history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving chat history"
        )


@router.post("/message")
async def send_message_rest(
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    REST fallback endpoint for sending messages (when WebSocket is unavailable).
    """
    try:
        from app.api.v1.ai_chat.agent import SchedulerAgent
        from app.api.v1.ai_chat.state import ConversationState
        
        # Get or create session
        sessions = state_manager.get_user_sessions(current_user.id)
        if sessions:
            conversation_state = sessions[0]  # Use first active session
        else:
            # Get tenant_id and office_id from user context
            tenant_id = current_user.tenant_id if hasattr(current_user, 'tenant_id') else 1
            office_id = tenant_id  # Simplified - adjust based on your logic
            conversation_state = state_manager.create_session(
                user_id=current_user.id,
                tenant_id=tenant_id,
                office_id=office_id
            )
        
        # Initialize agent
        tenant_id = current_user.tenant_id if hasattr(current_user, 'tenant_id') else 1
        office_id = tenant_id  # Simplified
        agent = SchedulerAgent(db, current_user.id, tenant_id, office_id)
        
        # Process message
        response_content = agent.process_message(
            request.content,
            conversation_state
        )
        
        # Update context if provided
        if request.context:
            conversation_state.update_context(request.context)
        
        return ChatMessageResponse(
            message_id=f"msg_{datetime.utcnow().timestamp()}",
            content=response_content,
            timestamp=datetime.utcnow().isoformat(),
            metadata={
                "tokens_used": len(response_content.split()),
                "model": "gemini-2.5-pro"
            }
        )
    
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )


@router.delete("/history")
async def clear_chat_history(
    session_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """
    Clear chat history for the current user.
    """
    try:
        if session_id:
            # Clear specific session
            state_manager.delete_session(session_id)
            sessions_cleared = 1
        else:
            # Clear all user sessions
            state_manager.clear_user_sessions(current_user.id)
            sessions_cleared = len(state_manager.get_user_sessions(current_user.id))
        
        return {
            "status": "success",
            "message": "Chat history cleared",
            "sessions_cleared": sessions_cleared
        }
    
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error clearing chat history"
        )


@router.get("/session")
async def get_session_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current session information.
    """
    try:
        sessions = state_manager.get_user_sessions(current_user.id)
        
        if not sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active session found"
            )
        
        # Return first active session
        session = sessions[0]
        
        return SessionInfo(
            session_id=session.session_id,
            created_at=session.created_at.isoformat(),
            last_activity=session.last_activity.isoformat(),
            message_count=len(session.messages),
            status=session.status
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving session information"
        )
