"""Unit tests for lyric underlay, choral distribution, and continuation."""

import pytest
from music21 import meter, note, pitch, stream, tempo

from music21_mcp.services import MusicAnalysisService
from music21_mcp.tools import (
    ChoralTextDistributionTool,
    ContinuationTool,
    TextUnderlayTool,
)


def make_part(
    name: str = "Soprano",
    pitches: tuple[str, ...] = ("C4", "D4", "E4", "F4"),
    measures: int = 4,
) -> stream.Part:
    part = stream.Part(id=name)
    part.partName = name
    for measure_number in range(1, measures + 1):
        measure = stream.Measure(number=measure_number)
        if measure_number == 1:
            measure.append(meter.TimeSignature("4/4"))
        for pitch_name in pitches:
            measure.append(note.Note(pitch_name, quarterLength=1))
        part.append(measure)
    return part


def make_score(part_names: tuple[str, ...] = ("Soprano",)) -> stream.Score:
    score = stream.Score()
    score.insert(0, tempo.MetronomeMark(number=96))
    default_pitches = {
        "Soprano": ("C5", "D5", "E5", "G5"),
        "Alto": ("G4", "A4", "C5", "B4"),
        "Tenor": ("E4", "F4", "G4", "D4"),
        "Bass": ("C3", "F3", "G3", "C3"),
    }
    for name in part_names:
        score.insert(0, make_part(name, default_pitches.get(name, ("C4",)), 4))
    return score


class TestTextUnderlayTool:
    def test_validation(self, clean_score_storage):
        tool = TextUnderlayTool(clean_score_storage)
        assert "not found" in tool.validate_inputs(score_id="missing", text="Kyrie")

        clean_score_storage["melody"] = make_part()
        assert "non-empty" in tool.validate_inputs(score_id="melody", text="")
        assert "Unsupported" in tool.validate_inputs(
            score_id="melody", text="Kyrie", language="klingon"
        )
        assert "Unsupported" in tool.validate_inputs(
            score_id="melody", text="Kyrie", language=[]
        )
        assert "positive integer" in tool.validate_inputs(
            score_id="melody", text="Kyrie", melisma_limit=0
        )
        assert "boolean" in tool.validate_inputs(
            score_id="melody", text="Kyrie", prefer_stressed_on_strong="yes"
        )
        assert tool.validate_inputs(score_id="melody", text="Kyrie") is None

    def test_language_aware_syllabification(self, clean_score_storage):
        tool = TextUnderlayTool(clean_score_storage)
        syllables = tool._syllabify_text("Gloria in excelsis Deo", "latin")
        assert [syllable.text.casefold() for syllable in syllables] == [
            "glo",
            "ri",
            "a",
            "in",
            "ex",
            "cel",
            "sis",
            "de",
            "o",
        ]
        assert syllables[1].stressed
        assert syllables[2].word_final

    def test_explicit_hyphenation_and_syllabic_values(self, clean_score_storage):
        tool = TextUnderlayTool(clean_score_storage)
        syllables = tool._syllabify_text("Hal-le-lu-jah", "english")
        assert [item.text for item in syllables] == ["Hal", "le", "lu", "jah"]
        assert [item.syllabic for item in syllables] == [
            "begin",
            "middle",
            "middle",
            "end",
        ]

    @pytest.mark.asyncio
    async def test_execute_applies_bounded_melismas(self, clean_score_storage):
        score = make_score()
        clean_score_storage["melody"] = score
        progress = []
        tool = TextUnderlayTool(clean_score_storage)
        tool.set_progress_callback(lambda value, message: progress.append(value))

        result = await tool.execute(
            score_id="melody", text="Hal-le-lu-jah", melisma_limit=3
        )

        assert result["status"] == "success"
        assert len(result["syllable_map"]) == 12
        assert any(item["melisma"] for item in result["syllable_map"])
        assert result["warnings"] == [
            "Melisma limit leaves 4 trailing notes without lyrics"
        ]
        assert progress[-1] == 1.0
        lyric_notes = [n for n in score.parts[0].recurse().notes if n.lyric]
        assert [n.lyric for n in lyric_notes] == ["Hal", "le", "lu", "jah"]

    @pytest.mark.asyncio
    async def test_execute_truncates_long_text(self, clean_score_storage):
        melody = stream.Part()
        melody.append(note.Note("C4"))
        melody.append(note.Note("D4"))
        clean_score_storage["short"] = melody

        result = await TextUnderlayTool(clean_score_storage).execute(
            score_id="short", text="one two three"
        )

        assert result["status"] == "success"
        assert len(result["syllable_map"]) == 2
        assert "truncated" in result["warnings"][0]

    @pytest.mark.asyncio
    async def test_execute_rejects_score_without_notes(self, clean_score_storage):
        clean_score_storage["empty"] = stream.Score()
        result = await TextUnderlayTool(clean_score_storage).execute(
            score_id="empty", text="Kyrie"
        )
        assert result == {
            "status": "error",
            "message": "No melody notes found in score",
        }

    def test_apply_underlay_handles_no_words(self, clean_score_storage):
        tool = TextUnderlayTool(clean_score_storage)
        result = tool.apply_underlay([note.Note("C4")], "123 !!!")
        assert result["syllable_map"] == []
        assert result["warnings"] == ["Text contained no words"]

    def test_strong_beat_rules(self, clean_score_storage):
        part = make_part(measures=1)
        notes = list(part.recurse().notes)
        tool = TextUnderlayTool(clean_score_storage)
        assert tool._is_strong(notes[0])
        assert not tool._is_strong(notes[1])
        assert tool._is_strong(notes[2])


class TestChoralTextDistributionTool:
    def test_validation(self, clean_score_storage):
        tool = ChoralTextDistributionTool(clean_score_storage)
        assert "not found" in tool.validate_inputs(score_id="missing", text="Gloria")

        clean_score_storage["part"] = make_part()
        assert "multi-part" in tool.validate_inputs(score_id="part", text="Gloria")

        clean_score_storage["one"] = make_score()
        assert "between 2 and 8" in tool.validate_inputs(score_id="one", text="Gloria")

        clean_score_storage["satb"] = make_score(("Soprano", "Alto", "Tenor", "Bass"))
        assert "non-empty" in tool.validate_inputs(score_id="satb", text="")
        assert "Invalid entry_scheme" in tool.validate_inputs(
            score_id="satb", text="Gloria", entry_scheme="random"
        )
        assert "Invalid entry_scheme" in tool.validate_inputs(
            score_id="satb", text="Gloria", entry_scheme=[]
        )
        assert "non-negative" in tool.validate_inputs(
            score_id="satb", text="Gloria", stagger_offset_measures=-1
        )
        assert "non-empty mapping" in tool.validate_inputs(
            score_id="satb", text="Gloria", voice_assignments={}
        )
        assert "unknown part" in tool.validate_inputs(
            score_id="satb",
            text="Gloria",
            voice_assignments={"Oboe": "Gloria"},
        )

    @pytest.mark.asyncio
    async def test_simultaneous_auto_distribution(self, clean_score_storage):
        score = make_score(("Soprano", "Alto", "Tenor", "Bass"))
        clean_score_storage["satb"] = score

        result = await ChoralTextDistributionTool(clean_score_storage).execute(
            score_id="satb",
            text="Gloria in excelsis Deo et in terra pax",
            entry_scheme="simultaneous",
        )

        assert result["status"] == "success"
        assert len(result["voice_assignments"]) == 4
        assert set(result["entry_points"].values()) == {1}
        assert all(result["syllable_maps"].values())
        assert all(any(n.lyric for n in part.recurse().notes) for part in score.parts)

    @pytest.mark.asyncio
    async def test_staggered_imitative_entries(self, clean_score_storage):
        score = make_score(("Soprano", "Alto", "Tenor", "Bass"))
        clean_score_storage["satb"] = score

        result = await ChoralTextDistributionTool(clean_score_storage).execute(
            score_id="satb",
            text="Kyrie eleison",
            entry_scheme="imitative",
            stagger_offset_measures=1,
        )

        assert result["entry_points"] == {
            "Soprano": 1,
            "Alto": 2,
            "Tenor": 3,
            "Bass": 4,
        }
        assert set(result["voice_assignments"].values()) == {"Kyrie eleison"}
        bass_map = result["syllable_maps"]["Bass"]
        assert bass_map[0]["measure"] == 4

    @pytest.mark.asyncio
    async def test_explicit_assignments_are_resolved_case_insensitively(
        self, clean_score_storage
    ):
        clean_score_storage["duet"] = make_score(("Soprano", "Alto"))
        result = await ChoralTextDistributionTool(clean_score_storage).execute(
            score_id="duet",
            text="fallback",
            voice_assignments={"soprano": "Ave Maria", "ALTO": "Sancta Maria"},
            entry_scheme="simultaneous",
        )
        assert result["voice_assignments"] == {
            "Soprano": "Ave Maria",
            "Alto": "Sancta Maria",
        }

    @pytest.mark.asyncio
    async def test_range_and_missing_entry_warnings(self, clean_score_storage):
        score = make_score(("Soprano", "Alto"))
        first_note = next(iter(score.parts[0].recurse().notes))
        first_note.pitch = pitch.Pitch("C7")
        clean_score_storage["duet"] = score
        tool = ChoralTextDistributionTool(clean_score_storage)

        range_result = await tool.execute(
            score_id="duet",
            text="one two",
            voice_assignments={"Soprano": "one"},
            entry_scheme="simultaneous",
        )
        assert any("outside" in warning for warning in range_result["warnings"])

        missing_result = await tool.execute(
            score_id="duet",
            text="one two",
            entry_scheme="staggered",
            stagger_offset_measures=10,
        )
        assert any("no notes" in warning for warning in missing_result["warnings"])

    def test_auto_split_with_fewer_words_than_parts(self, clean_score_storage):
        sections = ChoralTextDistributionTool._split_text("Kyrie eleison", 4)
        assert sections == ["Kyrie", "eleison", "", ""]


class TestContinuationTool:
    def test_validation(self, clean_score_storage):
        tool = ContinuationTool(clean_score_storage)
        assert "not found" in tool.validate_inputs(score_id="missing")
        clean_score_storage["score"] = make_score()
        assert "between 1 and 64" in tool.validate_inputs(
            score_id="score", continuation_length=0
        )
        assert "non-empty" in tool.validate_inputs(score_id="score", form_context="")
        assert "boolean" in tool.validate_inputs(
            score_id="score", preserve_motifs="yes"
        )
        assert "Invalid cadence" in tool.validate_inputs(
            score_id="score", cadence_target="AUTHENTIC"
        )
        assert "Invalid cadence" in tool.validate_inputs(
            score_id="score", cadence_target=[]
        )
        assert "style" in tool.validate_inputs(score_id="score", style="")
        assert tool.validate_inputs(score_id="score", cadence_target="PAC") is None

    @pytest.mark.asyncio
    async def test_generates_appended_score_and_analysis(self, clean_score_storage):
        source = make_score()
        clean_score_storage["phrase"] = source
        progress = []
        tool = ContinuationTool(clean_score_storage)
        tool.set_progress_callback(lambda value, message: progress.append(value))

        result = await tool.execute(
            score_id="phrase",
            continuation_length=2,
            form_context="AABA",
            cadence_target="PAC",
        )

        assert result["status"] == "success"
        assert result["continuation_score_id"] == "phrase_continuation"
        assert result["harmonic_analysis"]["progression"] == ["V", "I"]
        assert result["harmonic_analysis"]["cadence"] == "PAC"
        assert result["measures_generated"] == 2
        assert result["motivic_development"][0]["transformation"] == "sequence"
        assert progress[-1] == 1.0

        continued = clean_score_storage["phrase_continuation"]
        assert (
            max(
                m.number
                for m in source.parts[0].recurse().getElementsByClass(stream.Measure)
            )
            == 4
        )
        assert (
            max(
                m.number
                for m in continued.parts[0].recurse().getElementsByClass(stream.Measure)
            )
            == 6
        )

    @pytest.mark.asyncio
    async def test_generates_unique_ids_and_new_material(self, clean_score_storage):
        clean_score_storage["phrase"] = make_score()
        tool = ContinuationTool(clean_score_storage)
        first = await tool.execute(
            score_id="phrase", continuation_length=1, preserve_motifs=False
        )
        second = await tool.execute(
            score_id="phrase", continuation_length=1, preserve_motifs=False
        )
        assert first["continuation_score_id"] == "phrase_continuation"
        assert second["continuation_score_id"] == "phrase_continuation_2"
        assert first["motivic_development"] == []

    @pytest.mark.asyncio
    async def test_empty_score_is_rejected(self, clean_score_storage):
        clean_score_storage["empty"] = stream.Score()
        result = await ContinuationTool(clean_score_storage).execute(
            score_id="empty", continuation_length=2
        )
        assert result["status"] == "error"
        assert "no pitched material" in result["message"]

    @pytest.mark.parametrize(
        ("cadence", "ending"),
        [
            ("PAC", ["V", "I"]),
            ("IAC", ["V6", "I"]),
            ("HC", ["ii6", "V"]),
            ("DC", ["V", "vi"]),
            ("PC", ["IV", "I"]),
        ],
    )
    def test_cadence_progressions(self, clean_score_storage, cadence, ending):
        tool = ContinuationTool(clean_score_storage)
        assert tool._build_progression(4, cadence, "classical")[-2:] == ending

    def test_single_measure_half_cadence(self, clean_score_storage):
        tool = ContinuationTool(clean_score_storage)
        assert tool._build_progression(1, "HC", "baroque") == ["V"]

    def test_form_positions_and_transformations(self, clean_score_storage):
        tool = ContinuationTool(clean_score_storage)
        aaba = tool._form_position("AABA", 16)
        assert aaba["current_section"] == "A2"
        assert aaba["next_section"] == "B"
        assert tool._choose_transformation(True, aaba, "classical") == "inversion"

        sonata = tool._form_position("sonata", 24)
        assert sonata["next_section"] == "recapitulation"
        assert tool._form_position("through-composed", 12)["next_section"] == (
            "new contrasting phrase"
        )
        assert tool._choose_transformation(True, None, "romantic") == "augmentation"
        assert tool._choose_transformation(False, None, "classical") == "new material"

    def test_nearest_pitch_class(self):
        assert ContinuationTool._nearest_pitch_class(61, [0, 4, 7]) == 60

    @pytest.mark.asyncio
    async def test_plain_part_can_be_continued(self, clean_score_storage):
        clean_score_storage["part"] = make_part()
        result = await ContinuationTool(clean_score_storage).execute(
            score_id="part", continuation_length=1, style="unknown"
        )
        assert result["status"] == "success"
        assert result["style"] == "unknown"


class TestCompositionServiceRegistration:
    @pytest.mark.asyncio
    async def test_service_delegates_to_all_three_tools(self):
        service = MusicAnalysisService(max_memory_mb=64, max_scores=10)
        service.scores.clear()
        service.scores["satb"] = make_score(("Soprano", "Alto", "Tenor", "Bass"))

        underlay = await service.text_underlay("satb", "Kyrie eleison")
        distribution = await service.choral_text_distribution(
            "satb", "Gloria in excelsis Deo", entry_scheme="simultaneous"
        )
        continuation = await service.phrase_aware_continuation(
            "satb", continuation_length=1, cadence_target="HC"
        )

        assert underlay["status"] == "success"
        assert distribution["status"] == "success"
        assert continuation["status"] == "success"
        assert continuation["harmonic_analysis"]["progression"] == ["V"]
        assert {
            "text_underlay",
            "choral_text_distribution",
            "phrase_aware_continuation",
        }.issubset(service.get_available_tools())
