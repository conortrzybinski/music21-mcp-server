# Music21 Analysis - Multi-Interface Music Server

[![CI/CD Pipeline](https://github.com/brightlikethelight/music21-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/brightlikethelight/music21-mcp-server/actions/workflows/ci.yml)
[![CI](https://github.com/brightlikethelight/music21-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/brightlikethelight/music21-mcp-server/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-84%25-brightgreen.svg)](https://github.com/brightlikethelight/music21-mcp-server/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-green)](https://modelcontextprotocol.io)

**Professional music analysis through MCP, HTTP, CLI, and Python interfaces.**
Built on music21 with a protocol-independent core. This fork's complete 18-tool
composer-collaboration surface is available through MCP and
`MusicAnalysisService`; the HTTP, CLI, and convenience Python adapters currently
expose a legacy subset.

## 🎯 Why Multiple Interfaces?

The music-analysis service is separated from its protocol adapters so callers
can choose the integration appropriate to their workflow:

- 📡 **MCP Server** - Complete 18-tool composer-collaboration surface
- 🌐 **HTTP API** - Web integration for the legacy analysis surface
- 💻 **CLI Tools** - Interactive and scripted legacy operations
- 🐍 **Python Library** - Direct access to `MusicAnalysisService`, plus legacy
  convenience adapters

## 🎵 Core Music Analysis Features

### Analysis and Composition Tools (18 MCP/Core Tools)
- **Import**: MuseScore (`.mscz`/`.mscx`), MusicXML, MIDI, ABC, Humdrum, MEI,
  and the music21 corpus
- **Export**: MusicXML, MIDI, ABC, LilyPond and rendered formats where their
  external dependencies are installed
- **Key Analysis**: Multiple algorithms (Krumhansl, Aarden, Bellman-Budge)
- **Harmony Analysis**: Roman numerals, chord progressions, cadence detection
- **Voice Leading**: Parallel motion detection, voice crossing analysis
- **Pattern Recognition**: Melodic, rhythmic, and harmonic patterns
- **Compact Score Slices**: Bounded note/chord/rest events with exact voice,
  offset, lyric, meter/key, tempo, and direction context
- **Lyric Audit**: Read-only syllabic-state, coverage, reconstruction, and
  cross-part consistency evidence with measure-specific locators

### Advanced Capabilities  
- **Harmonization**: Bach chorale and jazz style harmonization
- **Counterpoint**: Species counterpoint generation (1-5)
- **Style Imitation**: Learn and generate music in composer styles
- **Text Underlay**: Prosody-aware lyric fitting with bounded melismas
- **Choral Text Distribution**: Simultaneous, staggered, and imitative entries
- **Phrase-Aware Continuation**: Motive development toward requested cadences

## 🚀 Quick Start

### Installation

#### Install from PyPI (Recommended)

```bash
# Install the package
pip install music21-mcp-server

# Start the server
music21-mcp          # MCP server for Claude Desktop
music21-http         # REST API at localhost:8000
music21-cli          # Interactive CLI
music21-analysis mcp          # Unified launcher (positional arg)
```

#### Install from Source

```bash
# Clone repository
git clone https://github.com/brightlikethelight/music21-mcp-server.git
cd music21-mcp-server

# Install with UV (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Or with pip
pip install .

# Configure music21 corpus
python -m music21.configure
```

### Usage - Pick Your Interface

#### 🎯 Show All Available Interfaces
```bash
python -m music21_mcp.launcher
```

#### 📡 MCP Server (for Claude Desktop)
```bash
# Start MCP server
python -m music21_mcp.launcher mcp

# Configure Claude Desktop with:
# ~/.config/claude-desktop/config.json
{
  "mcpServers": {
    "music21-analysis": {
      "command": "python",
      "args": ["-m", "music21_mcp.server_minimal"],
      "env": {
        "PYTHONPATH": "/path/to/music21-mcp-server/src",
        "MUSESCORE_EXECUTABLE": "/path/to/MuseScore4",
        "MUSIC21_ALLOWED_IMPORT_ROOTS": "/path/to/composer/projects",
        "MUSIC21_TOOL_TIMEOUT": "120"
      }
    }
  }
}
```

On Windows, JSON paths require escaped backslashes, for example
`C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe`. Restart the MCP host
after changing its environment.

#### 🌐 HTTP API Server (for web apps)
```bash
# Start HTTP API server
python -m music21_mcp.launcher http
# Opens: http://localhost:8000
# API docs: http://localhost:8000/docs

# Example usage:
curl -X POST "http://localhost:8000/scores/import" \
  -H "Content-Type: application/json" \
  -d '{"score_id": "chorale", "source": "bach/bwv66.6", "source_type": "corpus"}'

curl -X POST "http://localhost:8000/analysis/key" \
  -H "Content-Type: application/json" \
  -d '{"score_id": "chorale"}'
```

#### 💻 CLI Tools (for automation)
```bash
# Show CLI status
python -m music21_mcp.launcher cli status

# Import and analyze a Bach chorale
python -m music21_mcp.launcher cli import chorale bach/bwv66.6 corpus
python -m music21_mcp.launcher cli key-analysis chorale
python -m music21_mcp.launcher cli harmony chorale roman

# List all tools
python -m music21_mcp.launcher cli tools
```

#### 🐍 Python Library (for programming)
```python
from music21_mcp import create_sync_analyzer

# Create analyzer
analyzer = create_sync_analyzer()

# Import and analyze
analyzer.import_score("chorale", "bach/bwv66.6", "corpus")
key_result = analyzer.analyze_key("chorale")
harmony_result = analyzer.analyze_harmony("chorale", "roman")

print(f"Key: {key_result}")
print(f"Harmony: {harmony_result}")

# Quick comprehensive analysis
analysis = analyzer.quick_analysis("chorale")
```

## 🧪 Testing & Development

### Run Tests
```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage threshold
python -m pytest tests/ --cov=src/music21_mcp --cov-fail-under=82
```

### Development Setup
```bash
# Install development dependencies
uv sync --dev

# Set up pre-commit hooks
pre-commit install

# Run linting
ruff check src/
ruff format src/

# Type checking
mypy src/
```

## 🏗️ Architecture

### Protocol-Independent Design
```
Core Value Layer:
├── services.py              # Music21 analysis service (protocol-independent)
└── tools/                   # 18 music analysis and composition tools

Protocol Adapter Layer:
├── adapters/mcp_adapter.py   # MCP protocol isolation
├── adapters/http_adapter.py  # HTTP/REST API
├── adapters/cli_adapter.py   # Command-line interface  
└── adapters/python_adapter.py # Direct Python access

Unified Entry Point:
└── launcher.py              # Single entry point for all interfaces
```

### Design Philosophy
- **Core Value First**: Music21 analysis isolated from protocol concerns
- **Protocol Apocalypse Survival**: Works even when MCP fails (30-40% of time)
- **Multiple Escape Hatches**: Always have a working interface
- **Reality-Based**: Built for today's MCP ecosystem, not enterprise dreams

## 📊 Interface Reliability

| Interface | Success Rate | Best For |
|-----------|--------------|----------|
| **MCP** | 40-50% | AI assistant integration |
| **HTTP** | 95%+ | Web applications |
| **CLI** | 99%+ | Automation & scripting |
| **Python** | 99%+ | Direct programming |

## 📚 Documentation

- **[docs/architecture.md](docs/architecture.md)** - System architecture overview
- **[docs/getting-started.md](docs/getting-started.md)** - Quick start guide
- **[examples/](examples/)** - Working code examples
- **API Docs**: http://localhost:8000/docs (when HTTP server running)

### Discord Webhook Integration
- **[.github/webhook-config.md](.github/webhook-config.md)** - Complete Discord webhook setup guide
- **[docs/webhook-integration.md](docs/webhook-integration.md)** - Advanced webhook configuration
- **[scripts/test-webhook.sh](scripts/test-webhook.sh)** - Test webhook connectivity
- **[scripts/setup-webhook.sh](scripts/setup-webhook.sh)** - Automated webhook setup

## 🔧 Configuration

### Environment Variables
```bash
# Server host and port (used by HTTP adapter and launcher)
export MUSIC21_MCP_HOST=127.0.0.1
export MUSIC21_MCP_PORT=8000

# Operation timeouts (seconds)
export MUSIC21_MCP_TIMEOUT=30          # General async operation timeout
export MUSIC21_TOOL_TIMEOUT=30         # Per-tool execution timeout
export MUSIC21_CHORD_ANALYSIS_TIMEOUT=60  # Chord analysis timeout
export MUSIC21_BATCH_TIMEOUT=30        # Batch processing timeout

# Optional MuseScore import configuration
export MUSESCORE_EXECUTABLE="/path/to/MuseScore4"
export MUSIC21_ALLOWED_IMPORT_ROOTS="/path/to/composer/projects"

# CORS origins for HTTP adapter (comma-separated)
export MUSIC21_CORS_ORIGINS="http://localhost:*"
```

### Music21 Setup
```bash
# Configure corpus path (one-time setup)
python -m music21.configure
```

### Non-destructive MuseScore import

`import_score` accepts `.mscz` and `.mscx` files when MuseScore is installed.
It invokes MuseScore directly (no live MuseScore plug-in or network bridge),
exports a MusicXML derivative inside a temporary directory, parses that
derivative with music21, and then removes it. The original MuseScore file is
never rewritten. Import responses report conversion warnings and any bounded
MusicXML repairs that were required. The importer also reads tempo text and
gradual-tempo metadata directly from the native MuseScore XML and returns it as
`import_context`. This preserves semantic markings such as `half = quarter`
when MuseScore's MusicXML export contains only private-use music glyphs or an
invalid empty metronome element.

Set `MUSESCORE_EXECUTABLE` when MuseScore is not on `PATH` or in a standard
installation location. Imports are restricted to the server's working
directory and temporary directory by default. To opt additional composer
project folders into file access, set `MUSIC21_ALLOWED_IMPORT_ROOTS` to a
platform path-separator-delimited allowlist (`;` on Windows, `:` on macOS and
Linux).

### Composer collaboration workflow

The fork's XML-first workflow is intentionally analytical and approval-based:

1. Import the composer's authoritative `.mscz` with
   `import_score(score_id="magnificat", source="/path/Magnificat.mscz",
   source_type="file")`.
2. Use `score_slice` on a focused passage. The default is eight measures; each
   call is capped at 32 measures and rejects oversized event payloads instead
   of silently dropping later voices. `detail="compact"` is the model-friendly
   default; request `detail="full"` only when exact additional event metadata is
   needed.
3. Run `lyric_audit` for structural underlay evidence, reconstructed text,
   coverage, and conservative cross-part observations. Raw lyric events and
   per-word locator details are opt-in so a normal audit remains compact.
4. Discuss recommendations with the composer and apply approved changes in
   MuseScore. These inspection tools are read-only and never rewrite the source
   score.

Typical focused calls use arguments such as:

```json
{
  "score_slice": {
    "score_id": "magnificat",
    "start_measure": 17,
    "end_measure": 24,
    "parts": ["Soprano", "Alto", "Tenor", "Bass"],
    "detail": "compact",
    "max_events": 400
  },
  "lyric_audit": {
    "score_id": "magnificat",
    "language": "latin",
    "verse": 1,
    "include_lyric_events": false,
    "include_word_details": false
  }
}
```

Part names are matched case-insensitively; integer selectors are one-based.
`score_slice` defaults to eight measures, allows at most 32 measures, defaults
to 400 events, and has a hard ceiling of 4,000 events.

MusicXML carries musical structure well, but it is not a complete engraving
round trip: MuseScore-only layout, autoplace, collision, and some playback data
can be absent. The native-context recovery above covers known tempo-semantics
losses; final visual engraving still belongs in MuseScore. No live plug-in or
unauthenticated network bridge is required for this workflow.

### Interpretation boundaries

`score_slice` exposes the written evidence a reasoning model needs for close
reading; it does not declare a single harmonic interpretation. The existing
key, chord, and harmony analyzers are heuristic and primarily tonal, so their
labels should be checked against focused slices in music that uses clusters,
extended tonality, or rapid local modulation. Likewise, the current
voice-leading analyzer is advisory for complex polyphony rather than proof of
onset-synchronized contrapuntal errors.

`lyric_audit` checks encoded lyric states, coverage, and cross-part consistency.
It does not by itself prove Latin spelling, syllabification, stress, diction, or
the composer's intended melismas. Those decisions remain collaborative. The
server also does not yet maintain a persistent composer-style profile; supply
reference scores and a piece-specific style brief when stylistic continuity is
important.

## 🛠️ Available Analysis Tools

1. **import_score** - Import from the corpus and supported local files
2. **list_scores** - List all imported scores  
3. **score_info** - Detailed score information
4. **export_score** - Export to MIDI, MusicXML, etc.
5. **delete_score** - Remove scores from storage
6. **key_analysis** - Key signature analysis
7. **chord_analysis** - Chord progression analysis
8. **harmony_analysis** - Roman numeral/functional harmony
9. **voice_leading_analysis** - Voice leading quality analysis
10. **pattern_recognition** - Melodic/rhythmic patterns
11. **harmonize_melody** - Automatic harmonization
12. **generate_counterpoint** - Counterpoint generation
13. **imitate_style** - Style imitation and generation
14. **text_underlay** - Prosody-aware lyric fitting for a melody
15. **choral_text_distribution** - Multi-voice lyric distribution and entries
16. **phrase_aware_continuation** - Motivic, form- and cadence-aware continuation
17. **score_slice** - Compact, bounded score evidence for close musical reading
18. **lyric_audit** - Read-only lyric structure, coverage, and consistency audit

## 🚀 Quick Examples

### Analyze a Bach Chorale
```bash
# CLI approach
python -m music21_mcp.launcher cli import chorale bach/bwv66.6 corpus
python -m music21_mcp.launcher cli key-analysis chorale

# Python approach  
analyzer = create_sync_analyzer()
analyzer.import_score("chorale", "bach/bwv66.6", "corpus")
print(analyzer.analyze_key("chorale"))
```

### Start Services
```bash
# For Claude Desktop
python -m music21_mcp.launcher mcp

# For web development
python -m music21_mcp.launcher http

# For command-line work
python -m music21_mcp.launcher cli status
```

## 🔄 Migration from v1.0

The previous enterprise version has been **simplified for reliability**:

- ✅ **Kept**: All music21 analysis functionality
- ✅ **Added**: HTTP API, CLI, Python library interfaces
- ❌ **Removed**: Docker, K8s, complex auth, monitoring (too unstable for MCP ecosystem)
- 🔄 **Changed**: Focus on core value delivery through multiple interfaces

## 🔔 Discord Webhook Integration

Get real-time notifications for CI/CD pipeline status, pull requests, and releases:

- 📖 [Webhook Setup Guide](.github/webhook-config.md)
- 🛠️ [Quick Setup Script](scripts/setup-webhook.sh)
- 🧪 [Test Your Webhook](scripts/test-webhook.sh)
- 📚 [Advanced Configuration](docs/webhook-integration.md)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on:

- Development setup and requirements
- Code style guidelines (Ruff, MyPy)
- Testing requirements (maintain >82% coverage)
- Pull request process
- Branch protection rules

Quick start:
1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Run tests: `pytest tests/ --cov=src/music21_mcp --cov-fail-under=82`
4. Commit changes: `git commit -m 'feat: Add amazing feature'`
5. Push branch: `git push origin feature/amazing-feature`
6. Submit pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built on the excellent [music21](https://web.mit.edu/music21/) library
- Uses [FastMCP](https://github.com/jlowin/fastmcp) for MCP protocol support  
- Inspired by the need for reliable music analysis tools

---

**Choose the interface that works for you. All provide the same powerful music21 analysis capabilities!** 🎵
