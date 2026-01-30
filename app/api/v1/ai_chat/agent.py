"""
AI Agent service using LangChain and Google Vertex AI (Gemini).
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from datetime import datetime
from app.core.config import settings

# Initialize type hints (will be overridden if import succeeds)
if TYPE_CHECKING:
    from langchain_core.runnables import Runnable
else:
    Runnable = Any  # type: ignore

try:
    from langchain_google_vertexai import ChatVertexAI
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
    from langchain_core.tools import Tool
    from langchain_core.runnables import Runnable  # Override the Any fallback
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    LANGCHAIN_AVAILABLE = False
    logging.error(f"LangChain not available: {e}. Please install: pip install langchain langchain-google-vertexai")
    # Runnable is already set to Any above, so no need to redefine

from app.api.v1.ai_chat.state import ConversationState
from app.api.v1.ai_chat.guides import search_guides, get_guide_by_id, get_all_guides
from app.api.v1.scheduler.services import (
    create_appointment,
    update_appointment,
    get_appointment_by_id,
    delete_appointment,
    get_operatories,
    get_providers,
    get_procedure_types
)
from app.api.v1.scheduler.schemas import (
    OperatoryResponse,
    ProviderResponse,
    ProcedureTypeResponse
)
from app.api.v1.scheduler.schemas import AppointmentCreate, AppointmentUpdate
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SchedulerAgent:
    """AI Agent for scheduler appointment management"""
    
    def __init__(self, db: Session, user_id: int, tenant_id: int, office_id: int):
        self.db = db
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.office_id = office_id
        
        if not LANGCHAIN_AVAILABLE:
            logger.error("LangChain not available. Please install: pip install langchain langchain-google-vertexai")
            raise ImportError("LangChain dependencies not installed")
        
        # Initialize Vertex AI (Gemini)
        self.llm = self._initialize_llm()
        
        # Create scheduler tools
        self.tools = self._create_tools()
        
        # Create agent
        self.agent = self._create_agent()
        
        # Cache for validation data (refresh on each request to ensure freshness)
        self._operatories_cache = None
        self._procedure_types_cache = None
        self._providers_cache = None
    
    def _initialize_llm(self):
        """Initialize Google Vertex AI (Gemini) LLM"""
        try:
            # Get project ID from environment or config
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID") or settings.GOOGLE_CLOUD_PROJECT_ID or "dental-app-dev-483317"
            location = os.getenv("GOOGLE_CLOUD_LOCATION") or settings.GOOGLE_CLOUD_LOCATION or "us-central1"
            
            # Force use gemini-2.5-pro - prioritize config default over env var
            # Check if env var is explicitly set to gemini-pro and override it
            env_model = os.getenv("GEMINI_MODEL_NAME")
            if env_model == "gemini-pro":
                logger.warning(f"Environment variable GEMINI_MODEL_NAME is set to 'gemini-pro', overriding to 'gemini-2.5-pro'")
                model_name = "gemini-2.5-pro"
            else:
                # Use config settings first, then environment variable, then default
                model_name = settings.GEMINI_MODEL_NAME or env_model or "gemini-2.5-pro"
            
            if not project_id:
                logger.warning("GOOGLE_CLOUD_PROJECT_ID not set. Using default configuration.")
                # Try to infer from default credentials
                project_id = "default-project"
            
            logger.info(f"Using Gemini model: {model_name} (from config: {settings.GEMINI_MODEL_NAME}, from env: {env_model})")
            
            llm = ChatVertexAI(
                model_name=model_name,
                project=project_id,
                location=location,
                temperature=0.7,
                max_output_tokens=2048,
            )
            
            logger.info(f"Initialized Vertex AI LLM: {model_name} in {location}")
            return llm
        
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI LLM: {e}")
            raise
    
    def _create_tools(self) -> List[Tool]:
        """Create LangChain tools for scheduler operations"""
        
        def create_appointment_tool(query: str) -> str:
            """Tool to create a new appointment. Input should be a JSON string with appointment details."""
            try:
                logger.info(f"[TOOL] Parsing JSON query")
                data = json.loads(query)
                logger.debug(f"[TOOL] Parsed data (before unwrap): {data}")
                
                # CRITICAL FIX: LangChain/Gemini wraps arguments in __arg1 when tool has single string parameter
                if "__arg1" in data and isinstance(data["__arg1"], str):
                    logger.info(f"[TOOL] Unwrapping __arg1")
                    data = json.loads(data["__arg1"])
                    logger.debug(f"[TOOL] Unwrapped data: {data}")
                
                # Map natural language data to AppointmentCreate schema
                logger.info(f"[TOOL] Mapping data to AppointmentCreate schema")
                appointment_data = self._map_to_appointment_create(data)
                logger.info(f"[TOOL] Mapped appointment data. patient_id={appointment_data.patient_id}, date={appointment_data.date}, start_time={appointment_data.start_time}")
                logger.debug(f"[TOOL] Full appointment data: {appointment_data.model_dump()}")
                
                logger.info(f"[TOOL] Calling create_appointment service with office_id={self.office_id}")
                result = create_appointment(
                    db=self.db,
                    payload=appointment_data,
                    office_id=self.office_id
                )
                logger.info(f"[TOOL] create_appointment service returned. appointment_id={result.id}")
                
                success_msg = f"Appointment created successfully. ID: {result.id}, Patient: {result.patient_name}, Date: {result.date}, Time: {result.start_time}"
                logger.info(f"[TOOL] Returning success message: {success_msg}")
                return success_msg
            
            except json.JSONDecodeError as e:
                logger.error(f"[TOOL] JSON decode error in create_appointment_tool: {e}")
                logger.debug(f"[TOOL] Query that failed to parse: {query}")
                return f"Error: Invalid JSON format. {str(e)}"
            except Exception as e:
                logger.error(f"[TOOL] Error creating appointment: {e}", exc_info=True)
                return f"Error creating appointment: {str(e)}"
        
        def update_appointment_tool(query: str) -> str:
            """Tool to update an existing appointment. Input should be a JSON string with appointment_id and update fields."""
            try:
                data = json.loads(query)
                logger.debug(f"[TOOL] Parsed data (before unwrap): {data}")
                
                # CRITICAL FIX: LangChain/Gemini wraps arguments in __arg1 when tool has single string parameter
                if "__arg1" in data and isinstance(data["__arg1"], str):
                    logger.info(f"[TOOL] Unwrapping __arg1")
                    data = json.loads(data["__arg1"])
                    logger.debug(f"[TOOL] Unwrapped data: {data}")
                
                appointment_id = data.get("appointment_id") or data.get("id")
                
                if not appointment_id:
                    return "Error: appointment_id is required for update"
                
                # Map to AppointmentUpdate schema
                update_data = self._map_to_appointment_update(data)
                
                result = update_appointment(
                    db=self.db,
                    appointment_id=int(appointment_id),
                    payload=update_data
                )
                
                if result:
                    return f"Appointment {appointment_id} updated successfully. Date: {result.date}, Time: {result.start_time}"
                else:
                    return f"Appointment {appointment_id} not found"
            
            except Exception as e:
                logger.error(f"Error updating appointment: {e}")
                return f"Error updating appointment: {str(e)}"
        
        def get_appointment_tool(query: str) -> str:
            """Tool to get appointment details. Input should be appointment_id."""
            try:
                logger.info(f"[TOOL] get_appointment_tool called with query: '{query}'")
                # CRITICAL FIX: LangChain/Gemini wraps arguments in __arg1 when tool has single string parameter
                appointment_id = None
                try:
                    # Try parsing as JSON first
                    data = json.loads(query)
                    logger.debug(f"[TOOL] Parsed as JSON: {data}")
                    if "__arg1" in data:
                        appointment_id_str = data["__arg1"]
                        # If it's a JSON string, parse it again
                        if isinstance(appointment_id_str, str) and (appointment_id_str.startswith('"') or appointment_id_str.startswith('{')):
                            if appointment_id_str.startswith('"'):
                                appointment_id_str = appointment_id_str.strip('"')
                            else:
                                # It's a nested JSON string
                                nested_data = json.loads(appointment_id_str)
                                appointment_id_str = nested_data.get("__arg1", appointment_id_str)
                        appointment_id = int(appointment_id_str)
                    else:
                        # Try to find appointment_id in the data
                        appointment_id = int(data.get("appointment_id") or data.get("id") or query.strip())
                except (json.JSONDecodeError, ValueError, KeyError):
                    # Not JSON or can't parse, try as direct integer
                    logger.debug(f"[TOOL] Not JSON, trying as direct integer")
                    appointment_id = int(query.strip())
                
                logger.info(f"[TOOL] Extracted appointment_id: {appointment_id}")
                result = get_appointment_by_id(self.db, appointment_id)
                
                if result:
                    return f"Appointment {appointment_id}: Patient: {result.patient_name}, Date: {result.date}, Time: {result.start_time}, Status: {result.status}"
                else:
                    return f"Appointment {appointment_id} not found"
            
            except Exception as e:
                logger.error(f"Error getting appointment: {e}")
                return f"Error getting appointment: {str(e)}"
        
        def delete_appointment_tool(query: str) -> str:
            """Tool to delete/cancel an appointment. Input should be appointment_id."""
            try:
                logger.info(f"[TOOL] delete_appointment_tool called with query: '{query}'")
                # CRITICAL FIX: LangChain/Gemini wraps arguments in __arg1 when tool has single string parameter
                appointment_id = None
                try:
                    # Try parsing as JSON first
                    data = json.loads(query)
                    logger.debug(f"[TOOL] Parsed as JSON: {data}")
                    if "__arg1" in data:
                        appointment_id_str = data["__arg1"]
                        # If it's a JSON string, parse it again
                        if isinstance(appointment_id_str, str) and (appointment_id_str.startswith('"') or appointment_id_str.startswith('{')):
                            if appointment_id_str.startswith('"'):
                                appointment_id_str = appointment_id_str.strip('"')
                            else:
                                # It's a nested JSON string
                                nested_data = json.loads(appointment_id_str)
                                appointment_id_str = nested_data.get("__arg1", appointment_id_str)
                        appointment_id = int(appointment_id_str)
                    else:
                        # Try to find appointment_id in the data
                        appointment_id = int(data.get("appointment_id") or data.get("id") or query.strip())
                except (json.JSONDecodeError, ValueError, KeyError):
                    # Not JSON or can't parse, try as direct integer
                    logger.debug(f"[TOOL] Not JSON, trying as direct integer")
                    appointment_id = int(query.strip())
                
                logger.info(f"[TOOL] Extracted appointment_id: {appointment_id}")
                result = delete_appointment(self.db, appointment_id)
                
                if result:
                    return f"Appointment {appointment_id} deleted successfully"
                else:
                    return f"Appointment {appointment_id} not found"
            
            except Exception as e:
                logger.error(f"Error deleting appointment: {e}")
                return f"Error deleting appointment: {str(e)}"
        
        def get_task_guide_tool(query: str) -> str:
            """Tool to get step-by-step guide for performing a task in the system. Use this when user asks 'how to' questions or wants instructions on how to do something."""
            try:
                logger.info(f"[TOOL] get_task_guide_tool called with query: '{query}'")
                
                # Handle JSON wrapping
                search_query = query
                try:
                    data = json.loads(query)
                    if "__arg1" in data and isinstance(data["__arg1"], str):
                        search_query = data["__arg1"]
                    elif isinstance(data, dict) and "query" in data:
                        search_query = data["query"]
                    elif isinstance(data, str):
                        search_query = data
                except (json.JSONDecodeError, KeyError, TypeError):
                    # Not JSON, use query as-is
                    pass
                
                logger.info(f"[TOOL] Searching guides with query: '{search_query}'")
                
                # Search for matching guides
                guides = search_guides(search_query)
                
                if not guides:
                    # If no matches, try to get all guides and suggest some
                    all_guides = get_all_guides()
                    if all_guides:
                        available_tasks = "\n".join([f"  - {g.title}" for g in all_guides[:10]])
                        return f"I couldn't find a specific guide for '{search_query}'. Here are some available guides:\n\n{available_tasks}\n\nTry asking about one of these tasks, or rephrase your question."
                    else:
                        return f"I couldn't find a guide for '{search_query}'. Please try rephrasing your question or ask about a specific task like 'how to add a procedure' or 'how to create an appointment'."
                
                # If multiple matches, return the most relevant one or list them
                if len(guides) == 1:
                    guide = guides[0]
                    logger.info(f"[TOOL] Found guide: {guide.task_id} - {guide.title}")
                    return guide.format_for_response()
                else:
                    # Multiple matches - return the first one with a note about others
                    guide = guides[0]
                    other_guides = "\n".join([f"  - {g.title}" for g in guides[1:5]])
                    response = guide.format_for_response()
                    if other_guides:
                        response += f"\n\n**Other related guides:**\n{other_guides}"
                    return response
            
            except Exception as e:
                logger.error(f"Error getting task guide: {e}", exc_info=True)
                return f"Error retrieving guide: {str(e)}"
        
        return [
            Tool(
                name="create_appointment",
                func=create_appointment_tool,
                description="Create a new appointment. Input: JSON string with patient_id, date (YYYY-MM-DD), start_time (HH:MM), duration (REQUIRED - number in minutes, e.g., 10, 30, 60, 90), procedure_type, operatory, provider, and optional fields like notes, status. IMPORTANT: duration must be a number (extract from user input like '10 minutes' → 10)."
            ),
            Tool(
                name="update_appointment",
                func=update_appointment_tool,
                description="Update an existing appointment. Input: JSON string with appointment_id and fields to update (date, time, duration, patient_id, etc.)."
            ),
            Tool(
                name="get_appointment",
                func=get_appointment_tool,
                description="Get appointment details by ID. Input: appointment_id as integer."
            ),
            Tool(
                name="delete_appointment",
                func=delete_appointment_tool,
                description="Delete or cancel an appointment. Input: appointment_id as integer."
            ),
            Tool(
                name="get_task_guide",
                func=get_task_guide_tool,
                description="Get step-by-step instructions for how to perform a task in the dental practice management system. Use this tool when the user asks 'how to' questions, wants instructions, or needs guidance on performing a specific task. Examples: 'how to add a procedure', 'how to create a claim', 'how to add a payment', 'how to create an appointment', 'how to search for patients'. Input: A search query string describing the task (e.g., 'add procedure to ledger', 'create claim', 'new patient')."
            ),
        ]
    
    def _get_validation_data(self) -> tuple:
        """Get operatories, procedure types, and providers for validation"""
        if self._operatories_cache is None:
            self._operatories_cache = get_operatories(self.db, self.office_id)
        if self._procedure_types_cache is None:
            self._procedure_types_cache = get_procedure_types(self.db)
        if self._providers_cache is None:
            self._providers_cache = get_providers(self.db, self.office_id)
        return self._operatories_cache, self._procedure_types_cache, self._providers_cache
    
    def _validate_procedure_type(self, user_input: str) -> str:
        """
        Validate that user input matches a valid procedure type name.
        The LLM should already have matched it, but we validate to ensure data integrity.
        
        Args:
            user_input: User's input for procedure type (should already be matched by LLM)
        
        Returns:
            Validated procedure type name
        
        Raises:
            ValueError: If input doesn't match any valid procedure type
        """
        if not user_input:
            raise ValueError("Procedure type is required")
        
        _, procedure_types, _ = self._get_validation_data()
        procedure_names = [pt.name for pt in procedure_types]
        
        # Try exact match (case-insensitive)
        user_input_lower = user_input.lower().strip()
        for pt_name in procedure_names:
            if pt_name.lower().strip() == user_input_lower:
                logger.info(f"[AGENT] Validated procedure type: '{user_input}' -> '{pt_name}'")
                return pt_name
        
        # No match found
        available_types = ", ".join(procedure_names[:10])  # Show first 10
        raise ValueError(f"Invalid procedure type '{user_input}'. Available types: {available_types}{'...' if len(procedure_names) > 10 else ''}")
    
    def _validate_operatory(self, user_input: str) -> str:
        """
        Validate that user input matches a valid operatory ID or name.
        The LLM should already have matched it, but we validate to ensure data integrity.
        
        Args:
            user_input: User's input for operatory (should already be matched by LLM)
        
        Returns:
            Validated operatory ID
        
        Raises:
            ValueError: If input doesn't match any valid operatory
        """
        if not user_input:
            raise ValueError("Operatory is required")
        
        operatories, _, _ = self._get_validation_data()
        
        # Try exact match on ID first
        user_input_upper = user_input.upper().strip()
        for op in operatories:
            if op.id.upper().strip() == user_input_upper:
                logger.info(f"[AGENT] Validated operatory ID: '{user_input}' -> '{op.id}'")
                return op.id
        
        # Try exact match on name (case-insensitive)
        user_input_lower = user_input.lower().strip()
        for op in operatories:
            if op.name.lower().strip() == user_input_lower:
                logger.info(f"[AGENT] Validated operatory name: '{user_input}' -> '{op.id}' (name: '{op.name}')")
                return op.id
        
        # No match found
        available_ops = ", ".join([f"{op.id} ({op.name})" for op in operatories[:5]])  # Show first 5
        raise ValueError(f"Invalid operatory '{user_input}'. Available operatories: {available_ops}{'...' if len(operatories) > 5 else ''}")
    
    def _validate_provider(self, user_input: str) -> str:
        """
        Validate that user input matches a valid provider name.
        The LLM should already have matched it, but we validate to ensure data integrity.
        
        Args:
            user_input: User's input for provider name (should already be matched by LLM)
        
        Returns:
            Validated provider name
        
        Raises:
            ValueError: If input doesn't match any valid provider
        """
        if not user_input:
            raise ValueError("Provider is required")
        
        _, _, providers = self._get_validation_data()
        provider_names = [p.name for p in providers]
        
        # Try exact match (case-insensitive)
        user_input_lower = user_input.lower().strip()
        for provider_name in provider_names:
            if provider_name.lower().strip() == user_input_lower:
                logger.info(f"[AGENT] Validated provider: '{user_input}' -> '{provider_name}'")
                return provider_name
        
        # No match found
        available_providers = ", ".join(provider_names[:10])  # Show first 10
        raise ValueError(f"Invalid provider '{user_input}'. Available providers: {available_providers}{'...' if len(provider_names) > 10 else ''}")
    
    def _map_to_appointment_create(self, data: Dict[str, Any]) -> AppointmentCreate:
        """Map natural language data to AppointmentCreate schema"""
        from datetime import datetime
        
        # Extract and normalize date
        date_str = data.get("date") or data.get("appointment_date")
        if isinstance(date_str, str):
            # Try to parse various date formats
            try:
                # Try ISO format first
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                # Try other formats if needed
                pass
        
        # Extract and normalize time
        time_str = data.get("time") or data.get("start_time") or data.get("startTime")
        if isinstance(time_str, str):
            # Normalize time format to HH:MM
            if ":" not in time_str:
                # Handle formats like "10am", "2pm"
                time_str = self._normalize_time(time_str)
        elif not time_str:
            # If time is missing, log warning
            logger.warning(f"[AGENT] Time field is missing in data. Available keys: {list(data.keys())}")
            time_str = ""
        
        # Ensure time_str is a string and properly formatted
        if time_str and isinstance(time_str, str):
            # Validate format is HH:MM
            import re
            if not re.match(r'^\d{2}:\d{2}$', time_str):
                # Try to normalize again
                time_str = self._normalize_time(time_str)
        
        logger.debug(f"[AGENT] Mapped time_str: '{time_str}' (type: {type(time_str).__name__})")
        
        # Validate and normalize procedure_type, operatory, and provider
        procedure_type_input = data.get("procedure_type") or data.get("procedureType") or ""
        operatory_input = data.get("operatory") or ""
        provider_input = data.get("provider") or ""
        
        validated_procedure_type = ""
        validated_operatory = ""
        validated_provider = ""
        validation_errors = []
        
        # Validate procedure_type (LLM should have already matched it correctly)
        if procedure_type_input:
            try:
                validated_procedure_type = self._validate_procedure_type(procedure_type_input)
            except ValueError as e:
                validation_errors.append(str(e))
        else:
            validation_errors.append("Procedure type is required")
        
        # Validate operatory (LLM should have already matched it correctly)
        if operatory_input:
            try:
                validated_operatory = self._validate_operatory(operatory_input)
            except ValueError as e:
                validation_errors.append(str(e))
        else:
            validation_errors.append("Operatory is required")
        
        # Validate provider (LLM should have already matched it correctly)
        if provider_input:
            try:
                validated_provider = self._validate_provider(provider_input)
            except ValueError as e:
                validation_errors.append(str(e))
        else:
            validation_errors.append("Provider is required")
        
        # If any validation errors, raise exception
        if validation_errors:
            error_msg = "Validation errors: " + "; ".join(validation_errors)
            logger.error(f"[AGENT] {error_msg}")
            raise ValueError(error_msg)
        
        # Extract and normalize duration
        duration_input = data.get("duration") or data.get("duration_minutes") or data.get("durationMinutes")
        duration_value = 60  # Default fallback
        
        if duration_input is not None:
            try:
                # If it's already a number, use it directly
                if isinstance(duration_input, (int, float)):
                    duration_value = int(duration_input)
                elif isinstance(duration_input, str):
                    # Try to extract number from string (e.g., "10 minutes", "10 mins", "10")
                    import re
                    # Extract first number found in the string
                    match = re.search(r'\d+', duration_input)
                    if match:
                        duration_value = int(match.group())
                        logger.info(f"[AGENT] Extracted duration from '{duration_input}': {duration_value} minutes")
                    else:
                        logger.warning(f"[AGENT] Could not extract duration from '{duration_input}', using default 60")
                else:
                    duration_value = int(duration_input)
            except (ValueError, TypeError) as e:
                logger.warning(f"[AGENT] Error parsing duration '{duration_input}': {e}, using default 60")
        else:
            logger.warning(f"[AGENT] Duration not provided in data, using default 60. Available keys: {list(data.keys())}")
        
        # Validate duration is reasonable (1-480 minutes)
        if duration_value < 1:
            logger.warning(f"[AGENT] Duration {duration_value} is too small, setting to 15 minutes")
            duration_value = 15
        elif duration_value > 480:
            logger.warning(f"[AGENT] Duration {duration_value} is too large, setting to 480 minutes")
            duration_value = 480
        
        logger.debug(f"[AGENT] Final duration value: {duration_value} minutes")
        
        return AppointmentCreate(
            patient_id=data.get("patient_id") or data.get("patientId") or "",
            date=date_str or "",
            start_time=time_str or "",
            duration=duration_value,
            procedure_type=validated_procedure_type,  # Use validated value
            operatory=validated_operatory,  # Use validated value
            provider=validated_provider,  # Use validated value
            notes=data.get("notes") or "",
            status=data.get("status") or "Scheduled"
        )
    
    def _map_to_appointment_update(self, data: Dict[str, Any]) -> AppointmentUpdate:
        """Map natural language data to AppointmentUpdate schema with validation"""
        update_data = {}
        validation_errors = []
        
        if "date" in data or "appointment_date" in data:
            update_data["date"] = data.get("date") or data.get("appointment_date")
        
        if "time" in data or "start_time" in data or "startTime" in data:
            time_str = data.get("time") or data.get("start_time") or data.get("startTime")
            update_data["start_time"] = self._normalize_time(time_str) if time_str else None
        
        if "duration" in data:
            update_data["duration"] = int(data["duration"])
        
        if "patient_id" in data or "patientId" in data:
            update_data["patient_id"] = data.get("patient_id") or data.get("patientId")
        
        # Validate procedure_type if provided (LLM should have already matched it correctly)
        if "procedure_type" in data or "procedureType" in data:
            procedure_type_input = data.get("procedure_type") or data.get("procedureType")
            if procedure_type_input:
                try:
                    update_data["procedure_type"] = self._validate_procedure_type(procedure_type_input)
                except ValueError as e:
                    validation_errors.append(str(e))
        
        # Validate operatory if provided (LLM should have already matched it correctly)
        if "operatory" in data:
            operatory_input = data.get("operatory")
            if operatory_input:
                try:
                    update_data["operatory"] = self._validate_operatory(operatory_input)
                except ValueError as e:
                    validation_errors.append(str(e))
        
        # Validate provider if provided (LLM should have already matched it correctly)
        if "provider" in data:
            provider_input = data.get("provider")
            if provider_input:
                try:
                    update_data["provider"] = self._validate_provider(provider_input)
                except ValueError as e:
                    validation_errors.append(str(e))
        
        if "notes" in data:
            update_data["notes"] = data["notes"]
        
        if "status" in data:
            update_data["status"] = data["status"]
        
        # If any validation errors, raise exception
        if validation_errors:
            error_msg = "Validation errors: " + "; ".join(validation_errors)
            logger.error(f"[AGENT] {error_msg}")
            raise ValueError(error_msg)
        
        return AppointmentUpdate(**update_data)
    
    def _normalize_time(self, time_str: str) -> str:
        """Normalize time string to HH:MM format"""
        import re
        
        # Remove whitespace and convert to lowercase
        time_str = time_str.strip().lower()
        
        # Handle formats like "10am", "2pm", "10:30am"
        if "am" in time_str or "pm" in time_str:
            is_pm = "pm" in time_str
            time_str = re.sub(r"[amp\s]", "", time_str)
            
            if ":" in time_str:
                hour, minute = map(int, time_str.split(":"))
            else:
                hour = int(time_str)
                minute = 0
            
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0
            
            return f"{hour:02d}:{minute:02d}"
        
        # Already in HH:MM format
        if ":" in time_str:
            return time_str
        
        # Assume it's just hours
        try:
            hour = int(time_str)
            return f"{hour:02d}:00"
        except ValueError:
            return "09:00"  # Default
    
    # def _create_agent(self) -> Runnable:
    def _create_agent(self) -> Runnable:
        """Create LangChain agent by binding tools to LLM"""
        # Bind tools directly to the LLM
        # This works with any LangChain version that supports tool binding
        agent = self.llm.bind_tools(self.tools)
        
        return agent
    
    def process_message(
        self,
        user_message: str,
        conversation_state: ConversationState,
        max_retries: int = 3
    ) -> str:
        """Process user message and return AI response with retry logic"""
        logger.info(f"[AGENT] process_message called with user_message: '{user_message[:100]}...' (length: {len(user_message)})")
        logger.info(f"[AGENT] Conversation state has {len(conversation_state.messages)} messages")
        
        # Add user message to conversation history
        conversation_state.add_message("user", user_message)
        logger.info(f"[AGENT] Added user message to conversation history. Total messages: {len(conversation_state.messages)}")
        
        last_error = None
        for attempt in range(max_retries):
            try:
                # Build message history
                messages = []
                
                # Get available options for the system prompt
                operatories, procedure_types, providers = self._get_validation_data()
                
                # Format available options
                procedure_type_list = ", ".join([pt.name for pt in procedure_types])
                operatory_list = ", ".join([f"{op.id} ({op.name})" for op in operatories])
                provider_list = ", ".join([p.name for p in providers])
                
                # Add system message with available options
                system_msg = f"""You are a helpful AI assistant for a dental practice management system.

                                You have access to external tools (functions) for:
                                - create_appointment: Create new appointments
                                - update_appointment: Update existing appointments
                                - delete_appointment: Delete/cancel appointments
                                - get_appointment: Get appointment details
                                - get_task_guide: Get step-by-step instructions for how to perform tasks in the system

                                IMPORTANT: When users ask "how to" questions or want instructions on performing a task, you MUST use the get_task_guide tool.
                                Examples of when to use get_task_guide:
                                - "How do I add a procedure to a patient's ledger?"
                                - "How to create a claim?"
                                - "Show me how to add a payment"
                                - "I need help creating an appointment"
                                - "How do I search for patients?"
                                - Any question asking for step-by-step instructions or guidance

                                For "how to" questions, call get_task_guide with a search query describing the task, then present the guide to the user in a friendly, helpful manner.

                                AVAILABLE OPTIONS (CRITICAL - You MUST use these exact values):
                                
                                Procedure Types (use the exact name):
                                {procedure_type_list}
                                
                                Operatories (use the exact ID, e.g., "OP1"):
                                {operatory_list}
                                
                                Providers (use the exact name):
                                {provider_list}
                                
                                IMPORTANT MATCHING RULES:
                                - When the user mentions a procedure type, match it to one of the available procedure types above.
                                  Example: "cleaning" → "Cleaning", "filling" → "Filling", "crown" → "Crown"
                                - When the user mentions an operatory, match it to one of the available operatory IDs above.
                                  Example: "op 1" or "OP 1" or "op1 hygiene" → "OP1"
                                - When the user mentions a provider, match it to one of the available provider names above.
                                  Example: "jinna" or "dr jinna" → "Dr. Jinna"
                                - Always use the EXACT values from the lists above - do not use variations or user's original input.
                                - Handle spelling mistakes, abbreviations, and variations intelligently to match to the correct value.

                                Your primary goal is to successfully call the correct tool with valid arguments using ONLY the values from the lists above.

                                RULES (CRITICAL):
                                1. You MUST collect all required fields before calling any tool.
                                2. Once all required fields are available:
                                - DO NOT respond with normal text.
                                - IMMEDIATELY call the appropriate tool.
                                3. Your final response in that case MUST be a tool call.
                                4. NEVER return "None", empty content, or a normal message when a tool call is possible.
                                5. When calling tools, use ONLY the tool function directly - DO NOT wrap in print(), eval(), or any other function.
                                6. ALWAYS match user input to the exact values from the AVAILABLE OPTIONS lists above.

                                For creating an appointment, required fields:
                                - patient_id or patient_name
                                - date (YYYY-MM-DD)
                                - time (HH:MM, 24-hour)
                                - duration (REQUIRED - must be a NUMBER in minutes, e.g., 10, 30, 60, 90)
                                  CRITICAL: Extract the exact number from user input:
                                  * "10 minutes" → 10
                                  * "30 mins" → 30
                                  * "1 hour" → 60
                                  * "1.5 hours" → 90
                                  * "10" → 10
                                  Always pass duration as a number, not a string!
                                - procedure_type (MUST be one of: {procedure_type_list})
                                - operatory (MUST be one of the IDs: {", ".join([op.id for op in operatories])})
                                - provider (MUST be one of: {provider_list})

                                For updating an appointment:
                                - appointment_id (REQUIRED - must be an integer)
                                - Any fields to update: date, start_time, duration, patient_id, procedure_type, operatory, provider, notes, status
                                - Example: {{"appointment_id": 27, "start_time": "09:00"}}

                                For deleting:
                                - appointment_id (REQUIRED - must be an integer)

                                Conversation behavior:
                                - If any required field is missing → ask ONLY for the missing fields.
                                - Do not repeat already known information.
                                - Do not confirm with the user once all fields are present.
                                - Execute immediately.

                                Output policy:
                                - If tool call → return ONLY tool JSON.
                                - If missing data → return ONLY a natural language question.
                                - NEVER wrap tool calls in print(), eval(), or any other function.
                                - Call tools directly: tool_name({{"arg1": "value1", "arg2": "value2"}})

                                Before responding, internally check:
                                - Are all required fields present?
                                - Are procedure_type, operatory, and provider matched to exact values from the lists above?
                                If YES → tool call (directly, no wrappers).
                                If NO → ask only for missing fields.

                                CRITICAL: When calling update_appointment or create_appointment:
                                - Use: create_appointment({{"procedure_type": "Cleaning", "operatory": "OP1", "provider": "Dr. Jinna", ...}})
                                - NOT: print(create_appointment(...)) or any wrapper function
                                - Use EXACT values from the AVAILABLE OPTIONS lists above

                                """
                messages.append(SystemMessage(content=system_msg))
                
                # Add conversation history (last 10 messages)
                for msg in conversation_state.messages[-10:]:
                    msg_content = msg.get("content", "")
                    if msg_content:  # Only add messages with content
                        if msg["role"] == "user":
                            messages.append(HumanMessage(content=msg_content))
                        else:
                            messages.append(AIMessage(content=msg_content))
                
                # Add current user message - ensure it has content
                if user_message and user_message.strip():
                    messages.append(HumanMessage(content=user_message))
                else:
                    # If user message is empty, return early
                    return "I didn't receive your message. Please try again."
                
                # Extract content helper function
                def extract_content(msg):
                    """Extract text content from a message object"""
                    if hasattr(msg, "content"):
                        content = msg.content
                        # If content is a list (parts), extract text from each part
                        if isinstance(content, list):
                            text_parts = []
                            for part in content:
                                if isinstance(part, dict):
                                    if part.get("type") == "text":
                                        text_parts.append(part.get("text", ""))
                                    elif "text" in part:
                                        text_parts.append(part["text"])
                                elif isinstance(part, str):
                                    text_parts.append(part)
                            return " ".join(text_parts) if text_parts else str(content)
                        return str(content) if content else ""
                    elif isinstance(msg, list):
                        # Handle list of content parts directly
                        text_parts = []
                        for part in msg:
                            if isinstance(part, dict):
                                if part.get("type") == "text":
                                    text_parts.append(part.get("text", ""))
                                elif "text" in part:
                                    text_parts.append(part["text"])
                            elif isinstance(part, str):
                                text_parts.append(part)
                        return " ".join(text_parts) if text_parts else str(msg)
                    else:
                        return str(msg) if msg else ""
                
                # CRITICAL: Implement proper agent loop
                # Agent loop: Human -> LLM -> (tool?) -> Tool -> LLM -> Final Answer
                max_iterations = 10  # Prevent infinite loops
                iteration = 0
                
                while iteration < max_iterations:
                    iteration += 1
                    logger.info(f"[AGENT] Agent loop iteration {iteration}/{max_iterations}")
                    logger.debug(f"[AGENT] Invoking LLM with {len(messages)} messages")
                    
                    # Invoke LLM with tools bound
                    response = self.agent.invoke(messages)
                    logger.info(f"[AGENT] LLM response received. Type: {type(response).__name__}")
                    logger.info(f"[AGENT] LLM response received : {response}")
                    
                    # CRITICAL FIX: Gemini uses additional_kwargs["tool_calls"], not response.tool_calls
                    # Check both locations for tool calls
                    tool_calls = None
                    invalid_tool_calls = []
                    
                    # Check for invalid tool calls first (malformed function calls)
                    if hasattr(response, "invalid_tool_calls") and response.invalid_tool_calls:
                        invalid_tool_calls = response.invalid_tool_calls
                        logger.warning(f"[AGENT] Invalid tool calls detected: {invalid_tool_calls}")
                    
                    # Check response metadata for finish_reason
                    if hasattr(response, "response_metadata"):
                        finish_reason = response.response_metadata.get("finish_reason", "")
                        if finish_reason == "MALFORMED_FUNCTION_CALL":
                            finish_message = response.response_metadata.get("finish_message", "")
                            logger.error(f"[AGENT] Malformed function call detected: {finish_message}")
                            # Try to extract tool call info from the error message
                            if "update_appointment" in finish_message.lower():
                                logger.warning(f"[AGENT] Gemini attempted to call update_appointment but with malformed syntax")
                    
                    if hasattr(response, "tool_calls") and response.tool_calls:
                        tool_calls = response.tool_calls
                        logger.debug(f"[AGENT] Found tool_calls in response.tool_calls")
                    elif hasattr(response, "additional_kwargs"):
                        additional_kwargs = response.additional_kwargs or {}
                        tool_calls = additional_kwargs.get("tool_calls")
                        if tool_calls:
                            logger.debug(f"[AGENT] Found tool_calls in response.additional_kwargs['tool_calls']")
                    
                    # Handle list vs single tool call
                    if tool_calls and not isinstance(tool_calls, list):
                        tool_calls = [tool_calls]
                    
                    has_tool_calls = bool(tool_calls)
                    has_invalid_tool_calls = bool(invalid_tool_calls)
                    
                    # Check response metadata for malformed function calls
                    malformed_call = False
                    malformed_message = ""
                    if hasattr(response, "response_metadata"):
                        finish_reason = response.response_metadata.get("finish_reason", "")
                        if finish_reason == "MALFORMED_FUNCTION_CALL":
                            malformed_call = True
                            malformed_message = response.response_metadata.get("finish_message", "")
                            logger.error(f"[AGENT] Malformed function call detected: {malformed_message}")
                            # Try to extract tool call info from the error message
                            tool_name_to_extract = None
                            if "create_appointment" in malformed_message.lower():
                                tool_name_to_extract = "create_appointment"
                            elif "update_appointment" in malformed_message.lower():
                                tool_name_to_extract = "update_appointment"
                            
                            if tool_name_to_extract:
                                logger.warning(f"[AGENT] Gemini attempted to call {tool_name_to_extract} but with malformed syntax")
                                # Try to extract the JSON from the malformed call
                                import re
                                
                                # Try multiple extraction strategies
                                extracted_json = None
                                
                                # Strategy 1: Find JSON object by matching braces (most robust)
                                # Find the first { and then find the matching }
                                brace_start = malformed_message.find('{')
                                if brace_start != -1:
                                    brace_count = 0
                                    brace_end = -1
                                    in_string = False
                                    escape_next = False
                                    quote_char = None
                                    
                                    for i in range(brace_start, len(malformed_message)):
                                        char = malformed_message[i]
                                        
                                        if escape_next:
                                            escape_next = False
                                            continue
                                        
                                        if char == '\\':
                                            escape_next = True
                                            continue
                                        
                                        if not in_string:
                                            if char in ['"', "'"]:
                                                in_string = True
                                                quote_char = char
                                            elif char == '{':
                                                brace_count += 1
                                            elif char == '}':
                                                brace_count -= 1
                                                if brace_count == 0:
                                                    brace_end = i
                                                    break
                                        else:
                                            if char == quote_char:
                                                in_string = False
                                                quote_char = None
                                    
                                    if brace_end != -1:
                                        json_str = malformed_message[brace_start:brace_end + 1]
                                        # Remove surrounding quotes if present
                                        json_str = json_str.strip("'\"")
                                        # Clean up escaped quotes
                                        json_str = json_str.replace('\\"', '"').replace("\\'", "'")
                                        try:
                                            extracted_json = json.loads(json_str)
                                            logger.info(f"[AGENT] Extracted JSON using brace matching: {extracted_json}")
                                        except (json.JSONDecodeError, AttributeError) as e:
                                            logger.debug(f"[AGENT] Brace matching found JSON but decode failed: {e}, json_str: {json_str[:100]}")
                                
                                # Strategy 2: Try regex patterns if brace matching failed
                                if not extracted_json:
                                    json_patterns = [
                                        r"'(\{[^']+\})'",  # Single-quoted JSON (simple case)
                                        r'"(\{[^"]+\})"',  # Double-quoted JSON (simple case)
                                        r'(\{[^{}]+\})',   # Unquoted JSON (simple case, no nested objects)
                                    ]
                                    
                                    for pattern in json_patterns:
                                        json_match = re.search(pattern, malformed_message)
                                        if json_match:
                                            json_str = json_match.group(1) if json_match.lastindex else json_match.group(0)
                                            # Clean up escaped quotes if present
                                            json_str = json_str.replace('\\"', '"').replace("\\'", "'")
                                            try:
                                                extracted_json = json.loads(json_str)
                                                logger.info(f"[AGENT] Extracted JSON from malformed call using pattern '{pattern}': {extracted_json}")
                                                break
                                            except (json.JSONDecodeError, AttributeError) as e:
                                                logger.debug(f"[AGENT] Pattern '{pattern}' matched but JSON decode failed: {e}, json_str: {json_str[:100]}")
                                                continue
                                
                                if extracted_json:
                                    # Manually create a tool call structure
                                    if not tool_calls:
                                        tool_calls = [{
                                            "name": tool_name_to_extract,
                                            "args": extracted_json,
                                            "id": "manual_extract_1"
                                        }]
                                        has_tool_calls = True
                                        logger.info(f"[AGENT] Manually created tool call from malformed function call: {tool_name_to_extract}")
                                else:
                                    logger.warning(f"[AGENT] Could not extract JSON from malformed call message: {malformed_message[:200]}")
                    
                    logger.info(f"[AGENT] Response has tool_calls: {has_tool_calls}, invalid_tool_calls: {len(invalid_tool_calls)}, malformed_call: {malformed_call}")
                    
                    # If we have invalid or malformed tool calls (and couldn't extract), log warning but continue
                    if (has_invalid_tool_calls or malformed_call) and not has_tool_calls:
                        logger.warning(f"[AGENT] Tool call was malformed but couldn't extract valid call. Invalid: {invalid_tool_calls}, Malformed: {malformed_call}")
                    
                    if has_tool_calls:
                        logger.info(f"[AGENT] Tool calls detected: {len(tool_calls)} tool call(s)")
                        for i, tool_call in enumerate(tool_calls):
                            # Handle both dict and object tool calls
                            if isinstance(tool_call, dict):
                                tool_name = tool_call.get("name", tool_call.get("function", {}).get("name", "N/A"))
                                tool_args = tool_call.get("args", tool_call.get("function", {}).get("arguments", {}))
                            else:
                                tool_name = getattr(tool_call, "name", getattr(tool_call, "function", {}).get("name", "N/A"))
                                tool_args = getattr(tool_call, "args", getattr(tool_call, "function", {}).get("arguments", {}))
                            logger.info(f"[AGENT] Tool call {i}: name={tool_name}, args={tool_args}")
                        
                        # Execute tool calls
                        logger.info(f"[AGENT] Starting tool execution. Available tools: {[t.name for t in self.tools]}")
                        tool_results = []
                        
                        for idx, tool_call in enumerate(tool_calls):
                            # Handle both dict and object tool calls
                            if isinstance(tool_call, dict):
                                tool_name = tool_call.get("name", tool_call.get("function", {}).get("name", ""))
                                tool_input = tool_call.get("args", tool_call.get("function", {}).get("arguments", {}))
                                tool_call_id = tool_call.get("id", tool_call.get("tool_call_id", ""))
                            else:
                                # Handle object-style tool calls
                                tool_name = getattr(tool_call, "name", None) or getattr(tool_call, "function", {}).get("name", "")
                                tool_input = getattr(tool_call, "args", None) or getattr(tool_call, "function", {}).get("arguments", {})
                                tool_call_id = getattr(tool_call, "id", None) or getattr(tool_call, "tool_call_id", "")
                            
                            # If tool_input is a string (JSON), parse it
                            if isinstance(tool_input, str):
                                try:
                                    tool_input = json.loads(tool_input)
                                except json.JSONDecodeError:
                                    logger.warning(f"[AGENT] Tool input is not valid JSON, using as-is: {tool_input}")
                            
                            logger.info(f"[AGENT] Processing tool call {idx+1}/{len(tool_calls)}: name='{tool_name}', id='{tool_call_id}'")
                            logger.debug(f"[AGENT] Tool call {idx} input: {tool_input}")
                            
                            # Find and execute the tool
                            tool_found = False
                            for tool in self.tools:
                                logger.debug(f"[AGENT] Checking tool: {tool.name} == {tool_name}? {tool.name == tool_name}")
                                if tool.name == tool_name:
                                    tool_found = True
                                    logger.info(f"[AGENT] Tool '{tool_name}' found. Executing...")
                                    try:
                                        # Convert tool_input dict to JSON string if needed
                                        if isinstance(tool_input, dict):
                                            tool_input_str = json.dumps(tool_input)
                                            logger.debug(f"[AGENT] Converted tool input dict to JSON: {tool_input_str[:200]}")
                                        else:
                                            tool_input_str = str(tool_input)
                                        
                                        logger.info(f"[AGENT] Invoking tool '{tool_name}' with input length: {len(tool_input_str)}")
                                        result = tool.invoke(tool_input_str)
                                        logger.info(f"[AGENT] Tool '{tool_name}' executed successfully. Result type: {type(result).__name__}, length: {len(str(result))}")
                                        logger.debug(f"[AGENT] Tool '{tool_name}' result: {str(result)[:500]}")
                                        
                                        tool_results.append({
                                            "tool_call_id": tool_call_id,
                                            "name": tool_name,
                                            "result": result
                                        })
                                    except Exception as e:
                                        logger.error(f"[AGENT] Error executing tool '{tool_name}': {e}", exc_info=True)
                                        tool_results.append({
                                            "tool_call_id": tool_call_id,
                                            "name": tool_name,
                                            "result": f"Error: {str(e)}"
                                        })
                                    break
                            
                            if not tool_found:
                                logger.warning(f"[AGENT] Tool '{tool_name}' not found in available tools: {[t.name for t in self.tools]}")
                        
                        logger.info(f"[AGENT] Tool execution complete. Results: {len(tool_results)} result(s)")
                        
                        # CRITICAL: Add tool call response and tool results to messages, then LOOP BACK
                        # This is the agent loop - we must call LLM again with tool results
                        logger.info(f"[AGENT] Adding tool call response and results to messages, then looping back to LLM")
                        
                        # Add the tool call response (AIMessage with tool_calls)
                        # IMPORTANT: Gemini returns empty content when making tool calls - this is expected
                        messages.append(response)
                        logger.debug(f"[AGENT] Added AIMessage with tool_calls to messages")
                        
                        # Add tool results as ToolMessage objects
                        for tool_result in tool_results:
                            tool_call_id = tool_result.get("tool_call_id", "")
                            tool_result_str = str(tool_result.get("result", ""))
                            logger.debug(f"[AGENT] Adding ToolMessage: tool_call_id='{tool_call_id}', result length={len(tool_result_str)}")
                            messages.append(ToolMessage(
                                content=tool_result_str,
                                tool_call_id=tool_call_id
                            ))
                        
                        logger.info(f"[AGENT] Added {len(tool_results)} tool results. Total messages: {len(messages)}")
                        logger.info(f"[AGENT] Looping back to LLM to get final response after tool execution")
                        continue  # CRITICAL: Loop back to invoke LLM again with tool results
                    
                    else:
                        # No tool calls - we have the final answer
                        logger.info(f"[AGENT] No tool calls detected. This is the final response.")
                        response_text = extract_content(response)
                        logger.info(f"[AGENT] Extracted final response text. Length: {len(response_text)}")
                        logger.debug(f"[AGENT] Final response text: {response_text[:200]}")
                        
                        if not response_text or not response_text.strip():
                            logger.warning(f"[AGENT] Final response is empty. This might indicate an issue.")
                            response_text = "I'm sorry, I couldn't generate a response. Please try again."
                        
                        # Break out of the loop - we have the final answer
                        break
                
                # Check if we hit max iterations
                if iteration >= max_iterations:
                    logger.error(f"[AGENT] Hit max iterations ({max_iterations}) without getting final answer")
                    response_text = "I'm sorry, I encountered an issue processing your request. Please try again."
                
                
                # Add AI response to conversation history
                logger.info(f"[AGENT] Adding assistant response to conversation history")
                conversation_state.add_message("assistant", response_text)
                logger.info(f"[AGENT] process_message completed successfully. Returning response text (length: {len(response_text)})")
                
                return response_text
            
            except Exception as e:
                last_error = e
                logger.warning(f"Error processing message (attempt {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    import time
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                else:
                    # Final attempt failed
                    logger.error(f"Error processing message after {max_retries} attempts: {e}", exc_info=True)
                    error_msg = "I'm sorry, I encountered an error processing your request. Please try again or rephrase your question."
                    conversation_state.add_message("assistant", error_msg)
                    return error_msg
        
        # Should not reach here, but just in case
        error_msg = "I'm sorry, I encountered an error processing your request. Please try again."
        conversation_state.add_message("assistant", error_msg)
        return error_msg
