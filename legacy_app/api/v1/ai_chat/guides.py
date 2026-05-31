"""
Task Guides Knowledge Base for AI Chat Assistant.

This module contains step-by-step instructions for common tasks in the dental practice management system.
The AI assistant uses these guides to help users navigate the system UI.
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class TaskGuide:
    """Represents a task guide with steps and metadata"""
    
    def __init__(
        self,
        task_id: str,
        title: str,
        description: str,
        category: str,
        steps: List[Dict[str, str]],
        prerequisites: Optional[List[str]] = None,
        related_tasks: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None
    ):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.category = category
        self.steps = steps  # List of {"step": int, "action": str, "details": str}
        self.prerequisites = prerequisites or []
        self.related_tasks = related_tasks or []
        self.keywords = keywords or []
    
    def to_dict(self) -> Dict:
        """Convert guide to dictionary format"""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "steps": self.steps,
            "prerequisites": self.prerequisites,
            "related_tasks": self.related_tasks,
            "keywords": self.keywords
        }
    
    def format_for_response(self) -> str:
        """Format guide as a user-friendly response"""
        lines = [
            f"## {self.title}",
            "",
            self.description,
            "",
            "**Steps to follow:**",
            ""
        ]
        
        for step in self.steps:
            step_num = step.get("step", "")
            action = step.get("action", "")
            details = step.get("details", "")
            
            lines.append(f"**Step {step_num}: {action}**")
            if details:
                lines.append(f"  {details}")
            lines.append("")
        
        if self.prerequisites:
            lines.append("**Prerequisites:**")
            for prereq in self.prerequisites:
                lines.append(f"  - {prereq}")
            lines.append("")
        
        if self.related_tasks:
            lines.append("**Related tasks you might need:**")
            for related in self.related_tasks:
                lines.append(f"  - {related}")
            lines.append("")
        
        return "\n".join(lines)


# Task Guides Database
TASK_GUIDES: Dict[str, TaskGuide] = {}

def _register_guide(guide: TaskGuide):
    """Register a task guide"""
    TASK_GUIDES[guide.task_id] = guide
    # Also register by keywords for easier lookup
    for keyword in guide.keywords:
        TASK_GUIDES[keyword.lower()] = guide


# ==================================================
# Patient Ledger Guides
# ==================================================

_register_guide(TaskGuide(
    task_id="add_procedure_to_ledger",
    title="How to Add a Procedure to Patient Ledger",
    description="This guide will walk you through adding a procedure to a patient's ledger, which records the dental work performed and its associated fees.",
    category="Patient Ledger",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Patient Ledger",
            "details": "Go to the Patient module and select the patient you want to add a procedure for. Then click on the 'Ledger' tab or navigate to the Patient Ledger screen."
        },
        {
            "step": 2,
            "action": "Click 'Add Procedure' Button",
            "details": "Look for the 'Add Procedure' or '+' button in the ledger view. This is typically located at the top of the ledger entries list or in a toolbar."
        },
        {
            "step": 3,
            "action": "Fill in Procedure Details",
            "details": "In the procedure form, you'll need to enter:\n  - Procedure Code (CDT code, e.g., D0150, D6057)\n  - Date of Service (when the procedure was performed)\n  - Provider (the treating dentist/hygienist)\n  - Office (where the procedure was performed)\n  - Fee (the total charge for the procedure)\n  - Estimated Patient Portion\n  - Estimated Insurance Portion"
        },
        {
            "step": 4,
            "action": "Add Procedure-Specific Details (if required)",
            "details": "Some procedures require additional information:\n  - Tooth number (if applicable, e.g., for fillings, crowns)\n  - Surface codes (e.g., MOD for Mesial-Occlusal-Distal)\n  - Quadrant (1-4)\n  - Materials (if applicable)\n  The system will prompt you if these are required based on the procedure code."
        },
        {
            "step": 5,
            "action": "Add Optional Information",
            "details": "You can optionally add:\n  - Duration (in minutes)\n  - Billing Order (Primary, Secondary, etc.)\n  - Notes (any additional information about the procedure)\n  - Apply To (Patient or Responsible Party)"
        },
        {
            "step": 6,
            "action": "Review and Save",
            "details": "Review all the information you've entered to ensure accuracy. Click 'Save' or 'Add Procedure' to post the procedure to the patient's ledger. The procedure will appear in the ledger with a status of 'Not Sent' if it needs to be billed to insurance."
        }
    ],
    prerequisites=[
        "Patient must exist in the system",
        "Procedure code must be valid and active",
        "Provider and Office must be set up"
    ],
    related_tasks=[
        "Create a claim from procedures",
        "View patient ledger entries",
        "Update a procedure"
    ],
    keywords=["add procedure", "procedure ledger", "add procedure to patient", "post procedure", "create procedure", "procedure entry"]
))

_register_guide(TaskGuide(
    task_id="create_claim",
    title="How to Create a Claim from Procedures",
    description="Learn how to create an insurance claim from selected procedures in a patient's ledger.",
    category="Patient Ledger",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Patient Ledger",
            "details": "Go to the Patient module, select the patient, and open their Ledger tab."
        },
        {
            "step": 2,
            "action": "Select Procedures",
            "details": "In the ledger entries list, check the boxes next to the procedures you want to include in the claim. Only procedures with status 'Not Sent' can be included in a new claim."
        },
        {
            "step": 3,
            "action": "Click 'Create Claim' Button",
            "details": "After selecting procedures, click the 'Create Claim' or 'New Claim' button, typically located in the toolbar above the ledger entries."
        },
        {
            "step": 4,
            "action": "Configure Claim Details",
            "details": "In the claim creation dialog, you'll need to specify:\n  - Claim Type (Dental or Medical)\n  - Billing Order (Primary, Secondary, etc.)\n  - Date of Service Range (automatically populated from selected procedures)\n  - Notes (optional)"
        },
        {
            "step": 5,
            "action": "Review Selected Procedures",
            "details": "Verify that all the correct procedures are included in the claim. You can see the total fees and estimated insurance amounts."
        },
        {
            "step": 6,
            "action": "Save the Claim",
            "details": "Click 'Create' or 'Save' to create the claim. The claim will be assigned a claim number and the procedures will be linked to it. The claim status will be 'Created' (not yet sent to insurance)."
        }
    ],
    prerequisites=[
        "At least one procedure with status 'Not Sent' must exist in the patient's ledger",
        "Procedures must be from the same date range (typically)"
    ],
    related_tasks=[
        "Send claim to insurance",
        "View claim details",
        "Update claim information"
    ],
    keywords=["create claim", "new claim", "insurance claim", "bill insurance", "submit claim", "make claim"]
))

_register_guide(TaskGuide(
    task_id="send_claim_to_insurance",
    title="How to Send a Claim to Insurance",
    description="Learn how to send a created claim to the insurance company for processing.",
    category="Patient Ledger",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Patient Ledger",
            "details": "Go to the Patient module, select the patient, and open their Ledger tab."
        },
        {
            "step": 2,
            "action": "Open the Claim",
            "details": "Find the claim you want to send in the claims list (or from the ledger entries). Click on it to open the claim details view."
        },
        {
            "step": 3,
            "action": "Review Claim Information",
            "details": "Before sending, verify that:\n  - All required patient and insurance information is complete\n  - All procedures are correctly included\n  - Any required attachments are uploaded (if applicable)\n  - ICD-10 codes are added (if required)"
        },
        {
            "step": 4,
            "action": "Click 'Send Claim' Button",
            "details": "In the claim details view, click the 'Send Claim' or 'Submit to Insurance' button."
        },
        {
            "step": 5,
            "action": "Select Send Method",
            "details": "Choose how you want to send the claim:\n  - Electronic (EDI submission)\n  - Paper (print and mail)\n  - Fax"
        },
        {
            "step": 6,
            "action": "Confirm and Send",
            "details": "Review the send method and click 'Confirm' or 'Send'. The claim status will change to 'Sent' and a sent date will be recorded. The claim will be added to a batch if using electronic submission."
        }
    ],
    prerequisites=[
        "Claim must exist and have status 'Created'",
        "All required claim information must be complete",
        "Patient insurance information must be on file"
    ],
    related_tasks=[
        "Create a claim from procedures",
        "View claim status",
        "Track claim payments"
    ],
    keywords=["send claim", "submit claim", "send to insurance", "file claim", "transmit claim"]
))

_register_guide(TaskGuide(
    task_id="add_payment_to_ledger",
    title="How to Add a Payment to Patient Ledger",
    description="Learn how to record a payment (patient or insurance) in the patient ledger.",
    category="Patient Ledger",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Patient Ledger",
            "details": "Go to the Patient module, select the patient, and open their Ledger tab."
        },
        {
            "step": 2,
            "action": "Click 'Add Payment' Button",
            "details": "Look for the 'Add Payment' or 'Payment' button in the ledger toolbar."
        },
        {
            "step": 3,
            "action": "Select Payment Type",
            "details": "Choose whether this is a 'Patient Payment' or 'Insurance Payment'."
        },
        {
            "step": 4,
            "action": "Enter Payment Details",
            "details": "Fill in the payment form:\n  - Payment Date\n  - Payment Amount\n  - Payment Method (Check, Cash, Credit Card, etc.)\n  - Apply To (Patient or Responsible Party)"
        },
        {
            "step": 5,
            "action": "Apply Payment to Procedures (Optional)",
            "details": "If you want to apply the payment to specific procedures, select them from the list. Otherwise, the payment will be applied to the oldest outstanding balance."
        },
        {
            "step": 6,
            "action": "Add Payment Information",
            "details": "For checks, enter:\n  - Check Number\n  - Bank/Routing Number (if applicable)\n  - Notes (optional)"
        },
        {
            "step": 7,
            "action": "Save the Payment",
            "details": "Review the payment details and click 'Save' or 'Post Payment'. The payment will be recorded in the ledger and the patient's balance will be updated."
        }
    ],
    prerequisites=[
        "Patient must exist in the system",
        "Payment method code must be configured"
    ],
    related_tasks=[
        "View patient balance",
        "Add adjustment to ledger",
        "View payment history"
    ],
    keywords=["add payment", "record payment", "post payment", "payment entry", "patient payment", "insurance payment"]
))

_register_guide(TaskGuide(
    task_id="add_adjustment_to_ledger",
    title="How to Add an Adjustment to Patient Ledger",
    description="Learn how to add an adjustment (write-off, discount, etc.) to a patient's ledger.",
    category="Patient Ledger",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Patient Ledger",
            "details": "Go to the Patient module, select the patient, and open their Ledger tab."
        },
        {
            "step": 2,
            "action": "Click 'Add Adjustment' Button",
            "details": "Look for the 'Add Adjustment' or 'Adjustment' button in the ledger toolbar."
        },
        {
            "step": 3,
            "action": "Enter Adjustment Details",
            "details": "Fill in the adjustment form:\n  - Adjustment Date\n  - Adjustment Amount (negative amount that reduces balance)\n  - Adjustment Code (reason code, e.g., 'ADJ01' for Courtesy Discount)\n  - Adjustment Reason (description)"
        },
        {
            "step": 4,
            "action": "Select Apply To",
            "details": "Choose whether to apply the adjustment to 'Patient' or 'Responsible Party'."
        },
        {
            "step": 5,
            "action": "Apply to Specific Procedures (Optional)",
            "details": "If you want to apply the adjustment to specific procedures, select them from the list."
        },
        {
            "step": 6,
            "action": "Add Notes (Optional)",
            "details": "Add any additional notes or explanation for the adjustment."
        },
        {
            "step": 7,
            "action": "Save the Adjustment",
            "details": "Review the adjustment details and click 'Save' or 'Post Adjustment'. The adjustment will be recorded in the ledger and the patient's balance will be updated."
        }
    ],
    prerequisites=[
        "Patient must exist in the system",
        "Adjustment code must be configured"
    ],
    related_tasks=[
        "View patient balance",
        "Add payment to ledger",
        "View ledger entries"
    ],
    keywords=["add adjustment", "adjustment", "write off", "discount", "adjustment entry"]
))

# ==================================================
# Patient Management Guides
# ==================================================

_register_guide(TaskGuide(
    task_id="create_new_patient",
    title="How to Create a New Patient",
    description="Learn how to add a new patient to the system.",
    category="Patient Management",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Patients Module",
            "details": "Go to the main navigation menu and click on 'Patients' or use the search bar to access the patient module."
        },
        {
            "step": 2,
            "action": "Click 'New Patient' Button",
            "details": "Click the 'New Patient', 'Add Patient', or '+' button, typically located at the top right of the patient list."
        },
        {
            "step": 3,
            "action": "Enter Basic Information",
            "details": "Fill in the required patient information:\n  - First Name\n  - Last Name\n  - Date of Birth\n  - Gender\n  - Chart Number (or let system auto-generate)"
        },
        {
            "step": 4,
            "action": "Add Contact Information",
            "details": "Enter:\n  - Phone Number\n  - Email Address (optional)\n  - Address (Street, City, State, ZIP)"
        },
        {
            "step": 5,
            "action": "Add Insurance Information (if applicable)",
            "details": "If the patient has insurance:\n  - Insurance Carrier\n  - Subscriber Name and ID\n  - Group Plan Number\n  - Policy Number"
        },
        {
            "step": 6,
            "action": "Add Additional Information",
            "details": "Optionally add:\n  - Responsible Party (if different from patient)\n  - Emergency Contact\n  - Medical Alerts\n  - Notes"
        },
        {
            "step": 7,
            "action": "Save the Patient",
            "details": "Review all information and click 'Save' or 'Create Patient'. The patient will be added to the system and you'll be taken to their patient details page."
        }
    ],
    prerequisites=[
        "User must have permission to create patients",
        "Required fields must be filled"
    ],
    related_tasks=[
        "Search for patients",
        "Update patient information",
        "Check for duplicate patients"
    ],
    keywords=["new patient", "create patient", "add patient", "register patient", "patient registration"]
))

_register_guide(TaskGuide(
    task_id="search_patients",
    title="How to Search for Patients",
    description="Learn how to find patients in the system using the search functionality.",
    category="Patient Management",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Patients Module",
            "details": "Go to the main navigation and click on 'Patients'."
        },
        {
            "step": 2,
            "action": "Use the Search Bar",
            "details": "In the patient list view, you'll see a search bar at the top. You can search by:\n  - Patient Name (First or Last)\n  - Chart Number\n  - Phone Number\n  - Date of Birth"
        },
        {
            "step": 3,
            "action": "Enter Search Criteria",
            "details": "Type your search term in the search box. The system will search as you type and show matching results."
        },
        {
            "step": 4,
            "action": "Use Advanced Filters (Optional)",
            "details": "Click on 'Advanced Search' or 'Filters' to search by:\n  - Office\n  - Patient Type\n  - Insurance Carrier\n  - Date Range (Last Visit, etc.)"
        },
        {
            "step": 5,
            "action": "Select Patient from Results",
            "details": "Click on the patient you want to view from the search results. This will open their patient details page."
        }
    ],
    prerequisites=[],
    related_tasks=[
        "View patient details",
        "Create new patient",
        "Update patient information"
    ],
    keywords=["search patients", "find patient", "patient search", "lookup patient", "patient lookup"]
))

# ==================================================
# Scheduler Guides
# ==================================================

_register_guide(TaskGuide(
    task_id="create_appointment",
    title="How to Create an Appointment",
    description="Learn how to schedule a new appointment for a patient.",
    category="Scheduler",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Scheduler",
            "details": "Go to the main navigation menu and click on 'Scheduler' or 'Calendar'."
        },
        {
            "step": 2,
            "action": "Select Date and Time",
            "details": "Click on the desired date and time slot in the calendar view, or click the 'New Appointment' button and select the date/time."
        },
        {
            "step": 3,
            "action": "Select Patient",
            "details": "In the appointment creation dialog, search for and select the patient. You can search by name, chart number, or phone number."
        },
        {
            "step": 4,
            "action": "Choose Provider",
            "details": "Select the provider (dentist, hygienist, etc.) who will perform the procedure."
        },
        {
            "step": 5,
            "action": "Select Operatory",
            "details": "Choose the operatory (room) where the appointment will take place."
        },
        {
            "step": 6,
            "action": "Select Procedure Type",
            "details": "Choose the procedure type (e.g., Cleaning, Filling, Crown, etc.). This determines the appointment color and duration."
        },
        {
            "step": 7,
            "action": "Set Duration",
            "details": "The duration is usually auto-filled based on the procedure type, but you can adjust it if needed."
        },
        {
            "step": 8,
            "action": "Add Notes (Optional)",
            "details": "Add any special notes or instructions for this appointment."
        },
        {
            "step": 9,
            "action": "Save the Appointment",
            "details": "Click 'Save' or 'Create Appointment'. The appointment will appear on the scheduler calendar."
        }
    ],
    prerequisites=[
        "Patient must exist in the system",
        "Provider and Operatory must be available at the selected time"
    ],
    related_tasks=[
        "Update appointment",
        "Cancel appointment",
        "View appointment details"
    ],
    keywords=["create appointment", "schedule appointment", "new appointment", "book appointment", "add appointment"]
))

_register_guide(TaskGuide(
    task_id="update_appointment",
    title="How to Update an Appointment",
    description="Learn how to modify an existing appointment.",
    category="Scheduler",
    steps=[
        {
            "step": 1,
            "action": "Navigate to Scheduler",
            "details": "Go to the Scheduler/Calendar view."
        },
        {
            "step": 2,
            "action": "Find the Appointment",
            "details": "Locate the appointment on the calendar by date and time, or use the search/filter functionality."
        },
        {
            "step": 3,
            "action": "Open Appointment Details",
            "details": "Click on the appointment block in the calendar to open the appointment details dialog."
        },
        {
            "step": 4,
            "action": "Click 'Edit' Button",
            "details": "In the appointment details dialog, click the 'Edit' or pencil icon button."
        },
        {
            "step": 5,
            "action": "Modify Appointment Details",
            "details": "Update any of the following fields:\n  - Date and Time\n  - Patient\n  - Provider\n  - Operatory\n  - Procedure Type\n  - Duration\n  - Status\n  - Notes"
        },
        {
            "step": 6,
            "action": "Save Changes",
            "details": "Click 'Save' or 'Update' to apply the changes. The appointment will be updated on the calendar."
        }
    ],
    prerequisites=[
        "Appointment must exist",
        "User must have permission to edit appointments"
    ],
    related_tasks=[
        "Create appointment",
        "Cancel appointment",
        "Change appointment status"
    ],
    keywords=["update appointment", "edit appointment", "modify appointment", "change appointment", "reschedule appointment"]
))


def get_guide_by_id(task_id: str) -> Optional[TaskGuide]:
    """Get a task guide by its ID"""
    return TASK_GUIDES.get(task_id)


def search_guides(query: str) -> List[TaskGuide]:
    """
    Search for task guides by keyword or title.
    Returns guides that match the query.
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return []
    
    matches = []
    
    for guide in TASK_GUIDES.values():
        # Skip keyword entries (they're duplicates)
        if guide.task_id != guide.task_id.lower():
            continue
        
        # Check title
        if query_lower in guide.title.lower():
            matches.append(guide)
            continue
        
        # Check description
        if query_lower in guide.description.lower():
            matches.append(guide)
            continue
        
        # Check keywords
        for keyword in guide.keywords:
            if query_lower in keyword.lower():
                matches.append(guide)
                break
        
        # Check category
        if query_lower in guide.category.lower():
            matches.append(guide)
            continue
    
    # Remove duplicates (in case a guide matches multiple criteria)
    seen = set()
    unique_matches = []
    for guide in matches:
        if guide.task_id not in seen:
            seen.add(guide.task_id)
            unique_matches.append(guide)
    
    return unique_matches


def get_all_guides() -> List[TaskGuide]:
    """Get all task guides (excluding keyword duplicates)"""
    guides = []
    seen = set()
    for guide in TASK_GUIDES.values():
        if guide.task_id not in seen:
            seen.add(guide.task_id)
            guides.append(guide)
    return guides


def get_guides_by_category(category: str) -> List[TaskGuide]:
    """Get all guides in a specific category"""
    return [guide for guide in get_all_guides() if guide.category.lower() == category.lower()]
