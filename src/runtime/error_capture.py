"""
Error Capture Utility

Captures and structures Python tracebacks into a format that the
repair engine can consume, mapping errors to specific schema locations.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field


@dataclass
class CapturedError:
    """A structured representation of a runtime error."""
    error_type: str
    message: str
    traceback_text: str
    schema_location: str = ""
    affected_element: str = ""

    def to_repair_context(self) -> str:
        """Format this error for consumption by the repair engine."""
        lines = [
            f"Runtime Error: {self.error_type}: {self.message}",
        ]
        if self.schema_location:
            lines.append(f"Schema Location: {self.schema_location}")
        if self.affected_element:
            lines.append(f"Affected Element: {self.affected_element}")
        lines.append(f"Traceback:\n{self.traceback_text}")
        return "\n".join(lines)


@dataclass
class ErrorCapture:
    """Collects and categorizes runtime errors during simulation."""
    errors: list[CapturedError] = field(default_factory=list)

    def capture(
        self,
        exception: Exception,
        schema_location: str = "",
        affected_element: str = "",
    ) -> CapturedError:
        """Capture an exception with schema context."""
        error = CapturedError(
            error_type=type(exception).__name__,
            message=str(exception),
            traceback_text=traceback.format_exc(),
            schema_location=schema_location,
            affected_element=affected_element,
        )
        self.errors.append(error)
        return error

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def get_repair_context(self) -> str:
        """Get all errors formatted for the repair engine."""
        return "\n\n---\n\n".join(
            e.to_repair_context() for e in self.errors
        )


def map_sqlalchemy_error_to_schema(error_msg: str, table_name: str = "") -> str:
    """Map a SQLAlchemy error to a schema location string."""
    error_lower = error_msg.lower()

    if "no such table" in error_lower:
        return f"db_schema.tables (missing table)"
    if "duplicate column" in error_lower:
        return f"db_schema.tables['{table_name}'].columns (duplicate)"
    if "foreign key" in error_lower:
        return f"db_schema.tables['{table_name}'].foreign_keys"
    if "constraint" in error_lower:
        return f"db_schema.tables['{table_name}'].columns (constraint error)"

    return f"db_schema.tables['{table_name}']" if table_name else "db_schema"


def map_fastapi_error_to_schema(error_msg: str, endpoint_path: str = "") -> str:
    """Map a FastAPI error to a schema location string."""
    error_lower = error_msg.lower()

    if "path" in error_lower and "conflict" in error_lower:
        return f"api_schema.endpoints (path conflict at '{endpoint_path}')"
    if "method" in error_lower:
        return f"api_schema.endpoints['{endpoint_path}'].method"

    return f"api_schema.endpoints['{endpoint_path}']" if endpoint_path else "api_schema"
