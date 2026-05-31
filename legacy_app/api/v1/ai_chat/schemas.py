"""
Pydantic schemas for AI Chat Assistant API.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    """Message type enumeration"""
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TYPING = "typing"
    PING = "ping"
    PONG = "pong"
    CONNECTION_ACK = "connection_ack"
    CONNECTION_ERROR = "connection_error"
    ERROR = "error"
    CLEAR_HISTORY = "clear_history"
    HISTORY_CLEARED = "history_cleared"
    GET_CONTEXT = "get_context"
    CONTEXT_UPDATE = "context_update"
    CONNECTION_CLOSING = "connection_closing"


class BaseMessage(BaseModel):
    """Base message schema"""
    type: str
    message_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    session_id: Optional[str] = None


class ClientMessage(BaseMessage):
    """Client to server message schema"""
    type: MessageType = MessageType.USER_MESSAGE
    content: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ServerMessage(BaseMessage):
    """Server to client message schema"""
    type: MessageType
    content: Optional[str] = None
    is_streaming: Optional[bool] = False
    is_complete: Optional[bool] = True
    metadata: Optional[Dict[str, Any]] = None


class ConnectionAckMessage(ServerMessage):
    """Connection acknowledgment message"""
    type: MessageType = MessageType.CONNECTION_ACK
    status: str = "connected"
    server_info: Dict[str, Any] = Field(default_factory=lambda: {
        "version": "1.0.0",
        "features": ["streaming", "context_aware"]
    })


class ErrorMessage(ServerMessage):
    """Error message schema"""
    type: MessageType = MessageType.ERROR
    error: Dict[str, Any]


class ContextData(BaseModel):
    """Context data schema"""
    current_screen: Optional[str] = None
    user_role: Optional[str] = None
    office_id: Optional[str] = None
    organization_id: Optional[str] = None
    available_actions: Optional[List[str]] = None
    selected_data: Optional[Dict[str, Any]] = None


class ContextUpdateMessage(ServerMessage):
    """Context update message"""
    type: MessageType = MessageType.CONTEXT_UPDATE
    context: ContextData


class ChatHistoryRequest(BaseModel):
    """Request schema for getting chat history"""
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    session_id: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    """Response schema for chat history"""
    messages: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class ChatMessageRequest(BaseModel):
    """Request schema for REST fallback message endpoint"""
    content: str = Field(..., min_length=1, max_length=4000)
    context: Optional[Dict[str, Any]] = None


class ChatMessageResponse(BaseModel):
    """Response schema for REST fallback message endpoint"""
    message_id: str
    content: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class SessionInfo(BaseModel):
    """Session information schema"""
    session_id: str
    created_at: str
    last_activity: str
    message_count: int
    status: str
