# Task Guide System for AI Chat Assistant

## Overview

The AI Chat Assistant has been enhanced with a comprehensive task guide system that provides step-by-step instructions for common tasks in the dental practice management system. When users ask "how to" questions, the assistant can now provide detailed UI navigation guidance.

## Features

- **Step-by-step instructions** for common tasks
- **Categorized guides** by module (Patient Ledger, Patient Management, Scheduler)
- **Keyword-based search** for finding relevant guides
- **Prerequisites and related tasks** information
- **Natural language integration** - users can ask questions in plain English

## Available Guides

### Patient Ledger
1. **Add Procedure to Patient Ledger** - How to add a procedure with all required fields
2. **Create Claim from Procedures** - How to create an insurance claim
3. **Send Claim to Insurance** - How to submit a claim to insurance
4. **Add Payment to Ledger** - How to record patient or insurance payments
5. **Add Adjustment to Ledger** - How to add write-offs, discounts, etc.

### Patient Management
1. **Create New Patient** - How to register a new patient
2. **Search for Patients** - How to find patients in the system

### Scheduler
1. **Create Appointment** - How to schedule a new appointment
2. **Update Appointment** - How to modify an existing appointment

## Usage Examples

### User Queries That Trigger Guide Tool

The AI assistant will automatically use the guide tool when users ask questions like:

- "How do I add a procedure to a patient's ledger?"
- "How to create a claim?"
- "Show me how to add a payment"
- "I need help creating an appointment"
- "How do I search for patients?"
- "How to send a claim to insurance?"
- "Can you guide me through adding an adjustment?"

### Example Interaction

**User:** "How do I add a procedure to patient ledger?"

**AI Assistant:** (Calls `get_task_guide` with query "add procedure to ledger")

**Response:**
```
## How to Add a Procedure to Patient Ledger

This guide will walk you through adding a procedure to a patient's ledger, which records the dental work performed and its associated fees.

**Steps to follow:**

**Step 1: Navigate to Patient Ledger**
  Go to the Patient module and select the patient you want to add a procedure for. Then click on the 'Ledger' tab or navigate to the Patient Ledger screen.

**Step 2: Click 'Add Procedure' Button**
  Look for the 'Add Procedure' or '+' button in the ledger view. This is typically located at the top of the ledger entries list or in a toolbar.

**Step 3: Fill in Procedure Details**
  In the procedure form, you'll need to enter:
  - Procedure Code (CDT code, e.g., D0150, D6057)
  - Date of Service (when the procedure was performed)
  - Provider (the treating dentist/hygienist)
  - Office (where the procedure was performed)
  - Fee (the total charge for the procedure)
  - Estimated Patient Portion
  - Estimated Insurance Portion

[... continues with all steps ...]
```

## Technical Implementation

### Files Created/Modified

1. **`app/api/v1/ai_chat/guides.py`** (NEW)
   - Contains `TaskGuide` class for structured guide data
   - `TASK_GUIDES` dictionary with all registered guides
   - Search functions: `search_guides()`, `get_guide_by_id()`, `get_all_guides()`
   - Guide formatting: `format_for_response()`

2. **`app/api/v1/ai_chat/agent.py`** (MODIFIED)
   - Added `get_task_guide_tool` function
   - Updated `_create_tools()` to include the guide tool
   - Enhanced system prompt to recognize "how to" questions
   - Imported guide functions

### Guide Structure

Each guide contains:
- **task_id**: Unique identifier
- **title**: Human-readable title
- **description**: Brief overview
- **category**: Module category (Patient Ledger, Patient Management, Scheduler)
- **steps**: List of step-by-step instructions with actions and details
- **prerequisites**: Required conditions or setup
- **related_tasks**: Links to other relevant guides
- **keywords**: Search terms for finding the guide

### Search Algorithm

The `search_guides()` function matches queries against:
- Guide titles (case-insensitive)
- Guide descriptions
- Keywords list
- Category names

Returns guides ordered by relevance.

## Adding New Guides

To add a new guide, use the `_register_guide()` function in `guides.py`:

```python
_register_guide(TaskGuide(
    task_id="your_task_id",
    title="How to Do Something",
    description="Brief description of the task",
    category="Module Name",
    steps=[
        {
            "step": 1,
            "action": "First action",
            "details": "Detailed explanation of what to do"
        },
        # ... more steps
    ],
    prerequisites=["Prerequisite 1", "Prerequisite 2"],
    related_tasks=["Related task 1", "Related task 2"],
    keywords=["keyword1", "keyword2", "keyword3"]
))
```

## Future Enhancements

Potential improvements:
1. **More guides** for additional modules (Treatment Plans, Reports, Settings, etc.)
2. **Visual guides** with screenshots or diagrams
3. **Interactive guides** that highlight UI elements
4. **Context-aware guides** that adapt based on user's current screen
5. **Video tutorials** integration
6. **Multi-language support** for guides
7. **User feedback** on guide helpfulness
8. **Guide analytics** to track which guides are most used

## Testing

To test the guide system:

1. Connect to the AI chat via WebSocket or REST API
2. Ask questions like:
   - "How do I add a procedure to a patient ledger?"
   - "Show me how to create a claim"
   - "I need help adding a payment"
3. Verify that the assistant:
   - Recognizes the "how to" intent
   - Calls the `get_task_guide` tool
   - Returns formatted step-by-step instructions
   - Provides helpful, actionable guidance

## Notes

- The guide system is separate from action tools (create_appointment, etc.)
- Guides provide **instructions** only - they don't perform actions
- Users can still ask the assistant to perform actions directly (e.g., "Create an appointment for...")
- The assistant intelligently distinguishes between "how to" questions and action requests
