#!/usr/bin/env python3
"""
MCP Protocol Adapter
Isolates MCP protocol concerns from core music analysis service

This adapter handles:
- MCP protocol specifics (which change frequently)
- Tool registration and routing
- Response format translation
- Error handling and logging

The core music analysis service remains completely isolated from MCP.
When MCP breaks (every 3-6 months), only this adapter needs updating.
"""

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from ..exceptions import (
    AnalysisError,
    ExportError,
    GenerationError,
    Music21MCPError,
    ScoreImportError,
    ScoreNotFoundError,
    ValidationError,
)
from ..services import MusicAnalysisService

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def mcp_tool(tool_name: str, error_prefix: str | None = None):
    """
    Decorator for MCP tool methods that handles response formatting and errors.

    This decorator eliminates boilerplate by:
    - Catching and formatting errors consistently
    - Wrapping successful results in MCP response format
    - Logging errors with appropriate context

    Args:
        tool_name: Name of the MCP tool (used in response formatting)
        error_prefix: Custom error message prefix (defaults to tool_name)
    """
    prefix = error_prefix or tool_name.replace("_", " ").title()

    def decorator(
        func: Callable[P, Awaitable[dict[str, Any]]],
    ) -> Callable[P, Awaitable[dict[str, Any]]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
            try:
                result = await func(*args, **kwargs)
                return _format_mcp_response(result, tool_name)

            # Handle specific music21 MCP exceptions
            except ScoreNotFoundError as e:
                logger.warning(f"MCP tool {tool_name}: Score not found - {e.score_id}")
                return _format_mcp_error(str(e), tool_name)

            except (ScoreImportError, ExportError) as e:
                logger.error(f"MCP tool {tool_name}: I/O error - {e}")
                return _format_mcp_error(str(e), tool_name)

            except (AnalysisError, GenerationError) as e:
                logger.error(f"MCP tool {tool_name}: Analysis/generation error - {e}")
                return _format_mcp_error(str(e), tool_name)

            except ValidationError as e:
                logger.warning(f"MCP tool {tool_name}: Validation error - {e}")
                return _format_mcp_error(str(e), tool_name)

            except Music21MCPError as e:
                logger.error(f"MCP tool {tool_name}: {e}")
                return _format_mcp_error(str(e), tool_name)

            # Handle standard Python exceptions with more specificity
            except KeyError as e:
                logger.error(f"MCP tool {tool_name}: Missing key - {e}")
                return _format_mcp_error(
                    f"{prefix} failed: missing required data", tool_name
                )

            except ValueError as e:
                logger.error(f"MCP tool {tool_name}: Invalid value - {e}")
                return _format_mcp_error(f"{prefix} failed: {e}", tool_name)

            except TypeError as e:
                logger.error(f"MCP tool {tool_name}: Type error - {e}")
                return _format_mcp_error(
                    f"{prefix} failed: invalid input type", tool_name
                )

            except (OSError, FileNotFoundError, PermissionError) as e:
                logger.error(f"MCP tool {tool_name}: File system error - {e}")
                return _format_mcp_error(
                    f"{prefix} failed: file error - {e}", tool_name
                )

            except (ConnectionError, TimeoutError) as e:
                logger.error(f"MCP tool {tool_name}: Network/timeout error - {e}")
                return _format_mcp_error(f"{prefix} failed: {e}", tool_name)

            except Exception as e:
                # Last resort catch-all for truly unexpected errors
                logger.exception(f"MCP tool {tool_name}: Unexpected error - {e}")
                return _format_mcp_error(f"{prefix} failed: {e}", tool_name)

        return wrapper

    return decorator


def _format_mcp_response(core_result: dict[str, Any], tool_name: str) -> dict[str, Any]:
    """Format core service response for MCP protocol"""
    if isinstance(core_result, dict) and "status" in core_result:
        return core_result
    return {
        "status": "success",
        "tool": tool_name,
        "data": core_result,
        "message": f"{tool_name} completed successfully",
    }


def _format_mcp_error(error_message: str, tool_name: str) -> dict[str, Any]:
    """Format error response for MCP protocol"""
    return {
        "status": "error",
        "tool": tool_name,
        "error": error_message,
        "message": f"{tool_name} failed",
    }


class MCPAdapter:
    """
    Adapter between MCP protocol and core music analysis service

    Handles protocol volatility by isolating all MCP-specific code.
    When FastMCP introduces breaking changes, only this class needs updates.
    """

    def __init__(self):
        """Initialize MCP adapter with core service"""
        self.core_service = MusicAnalysisService()
        self.mcp_version = "fastmcp-2.14.0"  # Track which version we support

        logger.info(f"MCP adapter initialized for {self.mcp_version}")

    # === MCP Tool Interface ===
    # These methods match MCP tool signatures but delegate to core service
    # The @mcp_tool decorator handles all response formatting and error handling

    @mcp_tool("import_score", "Import")
    async def import_score(
        self, score_id: str, source: str, source_type: str = "corpus"
    ) -> dict[str, Any]:
        """MCP tool: Import a score from various sources"""
        return await self.core_service.import_score(score_id, source, source_type)

    @mcp_tool("list_scores", "List")
    async def list_scores(self) -> dict[str, Any]:
        """MCP tool: List all available scores"""
        return await self.core_service.list_scores()

    @mcp_tool("score_info", "Score info")
    async def score_info(self, score_id: str) -> dict[str, Any]:
        """MCP tool: Get detailed information about a score"""
        return await self.core_service.get_score_info(score_id)

    @mcp_tool("export_score", "Export")
    async def export_score(
        self, score_id: str, format: str = "musicxml"
    ) -> dict[str, Any]:
        """MCP tool: Export a score to various formats"""
        return await self.core_service.export_score(score_id, format)

    @mcp_tool("delete_score", "Delete")
    async def delete_score(self, score_id: str) -> dict[str, Any]:
        """MCP tool: Delete a score from storage"""
        return await self.core_service.delete_score(score_id)

    @mcp_tool("key_analysis", "Key analysis")
    async def key_analysis(self, score_id: str) -> dict[str, Any]:
        """MCP tool: Analyze the key signature of a score"""
        return await self.core_service.analyze_key(score_id)

    @mcp_tool("chord_analysis", "Chord analysis")
    async def chord_analysis(self, score_id: str) -> dict[str, Any]:
        """MCP tool: Analyze chord progressions in a score"""
        return await self.core_service.analyze_chords(score_id)

    @mcp_tool("harmony_analysis", "Harmony analysis")
    async def harmony_analysis(
        self, score_id: str, analysis_type: str = "roman"
    ) -> dict[str, Any]:
        """MCP tool: Perform harmony analysis"""
        return await self.core_service.analyze_harmony(score_id, analysis_type)

    @mcp_tool("voice_leading_analysis", "Voice leading analysis")
    async def voice_leading_analysis(self, score_id: str) -> dict[str, Any]:
        """MCP tool: Analyze voice leading quality"""
        return await self.core_service.analyze_voice_leading(score_id)

    @mcp_tool("pattern_recognition", "Pattern recognition")
    async def pattern_recognition(
        self, score_id: str, pattern_type: str = "melodic"
    ) -> dict[str, Any]:
        """MCP tool: Recognize musical patterns"""
        return await self.core_service.recognize_patterns(score_id, pattern_type)

    @mcp_tool("score_slice", "Score slice")
    async def score_slice(
        self,
        score_id: str,
        start_measure: int = 1,
        end_measure: int | None = None,
        parts: str | list[str | int] | None = None,
        include_rests: bool = True,
        include_lyrics: bool = True,
        include_annotations: bool = True,
        max_events: int = 400,
        detail: str = "compact",
    ) -> dict[str, Any]:
        """MCP tool: Inspect a bounded polyphonic score region in detail."""
        return await self.core_service.score_slice(
            score_id,
            start_measure,
            end_measure,
            parts,
            include_rests,
            include_lyrics,
            include_annotations,
            max_events,
            detail,
        )

    @mcp_tool("lyric_audit", "Lyric audit")
    async def lyric_audit(
        self,
        score_id: str,
        parts: str | list[str | int] | None = None,
        language: str = "latin",
        verse: int | str | None = None,
        include_lyric_events: bool = False,
        include_word_details: bool = False,
    ) -> dict[str, Any]:
        """MCP tool: Audit lyric engraving without mutating the score."""
        return await self.core_service.lyric_audit(
            score_id,
            parts,
            language,
            verse,
            include_lyric_events,
            include_word_details,
        )

    @mcp_tool("harmonize_melody", "Harmonization")
    async def harmonize_melody(
        self, score_id: str, style: str = "classical", voice_parts: int = 4
    ) -> dict[str, Any]:
        """MCP tool: Generate harmonization for a melody"""
        return await self.core_service.harmonize_melody(score_id, style)

    @mcp_tool("generate_counterpoint", "Counterpoint generation")
    async def generate_counterpoint(
        self, score_id: str, species: int = 1, voice_position: str = "above"
    ) -> dict[str, Any]:
        """MCP tool: Generate counterpoint melody"""
        # Convert species number to string for the tool
        species_map = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
        species_str = species_map.get(species, "first")

        # Call the tool directly since service method signature mismatch
        return await self.core_service.counterpoint_tool.execute(
            score_id=score_id, species=species_str, voice_position=voice_position
        )

    @mcp_tool("imitate_style", "Style imitation")
    async def imitate_style(
        self,
        score_id: str | None = None,
        composer: str | None = None,
        generation_length: int = 16,
        complexity: str = "medium",
    ) -> dict[str, Any]:
        """MCP tool: Generate music imitating a specific style"""
        if score_id:
            # Use score as style source
            return await self.core_service.imitate_style(score_id, composer or "custom")
        if composer:
            # Use predefined composer style
            return await self.core_service.style_tool.execute(
                composer=composer,
                generation_length=generation_length,
                complexity=complexity,
            )
        raise ValidationError(
            "score_id or composer",
            "None",
            "Must provide either score_id or composer",
        )

    @mcp_tool("text_underlay", "Text underlay")
    async def text_underlay(
        self,
        score_id: str,
        text: str,
        language: str = "english",
        melisma_limit: int = 3,
        prefer_stressed_on_strong: bool = True,
    ) -> dict[str, Any]:
        """MCP tool: Fit lyric text to an existing melody."""
        return await self.core_service.text_underlay(
            score_id,
            text,
            language,
            melisma_limit,
            prefer_stressed_on_strong,
        )

    @mcp_tool("choral_text_distribution", "Choral text distribution")
    async def choral_text_distribution(
        self,
        score_id: str,
        text: str,
        voice_assignments: dict[str, str] | None = None,
        entry_scheme: str = "staggered",
        stagger_offset_measures: int = 2,
    ) -> dict[str, Any]:
        """MCP tool: Distribute lyric text across choral voices."""
        return await self.core_service.choral_text_distribution(
            score_id,
            text,
            voice_assignments,
            entry_scheme,
            stagger_offset_measures,
        )

    @mcp_tool("phrase_aware_continuation", "Phrase-aware continuation")
    async def phrase_aware_continuation(
        self,
        score_id: str,
        continuation_length: int = 8,
        form_context: str | None = None,
        preserve_motifs: bool = True,
        cadence_target: str | None = None,
        style: str = "classical",
    ) -> dict[str, Any]:
        """MCP tool: Generate a phrase-aware continuation of a score."""
        return await self.core_service.phrase_aware_continuation(
            score_id,
            continuation_length,
            form_context,
            preserve_motifs,
            cadence_target,
            style,
        )

    # === Protocol Evolution Support ===

    def get_supported_tools(self) -> list[str]:
        """Get list of all supported MCP tools"""
        return [
            "import_score",
            "list_scores",
            "score_info",
            "export_score",
            "delete_score",
            "key_analysis",
            "chord_analysis",
            "harmony_analysis",
            "voice_leading_analysis",
            "pattern_recognition",
            "score_slice",
            "lyric_audit",
            "harmonize_melody",
            "generate_counterpoint",
            "imitate_style",
            "text_underlay",
            "choral_text_distribution",
            "phrase_aware_continuation",
        ]

    def check_protocol_compatibility(self) -> dict[str, Any]:
        """Check if current FastMCP version is compatible"""
        try:
            import fastmcp

            current_version = getattr(fastmcp, "__version__", "unknown")

            return {
                "supported_version": self.mcp_version,
                "current_version": current_version,
                "compatible": current_version.startswith("2."),
                "core_service_healthy": self.core_service.get_score_count() >= 0,
            }
        except ImportError:
            return {
                "supported_version": self.mcp_version,
                "current_version": "not_installed",
                "compatible": False,
                "error": "FastMCP not available",
            }
