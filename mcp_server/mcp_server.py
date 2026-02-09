"""
MCP (Model Context Protocol) Server Implementation
Wraps the expense orchestrator tools to be exposed via standard MCP protocol.
"""

import sys
import json
import base64
from typing import Any

try:
    from mcp.server.models import InitializationOptions
    from mcp.server import Server
except ImportError:
    print("Warning: MCP library not available. Install with: pip install mcp")
    sys.exit(1)

# Import our business logic tools
try:
    from mcp_server.tools.vision import vision_agent
    from mcp_server.tools.policy import apply_policy
    from mcp_server.tools.db import (
        get_or_create_report,
        add_expense,
        is_duplicate,
        get_report_by_trip,
        get_expenses_by_report,
    )
except ImportError as e:
    print(f"Error importing tools: {e}")
    sys.exit(1)

# Create the MCP server
server = Server("autonomous-expense-orchestrator")


# -------------------------------------------------
# TOOLS DEFINITION (MCP Protocol)
# -------------------------------------------------

TOOLS = {
    "vision_extract": {
        "description": "Extract expense information from receipt images or PDFs",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_bytes": {
                    "type": "string",
                    "description": "Base64-encoded file (image or PDF)"
                }
            },
            "required": ["file_bytes"]
        }
    },
    "policy_check": {
        "description": "Apply company policy rules to an expense",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Vendor name"},
                "amount": {"type": "number", "description": "Amount in rupees"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "text": {"type": "string", "description": "OCR text from receipt"}
            },
            "required": ["vendor", "amount", "date"]
        }
    },
    "db_create_report": {
        "description": "Create a new expense report for a trip",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trip_name": {"type": "string", "description": "Name of the trip"},
                "employee_name": {"type": "string", "description": "Employee filing the expense"},
                "thread_id": {"type": "string", "description": "Conversation thread ID"}
            },
            "required": ["trip_name"]
        }
    },
    "db_add_expense": {
        "description": "Add an expense to a report",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_id": {"type": "integer", "description": "Report ID"},
                "date": {"type": "string", "description": "Expense date"},
                "vendor": {"type": "string", "description": "Vendor name"},
                "amount": {"type": "number", "description": "Amount"},
                "category": {"type": "string", "description": "Expense category"},
                "status": {"type": "string", "description": "APPROVED or FLAGGED"},
                "text": {"type": "string", "description": "OCR text"}
            },
            "required": ["report_id", "date", "vendor", "amount"]
        }
    },
    "db_check_duplicate": {
        "description": "Check if expense is a duplicate",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_id": {"type": "integer"},
                "vendor": {"type": "string"},
                "amount": {"type": "number"},
                "date": {"type": "string"}
            },
            "required": ["report_id", "vendor", "amount", "date"]
        }
    },
    "db_get_trip_status": {
        "description": "Get status of a trip's expenses",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trip_name": {"type": "string", "description": "Trip name"}
            },
            "required": ["trip_name"]
        }
    }
}


# -------------------------------------------------
# TOOL HANDLERS (MCP Implementation)
# -------------------------------------------------

@server.list_tools()
async def list_tools() -> list[dict]:
    """List all available tools with their schemas."""
    return [
        {
            "name": tool_name,
            "description": tool_info["description"],
            "inputSchema": tool_info["inputSchema"]
        }
        for tool_name, tool_info in TOOLS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> Any:
    """Route tool calls to appropriate handlers."""
    
    if name == "vision_extract":
        return handle_vision_extract(arguments)
    
    elif name == "policy_check":
        return handle_policy_check(arguments)
    
    elif name == "db_create_report":
        return handle_db_create_report(arguments)
    
    elif name == "db_add_expense":
        return handle_db_add_expense(arguments)
    
    elif name == "db_check_duplicate":
        return handle_db_check_duplicate(arguments)
    
    elif name == "db_get_trip_status":
        return handle_db_get_trip_status(arguments)
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# -------------------------------------------------
# HANDLER IMPLEMENTATIONS
# -------------------------------------------------

def handle_vision_extract(arguments: dict) -> dict:
    """Handle vision extraction tool call via MCP."""
    try:
        # Decode base64 file
        file_data = base64.standard_b64decode(arguments["file_bytes"])
        
        # Extract using vision agent
        result = vision_agent(file_data)
        
        return {
            "success": True,
            "data": {
                "vendor": result.get("vendor"),
                "amount": result.get("amount"),
                "date": result.get("date"),
                "confidence": result.get("confidence"),
                "text_preview": result.get("text", "")[:200]
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_policy_check(arguments: dict) -> dict:
    """Handle policy check tool call via MCP."""
    try:
        expense_data = {
            "vendor": arguments["vendor"],
            "amount": arguments["amount"],
            "date": arguments["date"],
            "text": arguments.get("text", "")
        }
        
        result = apply_policy(expense_data)
        
        return {
            "success": True,
            "data": {
                "status": result.get("status"),
                "requires_review": result.get("requires_review"),
                "category": result.get("category"),
                "flag_reason": result.get("flag_reason")
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_db_create_report(arguments: dict) -> dict:
    """Handle database report creation via MCP."""
    try:
        report_id = get_or_create_report(
            arguments["trip_name"],
            employee_name=arguments.get("employee_name"),
            thread_id=arguments.get("thread_id")
        )
        
        return {
            "success": True,
            "data": {"report_id": report_id}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_db_add_expense(arguments: dict) -> dict:
    """Handle adding expense to database via MCP."""
    try:
        add_expense(
            report_id=arguments["report_id"],
            expense_date=arguments["date"],
            vendor=arguments["vendor"],
            amount=arguments["amount"],
            category=arguments.get("category", "Other"),
            status=arguments.get("status", "APPROVED"),
            ocr_text=arguments.get("text", "")
        )
        
        return {"success": True, "data": {"message": "Expense added"}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_db_check_duplicate(arguments: dict) -> dict:
    """Handle duplicate check via MCP."""
    try:
        is_dup = is_duplicate(
            arguments["report_id"],
            arguments["vendor"],
            arguments["amount"],
            arguments["date"]
        )
        
        return {
            "success": True,
            "data": {"is_duplicate": is_dup}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_db_get_trip_status(arguments: dict) -> dict:
    """Handle trip status retrieval via MCP."""
    try:
        trip_data = get_report_by_trip(arguments["trip_name"])
        
        if not trip_data:
            return {"success": False, "error": "Trip not found"}
        
        report_id = trip_data[0]
        expenses = get_expenses_by_report(report_id)
        
        return {
            "success": True,
            "data": {
                "report_id": report_id,
                "status": trip_data[1],
                "duplicate_count": trip_data[2],
                "expense_count": len(expenses),
                "expenses": [
                    {
                        "id": exp[0],
                        "date": exp[1],
                        "vendor": exp[2],
                        "amount": exp[3],
                        "category": exp[4],
                        "status": exp[5]
                    }
                    for exp in expenses
                ]
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# -------------------------------------------------
# SERVER STARTUP
# -------------------------------------------------

async def main():
    """Start the MCP server."""
    async with server:
        print("MCP Server started on stdio")
        await server.wait_for_shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
