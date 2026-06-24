"""
Stage 1: Intent Extraction

Transforms raw natural language input into a structured IntentManifest.
Uses the fast model (Flash) for speed, with ambiguity detection and
documented assumption injection for vague inputs.
"""

from __future__ import annotations

from src.models.intent import IntentManifest
from src.models.manifest import StageTelemetry
from src.providers.base import BaseLLMProvider

# Domain-specific assumption bank for common underspecified areas
ASSUMPTION_BANK = {
    "payments": "Assumed default payment processor is Stripe with standard checkout flow",
    "auth": "Assumed email/password authentication with JWT tokens",
    "email": "Assumed transactional email via SMTP (e.g., SendGrid or similar)",
    "storage": "Assumed file storage via local filesystem with S3-compatible interface",
    "search": "Assumed full-text search using database-native search capabilities",
    "notifications": "Assumed in-app notifications with optional email digest",
    "analytics": "Assumed basic analytics dashboard with read-only access for admins",
    "deployment": "Assumed Docker-based deployment with single-service architecture",
    "caching": "Assumed application-level caching with in-memory store",
    "logging": "Assumed structured JSON logging to stdout",
}

SYSTEM_INSTRUCTION = """You are the Intent Extraction stage of a compiler pipeline that converts
natural language application descriptions into structured specifications.

Your job is to:
1. Extract ALL features, entities, and user types mentioned or implied in the input.
2. Classify each feature into a canonical category.
3. Identify any areas that are vague or underspecified and flag them as ambiguity_flags.
4. For each ambiguous area, add a documented assumption from common industry patterns.
5. Assign feature priorities: core functionality = must_have, extras = nice_to_have.
6. Derive a clean, slug-friendly app_name from the description.
7. Identify domain_tags for the application (e.g., 'e-commerce', 'social', 'saas').

IMPORTANT RULES:
- Every application MUST have at minimum: user registration, user login, and a dashboard.
- If no authentication method is mentioned, assume JWT-based email/password auth.
- If no database preference is mentioned, default to PostgreSQL.
- If no frontend preference is mentioned, default to React.
- Extract ALL implied entities (nouns that represent data objects).
- The raw_input field must contain the exact original input string.
- Be thorough — it's better to extract too many features than too few.
"""


def extract_intent(
    user_input: str,
    provider: BaseLLMProvider,
    model: str,
) -> tuple[IntentManifest, StageTelemetry]:
    """
    Run the Intent Extraction pass on raw user input.

    Args:
        user_input: The raw natural language description from the user.
        provider: The LLM provider to use for generation.
        model: The model identifier (typically the fast model).

    Returns:
        Tuple of (IntentManifest, StageTelemetry).
    """
    # Detect ambiguity indicators
    word_count = len(user_input.split())
    ambiguity_hints = []

    if word_count < 5:
        ambiguity_hints.append(
            "INPUT IS VERY SHORT. Extract what you can and make extensive documented assumptions."
        )

    if word_count < 15:
        ambiguity_hints.append(
            "Input is brief. Infer standard features for the implied domain."
        )

    # Build the prompt
    prompt = f"""Analyze the following application description and extract a complete intent manifest.

--- USER INPUT ---
{user_input}
--- END USER INPUT ---

{chr(10).join(ambiguity_hints)}

Remember to:
- Include at minimum: user registration, login, and dashboard features
- Flag any underspecified domains in ambiguity_flags
- Add documented assumptions for each ambiguous area
- Set raw_input to the exact user input string above
- Extract ALL implied entities in each feature's implied_entities field
"""

    intent, telemetry = provider.generate_structured(
        prompt=prompt,
        response_model=IntentManifest,
        model=model,
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.1,
    )

    # Post-processing: ensure raw_input is set correctly
    intent.raw_input = user_input

    # Post-processing: inject assumptions for flagged ambiguities
    for flag in intent.ambiguity_flags:
        flag_lower = flag.lower()
        for domain, assumption in ASSUMPTION_BANK.items():
            if domain in flag_lower and assumption not in intent.assumptions:
                intent.assumptions.append(assumption)

    telemetry.stage_name = "intent_extraction"
    return intent, telemetry
