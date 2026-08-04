"""Read-only structural audit of lyrics already attached to a score."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from music21 import chord, note, spanner, stream

from .base_tool import BaseTool


@dataclass(frozen=True)
class _SelectedPart:
    """A score part plus its stable response identity."""

    part: stream.Stream
    name: str
    index: int


@dataclass(frozen=True)
class _PitchedEvent:
    """Internal note/chord representation used for coverage checks."""

    element: note.GeneralNote
    locator: dict[str, Any]
    verses: frozenset[str]
    texted_verses: frozenset[str]


class LyricAuditTool(BaseTool):
    """Audit lyric structure and coverage without changing the stored score."""

    SUPPORTED_LANGUAGES = {
        "english",
        "french",
        "german",
        "italian",
        "latin",
        "spanish",
    }
    VALID_SYLLABIC_STATES = {"single", "begin", "middle", "end"}

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Inspect existing lyrics and return evidence, observations, and patches."""
        score_id = kwargs.get("score_id", "")
        requested_parts = kwargs.get("parts")
        language = kwargs.get("language", "latin")
        requested_verse = kwargs.get("verse")
        include_lyric_events = kwargs.get("include_lyric_events", False)
        include_word_details = kwargs.get("include_word_details", False)

        error = self.validate_inputs(**kwargs)
        if error:
            return self.create_error_response(error)

        with self.error_handling(f"Lyric audit for '{score_id}'"):
            selected_parts = self._select_parts(
                self.get_score(score_id), requested_parts
            )
            verse_filter = self._normalize_requested_verse(requested_verse)
            self.report_progress(0.1, "Extracting lyric events")

            lyric_events: list[dict[str, Any]] = []
            pitched_by_part: dict[str, list[_PitchedEvent]] = {}
            available_verses: dict[str, list[str]] = {}
            for part_number, selected in enumerate(selected_parts, start=1):
                part_events, pitched_events, verses = self._extract_part(
                    selected, verse_filter
                )
                lyric_events.extend(part_events)
                pitched_by_part[selected.name] = pitched_events
                available_verses[selected.name] = self._sort_verses(verses)
                self.report_progress(
                    0.1 + 0.35 * (part_number / len(selected_parts)),
                    f"Extracted {selected.name}",
                )

            issues, proposed_patches = self._audit_lyric_events(lyric_events)
            reconstructed = self._reconstruct_text(lyric_events, issues)
            self.report_progress(0.6, "Checking coverage and lyric continuity")

            coverage, gap_observations = self._coverage_stats(
                selected_parts,
                pitched_by_part,
                lyric_events,
                reconstructed,
                available_verses,
                verse_filter,
            )
            observations = [
                *gap_observations,
                *self._verse_observations(available_verses, coverage),
                *self._cross_part_observations(reconstructed),
            ]
            finding_summary = self._finding_summary(
                issues, observations, proposed_patches
            )
            response_reconstruction = (
                reconstructed
                if include_word_details
                else self._compact_reconstruction(reconstructed)
            )

            self.report_progress(1.0, "Lyric audit complete")
            response = self.create_success_response(
                message=(
                    f"Audited {len(lyric_events)} lyric events across "
                    f"{len(selected_parts)} part(s)"
                ),
                score_id=score_id,
                read_only=True,
                language=language,
                verse=verse_filter,
                selected_parts=[part.name for part in selected_parts],
                available_verses=available_verses,
                coverage_stats=coverage,
                reconstructed_text=response_reconstruction,
                word_details_included=include_word_details,
                lyric_event_count=len(lyric_events),
                lyric_events_included=include_lyric_events,
                finding_summary=finding_summary,
                issues=issues,
                observations=observations,
                proposed_patches=proposed_patches,
            )
            if include_lyric_events:
                response["lyric_events"] = lyric_events
            return response

    def validate_inputs(self, **kwargs: Any) -> str | None:
        """Validate score, part selectors, language, and optional verse."""
        score_id = kwargs.get("score_id", "")
        language = kwargs.get("language", "latin")
        parts = kwargs.get("parts")
        verse = kwargs.get("verse")
        include_lyric_events = kwargs.get("include_lyric_events", False)
        include_word_details = kwargs.get("include_word_details", False)

        error = self.check_score_exists(score_id)
        if error:
            return error
        score = self.get_score(score_id)
        if not isinstance(score, stream.Stream):
            return "score must be a music21 Stream"
        if not isinstance(language, str) or language.casefold() not in (
            self.SUPPORTED_LANGUAGES
        ):
            return f"Unsupported language: {language}"
        if verse is not None and (
            isinstance(verse, bool)
            or not isinstance(verse, (int, str))
            or (isinstance(verse, int) and verse < 1)
            or (isinstance(verse, str) and not verse.strip())
        ):
            return "verse must be a positive integer or non-empty string"
        if parts is not None and not isinstance(parts, (str, list, tuple)):
            return "parts must be a part name or a list of names/one-based indexes"
        if isinstance(parts, (list, tuple)) and not parts:
            return "parts cannot be empty"
        if not isinstance(include_lyric_events, bool):
            return "include_lyric_events must be a boolean"
        if not isinstance(include_word_details, bool):
            return "include_word_details must be a boolean"
        try:
            self._select_parts(score, parts)
        except ValueError as exc:
            return str(exc)
        return None

    def _select_parts(
        self, score: stream.Stream, requested: Any
    ) -> list[_SelectedPart]:
        """Resolve optional names, IDs, or one-based indexes to score parts."""
        raw_parts: list[stream.Stream] = []
        if isinstance(score, stream.Score):
            raw_parts.extend(score.parts)
        else:
            raw_parts.append(score)
        if not raw_parts:
            raise ValueError("score contains no parts")

        names: list[str] = []
        counts: dict[str, int] = {}
        for index, part in enumerate(raw_parts, start=1):
            part_name = getattr(part, "partName", None)
            part_id = getattr(part, "id", None)
            base = str(part_name or part_id or f"Part {index}")
            if base in {"None", str(id(part))}:
                base = f"Part {index}"
            counts[base] = counts.get(base, 0) + 1
            names.append(base if counts[base] == 1 else f"{base} {counts[base]}")

        records = [
            _SelectedPart(part=part, name=name, index=index)
            for index, (part, name) in enumerate(
                zip(raw_parts, names, strict=True), start=1
            )
        ]
        if requested is None:
            return records
        selectors: list[Any] = (
            [requested] if isinstance(requested, str) else list(requested)
        )

        lookup: dict[str, _SelectedPart] = {}
        for lookup_record in records:
            lookup[lookup_record.name.casefold()] = lookup_record
            lookup[f"part {lookup_record.index}".casefold()] = lookup_record
            part_name = getattr(lookup_record.part, "partName", None)
            part_id = getattr(lookup_record.part, "id", None)
            if part_name:
                lookup.setdefault(str(part_name).casefold(), lookup_record)
            if part_id:
                lookup.setdefault(str(part_id).casefold(), lookup_record)

        resolved: list[_SelectedPart] = []
        seen: set[int] = set()
        for selector in selectors:
            matched: _SelectedPart | None = None
            if isinstance(selector, int) and not isinstance(selector, bool):
                if 1 <= selector <= len(records):
                    matched = records[selector - 1]
            elif isinstance(selector, str) and selector.strip():
                matched = lookup.get(selector.strip().casefold())
            if matched is None:
                raise ValueError(f"Unknown part selector: {selector}")
            if matched.index not in seen:
                resolved.append(matched)
                seen.add(matched.index)
        if not resolved:
            raise ValueError("parts did not select any score parts")
        return resolved

    def _extract_part(
        self, selected: _SelectedPart, verse_filter: str | None
    ) -> tuple[list[dict[str, Any]], list[_PitchedEvent], set[str]]:
        """Extract lyric and pitched-note data from one part."""
        lyrics: list[dict[str, Any]] = []
        pitched: list[_PitchedEvent] = []
        verses: set[str] = set()

        elements = list(selected.part.recurse().notesAndRests)
        for note_index, element in enumerate(elements, start=1):
            locator = self._locator(selected, element, note_index)
            verse_keys: set[str] = set()
            texted_verses: set[str] = set()
            for lyric_index, lyric in enumerate(element.lyrics, start=1):
                verse = self._lyric_verse(lyric)
                verses.add(verse)
                verse_keys.add(verse)
                text = "" if lyric.text is None else str(lyric.text)
                if text.strip():
                    texted_verses.add(verse)
                if verse_filter is not None and verse != verse_filter:
                    continue
                components = self._lyric_components(lyric)
                raw_state = lyric.syllabic
                normalized_state = (
                    self._composite_boundary_state(components)
                    if components
                    else (
                        str(raw_state).casefold()
                        if raw_state is not None
                        else "single"
                    )
                )
                lyrics.append(
                    {
                        **locator,
                        "lyric_index": lyric_index,
                        "verse": verse,
                        "text": text,
                        "syllabic": normalized_state,
                        "raw_syllabic": raw_state,
                        "composite": bool(components),
                        "components": components,
                        "elision_before": getattr(lyric, "elisionBefore", None),
                        "explicit_extension": self._has_explicit_extension(lyric),
                    }
                )
            if not isinstance(element, note.Rest):
                pitched.append(
                    _PitchedEvent(
                        element=element,
                        locator=locator,
                        verses=frozenset(verse_keys),
                        texted_verses=frozenset(texted_verses),
                    )
                )
        lyrics.sort(key=self._event_sort_key)
        pitched.sort(
            key=lambda item: (
                item.locator["offset"],
                item.locator["voice"],
                item.locator["note_index"],
            )
        )
        return lyrics, pitched, verses

    def _locator(
        self,
        selected: _SelectedPart,
        element: note.GeneralNote,
        note_index: int,
    ) -> dict[str, Any]:
        """Build a stable, serializable locator for a note, chord, or rest."""
        measure = element.getContextByClass(stream.Measure)
        measure_number = element.measureNumber
        if measure_number is None and measure is not None:
            measure_number = measure.number
        offset = self._hierarchy_offset(element, selected.part)
        offset_in_measure = (
            self._hierarchy_offset(element, measure)
            if measure is not None
            else float(element.offset)
        )
        voice = element.getContextByClass(stream.Voice)
        voice_id = "1" if voice is None or voice.id is None else str(voice.id)

        pitch_value: str | list[str] | None
        if isinstance(element, note.Note):
            pitch_value = element.pitch.nameWithOctave
        elif isinstance(element, chord.Chord):
            pitch_value = [pitch.nameWithOctave for pitch in element.pitches]
        else:
            pitch_value = None
        return {
            "part": selected.name,
            "part_index": selected.index,
            "measure": measure_number,
            "voice": voice_id,
            "offset": offset,
            "offset_fraction": self._fraction_string(
                element.getOffsetInHierarchy(selected.part)
            ),
            "offset_in_measure": offset_in_measure,
            "offset_in_measure_fraction": self._fraction_string(
                element.getOffsetInHierarchy(measure)
                if measure is not None
                else element.offset
            ),
            "note_index": note_index,
            "element_type": element.__class__.__name__,
            "pitch": pitch_value,
        }

    def _audit_lyric_events(
        self, events: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Find lyric-object problems independent of word reconstruction."""
        issues: list[dict[str, Any]] = []
        patches: list[dict[str, Any]] = []
        by_note_verse: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(
            list
        )
        for event in events:
            by_note_verse[
                (event["part"], event["note_index"], event["verse"])
            ].append(event)
            location = self._public_location(event)
            if not event["text"].strip() and not event["explicit_extension"]:
                issues.append(
                    self._finding(
                        "empty_lyric_text",
                        "error",
                        "high",
                        "Lyric object has empty or whitespace-only text.",
                        location=location,
                        verse=event["verse"],
                    )
                )
                patches.append(
                    {
                        "operation": "remove_empty_lyric",
                        "confidence": "high",
                        "part": event["part"],
                        "measure": event["measure"],
                        "voice": event["voice"],
                        "offset_in_measure": event["offset_in_measure"],
                        "note_index": event["note_index"],
                        "verse": event["verse"],
                        "reason": "The lyric object contains no visible text.",
                    }
                )
            if event["syllabic"] not in self.VALID_SYLLABIC_STATES:
                issues.append(
                    self._finding(
                        "invalid_syllabic_state",
                        "error",
                        "high",
                        f"Unknown syllabic state: {event['raw_syllabic']!r}.",
                        location=location,
                        verse=event["verse"],
                    )
                )

        for duplicates in by_note_verse.values():
            if len(duplicates) <= 1:
                continue
            issues.append(
                self._finding(
                    "duplicate_verse_on_note",
                    "error",
                    "high",
                    "More than one lyric object uses the same verse on one note.",
                    locations=[self._public_location(item) for item in duplicates],
                    verse=duplicates[0]["verse"],
                )
            )
        return issues, patches

    def _reconstruct_text(
        self, events: list[dict[str, Any]], issues: list[dict[str, Any]]
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Reconstruct words independently for every part, verse, and voice."""
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            for reconstruction_event in self._reconstruction_events(event):
                grouped[
                    (
                        reconstruction_event["part"],
                        reconstruction_event["verse"],
                        reconstruction_event["voice"],
                    )
                ].append(reconstruction_event)

        result: dict[str, dict[str, dict[str, Any]]] = {}
        for (part_name, verse, voice), voice_events in grouped.items():
            voice_events.sort(key=self._event_sort_key)
            words = self._reconstruct_voice(voice_events, issues)
            verse_result = result.setdefault(part_name, {}).setdefault(
                verse, {"text": "", "voices": {}, "words": []}
            )
            voice_text = " ".join(word["text"] for word in words if word["text"])
            verse_result["voices"][voice] = voice_text
            verse_result["words"].extend(words)

        for part_verses in result.values():
            for verse_result in part_verses.values():
                verse_result["words"].sort(
                    key=lambda word: (
                        word["start"]["offset"],
                        word["voice"],
                    )
                )
                if len(verse_result["voices"]) == 1:
                    verse_result["text"] = next(
                        iter(verse_result["voices"].values())
                    )
                else:
                    verse_result["text"] = " | ".join(
                        f"voice {voice}: {text}"
                        for voice, text in sorted(verse_result["voices"].items())
                    )
        return result

    @staticmethod
    def _compact_reconstruction(
        reconstructed: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Keep reconstructed text while omitting per-word locator duplication."""
        compact: dict[str, dict[str, dict[str, Any]]] = {}
        for part_name, part_verses in reconstructed.items():
            compact[part_name] = {}
            for verse, value in part_verses.items():
                words = value.get("words", [])
                compact[part_name][verse] = {
                    "text": value.get("text", ""),
                    "voices": value.get("voices", {}),
                    "word_count": len(words),
                    "malformed_word_count": sum(
                        not word.get("well_formed", False) for word in words
                    ),
                }
        return compact

    @staticmethod
    def _reconstruction_events(event: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand composite elisions so internal word boundaries remain visible."""
        components = event.get("components", [])
        if not components:
            return [event]
        expanded: list[dict[str, Any]] = []
        for component_index, component in enumerate(components, start=1):
            expanded.append(
                {
                    **event,
                    "text": component.get("text", ""),
                    "syllabic": str(
                        component.get("syllabic") or "single"
                    ).casefold(),
                    "component_index": component_index,
                }
            )
        return expanded

    def _reconstruct_voice(
        self, events: list[dict[str, Any]], issues: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Apply the begin/middle/end state machine to one lyric stream."""
        words: list[dict[str, Any]] = []
        open_events: list[dict[str, Any]] = []
        open_well_formed = True

        def append_word(
            fragments: list[dict[str, Any]], well_formed: bool
        ) -> None:
            if not fragments:
                return
            words.append(
                {
                    "text": "".join(item["text"].strip() for item in fragments),
                    "voice": fragments[0]["voice"],
                    "syllables": [item["text"] for item in fragments],
                    "well_formed": well_formed,
                    "start": self._public_location(fragments[0]),
                    "end": self._public_location(fragments[-1]),
                }
            )

        for event in events:
            state = event["syllabic"]
            if state not in self.VALID_SYLLABIC_STATES:
                state = "single"
            location = self._public_location(event)

            if state == "begin":
                if open_events:
                    issues.append(
                        self._finding(
                            "begin_before_previous_end",
                            "error",
                            "high",
                            "A new begin syllable appears before the prior word ends.",
                            locations=[
                                self._public_location(open_events[0]),
                                location,
                            ],
                            verse=event["verse"],
                        )
                    )
                    append_word(open_events, False)
                open_events = [event]
                open_well_formed = True
            elif state == "middle":
                if not open_events:
                    issues.append(
                        self._finding(
                            "middle_without_begin",
                            "error",
                            "high",
                            "A middle syllable has no preceding begin syllable.",
                            location=location,
                            verse=event["verse"],
                        )
                    )
                    open_well_formed = False
                open_events.append(event)
            elif state == "end":
                if not open_events:
                    issues.append(
                        self._finding(
                            "end_without_begin",
                            "error",
                            "high",
                            "An end syllable has no preceding begin syllable.",
                            location=location,
                            verse=event["verse"],
                        )
                    )
                    append_word([event], False)
                else:
                    open_events.append(event)
                    append_word(open_events, open_well_formed)
                    open_events = []
                    open_well_formed = True
            else:
                if open_events:
                    issues.append(
                        self._finding(
                            "single_before_previous_end",
                            "error",
                            "high",
                            "A single syllable interrupts an unfinished word.",
                            locations=[
                                self._public_location(open_events[0]),
                                location,
                            ],
                            verse=event["verse"],
                        )
                    )
                    append_word(open_events, False)
                    open_events = []
                    open_well_formed = True
                append_word([event], True)

        if open_events:
            issues.append(
                self._finding(
                    "word_missing_end",
                    "error",
                    "high",
                    "A begin/middle syllable sequence never reaches an end syllable.",
                    locations=[
                        self._public_location(open_events[0]),
                        self._public_location(open_events[-1]),
                    ],
                    verse=open_events[0]["verse"],
                )
            )
            append_word(open_events, False)
        return words

    def _coverage_stats(
        self,
        selected_parts: list[_SelectedPart],
        pitched_by_part: dict[str, list[_PitchedEvent]],
        lyric_events: list[dict[str, Any]],
        reconstructed: dict[str, dict[str, dict[str, Any]]],
        available_verses: dict[str, list[str]],
        verse_filter: str | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Compute score/active-span coverage and possible unexplained gaps."""
        by_part: dict[str, Any] = {}
        observations: list[dict[str, Any]] = []
        total_pitched = 0
        total_lyric_events = 0
        total_assignments = 0

        lyric_lookup: dict[
            tuple[str, str, str, int], list[dict[str, Any]]
        ] = defaultdict(list)
        for event in lyric_events:
            lyric_lookup[
                (
                    event["part"],
                    event["verse"],
                    event["voice"],
                    event["note_index"],
                )
            ].append(event)

        for selected in selected_parts:
            pitched = pitched_by_part[selected.name]
            total_pitched += len(pitched)
            verses = (
                [verse_filter]
                if verse_filter is not None
                else available_verses[selected.name]
            )
            part_stats: dict[str, Any] = {
                "pitched_notes": len(pitched),
                "verses": {},
            }
            for verse in verses:
                verse_stats, verse_observations = self._verse_coverage(
                    selected.name,
                    verse,
                    pitched,
                    lyric_lookup,
                    reconstructed,
                )
                part_stats["verses"][verse] = verse_stats
                observations.extend(verse_observations)
                total_lyric_events += verse_stats["lyric_events"]
                total_assignments += verse_stats["lyric_bearing_notes"]
            by_part[selected.name] = part_stats

        return (
            {
                "overall": {
                    "selected_parts": len(selected_parts),
                    "pitched_notes": total_pitched,
                    "lyric_events": total_lyric_events,
                    "lyric_bearing_note_assignments": total_assignments,
                    "audited_part_verses": sum(
                        len(item["verses"]) for item in by_part.values()
                    ),
                },
                "by_part": by_part,
            },
            observations,
        )

    def _verse_coverage(
        self,
        part_name: str,
        verse: str,
        pitched: list[_PitchedEvent],
        lyric_lookup: dict[tuple[str, str, str, int], list[dict[str, Any]]],
        reconstructed: dict[str, dict[str, dict[str, Any]]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Calculate coverage for one part/verse and inspect internal gaps."""
        bearing = [event for event in pitched if verse in event.verses]
        texted = [event for event in pitched if verse in event.texted_verses]
        by_voice: dict[str, list[_PitchedEvent]] = defaultdict(list)
        for event in pitched:
            by_voice[event.locator["voice"]].append(event)

        active_count = 0
        active_texted = 0
        inferred_melisma = 0
        possible_untexted = 0
        observations: list[dict[str, Any]] = []
        for voice, voice_events in by_voice.items():
            verse_positions = [
                index
                for index, event in enumerate(voice_events)
                if verse in event.texted_verses
            ]
            if not verse_positions:
                continue
            first, last = min(verse_positions), max(verse_positions)
            active = voice_events[first : last + 1]
            active_count += len(active)
            active_texted += sum(verse in event.texted_verses for event in active)
            inferred, possible, gap_findings = self._internal_gap_observations(
                part_name,
                verse,
                voice,
                active,
                lyric_lookup,
            )
            inferred_melisma += inferred
            possible_untexted += possible
            observations.extend(gap_findings)

        reconstructed_verse = reconstructed.get(part_name, {}).get(verse, {})
        lyric_count = sum(
            len(values)
            for key, values in lyric_lookup.items()
            if key[0] == part_name and key[1] == verse
        )
        return (
            {
                "lyric_events": lyric_count,
                "lyric_bearing_notes": len(bearing),
                "texted_notes": len(texted),
                "score_coverage_percent": self._percentage(len(texted), len(pitched)),
                "active_span_pitched_notes": active_count,
                "active_span_texted_notes": active_texted,
                "active_span_coverage_percent": self._percentage(
                    active_texted, active_count
                ),
                "inferred_melisma_or_sustain_notes": inferred_melisma,
                "possible_untexted_internal_notes": possible_untexted,
                "measures_with_lyrics": sorted(
                    {
                        event.locator["measure"]
                        for event in bearing
                        if event.locator["measure"] is not None
                    },
                    key=str,
                ),
                "reconstructed_words": len(reconstructed_verse.get("words", [])),
            },
            observations,
        )

    def _internal_gap_observations(
        self,
        part_name: str,
        verse: str,
        voice: str,
        active: list[_PitchedEvent],
        lyric_lookup: dict[tuple[str, str, str, int], list[dict[str, Any]]],
    ) -> tuple[int, int, list[dict[str, Any]]]:
        """Classify lyric-free notes inside a verse's active span conservatively."""
        observations: list[dict[str, Any]] = []
        inferred_count = 0
        possible_count = 0
        index = 0
        while index < len(active):
            if verse in active[index].texted_verses:
                index += 1
                continue
            start = index
            while index < len(active) and verse not in active[index].texted_verses:
                index += 1
            gap = active[start:index]
            if start == 0 or index >= len(active):
                continue
            previous = active[start - 1]
            following = active[index]
            previous_lyrics = lyric_lookup.get(
                (part_name, verse, voice, previous.locator["note_index"]), []
            )
            following_lyrics = lyric_lookup.get(
                (part_name, verse, voice, following.locator["note_index"]), []
            )
            previous_state = (
                previous_lyrics[-1]["syllabic"] if previous_lyrics else "single"
            )
            following_state = (
                following_lyrics[0]["syllabic"] if following_lyrics else "single"
            )
            explicit_extension = any(
                lyric["explicit_extension"] for lyric in previous_lyrics
            )
            tied_or_slurred = self._gap_is_tied_or_slurred(previous, gap, following)
            word_continues = previous_state in {"begin", "middle"} and (
                following_state in {"middle", "end"}
            )
            if explicit_extension or tied_or_slurred or word_continues:
                inferred_count += len(gap)
                continue

            possible_count += len(gap)
            locations = [self._public_location(item.locator) for item in gap]
            observations.append(
                self._finding(
                    "possible_untexted_internal_notes",
                    "observation",
                    "low",
                    (
                        f"{len(gap)} untied lyric-free note(s) occur between "
                        "texted notes. This may be an intended implicit melisma; "
                        "music21 does not reliably retain MusicXML lyric extenders."
                    ),
                    locations=locations,
                    verse=verse,
                )
            )
        return inferred_count, possible_count, observations

    def _verse_observations(
        self, available: dict[str, list[str]], coverage: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Report differing verse sets/coverage as neutral observations."""
        observations: list[dict[str, Any]] = []
        verse_sets = {part: tuple(verses) for part, verses in available.items()}
        if len(set(verse_sets.values())) > 1:
            observations.append(
                self._finding(
                    "cross_part_verse_set_difference",
                    "observation",
                    "high",
                    (
                        "Selected parts expose different verse sets; this may be "
                        "intentional or may indicate incomplete verse entry."
                    ),
                    verse_sets=verse_sets,
                )
            )

        for part_name, part_stats in coverage["by_part"].items():
            verses = part_stats["verses"]
            counts = {verse: stats["texted_notes"] for verse, stats in verses.items()}
            if len(counts) > 1 and len(set(counts.values())) > 1:
                observations.append(
                    self._finding(
                        "within_part_verse_coverage_difference",
                        "observation",
                        "low",
                        (
                            f"{part_name} has different texted-note counts among "
                            "verses; differing text lengths may be intentional."
                        ),
                        part=part_name,
                        texted_notes_by_verse=counts,
                    )
                )
        return observations

    def _cross_part_observations(
        self, reconstructed: dict[str, dict[str, dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Compare reconstructed text while treating differences as observations."""
        by_verse: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for part_name, part_verses in reconstructed.items():
            for verse, value in part_verses.items():
                by_verse[verse][part_name] = value

        observations: list[dict[str, Any]] = []
        for verse, part_values in by_verse.items():
            if len(part_values) < 2:
                continue
            normalized = {
                part: self._normalize_text(value["text"])
                for part, value in part_values.items()
            }
            if len(set(normalized.values())) <= 1:
                continue
            locations = self._first_text_difference_locations(part_values)
            observations.append(
                self._finding(
                    "cross_part_text_difference",
                    "observation",
                    "high",
                    (
                        "Parts have different reconstructed text. This is evidence "
                        "only: staggered entries, omissions, or polytext may be "
                        "intentional."
                    ),
                    locations=locations,
                    verse=verse,
                    text_by_part={
                        part: value["text"] for part, value in part_values.items()
                    },
                )
            )
        return observations

    @staticmethod
    def _first_text_difference_locations(
        part_values: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        word_lists = {
            part: value.get("words", []) for part, value in part_values.items()
        }
        maximum = max((len(words) for words in word_lists.values()), default=0)
        for index in range(maximum):
            values = {
                part: (
                    LyricAuditTool._normalize_text(words[index]["text"])
                    if index < len(words)
                    else None
                )
                for part, words in word_lists.items()
            }
            if len(set(values.values())) > 1:
                return [
                    {"part": part, **words[index]["start"]}
                    for part, words in word_lists.items()
                    if index < len(words)
                ]
        return []

    @staticmethod
    def _lyric_components(lyric: note.Lyric) -> list[dict[str, Any]]:
        components = getattr(lyric, "components", None)
        if not components:
            return []
        return [
            {
                "text": "" if component.text is None else str(component.text),
                "syllabic": component.syllabic,
                "elision_before": getattr(component, "elisionBefore", None),
            }
            for component in components
        ]

    @staticmethod
    def _composite_boundary_state(components: list[dict[str, Any]]) -> str:
        """Map an elided composite lyric to its external word-boundary state."""
        first_state = str(components[0].get("syllabic") or "single").casefold()
        last_state = str(components[-1].get("syllabic") or "single").casefold()
        continues_from_previous = first_state in {"middle", "end"}
        continues_to_next = last_state in {"begin", "middle"}
        if continues_from_previous and continues_to_next:
            return "middle"
        if continues_from_previous:
            return "end"
        if continues_to_next:
            return "begin"
        return "single"

    @staticmethod
    def _has_explicit_extension(lyric: note.Lyric) -> bool:
        """Best-effort check; music21 normally discards MusicXML extend markers."""
        for attribute in ("extend", "extension", "extendType"):
            if getattr(lyric, attribute, None):
                return True
        raw_text = "" if lyric.rawText is None else str(lyric.rawText)
        if raw_text.rstrip().endswith("_"):
            return True
        editorial = getattr(lyric, "editorial", None)
        if editorial is not None:
            try:
                return bool(editorial.get("extend"))
            except (AttributeError, TypeError):
                return False
        return False

    @staticmethod
    def _gap_is_tied_or_slurred(
        previous: _PitchedEvent,
        gap: list[_PitchedEvent],
        following: _PitchedEvent,
    ) -> bool:
        if gap and all(LyricAuditTool._is_tie_continuation(item.element) for item in gap):
            return True
        previous_slurs = LyricAuditTool._slur_ids(previous.element)
        if not previous_slurs:
            return False
        covered = [*gap, following]
        return any(
            previous_slurs.intersection(LyricAuditTool._slur_ids(item.element))
            for item in covered
        )

    @staticmethod
    def _is_tie_continuation(element: note.GeneralNote) -> bool:
        if isinstance(element, note.Note):
            return element.tie is not None and element.tie.type in {"continue", "stop"}
        if isinstance(element, chord.Chord):
            chord_notes = list(element.notes)
            return bool(chord_notes) and all(
                item.tie is not None and item.tie.type in {"continue", "stop"}
                for item in chord_notes
            )
        return False

    @staticmethod
    def _slur_ids(element: note.GeneralNote) -> set[int]:
        try:
            return {
                id(item)
                for item in element.getSpannerSites()
                if isinstance(item, spanner.Slur)
            }
        except (AttributeError, TypeError):
            return set()

    @staticmethod
    def _lyric_verse(lyric: note.Lyric) -> str:
        identifier: Any = lyric.identifier
        number: Any = lyric.number
        value: Any = number
        if (
            isinstance(identifier, str)
            and identifier.strip()
            and identifier.strip() != str(number)
        ):
            value = identifier
        if value is None:
            value = 1
        return str(value).strip()

    @staticmethod
    def _normalize_requested_verse(verse: Any) -> str | None:
        return None if verse is None else str(verse).strip()

    @staticmethod
    def _sort_verses(verses: set[str]) -> list[str]:
        def key(value: str) -> tuple[int, int | str]:
            return (0, int(value)) if value.isdigit() else (1, value.casefold())

        return sorted(verses, key=key)

    @staticmethod
    def _hierarchy_offset(
        element: note.GeneralNote, container: stream.Stream | None
    ) -> float:
        if container is None:
            return float(element.offset)
        return float(element.getOffsetInHierarchy(container))

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

    @staticmethod
    def _event_sort_key(event: dict[str, Any]) -> tuple[float, str, int, int]:
        return (
            event["offset"],
            event["voice"],
            event["note_index"],
            event.get("lyric_index", 0) * 1000 + event.get("component_index", 0),
        )

    @staticmethod
    def _public_location(event: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "part",
            "part_index",
            "measure",
            "voice",
            "offset",
            "offset_fraction",
            "offset_in_measure",
            "offset_in_measure_fraction",
            "note_index",
            "element_type",
            "pitch",
        )
        return {field: event.get(field) for field in fields}

    @staticmethod
    def _finding(
        finding_type: str,
        severity: str,
        confidence: str,
        message: str,
        **details: Any,
    ) -> dict[str, Any]:
        return {
            "type": finding_type,
            "severity": severity,
            "confidence": confidence,
            "message": message,
            **details,
        }

    @staticmethod
    def _finding_summary(
        issues: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        patches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return compact counts without duplicating detailed finding payloads."""
        issue_types = Counter(item["type"] for item in issues)
        observation_types = Counter(item["type"] for item in observations)
        finding_types = issue_types + observation_types
        patch_operations = Counter(item["operation"] for item in patches)
        return {
            "issue_count": len(issues),
            "observation_count": len(observations),
            "proposed_patch_count": len(patches),
            "by_finding_type": dict(sorted(finding_types.items())),
            "issue_types": dict(sorted(issue_types.items())),
            "observation_types": dict(sorted(observation_types.items())),
            "patch_operations": dict(sorted(patch_operations.items())),
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(re.findall(r"[^\W_]+", text.casefold(), re.UNICODE))

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0.0
        return round(100.0 * numerator / denominator, 2)
