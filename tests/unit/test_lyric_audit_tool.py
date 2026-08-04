"""Focused tests for the read-only lyric engraving audit."""

import copy

import pytest
from music21 import meter, note, stream

from music21_mcp.tools.lyric_audit_tool import LyricAuditTool


def add_lyric(
    target: note.Note,
    text: str,
    syllabic: str = "single",
    verse: int = 1,
) -> None:
    target.addLyric(text, lyricNumber=verse)
    target.lyrics[-1].syllabic = syllabic


def make_part(
    name: str,
    lyric_specs: list[tuple[str | None, str]],
) -> stream.Part:
    part = stream.Part(id=name)
    part.partName = name
    measure = stream.Measure(number=1)
    measure.append(meter.TimeSignature("4/4"))
    for index, (text, syllabic) in enumerate(lyric_specs):
        item = note.Note("C4", quarterLength=1)
        item.pitch.midi += index
        if text is not None:
            add_lyric(item, text, syllabic)
        measure.append(item)
    part.append(measure)
    return part


def make_score(*parts: stream.Part) -> stream.Score:
    score = stream.Score()
    for part in parts:
        score.insert(0, part)
    return score


class TestLyricAuditValidation:
    def test_validation_rejects_bad_inputs(self, clean_score_storage):
        tool = LyricAuditTool(clean_score_storage)
        assert "not found" in tool.validate_inputs(score_id="missing")

        clean_score_storage["not_score"] = object()
        assert "music21 Stream" in tool.validate_inputs(score_id="not_score")

        clean_score_storage["score"] = make_score(
            make_part("Soprano", [("Kyrie", "single")])
        )
        assert "Unsupported" in tool.validate_inputs(
            score_id="score", language="klingon"
        )
        assert "positive integer" in tool.validate_inputs(score_id="score", verse=0)
        assert "parts must" in tool.validate_inputs(score_id="score", parts={"S"})
        assert "cannot be empty" in tool.validate_inputs(score_id="score", parts=[])
        assert "must be a boolean" in tool.validate_inputs(
            score_id="score", include_lyric_events="yes"
        )
        assert "include_word_details" in tool.validate_inputs(
            score_id="score", include_word_details="yes"
        )
        assert "Unknown part" in tool.validate_inputs(
            score_id="score", parts=["Oboe"]
        )
        assert tool.validate_inputs(score_id="score") is None


class TestLyricAuditExtraction:
    @pytest.mark.asyncio
    async def test_reconstructs_words_with_exact_locators_and_no_mutation(
        self, clean_score_storage
    ):
        soprano = make_part(
            "Soprano",
            [
                ("Mag", "begin"),
                ("ni", "middle"),
                ("fi", "middle"),
                ("cat", "end"),
            ],
        )
        score = make_score(soprano)
        clean_score_storage["magnificat"] = score
        before = copy.deepcopy(
            [
                (item.lyric, item.lyrics[0].syllabic)
                for item in soprano.recurse().notes
            ]
        )

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="magnificat", include_lyric_events=True
        )

        after = [
            (item.lyric, item.lyrics[0].syllabic)
            for item in soprano.recurse().notes
        ]
        assert result["status"] == "success"
        assert result["read_only"] is True
        assert result["reconstructed_text"]["Soprano"]["1"]["text"] == (
            "Magnificat"
        )
        assert before == after

        second = result["lyric_events"][1]
        assert second["part"] == "Soprano"
        assert second["part_index"] == 1
        assert second["measure"] == 1
        assert second["voice"] == "1"
        assert second["offset"] == 1.0
        assert second["offset_in_measure"] == 1.0
        assert second["note_index"] == 2
        assert second["pitch"] == "C#4"
        assert second["verse"] == "1"
        assert result["coverage_stats"]["by_part"]["Soprano"]["verses"]["1"][
            "active_span_coverage_percent"
        ] == 100.0
        assert result["issues"] == []
        assert result["proposed_patches"] == []

    @pytest.mark.asyncio
    async def test_extracts_voice_and_fractional_offsets(self, clean_score_storage):
        part = stream.Part(id="Alto")
        part.partName = "Alto"
        measure = stream.Measure(number=3)
        voice = stream.Voice(id="2")
        first = note.Note("A4", quarterLength=0.5)
        second = note.Note("B4", quarterLength=0.5)
        add_lyric(first, "Ky", "begin")
        add_lyric(second, "rie", "end")
        voice.append(first)
        voice.append(second)
        measure.insert(0, voice)
        part.append(measure)
        clean_score_storage["alto"] = make_score(part)

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="alto", include_lyric_events=True
        )

        event = result["lyric_events"][1]
        assert event["measure"] == 3
        assert event["voice"] == "2"
        assert event["offset_in_measure"] == 0.5
        assert event["offset_in_measure_fraction"] == "1/2"

    @pytest.mark.asyncio
    async def test_part_selection_and_verse_filter(self, clean_score_storage):
        soprano = make_part("Soprano", [("Kyrie", "single")])
        alto = make_part("Alto", [("Christe", "single")])
        add_lyric(next(iter(alto.recurse().notes)), "Lord", verse=2)
        clean_score_storage["duet"] = make_score(soprano, alto)

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="duet",
            parts=[2, "Alto"],
            verse=2,
            include_lyric_events=True,
        )

        assert result["selected_parts"] == ["Alto"]
        assert result["verse"] == "2"
        assert [event["text"] for event in result["lyric_events"]] == ["Lord"]
        assert result["available_verses"] == {"Alto": ["1", "2"]}
        assert result["coverage_stats"]["overall"]["audited_part_verses"] == 1

    @pytest.mark.asyncio
    async def test_default_response_omits_bulk_lyric_events(self, clean_score_storage):
        clean_score_storage["compact"] = make_score(
            make_part("Soprano", [("Kyrie", "single")])
        )

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="compact"
        )

        assert result["lyric_event_count"] == 1
        assert result["lyric_events_included"] is False
        assert result["word_details_included"] is False
        assert "lyric_events" not in result
        assert "words" not in result["reconstructed_text"]["Soprano"]["1"]
        assert result["reconstructed_text"]["Soprano"]["1"]["word_count"] == 1
        assert result["finding_summary"] == {
            "issue_count": 0,
            "observation_count": 0,
            "proposed_patch_count": 0,
            "by_finding_type": {},
            "issue_types": {},
            "observation_types": {},
            "patch_operations": {},
        }

    @pytest.mark.asyncio
    async def test_full_word_details_are_opt_in(self, clean_score_storage):
        clean_score_storage["details"] = make_score(
            make_part("Soprano", [("Ky", "begin"), ("rie", "end")])
        )

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="details", include_word_details=True
        )

        assert result["word_details_included"] is True
        words = result["reconstructed_text"]["Soprano"]["1"]["words"]
        assert words[0]["text"] == "Kyrie"
        assert words[0]["start"]["measure"] == 1

    @pytest.mark.asyncio
    async def test_composite_elision_uses_external_boundary_state(
        self, clean_score_storage
    ):
        part = make_part("Soprano", [("bian", "begin"), (None, "single")])
        target = list(part.recurse().notes)[1]
        composite = note.Lyric()
        ending = note.Lyric("co", syllabic="end")
        elided = note.Lyric("e", syllabic="single")
        elided.elisionBefore = "_"
        composite.components = [ending, elided]
        target.lyrics = [composite]
        clean_score_storage["elision"] = make_score(part)

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="elision", include_lyric_events=True
        )

        event = result["lyric_events"][1]
        assert event["raw_syllabic"] == "composite"
        assert event["syllabic"] == "end"
        assert event["composite"] is True
        assert event["components"][1]["elision_before"] == "_"
        assert result["issues"] == []
        reconstruction = result["reconstructed_text"]["Soprano"]["1"]
        assert reconstruction["text"] == "bianco e"
        assert reconstruction["word_count"] == 2

    @pytest.mark.asyncio
    async def test_descriptive_verse_identifier_is_preserved(
        self, clean_score_storage
    ):
        part = make_part("Soprano", [("Kyrie", "single")])
        lyric = next(iter(part.recurse().notes)).lyrics[0]
        lyric.identifier = "Chorus"
        clean_score_storage["identifier"] = make_score(part)

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="identifier", include_lyric_events=True
        )

        assert result["available_verses"] == {"Soprano": ["Chorus"]}
        assert result["lyric_events"][0]["verse"] == "Chorus"

    @pytest.mark.asyncio
    async def test_empty_explicit_extender_is_not_removed(
        self, clean_score_storage, monkeypatch
    ):
        part = make_part("Soprano", [("", "single")])
        clean_score_storage["extender"] = make_score(part)
        monkeypatch.setattr(
            LyricAuditTool,
            "_has_explicit_extension",
            staticmethod(lambda _lyric: True),
        )

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="extender"
        )

        assert result["issues"] == []
        assert result["proposed_patches"] == []


class TestLyricAuditFindings:
    @pytest.mark.asyncio
    async def test_flags_malformed_states_and_only_proposes_safe_empty_patch(
        self, clean_score_storage
    ):
        part = make_part("Soprano", [("ni", "middle"), ("", "single")])
        clean_score_storage["bad"] = make_score(part)

        result = await LyricAuditTool(clean_score_storage).execute(score_id="bad")

        issue_types = {item["type"] for item in result["issues"]}
        assert "middle_without_begin" in issue_types
        assert "single_before_previous_end" in issue_types
        assert "empty_lyric_text" in issue_types
        assert all(item["confidence"] == "high" for item in result["issues"])
        assert result["finding_summary"]["issue_types"] == {
            "empty_lyric_text": 1,
            "middle_without_begin": 1,
            "single_before_previous_end": 1,
        }
        assert result["finding_summary"]["patch_operations"] == {
            "remove_empty_lyric": 1
        }
        assert result["proposed_patches"] == [
            {
                "operation": "remove_empty_lyric",
                "confidence": "high",
                "part": "Soprano",
                "measure": 1,
                "voice": "1",
                "offset_in_measure": 1.0,
                "note_index": 2,
                "verse": "1",
                "reason": "The lyric object contains no visible text.",
            }
        ]

    @pytest.mark.asyncio
    async def test_unexplained_internal_note_is_low_confidence_observation(
        self, clean_score_storage
    ):
        part = make_part(
            "Soprano",
            [("Ky", "single"), (None, "single"), ("rie", "single")],
        )
        clean_score_storage["gap"] = make_score(part)

        result = await LyricAuditTool(clean_score_storage).execute(score_id="gap")

        gaps = [
            item
            for item in result["observations"]
            if item["type"] == "possible_untexted_internal_notes"
        ]
        assert len(gaps) == 1
        assert gaps[0]["severity"] == "observation"
        assert gaps[0]["confidence"] == "low"
        assert gaps[0]["locations"][0]["measure"] == 1
        stats = result["coverage_stats"]["by_part"]["Soprano"]["verses"]["1"]
        assert stats["possible_untexted_internal_notes"] == 1
        assert stats["active_span_coverage_percent"] == 66.67

    @pytest.mark.asyncio
    async def test_word_continuation_gap_is_treated_as_inferred_melisma(
        self, clean_score_storage
    ):
        part = make_part(
            "Soprano",
            [("Ky", "begin"), (None, "single"), ("rie", "end")],
        )
        clean_score_storage["melisma"] = make_score(part)

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="melisma"
        )

        stats = result["coverage_stats"]["by_part"]["Soprano"]["verses"]["1"]
        assert stats["inferred_melisma_or_sustain_notes"] == 1
        assert stats["possible_untexted_internal_notes"] == 0
        assert not any(
            item["type"] == "possible_untexted_internal_notes"
            for item in result["observations"]
        )

    @pytest.mark.asyncio
    async def test_cross_part_text_and_verse_differences_are_observations(
        self, clean_score_storage
    ):
        soprano = make_part("Soprano", [("Kyrie", "single")])
        alto = make_part("Alto", [("Christe", "single")])
        add_lyric(next(iter(soprano.recurse().notes)), "Lord", verse=2)
        clean_score_storage["polytext"] = make_score(soprano, alto)

        result = await LyricAuditTool(clean_score_storage).execute(
            score_id="polytext"
        )

        observation_types = {item["type"] for item in result["observations"]}
        assert "cross_part_text_difference" in observation_types
        assert "cross_part_verse_set_difference" in observation_types
        assert all(
            item["severity"] == "observation" for item in result["observations"]
        )
        assert not any(
            item["type"].startswith("cross_part") for item in result["issues"]
        )
