"""
Conversation state management for AI Chat Assistant.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from uuid import uuid4
import json
import logging

logger = logging.getLogger(__name__)


class ConversationState:
    """Manages conversation state for a single session"""
    
    def __init__(self, session_id: str, user_id: int, tenant_id: int, office_id: int):
        self.session_id = session_id
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.office_id = office_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.messages: List[Dict[str, Any]] = []
        self.context: Dict[str, Any] = {}
        self.pending_intent: Optional[str] = None
        self.pending_entities: Dict[str, Any] = {}
        self.required_fields: List[str] = []
        self.status: str = "active"
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a message to the conversation history"""
        message = {
            "id": f"msg_{uuid4().hex[:10]}",
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)
        self.last_activity = datetime.utcnow()
        
        # Keep only last 100 messages to prevent memory issues
        if len(self.messages) > 100:
            self.messages = self.messages[-100:]
    
    def update_context(self, context: Dict[str, Any]):
        """Update conversation context"""
        self.context.update(context)
        self.last_activity = datetime.utcnow()
    
    def set_pending_intent(self, intent: str, required_fields: List[str]):
        """Set pending intent and required fields"""
        self.pending_intent = intent
        self.required_fields = required_fields
        self.last_activity = datetime.utcnow()
    
    def update_entities(self, entities: Dict[str, Any]):
        """Update extracted entities"""
        self.pending_entities.update(entities)
        self.last_activity = datetime.utcnow()
    
    def clear_pending(self):
        """Clear pending intent and entities"""
        self.pending_intent = None
        self.pending_entities = {}
        self.required_fields = []
    
    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """Check if session has expired"""
        if self.status != "active":
            return True
        elapsed = datetime.utcnow() - self.last_activity
        return elapsed > timedelta(minutes=timeout_minutes)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "office_id": self.office_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "message_count": len(self.messages),
            "status": self.status,
            "context": self.context,
            "pending_intent": self.pending_intent,
            "pending_entities": self.pending_entities
        }


class ConversationStateManager:
    """Manages multiple conversation states"""
    
    def __init__(self):
        self._sessions: Dict[str, ConversationState] = {}
        self._cleanup_interval = timedelta(minutes=5)
        self._last_cleanup = datetime.utcnow()
    
    def create_session(self, user_id: int, tenant_id: int, office_id: int) -> ConversationState:
        """Create a new conversation session"""
        session_id = f"session_{uuid4().hex[:12]}"
        state = ConversationState(session_id, user_id, tenant_id, office_id)
        self._sessions[session_id] = state
        logger.info(f"Created new conversation session: {session_id} for user {user_id}")
        return state
    
    def get_session(self, session_id: str) -> Optional[ConversationState]:
        """Get conversation state by session ID"""
        state = self._sessions.get(session_id)
        if state and state.is_expired():
            logger.info(f"Session {session_id} has expired")
            self._sessions.pop(session_id, None)
            return None
        return state
    
    def update_session(self, session_id: str, state: ConversationState):
        """Update session state"""
        self._sessions[session_id] = state
    
    def delete_session(self, session_id: str):
        """Delete a session"""
        self._sessions.pop(session_id, None)
        logger.info(f"Deleted session: {session_id}")
    
    def clear_user_sessions(self, user_id: int):
        """Clear all sessions for a user"""
        sessions_to_delete = [
            sid for sid, state in self._sessions.items()
            if state.user_id == user_id
        ]
        for sid in sessions_to_delete:
            self.delete_session(sid)
    
    def cleanup_expired(self):
        """Clean up expired sessions"""
        now = datetime.utcnow()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        expired_sessions = [
            sid for sid, state in self._sessions.items()
            if state.is_expired()
        ]
        
        for sid in expired_sessions:
            self.delete_session(sid)
        
        self._last_cleanup = now
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    def get_user_sessions(self, user_id: int) -> List[ConversationState]:
        """Get all active sessions for a user"""
        return [
            state for state in self._sessions.values()
            if state.user_id == user_id and not state.is_expired()
        ]


# Global state manager instance
state_manager = ConversationStateManager()
