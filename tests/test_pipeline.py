"""
Unit Tests: Pipeline Stages

Tests Pydantic model validation and pipeline stage contracts
without requiring an LLM provider (uses mock data).
"""

from __future__ import annotations

import json
import pytest

from src.models.intent import (
    IntentManifest,
    FeatureSpec,
    FeatureCategory,
    FeaturePriority,
    TechPreferences,
)
from src.models.design import (
    SystemDesignIR,
    Role,
    Permission,
    Entity,
    EntityField,
    FieldType,
    Relationship,
    RelationshipType,
    FeatureGate,
    Workflow,
    WorkflowStep,
    WorkflowStepType,
)
from src.models.schema import (
    DBSchema,
    Table,
    Column,
    SQLType,
    ColumnConstraint,
    ForeignKey,
    APISchema,
    Endpoint,
    HTTPMethod,
    PayloadField,
    RequestPayload,
    AuthGuard,
    ResponsePayload,
    UISchema,
    Page,
    UIComponent,
    UIComponentType,
    FormField,
    NavigationItem,
)
from src.models.manifest import (
    AppManifest,
    ManifestMetadata,
    ValidationReport,
    RuntimeTestResult,
    RuntimeTestStatus,
    PipelineTelemetry,
)


# ---------------------------------------------------------------------------
# Fixtures: Minimal valid instances for each model
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_intent() -> IntentManifest:
    return IntentManifest(
        app_name="test-app",
        app_description="A test application",
        target_users=["Admin", "User"],
        features=[
            FeatureSpec(
                name="user_registration",
                category=FeatureCategory.AUTH,
                description="Users can register",
                priority=FeaturePriority.MUST_HAVE,
            )
        ],
        raw_input="Build a test app",
    )


@pytest.fixture
def minimal_design() -> SystemDesignIR:
    return SystemDesignIR(
        roles=[
            Role(
                name="admin",
                description="Full access",
                permissions=[Permission(resource="users", action="create")],
            ),
            Role(
                name="user",
                description="Standard access",
                permissions=[Permission(resource="users", action="read")],
            ),
        ],
        entities=[
            Entity(
                name="User",
                description="Application user",
                fields=[
                    EntityField(name="email", field_type=FieldType.EMAIL),
                    EntityField(name="password_hash", field_type=FieldType.STRING),
                ],
            ),
        ],
    )


@pytest.fixture
def minimal_db_schema() -> DBSchema:
    return DBSchema(tables=[
        Table(
            name="users",
            columns=[
                Column(name="id", sql_type=SQLType.INTEGER, constraints=[ColumnConstraint.PRIMARY_KEY], nullable=False),
                Column(name="email", sql_type=SQLType.VARCHAR, max_length=255, nullable=False),
                Column(name="password_hash", sql_type=SQLType.VARCHAR, max_length=255, nullable=False),
                Column(name="created_at", sql_type=SQLType.TIMESTAMP),
                Column(name="updated_at", sql_type=SQLType.TIMESTAMP),
            ],
            source_entity="User",
        ),
    ])


@pytest.fixture
def minimal_api_schema() -> APISchema:
    return APISchema(endpoints=[
        Endpoint(
            path="/api/v1/users",
            method=HTTPMethod.GET,
            summary="List users",
            target_table="users",
            auth_guard=AuthGuard(required=True, allowed_roles=["admin"]),
            response_payloads=[
                ResponsePayload(status_code=200, fields=[
                    PayloadField(name="id", field_type="integer"),
                    PayloadField(name="email", field_type="string"),
                ]),
            ],
        ),
        Endpoint(
            path="/api/v1/users",
            method=HTTPMethod.POST,
            summary="Create user",
            target_table="users",
            request_payload=RequestPayload(fields=[
                PayloadField(name="email", field_type="string"),
                PayloadField(name="password_hash", field_type="string"),
            ]),
            response_payloads=[
                ResponsePayload(status_code=201, fields=[
                    PayloadField(name="id", field_type="integer"),
                    PayloadField(name="email", field_type="string"),
                ]),
            ],
        ),
    ])


@pytest.fixture
def minimal_ui_schema() -> UISchema:
    return UISchema(pages=[
        Page(
            path="/login",
            title="Login",
            is_public=True,
            components=[
                UIComponent(
                    id="login_form",
                    component_type=UIComponentType.FORM,
                    title="Login",
                    bound_endpoint="/api/v1/auth/login",
                    bound_method=HTTPMethod.POST,
                    form_fields=[
                        FormField(name="email", label="Email", input_type="email"),
                        FormField(name="password", label="Password", input_type="password"),
                    ],
                ),
            ],
        ),
    ])


# ---------------------------------------------------------------------------
# Tests: Pydantic Model Validation
# ---------------------------------------------------------------------------

class TestIntentModels:
    def test_intent_manifest_creation(self, minimal_intent):
        assert minimal_intent.app_name == "test-app"
        assert len(minimal_intent.features) == 1
        assert minimal_intent.features[0].category == FeatureCategory.AUTH

    def test_intent_manifest_serialization(self, minimal_intent):
        json_str = minimal_intent.model_dump_json()
        restored = IntentManifest.model_validate_json(json_str)
        assert restored.app_name == minimal_intent.app_name

    def test_tech_preferences_defaults(self):
        prefs = TechPreferences()
        assert prefs.backend.value == "fastapi"
        assert prefs.database.value == "postgresql"
        assert prefs.frontend.value == "react"

    def test_feature_spec_all_categories(self):
        for cat in FeatureCategory:
            spec = FeatureSpec(
                name=f"test_{cat.value}",
                category=cat,
                description=f"Test {cat.value}",
                priority=FeaturePriority.MUST_HAVE,
            )
            assert spec.category == cat


class TestDesignModels:
    def test_system_design_ir_creation(self, minimal_design):
        assert len(minimal_design.roles) == 2
        assert len(minimal_design.entities) == 1

    def test_entity_lookup(self, minimal_design):
        user = minimal_design.get_entity("User")
        assert user is not None
        assert user.name == "User"

    def test_entity_lookup_case_insensitive(self, minimal_design):
        user = minimal_design.get_entity("user")
        assert user is not None

    def test_role_lookup(self, minimal_design):
        admin = minimal_design.get_role("admin")
        assert admin is not None
        assert admin.name == "admin"

    def test_permission_key(self):
        perm = Permission(resource="users", action="create")
        assert perm.key == "create:users"

    def test_entity_names_property(self, minimal_design):
        assert minimal_design.entity_names == ["User"]


class TestSchemaModels:
    def test_db_schema_table_lookup(self, minimal_db_schema):
        table = minimal_db_schema.get_table("users")
        assert table is not None
        assert len(table.columns) == 5

    def test_db_schema_column_names(self, minimal_db_schema):
        cols = minimal_db_schema.get_all_columns("users")
        assert "id" in cols
        assert "email" in cols

    def test_api_schema_endpoint_lookup(self, minimal_api_schema):
        endpoints = minimal_api_schema.get_endpoints_for_table("users")
        assert len(endpoints) == 2

    def test_api_schema_all_paths(self, minimal_api_schema):
        paths = minimal_api_schema.all_paths
        assert "GET /api/v1/users" in paths
        assert "POST /api/v1/users" in paths

    def test_ui_schema_page_lookup(self, minimal_ui_schema):
        page = minimal_ui_schema.get_page("/login")
        assert page is not None
        assert page.title == "Login"


class TestManifestModels:
    def test_manifest_metadata_hash(self):
        hash1 = ManifestMetadata.hash_prompt("test")
        hash2 = ManifestMetadata.hash_prompt("test")
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256

    def test_validation_report_pass_rate(self):
        report = ValidationReport(
            passed=True,
            total_checks_run=10,
            checks_passed=8,
        )
        assert report.pass_rate == 0.8

    def test_full_manifest_creation(
        self, minimal_intent, minimal_design, minimal_db_schema,
        minimal_api_schema, minimal_ui_schema,
    ):
        manifest = AppManifest(
            intent=minimal_intent,
            design=minimal_design,
            db_schema=minimal_db_schema,
            api_schema=minimal_api_schema,
            ui_schema=minimal_ui_schema,
        )
        assert manifest.metadata.version == "1.0.0"
        assert manifest.intent.app_name == "test-app"

    def test_manifest_round_trip(
        self, minimal_intent, minimal_design, minimal_db_schema,
        minimal_api_schema, minimal_ui_schema,
    ):
        manifest = AppManifest(
            intent=minimal_intent,
            design=minimal_design,
            db_schema=minimal_db_schema,
            api_schema=minimal_api_schema,
            ui_schema=minimal_ui_schema,
        )
        json_str = manifest.model_dump_json()
        restored = AppManifest.model_validate_json(json_str)
        assert restored.intent.app_name == "test-app"
        assert len(restored.db_schema.tables) == 1


# ---------------------------------------------------------------------------
# Smoke test (requires no LLM)
# ---------------------------------------------------------------------------

class TestPipelineSmoke:
    def test_runtime_simulation_with_minimal_schema(
        self, minimal_db_schema, minimal_api_schema,
    ):
        """Test that the runtime simulator works with a minimal valid schema."""
        from src.runtime.simulator import run_simulation

        result, telemetry = run_simulation(minimal_db_schema, minimal_api_schema)
        assert result.db_boot_status.value in ("passed", "failed")
        assert telemetry.duration_seconds >= 0
