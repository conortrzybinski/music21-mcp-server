"""Prosody-aware lyric underlay for an existing melody."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from music21 import meter, note, stream

from .base_tool import BaseTool

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Syllable:
    """A syllable plus the word-level information needed for prosody."""

    text: str
    word_index: int
    syllable_index: int
    syllables_in_word: int
    stressed: bool

    @property
    def word_final(self) -> bool:
        return self.syllable_index == self.syllables_in_word - 1

    @property
    def syllabic(self) -> Literal["single", "begin", "end", "middle"]:
        if self.syllables_in_word == 1:
            return "single"
        if self.syllable_index == 0:
            return "begin"
        if self.word_final:
            return "end"
        return "middle"


class TextUnderlayTool(BaseTool):
    """Fit text to a melody with bounded melismas and simple prosody."""

    _WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*(?:-[^\W\d_]+)*", re.UNICODE)
    _VOWELS = {
        "english": "aeiouy",
        "french": "aeiouyàâæéèêëîïôœùûüÿ",
        "german": "aeiouyäöü",
        "italian": "aeiouàèéìíîòóùú",
        "latin": "aeiouy",
        "spanish": "aeiouyáéíóúü",
    }
    _DIPHTHONGS = {
        "english": {
            "ai",
            "ay",
            "ea",
            "ee",
            "ei",
            "ey",
            "ie",
            "oa",
            "oe",
            "oo",
            "ou",
            "ow",
            "oy",
            "ue",
            "ui",
        },
        "french": {"ai", "au", "eau", "ei", "eu", "oe", "oi", "ou", "ui"},
        "german": {"au", "ai", "ei", "eu", "äu", "ie"},
        "italian": {"ai", "au", "ei", "eu", "oi", "ui"},
        "latin": {"ae", "au", "eu", "oe"},
        "spanish": {
            "ai",
            "au",
            "ei",
            "eu",
            "ia",
            "ie",
            "io",
            "oi",
            "ou",
            "ua",
            "ue",
            "ui",
            "uo",
        },
    }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Apply the supplied text to the first (melody) part of a score."""
        score_id = kwargs.get("score_id", "")
        text = kwargs.get("text", "")
        language = kwargs.get("language", "english")
        melisma_limit = kwargs.get("melisma_limit", 3)
        prefer_stressed_on_strong = kwargs.get("prefer_stressed_on_strong", True)

        error = self.validate_inputs(**kwargs)
        if error:
            return self.create_error_response(error)

        with self.error_handling(f"Text underlay for '{score_id}'"):
            melody = self._melody_stream(self.get_score(score_id))
            melody_notes = self._extract_notes(melody)
            if not melody_notes:
                return self.create_error_response("No melody notes found in score")

            self.report_progress(0.2, "Syllabifying text")
            result = self.apply_underlay(
                melody_notes,
                text,
                language=language,
                melisma_limit=melisma_limit,
                prefer_stressed_on_strong=prefer_stressed_on_strong,
            )
            self.report_progress(1.0, "Text underlay complete")
            return self.create_success_response(
                message=f"Applied text underlay to {len(melody_notes)} melody notes",
                score_id=score_id,
                syllable_map=result["syllable_map"],
                warnings=result["warnings"],
            )

    def validate_inputs(self, **kwargs: Any) -> str | None:
        """Validate score, text, language, and melisma options."""
        score_id = kwargs.get("score_id", "")
        text = kwargs.get("text", "")
        language = kwargs.get("language", "english")
        melisma_limit = kwargs.get("melisma_limit", 3)
        prefer_stressed = kwargs.get("prefer_stressed_on_strong", True)

        error = self.check_score_exists(score_id)
        if error:
            return error
        if not isinstance(text, str) or not text.strip():
            return "text must be a non-empty string"
        if not isinstance(language, str) or language not in self._VOWELS:
            return f"Unsupported language: {language}"
        if (
            isinstance(melisma_limit, bool)
            or not isinstance(melisma_limit, int)
            or melisma_limit < 1
        ):
            return "melisma_limit must be a positive integer"
        if not isinstance(prefer_stressed, bool):
            return "prefer_stressed_on_strong must be a boolean"
        return None

    def apply_underlay(
        self,
        melody_notes: Sequence[note.Note],
        text: str,
        *,
        language: str = "english",
        melisma_limit: int = 3,
        prefer_stressed_on_strong: bool = True,
    ) -> dict[str, Any]:
        """Apply lyrics to a concrete note sequence and return its mapping."""
        syllables = self._syllabify_text(text, language)
        warnings: list[str] = []
        if not syllables:
            return {"syllable_map": [], "warnings": ["Text contained no words"]}

        usable_notes = list(melody_notes)
        groups: list[int]
        if len(syllables) > len(usable_notes):
            omitted = len(syllables) - len(usable_notes)
            warnings.append(
                f"Text has {len(syllables)} syllables but only {len(usable_notes)} "
                f"notes; truncated {omitted} syllables"
            )
            syllables = syllables[: len(usable_notes)]
            groups = [1] * len(syllables)
        else:
            capacity = len(syllables) * melisma_limit
            if len(usable_notes) > capacity:
                unassigned = len(usable_notes) - capacity
                warnings.append(
                    f"Melisma limit leaves {unassigned} trailing notes without lyrics"
                )
                usable_notes = usable_notes[:capacity]
            groups = self._allocate_notes(
                syllables,
                usable_notes,
                melisma_limit,
                prefer_stressed_on_strong,
            )

        for melody_note in melody_notes:
            melody_note.lyrics = []

        syllable_map: list[dict[str, Any]] = []
        note_index = 0
        for syllable, group_size in zip(syllables, groups, strict=True):
            lyric_note = usable_notes[note_index]
            lyric_note.addLyric(syllable.text, lyricNumber=1)
            lyric_note.lyrics[0].syllabic = syllable.syllabic

            for melisma_index in range(group_size):
                melody_note = usable_notes[note_index + melisma_index]
                syllable_map.append(
                    {
                        "syllable": syllable.text,
                        "note_index": note_index + melisma_index,
                        "pitch": melody_note.pitch.nameWithOctave,
                        "beat": self._beat(melody_note),
                        "measure": melody_note.measureNumber,
                        "word_index": syllable.word_index,
                        "syllable_index": syllable.syllable_index,
                        "melisma": melisma_index > 0,
                    }
                )
            note_index += group_size

        return {"syllable_map": syllable_map, "warnings": warnings}

    def _melody_stream(self, score: Any) -> stream.Stream:
        """Select the top part when a score contains multiple parts."""
        if isinstance(score, stream.Score) and score.parts:
            return score.parts[0]
        if isinstance(score, stream.Stream):
            return score
        raise TypeError("Stored score is not a music21 stream")

    @staticmethod
    def _extract_notes(melody: stream.Stream) -> list[note.Note]:
        return [
            element
            for element in melody.recurse().notes
            if isinstance(element, note.Note)
        ]

    def _syllabify_text(self, text: str, language: str) -> list[_Syllable]:
        """Use deterministic language-aware rules without an external dictionary."""
        result: list[_Syllable] = []
        for word_index, match in enumerate(self._WORD_RE.finditer(text)):
            word = match.group(0)
            if "-" in word:
                pieces = [piece for piece in word.split("-") if piece]
            else:
                pieces = self._syllabify_word(word, language)
            stress_index = self._stress_index(word, pieces, language)
            for syllable_index, piece in enumerate(pieces):
                result.append(
                    _Syllable(
                        text=piece,
                        word_index=word_index,
                        syllable_index=syllable_index,
                        syllables_in_word=len(pieces),
                        stressed=syllable_index == stress_index,
                    )
                )
        return result

    def _syllabify_word(self, word: str, language: str) -> list[str]:
        """Split before an onset consonant and preserve common diphthongs."""
        lowered = word.casefold()
        vowels = self._VOWELS[language]
        diphthongs = self._DIPHTHONGS[language]
        nuclei: list[tuple[int, int]] = []
        index = 0
        while index < len(lowered):
            if lowered[index] not in vowels:
                index += 1
                continue
            start = index
            end = index + 1
            while end < len(lowered) and lowered[end] in vowels:
                candidate = lowered[start : end + 1]
                if candidate not in diphthongs:
                    break
                end += 1
            nuclei.append((start, end))
            index = end

        if language == "english" and len(nuclei) > 1 and lowered.endswith("e"):
            nuclei.pop()
        if len(nuclei) <= 1:
            return [word]

        boundaries: list[int] = []
        for (_, previous_end), (next_start, _) in zip(nuclei, nuclei[1:], strict=False):
            consonant_count = next_start - previous_end
            if consonant_count <= 1:
                boundaries.append(previous_end)
            else:
                boundaries.append(next_start - 1)

        pieces: list[str] = []
        start = 0
        for boundary in boundaries:
            if boundary > start:
                pieces.append(word[start:boundary])
                start = boundary
        pieces.append(word[start:])
        return [piece for piece in pieces if piece]

    @staticmethod
    def _stress_index(word: str, pieces: Sequence[str], language: str) -> int:
        if len(pieces) <= 1:
            return 0
        if language in {"french"}:
            return len(pieces) - 1
        if language in {"italian", "latin"}:
            return len(pieces) - 2
        if language == "spanish":
            return (
                len(pieces) - 2 if word.casefold()[-1] in "aeiouns" else len(pieces) - 1
            )
        return 0

    def _allocate_notes(
        self,
        syllables: Sequence[_Syllable],
        melody_notes: Sequence[note.Note],
        melisma_limit: int,
        prefer_stressed_on_strong: bool,
    ) -> list[int]:
        """Find a low-cost monotonic syllable grouping with dynamic programming."""
        note_count = len(melody_notes)
        syllable_count = len(syllables)
        states: dict[tuple[int, int], tuple[float, list[int]]] = {(0, 0): (0.0, [])}
        long_note = sorted(float(n.quarterLength) for n in melody_notes)[
            len(melody_notes) // 2
        ]

        for syllable_index, syllable in enumerate(syllables):
            next_states: dict[tuple[int, int], tuple[float, list[int]]] = {}
            for (_, notes_used), (cost, allocation) in states.items():
                remaining_syllables = syllable_count - syllable_index - 1
                for group_size in range(1, melisma_limit + 1):
                    end = notes_used + group_size
                    if end > note_count or note_count - end < remaining_syllables:
                        continue
                    if note_count - end > remaining_syllables * melisma_limit:
                        continue
                    group = melody_notes[notes_used:end]
                    # Prefer extending later syllables, especially the final one.
                    group_cost = (
                        0.15 + 0.02 * (syllable_count - syllable_index - 1)
                    ) * (group_size - 1)
                    if prefer_stressed_on_strong and syllable.stressed:
                        group_cost += -2.0 if self._is_strong(group[0]) else 1.0
                    if syllable.word_final:
                        if float(group[-1].quarterLength) >= long_note:
                            group_cost -= 0.5
                        if end == note_count:
                            group_cost -= 0.75
                    state_key = (syllable_index + 1, end)
                    candidate = (cost + group_cost, [*allocation, group_size])
                    if (
                        state_key not in next_states
                        or candidate[0] < next_states[state_key][0]
                    ):
                        next_states[state_key] = candidate
            states = next_states

        final = states.get((syllable_count, note_count))
        if (
            final is None
        ):  # Defensive fallback; validated bounds should make this unreachable.
            return [1] * syllable_count
        return final[1]

    @staticmethod
    def _beat(melody_note: note.Note) -> float:
        try:
            return float(melody_note.beat)
        except Exception:
            return float(melody_note.offset % 4) + 1.0

    def _is_strong(self, melody_note: note.Note) -> bool:
        beat = self._beat(melody_note)
        time_signature = melody_note.getContextByClass(meter.TimeSignature)
        if time_signature and time_signature.numerator == 4:
            return beat in {1.0, 3.0}
        if time_signature and time_signature.numerator == 3:
            return beat == 1.0
        if time_signature and time_signature.numerator in {6, 9, 12}:
            return beat in {1.0, 4.0, 7.0, 10.0}
        return beat == 1.0
