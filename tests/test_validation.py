"""
Unit Tests: Validation Layer

Tests structural and referential validation checks using
known-good and known-bad schema fixtures.
"""

from __future__ import annotations

import pytest

from src.models.design import (
    SystemDesignIR,
    Role,
    Permission,
    Entity,
    EntityField,
    FieldType,
    Relationship,
    RelationshipType,
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
)
from src.models.manifest import ValidationSeverity, ValidationErrorCategory
from src.validation.structural import run_structural_checks
from src.validation.referential import run_referential_checks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def good_db_schema() -> DBSchema:
    """A well-formed DB schema with no errors."""
    return DBSchema(tables=[
        Table(
            name="users",
            columns=[
                Column(name="id", sql_type=SQLType.INTEGER, constraints=[ColumnConstraint.PRIMARY_KEY], nullable=False),
                Column(name="email", sql_type=SQLType.VARCHAR, max_length=255, nullable=False),
                Column(name="name", sql_type=SQLType.VARCHAR, max_length=255),
                Column(name="created_at", sql_type=SQLType.TIMESTAMP),
                Column(name="updated_at", sql_type=SQLType.TIMESTAMP),
            ],
            source_entity="User",
        ),
        Table(
            name="posts",
            columns=[
                Column(name="id", sql_type=SQLType.INTEGER, constraints=[ColumnConstraint.PRIMARY_KEY], nullable=False),
                Column(name="title", sql_type=SQLType.VARCHAR, max_length=255, nullable=False),
                Column(name="body", sql_type=SQLType.TEXT),
                Column(name="user_id", sql_type=SQLType.INTEGER, nullable=False),
                Column(name="created_at", sql_type=SQLType.TIMESTAMP),
                Column(name="updated_at", sql_type=SQLType.TIMESTAMP),
            ],
            foreign_keys=[
                ForeignKey(column="user_id", references_table="users", references_column="id"),
            ],
            source_entity="Post",
        ),
    ])


@pytest.fixture
def good_api_schema() -> APISchema:
    return APISchema(endpoints=[
        Endpoint(
            path="/api/v1/users",
            method=HTTPMethod.GET,
            summary="List users",
            target_table="users",
        ),
        Endpoint(
            path="/api/v1/users/{user_id}",
            method=HTTPMethod.GET,
            summary="Get user",
            target_table="users",
            path_params=["user_id"],
        ),
        Endpoint(
            path="/api/v1/posts",
            method=HTTPMethod.POST,
            summary="Create post",
            target_table="posts",
            request_payload=RequestPayload(fields=[
                PayloadField(name="title", field_type="string"),
                PayloadField(name="body", field_type="string"),
                PayloadField(name="user_id", field_type="integer"),
            ]),
        ),
    ])


@pytest.fixture
def good_ui_schema() -> UISchema:
    return UISchema(pages=[
        Page(
            path="/users",
            title="Users",
            components=[
                UIComponent(
                    id="users_table",
                    component_type=UIComponentType.TABLE,
                    title="Users List",
                    bound_endpoint="/api/v1/users",
                    bound_method=HTTPMethod.GET,
                ),
            ],
        ),
        Page(
            path="/posts/new",
            title="Create Post",
            components=[
                UIComponent(
                    id="create_post_form",
                    component_type=UIComponentType.FORM,
                    title="New Post",
                    bound_endpoint="/api/v1/posts",
                    bound_method=HTTPMethod.POST,
                    form_fields=[
                        FormField(name="title", label="Title", input_type="text"),
                        FormField(name="body", label="Body", input_type="textarea"),
                    ],
                ),
            ],
        ),
    ])


@pytest.fixture
def good_design() -> SystemDesignIR:
    return SystemDesignIR(
        roles=[
            Role(
                name="admin",
                description="Full access",
                permissions=[Permission(resource="users", action="read")],
            ),
        ],
        entities=[
            Entity(
                name="User",
                description="App user",
                fields=[EntityField(name="email", field_type=FieldType.EMAIL)],
            ),
            Entity(
                name="Post",
                description="Blog post",
                fields=[EntityField(name="title", field_type=FieldType.STRING)],
                relationships=[
                    Relationship(target_entity="User", relationship_type=RelationshipType.BELONGS_TO),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Structural Validation Tests
# ---------------------------------------------------------------------------

class TestStructuralValidation:
    def test_good_schema_has_no_errors(self, good_db_schema, good_api_schema, good_ui_schema):
        errors = run_structural_checks(good_db_schema, good_api_schema, good_ui_schema)
        critical_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(critical_errors) == 0

    def test_empty_db_tables(self, good_api_schema, good_ui_schema):
        empty_db = DBSchema(tables=[])
        errors = run_structural_checks(empty_db, good_api_schema, good_ui_schema)
        assert any(e.message == "DB schema has no tables defined" for e in errors)

    def test_duplicate_table_names(self, good_api_schema, good_ui_schema):
        dup_db = DBSchema(tables=[
            Table(name="users", columns=[
                Column(name="id", sql_type=SQLType.INTEGER, nullable=False),
            ], source_entity="User"),
            Table(name="users", columns=[
                Column(name="id", sql_type=SQLType.INTEGER, nullable=False),
            ], source_entity="User2"),
        ])
        errors = run_structural_checks(dup_db, good_api_schema, good_ui_schema)
        assert any("Duplicate table name" in e.message for e in errors)

    def test_empty_columns(self, good_api_schema, good_ui_schema):
        no_cols_db = DBSchema(tables=[
            Table(name="users", columns=[], source_entity="User"),
        ])
        errors = run_structural_checks(no_cols_db, good_api_schema, good_ui_schema)
        assert any("no columns" in e.message for e in errors)

    def test_duplicate_endpoint_routes(self, good_db_schema, good_ui_schema):
        dup_api = APISchema(endpoints=[
            Endpoint(path="/api/v1/users", method=HTTPMethod.GET, summary="List", target_table="users"),
            Endpoint(path="/api/v1/users", method=HTTPMethod.GET, summary="List2", target_table="users"),
        ])
        errors = run_structural_checks(good_db_schema, dup_api, good_ui_schema)
        assert any("Duplicate endpoint" in e.message for e in errors)

    def test_bad_path_format(self, good_db_schema, good_ui_schema):
        bad_api = APISchema(endpoints=[
            Endpoint(path="api/v1/users", method=HTTPMethod.GET, summary="List", target_table="users"),
        ])
        errors = run_structural_checks(good_db_schema, bad_api, good_ui_schema)
        assert any("must start with '/'" in e.message for e in errors)

    def test_duplicate_page_paths(self, good_db_schema, good_api_schema):
        dup_ui = UISchema(pages=[
            Page(path="/users", title="Users", components=[]),
            Page(path="/users", title="Users2", components=[]),
        ])
        errors = run_structural_checks(good_db_schema, good_api_schema, dup_ui)
        assert any("Duplicate page path" in e.message for e in errors)

    def test_fk_column_not_in_table(self, good_api_schema, good_ui_schema):
        bad_fk_db = DBSchema(tables=[
            Table(
                name="posts",
                columns=[
                    Column(name="id", sql_type=SQLType.INTEGER, nullable=False),
                ],
                foreign_keys=[
                    ForeignKey(column="user_id", references_table="users", references_column="id"),
                ],
                source_entity="Post",
            ),
        ])
        errors = run_structural_checks(bad_fk_db, good_api_schema, good_ui_schema)
        assert any("FK column 'user_id' not found" in e.message for e in errors)


# ---------------------------------------------------------------------------
# Referential Integrity Tests
# ---------------------------------------------------------------------------

class TestReferentialValidation:
    def test_good_schemas_have_no_ref_errors(
        self, good_design, good_db_schema, good_api_schema, good_ui_schema,
    ):
        errors = run_referential_checks(good_design, good_db_schema, good_api_schema, good_ui_schema)
        critical = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(critical) == 0

    def test_api_references_nonexistent_table(self, good_design, good_db_schema, good_ui_schema):
        bad_api = APISchema(endpoints=[
            Endpoint(
                path="/api/v1/comments",
                method=HTTPMethod.GET,
                summary="List comments",
                target_table="comments",  # Does not exist in DB
            ),
        ])
        errors = run_referential_checks(good_design, good_db_schema, bad_api, good_ui_schema)
        assert any("non-existent table" in e.message for e in errors)

    def test_ui_references_nonexistent_endpoint(self, good_design, good_db_schema, good_api_schema):
        bad_ui = UISchema(pages=[
            Page(
                path="/comments",
                title="Comments",
                components=[
                    UIComponent(
                        id="comments_table",
                        component_type=UIComponentType.TABLE,
                        title="Comments",
                        bound_endpoint="/api/v1/comments",  # Does not exist
                    ),
                ],
            ),
        ])
        errors = run_referential_checks(good_design, good_db_schema, good_api_schema, bad_ui)
        assert any("non-existent" in e.message.lower() for e in errors)

    def test_fk_references_nonexistent_table(self, good_design, good_api_schema, good_ui_schema):
        bad_fk_db = DBSchema(tables=[
            Table(
                name="posts",
                columns=[
                    Column(name="id", sql_type=SQLType.INTEGER, nullable=False),
                    Column(name="category_id", sql_type=SQLType.INTEGER),
                ],
                foreign_keys=[
                    ForeignKey(column="category_id", references_table="categories"),
                ],
                source_entity="Post",
            ),
        ])
        errors = run_referential_checks(good_design, bad_fk_db, good_api_schema, good_ui_schema)
        assert any("non-existent table 'categories'" in e.message for e in errors)

    def test_naming_mismatch_detected(self, good_design, good_ui_schema):
        """API uses 'user_email' but DB has 'email' — should flag naming mismatch."""
        db = DBSchema(tables=[
            Table(
                name="users",
                columns=[
                    Column(name="id", sql_type=SQLType.INTEGER, nullable=False),
                    Column(name="email", sql_type=SQLType.VARCHAR, nullable=False),
                    Column(name="created_at", sql_type=SQLType.TIMESTAMP),
                    Column(name="updated_at", sql_type=SQLType.TIMESTAMP),
                ],
                source_entity="User",
            ),
        ])
        api = APISchema(endpoints=[
            Endpoint(
                path="/api/v1/users",
                method=HTTPMethod.POST,
                summary="Create user",
                target_table="users",
                request_payload=RequestPayload(fields=[
                    PayloadField(name="user_email", field_type="string"),
                ]),
            ),
        ])
        errors = run_referential_checks(good_design, db, api, good_ui_schema)
        naming_errors = [
            e for e in errors
            if e.category == ValidationErrorCategory.NAMING_MISMATCH
        ]
        assert len(naming_errors) > 0
