# AI Chat Assistant for Scheduler

This module implements a conversational AI Chat Assistant that can create, update, and delete scheduler appointments using natural language interactions.

## Features

- **Natural Language Processing**: Understands user intents for appointment management
- **Conversational Workflow**: Asks follow-up questions when information is missing
- **Real-time Communication**: WebSocket-based bidirectional communication
- **State Management**: Maintains conversation context and state
- **Integration**: Uses existing scheduler services and APIs

## Architecture

### Components

1. **WebSocket Handler** (`websocket_handler.py`): Manages WebSocket connections and message routing
2. **AI Agent** (`agent.py`): LangChain agent with Google Vertex AI (Gemini) integration
3. **State Management** (`state.py`): Conversation state and session management
4. **Schemas** (`schemas.py`): Pydantic models for API contracts
5. **Routes** (`routes.py`): REST endpoints for fallback and session management

### Technology Stack

- **LangChain**: Agent orchestration framework
- **Google Vertex AI (Gemini)**: Large Language Model
- **FastAPI WebSocket**: Real-time bidirectional communication
- **SQLAlchemy**: Database integration

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `langchain>=0.1.0`
- `langchain-google-vertexai>=1.0.0`
- `google-cloud-aiplatform>=1.38.0`
- `websockets>=12.0`

### 2. Configure Google Cloud

Set environment variables:

```bash
export GOOGLE_CLOUD_PROJECT_ID="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"  # Optional, default: us-central1
export GEMINI_MODEL_NAME="gemini-pro"  # Optional, default: gemini-pro
```

Or add to `.env` file:

```
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL_NAME=gemini-pro
```

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

Or set service account key:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

## API Endpoints

### WebSocket

**Endpoint:** `ws://localhost:8000/api/v1/ai-chat/ws?token=<access_token>`

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ai-chat/ws?token=YOUR_TOKEN');

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};

ws.send(JSON.stringify({
  type: 'user_message',
  content: 'Create an appointment for John Doe on January 25th at 10am',
  timestamp: new Date().toISOString()
}));
```

### REST Endpoints

#### Get Chat History
```
GET /api/v1/ai-chat/history?limit=50&offset=0&session_id=optional
```

#### Send Message (Fallback)
```
POST /api/v1/ai-chat/message
Content-Type: application/json
Authorization: Bearer <token>

{
  "content": "Create an appointment for John Doe on January 25th at 10am",
  "context": {
    "screen": "/scheduler"
  }
}
```

#### Clear Chat History
```
DELETE /api/v1/ai-chat/history?session_id=optional
```

#### Get Session Info
```
GET /api/v1/ai-chat/session
```

## Usage Examples

### Create Appointment

**User:** "Create an appointment for patient CH001 on January 25th at 10am for a cleaning"

**AI:** "I'll create that appointment. I need a few more details:
- What's the duration? (default: 60 minutes)
- Which operatory?
- Which provider?"

**User:** "60 minutes, Operatory 1, Dr. Smith"

**AI:** "Appointment created successfully. ID: 123, Patient: John Doe, Date: 2026-01-25, Time: 10:00"

### Update Appointment

**User:** "Change appointment 123 to 2pm"

**AI:** "Appointment 123 updated successfully. Date: 2026-01-25, Time: 14:00"

### Delete Appointment

**User:** "Cancel appointment 123"

**AI:** "Appointment 123 deleted successfully"

## Message Protocol

### Client → Server

```json
{
  "type": "user_message",
  "message_id": "msg_123",
  "content": "Create an appointment",
  "timestamp": "2026-01-20T10:30:00Z",
  "session_id": "session_abc",
  "context": {
    "screen": "/scheduler",
    "selected_data": {
      "date": "2026-01-25"
    }
  }
}
```

### Server → Client

```json
{
  "type": "assistant_message",
  "message_id": "msg_123",
  "content": "I'll help you create an appointment...",
  "is_streaming": false,
  "is_complete": true,
  "timestamp": "2026-01-20T10:30:05Z",
  "session_id": "session_abc",
  "metadata": {
    "tokens_used": 45,
    "model": "gemini-2.5-pro",
    "response_time_ms": 3000
  }
}
```

## Error Handling

The system handles various error scenarios:

- **Authentication Errors**: Invalid or expired tokens
- **Model Errors**: AI service unavailable or processing errors
- **Validation Errors**: Invalid message format or missing required fields
- **Database Errors**: Connection issues or constraint violations

Error responses follow this format:

```json
{
  "type": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": "Additional details"
  },
  "timestamp": "2026-01-20T10:30:00Z"
}
```

## Conversation State

The system maintains conversation state including:

- **Messages**: Full conversation history (last 100 messages)
- **Context**: Current screen, selected data, user actions
- **Pending Intent**: Current operation being performed
- **Pending Entities**: Extracted information waiting for confirmation
- **Required Fields**: Fields still needed to complete the operation

## Security

- **Authentication**: JWT token required for all connections
- **Authorization**: User permissions checked before operations
- **Rate Limiting**: Recommended: 60 messages/minute per user
- **Input Validation**: All inputs validated and sanitized
- **Session Timeout**: Sessions expire after 30 minutes of inactivity

## Troubleshooting

### LangChain Import Errors

If you see `LangChain not available` errors:

```bash
pip install langchain langchain-google-vertexai
```

### Google Cloud Authentication Errors

Ensure you're authenticated:

```bash
gcloud auth application-default login
```

Or set service account:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
```

### WebSocket Connection Issues

1. Check token is valid and not expired
2. Verify WebSocket URL format: `ws://host:port/api/v1/ai-chat/ws?token=...`
3. Check CORS settings if connecting from browser

## Future Enhancements

- True streaming responses (token-by-token)
- Multi-turn conversation optimization
- Context-aware suggestions
- Voice input/output support
- Multi-language support
- Advanced entity extraction
- Appointment conflict detection and suggestions
