"""Focused tests for compact, read-only score slices."""

import pytest
from music21 import chord, dynamics, key, meter, note, stream, tempo

from music21_mcp.tools.score_slice_tool import ScoreSliceTool


def make_score() -> stream.Score:
    score = stream.Score()
    for part_index, name in enumerate(("Soprano", "Alto")):
        part = stream.Part(id=name)
        part.partName = name
        for measure_number in range(1, 4):
            measure = stream.Measure(number=measure_number)
            if measure_number == 1:
                measure.append(meter.TimeSignature("3/4"))
                measure.append(key.KeySignature(-2))
                measure.insert(0, dynamics.Dynamic("mf"))
            if part_index == 0 and measure_number == 2:
                event = chord.Chord(["B-4", "D5"], quarterLength=1)
                event.addLyric("Mag-", lyricNumber=1)
                measure.insert(0.5, event)
                measure.insert(1.5, note.Rest(quarterLength=1.5))
            else:
                measure.append(note.Note("C4", quarterLength=3))
            part.append(measure)
        score.insert(0, part)
    return score


@pytest.mark.asyncio
async def test_slice_returns_exact_chord_lyric_and_annotation_locators():
    score = make_score()
    before = [
        (
            id(event),
            float(event.offset),
            float(event.duration.quarterLength),
            tuple(pitch.nameWithOctave for pitch in getattr(event, "pitches", ())),
            tuple((lyric.text, lyric.syllabic) for lyric in event.lyrics),
        )
        for event in score.recurse().notesAndRests
    ]

    result = await ScoreSliceTool({"draft": score}).execute(
        score_id="draft", start_measure=1, end_measure=2, parts=["Soprano"]
    )

    assert result["status"] == "success"
    assert result["read_only"] is True
    assert result["returned_measures"] == [1, 2]
    assert result["selected_parts"] == ["Soprano"]
    first_measure = result["parts"][0]["measures"][0]
    assert first_measure["context"]["time_signature"] == "3/4"
    assert first_measure["context"]["key_signature"]["sharps"] == -2
    assert any(item["type"] == "dynamic" for item in first_measure["annotations"])

    chord_event = result["parts"][0]["measures"][1]["events"][0]
    assert chord_event["type"] == "chord"
    assert chord_event["locator"] == "Soprano:m2:v1:o1/2"
    assert chord_event["offset"] == "1/2"
    assert chord_event["pitches"] == ["B-4", "D5"]
    assert chord_event["lyrics"][0]["text"] == "Mag"
    assert chord_event["lyrics"][0]["syllabic"] == "begin"
    after = [
        (
            id(event),
            float(event.offset),
            float(event.duration.quarterLength),
            tuple(pitch.nameWithOctave for pitch in getattr(event, "pitches", ())),
            tuple((lyric.text, lyric.syllabic) for lyric in event.lyrics),
        )
        for event in score.recurse().notesAndRests
    ]
    assert after == before


@pytest.mark.asyncio
async def test_slice_selects_by_index_and_honors_compact_flags():
    result = await ScoreSliceTool({"draft": make_score()}).execute(
        score_id="draft",
        start_measure=2,
        end_measure=2,
        parts=[2, "Alto"],
        include_rests=False,
        include_lyrics=False,
        include_annotations=False,
    )

    assert result["status"] == "success"
    assert result["selected_parts"] == ["Alto"]
    measure = result["parts"][0]["measures"][0]
    assert "annotations" not in measure
    assert all("lyrics" not in event for event in measure["events"])
    assert all(event["type"] != "rest" for event in measure["events"])


@pytest.mark.asyncio
async def test_slice_rejects_oversized_event_payload_without_partial_parts():
    result = await ScoreSliceTool({"draft": make_score()}).execute(
        score_id="draft", start_measure=1, end_measure=3, max_events=2
    )

    assert result["status"] == "error"
    assert result["event_count"] > result["max_events"]
    assert "narrow" in result["message"]


def test_slice_validation_rejects_unsafe_response_shapes():
    tool = ScoreSliceTool({"draft": make_score()})
    assert "not found" in tool.validate_inputs(score_id="missing")
    assert "at most 32" in tool.validate_inputs(
        score_id="draft", start_measure=1, end_measure=33
    )
    assert "greater than" in tool.validate_inputs(
        score_id="draft", start_measure=3, end_measure=2
    )
    assert "Unknown part" in tool.validate_inputs(
        score_id="draft", parts=["Bass"]
    )
    assert "max_events" in tool.validate_inputs(score_id="draft", max_events=0)
    assert "include_rests" in tool.validate_inputs(
        score_id="draft", include_rests="yes"
    )
    assert "detail" in tool.validate_inputs(score_id="draft", detail="verbose")


@pytest.mark.asyncio
async def test_events_are_chronological_across_voices():
    part = stream.Part(id="Choir")
    part.partName = "Choir"
    measure = stream.Measure(number=1)
    first_voice = stream.Voice(id="1")
    first_voice.insert(0, note.Note("C4"))
    first_voice.insert(2, note.Note("D4"))
    second_voice = stream.Voice(id="2")
    second_voice.insert(1, note.Note("E4"))
    second_voice.insert(3, note.Note("F4"))
    measure.insert(0, first_voice)
    measure.insert(0, second_voice)
    part.append(measure)
    score = stream.Score([part])

    result = await ScoreSliceTool({"polyphony": score}).execute(
        score_id="polyphony", start_measure=1, end_measure=1
    )

    events = result["parts"][0]["measures"][0]["events"]
    assert [event["offset"] for event in events] == ["0/1", "1/1", "2/1", "3/1"]
    assert [event["pitches"][0] for event in events] == ["C4", "E4", "D4", "F4"]


@pytest.mark.asyncio
async def test_slice_exposes_playback_tempo_and_native_metric_context():
    score = make_score()
    playback_tempo = tempo.MetronomeMark(number=None)
    playback_tempo.numberSounding = 120
    score.parts[0].measure(2).insert(0, playback_tempo)
    score.editorial["music21_mcp_import_context"] = [
        {
            "type": "tempo",
            "source": "musescore_native",
            "measure": 2,
            "quarter_bpm": 120.0,
            "text": "half = quarter",
            "metric_modulation": {
                "left": "half",
                "relation": "equals",
                "right": "quarter",
            },
        }
    ]

    result = await ScoreSliceTool({"tempo": score}).execute(
        score_id="tempo", start_measure=2, end_measure=2, parts=["Soprano"]
    )

    measure = result["parts"][0]["measures"][0]
    assert measure["context"]["tempo"]["number_sounding"] == 120
    assert measure["context"]["tempo"]["quarter_bpm"] == 120.0
    assert result["source_context"][0]["metric_modulation"] == {
        "left": "half",
        "relation": "equals",
        "right": "quarter",
    }


@pytest.mark.asyncio
async def test_slice_reports_empty_measure_range():
    result = await ScoreSliceTool({"draft": make_score()}).execute(
        score_id="draft", start_measure=20, end_measure=21
    )
    assert result["status"] == "error"
    assert "No measures found" in result["message"]
