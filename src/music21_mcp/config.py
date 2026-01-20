#!/usr/bin/env python3
"""
Centralized Configuration for Music21 MCP Server

This module provides a single source of truth for all configuration values,
replacing hardcoded magic numbers throughout the codebase.

Configuration can be overridden via environment variables with the MUSIC21_ prefix.
Example: MUSIC21_MAX_MEMORY_MB=1024 will set max_memory_mb to 1024.
"""

import logging
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Music21MCPConfig(BaseSettings):
    """
    Configuration settings for Music21 MCP Server.

    All settings can be overridden via environment variables using the MUSIC21_ prefix.
    For example, MUSIC21_MAX_MEMORY_MB=1024 will override max_memory_mb.
    """

    # Memory Management
    max_memory_mb: int = Field(
        default=512,
        ge=1,
        description="Maximum memory usage in MB for score storage",
    )
    gc_threshold_mb: int = Field(
        default=100,
        ge=1,
        description="Memory threshold in MB to trigger garbage collection",
    )

    # Score Storage
    max_scores: int = Field(
        default=100,
        ge=1,
        description="Maximum number of scores to store in memory",
    )
    score_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="Time-to-live for scores in seconds (default 1 hour)",
    )
    cleanup_interval_seconds: int = Field(
        default=300,
        ge=10,
        description="Interval between automatic cleanup runs in seconds",
    )

    # Health Checks
    memory_threshold_percent: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description="Memory usage percentage threshold for health warnings",
    )
    cpu_threshold_percent: float = Field(
        default=90.0,
        ge=0.0,
        le=100.0,
        description="CPU usage percentage threshold for health warnings",
    )
    response_time_threshold_ms: float = Field(
        default=5000.0,
        ge=0.0,
        description="Response time threshold in milliseconds for health warnings",
    )

    # Retry Logic and Circuit Breaker
    circuit_breaker_threshold: int = Field(
        default=5,
        ge=1,
        description="Number of failures before circuit breaker opens",
    )
    recovery_timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        description="Time in seconds before circuit breaker attempts recovery",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retry attempts for failed operations",
    )
    retry_base_delay_seconds: float = Field(
        default=1.0,
        ge=0.0,
        description="Base delay in seconds between retry attempts",
    )

    # Async Optimization
    batch_timeout_seconds: float = Field(
        default=0.05,
        ge=0.001,
        description="Batch collection window in seconds",
    )
    batch_size: int = Field(
        default=20,
        ge=1,
        description="Maximum number of items per batch",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="TTL for analysis caches in seconds",
    )
    thread_pool_workers: int = Field(
        default=4,
        ge=1,
        description="Number of workers in the thread pool",
    )
    max_concurrent_operations: int = Field(
        default=10,
        ge=1,
        description="Maximum concurrent async operations",
    )

    # HTTP Server
    max_file_size_mb: int = Field(
        default=100,
        ge=1,
        description="Maximum file upload size in MB",
    )
    http_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="HTTP server port",
    )
    http_host: str = Field(
        default="127.0.0.1",
        description="HTTP server host",
    )

    # Rate Limiting
    rate_limit_requests: int = Field(
        default=100,
        ge=1,
        description="Maximum requests per rate limit window",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        description="Rate limit window in seconds",
    )

    # Memory Pressure Monitoring
    memory_monitoring_interval_seconds: float = Field(
        default=5.0,
        ge=1.0,
        description="Interval between memory pressure checks in seconds",
    )
    aggressive_gc_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Memory utilization ratio to trigger aggressive GC",
    )
    emergency_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Memory utilization ratio for emergency cleanup",
    )

    # Tool Timeouts
    default_tool_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        description="Default timeout for tool operations in seconds",
    )
    long_operation_timeout_seconds: float = Field(
        default=120.0,
        ge=10.0,
        description="Timeout for long-running operations in seconds",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Default logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    model_config = {
        "env_prefix": "MUSIC21_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for logging/debugging"""
        return self.model_dump()


@lru_cache
def get_config() -> Music21MCPConfig:
    """
    Get the global configuration instance.

    Uses caching to ensure only one config instance exists.
    The config is loaded once and reused throughout the application.

    Returns:
        Music21MCPConfig: The configuration instance
    """
    config = Music21MCPConfig()
    logger.info(
        f"Loaded configuration: max_memory={config.max_memory_mb}MB, "
        f"max_scores={config.max_scores}, cache_ttl={config.cache_ttl_seconds}s"
    )
    return config


def reload_config() -> Music21MCPConfig:
    """
    Reload configuration from environment.

    Clears the cached config and loads fresh values.
    Useful for testing or when environment variables change.

    Returns:
        Music21MCPConfig: The newly loaded configuration instance
    """
    get_config.cache_clear()
    return get_config()


# Convenience access to common config values
def get_memory_config() -> dict[str, Any]:
    """Get memory-related configuration values"""
    config = get_config()
    return {
        "max_memory_mb": config.max_memory_mb,
        "gc_threshold_mb": config.gc_threshold_mb,
        "aggressive_gc_threshold": config.aggressive_gc_threshold,
        "emergency_threshold": config.emergency_threshold,
    }


def get_storage_config() -> dict[str, Any]:
    """Get score storage configuration values"""
    config = get_config()
    return {
        "max_scores": config.max_scores,
        "score_ttl_seconds": config.score_ttl_seconds,
        "cleanup_interval_seconds": config.cleanup_interval_seconds,
    }


def get_async_config() -> dict[str, Any]:
    """Get async optimization configuration values"""
    config = get_config()
    return {
        "batch_timeout_seconds": config.batch_timeout_seconds,
        "batch_size": config.batch_size,
        "cache_ttl_seconds": config.cache_ttl_seconds,
        "thread_pool_workers": config.thread_pool_workers,
        "max_concurrent_operations": config.max_concurrent_operations,
    }


def get_health_config() -> dict[str, Any]:
    """Get health check configuration values"""
    config = get_config()
    return {
        "memory_threshold_percent": config.memory_threshold_percent,
        "cpu_threshold_percent": config.cpu_threshold_percent,
        "response_time_threshold_ms": config.response_time_threshold_ms,
    }
