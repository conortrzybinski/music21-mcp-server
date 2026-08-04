"""Compact, read-only inspection of a bounded score region."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from music21 import (
    bar,
    chord,
    clef,
    dynamics,
    expressions,
    harmony,
    key,
    meter,
    note,
    stream,
    tempo,
)

from .base_tool import BaseTool


@dataclass(frozen=True)
class _PartSelection:
    part: stream.Stream
    name: str
    index: int


class ScoreSliceTool(BaseTool):
    """Return model-friendly notation evidence without changing the score."""

    MAX_MEASURES = 32
    DEFAULT_MEASURES = 8
    DEFAULT_MAX_EVENTS = 400
    MAX_EVENTS = 4000

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Inspect selected parts and measures with stable musical locators."""
        score_id = kwargs.get("score_id", "")
        start_measure = kwargs.get("start_measure", 1)
        end_measure = kwargs.get("end_measure")
        requested_parts = kwargs.get("parts")
        include_rests = kwargs.get("include_rests", True)
        include_lyrics = kwargs.get("include_lyrics", True)
        include_annotations = kwargs.get("include_annotations", True)
        max_events = kwargs.get("max_events", self.DEFAULT_MAX_EVENTS)
        detail = kwargs.get("detail", "compact")

        error = self.validate_inputs(**kwargs)
        if error:
            return self.create_error_response(error)

        if end_measure is None:
            end_measure = start_measure + self.DEFAULT_MEASURES - 1

        score = self.get_score(score_id)
        selected_parts = self._select_parts(score, requested_parts)
        part_results: list[dict[str, Any]] = []
        returned_measure_numbers: set[int] = set()

        with self.error_handling(f"Score slice for '{score_id}'"):
            selected_ranges = [
                (
                    selected,
                    self._measures_in_range(selected.part, start_measure, end_measure),
                )
                for selected in selected_parts
            ]
            total_event_count = sum(
                len(self._eligible_events(measure, include_rests))
                for _selected, measures in selected_ranges
                for measure in measures
            )
            if total_event_count > max_events:
                return self.create_error_response(
                    (
                        f"Requested slice contains {total_event_count} events, "
                        f"exceeding max_events={max_events}; narrow the measure/part "
                        "selection or explicitly raise max_events"
                    ),
                    details={
                        "score_id": score_id,
                        "read_only": True,
                        "requested_range": {
                            "start": start_measure,
                            "end": end_measure,
                        },
                        "event_count": total_event_count,
                        "max_events": max_events,
                    },
                )

            for selected_number, (selected, selected_measures) in enumerate(
                selected_ranges, start=1
            ):
                measure_results: list[dict[str, Any]] = []
                for measure in selected_measures:
                    measure_number = self._measure_number(measure)
                    returned_measure_numbers.add(measure_number)
                    serialized_events: list[dict[str, Any]] = []
                    measure_event_count = 0

                    for event_index, event in enumerate(
                        self._eligible_events(measure, include_rests), start=1
                    ):
                        measure_event_count += 1
                        serialized_events.append(
                            self._serialize_event(
                                selected,
                                measure,
                                event,
                                event_index,
                                include_lyrics,
                                detail,
                            )
                        )

                    result = {
                        "number": measure_number,
                        "duration": self._fraction_string(
                            measure.duration.quarterLength
                        ),
                        "context": self._measure_context(measure),
                        "events": serialized_events,
                    }
                    if measure.numberSuffix:
                        result["label"] = self._measure_label(measure)
                    if detail == "full":
                        result.update(
                            {
                                "offset": self._float_offset(
                                    measure, selected.part
                                ),
                                "offset_fraction": self._fraction_string(
                                    measure.getOffsetInHierarchy(selected.part)
                                ),
                                "duration_quarter": float(
                                    measure.duration.quarterLength
                                ),
                                "event_count": measure_event_count,
                            }
                        )
                    if include_annotations:
                        annotations = self._measure_annotations(measure, detail)
                        if annotations:
                            result["annotations"] = annotations
                    measure_results.append(result)

                part_result: dict[str, Any] = {
                    "part": selected.name,
                    "measures": measure_results,
                }
                if detail == "full":
                    part_result.update(
                        {
                            "part_index": selected.index,
                            "part_id": str(selected.part.id),
                            "measure_count": len(measure_results),
                        }
                    )
                part_results.append(part_result)
                self.report_progress(
                    selected_number / len(selected_parts),
                    f"Inspected {selected.name}",
                )

            if not returned_measure_numbers:
                return self.create_error_response(
                    f"No measures found in requested range {start_measure}-{end_measure}"
                )

            response = self.create_success_response(
                message=(
                    f"Returned score slice for measures {start_measure}-{end_measure} "
                    f"across {len(selected_parts)} part(s)"
                ),
                score_id=score_id,
                read_only=True,
                requested_range={"start": start_measure, "end": end_measure},
                returned_measures=sorted(returned_measure_numbers),
                selected_parts=[part.name for part in selected_parts],
                include_rests=include_rests,
                include_lyrics=include_lyrics,
                include_annotations=include_annotations,
                detail=detail,
                event_count=total_event_count,
                events_returned=total_event_count,
                events_truncated=False,
                max_events=max_events,
                parts=part_results,
            )
            source_context = self._native_source_context(
                score, start_measure, end_measure
            )
            if source_context:
                response["source_context"] = source_context
            return response

    def validate_inputs(self, **kwargs: Any) -> str | None:
        """Validate score, range, selectors, flags, and response bound."""
        score_id = kwargs.get("score_id", "")
        start_measure = kwargs.get("start_measure", 1)
        end_measure = kwargs.get("end_measure")
        parts = kwargs.get("parts")
        max_events = kwargs.get("max_events", self.DEFAULT_MAX_EVENTS)
        detail = kwargs.get("detail", "compact")

        error = self.check_score_exists(score_id)
        if error:
            return error
        score = self.get_score(score_id)
        if not isinstance(score, stream.Stream):
            return "score must be a music21 Stream"
        if isinstance(start_measure, bool) or not isinstance(start_measure, int):
            return "start_measure must be a non-negative integer"
        if start_measure < 0:
            return "start_measure must be a non-negative integer"
        if end_measure is not None and (
            isinstance(end_measure, bool) or not isinstance(end_measure, int)
        ):
            return "end_measure must be a non-negative integer or null"
        if end_measure is not None and end_measure < start_measure:
            return "end_measure must be greater than or equal to start_measure"
        if (
            end_measure is not None
            and end_measure - start_measure + 1 > self.MAX_MEASURES
        ):
            return f"A score slice can contain at most {self.MAX_MEASURES} measures"
        if parts is not None and not isinstance(parts, (str, list, tuple)):
            return "parts must be a part name or a list of names/one-based indexes"
        if isinstance(parts, (list, tuple)) and not parts:
            return "parts cannot be empty"
        for flag in ("include_rests", "include_lyrics", "include_annotations"):
            if not isinstance(kwargs.get(flag, True), bool):
                return f"{flag} must be a boolean"
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
            or not 1 <= max_events <= self.MAX_EVENTS
        ):
            return f"max_events must be an integer from 1 to {self.MAX_EVENTS}"
        if detail not in {"compact", "full"}:
            return "detail must be 'compact' or 'full'"
        try:
            self._select_parts(score, parts)
        except ValueError as exc:
            return str(exc)
        return None

    def _select_parts(
        self, score: stream.Stream, requested: Any
    ) -> list[_PartSelection]:
        raw_parts: list[stream.Stream] = (
            list(score.parts) if isinstance(score, stream.Score) else [score]
        )
        if not raw_parts:
            raise ValueError("score contains no parts")

        records: list[_PartSelection] = []
        name_counts: dict[str, int] = {}
        for index, part in enumerate(raw_parts, start=1):
            part_name = getattr(part, "partName", None)
            part_id = getattr(part, "id", None)
            base_name = str(part_name or part_id or f"Part {index}")
            if base_name in {"None", str(id(part))}:
                base_name = f"Part {index}"
            name_counts[base_name] = name_counts.get(base_name, 0) + 1
            count = name_counts[base_name]
            name = base_name if count == 1 else f"{base_name} {count}"
            records.append(_PartSelection(part=part, name=name, index=index))

        if requested is None:
            return records
        selectors: list[Any] = (
            [requested] if isinstance(requested, str) else list(requested)
        )
        lookup: dict[str, _PartSelection] = {}
        for part_record in records:
            lookup[part_record.name.casefold()] = part_record
            lookup[f"part {part_record.index}"] = part_record
            part_name = getattr(part_record.part, "partName", None)
            part_id = getattr(part_record.part, "id", None)
            if part_name:
                lookup.setdefault(str(part_name).casefold(), part_record)
            if part_id:
                lookup.setdefault(str(part_id).casefold(), part_record)

        selected: list[_PartSelection] = []
        seen: set[int] = set()
        for selector in selectors:
            selected_record: _PartSelection | None = None
            if isinstance(selector, int) and not isinstance(selector, bool):
                if 1 <= selector <= len(records):
                    selected_record = records[selector - 1]
            elif isinstance(selector, str) and selector.strip():
                selected_record = lookup.get(selector.strip().casefold())
            if selected_record is None:
                raise ValueError(f"Unknown part selector: {selector}")
            if selected_record.index not in seen:
                selected.append(selected_record)
                seen.add(selected_record.index)
        if not selected:
            raise ValueError("parts did not select any score parts")
        return selected

    @staticmethod
    def _measures_in_range(
        part: stream.Stream, start_measure: int, end_measure: int
    ) -> list[stream.Measure]:
        return [
            measure
            for measure in part.getElementsByClass(stream.Measure)
            if start_measure <= ScoreSliceTool._measure_number(measure) <= end_measure
        ]

    def _serialize_event(
        self,
        selected: _PartSelection,
        measure: stream.Measure,
        event: note.GeneralNote,
        event_index: int,
        include_lyrics: bool,
        detail: str,
    ) -> dict[str, Any]:
        voice = event.getContextByClass(stream.Voice)
        voice_id = "1" if voice is None or voice.id is None else str(voice.id)
        event_type = "rest"
        pitches: list[Any] = []
        if isinstance(event, note.Note):
            event_type = "note"
            pitches = [event.pitch.nameWithOctave]
        elif isinstance(event, chord.Chord):
            event_type = "chord"
            pitches = [pitch.nameWithOctave for pitch in event.pitches]
        elif isinstance(event, note.Unpitched):
            event_type = "unpitched"

        result: dict[str, Any] = {
            "locator": (
                f"{selected.name}:m{self._measure_label(measure)}:"
                f"v{voice_id}:o{self._fraction_string(event.getOffsetInHierarchy(measure))}"
            ),
            "voice": voice_id,
            "event_index": event_index,
            "type": event_type,
            "offset": self._fraction_string(
                event.getOffsetInHierarchy(measure)
            ),
            "duration": self._fraction_string(event.duration.quarterLength),
            "beat": self._safe_beat(event),
            "pitches": pitches,
        }
        tie_value = self._tie_type(event)
        if tie_value is not None:
            result["tie"] = tie_value
        tuplets = [
            {
                "actual": tuplet.numberNotesActual,
                "normal": tuplet.numberNotesNormal,
                "type": tuplet.type,
            }
            for tuplet in event.duration.tuplets
        ]
        if tuplets:
            result["tuplets"] = tuplets
        articulations = [
            articulation.__class__.__name__ for articulation in event.articulations
        ]
        if articulations:
            result["articulations"] = articulations
        event_expressions = [item.__class__.__name__ for item in event.expressions]
        if event_expressions:
            result["expressions"] = event_expressions
        spanners = self._event_spanners(event)
        if spanners:
            result["spanners"] = spanners
        if include_lyrics:
            lyrics = [self._serialize_lyric(lyric, detail) for lyric in event.lyrics]
            if lyrics:
                result["lyrics"] = lyrics
        if detail == "full":
            result.update(
                {
                    "part": selected.name,
                    "part_index": selected.index,
                    "measure": self._measure_number(measure),
                    "absolute_offset": self._float_offset(event, selected.part),
                    "absolute_offset_fraction": self._fraction_string(
                        event.getOffsetInHierarchy(selected.part)
                    ),
                    "offset_quarter": self._float_offset(event, measure),
                    "duration_quarter": float(event.duration.quarterLength),
                    "pitch_details": [
                        self._serialize_pitch(score_pitch)
                        for score_pitch in getattr(event, "pitches", ())
                    ],
                }
            )
        return result

    @staticmethod
    def _serialize_pitch(score_pitch: Any) -> dict[str, Any]:
        return {
            "name": score_pitch.nameWithOctave,
            "step": score_pitch.step,
            "alter": float(score_pitch.accidental.alter)
            if score_pitch.accidental is not None
            else 0.0,
            "octave": score_pitch.octave,
            "midi": score_pitch.midi,
        }

    @staticmethod
    def _serialize_lyric(lyric: note.Lyric, detail: str) -> dict[str, Any]:
        components = getattr(lyric, "components", None) or []
        identifier = lyric.identifier
        verse: int | str = lyric.number or 1
        if (
            isinstance(identifier, str)
            and identifier.strip()
            and identifier.strip() != str(lyric.number)
        ):
            verse = identifier.strip()
        result: dict[str, Any] = {
            "verse": str(verse),
            "text": lyric.text,
            "syllabic": lyric.syllabic,
        }
        if detail == "full" or lyric.rawText != lyric.text:
            result["raw_text"] = lyric.rawText
        if components:
            result["components"] = [
                {
                    "text": component.text,
                    "syllabic": component.syllabic,
                    "elision_before": component.elisionBefore,
                }
                for component in components
            ]
        return result

    @staticmethod
    def _native_source_context(
        score: stream.Stream, start_measure: int, end_measure: int
    ) -> list[dict[str, Any]]:
        editorial = getattr(score, "editorial", None)
        if editorial is None:
            return []
        try:
            context = editorial.get("music21_mcp_import_context", [])
        except (AttributeError, TypeError):
            return []
        return [
            item
            for item in context
            if isinstance(item, dict)
            and isinstance(item.get("measure"), int)
            and start_measure <= item["measure"] <= end_measure
        ]

    @staticmethod
    def _eligible_events(
        measure: stream.Measure, include_rests: bool
    ) -> list[note.GeneralNote]:
        """Return events in musical-time order across nested voices."""
        events = [
            event
            for event in measure.recurse().notesAndRests
            if include_rests or not isinstance(event, note.Rest)
        ]
        events.sort(
            key=lambda event: (
                float(event.getOffsetInHierarchy(measure)),
                str(
                    getattr(event.getContextByClass(stream.Voice), "id", None)
                    or "1"
                ),
                event.classSortOrder,
            )
        )
        return events

    def _measure_context(self, measure: stream.Measure) -> dict[str, Any]:
        time_signature = measure.timeSignature or measure.getContextByClass(
            meter.TimeSignature
        )
        key_signature = measure.keySignature or measure.getContextByClass(
            key.KeySignature
        )
        current_clef = measure.clef or measure.getContextByClass(clef.Clef)
        direct_tempos = list(measure.recurse().getElementsByClass(tempo.MetronomeMark))
        current_tempo = (
            direct_tempos[0]
            if direct_tempos
            else measure.getContextByClass(tempo.MetronomeMark)
        )
        context: dict[str, Any] = {
            "time_signature": (
                time_signature.ratioString if time_signature is not None else None
            ),
            "key_signature": self._serialize_key_signature(key_signature),
            "clef": self._serialize_clef(current_clef),
            "tempo": self._serialize_metronome(current_tempo),
        }
        try:
            context["bar_duration"] = float(measure.barDuration.quarterLength)
        except (AttributeError, TypeError):
            context["bar_duration"] = None
        return context

    def _measure_annotations(
        self, measure: stream.Measure, detail: str
    ) -> list[dict[str, Any]]:
        annotations: list[dict[str, Any]] = []
        for item in measure.recurse():
            value = self._serialize_annotation(item, measure, detail)
            if value is not None:
                annotations.append(value)
        if measure.leftBarline is not None:
            annotations.append(self._serialize_barline(measure.leftBarline, "left"))
        if measure.rightBarline is not None:
            annotations.append(self._serialize_barline(measure.rightBarline, "right"))
        annotations.sort(key=lambda value: (value.get("offset", 0.0), value["type"]))
        return annotations

    def _serialize_annotation(
        self, item: Any, measure: stream.Measure, detail: str
    ) -> dict[str, Any] | None:
        annotation: dict[str, Any] | None = None
        if isinstance(item, meter.TimeSignature):
            annotation = {"type": "time_signature", "value": item.ratioString}
        elif isinstance(item, key.Key):
            annotation = {
                "type": "key",
                "tonic": item.tonic.name,
                "mode": item.mode,
                "sharps": item.sharps,
            }
        elif isinstance(item, key.KeySignature):
            annotation = {"type": "key_signature", "sharps": item.sharps}
        elif isinstance(item, clef.Clef):
            annotation = {"type": "clef", **self._serialize_clef(item)}
        elif isinstance(item, tempo.MetricModulation):
            annotation = {
                "type": "metric_modulation",
                "old": self._serialize_metronome(item.oldMetronome),
                "new": self._serialize_metronome(item.newMetronome),
                "maintain_beat": item.maintainBeat,
            }
        elif isinstance(item, tempo.MetronomeMark):
            annotation = {"type": "tempo", **self._serialize_metronome(item)}
        elif isinstance(item, tempo.TempoText):
            annotation = {"type": "tempo_text", "text": item.text}
        elif isinstance(item, dynamics.Dynamic):
            annotation = {"type": "dynamic", "value": item.value}
        elif isinstance(item, expressions.RehearsalMark):
            annotation = {"type": "rehearsal_mark", "text": item.content}
        elif isinstance(item, expressions.TextExpression):
            annotation = {"type": "text", "text": item.content}
        elif isinstance(item, harmony.ChordSymbol):
            annotation = {"type": "chord_symbol", "figure": item.figure}
        if annotation is None:
            return None
        annotation["offset"] = self._float_offset(item, measure)
        if detail == "full":
            annotation["offset_fraction"] = self._fraction_string(
                item.getOffsetInHierarchy(measure)
            )
        return annotation

    @staticmethod
    def _serialize_metronome(mark: tempo.MetronomeMark | None) -> Any:
        if mark is None:
            return None
        try:
            quarter_bpm = mark.getQuarterBPM()
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            quarter_bpm = None
        return {
            "number": mark.number,
            "number_sounding": getattr(mark, "numberSounding", None),
            "number_implicit": getattr(mark, "numberImplicit", None),
            "quarter_bpm": quarter_bpm,
            "text": mark.text,
            "referent_duration": float(mark.referent.quarterLength)
            if mark.referent is not None
            else None,
        }

    @staticmethod
    def _serialize_key_signature(signature: key.KeySignature | None) -> Any:
        if signature is None:
            return None
        result: dict[str, Any] = {"sharps": signature.sharps}
        if isinstance(signature, key.Key):
            result.update({"tonic": signature.tonic.name, "mode": signature.mode})
        return result

    @staticmethod
    def _serialize_clef(current_clef: clef.Clef | None) -> Any:
        if current_clef is None:
            return None
        return {
            "name": current_clef.__class__.__name__,
            "sign": current_clef.sign,
            "line": current_clef.line,
            "octave_change": current_clef.octaveChange,
        }

    @staticmethod
    def _serialize_barline(value: bar.Barline, location: str) -> dict[str, Any]:
        return {
            "type": "barline",
            "location": location,
            "value": value.type,
            "offset": 0.0 if location == "left" else None,
        }

    @staticmethod
    def _event_spanners(event: note.GeneralNote) -> list[dict[str, str]]:
        values: list[dict[str, str]] = []
        for item in event.getSpannerSites():
            role = "continue"
            if item.isFirst(event):
                role = "start"
            elif item.isLast(event):
                role = "stop"
            values.append({"type": item.__class__.__name__, "role": role})
        return values

    @staticmethod
    def _tie_type(event: note.GeneralNote) -> str | list[str] | None:
        if isinstance(event, note.Note):
            return event.tie.type if event.tie is not None else None
        if isinstance(event, chord.Chord):
            return [
                chord_note.tie.type if chord_note.tie is not None else "none"
                for chord_note in event.notes
            ]
        return None

    @staticmethod
    def _safe_beat(event: note.GeneralNote) -> float | None:
        try:
            return float(event.beat)
        except (AttributeError, TypeError, ZeroDivisionError):
            return None

    @staticmethod
    def _measure_number(measure: stream.Measure) -> int:
        return int(measure.number or 0)

    @staticmethod
    def _measure_label(measure: stream.Measure) -> str:
        suffix = measure.numberSuffix or ""
        return f"{ScoreSliceTool._measure_number(measure)}{suffix}"

    @staticmethod
    def _float_offset(item: Any, container: stream.Stream) -> float:
        return float(item.getOffsetInHierarchy(container))

    @staticmethod
    def _fraction_string(value: Any) -> str:
        numerator = getattr(value, "numerator", None)
        denominator = getattr(value, "denominator", None)
        if numerator is not None and denominator is not None:
            return f"{numerator}/{denominator}"
        try:
            fraction = Fraction(str(value)).limit_denominator()
        except (TypeError, ValueError, ZeroDivisionError):
            return str(value)
        return f"{fraction.numerator}/{fraction.denominator}"
