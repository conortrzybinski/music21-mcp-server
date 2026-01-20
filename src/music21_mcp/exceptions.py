#!/usr/bin/env python3
"""
Custom Exception Hierarchy for Music21 MCP Server

This module provides specific exceptions for different error types,
replacing over-broad 'except Exception' patterns throughout the codebase.
"""


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
