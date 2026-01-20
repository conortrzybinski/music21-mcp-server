#!/usr/bin/env python3
"""
Custom Exception Hierarchy for Music21 MCP Server

This module provides specific exceptions for different error types,
replacing over-broad 'except Exception' patterns throughout the codebase.

Also provides HTTP status code mapping and structured error response utilities.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ErrorResponse:
    """Structured error response for HTTP and MCP interfaces."""

    error: str
    error_code: str
    message: str
    details: dict[str, Any] | None = None
    retry_after: float | None = None
    http_status: int = 500

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "error": self.error,
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result


class Music21MCPError(Exception):
    """Base exception for all Music21 MCP errors"""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ScoreNotFoundError(Music21MCPError):
    """Raised when a requested score is not found in storage"""

    def __init__(self, score_id: str):
        super().__init__(f"Score not found: {score_id}", {"score_id": score_id})
        self.score_id = score_id


class InvalidScoreFormatError(Music21MCPError):
    """Raised when a score format is invalid or unsupported"""

    def __init__(self, format_name: str, supported_formats: list[str] | None = None):
        supported = supported_formats or []
        super().__init__(
            f"Invalid format: {format_name}. Supported: {supported}",
            {"format": format_name, "supported": supported},
        )
        self.format_name = format_name
        self.supported_formats = supported


class ScoreImportError(Music21MCPError):
    """Raised when score import fails"""

    def __init__(self, source: str, source_type: str, reason: str):
        super().__init__(
            f"Failed to import from {source_type}: {source}. Reason: {reason}",
            {"source": source, "source_type": source_type, "reason": reason},
        )
        self.source = source
        self.source_type = source_type
        self.reason = reason


class ExportError(Music21MCPError):
    """Raised when score export fails"""

    def __init__(self, score_id: str, format_name: str, reason: str):
        super().__init__(
            f"Failed to export {score_id} as {format_name}: {reason}",
            {"score_id": score_id, "format": format_name, "reason": reason},
        )
        self.score_id = score_id
        self.format_name = format_name
        self.reason = reason


class AnalysisError(Music21MCPError):
    """Raised when music analysis fails"""

    def __init__(self, analysis_type: str, score_id: str, reason: str):
        super().__init__(
            f"{analysis_type} analysis failed for {score_id}: {reason}",
            {"analysis_type": analysis_type, "score_id": score_id, "reason": reason},
        )
        self.analysis_type = analysis_type
        self.score_id = score_id
        self.reason = reason


class GenerationError(Music21MCPError):
    """Raised when music generation fails (harmonization, counterpoint, etc.)"""

    def __init__(self, generation_type: str, reason: str):
        super().__init__(
            f"{generation_type} generation failed: {reason}",
            {"generation_type": generation_type, "reason": reason},
        )
        self.generation_type = generation_type
        self.reason = reason


class ResourceExhaustedError(Music21MCPError):
    """Raised when system resources are exhausted"""

    def __init__(self, resource_type: str, current: float, limit: float):
        super().__init__(
            f"{resource_type} exhausted: {current:.1f}/{limit:.1f}",
            {"resource_type": resource_type, "current": current, "limit": limit},
        )
        self.resource_type = resource_type
        self.current = current
        self.limit = limit


class ConfigurationError(Music21MCPError):
    """Raised when configuration is invalid"""

    def __init__(self, setting: str, value: str, reason: str):
        super().__init__(
            f"Invalid configuration for {setting}={value}: {reason}",
            {"setting": setting, "value": value, "reason": reason},
        )
        self.setting = setting
        self.value = value
        self.reason = reason


class OperationTimeoutError(Music21MCPError):
    """Raised when an operation times out"""

    def __init__(self, operation: str, timeout_seconds: float):
        super().__init__(
            f"Operation '{operation}' timed out after {timeout_seconds}s",
            {"operation": operation, "timeout_seconds": timeout_seconds},
        )
        self.operation = operation
        self.timeout_seconds = timeout_seconds


class ValidationError(Music21MCPError):
    """Raised when input validation fails"""

    def __init__(self, field: str, value: str, constraint: str):
        super().__init__(
            f"Validation failed for {field}={value}: {constraint}",
            {"field": field, "value": value, "constraint": constraint},
        )
        self.field = field
        self.value = value
        self.constraint = constraint


# Exception categories for catch blocks
RETRYABLE_EXCEPTIONS = (
    OperationTimeoutError,
    ResourceExhaustedError,
    ConnectionError,
    TimeoutError,
)

NON_RETRYABLE_EXCEPTIONS = (
    ScoreNotFoundError,
    InvalidScoreFormatError,
    ValidationError,
    ConfigurationError,
)

ANALYSIS_EXCEPTIONS = (
    AnalysisError,
    ScoreNotFoundError,
)

IO_EXCEPTIONS = (
    ScoreImportError,
    ExportError,
    OSError,
    FileNotFoundError,
    PermissionError,
)

# HTTP Status Code Mapping
EXCEPTION_TO_HTTP_STATUS: dict[type[Exception], int] = {
    ScoreNotFoundError: 404,
    InvalidScoreFormatError: 400,
    ValidationError: 400,
    ConfigurationError: 400,
    ScoreImportError: 422,  # Unprocessable Entity
    ExportError: 422,
    AnalysisError: 500,
    GenerationError: 500,
    ResourceExhaustedError: 503,  # Service Unavailable
    OperationTimeoutError: 504,  # Gateway Timeout
}

# Error codes for structured responses
EXCEPTION_TO_ERROR_CODE: dict[type[Exception], str] = {
    ScoreNotFoundError: "SCORE_NOT_FOUND",
    InvalidScoreFormatError: "INVALID_FORMAT",
    ValidationError: "VALIDATION_ERROR",
    ConfigurationError: "CONFIGURATION_ERROR",
    ScoreImportError: "IMPORT_ERROR",
    ExportError: "EXPORT_ERROR",
    AnalysisError: "ANALYSIS_ERROR",
    GenerationError: "GENERATION_ERROR",
    ResourceExhaustedError: "RESOURCE_EXHAUSTED",
    OperationTimeoutError: "OPERATION_TIMEOUT",
}


def exception_to_error_response(exc: Exception) -> ErrorResponse:
    """Convert an exception to a structured error response."""
    exc_type = type(exc)

    # Get HTTP status code
    http_status = EXCEPTION_TO_HTTP_STATUS.get(exc_type, 500)

    # Get error code
    error_code = EXCEPTION_TO_ERROR_CODE.get(exc_type, "INTERNAL_ERROR")

    # Get details if available
    details = getattr(exc, "details", None)

    # Get retry_after for retryable errors
    retry_after = None
    if exc_type in RETRYABLE_EXCEPTIONS:
        retry_after = 5.0  # Default 5 second retry

    return ErrorResponse(
        error=exc_type.__name__,
        error_code=error_code,
        message=str(exc),
        details=details,
        retry_after=retry_after,
        http_status=http_status,
    )
