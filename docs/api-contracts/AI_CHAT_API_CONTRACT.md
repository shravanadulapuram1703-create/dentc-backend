# AI Chat Assistant API Contract

## Overview

This document defines the API contracts for the AI Chat Assistant feature. The implementation uses **WebSocket** for real-time bidirectional communication between the frontend and backend, with optional REST endpoints for fallback and initial connection setup.

---

## Table of Contents

1. [WebSocket Connection](#websocket-connection)
2. [Message Protocol](#message-protocol)
3. [Authentication](#authentication)
4. [Message Types](#message-types)
5. [Error Handling](#error-handling)
6. [Connection Lifecycle](#connection-lifecycle)
7. [REST Endpoints (Optional)](#rest-endpoints-optional)
8. [Future Extensibility](#future-extensibility)

---

## WebSocket Connection

### Endpoint

```
ws://localhost:8000/api/v1/ai-chat/ws
wss://your-domain.com/api/v1/ai-chat/ws (Production)
```

### Connection Establishment

**Client → Server: Connection Request**

The WebSocket connection should be established with authentication token in the query string or headers.

**Option 1: Query String (Recommended)**
```
ws://localhost:8000/api/v1/ai-chat/ws?token=<access_token>
```

**Option 2: Authorization Header**
```
Authorization: Bearer <access_token>
```

### Connection Response

**Server → Client: Connection Acknowledgment**

```json
{
  "type": "connection_ack",
  "status": "connected",
  "session_id": "session_abc123xyz",
  "timestamp": "2026-01-20T10:30:00Z",
  "server_info": {
    "version": "1.0.0",
    "features": ["streaming", "context_aware"]
  }
}
```

**Error Response (Connection Failed)**

```json
{
  "type": "connection_error",
  "error": {
    "code": "AUTH_FAILED",
    "message": "Invalid or expired authentication token",
    "details": "Token expired at 2026-01-20T10:00:00Z"
  },
  "timestamp": "2026-01-20T10:30:00Z"
}
```

---

## Message Protocol

### Message Format

All messages follow a consistent JSON structure:

```typescript
interface BaseMessage {
  type: string;           // Message type (see Message Types section)
  message_id?: string;    // Unique message ID (client-generated for requests)
  timestamp: string;       // ISO 8601 timestamp
  session_id?: string;   // Session ID (server-provided on connection)
}
```

### Client → Server Message Format

```typescript
interface ClientMessage extends BaseMessage {
  type: "user_message" | "ping" | "clear_history" | "get_context";
  content?: string;       // Message content (for user_message)
  context?: {             // Optional context data
    screen?: string;
    selected_data?: any;
    user_action?: string;
  };
}
```

### Server → Client Message Format

```typescript
interface ServerMessage extends BaseMessage {
  type: "assistant_message" | "pong" | "error" | "typing" | "context_update";
  content?: string;       // Response content
  is_streaming?: boolean; // Whether this is a streaming response
  is_complete?: boolean;  // Whether streaming is complete
  metadata?: {
    tokens_used?: number;
    model?: string;
    response_time_ms?: number;
  };
}
```

---

## Authentication

### WebSocket Authentication

The WebSocket connection requires a valid JWT access token. The token should be:

1. **Valid** (not expired)
2. **Authenticated** (user exists and is active)
3. **Authorized** (user has permission to use AI chat feature)

### Token Validation

**Request:**
- Token provided in query string: `?token=<access_token>`
- Or in Authorization header: `Authorization: Bearer <access_token>`

**Response:**
- **Success:** Connection established, `connection_ack` message sent
- **Failure:** Connection rejected, `connection_error` message sent, WebSocket closed

### Token Refresh

If the token expires during an active session:

**Server → Client: Token Expired**

```json
{
  "type": "error",
  "error": {
    "code": "TOKEN_EXPIRED",
    "message": "Authentication token has expired. Please reconnect with a fresh token."
  },
  "timestamp": "2026-01-20T10:30:00Z"
}
```

The client should:
1. Refresh the token using the refresh token endpoint
2. Reconnect the WebSocket with the new token
3. Optionally restore conversation history

---

## Message Types

### 1. User Message

**Client → Server: Send User Message**

```json
{
  "type": "user_message",
  "message_id": "msg_1234567890",
  "content": "How do I create a new appointment?",
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc123xyz",
  "context": {
    "screen": "/scheduler",
    "selected_data": {
      "date": "2026-01-25",
      "time": "10:00"
    },
    "user_action": "clicked_new_appointment_button"
  }
}
```

**Server → Client: Typing Indicator**

```json
{
  "type": "typing",
  "timestamp": "2026-01-20T10:30:01Z",
  "session_id": "session_abc123xyz"
}
```

**Server → Client: Streaming Response (Chunks)**

```json
{
  "type": "assistant_message",
  "message_id": "msg_1234567890",
  "content": "To create a new appointment, you can",
  "is_streaming": true,
  "is_complete": false,
  "timestamp": "2026-01-20T10:30:02Z",
  "session_id": "session_abc123xyz"
}
```

```json
{
  "type": "assistant_message",
  "message_id": "msg_1234567890",
  "content": " click on an empty time slot in the scheduler",
  "is_streaming": true,
  "is_complete": false,
  "timestamp": "2026-01-20T10:30:02.5Z",
  "session_id": "session_abc123xyz"
}
```

**Server → Client: Final Response**

```json
{
  "type": "assistant_message",
  "message_id": "msg_1234567890",
  "content": "To create a new appointment, you can click on an empty time slot in the scheduler, or use the 'New Appointment' button in the top right. Then fill in the patient details, select a procedure type, choose a provider, and set the appointment time.",
  "is_streaming": false,
  "is_complete": true,
  "timestamp": "2026-01-20T10:30:05Z",
  "session_id": "session_abc123xyz",
  "metadata": {
    "tokens_used": 45,
    "model": "gpt-4",
    "response_time_ms": 3000
  }
}
```

### 2. Ping/Pong (Keep-Alive)

**Client → Server: Ping**

```json
{
  "type": "ping",
  "timestamp": "2026-01-20T10:30:00Z"
}
```

**Server → Client: Pong**

```json
{
  "type": "pong",
  "timestamp": "2026-01-20T10:30:00Z"
}
```

**Purpose:** Keep WebSocket connection alive, detect connection issues.

**Frequency:** Client should send ping every 30 seconds if no other messages are sent.

### 3. Clear History

**Client → Server: Clear Conversation History**

```json
{
  "type": "clear_history",
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc123xyz"
}
```

**Server → Client: Confirmation**

```json
{
  "type": "history_cleared",
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc123xyz"
}
```

### 4. Get Context

**Client → Server: Request Current Context**

```json
{
  "type": "get_context",
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc123xyz"
}
```

**Server → Client: Context Response**

```json
{
  "type": "context_update",
  "context": {
    "current_screen": "/scheduler",
    "user_role": "admin",
    "office_id": "O-001",
    "organization_id": "ORG-001",
    "available_actions": [
      "create_appointment",
      "view_patient",
      "edit_appointment"
    ]
  },
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc123xyz"
}
```

---

## Error Handling

### Error Message Format

```json
{
  "type": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": "Additional error details (optional)"
  },
  "message_id": "msg_1234567890", // If error is related to a specific message
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc123xyz"
}
```

### Error Codes

| Code | Description | HTTP Equivalent | Action |
|------|-------------|----------------|--------|
| `AUTH_FAILED` | Invalid or missing authentication token | 401 | Reconnect with valid token |
| `TOKEN_EXPIRED` | Authentication token has expired | 401 | Refresh token and reconnect |
| `RATE_LIMIT_EXCEEDED` | Too many requests in a short time | 429 | Wait before retrying |
| `INVALID_MESSAGE` | Message format is invalid | 400 | Check message structure |
| `CONTEXT_ERROR` | Error processing context data | 400 | Verify context format |
| `MODEL_ERROR` | AI model processing error | 500 | Retry or report issue |
| `SESSION_EXPIRED` | WebSocket session has expired | 440 | Reconnect to create new session |
| `PERMISSION_DENIED` | User doesn't have permission | 403 | Check user permissions |
| `SERVICE_UNAVAILABLE` | AI service is temporarily unavailable | 503 | Retry after delay |

### Error Handling Flow

1. **Client receives error message**
2. **Client checks error code**
3. **Client takes appropriate action:**
   - **AUTH_FAILED / TOKEN_EXPIRED:** Refresh token, reconnect
   - **RATE_LIMIT_EXCEEDED:** Implement exponential backoff
   - **SERVICE_UNAVAILABLE:** Show user-friendly message, retry later
   - **Other errors:** Log error, show user-friendly message

---

## Connection Lifecycle

### 1. Connection Establishment

```
Client                    Server
  |                         |
  |--- WebSocket Connect --->|
  |   (with token)          |
  |                         |
  |<-- connection_ack -------|
  |   (session_id)          |
```

### 2. Normal Message Flow

```
Client                    Server
  |                         |
  |--- user_message ------->|
  |                         |
  |<-- typing --------------|
  |                         |
  |<-- assistant_message ---|
  |   (streaming chunks)    |
  |                         |
  |<-- assistant_message ---|
  |   (final, complete)     |
```

### 3. Connection Termination

**Graceful Disconnect (Client Initiated)**

```
Client                    Server
  |                         |
  |--- WebSocket Close ---->|
  |   (code: 1000)          |
```

**Server Initiated Disconnect**

```json
{
  "type": "connection_closing",
  "reason": "Server maintenance",
  "reconnect_after": 300, // seconds
  "timestamp": "2026-01-20T10:30:00Z"
}
```

**Unexpected Disconnect**

- Client should implement reconnection logic with exponential backoff
- Maximum retry attempts: 5
- Backoff intervals: 1s, 2s, 4s, 8s, 16s

---

## REST Endpoints (Optional)

### 1. Get Chat History

**Endpoint:** `GET /api/v1/ai-chat/history`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `limit` (optional, default: 50): Number of messages to retrieve
- `offset` (optional, default: 0): Pagination offset
- `session_id` (optional): Filter by session ID

**Response:**

```json
{
  "messages": [
    {
      "id": "msg_1234567890",
      "role": "user",
      "content": "How do I create a new appointment?",
      "timestamp": "2026-01-20T10:30:00Z",
      "session_id": "session_abc123xyz"
    },
    {
      "id": "msg_1234567891",
      "role": "assistant",
      "content": "To create a new appointment...",
      "timestamp": "2026-01-20T10:30:05Z",
      "session_id": "session_abc123xyz"
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

### 2. Send Message (REST Fallback)

**Endpoint:** `POST /api/v1/ai-chat/message`

**Headers:**
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "content": "How do I create a new appointment?",
  "context": {
    "screen": "/scheduler",
    "selected_data": {
      "date": "2026-01-25"
    }
  }
}
```

**Response:**

```json
{
  "message_id": "msg_1234567890",
  "content": "To create a new appointment...",
  "timestamp": "2026-01-20T10:30:05Z",
  "metadata": {
    "tokens_used": 45,
    "model": "gpt-4",
    "response_time_ms": 3000
  }
}
```

**Note:** This endpoint is for fallback when WebSocket is unavailable. Prefer WebSocket for real-time streaming.

### 3. Clear Chat History

**Endpoint:** `DELETE /api/v1/ai-chat/history`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `session_id` (optional): Clear specific session, or all sessions if omitted

**Response:**

```json
{
  "status": "success",
  "message": "Chat history cleared",
  "sessions_cleared": 1
}
```

### 4. Get Session Info

**Endpoint:** `GET /api/v1/ai-chat/session`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**

```json
{
  "session_id": "session_abc123xyz",
  "created_at": "2026-01-20T10:00:00Z",
  "last_activity": "2026-01-20T10:30:00Z",
  "message_count": 10,
  "status": "active"
}
```

---

## Future Extensibility

### Context-Aware Actions

The message protocol includes a `context` field to support future context-aware features:

```json
{
  "type": "user_message",
  "content": "Create an appointment for this patient",
  "context": {
    "screen": "/patient/CH011/overview",
    "selected_data": {
      "patient_id": "CH011",
      "patient_name": "John Doe"
    },
    "user_action": "clicked_create_appointment",
    "available_actions": [
      "create_appointment",
      "view_patient_details"
    ]
  }
}
```

### Task Execution Commands

Future support for executing actions directly from chat:

**Client → Server: Execute Action**

```json
{
  "type": "execute_action",
  "action": "create_appointment",
  "parameters": {
    "patient_id": "CH011",
    "date": "2026-01-25",
    "time": "10:00",
    "procedure_type": "Cleaning"
  },
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc123xyz"
}
```

**Server → Client: Action Result**

```json
{
  "type": "action_result",
  "action": "create_appointment",
  "status": "success",
  "result": {
    "appointment_id": "APT-001",
    "message": "Appointment created successfully"
  },
  "timestamp": "2026-01-20T10:30:05Z",
  "session_id": "session_abc123xyz"
}
```

### Streaming Support

The protocol already supports streaming responses. The backend should:

1. Send multiple `assistant_message` chunks with `is_streaming: true`
2. Send final chunk with `is_streaming: false` and `is_complete: true`
3. Client should concatenate chunks to build the complete response

---

## Implementation Notes

### Backend Requirements

1. **WebSocket Server:**
   - Use a WebSocket library (e.g., `websockets` for Python, `ws` for Node.js)
   - Implement connection pooling and session management
   - Handle reconnection gracefully

2. **Authentication:**
   - Validate JWT token on connection
   - Refresh token validation periodically
   - Handle token expiration during active sessions

3. **Message Queue:**
   - Queue messages if AI service is temporarily unavailable
   - Implement retry logic for failed AI requests

4. **Rate Limiting:**
   - Implement rate limiting per user/session
   - Suggested limits:
     - 60 messages per minute per user
     - 1000 messages per hour per user

5. **Session Management:**
   - Store session state (conversation history, context)
   - Session timeout: 30 minutes of inactivity
   - Clean up expired sessions

6. **AI Integration:**
   - Integrate with AI service (OpenAI, Anthropic, or custom)
   - Support streaming responses
   - Handle AI service errors gracefully

### Frontend Implementation

The frontend should:

1. **Connection Management:**
   - Connect WebSocket on component mount (when authenticated)
   - Implement reconnection logic with exponential backoff
   - Handle connection errors gracefully

2. **Message Handling:**
   - Queue outgoing messages if connection is down
   - Display streaming responses in real-time
   - Store conversation history in localStorage as backup

3. **Error Handling:**
   - Show user-friendly error messages
   - Implement retry logic for transient errors
   - Handle token expiration and refresh

4. **Performance:**
   - Debounce rapid message sends
   - Limit conversation history length (e.g., last 100 messages)
   - Implement message pagination for long conversations

---

## Example Implementation Flow

### Complete Conversation Example

```
1. Client connects WebSocket with token
   → Server responds with connection_ack

2. Client sends user message:
   {
     "type": "user_message",
     "message_id": "msg_001",
     "content": "How do I schedule an appointment?",
     "context": { "screen": "/scheduler" }
   }

3. Server responds with typing indicator:
   {
     "type": "typing"
   }

4. Server streams response chunks:
   {
     "type": "assistant_message",
     "message_id": "msg_001",
     "content": "To schedule an appointment,",
     "is_streaming": true,
     "is_complete": false
   }
   ... (more chunks) ...
   {
     "type": "assistant_message",
     "message_id": "msg_001",
     "content": " click on an empty time slot.",
     "is_streaming": false,
     "is_complete": true
   }

5. Client sends ping every 30 seconds to keep connection alive

6. Client closes connection gracefully when done
```

---

## Security Considerations

1. **Authentication:**
   - Always validate JWT tokens
   - Use HTTPS/WSS in production
   - Implement token refresh mechanism

2. **Rate Limiting:**
   - Prevent abuse with rate limits
   - Monitor for suspicious activity

3. **Input Validation:**
   - Validate and sanitize all user inputs
   - Limit message length (e.g., 4000 characters)

4. **Context Data:**
   - Validate context data structure
   - Sanitize sensitive information before sending to AI

5. **Session Security:**
   - Use secure session IDs
   - Implement session timeout
   - Clear sensitive data on session end

---

## Testing

### Test Cases

1. **Connection:**
   - Valid token connection
   - Invalid token rejection
   - Expired token handling

2. **Messaging:**
   - Send and receive messages
   - Streaming response handling
   - Error message handling

3. **Reconnection:**
   - Automatic reconnection on disconnect
   - Message queue on reconnection
   - Session restoration

4. **Rate Limiting:**
   - Rate limit enforcement
   - Rate limit error handling

5. **Context:**
   - Context data transmission
   - Context-aware responses

---

## Version History

- **v1.0.0** (2026-01-20): Initial API contract specification

---

## Support

For questions or clarifications about this API contract, please contact the development team.
