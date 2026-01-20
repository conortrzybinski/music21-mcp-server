"""
Security tests for input validation.

Tests for:
- SQL injection resistance
- Path traversal prevention
- XSS prevention
- Command injection prevention
- Resource exhaustion prevention
"""

import pytest

from music21_mcp.adapters.mcp_adapter import MCPAdapter
from music21_mcp.services import MusicAnalysisService


class TestInputValidation:
    """Test input validation for security vulnerabilities."""

    @pytest.fixture
    def service(self):
        """Create a fresh service instance."""
        return MusicAnalysisService(max_memory_mb=64, max_scores=10)

    @pytest.fixture
    def adapter(self):
        """Create a fresh adapter instance."""
        return MCPAdapter()

    # SQL Injection Tests
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_score_id_sql_injection(self, adapter):
        """Test that SQL injection attempts in score_id are handled safely."""
        dangerous_inputs = [
            "'; DROP TABLE scores;--",
            "1; DELETE FROM users WHERE '1'='1",
            "' OR '1'='1",
            "1' OR '1'='1' --",
            "admin'--",
            "1' UNION SELECT * FROM users--",
        ]
        for bad_input in dangerous_inputs:
            result = await adapter.import_score(bad_input, "bach/bwv66.6", "corpus")
            # Should either succeed safely or return an error, not execute SQL
            assert isinstance(result, dict)
            assert "status" in result or "error" in result or "message" in result

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_source_sql_injection(self, adapter):
        """Test that SQL injection in source parameter is handled safely."""
        dangerous_sources = [
            "'; DROP TABLE scores;--",
            "bach/bwv66.6'; DELETE FROM scores WHERE '1'='1",
        ]
        for bad_source in dangerous_sources:
            result = await adapter.import_score("test_score", bad_source, "corpus")
            # Should handle gracefully
            assert isinstance(result, dict)
            assert "status" in result or "error" in result or "message" in result

    # Path Traversal Tests
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_path_traversal_score_id(self, adapter):
        """Test that path traversal attempts in score_id are blocked."""
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\SAM",
            "....//....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%252f..%252f..%252fetc/passwd",
            "..%c0%af..%c0%af..%c0%afetc/passwd",
        ]
        for bad_path in dangerous_paths:
            result = await adapter.import_score(bad_path, "bach/bwv66.6", "corpus")
            # Should not expose system files
            if "result" in result:
                assert "/etc/passwd" not in str(result)
                assert "windows" not in str(result).lower()

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_path_traversal_source(self, adapter):
        """Test that path traversal in source parameter is handled safely."""
        dangerous_sources = [
            "../../../etc/passwd",
            "/etc/shadow",
            "file:///etc/passwd",
            "file://localhost/etc/passwd",
        ]
        for bad_source in dangerous_sources:
            result = await adapter.import_score("test", bad_source, "file")
            # Should fail safely, not expose system files
            if "error" not in str(result).lower():
                assert "/etc/" not in str(result)

    # XSS Prevention Tests
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_xss_in_score_id(self, adapter):
        """Test that XSS attempts in score_id are handled safely.

        Note: This is a JSON API, not an HTML renderer. XSS protection is
        primarily a frontend concern. The backend should handle these inputs
        without crashing and return valid responses. HTML escaping would be
        done by the frontend when rendering.
        """
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>",
            "'><script>alert('xss')</script>",
            '"onmouseover="alert(\'xss\')"',
        ]
        for payload in xss_payloads:
            result = await adapter.import_score(payload, "bach/bwv66.6", "corpus")
            # Should handle gracefully - valid JSON response
            assert isinstance(result, dict)
            assert "status" in result or "error" in result or "message" in result

    # Command Injection Tests
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_command_injection_score_id(self, adapter):
        """Test that command injection attempts are blocked."""
        dangerous_inputs = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "& whoami",
            "`whoami`",
            "$(whoami)",
            "\n/bin/sh -c 'cat /etc/passwd'",
            "test\ncat /etc/passwd",
        ]
        for bad_input in dangerous_inputs:
            result = await adapter.import_score(bad_input, "bach/bwv66.6", "corpus")
            # Should handle safely
            assert isinstance(result, dict)
            assert "status" in result or "error" in result or "message" in result
            # Result should not contain command output
            result_str = str(result)
            assert "root:" not in result_str  # /etc/passwd content

    # Null Byte Injection Tests
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_null_byte_injection(self, adapter):
        """Test that null byte injection is handled safely."""
        dangerous_inputs = [
            "valid_score\x00.evil",
            "score\x00../../etc/passwd",
            "test%00.txt",
        ]
        for bad_input in dangerous_inputs:
            result = await adapter.import_score(bad_input, "bach/bwv66.6", "corpus")
            # Should handle gracefully
            assert isinstance(result, dict)
            assert "status" in result or "error" in result or "message" in result

    # Resource Exhaustion Tests
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_oversized_score_id(self, adapter):
        """Test handling of extremely long score IDs."""
        # 10KB string
        huge_id = "x" * 10000
        result = await adapter.import_score(huge_id, "bach/bwv66.6", "corpus")
        # Should handle without crashing - success or error response is acceptable
        assert isinstance(result, dict)
        # Verify it didn't cause a server crash
        assert "message" in result or "error" in result

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_unicode_edge_cases(self, adapter):
        """Test handling of unusual Unicode inputs."""
        unicode_inputs = [
            "\u0000",  # Null
            "\uffff",  # Max BMP
            "\U0001f4a9",  # Emoji
            "test\u202eevil",  # Right-to-left override
            "test\u200btest",  # Zero-width space
            "\ud800",  # Lone surrogate (invalid)
        ]
        for bad_input in unicode_inputs:
            try:
                result = await adapter.import_score(bad_input, "bach/bwv66.6", "corpus")
                # Should handle gracefully
                assert isinstance(result, dict)
                assert "status" in result or "error" in result or "message" in result
            except (UnicodeError, ValueError):
                # Acceptable to reject invalid Unicode
                pass


class TestExportSecurity:
    """Test security of export functionality."""

    @pytest.fixture
    def adapter(self):
        return MCPAdapter()

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_export_format_injection(self, adapter):
        """Test that format parameter doesn't allow injection."""
        # First import a valid score
        await adapter.import_score("test_export", "bach/bwv66.6", "corpus")

        dangerous_formats = [
            "../../../etc/passwd",
            "musicxml; rm -rf /",
            "musicxml\ncat /etc/passwd",
        ]
        for bad_format in dangerous_formats:
            result = await adapter.export_score("test_export", bad_format)
            # Should fail safely
            assert isinstance(result, dict)
            assert "status" in result or "error" in result or "message" in result


class TestAnalysisSecurity:
    """Test security of analysis operations."""

    @pytest.fixture
    def adapter(self):
        return MCPAdapter()

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_analysis_with_malicious_score_id(self, adapter):
        """Test that analysis functions handle malicious score IDs safely."""
        dangerous_ids = [
            "../../../etc/passwd",
            "'; DROP TABLE scores;--",
            "<script>alert('xss')</script>",
        ]

        for bad_id in dangerous_ids:
            # These should all fail safely (score not found)
            key_result = await adapter.key_analysis(bad_id)
            assert (
                "error" in str(key_result).lower()
                or "not found" in str(key_result).lower()
            )

            chord_result = await adapter.chord_analysis(bad_id)
            assert (
                "error" in str(chord_result).lower()
                or "not found" in str(chord_result).lower()
            )


class TestRateLimitingPrerequisites:
    """Test that rate limiting prerequisites are in place."""

    @pytest.mark.security
    def test_rate_limiter_exists(self):
        """Verify rate limiter module exists and is importable."""
        from music21_mcp.rate_limiter import RateLimitConfig, RateLimiter

        config = RateLimitConfig(requests_per_minute=10)
        limiter = RateLimiter(config)
        assert limiter is not None

    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_excessive_requests(self):
        """Test that rate limiter actually limits requests."""
        from music21_mcp.rate_limiter import RateLimitConfig, RateLimiter

        # Very low limit to trigger blocking
        config = RateLimitConfig(requests_per_minute=2, burst_size=1)
        limiter = RateLimiter(config)

        # First request should succeed
        allowed, _ = await limiter.check_rate_limit("test_client")
        assert allowed

        # Rapid requests should eventually be blocked
        blocked = False
        for _ in range(20):
            allowed, _ = await limiter.check_rate_limit("test_client")
            if not allowed:
                blocked = True
                break

        assert blocked, "Rate limiter should block excessive requests"
