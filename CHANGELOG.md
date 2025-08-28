# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub branch protection rules for main branch
- Discord webhook integration for CI/CD notifications
- Comprehensive webhook documentation and setup scripts
- Test coverage increased from 75.70% to 79.74%
- Advanced CI/CD monitoring capabilities
- Webhook test scripts for validation

### Fixed
- Fixed 54 test failures in unit tests
- Resolved import errors across test modules
- Fixed linting issues (single quotes to double quotes)
- Fixed variable naming convention violations
- Corrected import sorting and formatting issues
- Fixed MemoryManager constructor parameters
- Fixed ParallelProcessor.process_batch() parameters

### Changed
- Updated test modules to use get_logger() instead of direct logger import
- Improved test assertions for tool attributes
- Enhanced CI/CD pipeline stability
- Refactored observability module imports

### Security
- Implemented webhook secret management
- Added branch protection to prevent force pushes
- Required status checks before merging
- Enforced administrator restrictions

## [0.9.0] - 2025-08-25

### Added
- Multi-interface architecture (MCP, HTTP API, CLI, Python Library)
- 13 comprehensive music analysis tools
- FastMCP integration for Model Context Protocol support
- HTTP API with FastAPI backend
- Command-line interface for automation
- Python library for direct programming access

### Features
- Import/Export support for MusicXML, MIDI, ABC, Lilypond
- Key analysis with multiple algorithms (Krumhansl, Aarden, Bellman-Budge)
- Harmony analysis with Roman numerals and chord progression detection
- Voice leading analysis with parallel motion detection
- Pattern recognition for melodic, rhythmic, and harmonic patterns
- Bach chorale and jazz style harmonization
- Species counterpoint generation (1-5)
- Style imitation and generation
- Score manipulation (transposition, time stretching, orchestration)

### Infrastructure
- GitHub Actions CI/CD pipeline
- Multi-version Python testing (3.10, 3.11, 3.12)
- Security scanning with bandit and pip-audit
- Performance benchmarks
- Release readiness checks
- Automated PyPI publication workflow

## [0.8.0] - 2025-08-24

### Initial Release
- Core music21 integration
- Basic MCP server implementation
- Initial test suite with 75% coverage
- Documentation framework
- Basic CI/CD setup

[Unreleased]: https://github.com/brightlikethelight/music21-mcp-server/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/brightlikethelight/music21-mcp-server/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/brightlikethelight/music21-mcp-server/releases/tag/v0.8.0