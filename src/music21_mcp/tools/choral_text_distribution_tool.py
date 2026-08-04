"""Distribute lyric text across the parts of a choral score."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from music21 import meter, note, pitch, stream

from .base_tool import BaseTool
from .text_underlay_tool import TextUnderlayTool

if TYPE_CHECKING:
    from collections.abc import MutableMapping


class ChoralTextDistributionTool(BaseTool):
    """Apply independent or shared text underlay to two through eight voices."""

    VOICE_RANGES = {
        "soprano": ("C4", "A5"),
        "alto": ("F3", "D5"),
        "tenor": ("C3", "G4"),
        "bass": ("E2", "C4"),
    }
    VALID_ENTRY_SCHEMES = {"staggered", "simultaneous", "imitative"}

    def __init__(self, score_manager: MutableMapping[str, Any]):
        super().__init__(score_manager)
        self.underlay_tool = TextUnderlayTool(score_manager)

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Distribute text and write lyrics directly to each selected part."""
        score_id = kwargs.get("score_id", "")
        text = kwargs.get("text", "")
        supplied_assignments = kwargs.get("voice_assignments")
        entry_scheme = kwargs.get("entry_scheme", "staggered")
        stagger_offset = kwargs.get("stagger_offset_measures", 2)

        error = self.validate_inputs(**kwargs)
        if error:
            return self.create_error_response(error)

        with self.error_handling(f"Choral text distribution for '{score_id}'"):
            score = self.get_score(score_id)
            parts = list(score.parts)
            part_names = self._part_names(parts)

            self.report_progress(0.1, "Assigning text to voices")
            if supplied_assignments:
                assignments = self._resolve_assignments(
                    supplied_assignments, parts, part_names
                )
            elif entry_scheme == "imitative":
                assignments = dict.fromkeys(part_names, text)
            else:
                assignments = dict(
                    zip(part_names, self._split_text(text, len(parts)), strict=True)
                )

            entry_points = self._entry_points(
                list(assignments), part_names, entry_scheme, stagger_offset
            )
            warnings: list[str] = []
            syllable_maps: dict[str, list[dict[str, Any]]] = {}

            for index, (part, part_name) in enumerate(
                zip(parts, part_names, strict=True)
            ):
                if part_name not in assignments:
                    continue
                voice_text = assignments[part_name]
                start_measure = entry_points[part_name]
                target_notes = self._notes_from_measure(part, start_measure)
                if not voice_text.strip():
                    warnings.append(f"{part_name} received no text")
                    syllable_maps[part_name] = []
                    continue
                if not target_notes:
                    warnings.append(
                        f"{part_name} has no notes at or after measure {start_measure}"
                    )
                    syllable_maps[part_name] = []
                    continue

                result = self.underlay_tool.apply_underlay(target_notes, voice_text)
                syllable_maps[part_name] = result["syllable_map"]
                warnings.extend(
                    f"{part_name}: {warning}" for warning in result["warnings"]
                )
                warnings.extend(
                    self._range_warnings(part_name, index, len(parts), target_notes)
                )
                self.report_progress(
                    0.2 + 0.7 * ((index + 1) / len(parts)),
                    f"Underlaid {part_name}",
                )

            self.report_progress(1.0, "Choral text distribution complete")
            return self.create_success_response(
                message=f"Distributed text across {len(assignments)} voices",
                score_id=score_id,
                voice_assignments=assignments,
                entry_points=entry_points,
                syllable_maps=syllable_maps,
                warnings=warnings,
            )

    def validate_inputs(self, **kwargs: Any) -> str | None:
        """Validate part count, entry scheme, and optional voice mapping."""
        score_id = kwargs.get("score_id", "")
        text = kwargs.get("text", "")
        assignments = kwargs.get("voice_assignments")
        entry_scheme = kwargs.get("entry_scheme", "staggered")
        stagger_offset = kwargs.get("stagger_offset_measures", 2)

        error = self.check_score_exists(score_id)
        if error:
            return error
        score = self.get_score(score_id)
        if not isinstance(score, stream.Score):
            return "score must be a multi-part music21 Score"
        if not 2 <= len(score.parts) <= 8:
            return "score must contain between 2 and 8 parts"
        if not isinstance(text, str) or not text.strip():
            return "text must be a non-empty string"
        if (
            not isinstance(entry_scheme, str)
            or entry_scheme not in self.VALID_ENTRY_SCHEMES
        ):
            return (
                f"Invalid entry_scheme: {entry_scheme}. Choose from: "
                f"{', '.join(sorted(self.VALID_ENTRY_SCHEMES))}"
            )
        if (
            isinstance(stagger_offset, bool)
            or not isinstance(stagger_offset, int)
            or stagger_offset < 0
        ):
            return "stagger_offset_measures must be a non-negative integer"
        if assignments is not None:
            if not isinstance(assignments, dict) or not assignments:
                return "voice_assignments must be a non-empty mapping"
            if not all(
                isinstance(name, str) and isinstance(value, str) and value.strip()
                for name, value in assignments.items()
            ):
                return "voice_assignments must map part names to non-empty text"
            try:
                self._resolve_assignments(
                    assignments, list(score.parts), self._part_names(list(score.parts))
                )
            except ValueError as exc:
                return str(exc)
        return None

    @staticmethod
    def _part_names(parts: list[stream.Part]) -> list[str]:
        """Return stable, unique display names for score parts."""
        names: list[str] = []
        counts: dict[str, int] = {}
        for index, part in enumerate(parts):
            base = str(part.partName or part.id or f"Part {index + 1}")
            if base == str(id(part)) or base == "None":
                base = f"Part {index + 1}"
            counts[base] = counts.get(base, 0) + 1
            names.append(base if counts[base] == 1 else f"{base} {counts[base]}")
        return names

    def _resolve_assignments(
        self,
        supplied: dict[str, str],
        parts: list[stream.Part],
        part_names: list[str],
    ) -> dict[str, str]:
        """Resolve user names case-insensitively against display names and part IDs."""
        lookup: dict[str, str] = {name.casefold(): name for name in part_names}
        for part, display_name in zip(parts, part_names, strict=True):
            if part.partName:
                lookup[str(part.partName).casefold()] = display_name
            if part.id:
                lookup[str(part.id).casefold()] = display_name

        resolved: dict[str, str] = {}
        for supplied_name, voice_text in supplied.items():
            canonical = lookup.get(supplied_name.casefold())
            if canonical is None:
                raise ValueError(
                    f"Voice assignment refers to unknown part: {supplied_name}"
                )
            if canonical in resolved:
                raise ValueError(f"Duplicate voice assignment for part: {canonical}")
            resolved[canonical] = voice_text
        return resolved

    @staticmethod
    def _split_text(text: str, part_count: int) -> list[str]:
        """Split words into contiguous, near-equal sections."""
        words = text.split()
        base, remainder = divmod(len(words), part_count)
        sections: list[str] = []
        cursor = 0
        for index in range(part_count):
            size = base + (1 if index < remainder else 0)
            sections.append(" ".join(words[cursor : cursor + size]))
            cursor += size
        return sections

    @staticmethod
    def _entry_points(
        assigned_names: list[str],
        all_part_names: list[str],
        entry_scheme: str,
        stagger_offset: int,
    ) -> dict[str, int]:
        if entry_scheme == "simultaneous":
            return dict.fromkeys(assigned_names, 1)
        return {
            name: 1 + all_part_names.index(name) * stagger_offset
            for name in assigned_names
        }

    @staticmethod
    def _notes_from_measure(part: stream.Part, start_measure: int) -> list[note.Note]:
        """Select notes using measure metadata, falling back to metric offsets."""
        time_signature = part.recurse().getElementsByClass(meter.TimeSignature).first()
        bar_length = (
            float(time_signature.barDuration.quarterLength) if time_signature else 4.0
        )
        selected: list[note.Note] = []
        for element in part.recurse().notes:
            if not isinstance(element, note.Note):
                continue
            measure_number = element.measureNumber
            if measure_number is None:
                offset = float(element.getOffsetInHierarchy(part))
                measure_number = int(offset // bar_length) + 1
            if measure_number >= start_measure:
                selected.append(element)
        return selected

    def _range_warnings(
        self,
        part_name: str,
        part_index: int,
        part_count: int,
        part_notes: list[note.Note],
    ) -> list[str]:
        """Report notes outside conventional SATB ranges without changing pitches."""
        voice = self._voice_type(part_name, part_index, part_count)
        if voice is None:
            return []
        low_name, high_name = self.VOICE_RANGES[voice]
        low = pitch.Pitch(low_name).midi
        high = pitch.Pitch(high_name).midi
        outside = [n for n in part_notes if not low <= n.pitch.midi <= high]
        if not outside:
            return []
        return [
            f"{part_name} has {len(outside)} notes outside the conventional "
            f"{voice} range {low_name}-{high_name}"
        ]

    @staticmethod
    def _voice_type(part_name: str, part_index: int, part_count: int) -> str | None:
        lowered = part_name.casefold()
        for voice in ("soprano", "alto", "tenor", "bass"):
            if voice in lowered or lowered == voice[0]:
                return voice
        if part_count == 4:
            return ("soprano", "alto", "tenor", "bass")[part_index]
        return None
