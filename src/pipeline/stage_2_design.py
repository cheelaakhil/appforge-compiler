"""
Stage 2: System Design (Intermediate Representation)

Takes the structured IntentManifest and generates the architectural
blueprint: RBAC matrix, entity-relationship graph, feature gates,
and workflow definitions.
"""

from __future__ import annotations
import json

from src.models.intent import IntentManifest
from src.models.design import SystemDesignIR
from src.models.manifest import StageTelemetry
from src.providers.base import BaseLLMProvider

SYSTEM_INSTRUCTION = """You are the System Design stage of a compiler pipeline. You receive a
structured intent manifest (features, users, tech preferences) and produce
an architectural Intermediate Representation (IR).

Your job is to generate:

1. **RBAC Matrix (roles):**
   - Create roles for each distinct user type identified in the intent.
   - Always include an 'admin' role with full permissions.
   - Define granular permissions using the format: resource + action (e.g., "read", "create").
   - Use role inheritance where appropriate (e.g., admin inherits from standard_user).

2. **Entity Graph (entities):**
   - Create an entity for each distinct data object implied by the features.
   - Always include a 'User' entity with standard auth fields (email, password_hash, role).
   - Define fields with appropriate abstract types (string, integer, datetime, etc.).
   - Define relationships between entities (has_many, belongs_to, many_to_many).
   - Mark entities that should NOT be directly API-exposed as is_user_facing=false.

3. **Feature Gates (feature_gates):**
   - Gate features that are role-restricted (e.g., admin dashboard, analytics).
   - Reference feature names from the intent manifest.

4. **Workflows (workflows):**
   - Define multi-step business processes implied by the features.
   - Each workflow should have ordered steps with clear triggers.
   - Common workflows: user registration flow, purchase/checkout flow, content creation flow.

CRITICAL RULES:
- Every entity MUST have fields defined — no empty entities.
- Every relationship's target_entity must reference an entity that exists in the entities list.
- Every feature_gate's feature must reference a feature from the intent manifest.
- Every feature_gate's required_role must reference a role from the roles list.
- Permissions must cover all CRUD operations for all user-facing entities.
- Use snake_case for all field names and entity relationships.
- Use PascalCase for entity names.
"""


def generate_system_design(
    intent: IntentManifest,
    provider: BaseLLMProvider,
    model: str,
) -> tuple[SystemDesignIR, StageTelemetry]:
    """
    Run the System Design pass to produce the architectural IR.

    Args:
        intent: The structured intent manifest from Stage 1.
        provider: The LLM provider.
        model: The model identifier (typically the analytical model).

    Returns:
        Tuple of (SystemDesignIR, StageTelemetry).
    """
    # Serialize the intent summary for context
    intent_json = json.dumps(intent.to_context_summary(), indent=2)

    prompt = f"""Generate a complete System Design Intermediate Representation (IR) for the following application.

--- INTENT MANIFEST ---
{intent_json}
--- END INTENT MANIFEST ---

Based on the features, user types, and tech preferences above, produce:
1. A complete RBAC matrix with all roles and granular permissions
2. All data entities with fields and relationships
3. Feature gates for role-restricted features
4. Key business workflows

Key entities to consider based on features:
{_extract_entity_hints(intent)}

Ensure EVERY entity has concrete fields — do not create empty entities.
Ensure ALL relationships reference valid entities.
"""

    design, telemetry = provider.generate_structured(
        prompt=prompt,
        response_model=SystemDesignIR,
        model=model,
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.15,
    )

    telemetry.stage_name = "system_design"
    return design, telemetry


def _extract_entity_hints(intent: IntentManifest) -> str:
    """Extract entity hints from features to guide the design."""
    entities = set()
    for feature in intent.features:
        for entity in feature.implied_entities:
            entities.add(entity)

    if not entities:
        return "No explicit entities found — infer from features and user types."

    return "Implied entities: " + ", ".join(sorted(entities))
