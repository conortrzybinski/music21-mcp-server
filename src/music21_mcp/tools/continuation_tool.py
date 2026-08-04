"""Phrase- and cadence-aware deterministic score continuation."""

from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING, Any

from music21 import bar, chord, key, meter, note, pitch, roman, stream, tempo

from .base_tool import BaseTool

if TYPE_CHECKING:
    from collections.abc import Sequence


class ContinuationTool(BaseTool):
    """Develop existing motives into an appended continuation score."""

    VALID_CADENCES = {"PAC", "IAC", "HC", "DC", "PC"}
    STYLE_PROGRESSIONS = {
        "baroque": ["I", "ii6", "V", "I"],
        "classical": ["I", "vi", "IV", "V"],
        "jazz": ["I7", "vi7", "ii7", "V7"],
        "pop": ["I", "V", "vi", "IV"],
        "romantic": ["I", "IV", "ii6", "V"],
    }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Analyze a score, append generated measures, and store a new score."""
        score_id = kwargs.get("score_id", "")
        continuation_length = kwargs.get("continuation_length", 8)
        form_context = kwargs.get("form_context")
        preserve_motifs = kwargs.get("preserve_motifs", True)
        cadence_target = kwargs.get("cadence_target")
        style = kwargs.get("style", "classical")

        error = self.validate_inputs(**kwargs)
        if error:
            return self.create_error_response(error)

        with self.error_handling(f"Phrase-aware continuation for '{score_id}'"):
            source = self.get_score(score_id)
            source_parts = self._musical_parts(source)
            if not any(self._pitched_notes(part) for part in source_parts):
                return self.create_error_response("Score contains no pitched material")

            self.report_progress(0.1, "Analyzing key, phrases, and motives")
            analysis = self._analyze_score(source, form_context)
            key_object = analysis.pop("_key_object")
            time_signature = analysis.pop("_time_signature_object")
            progression = self._build_progression(
                continuation_length, cadence_target, style
            )
            transformation = self._choose_transformation(
                preserve_motifs, analysis["form_position"], style
            )

            continued = copy.deepcopy(source)
            target_parts = self._musical_parts(continued)
            append_offset = float(continued.highestTime)
            first_measure = analysis["existing_measures"] + 1
            motivic_development: list[dict[str, Any]] = []

            self.report_progress(0.35, "Generating continuation")
            for index, (source_part, target_part) in enumerate(
                zip(source_parts, target_parts, strict=True)
            ):
                motif = self._pitched_notes(source_part)[:4]
                self._append_part(
                    target_part,
                    motif,
                    append_offset=append_offset,
                    first_measure=first_measure,
                    measure_count=continuation_length,
                    time_signature=time_signature,
                    key_object=key_object,
                    progression=progression,
                    transformation=transformation,
                    phrase_length=analysis["phrase_length"],
                    part_index=index,
                )
                if preserve_motifs:
                    motivic_development.append(
                        {
                            "original_motif": [n.pitch.nameWithOctave for n in motif],
                            "transformation": transformation,
                            "location": {
                                "part": self._part_name(source_part, index),
                                "start_measure": first_measure,
                                "end_measure": first_measure + continuation_length - 1,
                            },
                        }
                    )
                self.report_progress(
                    0.4 + 0.45 * ((index + 1) / len(source_parts)),
                    f"Generated {self._part_name(source_part, index)} continuation",
                )

            output_id = self._next_output_id(score_id)
            self.score_manager[output_id] = continued
            cadence = cadence_target or "PAC"
            self.report_progress(1.0, "Continuation complete")
            return self.create_success_response(
                message=f"Generated {continuation_length} continuation measures",
                continuation_score_id=output_id,
                measures_generated=continuation_length,
                harmonic_analysis={
                    "key": analysis["key"],
                    "progression": progression,
                    "cadence": cadence,
                    "source_progression": analysis["source_progression"],
                    "harmonic_rhythm": analysis["harmonic_rhythm"],
                },
                motivic_development=motivic_development,
                form_position=analysis["form_position"],
                phrase_length=analysis["phrase_length"],
                time_signature=analysis["time_signature"],
                tempo=analysis["tempo"],
                style=style,
            )

    def validate_inputs(self, **kwargs: Any) -> str | None:
        """Validate generation bounds and musical options."""
        score_id = kwargs.get("score_id", "")
        continuation_length = kwargs.get("continuation_length", 8)
        form_context = kwargs.get("form_context")
        preserve_motifs = kwargs.get("preserve_motifs", True)
        cadence_target = kwargs.get("cadence_target")
        style = kwargs.get("style", "classical")

        error = self.check_score_exists(score_id)
        if error:
            return error
        if (
            isinstance(continuation_length, bool)
            or not isinstance(continuation_length, int)
            or not 1 <= continuation_length <= 64
        ):
            return "continuation_length must be an integer between 1 and 64"
        if form_context is not None and (
            not isinstance(form_context, str) or not form_context.strip()
        ):
            return "form_context must be a non-empty string when provided"
        if not isinstance(preserve_motifs, bool):
            return "preserve_motifs must be a boolean"
        if cadence_target is not None and (
            not isinstance(cadence_target, str)
            or cadence_target not in self.VALID_CADENCES
        ):
            return (
                f"Invalid cadence_target: {cadence_target}. Choose from: "
                f"{', '.join(sorted(self.VALID_CADENCES))}"
            )
        if not isinstance(style, str) or not style.strip():
            return "style must be a non-empty string"
        return None

    def _analyze_score(
        self, score: stream.Stream, form_context: str | None
    ) -> dict[str, Any]:
        """Extract compact, JSON-safe musical context for continuation."""
        try:
            key_object = score.analyze("key")
        except Exception:
            key_object = key.Key("C")
        if not isinstance(key_object, key.Key):
            key_object = key.Key(str(key_object.tonic), str(key_object.mode))

        time_signatures = list(score.recurse().getElementsByClass(meter.TimeSignature))
        time_signature = (
            copy.deepcopy(time_signatures[0])
            if time_signatures
            else meter.TimeSignature("4/4")
        )
        tempo_marks = list(score.recurse().getElementsByClass(tempo.MetronomeMark))
        bpm = float(tempo_marks[0].number or 120) if tempo_marks else 120.0
        existing_measures = self._measure_count(score, time_signature)
        phrase_length = self._estimate_phrase_length(existing_measures)
        source_progression, harmonic_rhythm = self._source_harmony(
            score, key_object, existing_measures
        )

        return {
            "key": f"{key_object.tonic.name} {key_object.mode}",
            "time_signature": time_signature.ratioString,
            "tempo": bpm,
            "existing_measures": existing_measures,
            "phrase_length": phrase_length,
            "source_progression": source_progression,
            "harmonic_rhythm": harmonic_rhythm,
            "form_position": self._form_position(form_context, existing_measures),
            "_key_object": key_object,
            "_time_signature_object": time_signature,
        }

    @staticmethod
    def _musical_parts(score: stream.Stream) -> list[stream.Stream]:
        if isinstance(score, stream.Score) and score.parts:
            return list(score.parts)
        return [score]

    @staticmethod
    def _pitched_notes(part: stream.Stream) -> list[note.Note]:
        return [n for n in part.recurse().notes if isinstance(n, note.Note)]

    @staticmethod
    def _part_name(part: stream.Stream, index: int) -> str:
        return str(getattr(part, "partName", None) or f"Part {index + 1}")

    @staticmethod
    def _measure_count(
        score: stream.Stream, time_signature: meter.TimeSignature
    ) -> int:
        measures = list(score.recurse().getElementsByClass(stream.Measure))
        numbers = [m.number for m in measures if isinstance(m.number, int)]
        if numbers:
            return max(numbers)
        bar_length = float(time_signature.barDuration.quarterLength)
        return max(1, math.ceil(float(score.highestTime) / bar_length))

    @staticmethod
    def _estimate_phrase_length(existing_measures: int) -> int:
        for conventional_length in (8, 4, 2):
            if existing_measures >= conventional_length:
                return conventional_length
        return max(1, existing_measures)

    @staticmethod
    def _source_harmony(
        score: stream.Stream, key_object: key.Key, measure_count: int
    ) -> tuple[list[str], float]:
        try:
            chords = list(score.chordify().recurse().getElementsByClass(chord.Chord))
            numerals: list[str] = []
            for sonority in chords:
                figure = roman.romanNumeralFromChord(sonority, key_object).figure
                if not numerals or numerals[-1] != figure:
                    numerals.append(figure)
            return numerals[-8:], round(len(chords) / max(1, measure_count), 2)
        except Exception:
            return [], 0.0

    def _build_progression(
        self, length: int, cadence_target: str | None, style: str
    ) -> list[str]:
        base = self.STYLE_PROGRESSIONS.get(
            style.casefold(), self.STYLE_PROGRESSIONS["classical"]
        )
        progression = [base[index % len(base)] for index in range(length)]
        cadence = cadence_target or "PAC"
        cadence_pairs = {
            "PAC": ("V", "I"),
            "IAC": ("V6", "I"),
            "HC": ("ii6", "V"),
            "DC": ("V", "vi"),
            "PC": ("IV", "I"),
        }
        approach, arrival = cadence_pairs[cadence]
        if length == 1:
            progression[-1] = arrival if cadence != "HC" else "V"
        else:
            progression[-2:] = [approach, arrival]
        return progression

    @staticmethod
    def _form_position(
        form_context: str | None, existing_measures: int
    ) -> dict[str, Any] | None:
        if form_context is None:
            return None
        normalized = form_context.casefold().replace("_", "-")
        if normalized == "aaba":
            aaba_labels = ("A1", "A2", "B", "A3")
            current = aaba_labels[
                ((max(existing_measures, 1) - 1) // 8) % len(aaba_labels)
            ]
            following = aaba_labels[(aaba_labels.index(current) + 1) % len(aaba_labels)]
        elif normalized == "verse-chorus":
            verse_labels = ("verse", "chorus")
            current = verse_labels[((max(existing_measures, 1) - 1) // 8) % 2]
            following = verse_labels[1 - verse_labels.index(current)]
        elif normalized == "sonata":
            current = (
                "exposition"
                if existing_measures <= 16
                else "development"
                if existing_measures <= 32
                else "recapitulation"
            )
            following = {
                "exposition": "development",
                "development": "recapitulation",
                "recapitulation": "coda",
            }[current]
        else:
            current = form_context
            following = "new contrasting phrase"
        return {
            "form": form_context,
            "current_section": current,
            "next_section": following,
        }

    @staticmethod
    def _choose_transformation(
        preserve_motifs: bool, form_position: dict[str, Any] | None, style: str
    ) -> str:
        if not preserve_motifs:
            return "new material"
        if form_position and form_position["next_section"] in {"B", "development"}:
            return "inversion"
        if style.casefold() == "romantic":
            return "augmentation"
        return "sequence"

    def _append_part(
        self,
        target_part: stream.Stream,
        motif: Sequence[note.Note],
        *,
        append_offset: float,
        first_measure: int,
        measure_count: int,
        time_signature: meter.TimeSignature,
        key_object: key.Key,
        progression: Sequence[str],
        transformation: str,
        phrase_length: int,
        part_index: int,
    ) -> None:
        """Generate measured monophony for one part at the common append offset."""
        existing_measures = list(
            target_part.recurse().getElementsByClass(stream.Measure)
        )
        if existing_measures:
            existing_measures[-1].rightBarline = None

        bar_length = float(time_signature.barDuration.quarterLength)
        motif_pitches = [n.pitch.midi for n in motif] or [60 - 7 * part_index]
        motif_rhythms = [max(0.25, float(n.quarterLength)) for n in motif] or [1.0]
        if transformation == "augmentation":
            motif_rhythms = [duration * 2 for duration in motif_rhythms]

        event_index = 0
        for measure_index in range(measure_count):
            generated_measure = stream.Measure(number=first_measure + measure_index)
            if measure_index == 0 and not list(
                target_part.recurse().getElementsByClass(meter.TimeSignature)
            ):
                generated_measure.insert(0, copy.deepcopy(time_signature))

            harmony = roman.RomanNumeral(progression[measure_index], key_object)
            remaining = bar_length
            while remaining > 1e-9:
                duration = min(
                    motif_rhythms[event_index % len(motif_rhythms)], remaining
                )
                proposed = motif_pitches[event_index % len(motif_pitches)]
                if transformation == "inversion":
                    proposed = motif_pitches[0] - (proposed - motif_pitches[0])
                elif transformation == "sequence":
                    sequence_step = (measure_index // max(1, phrase_length)) % 3
                    proposed += 2 * sequence_step

                is_strong = math.isclose(remaining, bar_length)
                is_final = measure_index == measure_count - 1 and math.isclose(
                    duration, remaining
                )
                pitch_classes = (
                    [p.pitchClass for p in harmony.pitches]
                    if is_strong or is_final or transformation == "new material"
                    else [p.pitchClass for p in key_object.getPitches()[:-1]]
                )
                generated_pitch = self._nearest_pitch_class(proposed, pitch_classes)
                generated_measure.append(
                    note.Note(pitch.Pitch(midi=generated_pitch), quarterLength=duration)
                )
                remaining -= duration
                event_index += 1

            if measure_index == measure_count - 1:
                generated_measure.rightBarline = bar.Barline("final")
            target_part.insert(
                append_offset + measure_index * bar_length, generated_measure
            )

    @staticmethod
    def _nearest_pitch_class(proposed_midi: int, pitch_classes: Sequence[int]) -> int:
        candidates = [
            midi
            for midi in range(proposed_midi - 12, proposed_midi + 13)
            if midi % 12 in pitch_classes
        ]
        return min(candidates, key=lambda midi: (abs(midi - proposed_midi), midi))

    def _next_output_id(self, score_id: str) -> str:
        base = f"{score_id}_continuation"
        candidate = base
        suffix = 2
        while candidate in self.score_manager:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate
