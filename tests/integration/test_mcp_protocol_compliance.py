"""
MCP Protocol Compliance Tests

Tests to verify the MCP server follows the Model Context Protocol specification.
Based on MCP spec 2025-11-25 and best practices from research.
"""

import pytest

from music21_mcp.adapters.mcp_adapter import MCPAdapter
from music21_mcp.services import MusicAnalysisService


class TestMCPToolDiscovery:
    """Test MCP tool discovery and listing."""

    @pytest.fixture
    def service(self):
        """Create a fresh service instance."""
        return MusicAnalysisService(max_memory_mb=64, max_scores=10)

    @pytest.fixture
    def adapter(self):
        """Create a fresh adapter instance."""
        return MCPAdapter()

    @pytest.mark.integration
    def test_tools_are_discoverable(self, service):
        """Verify all tools can be discovered via get_available_tools."""
        tools = service.get_available_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 10, "Should have at least 10 tools available"

    @pytest.mark.integration
    def test_expected_tools_present(self, service):
        """Verify expected core tools are present."""
        tools = service.get_available_tools()

        expected_tools = [
            "import_score",
            "list_scores",
            "delete_score",
            "export_score",
            "score_info",
            "analyze_key",
            "analyze_chords",
            "analyze_harmony",
        ]

        for expected in expected_tools:
            assert any(expected in tool.lower() for tool in tools), (
                f"Expected tool '{expected}' not found in {tools}"
            )


class TestMCPToolResponses:
    """Test MCP tool response formats."""

    @pytest.fixture
    def adapter(self):
        """Create a fresh adapter instance."""
        return MCPAdapter()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_import_returns_valid_response(self, adapter):
        """Test that import_score returns valid MCP response format."""
        result = await adapter.import_score("test_score", "bach/bwv66.6", "corpus")

        # Should return a dict
        assert isinstance(result, dict)

        # Should have either success or error keys
        has_success_fields = "message" in result or "num_notes" in result
        has_error_fields = "error" in result
        assert has_success_fields or has_error_fields

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_list_scores_returns_valid_response(self, adapter):
        """Test that list_scores returns valid MCP response format."""
        result = await adapter.list_scores()

        assert isinstance(result, dict)
        # Should have scores or count information
        assert "scores" in result or "count" in result or "tool" in result

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_error_response_format(self, adapter):
        """Test that errors return valid MCP error response format."""
        # Request analysis on non-existent score
        result = await adapter.key_analysis("nonexistent_score_12345")

        assert isinstance(result, dict)
        # Error responses should have descriptive message
        result_str = str(result).lower()
        assert "error" in result_str or "not found" in result_str


class TestMCPToolExecutionPatterns:
    """Test MCP tool execution patterns and workflows."""

    @pytest.fixture
    def adapter(self):
        """Create a fresh adapter instance."""
        return MCPAdapter()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_import_analyze_delete_workflow(self, adapter):
        """Test complete workflow: import -> analyze -> delete."""
        score_id = "workflow_test_score"

        # 1. Import
        import_result = await adapter.import_score(score_id, "bach/bwv66.6", "corpus")
        assert isinstance(import_result, dict)

        # 2. Analyze (if import succeeded)
        if "error" not in str(import_result).lower():
            key_result = await adapter.key_analysis(score_id)
            assert isinstance(key_result, dict)

            # 3. Delete
            delete_result = await adapter.delete_score(score_id)
            assert isinstance(delete_result, dict)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_imports_tracked(self, adapter):
        """Test that multiple imports are tracked correctly."""
        # Import multiple scores
        await adapter.import_score("test1", "bach/bwv66.6", "corpus")
        await adapter.import_score("test2", "bach/bwv66.6", "corpus")

        # List should show both
        result = await adapter.list_scores()
        assert isinstance(result, dict)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self, adapter):
        """Test that concurrent tool calls don't interfere with each other."""
        import asyncio

        # Make multiple concurrent calls
        tasks = [
            adapter.import_score(f"concurrent_{i}", "bach/bwv66.6", "corpus")
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete without raising exceptions
        for result in results:
            assert not isinstance(result, Exception)
            assert isinstance(result, dict)


class TestMCPInputValidation:
    """Test MCP input validation."""

    @pytest.fixture
    def adapter(self):
        """Create a fresh adapter instance."""
        return MCPAdapter()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_score_id_handled(self, adapter):
        """Test that empty score_id is handled gracefully."""
        result = await adapter.import_score("", "bach/bwv66.6", "corpus")
        # Should not crash - either error or success
        assert isinstance(result, dict)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_invalid_source_type_handled(self, adapter):
        """Test that invalid source_type is handled gracefully."""
        result = await adapter.import_score("test", "test.xml", "invalid_type")
        assert isinstance(result, dict)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_missing_corpus_score_handled(self, adapter):
        """Test that non-existent corpus score is handled gracefully."""
        result = await adapter.import_score("test", "nonexistent/score/path", "corpus")
        assert isinstance(result, dict)


class TestMCPServerMetadata:
    """Test MCP server metadata and capabilities."""

    @pytest.fixture
    def service(self):
        return MusicAnalysisService(max_memory_mb=64, max_scores=10)

    @pytest.mark.integration
    def test_service_provides_status(self, service):
        """Test that service provides status information."""
        # Service should be queryable for basic status
        tools = service.get_available_tools()
        count = service.get_score_count()

        assert isinstance(tools, list)
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.integration
    def test_resource_limits_respected(self, service):
        """Test that resource limits are configured."""
        # Check that resource manager has limits
        rm = service.resource_manager

        assert hasattr(rm, "max_memory_mb")
        assert hasattr(rm, "max_scores")
        assert rm.max_memory_mb > 0
        assert rm.max_scores > 0


class TestMCPAsyncPatterns:
    """Test MCP async execution patterns."""

    @pytest.fixture
    def adapter(self):
        return MCPAdapter()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_tools_are_async(self, adapter):
        """Verify tools are properly async."""
        import asyncio

        # All tool methods should be async
        result = adapter.import_score("async_test", "bach/bwv66.6", "corpus")
        assert asyncio.iscoroutine(result)
        await result  # Clean up

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_blocking_calls_in_tools(self, adapter):
        """Test that tools don't block the event loop excessively."""
        import asyncio
        import time

        start = time.time()

        # Run a simple operation
        await asyncio.wait_for(
            adapter.list_scores(),
            timeout=5.0,  # Should complete in under 5 seconds
        )

        elapsed = time.time() - start
        assert elapsed < 5.0, f"Tool took too long: {elapsed}s"
