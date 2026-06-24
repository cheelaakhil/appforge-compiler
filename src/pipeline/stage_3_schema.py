"""
Stage 3: Schema Generation

Produces three independent but aligned schema configurations:
  1. DB Schema (tables, columns, FKs, indexes)
  2. API Schema (endpoints, payloads, auth guards)
  3. UI Schema (pages, components, form fields)

Each schema is generated in sequence so that downstream schemas
can reference upstream outputs for alignment.
"""

from __future__ import annotations
import json

from src.models.design import SystemDesignIR
from src.models.schema import DBSchema, APISchema, UISchema
from src.models.manifest import StageTelemetry
from src.providers.base import BaseLLMProvider

# ---------------------------------------------------------------------------
# System Instructions
# ---------------------------------------------------------------------------

DB_SYSTEM_INSTRUCTION = """You are the Database Schema Generator in a compiler pipeline.
You receive a System Design IR and produce a complete relational database schema.

RULES:
- Every table MUST have: id (INTEGER PRIMARY KEY), created_at (TIMESTAMP), updated_at (TIMESTAMP).
- Use snake_case for all table and column names.
- Table names should be plural (e.g., 'users', 'contacts', 'orders').
- Map abstract field types to concrete SQL types:
  - string → VARCHAR(255), text → TEXT, integer → INTEGER, float → FLOAT
  - boolean → BOOLEAN, datetime → TIMESTAMP, date → DATE, uuid → UUID
  - email → VARCHAR(255), url → TEXT, json → JSON, decimal → DECIMAL(10,2)
  - enum → VARCHAR(50) (list valid values in enum_values)
- Create foreign key columns for belongs_to relationships (e.g., user_id → users.id).
- For many_to_many relationships, create a junction table.
- Add indexes on foreign key columns and frequently queried fields.
- The source_entity field MUST reference a valid entity name from the IR.
- Include a 'users' table derived from the User entity with auth-relevant columns.
"""

API_SYSTEM_INSTRUCTION = """You are the API Schema Generator in a compiler pipeline.
You receive a System Design IR and the generated DB Schema, and produce a REST API specification.

RULES:
- Generate standard CRUD endpoints for each user-facing entity:
  - GET /api/v1/{resource} (list), GET /api/v1/{resource}/{id} (detail)
  - POST /api/v1/{resource} (create), PUT /api/v1/{resource}/{id} (update)
  - DELETE /api/v1/{resource}/{id} (delete)
- Use the DB schema column names in request/response payloads (NOT the IR field names).
- Set auth_guard based on the RBAC matrix — match roles to endpoints.
- Add path_params for endpoints with path variables (e.g., ['user_id']).
- The target_table field MUST reference a valid table name from the DB schema.
- Add auth endpoints: POST /api/v1/auth/login, POST /api/v1/auth/register.
- Request payloads should exclude auto-generated fields (id, created_at, updated_at).
- Response payloads should include all fields.
- Use plural resource names matching table names.
"""

UI_SYSTEM_INSTRUCTION = """You are the UI Schema Generator in a compiler pipeline.
You receive a System Design IR, DB Schema, and API Schema, and produce a UI layout specification.

RULES:
- Create pages for: login, register, dashboard, and each major resource (list + detail views).
- Each page should have components that map to specific API endpoints.
- Form components must have form_fields matching the API request payload field names exactly.
- Table components should list columns matching the API response payload field names.
- Set bound_endpoint to match real API endpoint paths from the API schema.
- Set bound_method to the HTTP method for the bound endpoint.
- Set required_role on components/pages that are role-restricted (from feature gates).
- Login and register pages should be is_public=true.
- Create a navigation structure with items for each major page.
- Use unique, descriptive ids for all components (e.g., 'users_list_table', 'create_contact_form').
"""


# ---------------------------------------------------------------------------
# Schema Generation Functions
# ---------------------------------------------------------------------------

def generate_db_schema(
    design: SystemDesignIR,
    provider: BaseLLMProvider,
    model: str,
) -> tuple[DBSchema, StageTelemetry]:
    """Generate the database schema from the System Design IR."""
    design_json = json.dumps(design.to_context_summary(), indent=2)

    prompt = f"""Generate a complete relational database schema for the following system design.

--- SYSTEM DESIGN IR ---
{design_json}
--- END SYSTEM DESIGN IR ---

Create tables for ALL entities. Include:
- Primary key (id), created_at, updated_at on every table
- Foreign keys for all relationships
- Junction tables for many_to_many relationships
- Appropriate indexes
- The source_entity field linking each table to its IR entity
"""

    db_schema, telemetry = provider.generate_structured(
        prompt=prompt,
        response_model=DBSchema,
        model=model,
        system_instruction=DB_SYSTEM_INSTRUCTION,
        temperature=0.1,
    )

    telemetry.stage_name = "schema_generation_db"
    return db_schema, telemetry


def generate_api_schema(
    design: SystemDesignIR,
    db_schema: DBSchema,
    provider: BaseLLMProvider,
    model: str,
) -> tuple[APISchema, StageTelemetry]:
    """Generate the API schema using the IR and DB schema for alignment."""
    design_json = json.dumps(design.to_context_summary(), indent=2)
    db_summary = json.dumps(db_schema.to_context_summary(), indent=2)

    prompt = f"""Generate a complete REST API specification aligned with the database schema below.

--- SYSTEM DESIGN IR ---
{design_json}
--- END SYSTEM DESIGN IR ---

--- DATABASE SCHEMA (SUMMARY) ---
{db_summary}
--- END DATABASE SCHEMA ---

CRITICAL: Use the EXACT column names from the DB schema in your request/response payloads.
The target_table for each endpoint MUST be a valid table name from the DB schema.
Table names available: {', '.join(db_schema.table_names)}
"""

    api_schema, telemetry = provider.generate_structured(
        prompt=prompt,
        response_model=APISchema,
        model=model,
        system_instruction=API_SYSTEM_INSTRUCTION,
        temperature=0.1,
    )

    telemetry.stage_name = "schema_generation_api"
    return api_schema, telemetry


def generate_ui_schema(
    design: SystemDesignIR,
    db_schema: DBSchema,
    api_schema: APISchema,
    provider: BaseLLMProvider,
    model: str,
) -> tuple[UISchema, StageTelemetry]:
    """Generate the UI schema using all previous outputs for alignment."""
    design_json = json.dumps(design.to_context_summary(), indent=2)
    api_summary = json.dumps(api_schema.to_context_summary(), indent=2)

    prompt = f"""Generate a complete UI schema aligned with the API specification below.

--- SYSTEM DESIGN IR ---
{design_json}
--- END SYSTEM DESIGN IR ---

--- API SCHEMA (SUMMARY) ---
{api_summary}
--- END API SCHEMA ---

CRITICAL:
- Form field names MUST match API request payload field names exactly.
- bound_endpoint values MUST match real API endpoint paths from the API schema.
- Create pages for: login, register, dashboard, and each major resource.
"""

    ui_schema, telemetry = provider.generate_structured(
        prompt=prompt,
        response_model=UISchema,
        model=model,
        system_instruction=UI_SYSTEM_INSTRUCTION,
        temperature=0.1,
    )

    telemetry.stage_name = "schema_generation_ui"
    return ui_schema, telemetry
