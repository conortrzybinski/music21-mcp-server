"""Focused tests for MuseScore conversion and safe MusicXML repair."""

import os
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from music21 import chord, note, stream

import music21_mcp.tools.import_tool as import_module
from music21_mcp.tools.import_tool import ImportScoreTool

VALID_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Voice</part-name></score-part>
  </part-list>
  <part id="P1"><measure number="1" /></part>
</score-partwise>
"""

MUSICXML_WITH_EMPTY_BEAT_UNIT = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Voice</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <direction>
        <direction-type><words>gently</words></direction-type>
        <direction-type>
          <metronome parentheses="yes">
            <beat-unit></beat-unit>
            <per-minute>84</per-minute>
          </metronome>
        </direction-type>
        <sound tempo="84" />
      </direction>
    </measure>
  </part>
</score-partwise>
"""

MUSESCORE_NATIVE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<museScore version="4.7">
  <Score>
    <Part><Staff><eid>definition-only</eid><bracket>1</bracket></Staff></Part>
    <Staff id="1">
      <VBox />
      <Measure>
        <voice>
          <Tempo><tempo>1.5</tempo><text>Andante</text></Tempo>
        </voice>
      </Measure>
      <Measure>
        <voice>
          <Tempo>
            <tempo>2</tempo>
            <text><sym>metNoteHalfUp</sym><font face="Edwin"/> = <sym>metNoteQuarterUp</sym></text>
          </Tempo>
          <Spanner type="GradualTempoChange">
            <GradualTempoChange>
              <tempoChangeType>allargando</tempoChangeType>
              <tempoChangeFactor>0.83</tempoChangeFactor>
              <beginText>poco allarg.</beginText>
              <continueText>(allarg.)</continueText>
            </GradualTempoChange>
            <next><location><measures>1</measures><fractions>1/4</fractions></location></next>
          </Spanner>
        </voice>
      </Measure>
    </Staff>
  </Score>
</museScore>
"""


def _parsed_score() -> stream.Score:
    score = stream.Score()
    part = stream.Part()
    part.append(note.Note("C4"))
    score.append(part)
    return score


@pytest.mark.asyncio
async def test_mscz_import_uses_explicit_musescore_and_temporary_export(
    monkeypatch, tmp_path
):
    source = tmp_path / "working score.mscz"
    original_bytes = b"not-a-real-mscz-but-never-modified"
    source.write_bytes(original_bytes)
    executable = tmp_path / "MuseScore4.exe"
    executable.write_bytes(b"mock executable")
    monkeypatch.setenv("MUSESCORE_EXECUTABLE", str(executable))

    subprocess_calls = []
    parsed_paths = []

    def fake_run(command, **kwargs):
        subprocess_calls.append((command, kwargs))
        Path(command[2]).write_text(VALID_MUSICXML, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def fake_parse(path):
        parsed_paths.append(Path(path))
        return _parsed_score()

    monkeypatch.setattr(import_module.subprocess, "run", fake_run)
    monkeypatch.setattr(import_module.converter, "parse", fake_parse)

    scores = {}
    result = await ImportScoreTool(scores).execute(
        score_id="draft", source=str(source), source_type="auto"
    )

    assert result["status"] == "success"
    assert result["source_type"] == "file"
    assert scores["draft"] is not None
    assert source.read_bytes() == original_bytes
    assert result["import_repairs"] == []
    warning_codes = {item["code"] for item in result["import_warnings"]}
    assert warning_codes == {
        "musescore_native_context_unavailable",
        "musescore_musicxml_conversion",
    }
    assert result["import_context"] == []

    command, kwargs = subprocess_calls[0]
    assert command[0] == str(executable)
    assert command[1] == "-o"
    assert command[3] == str(source.resolve())
    assert Path(command[2]) != source
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert 0 < kwargs["timeout"] <= 120
    assert len(parsed_paths) == 1
    assert parsed_paths[0] != source
    assert not parsed_paths[0].exists()


@pytest.mark.asyncio
async def test_plain_musicxml_repairs_empty_beat_unit_in_derivative_only(
    monkeypatch, tmp_path
):
    source = tmp_path / "malformed.musicxml"
    source.write_text(MUSICXML_WITH_EMPTY_BEAT_UNIT, encoding="utf-8")
    original_text = source.read_text(encoding="utf-8")
    parsed = {}
    real_parse = import_module.converter.parse

    def fake_parse(path):
        parsed_path = Path(path)
        parsed["path"] = parsed_path
        parsed["xml"] = parsed_path.read_text(encoding="utf-8")
        return real_parse(path)

    monkeypatch.setattr(import_module.converter, "parse", fake_parse)

    result = await ImportScoreTool({}).execute(
        score_id="repaired", source=str(source), source_type="file"
    )

    assert result["status"] == "success"
    assert source.read_text(encoding="utf-8") == original_text
    assert parsed["path"] != source
    assert not parsed["path"].exists()

    derivative = parsed["xml"]
    assert "<metronome" not in derivative
    assert "<beat-unit" not in derivative
    assert "<words>gently</words>" in derivative
    assert '<sound tempo="84"' in derivative
    assert result["import_repairs"] == [
        {
            "code": "removed_invalid_metronome",
            "count": 1,
            "message": result["import_repairs"][0]["message"],
        }
    ]
    assert "no beat unit was inferred" in result["import_repairs"][0]["message"].lower()
    assert [item["code"] for item in result["import_warnings"]] == [
        "invalid_metronome_semantics_removed"
    ]


@pytest.mark.asyncio
async def test_valid_musicxml_is_parsed_from_original_without_derivative(
    monkeypatch, tmp_path
):
    source = tmp_path / "valid.musicxml"
    source.write_text(VALID_MUSICXML, encoding="utf-8")
    parsed_paths = []

    def fake_parse(path):
        parsed_paths.append(Path(path))
        return _parsed_score()

    monkeypatch.setattr(import_module.converter, "parse", fake_parse)

    result = await ImportScoreTool({}).execute(
        score_id="clean", source=str(source), source_type="file"
    )

    assert result["status"] == "success"
    assert parsed_paths == [source.resolve()]
    assert result["import_repairs"] == []
    assert result["import_warnings"] == []


@pytest.mark.asyncio
async def test_missing_musescore_returns_actionable_error(monkeypatch, tmp_path):
    source = tmp_path / "draft.mscx"
    source.write_text("<museScore />", encoding="utf-8")
    monkeypatch.delenv("MUSESCORE_EXECUTABLE", raising=False)
    monkeypatch.setattr(import_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        ImportScoreTool, "_common_musescore_paths", staticmethod(lambda: [])
    )

    def unexpected_subprocess(*_args, **_kwargs):
        pytest.fail("subprocess should not run when MuseScore cannot be located")

    monkeypatch.setattr(import_module.subprocess, "run", unexpected_subprocess)

    result = await ImportScoreTool({}).execute(
        score_id="missing-app", source=str(source), source_type="file"
    )

    assert result["status"] == "error"
    assert "MuseScore is required" in result["message"]
    assert "MUSESCORE_EXECUTABLE" in result["message"]
    assert "PATH" in result["message"]


@pytest.mark.asyncio
async def test_musescore_export_failure_reports_diagnostic_without_modifying_source(
    monkeypatch, tmp_path
):
    source = tmp_path / "draft.mscz"
    source.write_bytes(b"original")
    executable = tmp_path / "MuseScore4.exe"
    executable.write_bytes(b"mock executable")
    monkeypatch.setenv("MUSESCORE_EXECUTABLE", str(executable))

    def failed_run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command, 2, stdout="", stderr="Could not read score"
        )

    monkeypatch.setattr(import_module.subprocess, "run", failed_run)

    result = await ImportScoreTool({}).execute(
        score_id="failed-export", source=str(source), source_type="file"
    )

    assert result["status"] == "error"
    assert "exit code 2" in result["message"]
    assert "Could not read score" in result["message"]
    assert "original file was not modified" in result["message"].lower()
    assert source.read_bytes() == b"original"


def test_musescore_path_lookup_precedes_common_install_paths(monkeypatch):
    monkeypatch.delenv("MUSESCORE_EXECUTABLE", raising=False)
    lookup_order = []

    def fake_which(name):
        lookup_order.append(name)
        return "C:/tools/mscore4.exe" if name == "mscore4" else None

    monkeypatch.setattr(import_module.shutil, "which", fake_which)

    assert ImportScoreTool._find_musescore_executable() == "C:/tools/mscore4.exe"
    assert lookup_order == ["MuseScore4", "mscore4"]


def test_allowed_import_roots_are_opt_in_and_use_resolved_containment(
    monkeypatch, tmp_path
):
    cwd = tmp_path / "server-cwd"
    fake_temp = tmp_path / "isolated-temp"
    allowed_one = tmp_path / "projects-a"
    allowed_two = tmp_path / "projects-b"
    outside = tmp_path / "outside"
    for directory in (cwd, fake_temp, allowed_one, allowed_two, outside):
        directory.mkdir()

    allowed_score = allowed_two / "piece" / "score.musicxml"
    allowed_score.parent.mkdir()
    allowed_score.write_text(VALID_MUSICXML, encoding="utf-8")
    outside_score = outside / "score.musicxml"
    outside_score.write_text(VALID_MUSICXML, encoding="utf-8")

    monkeypatch.chdir(cwd)
    monkeypatch.setattr(import_module.tempfile, "gettempdir", lambda: str(fake_temp))
    monkeypatch.setenv(
        "MUSIC21_ALLOWED_IMPORT_ROOTS",
        os.pathsep.join((str(allowed_one), str(allowed_two / ".." / "projects-b"))),
    )

    tool = ImportScoreTool({})
    assert tool._validate_safe_path(str(allowed_score)) == str(allowed_score.resolve())
    with pytest.raises(ValueError, match="outside allowed directories"):
        tool._validate_safe_path(str(outside_score))


@pytest.mark.asyncio
async def test_import_metadata_counts_measures_and_divisi_pitch_range():
    score = stream.Score()
    soprano = stream.Part(id="Soprano")
    alto = stream.Part(id="Alto")
    for measure_number in (1, 2):
        soprano_measure = stream.Measure(number=measure_number)
        soprano_measure.append(chord.Chord(["C4", "G5"]))
        soprano.append(soprano_measure)
        alto_measure = stream.Measure(number=measure_number)
        alto_measure.append(note.Note("E3"))
        alto.append(alto_measure)
    score.insert(0, soprano)
    score.insert(0, alto)

    metadata = await ImportScoreTool({})._extract_metadata(score)

    assert metadata["num_parts"] == 2
    assert metadata["num_measures"] == 2
    assert metadata["num_notes"] == 4
    assert metadata["pitch_range"] == 27


def test_native_musescore_context_decodes_metric_modulation_and_gradual_tempo():
    root = ET.fromstring(MUSESCORE_NATIVE_XML)  # noqa: S314 - fixed test fixture

    context = ImportScoreTool._musescore_context_from_xml(root)

    assert context[0] == {
        "type": "tempo",
        "source": "musescore_native",
        "measure": 1,
        "quarter_bpm": 90.0,
        "text": "Andante",
    }
    metric_tempo = context[1]
    assert metric_tempo["measure"] == 2
    assert metric_tempo["quarter_bpm"] == 120.0
    assert metric_tempo["text"] == "half = quarter"
    assert metric_tempo["metric_modulation"] == {
        "left": "half",
        "relation": "equals",
        "right": "quarter",
    }
    gradual = context[2]
    assert gradual["change_type"] == "allargando"
    assert gradual["factor"] == 0.83
    assert gradual["span"] == {"measures": "1", "fractions": "1/4"}


def test_native_musescore_context_is_read_from_mscz_archive(tmp_path):
    source = tmp_path / "draft.mscz"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("score.mscx", MUSESCORE_NATIVE_XML)
        archive.writestr("META-INF/container.xml", "<container />")
    original_bytes = source.read_bytes()
    warnings: list[dict[str, object]] = []

    context = ImportScoreTool._extract_musescore_native_context(
        source, ".mscz", warnings
    )

    assert warnings == []
    assert context[0]["measure"] == 1
    assert context[1]["metric_modulation"] == {
        "left": "half",
        "relation": "equals",
        "right": "quarter",
    }
    assert source.read_bytes() == original_bytes


@pytest.mark.asyncio
async def test_native_context_is_returned_and_attached_to_imported_score(
    monkeypatch, tmp_path
):
    source = tmp_path / "draft.mscx"
    source.write_text(MUSESCORE_NATIVE_XML, encoding="utf-8")
    executable = tmp_path / "MuseScore4.exe"
    executable.write_bytes(b"mock executable")
    monkeypatch.setenv("MUSESCORE_EXECUTABLE", str(executable))

    def fake_run(command, **_kwargs):
        Path(command[2]).write_text(VALID_MUSICXML, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(import_module.subprocess, "run", fake_run)
    monkeypatch.setattr(import_module.converter, "parse", lambda _path: _parsed_score())
    scores = {}

    result = await ImportScoreTool(scores).execute(
        score_id="native", source=str(source), source_type="file"
    )

    assert result["status"] == "success"
    assert result["import_context"][1]["metric_modulation"]["left"] == "half"
    attached = scores["native"].editorial.get("music21_mcp_import_context")
    assert attached == result["import_context"]


@pytest.mark.asyncio
async def test_post_export_parse_error_keeps_diagnostics_and_repairs(
    monkeypatch, tmp_path
):
    source = tmp_path / "broken.mscx"
    source.write_text(MUSESCORE_NATIVE_XML, encoding="utf-8")
    executable = tmp_path / "MuseScore4.exe"
    executable.write_bytes(b"mock executable")
    monkeypatch.setenv("MUSESCORE_EXECUTABLE", str(executable))

    def fake_run(command, **_kwargs):
        Path(command[2]).write_text(
            MUSICXML_WITH_EMPTY_BEAT_UNIT, encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def failed_parse(_path):
        raise ValueError("unknown MusicXML type near measure 20")

    monkeypatch.setattr(import_module.subprocess, "run", fake_run)
    monkeypatch.setattr(import_module.converter, "parse", failed_parse)

    result = await ImportScoreTool({}).execute(
        score_id="diagnostic", source=str(source), source_type="file"
    )

    assert result["status"] == "error"
    assert "unknown MusicXML type near measure 20" in result["message"]
    assert result["import_repairs"][0]["code"] == "removed_invalid_metronome"
    assert result["import_context"][1]["metric_modulation"]["right"] == "quarter"
