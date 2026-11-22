"""Command-line interface for sci-integrity-guard."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .linter import SciIntegrityGuard
from .omml import latex_to_omml


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="sci-guard",
        description="Verify table consistency, DOIs, and Word OMML math syntax in Markdown papers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser("check", help="Lint a Markdown manuscript.")
    check_p.add_argument("file", help="Path to Markdown file.")
    check_p.add_argument("--verify-dois", action="store_true", help="Resolve extracted DOIs via CrossRef/OpenAlex.")
    check_p.add_argument("--tolerance", type=float, default=0.05, help="Numeric delta threshold across tables.")
    check_p.add_argument("--json", action="store_true", dest="as_json", help="Emit structured JSON report.")

    omml_p = sub.add_parser("omml", help="Convert a LaTeX math expression to Word OMML XML.")
    omml_p.add_argument("latex", help="LaTeX expression string.")
    omml_p.add_argument("--display", action="store_true", help="Wrap in block <m:oMathPara>.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint returning process exit code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "omml":
        try:
            print(latex_to_omml(args.latex, display=args.display))
            return 0
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    target = Path(args.file)
    if not target.exists():
        print(f"ERROR: File not found: {target}", file=sys.stderr)
        return 2

    markdown = target.read_text(encoding="utf-8")
    guard = SciIntegrityGuard(tolerance=args.tolerance)
    report = guard.check_markdown(markdown, verify_dois=args.verify_dois)

    if args.as_json:
        print(report.to_json())
    else:
        status = "PASS" if report.passed else "FAIL"
        print(f"[{status}] errors={report.summary['errors']} warnings={report.summary['warnings']} dois={report.summary['dois_found']}")
        for issue in report.issues:
            print(f" - ({issue.severity.upper()}) {issue.code}: {issue.message}")
    return 0 if report.passed else 1
