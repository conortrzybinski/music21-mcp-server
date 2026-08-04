"""
Import Score Tool - Import musical scores from various sources
Supports files, corpus, and text notation with intelligent auto-detection
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from music21 import converter, corpus, note, stream

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class MuseScoreImportError(RuntimeError):
    """Raised when a MuseScore source cannot be converted for music21."""


class ScoreFileParseError(RuntimeError):
    """Raised when a prepared local score still cannot be parsed."""


class ImportScoreTool(BaseTool):
    """Tool for importing musical scores from various sources"""

    MAX_MUSESCORE_EXPORT_TIMEOUT_SECONDS = 120.0
    MAX_XML_PREFLIGHT_BYTES = 25 * 1024 * 1024
    MAX_MUSESCORE_NATIVE_XML_BYTES = 50 * 1024 * 1024

    SUPPORTED_FILE_EXTENSIONS = {
        ".mid",
        ".midi",
        ".xml",
        ".musicxml",
        ".mxl",
        ".abc",
        ".krn",
        ".mei",
        ".mscz",
        ".mscx",
    }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Import a musical score from various sources

        Args:
            **kwargs: Keyword arguments including:
                score_id: Unique identifier for the score
                source: File path, corpus path, or note sequence
                source_type: Type of source ('file', 'corpus', 'text', 'auto')
        """
        # Extract parameters from kwargs
        score_id = kwargs.get("score_id", "")
        source = kwargs.get("source", "")
        source_type = kwargs.get("source_type", "auto")
        # Validate inputs
        error = self.validate_inputs(**kwargs)
        if error:
            return self.create_error_response(error)

        with self.error_handling(f"Import score '{score_id}'"):
            # Auto-detect source type if needed
            if source_type == "auto":
                source_type = self._detect_source_type(source)

            self.report_progress(0.1, f"Importing from {source_type}")

            # Import based on source type
            score = None
            import_repairs: list[dict[str, Any]] = []
            import_warnings: list[dict[str, Any]] = []
            import_context: list[dict[str, Any]] = []

            try:
                if source_type == "file":
                    score = await self._import_from_file(
                        source,
                        import_repairs=import_repairs,
                        import_warnings=import_warnings,
                        import_context=import_context,
                    )
                elif source_type == "corpus":
                    score = await self._import_from_corpus(source)
                elif source_type == "text":
                    score = await self._import_from_text(source)
                else:
                    return self.create_error_response(
                        f"Unknown source type: {source_type}"
                    )

                if score is None:
                    return self.create_error_response(
                        f"Could not find or import score: {source}",
                        details={
                            "import_repairs": import_repairs,
                            "import_warnings": import_warnings,
                            "import_context": import_context,
                        },
                    )
            except Exception as e:
                # Return the specific error message from music21
                error_msg = str(e)
                if "Could not find" in error_msg:
                    message = f"Could not find score: {source}"
                else:
                    message = f"Import failed: {error_msg}"
                return self.create_error_response(
                    message,
                    details={
                        "import_repairs": import_repairs,
                        "import_warnings": import_warnings,
                        "import_context": import_context,
                    },
                )

            self.report_progress(0.8, "Analyzing score metadata")

            # Store the score
            self.score_manager[score_id] = score

            # Get metadata asynchronously
            metadata = await self._extract_metadata(score)

            self.report_progress(1.0, "Import complete")

            return self.create_success_response(
                message=f"Successfully imported score '{score_id}' from {source_type}",
                score_id=score_id,
                source_type=source_type,
                import_repairs=import_repairs,
                import_warnings=import_warnings,
                import_context=import_context,
                **metadata,
            )

    def validate_inputs(self, **kwargs: Any) -> str | None:
        """Validate input parameters"""
        score_id = kwargs.get("score_id", "")
        source = kwargs.get("source", "")
        source_type = kwargs.get("source_type", "auto")

        if not score_id:
            return "score_id cannot be empty"

        if not source:
            return "source cannot be empty"

        if score_id in self.score_manager:
            return f"Score with ID '{score_id}' already exists"

        if source_type not in ["auto", "file", "corpus", "text"]:
            return f"Invalid source_type: {source_type}"

        return None

    def _detect_source_type(self, source: str) -> str:
        """Auto-detect the source type"""
        # Check if it's a file path
        if os.path.exists(source):
            return "file"

        # Check if it has a file extension
        if any(source.lower().endswith(ext) for ext in self.SUPPORTED_FILE_EXTENSIONS):
            return "file"

        # Check if it looks like a corpus path
        if "/" in source and not os.path.exists(source):
            # Common corpus patterns
            if any(
                composer in source.lower()
                for composer in ["bach", "mozart", "beethoven", "chopin"]
            ):
                return "corpus"

        # Check if it looks like note text
        if " " in source:
            # Check if all tokens look like notes
            tokens = source.split()
            if all(self._is_note_like(token) for token in tokens):
                return "text"

        # Default to trying as file
        return "file"

    def _is_note_like(self, token: str) -> bool:
        """Check if a token looks like a note"""
        # Remove accidentals
        cleaned = token.replace("#", "").replace("-", "").replace("b", "")
        # Check if it's alphanumeric with letter followed by number
        if len(cleaned) >= 2:
            return cleaned[0].isalpha() and cleaned[1:].isdigit()
        return False

    async def _import_from_file(
        self,
        file_path: str,
        *,
        import_repairs: list[dict[str, Any]] | None = None,
        import_warnings: list[dict[str, Any]] | None = None,
        import_context: list[dict[str, Any]] | None = None,
    ) -> stream.Score | None:
        """Import from a file using async execution"""
        # Validate path for security (prevent directory traversal)
        validated_path = self._validate_safe_path(file_path)

        if not os.path.exists(validated_path):
            return None

        try:
            # Parse file in background thread to avoid blocking event loop
            def _parse_file():
                repairs = import_repairs if import_repairs is not None else []
                warnings = import_warnings if import_warnings is not None else []
                context = import_context if import_context is not None else []
                return self._parse_file_with_temporary_derivatives(
                    Path(validated_path), repairs, warnings, context
                )

            parsed = await self.run_with_progress(
                _parse_file,
                progress_start=0.3,
                progress_end=0.7,
                message="Parsing file",
                timeout=self._musescore_export_timeout() + 5.0,
            )

            # Ensure we return a Score object
            if isinstance(parsed, stream.Score):
                return parsed
            if hasattr(parsed, "flatten"):
                # Convert to Score if it's another stream type
                def _convert_to_score():
                    score = stream.Score()
                    score.append(parsed)
                    return score

                return await self.run_music21_operation(_convert_to_score)
            return None
        except (MuseScoreImportError, ScoreFileParseError):
            raise
        except Exception as e:
            logger.error(f"Failed to parse file {validated_path}: {e}")
            return None

    def _parse_file_with_temporary_derivatives(
        self,
        source_path: Path,
        import_repairs: list[dict[str, Any]],
        import_warnings: list[dict[str, Any]],
        import_context: list[dict[str, Any]],
    ) -> Any:
        """Prepare a safe derivative when required, then parse it with music21."""
        suffix = source_path.suffix.lower()

        with tempfile.TemporaryDirectory(prefix="music21-mcp-import-") as temp_dir:
            temporary_directory = Path(temp_dir)
            parse_path = source_path

            if suffix in {".mscz", ".mscx"}:
                import_context.extend(
                    self._extract_musescore_native_context(
                        source_path, suffix, import_warnings
                    )
                )
                executable = self._find_musescore_executable()
                exported_path = temporary_directory / "musescore-export.musicxml"
                self._export_musescore_to_musicxml(
                    executable, source_path, exported_path
                )
                parse_path = exported_path
                import_warnings.append(
                    {
                        "code": "musescore_musicxml_conversion",
                        "source_format": suffix.lstrip("."),
                        "message": (
                            "Imported through a temporary MusicXML export. "
                            "The original MuseScore file was not modified, but "
                            "MuseScore-specific layout or engraving details may not "
                            "be represented in music21."
                        ),
                    }
                )

            if parse_path.suffix.lower() in {".xml", ".musicxml"}:
                parse_path = self._sanitized_musicxml_derivative_if_needed(
                    parse_path,
                    temporary_directory,
                    import_repairs,
                    import_warnings,
                )

            try:
                parsed = converter.parse(str(parse_path))
            except Exception as exc:
                diagnostic = str(exc).strip()
                if len(diagnostic) > 1000:
                    diagnostic = f"{diagnostic[:1000]}..."
                derivative_note = (
                    " after temporary MuseScore-to-MusicXML conversion"
                    if suffix in {".mscz", ".mscx"}
                    else ""
                )
                raise ScoreFileParseError(
                    f"music21 could not parse '{source_path.name}'{derivative_note}: "
                    f"{diagnostic or exc.__class__.__name__}"
                ) from exc

            if import_context and hasattr(parsed, "editorial"):
                parsed.editorial["music21_mcp_import_context"] = import_context
            return parsed

    @classmethod
    def _extract_musescore_native_context(
        cls,
        source_path: Path,
        suffix: str,
        import_warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Preserve tempo semantics that MuseScore's MusicXML export can lose."""
        try:
            if suffix == ".mscz":
                with zipfile.ZipFile(source_path) as archive:
                    candidates = [
                        info
                        for info in archive.infolist()
                        if info.filename.lower().endswith(".mscx")
                    ]
                    if not candidates:
                        raise ValueError("archive contains no .mscx score document")
                    score_info = min(
                        candidates,
                        key=lambda info: (info.filename.count("/"), len(info.filename)),
                    )
                    if score_info.file_size > cls.MAX_MUSESCORE_NATIVE_XML_BYTES:
                        raise ValueError(
                            "native score XML exceeds the 50 MiB inspection limit"
                        )
                    with archive.open(score_info) as score_file:
                        xml_bytes = score_file.read(
                            cls.MAX_MUSESCORE_NATIVE_XML_BYTES + 1
                        )
                    if len(xml_bytes) > cls.MAX_MUSESCORE_NATIVE_XML_BYTES:
                        raise ValueError(
                            "native score XML exceeds the 50 MiB inspection limit"
                        )
            else:
                if source_path.stat().st_size > cls.MAX_MUSESCORE_NATIVE_XML_BYTES:
                    raise ValueError(
                        "native score XML exceeds the 50 MiB inspection limit"
                    )
                xml_bytes = source_path.read_bytes()

            root = ET.fromstring(xml_bytes)  # noqa: S314
            return cls._musescore_context_from_xml(root)
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
            import_warnings.append(
                {
                    "code": "musescore_native_context_unavailable",
                    "message": (
                        "Could not inspect native MuseScore tempo semantics; "
                        f"MusicXML-only context will be used ({exc})."
                    ),
                }
            )
            return []

    @classmethod
    def _musescore_context_from_xml(
        cls, root: ET.Element
    ) -> list[dict[str, Any]]:
        """Extract tempo marks and gradual tempo spans from the first staff."""
        staffs = [
            element
            for element in root.iter()
            if cls._local_xml_name(element.tag) == "Staff"
        ]
        if not staffs:
            return []
        # MuseScore 4 may serialize staff-definition nodes (for example under a
        # Choir layout block) before the score staves.  Those nodes share the
        # ``Staff`` tag but contain no measures, so select the first actual
        # notation staff instead of blindly using ``staffs[0]``.
        measures: list[ET.Element] = []
        for staff in staffs:
            staff_measures = [
                element
                for element in list(staff)
                if cls._local_xml_name(element.tag) == "Measure"
            ]
            if staff_measures:
                measures = staff_measures
                break
        if not measures:
            return []

        context: list[dict[str, Any]] = []
        for measure_number, measure in enumerate(measures, start=1):
            for element in measure.iter():
                local_name = cls._local_xml_name(element.tag)
                if local_name == "Tempo":
                    context.append(
                        cls._serialize_native_tempo(element, measure_number)
                    )
                elif (
                    local_name == "Spanner"
                    and element.get("type") == "GradualTempoChange"
                ):
                    gradual = next(
                        (
                            child
                            for child in list(element)
                            if cls._local_xml_name(child.tag)
                            == "GradualTempoChange"
                        ),
                        None,
                    )
                    if gradual is not None:
                        context.append(
                            cls._serialize_native_gradual_tempo(
                                element, gradual, measure_number
                            )
                        )
        return context

    @classmethod
    def _serialize_native_tempo(
        cls, element: ET.Element, measure_number: int
    ) -> dict[str, Any]:
        tempo_value = cls._child_text(element, "tempo")
        quarter_bpm: float | None
        if tempo_value is None:
            quarter_bpm = None
        else:
            try:
                quarter_bpm = round(float(tempo_value) * 60.0, 6)
            except ValueError:
                quarter_bpm = None

        text_element = next(
            (
                child
                for child in list(element)
                if cls._local_xml_name(child.tag) == "text"
            ),
            None,
        )
        rendered_text = (
            cls._render_musescore_text(text_element)
            if text_element is not None
            else ""
        )
        symbols = [
            (child.text or "").strip()
            for child in text_element.iter()
            if text_element is not None
            and cls._local_xml_name(child.tag) == "sym"
            and (child.text or "").strip()
        ] if text_element is not None else []

        metric_modulation = None
        note_values = [cls._musescore_symbol_name(symbol) for symbol in symbols]
        note_values = [value for value in note_values if value is not None]
        if "=" in rendered_text and len(note_values) >= 2:
            metric_modulation = {
                "left": note_values[0],
                "relation": "equals",
                "right": note_values[1],
            }

        result: dict[str, Any] = {
            "type": "tempo",
            "source": "musescore_native",
            "measure": measure_number,
            "quarter_bpm": quarter_bpm,
            "text": rendered_text or None,
        }
        if symbols:
            result["source_symbols"] = symbols
        if metric_modulation is not None:
            result["metric_modulation"] = metric_modulation
        return result

    @classmethod
    def _serialize_native_gradual_tempo(
        cls,
        spanner_element: ET.Element,
        gradual: ET.Element,
        measure_number: int,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": "gradual_tempo_change",
            "source": "musescore_native",
            "measure": measure_number,
            "change_type": cls._child_text(gradual, "tempoChangeType"),
            "begin_text": cls._child_text(gradual, "beginText"),
            "continue_text": cls._child_text(gradual, "continueText"),
        }
        factor = cls._child_text(gradual, "tempoChangeFactor")
        if factor is not None:
            try:
                result["factor"] = float(factor)
            except ValueError:
                result["factor"] = factor

        next_element = next(
            (
                child
                for child in list(spanner_element)
                if cls._local_xml_name(child.tag) == "next"
            ),
            None,
        )
        if next_element is not None:
            location = next(
                (
                    child
                    for child in next_element.iter()
                    if cls._local_xml_name(child.tag) == "location"
                ),
                None,
            )
            if location is not None:
                result["span"] = {
                    "measures": cls._child_text(location, "measures") or "0",
                    "fractions": cls._child_text(location, "fractions") or "0/1",
                }
        return result

    @classmethod
    def _render_musescore_text(cls, element: ET.Element) -> str:
        parts: list[str] = []
        if element.text:
            parts.append(element.text)
        for child in list(element):
            if cls._local_xml_name(child.tag) == "sym":
                symbol = (child.text or "").strip()
                parts.append(cls._musescore_symbol_name(symbol) or f"[{symbol}]")
            elif child.text:
                parts.append(child.text)
            if child.tail:
                parts.append(child.tail)
        rendered = " ".join("".join(parts).split())
        return rendered.replace(" .", ".")

    @staticmethod
    def _musescore_symbol_name(symbol: str) -> str | None:
        names = {
            "metNoteDoubleWholeUp": "breve",
            "metNoteWholeUp": "whole",
            "metNoteHalfUp": "half",
            "metNoteQuarterUp": "quarter",
            "metNote8thUp": "eighth",
            "metNote16thUp": "16th",
            "metNote32ndUp": "32nd",
            "metNote64thUp": "64th",
            "metNote128thUp": "128th",
            "augmentationDot": ".",
        }
        return names.get(symbol)

    @classmethod
    def _child_text(cls, element: ET.Element, name: str) -> str | None:
        for child in list(element):
            if cls._local_xml_name(child.tag) == name:
                value = "".join(child.itertext()).strip()
                return value or None
        return None

    def _musescore_export_timeout(self) -> float:
        """Return a positive, bounded timeout for the external conversion."""
        return max(
            1.0, min(float(self.timeout), self.MAX_MUSESCORE_EXPORT_TIMEOUT_SECONDS)
        )

    @classmethod
    def _find_musescore_executable(cls) -> str:
        """Locate MuseScore, honoring an explicit environment override first."""
        configured = os.getenv("MUSESCORE_EXECUTABLE", "").strip().strip('"')
        if configured:
            expanded = os.path.expandvars(os.path.expanduser(configured))
            configured_path = Path(expanded)
            if configured_path.is_file():
                return str(configured_path)

            discovered = shutil.which(expanded)
            if discovered:
                return discovered

            raise MuseScoreImportError(
                "MUSESCORE_EXECUTABLE is set to "
                f"'{configured}', but that executable was not found. Set it to the "
                "full MuseScore executable path, or unset it to search PATH and "
                "standard install locations."
            )

        executable_names = (
            "MuseScore4",
            "mscore4",
            "musescore4",
            "mscore",
            "musescore",
        )
        for executable_name in executable_names:
            discovered = shutil.which(executable_name)
            if discovered:
                return discovered

        for candidate in cls._common_musescore_paths():
            if candidate.is_file():
                return str(candidate)

        raise MuseScoreImportError(
            "MuseScore is required to import .mscz or .mscx files, but no "
            "executable was found. Install MuseScore 4, add it to PATH, or set "
            "MUSESCORE_EXECUTABLE to the full executable path."
        )

    @staticmethod
    def _common_musescore_paths() -> list[Path]:
        """Return conventional MuseScore executable paths for the current OS."""
        platform_name = sys.platform
        if platform_name == "win32":
            roots = [
                os.getenv("PROGRAMW6432"),
                os.getenv("PROGRAMFILES"),
                os.getenv("PROGRAMFILES(X86)"),
            ]
            candidates: list[Path] = []
            for root in dict.fromkeys(value for value in roots if value):
                root_path = Path(root)
                candidates.extend(
                    [
                        root_path / "MuseScore 4" / "bin" / "MuseScore4.exe",
                        root_path / "MuseScore Studio 4" / "bin" / "MuseScore4.exe",
                    ]
                )

            local_app_data = os.getenv("LOCALAPPDATA")
            if local_app_data:
                candidates.extend(
                    [
                        Path(local_app_data)
                        / "Programs"
                        / "MuseScore 4"
                        / "bin"
                        / "MuseScore4.exe",
                        Path(local_app_data)
                        / "Programs"
                        / "MuseScore Studio 4"
                        / "bin"
                        / "MuseScore4.exe",
                    ]
                )
            return candidates

        if platform_name == "darwin":
            return [
                Path("/Applications/MuseScore 4.app/Contents/MacOS/MuseScore4"),
                Path("/Applications/MuseScore Studio 4.app/Contents/MacOS/MuseScore4"),
                Path("/Applications/MuseScore 4.app/Contents/MacOS/mscore"),
            ]

        return [
            Path("/usr/bin/mscore4"),
            Path("/usr/bin/musescore4"),
            Path("/usr/local/bin/mscore4"),
            Path("/usr/local/bin/musescore4"),
            Path("/snap/bin/musescore"),
        ]

    def _export_musescore_to_musicxml(
        self, executable: str, source_path: Path, output_path: Path
    ) -> None:
        """Export a MuseScore file to a temporary MusicXML file."""
        command = [executable, "-o", str(output_path), str(source_path)]
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._musescore_export_timeout(),
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MuseScoreImportError(
                "MuseScore export timed out after "
                f"{self._musescore_export_timeout():g} seconds. The original file "
                "was not modified; try opening and re-saving it in MuseScore, then "
                "import again."
            ) from exc
        except OSError as exc:
            raise MuseScoreImportError(
                f"MuseScore could not be started from '{executable}': {exc}. "
                "Check MUSESCORE_EXECUTABLE and file permissions."
            ) from exc

        if completed.returncode != 0:
            diagnostic = (completed.stderr or completed.stdout or "").strip()
            if len(diagnostic) > 1000:
                diagnostic = f"{diagnostic[:1000]}..."
            detail = f" MuseScore reported: {diagnostic}" if diagnostic else ""
            raise MuseScoreImportError(
                f"MuseScore export failed with exit code {completed.returncode}."
                f"{detail} The original file was not modified. Open the score in "
                "MuseScore to check for repair prompts, then retry."
            )

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise MuseScoreImportError(
                "MuseScore reported a successful export but did not create a "
                "readable MusicXML file. The original file was not modified. "
                "Open the score in MuseScore and export it as MusicXML manually, "
                "or verify that MuseScore has permission to use the temporary folder."
            )

    @staticmethod
    def _local_xml_name(tag: str) -> str:
        """Return an XML element's local name, ignoring its namespace."""
        return tag.rsplit("}", 1)[-1]

    def _sanitized_musicxml_derivative_if_needed(
        self,
        source_path: Path,
        temporary_directory: Path,
        import_repairs: list[dict[str, Any]],
        import_warnings: list[dict[str, Any]],
    ) -> Path:
        """Remove invalid empty-beat metronomes without changing the source file."""
        try:
            source_size = source_path.stat().st_size
        except OSError as exc:
            import_warnings.append(
                {
                    "code": "musicxml_preflight_skipped",
                    "message": f"MusicXML preflight could not stat the file ({exc}).",
                }
            )
            return source_path
        if source_size > self.MAX_XML_PREFLIGHT_BYTES:
            import_warnings.append(
                {
                    "code": "musicxml_preflight_size_limit",
                    "size_bytes": source_size,
                    "limit_bytes": self.MAX_XML_PREFLIGHT_BYTES,
                    "message": (
                        "MusicXML preflight was skipped because the document exceeds "
                        "the bounded 25 MiB inspection limit; music21 will attempt it "
                        "unchanged."
                    ),
                }
            )
            return source_path
        try:
            # The existing import already accepts local MusicXML. This bounded
            # preflight only creates a derivative and never resolves external DTDs.
            tree = ET.parse(source_path)  # noqa: S314
        except (ET.ParseError, OSError) as exc:
            import_warnings.append(
                {
                    "code": "musicxml_preflight_skipped",
                    "message": (
                        "MusicXML preflight could not inspect the file; music21 "
                        f"will attempt the original unchanged ({exc})."
                    ),
                }
            )
            return source_path

        root = tree.getroot()
        parent_by_child = {
            child: parent for parent in root.iter() for child in list(parent)
        }
        invalid_metronomes: list[ET.Element] = []
        ambiguous_per_minute_values: list[str] = []

        for metronome in root.iter():
            if self._local_xml_name(metronome.tag) != "metronome":
                continue
            beat_units = [
                child
                for child in list(metronome)
                if self._local_xml_name(child.tag) == "beat-unit"
            ]
            if not beat_units or all((unit.text or "").strip() for unit in beat_units):
                continue

            invalid_metronomes.append(metronome)
            per_minute_values = [
                (child.text or "").strip()
                for child in list(metronome)
                if self._local_xml_name(child.tag) == "per-minute"
                and (child.text or "").strip()
            ]

            ancestor = parent_by_child.get(metronome)
            while (
                ancestor is not None
                and self._local_xml_name(ancestor.tag) != "direction"
            ):
                ancestor = parent_by_child.get(ancestor)
            has_sound_tempo = ancestor is not None and any(
                self._local_xml_name(element.tag) == "sound"
                and (element.get("tempo") or "").strip()
                for element in ancestor.iter()
            )
            if not has_sound_tempo:
                ambiguous_per_minute_values.extend(per_minute_values)

        if not invalid_metronomes:
            return source_path

        for metronome in invalid_metronomes:
            direction_type = parent_by_child.get(metronome)
            if direction_type is None:
                continue
            direction_type.remove(metronome)

            if (
                self._local_xml_name(direction_type.tag) == "direction-type"
                and not list(direction_type)
                and not (direction_type.text or "").strip()
            ):
                direction = parent_by_child.get(direction_type)
                if direction is not None:
                    direction.remove(direction_type)

        sanitized_path = temporary_directory / "sanitized-import.musicxml"
        tree.write(sanitized_path, encoding="utf-8", xml_declaration=True)

        import_repairs.append(
            {
                "code": "removed_invalid_metronome",
                "count": len(invalid_metronomes),
                "message": (
                    "Removed invalid metronome markup with an empty beat-unit from "
                    "a temporary MusicXML derivative; no beat unit was inferred. "
                    "Direction words and sound tempo markings were preserved."
                ),
            }
        )
        import_warnings.append(
            {
                "code": "invalid_metronome_semantics_removed",
                "count": len(invalid_metronomes),
                "message": (
                    "The invalid MusicXML metronome graphic could not be interpreted "
                    "without inventing a beat unit. For MuseScore sources, consult "
                    "import_context for tempo text and metric-modulation semantics "
                    "recovered from the native score."
                ),
            }
        )
        if ambiguous_per_minute_values:
            import_warnings.append(
                {
                    "code": "ambiguous_metronome_tempo_omitted",
                    "values": ambiguous_per_minute_values,
                    "message": (
                        "Per-minute values in the invalid metronome markup were "
                        "omitted because their beat unit was empty and no separate "
                        "sound tempo was available."
                    ),
                }
            )

        return sanitized_path

    async def _import_from_corpus(self, corpus_path: str) -> stream.Score | None:
        """Import from music21 corpus using async execution"""
        try:
            # Parse corpus in background thread to avoid blocking event loop
            def _parse_corpus():
                return corpus.parse(corpus_path)

            parsed = await self.run_with_progress(
                _parse_corpus,
                progress_start=0.3,
                progress_end=0.7,
                message="Loading from corpus",
            )

            # Ensure we return a Score object
            if isinstance(parsed, stream.Score):
                return parsed
            if hasattr(parsed, "expandRepeats"):
                # Convert to Score if it's another stream type
                def _convert_to_score():
                    score = stream.Score()
                    score.append(parsed)
                    return score

                return await self.run_music21_operation(_convert_to_score)
            return None
        except Exception as e:
            logger.error(f"Failed to load corpus {corpus_path}: {e}")
            return None

    async def _import_from_text(self, text: str) -> stream.Score | None:
        """Import from text notation using async execution"""
        try:
            self.report_progress(0.3, "Parsing text notation")

            # Check if it's tinyNotation format
            if text.strip().startswith("tinyNotation:"):
                tiny_text = text.replace("tinyNotation:", "").strip()

                def _parse_tiny_notation():
                    from music21 import converter

                    return converter.parse(f"tinyNotation: {tiny_text}")

                # Parse in background thread
                parsed = await self.run_music21_operation(_parse_tiny_notation)

                # Ensure we return a Score object
                if isinstance(parsed, stream.Score):
                    self.report_progress(0.7, "TinyNotation parsed")
                    return parsed

                # Convert to Score if it's another stream type
                def _convert_to_score():
                    score = stream.Score()
                    score.append(parsed)
                    return score

                result = await self.run_music21_operation(_convert_to_score)
                self.report_progress(0.7, "TinyNotation parsed and converted to Score")
                return result

            # Otherwise parse as space-separated notes
            def _parse_note_sequence():
                score = stream.Score()
                part = stream.Part()
                tokens = text.split()

                for note_str in tokens:
                    try:
                        n = note.Note(note_str)
                        part.append(n)
                    except Exception as e:
                        logger.warning(f"Invalid note '{note_str}': {e}")
                        raise ValueError(f"Invalid note: {note_str}") from e

                score.append(part)
                return score

            # Parse note sequence in background thread
            result = await self.run_with_progress(
                _parse_note_sequence,
                progress_start=0.3,
                progress_end=0.7,
                message="Parsing text notation",
            )
            return result

        except Exception as e:
            logger.error(f"Failed to parse text notation: {e}")
            return None

    async def _extract_metadata(self, score: stream.Score) -> dict[str, Any]:
        """Extract metadata from score using async execution"""

        def _extract_sync():
            try:
                notes = list(score.flatten().notes)
                num_notes = len(notes)
                if isinstance(score, stream.Score) and score.parts:
                    measure_counts = [
                        len(list(part.getElementsByClass(stream.Measure)))
                        for part in score.parts
                    ]
                    num_measures = max(measure_counts, default=0)
                else:
                    num_measures = len(
                        list(score.getElementsByClass(stream.Measure))
                    )
                num_parts = len(score.parts) if hasattr(score, "parts") else 1

                # Get first and last notes for range
                pitches = [
                    score_pitch.midi
                    for event in notes
                    for score_pitch in getattr(event, "pitches", ())
                ]
                if pitches:
                    lowest = min(pitches)
                    highest = max(pitches)
                    pitch_range = highest - lowest
                else:
                    pitch_range = 0

                return {
                    "num_notes": num_notes,
                    "num_measures": num_measures,
                    "num_parts": num_parts,
                    "pitch_range": pitch_range,
                }
            except Exception as e:
                logger.warning(f"Error extracting metadata: {e}")
                return {
                    "num_notes": 0,
                    "num_measures": 0,
                    "num_parts": 0,
                    "pitch_range": 0,
                }

        return await self.run_music21_operation(_extract_sync)

    def _validate_safe_path(self, file_path: str) -> str:
        """Validate path for security (prevent directory traversal)"""
        # Convert to Path object and resolve
        path = Path(file_path).resolve()

        # Preserve the default cwd/temp policy while allowing explicit project roots.
        allowed_directories = [
            Path.cwd().resolve(),
            Path(tempfile.gettempdir()).resolve(),
        ]
        configured_roots = os.getenv("MUSIC21_ALLOWED_IMPORT_ROOTS", "")
        allowed_directories.extend(
            Path(
                os.path.expandvars(os.path.expanduser(value.strip().strip('"')))
            ).resolve()
            for value in configured_roots.split(os.pathsep)
            if value.strip().strip('"')
        )

        for allowed_directory in allowed_directories:
            try:
                path.relative_to(allowed_directory)
                return str(path)
            except ValueError:
                continue

        # Path is outside allowed directories
        raise ValueError(
            f"Path '{file_path}' is outside allowed directories. "
            "Files can only be imported from the current directory, temp directory, "
            "or roots explicitly configured in MUSIC21_ALLOWED_IMPORT_ROOTS."
        )
