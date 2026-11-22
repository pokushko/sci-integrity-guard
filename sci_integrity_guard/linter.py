"""Unified manuscript linter combining tables, citations, LaTeX/OMML, and leak checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any

from .citations import CitationVerifier, extract_dois
from .omml import detect_escape_corruptions, latex_to_omml
from .tables import TableConsistencyGuard

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)")
_LOCAL_LEAK_RE = re.compile(
    r"(?:[A-Za-z]:\\[^\s\"'<>]+|/(?:Users|home)/[^\s\"'<>]+|\b[A-Za-z0-9_/-]+\.(?:py|log|bat|ps1)\b)"
)


@dataclass
class LintIssue:
    """Single validation finding raised during manuscript inspection."""

    code: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LintReport:
    """Aggregate integrity report returned by `SciIntegrityGuard`."""

    passed: bool
    issues: list[LintIssue]
    summary: dict[str, Any]

    def to_json(self) -> str:
        """Serialize the lint report cleanly to formatted JSON."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class SciIntegrityGuard:
    """Run neuro-symbolic consistency, LaTeX/OMML, anti-leak, and DOI checks."""

    def __init__(
        self,
        tolerance: float = 0.05,
        anchor_tolerance: float = 0.15,
        citation_verifier: CitationVerifier | None = None,
    ) -> None:
        self.table_guard = TableConsistencyGuard(tolerance=tolerance, anchor_tolerance=anchor_tolerance)
        self.citation_verifier = citation_verifier or CitationVerifier()

    def check_markdown(self, markdown: str, verify_dois: bool = False) -> LintReport:
        """Inspect a Markdown manuscript and return a structured `LintReport`."""
        issues: list[LintIssue] = []

        # 1. Cross-table numerical parity and prose anchoring
        for raw_issue in self.table_guard.validate(markdown):
            issues.append(
                LintIssue(
                    code=raw_issue["code"],
                    severity=raw_issue["severity"],
                    message=raw_issue["message"],
                    details={k: v for k, v in raw_issue.items() if k not in {"code", "severity", "message"}},
                )
            )

        # 2. Python escape-character corruption in prose or formulas
        for esc in detect_escape_corruptions(markdown):
            issues.append(
                LintIssue(
                    code=esc["code"],
                    severity=esc["severity"],
                    message=esc["message"],
                    details={"line": esc["line"], "hint": esc["hint"]},
                )
            )

        # 3. Internal file path / artifact leak check outside fenced & inline code
        prose_only = _INLINE_CODE_RE.sub(" ", _FENCED_CODE_RE.sub(" ", markdown))
        for leak in _LOCAL_LEAK_RE.finditer(prose_only):
            issues.append(
                LintIssue(
                    code="INTERNAL_ARTIFACT_LEAK",
                    severity="error",
                    message=f"Internal path or script reference leaked in prose: '{leak.group(0)}'.",
                    details={"token": leak.group(0)},
                )
            )

        # 4. LaTeX math syntax and OMML convertibility validation
        no_code = _FENCED_CODE_RE.sub(" ", markdown)
        math_count = 0
        for pat, is_display in [(_DISPLAY_MATH_RE, True), (_INLINE_MATH_RE, False)]:
            for match in pat.finditer(no_code):
                math_count += 1
                expr = match.group(1).strip()
                try:
                    latex_to_omml(expr, display=is_display)
                except ValueError as exc:
                    issues.append(
                        LintIssue(
                            code="INVALID_LATEX_SYNTAX",
                            severity="error",
                            message=f"Invalid LaTeX expression '{expr}': {exc}",
                            details={"expression": expr},
                        )
                    )

        # 5. Optional live/mocked DOI resolution verification
        dois = extract_dois(markdown)
        verified_dois = 0
        if verify_dois:
            for doi in dois:
                res = self.citation_verifier.verify_doi(doi)
                if res["valid"]:
                    verified_dois += 1
                else:
                    for err_msg in res["issues"]:
                        issues.append(
                            LintIssue(
                                code="UNRESOLVED_DOI",
                                severity="error",
                                message=err_msg,
                                details={"doi": doi},
                            )
                        )

        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        summary = {
            "errors": error_count,
            "warnings": warning_count,
            "dois_found": len(dois),
            "dois_verified": verified_dois if verify_dois else None,
            "math_expressions_checked": math_count,
        }
        return LintReport(passed=(error_count == 0), issues=issues, summary=summary)
