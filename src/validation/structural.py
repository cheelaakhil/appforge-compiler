"""
Structural Validators

Rule-based checks that verify the internal structural correctness of
each schema independently (no cross-schema references).
"""

from __future__ import annotations

from src.models.schema import (
    DBSchema, APISchema, UISchema,
    SQLType, HTTPMethod, Column, ColumnConstraint,
)
from src.models.manifest import (
    ValidationError,
    ValidationSeverity,
    ValidationErrorCategory,
)


def run_structural_checks(
    db_schema: DBSchema,
    api_schema: APISchema,
    ui_schema: UISchema,
) -> list[ValidationError]:
    """Run all structural validation checks."""
    errors: list[ValidationError] = []
    errors.extend(_check_db_structure(db_schema))
    errors.extend(_check_api_structure(api_schema))
    errors.extend(_check_ui_structure(ui_schema))
    return errors


# ---------------------------------------------------------------------------
# Database structural checks
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {"id", "created_at", "updated_at"}


def _check_db_structure(db: DBSchema) -> list[ValidationError]:
    errors: list[ValidationError] = []

    if not db.tables:
        errors.append(ValidationError(
            category=ValidationErrorCategory.STRUCTURAL,
            severity=ValidationSeverity.ERROR,
            message="DB schema has no tables defined",
            location="db_schema.tables",
        ))
        return errors

    table_names = set()
    for i, table in enumerate(db.tables):
        loc_prefix = f"db_schema.tables[{i}]"

        # Check for duplicate table names
        if table.name.lower() in table_names:
            errors.append(ValidationError(
                category=ValidationErrorCategory.STRUCTURAL,
                severity=ValidationSeverity.ERROR,
                message=f"Duplicate table name: '{table.name}'",
                location=f"{loc_prefix}.name",
            ))
        table_names.add(table.name.lower())

        # Check for empty columns
        if not table.columns:
            errors.append(ValidationError(
                category=ValidationErrorCategory.STRUCTURAL,
                severity=ValidationSeverity.ERROR,
                message=f"Table '{table.name}' has no columns defined",
                location=f"{loc_prefix}.columns",
            ))
            continue

        # Check required columns (id, created_at, updated_at)
        column_names = {c.name.lower() for c in table.columns}
        for req_col in REQUIRED_COLUMNS:
            if req_col not in column_names:
                errors.append(ValidationError(
                    category=ValidationErrorCategory.MISSING_FIELD,
                    severity=ValidationSeverity.WARNING,
                    message=f"Table '{table.name}' missing standard column '{req_col}'",
                    location=f"{loc_prefix}.columns",
                    expected=req_col,
                    suggestion=f"Add '{req_col}' column to table '{table.name}'",
                ))

        # Check for duplicate column names within a table
        col_names_seen = set()
        for j, col in enumerate(table.columns):
            if col.name.lower() in col_names_seen:
                errors.append(ValidationError(
                    category=ValidationErrorCategory.STRUCTURAL,
                    severity=ValidationSeverity.ERROR,
                    message=f"Duplicate column '{col.name}' in table '{table.name}'",
                    location=f"{loc_prefix}.columns[{j}]",
                ))
            col_names_seen.add(col.name.lower())

        # Check FK columns exist in the table
        for j, fk in enumerate(table.foreign_keys):
            if fk.column.lower() not in column_names:
                errors.append(ValidationError(
                    category=ValidationErrorCategory.MISSING_FIELD,
                    severity=ValidationSeverity.ERROR,
                    message=f"FK column '{fk.column}' not found in table '{table.name}'",
                    location=f"{loc_prefix}.foreign_keys[{j}]",
                    expected=fk.column,
                    suggestion=f"Add column '{fk.column}' to table '{table.name}' or fix the FK definition",
                ))

    return errors


# ---------------------------------------------------------------------------
# API structural checks
# ---------------------------------------------------------------------------

def _check_api_structure(api: APISchema) -> list[ValidationError]:
    errors: list[ValidationError] = []

    if not api.endpoints:
        errors.append(ValidationError(
            category=ValidationErrorCategory.STRUCTURAL,
            severity=ValidationSeverity.ERROR,
            message="API schema has no endpoints defined",
            location="api_schema.endpoints",
        ))
        return errors

    # Check for duplicate method+path combinations
    seen_routes = set()
    for i, endpoint in enumerate(api.endpoints):
        loc_prefix = f"api_schema.endpoints[{i}]"
        route_key = f"{endpoint.method} {endpoint.path}"

        if route_key in seen_routes:
            errors.append(ValidationError(
                category=ValidationErrorCategory.ENDPOINT_CONFLICT,
                severity=ValidationSeverity.ERROR,
                message=f"Duplicate endpoint: {route_key}",
                location=f"{loc_prefix}",
            ))
        seen_routes.add(route_key)

        # Validate path format
        if not endpoint.path.startswith("/"):
            errors.append(ValidationError(
                category=ValidationErrorCategory.STRUCTURAL,
                severity=ValidationSeverity.ERROR,
                message=f"Endpoint path must start with '/': '{endpoint.path}'",
                location=f"{loc_prefix}.path",
                suggestion=f"Change path to '/{endpoint.path}'",
            ))

        # Validate path params exist in path
        for param in endpoint.path_params:
            if f"{{{param}}}" not in endpoint.path:
                errors.append(ValidationError(
                    category=ValidationErrorCategory.STRUCTURAL,
                    severity=ValidationSeverity.WARNING,
                    message=f"Path param '{param}' declared but not in path '{endpoint.path}'",
                    location=f"{loc_prefix}.path_params",
                ))

        # POST/PUT/PATCH should have request payloads
        if endpoint.method in (HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH):
            if endpoint.request_payload is None or not endpoint.request_payload.fields:
                errors.append(ValidationError(
                    category=ValidationErrorCategory.MISSING_FIELD,
                    severity=ValidationSeverity.WARNING,
                    message=f"Endpoint {route_key} has no request payload defined",
                    location=f"{loc_prefix}.request_payload",
                    suggestion="Add request payload fields",
                ))

    return errors


# ---------------------------------------------------------------------------
# UI structural checks
# ---------------------------------------------------------------------------

def _check_ui_structure(ui: UISchema) -> list[ValidationError]:
    errors: list[ValidationError] = []

    if not ui.pages:
        errors.append(ValidationError(
            category=ValidationErrorCategory.STRUCTURAL,
            severity=ValidationSeverity.ERROR,
            message="UI schema has no pages defined",
            location="ui_schema.pages",
        ))
        return errors

    # Check for duplicate page paths
    page_paths = set()
    component_ids = set()

    for i, page in enumerate(ui.pages):
        loc_prefix = f"ui_schema.pages[{i}]"

        if page.path in page_paths:
            errors.append(ValidationError(
                category=ValidationErrorCategory.STRUCTURAL,
                severity=ValidationSeverity.ERROR,
                message=f"Duplicate page path: '{page.path}'",
                location=f"{loc_prefix}.path",
            ))
        page_paths.add(page.path)

        # Check component IDs are unique
        for j, component in enumerate(page.components):
            _check_component_ids(
                component, f"{loc_prefix}.components[{j}]",
                component_ids, errors
            )

    # Check navigation items reference valid pages
    for i, nav_item in enumerate(ui.navigation):
        if nav_item.path not in page_paths:
            errors.append(ValidationError(
                category=ValidationErrorCategory.REFERENCE_INTEGRITY,
                severity=ValidationSeverity.WARNING,
                message=f"Navigation item '{nav_item.label}' references non-existent page: '{nav_item.path}'",
                location=f"ui_schema.navigation[{i}]",
            ))

    return errors


def _check_component_ids(
    component,
    loc_prefix: str,
    seen_ids: set,
    errors: list[ValidationError],
) -> None:
    """Recursively check component IDs for uniqueness."""
    if component.id in seen_ids:
        errors.append(ValidationError(
            category=ValidationErrorCategory.STRUCTURAL,
            severity=ValidationSeverity.WARNING,
            message=f"Duplicate component ID: '{component.id}'",
            location=f"{loc_prefix}.id",
        ))
    seen_ids.add(component.id)

    for k, child in enumerate(component.children or []):
        _check_component_ids(child, f"{loc_prefix}.children[{k}]", seen_ids, errors)
