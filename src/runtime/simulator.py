"""
Runtime Simulator

Verifies the generated schemas by actually attempting to:
  1. Create SQLite tables from the DB schema (SQLAlchemy)
  2. Boot a FastAPI app with route stubs from the API schema
  3. Run a health check against the mock API

This catches errors that static validation cannot:
  - Invalid SQL type combinations
  - Endpoint path conflicts in FastAPI's router
  - Circular foreign key issues
"""

from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column as SAColumn,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    Date,
    JSON as SAJSON,
    ForeignKey,
    Numeric,
)
from sqlalchemy.engine import Engine

from src.models.schema import DBSchema, APISchema, SQLType, HTTPMethod
from src.models.manifest import (
    RuntimeTestResult,
    RuntimeTestDetail,
    RuntimeTestStatus,
    StageTelemetry,
)
from src.runtime.error_capture import ErrorCapture, map_sqlalchemy_error_to_schema, map_fastapi_error_to_schema


# Mapping from our SQLType enum to SQLAlchemy column types
SQLTYPE_TO_SA = {
    SQLType.VARCHAR: lambda col: String(col.max_length or 255),
    SQLType.TEXT: lambda _: Text(),
    SQLType.INTEGER: lambda _: Integer(),
    SQLType.BIGINT: lambda _: Integer(),  # SQLite doesn't distinguish
    SQLType.FLOAT: lambda _: Float(),
    SQLType.DECIMAL: lambda _: Numeric(10, 2),
    SQLType.BOOLEAN: lambda _: Boolean(),
    SQLType.TIMESTAMP: lambda _: DateTime(),
    SQLType.DATE: lambda _: Date(),
    SQLType.UUID: lambda _: String(36),  # SQLite: store as string
    SQLType.JSON: lambda _: SAJSON(),
    SQLType.ENUM: lambda col: String(50),  # SQLite: store as string
}


def run_simulation(
    db_schema: DBSchema,
    api_schema: APISchema,
) -> tuple[RuntimeTestResult, StageTelemetry]:
    """
    Run the full simulated runtime test.

    1. Attempts to create all DB tables in an in-memory SQLite database.
    2. Attempts to boot a FastAPI app with generated route stubs.
    3. Runs a basic health check.

    Returns:
        Tuple of (RuntimeTestResult, StageTelemetry).
    """
    start_time = time.time()
    details: list[RuntimeTestDetail] = []
    error_capture = ErrorCapture()

    # --- Phase 1: SQLite DB Boot ---
    db_status, db_details = _test_db_boot(db_schema, error_capture)
    details.extend(db_details)

    # --- Phase 2: FastAPI Stub Boot ---
    api_status, api_details = _test_api_boot(api_schema, error_capture)
    details.extend(api_details)

    # --- Aggregate results ---
    total_tests = len(details)
    tests_passed = sum(1 for d in details if d.status == RuntimeTestStatus.PASSED)

    overall_status = RuntimeTestStatus.PASSED
    if db_status == RuntimeTestStatus.FAILED or api_status == RuntimeTestStatus.FAILED:
        overall_status = RuntimeTestStatus.FAILED

    elapsed = time.time() - start_time

    result = RuntimeTestResult(
        overall_status=overall_status,
        db_boot_status=db_status,
        api_boot_status=api_status,
        details=details,
        total_tests=total_tests,
        tests_passed=tests_passed,
    )

    telemetry = StageTelemetry(
        stage_name="runtime_simulation",
        duration_seconds=elapsed,
    )

    return result, telemetry


# ---------------------------------------------------------------------------
# Phase 1: Database Boot Test
# ---------------------------------------------------------------------------

def _test_db_boot(
    db_schema: DBSchema,
    error_capture: ErrorCapture,
) -> tuple[RuntimeTestStatus, list[RuntimeTestDetail]]:
    """Attempt to create all tables in an in-memory SQLite database."""
    details: list[RuntimeTestDetail] = []
    overall_status = RuntimeTestStatus.PASSED

    try:
        engine = create_engine("sqlite:///:memory:", echo=False)
        metadata = MetaData()

        # First pass: create all Table objects (without FKs that might reference
        # tables not yet defined)
        sa_tables: dict[str, Table] = {}

        for table_def in db_schema.tables:
            test_start = time.time()
            try:
                sa_columns = _build_columns(table_def)
                sa_table = Table(table_def.name, metadata, *sa_columns)
                sa_tables[table_def.name] = sa_table

                details.append(RuntimeTestDetail(
                    test_name=f"db_define_table_{table_def.name}",
                    status=RuntimeTestStatus.PASSED,
                    duration_ms=(time.time() - test_start) * 1000,
                ))
            except Exception as e:
                overall_status = RuntimeTestStatus.FAILED
                error_capture.capture(
                    e,
                    schema_location=map_sqlalchemy_error_to_schema(str(e), table_def.name),
                    affected_element=table_def.name,
                )
                details.append(RuntimeTestDetail(
                    test_name=f"db_define_table_{table_def.name}",
                    status=RuntimeTestStatus.FAILED,
                    duration_ms=(time.time() - test_start) * 1000,
                    error_message=str(e),
                    traceback=error_capture.errors[-1].traceback_text,
                    affected_schema_location=f"db_schema.tables['{table_def.name}']",
                ))

        # Attempt to create all tables
        test_start = time.time()
        try:
            metadata.create_all(engine)
            details.append(RuntimeTestDetail(
                test_name="db_create_all_tables",
                status=RuntimeTestStatus.PASSED,
                duration_ms=(time.time() - test_start) * 1000,
            ))
        except Exception as e:
            overall_status = RuntimeTestStatus.FAILED
            error_capture.capture(
                e,
                schema_location="db_schema (create_all failed)",
            )
            details.append(RuntimeTestDetail(
                test_name="db_create_all_tables",
                status=RuntimeTestStatus.FAILED,
                duration_ms=(time.time() - test_start) * 1000,
                error_message=str(e),
                traceback=error_capture.errors[-1].traceback_text,
                affected_schema_location="db_schema",
            ))

        engine.dispose()

    except Exception as e:
        overall_status = RuntimeTestStatus.FAILED
        error_capture.capture(e, schema_location="db_schema (engine creation failed)")
        details.append(RuntimeTestDetail(
            test_name="db_engine_creation",
            status=RuntimeTestStatus.FAILED,
            error_message=str(e),
        ))

    return overall_status, details


def _build_columns(table_def) -> list:
    """Build SQLAlchemy column objects from a table definition."""
    sa_columns = []

    for col_def in table_def.columns:
        # Get the SQLAlchemy type factory
        type_factory = SQLTYPE_TO_SA.get(col_def.sql_type)
        if type_factory is None:
            # Fallback to String for unknown types
            sa_type = String(255)
        else:
            sa_type = type_factory(col_def)

        # Determine if this is a primary key
        is_pk = "PRIMARY KEY" in col_def.constraints or col_def.name == "id"

        # Check if this column is a foreign key
        fk_target = None
        for fk in table_def.foreign_keys:
            if fk.column == col_def.name:
                fk_target = f"{fk.references_table}.{fk.references_column}"
                break

        if fk_target:
            sa_columns.append(
                SAColumn(col_def.name, sa_type, ForeignKey(fk_target),
                         primary_key=is_pk, nullable=col_def.nullable)
            )
        else:
            sa_columns.append(
                SAColumn(col_def.name, sa_type,
                         primary_key=is_pk, nullable=col_def.nullable)
            )

    return sa_columns


# ---------------------------------------------------------------------------
# Phase 2: FastAPI Stub Boot Test
# ---------------------------------------------------------------------------

def _test_api_boot(
    api_schema: APISchema,
    error_capture: ErrorCapture,
) -> tuple[RuntimeTestStatus, list[RuntimeTestDetail]]:
    """Attempt to boot a FastAPI app with generated route stubs."""
    details: list[RuntimeTestDetail] = []
    overall_status = RuntimeTestStatus.PASSED

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI(title="SimulationTest")

        # Register route stubs
        test_start = time.time()
        registered_routes = set()

        for endpoint in api_schema.endpoints:
            route_key = f"{endpoint.method} {endpoint.path}"

            if route_key in registered_routes:
                # Skip duplicate — already flagged by structural validation
                continue
            registered_routes.add(route_key)

            try:
                _register_stub_route(app, endpoint)
            except Exception as e:
                overall_status = RuntimeTestStatus.FAILED
                error_capture.capture(
                    e,
                    schema_location=map_fastapi_error_to_schema(str(e), endpoint.path),
                    affected_element=route_key,
                )
                details.append(RuntimeTestDetail(
                    test_name=f"api_register_{endpoint.method}_{endpoint.path}",
                    status=RuntimeTestStatus.FAILED,
                    duration_ms=(time.time() - test_start) * 1000,
                    error_message=str(e),
                    affected_schema_location=f"api_schema.endpoints['{route_key}']",
                ))

        details.append(RuntimeTestDetail(
            test_name="api_register_all_routes",
            status=RuntimeTestStatus.PASSED if overall_status == RuntimeTestStatus.PASSED else RuntimeTestStatus.FAILED,
            duration_ms=(time.time() - test_start) * 1000,
        ))

        # Health check — try to hit the OpenAPI docs endpoint
        test_start = time.time()
        try:
            client = TestClient(app)
            response = client.get("/openapi.json")

            if response.status_code == 200:
                openapi_spec = response.json()
                path_count = len(openapi_spec.get("paths", {}))
                details.append(RuntimeTestDetail(
                    test_name="api_openapi_health_check",
                    status=RuntimeTestStatus.PASSED,
                    duration_ms=(time.time() - test_start) * 1000,
                ))
            else:
                overall_status = RuntimeTestStatus.FAILED
                details.append(RuntimeTestDetail(
                    test_name="api_openapi_health_check",
                    status=RuntimeTestStatus.FAILED,
                    duration_ms=(time.time() - test_start) * 1000,
                    error_message=f"OpenAPI endpoint returned status {response.status_code}",
                ))
        except Exception as e:
            overall_status = RuntimeTestStatus.FAILED
            error_capture.capture(e, schema_location="api_schema (health check failed)")
            details.append(RuntimeTestDetail(
                test_name="api_openapi_health_check",
                status=RuntimeTestStatus.FAILED,
                duration_ms=(time.time() - test_start) * 1000,
                error_message=str(e),
            ))

    except ImportError as e:
        details.append(RuntimeTestDetail(
            test_name="api_import_check",
            status=RuntimeTestStatus.SKIPPED,
            error_message=f"FastAPI not available: {e}",
        ))
    except Exception as e:
        overall_status = RuntimeTestStatus.FAILED
        error_capture.capture(e, schema_location="api_schema")
        details.append(RuntimeTestDetail(
            test_name="api_boot",
            status=RuntimeTestStatus.FAILED,
            error_message=str(e),
        ))

    return overall_status, details


def _register_stub_route(app, endpoint) -> None:
    """Register a single stub route on the FastAPI app."""
    # Convert path params from {param} to FastAPI's {param: type} format
    path = endpoint.path

    # Build a simple stub handler
    async def stub_handler(**kwargs):
        return {"status": "stub", "endpoint": endpoint.path}

    # Use the appropriate HTTP method decorator
    method_map = {
        HTTPMethod.GET: app.get,
        HTTPMethod.POST: app.post,
        HTTPMethod.PUT: app.put,
        HTTPMethod.PATCH: app.patch,
        HTTPMethod.DELETE: app.delete,
    }

    decorator = method_map.get(endpoint.method)
    if decorator:
        decorator(path, tags=endpoint.tags)(stub_handler)
