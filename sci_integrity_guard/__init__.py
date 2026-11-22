"""Sci Integrity Guard: Neuro-symbolic linter for scientific manuscripts."""

from .citations import CitationVerifier, extract_dois
from .linter import LintIssue, LintReport, SciIntegrityGuard
from .omml import LatexToOmmlConverter, detect_escape_corruptions, latex_to_omml
from .tables import TableConsistencyGuard, check_cross_table_parity, check_prose_metric_anchors, extract_markdown_tables

__all__ = [
    "__version__",
    "CitationVerifier",
    "LatexToOmmlConverter",
    "LintIssue",
    "LintReport",
    "SciIntegrityGuard",
    "TableConsistencyGuard",
    "check_cross_table_parity",
    "check_prose_metric_anchors",
    "detect_escape_corruptions",
    "extract_dois",
    "extract_markdown_tables",
    "latex_to_omml",
]

__version__ = "1.0.0"
