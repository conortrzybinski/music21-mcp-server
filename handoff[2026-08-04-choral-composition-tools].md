# Handoff: music21-mcp-server — New Choral Composition Tools

**Repo:** `c:\Users\cjtrz\Documents\GitHub\music21-mcp-server` (fork of `brightlikethelight/music21-mcp-server`, MIT license)

**Goal:** Add three new MCP tools for choral composition assistance: text underlay, multi-voice text distribution, and phrase-aware continuation/suggestion.

## Architecture (follow this pattern exactly)

Every tool follows a 4-layer registration chain:

1. **Tool module** — `src/music21_mcp/tools/<name>_tool.py` — extends `BaseTool`, implements `execute(**kwargs)`
2. **Core service** — `src/music21_mcp/services.py` — `MusicAnalysisService` instantiates the tool in `_init_tools()` and exposes a delegate method
3. **MCP adapter** — `src/music21_mcp/adapters/mcp_adapter.py` — `MCPAdapter` wraps the service method with `@mcp_tool("tool_name")`
4. **MCP server** — `src/music21_mcp/server_minimal.py` — registers the adapter method as a `@mcp.tool()` FastMCP function

Plus:
- `src/music21_mcp/tools/__init__.py` — export the new tool class
- `src/music21_mcp/tools/base_tool.py` — base class with `create_success_response()`, `create_error_response()`, `validate_inputs()`, `get_score()`, `check_score_exists()`, `error_handling()`, `report_progress()`

## Tool 1: Text Underlay (`text_underlay_tool.py`)

**Purpose:** Take a preset text (lyrics) and fit it tastefully into an existing melody, handling syllable-to-note assignment with prosodic constraints.

**Inputs:**
- `score_id: str` — the melody score already imported
- `text: str` — the lyrics text (multi-word, multi-syllable)
- `language: str = "english"` — for language-specific hyphenation rules
- `melisma_limit: int = 3` — max notes per syllable before forcing a new syllable
- `prefer_stressed_on_strong: bool = True` — place stressed syllables on strong beats

**Behavior:**
- Tokenize text into syllables (use a simple rule-based approach or `pyphen` for hyphenation)
- Extract the melody notes from the score
- Assign syllables to notes respecting:
  - One syllable per note minimum, with melisma (multiple notes per syllable) allowed up to `melisma_limit`
  - Stressed syllables prefer metrically strong positions (beat 1 and 3 in 4/4, beat 1 in 3/4)
  - Word-final syllables prefer longer note values or phrase endings
  - If text is longer than available notes, truncate with a warning
  - If text is shorter, pad with melisma on final syllable
- Write lyrics back to the score using music21's `note.Note.lyric` or `note.Lyric` objects
- Return the modified score with syllable-to-note mapping in the response

**Output:** `{ status, message, syllable_map: [{syllable, note_index, pitch, beat}], warnings: [...] }`

## Tool 2: Multi-Voice Text Distribution (`choral_text_distribution_tool.py`)

**Purpose:** Distribute text across multiple voices in a choral score (SATB), handling staggered entries, voice-specific ranges, and text overlap.

**Inputs:**
- `score_id: str` — the multi-part score (must have 2-8 parts)
- `text: str` — the lyrics text
- `voice_assignments: dict[str, str] | None` — optional mapping of part names to text portions, e.g. `{"Soprano": "Gloria in excelsis Deo", "Alto": "Et in terra pax"}`
- `entry_scheme: str = "staggered"` — "staggered" (voices enter sequentially), "simultaneous" (all together), "imitative" (each voice enters with same text offset)
- `stagger_offset_measures: int = 2` — measures between voice entries in staggered mode

**Behavior:**
- If `voice_assignments` is provided, use those text-to-voice mappings directly
- If not, auto-distribute: split text into sections proportional to the number of voices, assign each section to a voice
- For staggered entries: voice 1 starts at measure 1, voice 2 at measure 1+offset, etc.
- For imitative: each voice gets the same text, entering at staggered offsets
- Apply text underlay (Tool 1 logic) per voice
- Ensure voice ranges are respected (S: C4-A5, A: F3-D5, T: C3-G4, B: E2-C4 — configurable)
- Return the modified score

**Output:** `{ status, message, voice_assignments: {part_name: text_section}, entry_points: {part_name: measure} }`

## Tool 3: Phrase-Aware Continuation (`continuation_tool.py`)

**Purpose:** Suggest next sections of music in light of the broader context of an in-progress score, with awareness of form, harmonic trajectory, and motivic material.

**Inputs:**
- `score_id: str` — the in-progress score
- `continuation_length: int = 8` — measures to generate
- `form_context: str | None` — e.g. "AABA", "verse-chorus", "sonata", "through-composed"
- `preserve_motifs: bool = True` — reuse and develop existing motivic material
- `cadence_target: str | None` — target cadence type ("PAC", "IAC", "HC", "DC", "PC")
- `style: str = "classical"` — style context for generation

**Behavior:**
- Analyze the existing score: extract key, tempo, time signature, motivic fragments, harmonic rhythm, phrase structure
- If `form_context` is provided, determine where we are in the form and what typically follows
- Generate a continuation that:
  - Maintains the established key (or modulates appropriately if at a form boundary)
  - Develops existing motivic material (sequence, inversion, augmentation/diminution) if `preserve_motifs`
  - Builds toward the target cadence if specified
  - Respects phrase lengths consistent with the existing material
- Use music21's analysis tools (key detection, chord analysis) already available in the codebase
- Return the continuation as a new score section appended to the original

**Output:** `{ status, message, continuation_score_id, measures_generated, harmonic_analysis: {key, progression, cadence}, motivic_development: [{original_motif, transformation, location}] }`

## Files to Create

```
src/music21_mcp/tools/text_underlay_tool.py
src/music21_mcp/tools/choral_text_distribution_tool.py
src/music21_mcp/tools/continuation_tool.py
```

## Files to Modify

```
src/music21_mcp/tools/__init__.py          — add imports and __all__ entries
src/music21_mcp/services.py                — instantiate tools, add delegate methods
src/music21_mcp/adapters/mcp_adapter.py     — add @mcp_tool wrapper methods
src/music21_mcp/server_minimal.py           — register @mcp.tool() functions
```

## Conventions

- Follow the existing `BaseTool` pattern: `validate_inputs()`, `execute()`, `create_success_response()`, `create_error_response()`
- Use `self.report_progress()` for long operations
- Use `self.error_handling()` context manager for consistent error wrapping
- All music21 operations go through the tool, not the adapter
- Type hints on all public methods
- Add tests in `tests/` following existing patterns (pytest, asyncio)
- Run `uv run ruff check src/` and `uv run pytest` before committing

## Dev Environment

```powershell
cd c:\Users\cjtrz\Documents\GitHub\music21-mcp-server
uv sync --dev          # install all deps
uv run pytest          # verify existing tests pass first
```
