"""
Referential Integrity Validators

Cross-layer checks that verify references between schemas are consistent:
  - API endpoints reference valid DB tables/columns
  - UI components reference valid API endpoints
  - FK references point to existing tables
  - Feature gates reference valid roles/features
"""

from __future__ import annotations

from thefuzz import fuzz

from src.models.design import SystemDesignIR
from src.models.schema import DBSchema, APISchema, UISchema, HTTPMethod
from src.models.manifest import (
    ValidationError,
    ValidationSeverity,
    ValidationErrorCategory,
)


# Minimum fuzzy match score to flag a naming mismatch (vs. completely missing)
FUZZY_MATCH_THRESHOLD = 75


def run_referential_checks(
    design: SystemDesignIR,
    db_schema: DBSchema,
    api_schema: APISchema,
    ui_schema: UISchema,
) -> list[ValidationError]:
    """Run all cross-layer referential integrity checks."""
    errors: list[ValidationError] = []
    errors.extend(_check_api_to_db_refs(db_schema, api_schema))
    errors.extend(_check_ui_to_api_refs(api_schema, ui_schema))
    errors.extend(_check_db_fk_integrity(db_schema))
    errors.extend(_check_payload_field_alignment(db_schema, api_schema))
    errors.extend(_check_form_field_alignment(api_schema, ui_schema))
    return errors


# ---------------------------------------------------------------------------
# API → DB reference checks
# ---------------------------------------------------------------------------

def _check_api_to_db_refs(db: DBSchema, api: APISchema) -> list[ValidationError]:
    """Verify every API endpoint's target_table exists in the DB schema."""
    errors: list[ValidationError] = []
    table_names_lower = {t.name.lower() for t in db.tables}

    for i, endpoint in enumerate(api.endpoints):
        loc = f"api_schema.endpoints[{i}]"

        if not endpoint.target_table:
            continue

        if endpoint.target_table.lower() not in table_names_lower:
            # Try fuzzy match
            suggestion = _fuzzy_find(endpoint.target_table, [t.name for t in db.tables])

            errors.append(ValidationError(
                category=ValidationErrorCategory.REFERENCE_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"Endpoint '{endpoint.method} {endpoint.path}' references "
                    f"non-existent table '{endpoint.target_table}'"
                ),
                location=f"{loc}.target_table",
                expected="A valid table name from db_schema",
                actual=endpoint.target_table,
                suggestion=f"Did you mean '{suggestion}'?" if suggestion else "Check table name",
            ))

    return errors


# ---------------------------------------------------------------------------
# UI → API reference checks
# ---------------------------------------------------------------------------

def _check_ui_to_api_refs(api: APISchema, ui: UISchema) -> list[ValidationError]:
    """Verify every UI component's bound_endpoint exists in the API schema."""
    errors: list[ValidationError] = []
    api_paths = {e.path.lower() for e in api.endpoints}

    for i, page in enumerate(ui.pages):
        for j, component in enumerate(page.components):
            _check_component_api_refs(
                component, f"ui_schema.pages[{i}].components[{j}]",
                api_paths, api, errors
            )

    return errors


def _check_component_api_refs(
    component, loc: str, api_paths: set, api: APISchema,
    errors: list[ValidationError],
) -> None:
    """Recursively check a component's API endpoint references."""
    if component.bound_endpoint:
        if component.bound_endpoint.lower() not in api_paths:
            suggestion = _fuzzy_find(
                component.bound_endpoint,
                [e.path for e in api.endpoints]
            )
            errors.append(ValidationError(
                category=ValidationErrorCategory.REFERENCE_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"UI component '{component.id}' references non-existent "
                    f"API endpoint '{component.bound_endpoint}'"
                ),
                location=f"{loc}.bound_endpoint",
                expected="A valid API endpoint path",
                actual=component.bound_endpoint,
                suggestion=f"Did you mean '{suggestion}'?" if suggestion else "Check endpoint path",
            ))

    for k, child in enumerate(component.children or []):
        _check_component_api_refs(
            child, f"{loc}.children[{k}]", api_paths, api, errors
        )


# ---------------------------------------------------------------------------
# DB Foreign Key integrity
# ---------------------------------------------------------------------------

def _check_db_fk_integrity(db: DBSchema) -> list[ValidationError]:
    """Verify all foreign keys reference existing tables and columns."""
    errors: list[ValidationError] = []
    table_names_lower = {t.name.lower() for t in db.tables}

    for i, table in enumerate(db.tables):
        for j, fk in enumerate(table.foreign_keys):
            loc = f"db_schema.tables[{i}].foreign_keys[{j}]"

            # Check referenced table exists
            if fk.references_table.lower() not in table_names_lower:
                suggestion = _fuzzy_find(fk.references_table, [t.name for t in db.tables])
                errors.append(ValidationError(
                    category=ValidationErrorCategory.RELATIONSHIP_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"FK in '{table.name}' references non-existent "
                        f"table '{fk.references_table}'"
                    ),
                    location=f"{loc}.references_table",
                    expected="A valid table name",
                    actual=fk.references_table,
                    suggestion=f"Did you mean '{suggestion}'?" if suggestion else "",
                ))
            else:
                # Check referenced column exists
                ref_table = db.get_table(fk.references_table)
                if ref_table:
                    ref_columns = {c.name.lower() for c in ref_table.columns}
                    if fk.references_column.lower() not in ref_columns:
                        errors.append(ValidationError(
                            category=ValidationErrorCategory.RELATIONSHIP_INTEGRITY,
                            severity=ValidationSeverity.ERROR,
                            message=(
                                f"FK in '{table.name}' references column "
                                f"'{fk.references_column}' which doesn't exist in "
                                f"table '{fk.references_table}'"
                            ),
                            location=f"{loc}.references_column",
                            expected=f"A valid column in '{fk.references_table}'",
                            actual=fk.references_column,
                        ))

    return errors


# ---------------------------------------------------------------------------
# API payload ↔ DB column alignment
# ---------------------------------------------------------------------------

def _check_payload_field_alignment(db: DBSchema, api: APISchema) -> list[ValidationError]:
    """Check that API request payload fields correspond to DB columns."""
    errors: list[ValidationError] = []

    for i, endpoint in enumerate(api.endpoints):
        if not endpoint.request_payload or not endpoint.target_table:
            continue

        table = db.get_table(endpoint.target_table)
        if not table:
            continue  # Already caught by api_to_db_refs check

        db_columns = {c.name.lower() for c in table.columns}
        # Exclude auto-generated columns from the check
        auto_cols = {"id", "created_at", "updated_at"}
        writable_columns = db_columns - auto_cols

        for j, field in enumerate(endpoint.request_payload.fields):
            loc = f"api_schema.endpoints[{i}].request_payload.fields[{j}]"

            if field.name.lower() not in db_columns:
                # Check for naming mismatch
                match = _fuzzy_find(field.name, [c.name for c in table.columns])

                if match:
                    errors.append(ValidationError(
                        category=ValidationErrorCategory.NAMING_MISMATCH,
                        severity=ValidationSeverity.ERROR,
                        message=(
                            f"API field '{field.name}' in endpoint "
                            f"'{endpoint.method} {endpoint.path}' doesn't match "
                            f"any column in table '{table.name}'"
                        ),
                        location=loc,
                        expected=match,
                        actual=field.name,
                        suggestion=f"Rename to '{match}' to match the DB schema",
                    ))
                else:
                    errors.append(ValidationError(
                        category=ValidationErrorCategory.REFERENCE_INTEGRITY,
                        severity=ValidationSeverity.WARNING,
                        message=(
                            f"API field '{field.name}' has no corresponding column "
                            f"in table '{table.name}'"
                        ),
                        location=loc,
                        actual=field.name,
                    ))

    return errors


# ---------------------------------------------------------------------------
# UI form fields ↔ API payload alignment
# ---------------------------------------------------------------------------

def _check_form_field_alignment(api: APISchema, ui: UISchema) -> list[ValidationError]:
    """Check that UI form field names match API request payload field names."""
    errors: list[ValidationError] = []

    # Build a lookup of endpoint path → request field names
    endpoint_fields: dict[str, set[str]] = {}
    for endpoint in api.endpoints:
        if endpoint.request_payload:
            endpoint_fields[endpoint.path.lower()] = {
                f.name.lower() for f in endpoint.request_payload.fields
            }

    for i, page in enumerate(ui.pages):
        for j, component in enumerate(page.components):
            _check_form_fields_recursive(
                component, f"ui_schema.pages[{i}].components[{j}]",
                endpoint_fields, errors
            )

    return errors


def _check_form_fields_recursive(
    component, loc: str, endpoint_fields: dict,
    errors: list[ValidationError],
) -> None:
    """Recursively check form field alignment."""
    if (
        component.form_fields
        and component.bound_endpoint
        and component.bound_endpoint.lower() in endpoint_fields
    ):
        api_fields = endpoint_fields[component.bound_endpoint.lower()]
        for k, form_field in enumerate(component.form_fields):
            if form_field.name.lower() not in api_fields:
                errors.append(ValidationError(
                    category=ValidationErrorCategory.NAMING_MISMATCH,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Form field '{form_field.name}' in component '{component.id}' "
                        f"doesn't match any API payload field for endpoint "
                        f"'{component.bound_endpoint}'"
                    ),
                    location=f"{loc}.form_fields[{k}]",
                    actual=form_field.name,
                ))

    for k, child in enumerate(component.children or []):
        _check_form_fields_recursive(
            child, f"{loc}.children[{k}]", endpoint_fields, errors
        )


# ---------------------------------------------------------------------------
# Fuzzy matching utility
# ---------------------------------------------------------------------------

def _fuzzy_find(needle: str, haystack: list[str], threshold: int = FUZZY_MATCH_THRESHOLD) -> str | None:
    """Find the best fuzzy match for a string in a list.

    Uses both full ratio and partial ratio to catch substring matches
    (e.g., 'user_email' vs 'email' where one name is prefixed).
    """
    if not haystack:
        return None

    best_match = None
    best_score = 0

    for candidate in haystack:
        # Use the higher of full ratio and partial ratio
        full_score = fuzz.ratio(needle.lower(), candidate.lower())
        partial_score = fuzz.partial_ratio(needle.lower(), candidate.lower())
        score = max(full_score, partial_score)

        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate

    return best_match

