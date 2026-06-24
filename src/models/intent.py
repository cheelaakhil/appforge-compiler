"""
Intent Extraction Models — Stage 1 Output

These models define the structured output of the Intent Extraction pass.
They transform messy, open-ended user descriptions into a platform-agnostic
target manifest with documented assumptions for any ambiguous inputs.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FeatureCategory(str, Enum):
    """Canonical categories for application features."""
    AUTH = "auth"
    CRUD = "crud"
    ANALYTICS = "analytics"
    MESSAGING = "messaging"
    PAYMENTS = "payments"
    MEDIA = "media"
    SEARCH = "search"
    ADMIN = "admin"
    NOTIFICATIONS = "notifications"
    SOCIAL = "social"
    INTEGRATIONS = "integrations"
    REPORTING = "reporting"


class FeaturePriority(str, Enum):
    """Priority classification for features."""
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class FeatureSpec(BaseModel):
    """A single application feature extracted from user input."""
    name: str = Field(
        description="Snake_case feature identifier, e.g. 'user_registration'"
    )
    category: FeatureCategory = Field(
        description="Canonical category this feature belongs to"
    )
    description: str = Field(
        description="One-sentence description of what this feature does"
    )
    priority: FeaturePriority = Field(
        description="Whether this feature is essential or optional"
    )
    implied_entities: list[str] = Field(
        default_factory=list,
        description="Entity nouns implied by this feature, e.g. ['User', 'Contact']"
    )


class TechStack(str, Enum):
    """Supported backend frameworks."""
    FASTAPI = "fastapi"
    EXPRESS = "express"
    DJANGO = "django"


class DatabaseType(str, Enum):
    """Supported database types."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    MONGODB = "mongodb"


class FrontendFramework(str, Enum):
    """Supported frontend frameworks."""
    REACT = "react"
    VUE = "vue"
    SVELTE = "svelte"
    NEXTJS = "nextjs"


class TechPreferences(BaseModel):
    """Technology stack preferences — user-stated or defaulted."""
    backend: TechStack = Field(
        default=TechStack.FASTAPI,
        description="Backend framework"
    )
    database: DatabaseType = Field(
        default=DatabaseType.POSTGRESQL,
        description="Primary database"
    )
    frontend: FrontendFramework = Field(
        default=FrontendFramework.REACT,
        description="Frontend framework"
    )
    auth_method: str = Field(
        default="jwt",
        description="Authentication method: 'jwt', 'oauth2', 'session', 'none'"
    )
    deployment_target: str = Field(
        default="docker",
        description="Deployment target: 'docker', 'serverless', 'bare_metal'"
    )


class IntentManifest(BaseModel):
    """
    The complete output of Stage 1: Intent Extraction.

    This is a platform-agnostic inventory of what the user wants,
    with documented assumptions for anything left ambiguous.
    """
    app_name: str = Field(
        description="A concise, slug-friendly application name derived from the input"
    )
    app_description: str = Field(
        description="One-paragraph summary of the application's purpose"
    )
    target_users: list[str] = Field(
        description="Types of users who will use this application, e.g. ['Admin', 'Customer', 'Vendor']"
    )
    features: list[FeatureSpec] = Field(
        description="Complete inventory of features extracted from the input"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Documented assumptions made to fill gaps in vague inputs. "
            "e.g. 'Assumed default payment processor is Stripe'"
        )
    )
    tech_preferences: TechPreferences = Field(
        default_factory=TechPreferences,
        description="Technology stack preferences — user-stated or defaulted"
    )
    ambiguity_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Domains flagged as underspecified in the input. "
            "e.g. 'Payment processing details not specified'"
        )
    )
    raw_input: str = Field(
        description="The original user input string, preserved for traceability"
    )
    domain_tags: list[str] = Field(
        default_factory=list,
        description="High-level domain classifications, e.g. ['e-commerce', 'social', 'saas']"
    )

    def to_context_summary(self) -> dict:
        """Returns a compressed dictionary representation of the intent to save tokens."""
        return {
            "app_name": self.app_name,
            "features": [f.name for f in self.features],
            "target_users": self.target_users,
        }
