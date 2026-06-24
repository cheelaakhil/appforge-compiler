import json
from pathlib import Path
from src.models.manifest import AppManifest, ValidationReport
from src.models.intent import IntentManifest, FeatureSpec, FeatureCategory, FeaturePriority
from src.models.design import SystemDesignIR, Role, Permission, Entity, EntityField, FieldType
from src.models.schema import DBSchema, Table, Column, SQLType, ColumnConstraint, APISchema, Endpoint, HTTPMethod, RequestPayload, PayloadField, ResponsePayload, AuthGuard, UISchema, Page, UIComponent, UIComponentType, FormField

def create_mock_manifest():
    intent = IntentManifest(
        app_name="mock-app",
        app_description="A mock app",
        target_users=["Admin", "User"],
        features=[FeatureSpec(name="auth", category=FeatureCategory.AUTH, description="Login", priority=FeaturePriority.MUST_HAVE)],
        raw_input="Build a mock app",
    )
    
    design = SystemDesignIR(
        roles=[Role(name="admin", description="Admin", permissions=[Permission(resource="users", action="create")])],
        entities=[Entity(name="User", description="User", fields=[EntityField(name="email", field_type=FieldType.EMAIL)])],
    )
    
    db_schema = DBSchema(tables=[
        Table(name="users", columns=[
            Column(name="id", sql_type=SQLType.INTEGER, constraints=[ColumnConstraint.PRIMARY_KEY], nullable=False),
            Column(name="email", sql_type=SQLType.VARCHAR, nullable=False),
            Column(name="created_at", sql_type=SQLType.TIMESTAMP),
            Column(name="updated_at", sql_type=SQLType.TIMESTAMP),
        ], source_entity="User")
    ])
    
    api_schema = APISchema(endpoints=[
        Endpoint(
            path="/api/users", method=HTTPMethod.POST, summary="Create", target_table="users",
            request_payload=RequestPayload(fields=[PayloadField(name="email", field_type="string")])
        )
    ])
    
    ui_schema = UISchema(pages=[
        Page(path="/users", title="Users", components=[
            UIComponent(id="form", component_type=UIComponentType.FORM, title="Form", bound_endpoint="/api/users", bound_method=HTTPMethod.POST, form_fields=[FormField(name="email", label="Email", input_type="email")])
        ])
    ])
    
    manifest = AppManifest(
        intent=intent, design=design, db_schema=db_schema, api_schema=api_schema, ui_schema=ui_schema,
        validation_report=ValidationReport(passed=True, total_checks_run=15, checks_passed=15)
    )
    
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    path = output_dir / "mock_manifest.json"
    with open(path, "w") as f:
        f.write(manifest.model_dump_json(indent=2))
    print(f"Mock manifest created at {path}")

if __name__ == "__main__":
    create_mock_manifest()
