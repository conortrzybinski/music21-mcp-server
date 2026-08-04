"""
Music21 MCP Tools - Modular tool implementations
Each tool is a self-contained module with clear contracts
"""

from .choral_text_distribution_tool import ChoralTextDistributionTool
from .chord_analysis_tool import ChordAnalysisTool
from .continuation_tool import ContinuationTool
from .counterpoint_tool import CounterpointGeneratorTool
from .delete_tool import DeleteScoreTool
from .export_tool import ExportScoreTool
from .harmonization_tool import HarmonizationTool
from .harmony_analysis_tool import HarmonyAnalysisTool
from .import_tool import ImportScoreTool
from .key_analysis_tool import KeyAnalysisTool
from .list_tool import ListScoresTool
from .lyric_audit_tool import LyricAuditTool
from .pattern_recognition_tool import PatternRecognitionTool
from .score_info_tool import ScoreInfoTool
from .score_slice_tool import ScoreSliceTool
from .style_imitation_tool import StyleImitationTool
from .text_underlay_tool import TextUnderlayTool
from .voice_leading_tool import VoiceLeadingAnalysisTool

__all__ = [
    "ImportScoreTool",
    "ListScoresTool",
    "KeyAnalysisTool",
    "ChordAnalysisTool",
    "ScoreInfoTool",
    "ExportScoreTool",
    "DeleteScoreTool",
    "HarmonyAnalysisTool",
    "VoiceLeadingAnalysisTool",
    "PatternRecognitionTool",
    "HarmonizationTool",
    "CounterpointGeneratorTool",
    "StyleImitationTool",
    "TextUnderlayTool",
    "ChoralTextDistributionTool",
    "ContinuationTool",
    "ScoreSliceTool",
    "LyricAuditTool",
]
