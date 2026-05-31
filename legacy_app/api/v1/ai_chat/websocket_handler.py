"""
WebSocket handler for AI Chat Assistant.
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.ai_chat.schemas import (
    ClientMessage,
    ServerMessage,
    ConnectionAckMessage,
    ErrorMessage,
    MessageType
)
from app.api.v1.ai_chat.state import ConversationState, state_manager
from app.api.v1.ai_chat.agent import SchedulerAgent
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept WebSocket connection"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")
    
    def disconnect(self, session_id: str):
        """Remove WebSocket connection"""
        self.active_connections.pop(session_id, None)
        logger.info(f"WebSocket disconnected: {session_id}")
    
    async def send_message(self, session_id: str, message: Dict[str, Any]):
        """Send message to specific WebSocket connection"""
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {session_id}: {e}")
                self.disconnect(session_id)
                raise
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send message to a specific WebSocket"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            raise


# Global connection manager
connection_manager = WebSocketConnectionManager()


async def authenticate_websocket(
    websocket: WebSocket,
    token: Optional[str] = None
) -> tuple[User, int, int]:
    """
    Authenticate WebSocket connection.
    Returns (user, tenant_id, office_id)
    """
    from app.utils.token import decode_access_token
    from app.api.v1.auth.dependencies import get_current_user_full
    
    # Get token from query string or headers
    if not token:
        # Try to get from query params
        query_params = dict(websocket.query_params)
        token = query_params.get("token")
    
    if not token:
        # Try to get from headers (if supported by WebSocket)
        headers = dict(websocket.headers)
        auth_header = headers.get("authorization") or headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        error_msg = ErrorMessage(
            type=MessageType.CONNECTION_ERROR,
            error={
                "code": "AUTH_FAILED",
                "message": "Authentication token is required",
                "details": "Provide token in query string: ?token=<access_token>"
            }
        )
        await websocket.send_json(error_msg.model_dump(exclude_none=True))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        # Decode and validate token
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Get user from database
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if not user or not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive"
                )
            
            # Get office_id from user context (simplified - you may need to adjust)
            office_id = tenant_id  # Simplified - adjust based on your logic
            
            return user, tenant_id, office_id
        
        finally:
            db.close()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        error_msg = ErrorMessage(
            type=MessageType.CONNECTION_ERROR,
            error={
                "code": "AUTH_FAILED",
                "message": "Invalid or expired authentication token",
                "details": str(e)
            }
        )
        await websocket.send_json(error_msg.model_dump(exclude_none=True))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


async def handle_websocket(websocket: WebSocket, token: Optional[str] = None):
    """
    Handle WebSocket connection for AI Chat Assistant.
    """
    user = None
    conversation_state: Optional[ConversationState] = None
    agent: Optional[SchedulerAgent] = None
    db: Optional[Session] = None
    
    try:
        # Authenticate
        user, tenant_id, office_id = await authenticate_websocket(websocket, token)
        
        # Get database session
        db = next(get_db())
        
        # Create or get conversation state
        session_id = None
        try:
            # Try to get existing session from query params
            query_params = dict(websocket.query_params)
            existing_session_id = query_params.get("session_id")
            
            if existing_session_id:
                conversation_state = state_manager.get_session(existing_session_id)
            
            if not conversation_state:
                conversation_state = state_manager.create_session(
                    user_id=user.id,
                    tenant_id=tenant_id,
                    office_id=office_id
                )
            
            session_id = conversation_state.session_id
            
            # Initialize AI agent
            try:
                agent = SchedulerAgent(db, user.id, tenant_id, office_id)
            except ImportError as e:
                # LangChain not installed - send error and close connection
                error_msg = ErrorMessage(
                    type=MessageType.CONNECTION_ERROR,
                    error={
                        "code": "DEPENDENCY_MISSING",
                        "message": "AI Chat service is not available",
                        "details": "LangChain dependencies are not installed. Please install: pip install langchain langchain-google-vertexai google-cloud-aiplatform"
                    },
                    timestamp=datetime.utcnow().isoformat()
                )
                await websocket.send_json(error_msg.model_dump(exclude_none=True))
                await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
                logger.error(f"Failed to initialize AI agent: {e}")
                return
            
            # Connect WebSocket
            await connection_manager.connect(websocket, session_id)
            
            # Send connection acknowledgment
            ack_message = ConnectionAckMessage(
                session_id=session_id,
                timestamp=datetime.utcnow().isoformat()
            )
            await websocket.send_json(ack_message.model_dump(exclude_none=True))
            
            # Main message loop
            while True:
                try:
                    # Receive message
                    data = await websocket.receive_json()
                    client_message = ClientMessage(**data)
                    
                    # Handle different message types
                    if client_message.type == MessageType.USER_MESSAGE:
                        await handle_user_message(
                            websocket,
                            client_message,
                            conversation_state,
                            agent,
                            db
                        )
                    
                    elif client_message.type == MessageType.PING:
                        # Respond to ping
                        pong_message = ServerMessage(
                            type=MessageType.PONG,
                            timestamp=datetime.utcnow().isoformat(),
                            session_id=session_id
                        )
                        await websocket.send_json(pong_message.model_dump(exclude_none=True))
                    
                    elif client_message.type == MessageType.CLEAR_HISTORY:
                        # Clear conversation history
                        conversation_state.messages = []
                        conversation_state.clear_pending()
                        cleared_message = ServerMessage(
                            type=MessageType.HISTORY_CLEARED,
                            timestamp=datetime.utcnow().isoformat(),
                            session_id=session_id
                        )
                        await websocket.send_json(cleared_message.model_dump(exclude_none=True))
                    
                    elif client_message.type == MessageType.GET_CONTEXT:
                        # Send context update
                        from app.api.v1.ai_chat.schemas import ContextUpdateMessage, ContextData
                        context_message = ContextUpdateMessage(
                            context=ContextData(
                                current_screen=conversation_state.context.get("screen"),
                                user_role=user.role if hasattr(user, 'role') else None,
                                office_id=str(office_id),
                                organization_id=str(tenant_id),
                                available_actions=["create_appointment", "update_appointment", "delete_appointment"]
                            ),
                            timestamp=datetime.utcnow().isoformat(),
                            session_id=session_id
                        )
                        await websocket.send_json(context_message.model_dump(exclude_none=True))
                    
                    # Update context if provided
                    if client_message.context:
                        conversation_state.update_context(client_message.context)
                
                except json.JSONDecodeError:
                    error_msg = ErrorMessage(
                        type=MessageType.ERROR,
                        error={
                            "code": "INVALID_MESSAGE",
                            "message": "Invalid JSON format"
                        },
                        timestamp=datetime.utcnow().isoformat(),
                        session_id=session_id
                    )
                    await websocket.send_json(error_msg.model_dump(exclude_none=True))
                
                except Exception as e:
                    logger.error(f"Error handling message: {e}", exc_info=True)
                    error_msg = ErrorMessage(
                        type=MessageType.ERROR,
                        error={
                            "code": "PROCESSING_ERROR",
                            "message": "Error processing message",
                            "details": str(e)
                        },
                        timestamp=datetime.utcnow().isoformat(),
                        session_id=session_id
                    )
                    await websocket.send_json(error_msg.model_dump(exclude_none=True))
        
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {session_id}")
        
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
            if websocket.client_state.name == "CONNECTED":
                error_msg = ErrorMessage(
                    type=MessageType.ERROR,
                    error={
                        "code": "CONNECTION_ERROR",
                        "message": "Connection error occurred",
                        "details": str(e)
                    },
                    timestamp=datetime.utcnow().isoformat(),
                    session_id=session_id
                )
                try:
                    await websocket.send_json(error_msg.model_dump(exclude_none=True))
                except:
                    pass
    
    finally:
        # Cleanup
        if session_id:
            connection_manager.disconnect(session_id)
        if db:
            db.close()
        logger.info(f"WebSocket connection closed: {session_id}")


async def handle_user_message(
    websocket: WebSocket,
    client_message: ClientMessage,
    conversation_state: ConversationState,
    agent: SchedulerAgent,
    db: Session
):
    """Handle user message and generate AI response"""
    logger.info(f"[WEBSOCKET] handle_user_message called. message_id={client_message.message_id}, content_length={len(client_message.content or '')}")
    logger.debug(f"[WEBSOCKET] Client message: {client_message.model_dump(exclude_none=True)}")
    logger.info(f"[WEBSOCKET] Conversation state session_id: {conversation_state.session_id}, message_count: {len(conversation_state.messages)}")
    
    try:
        # Send typing indicator
        logger.info(f"[WEBSOCKET] Sending typing indicator")
        typing_message = ServerMessage(
            type=MessageType.TYPING,
            timestamp=datetime.utcnow().isoformat(),
            session_id=conversation_state.session_id
        )
        await websocket.send_json(typing_message.model_dump(exclude_none=True))
        logger.info(f"[WEBSOCKET] Typing indicator sent")
        
        # Process message with AI agent
        user_content = client_message.content or ""
        logger.info(f"[WEBSOCKET] Calling agent.process_message with content: '{user_content[:100]}...'")
        response_content = agent.process_message(
            user_content,
            conversation_state
        )
        logger.info(f"[WEBSOCKET] Agent returned response. Type: {type(response_content).__name__}, length: {len(str(response_content))}")
        logger.debug(f"[WEBSOCKET] Agent response content: {str(response_content)[:500]}")
        
        # Send response (streaming simulation - can be enhanced for true streaming)
        logger.info(f"[WEBSOCKET] Creating ServerMessage response")
        response_message = ServerMessage(
            type=MessageType.ASSISTANT_MESSAGE,
            message_id=client_message.message_id,
            content=response_content,
            is_streaming=False,
            is_complete=True,
            timestamp=datetime.utcnow().isoformat(),
            session_id=conversation_state.session_id,
            metadata={
                "tokens_used": len(str(response_content).split()) if isinstance(response_content, str) else 0,  # Approximate
                "model": "gemini-2.5-pro",
                "response_time_ms": 0  # Can be calculated
            }
        )
        logger.info(f"[WEBSOCKET] Sending response message to client")
        logger.debug(f"[WEBSOCKET] Response message: {response_message.model_dump(exclude_none=True)}")
        await websocket.send_json(response_message.model_dump(exclude_none=True))
        logger.info(f"[WEBSOCKET] Response message sent successfully")
    
    except Exception as e:
        logger.error(f"[WEBSOCKET] Error handling user message: {e}", exc_info=True)
        error_msg = ErrorMessage(
            type=MessageType.ERROR,
            message_id=client_message.message_id,
            error={
                "code": "MODEL_ERROR",
                "message": "Error processing your message",
                "details": str(e)
            },
            timestamp=datetime.utcnow().isoformat(),
            session_id=conversation_state.session_id
        )
        await websocket.send_json(error_msg.model_dump(exclude_none=True))
