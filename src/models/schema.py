"""
Schema Models — Stage 3 Output

Three independent schema definitions: Database, API, and UI.
Each is generated separately but aligned through the shared System Design IR.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ===========================================================================
# DATABASE SCHEMA
# ===========================================================================

class SQLType(str, Enum):
    """Concrete SQL column types."""
    VARCHAR = "VARCHAR"
    TEXT = "TEXT"
    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    FLOAT = "FLOAT"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    TIMESTAMP = "TIMESTAMP"
    DATE = "DATE"
    UUID = "UUID"
    JSON = "JSON"
    ENUM = "ENUM"


class ColumnConstraint:
    """Column-level constraints."""
    PRIMARY_KEY = "PRIMARY KEY"
    NOT_NULL = "NOT NULL"
    UNIQUE = "UNIQUE"
    DEFAULT = "DEFAULT"
    CHECK = "CHECK"


class Column(BaseModel):
    """A single column in a database table."""
    name: str = Field(description="Snake_case column name")
    sql_type: str = Field(description="Concrete SQL data type")
    constraints: list[str] = Field(
        default_factory=list,
        description="Column constraints"
    )
    default_value: Optional[str] = Field(default=None, description="SQL default expression")
    nullable: bool = Field(default=True, description="Whether NULL is allowed")
    description: str = Field(default="", description="Column purpose")
    enum_values: Optional[list[str]] = Field(
        default=None,
        description="Allowed values for ENUM type columns"
    )
    max_length: Optional[int] = Field(
        default=None,
        description="Max length for VARCHAR columns"
    )


class ForeignKey(BaseModel):
    """A foreign key relationship between tables."""
    column: str = Field(description="Local column name")
    references_table: str = Field(description="Referenced table name")
    references_column: str = Field(default="id", description="Referenced column name")
    on_delete: str = Field(default="CASCADE", description="ON DELETE action")
    on_update: str = Field(default="CASCADE", description="ON UPDATE action")


class Index(BaseModel):
    """A database index."""
    name: str = Field(description="Index name")
    columns: list[str] = Field(description="Columns included in the index")
    unique: bool = Field(default=False, description="Whether this is a unique index")


class Table(BaseModel):
    """A single database table."""
    name: str = Field(description="Snake_case table name, e.g. 'user_profiles'")
    description: str = Field(default="", description="Table purpose")
    columns: list[Column] = Field(description="All columns including id and timestamps")
    foreign_keys: list[ForeignKey] = Field(
        default_factory=list,
        description="Foreign key constraints"
    )
    indexes: list[Index] = Field(
        default_factory=list,
        description="Additional indexes beyond PK"
    )
    source_entity: Optional[str] = Field(
        default=None,
        description="The System Design IR entity this table was derived from"
    )


class DBSchema(BaseModel):
    """Complete database schema — all tables with relationships."""
    tables: list[Table] = Field(description="All database tables")

    def get_table(self, name: str) -> Optional[Table]:
        """Look up a table by name (case-insensitive)."""
        for table in self.tables:
            if table.name.lower() == name.lower():
                return table
        return None

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def get_all_columns(self, table_name: str) -> list[str]:
        """Get all column names for a table."""
        table = self.get_table(table_name)
        if table:
            return [c.name for c in table.columns]
        return []

    def to_context_summary(self) -> dict:
        """Returns a highly compressed dictionary representation of the schema to save tokens."""
        return {
            t.name: [c.name for c in t.columns]
            for t in self.tables
        }


# ===========================================================================
# API SCHEMA
# ===========================================================================
class HTTPMethod(str, Enum):
    """Supported HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
class PayloadField(BaseModel):
    """A single field in a request or response payload."""
    name: str = Field(description="Field name")
    field_type: str = Field(description="Data type: 'string', 'integer', 'boolean', 'object', 'array'")
    required: bool = Field(default=True, description="Whether field is required")
    description: str = Field(default="", description="Field purpose")
    nested_fields: Optional[list[PayloadField]] = Field(
        default=None,
        description="Nested fields for object/array types"
    )


class RequestPayload(BaseModel):
    """Request body specification."""
    content_type: str = Field(default="application/json")
    fields: list[PayloadField] = Field(default_factory=list)


class ResponsePayload(BaseModel):
    """Response body specification."""
    status_code: int = Field(description="HTTP status code")
    content_type: str = Field(default="application/json")
    fields: list[PayloadField] = Field(default_factory=list)
    description: str = Field(default="")


class AuthGuard(BaseModel):
    """Authorization requirement for an endpoint."""
    required: bool = Field(default=True, description="Whether authentication is required")
    allowed_roles: list[str] = Field(
        default_factory=list,
        description="Roles permitted to access this endpoint (empty = any authenticated user)"
    )


class Endpoint(BaseModel):
    """A single API endpoint."""
    path: str = Field(description="URL path, e.g. '/api/v1/users/{user_id}'")
    method: str = Field(description="HTTP method (GET, POST, PUT, PATCH, DELETE)")
    summary: str = Field(description="Brief description of what this endpoint does")
    tags: list[str] = Field(default_factory=list, description="Grouping tags")
    auth_guard: AuthGuard = Field(
        default_factory=AuthGuard,
        description="Authorization requirements"
    )
    request_payload: Optional[RequestPayload] = Field(
        default=None,
        description="Request body specification (for POST/PUT/PATCH)"
    )
    response_payloads: list[ResponsePayload] = Field(
        default_factory=list,
        description="Possible response specifications"
    )
    target_table: Optional[str] = Field(
        default=None,
        description="The DB table this endpoint primarily operates on"
    )
    path_params: list[str] = Field(
        default_factory=list,
        description="Path parameter names, e.g. ['user_id']"
    )
    query_params: list[PayloadField] = Field(
        default_factory=list,
        description="Query parameter specifications"
    )


class APISchema(BaseModel):
    """Complete API schema — all endpoints."""
    base_url: str = Field(default="/api/v1", description="API base URL prefix")
    endpoints: list[Endpoint] = Field(description="All API endpoints")

    def get_endpoints_for_table(self, table_name: str) -> list[Endpoint]:
        """Get all endpoints targeting a specific table."""
        return [e for e in self.endpoints if e.target_table == table_name]

    @property
    def all_paths(self) -> list[str]:
        return [f"{e.method} {e.path}" for e in self.endpoints]

    def to_context_summary(self) -> dict:
        """Returns a highly compressed dictionary representation of the schema to save tokens."""
        return {
            "base_url": self.base_url,
            "endpoints": [f"{e.method} {e.path} ({e.summary})" for e in self.endpoints]
        }


# ===========================================================================
# UI SCHEMA
# ===========================================================================

class UIComponentType(str, Enum):
    """Types of UI components."""
    PAGE = "page"
    FORM = "form"
    TABLE = "table"
    DETAIL_VIEW = "detail_view"
    DASHBOARD = "dashboard"
    MODAL = "modal"
    NAVIGATION = "navigation"
    CARD = "card"
    LIST = "list"
    CHART = "chart"
    SEARCH_BAR = "search_bar"
    BUTTON = "button"


class FormField(BaseModel):
    """A single form input field."""
    name: str = Field(description="Field name matching API payload field")
    label: str = Field(description="Human-readable label")
    input_type: str = Field(
        description="Input type: 'text', 'email', 'password', 'number', 'select', 'textarea', 'date', 'checkbox', 'file'"
    )
    required: bool = Field(default=True)
    placeholder: str = Field(default="")
    options: Optional[list[str]] = Field(
        default=None,
        description="Options for select/radio inputs"
    )
    validation_rules: Optional[list[str]] = Field(
        default=None,
        description="Client-side validation rules, e.g. ['min_length:3', 'max_length:100']"
    )


class UIComponent(BaseModel):
    """A single UI component."""
    id: str = Field(description="Unique component identifier")
    component_type: str = Field(description="Component type (page, form, table, modal, etc.)")
    title: str = Field(description="Display title")
    description: str = Field(default="", description="Component purpose")
    bound_endpoint: Optional[str] = Field(
        default=None,
        description="API endpoint path this component is bound to"
    )
    bound_method: Optional[str] = Field(
        default=None,
        description="HTTP method for the bound endpoint"
    )
    form_fields: Optional[list[FormField]] = Field(
        default=None,
        description="Form fields (for form components)"
    )
    children: Optional[list[UIComponent]] = Field(
        default=None,
        description="Nested child components"
    )
    required_role: Optional[str] = Field(
        default=None,
        description="Role required to see this component"
    )
    columns: Optional[list[str]] = Field(
        default=None,
        description="Column names for table components"
    )


class Page(BaseModel):
    """A single page/view in the application."""
    path: str = Field(description="Frontend route path, e.g. '/users'")
    title: str = Field(description="Page title")
    description: str = Field(default="")
    components: list[UIComponent] = Field(description="Components on this page")
    required_role: Optional[str] = Field(
        default=None,
        description="Minimum role required to access this page"
    )
    is_public: bool = Field(default=False, description="Whether this page is publicly accessible")


class NavigationItem(BaseModel):
    """A navigation menu item."""
    label: str = Field(description="Menu label")
    path: str = Field(description="Route path")
    icon: str = Field(default="", description="Icon name/class")
    required_role: Optional[str] = Field(default=None)
    children: Optional[list[NavigationItem]] = Field(default=None)


class UISchema(BaseModel):
    """Complete UI schema — pages, navigation, and component tree."""
    pages: list[Page] = Field(description="All pages in the application")
    navigation: list[NavigationItem] = Field(
        default_factory=list,
        description="Main navigation structure"
    )
    default_page: str = Field(
        default="/dashboard",
        description="Default landing page path"
    )

    def get_page(self, path: str) -> Optional[Page]:
        """Look up a page by route path."""
        for page in self.pages:
            if page.path == path:
                return page
        return None

    @property
    def all_bound_endpoints(self) -> list[str]:
        """Collect all API endpoints referenced by UI components."""
        endpoints = []
        for page in self.pages:
            for component in page.components:
                self._collect_endpoints(component, endpoints)
        return list(set(endpoints))

    def _collect_endpoints(self, component: UIComponent, endpoints: list[str]) -> None:
        if component.bound_endpoint:
            endpoints.append(component.bound_endpoint)
        for child in (component.children or []):
            self._collect_endpoints(child, endpoints)
