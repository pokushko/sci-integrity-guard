"""LaTeX escape-corruption sanitizer and LaTeX-to-Word OMML XML converter."""

from __future__ import annotations

import html
import re
from typing import Any
import xml.etree.ElementTree as ET

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

_SYMBOLS: dict[str, str] = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Xi": "Ξ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
    "times": "×",
    "cdot": "·",
    "pm": "±",
    "mp": "∓",
    "le": "≤",
    "leq": "≤",
    "ge": "≥",
    "geq": "≥",
    "ne": "≠",
    "neq": "≠",
    "approx": "≈",
    "equiv": "≡",
    "to": "→",
    "rightarrow": "→",
    "leftarrow": "←",
    "leftrightarrow": "↔",
    "Rightarrow": "⇒",
    "in": "∈",
    "notin": "∉",
    "subset": "⊂",
    "subseteq": "⊆",
    "sum": "∑",
    "prod": "∏",
    "int": "∫",
    "infty": "∞",
    "partial": "∂",
    "nabla": "∇",
    "forall": "∀",
    "exists": "∃",
    "deg": "°",
}

_CORRUPT_SEQUENCES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\x0c(rac|orall)"), r"\f...", "Python escape '\\f' corrupted '\\frac' or '\\forall'"),
    (re.compile(r"\x09(imes|heta|au|o\b)"), r"\t...", "Python escape '\\t' corrupted '\\times'/'\\theta'/'\\tau'/'\\to'"),
    (re.compile(r"\x07(lpha|pprox|nd)"), r"\a...", "Python escape '\\a' corrupted '\\alpha'/'\\approx'"),
    (re.compile(r"\x08(eta|ar|inom)"), r"\b...", "Python escape '\\b' corrupted '\\beta'/'\\bar'/'\\binom'"),
    (re.compile(r"[\x07\x08\x0c\x0b]"), "control-char", "Unexpected ASCII control character inside text"),
]


def detect_escape_corruptions(text: str) -> list[dict[str, Any]]:
    """Detect Python string escape corruptions in Markdown/LaTeX documents."""
    issues: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for pat, hint, msg in _CORRUPT_SEQUENCES:
            m = pat.search(line)
            if m:
                issues.append(
                    {
                        "code": "LATEX_ESCAPE_CORRUPTION",
                        "severity": "error",
                        "line": line_no,
                        "hint": hint,
                        "message": f"Line {line_no}: {msg}.",
                    }
                )
                break
    return issues


def _omml_run(text: str) -> str:
    """Wrap literal text inside a Word OMML math run element."""
    if not text:
        return ""
    return f"<m:r><m:t>{html.escape(text)}</m:t></m:r>"


def _read_group(src: str, pos: int) -> tuple[str, int]:
    """Read a braced `{...}` group or single atom starting at `pos`."""
    n = len(src)
    while pos < n and src[pos].isspace():
        pos += 1
    if pos >= n:
        return "", pos
    if src[pos] == "{":
        depth = 0
        start = pos + 1
        i = pos
        while i < n:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    return src[start:i], i + 1
            i += 1
        raise ValueError("Unbalanced '{' in LaTeX expression.")
    if src[pos] == "\\":
        j = pos + 1
        while j < n and src[j].isalpha():
            j += 1
        if j == pos + 1 and j < n:
            j += 1
        return src[pos:j], j
    return src[pos], pos + 1


def _parse_expr(src: str) -> str:
    """Recursively convert a LaTeX expression into inner OMML child elements."""
    out: list[str] = []
    pos = 0
    n = len(src)

    while pos < n:
        ch = src[pos]
        if ch.isspace():
            pos += 1
            continue

        base_omml = ""
        if ch == "{":
            inner, pos = _read_group(src, pos)
            base_omml = _parse_expr(inner)
        elif ch == "\\":
            j = pos + 1
            while j < n and src[j].isalpha():
                j += 1
            cmd = src[pos + 1 : j]
            if not cmd and j < n:
                sym = src[j]
                pos = j + 1
                base_omml = _omml_run(sym)
            elif cmd == "frac":
                num_raw, pos = _read_group(src, j)
                den_raw, pos = _read_group(src, pos)
                base_omml = f"<m:f><m:num>{_parse_expr(num_raw)}</m:num><m:den>{_parse_expr(den_raw)}</m:den></m:f>"
            elif cmd == "sqrt":
                rad_raw, pos = _read_group(src, j)
                base_omml = f"<m:rad><m:deg/><m:e>{_parse_expr(rad_raw)}</m:e></m:rad>"
            elif cmd in {"text", "mathrm", "mathbf", "mathit"}:
                inner, pos = _read_group(src, j)
                base_omml = _omml_run(inner)
            elif cmd in _SYMBOLS:
                pos = j
                base_omml = _omml_run(_SYMBOLS[cmd])
            else:
                pos = j
                base_omml = _omml_run(cmd)
        else:
            pos += 1
            base_omml = _omml_run(ch)

        # Attach optional subscript (`_`) and superscript (`^`) modifiers cleanly
        sub_omml: str | None = None
        sup_omml: str | None = None
        while pos < n:
            while pos < n and src[pos].isspace():
                pos += 1
            if pos < n and src[pos] == "_" and sub_omml is None:
                sub_raw, pos = _read_group(src, pos + 1)
                sub_omml = _parse_expr(sub_raw)
            elif pos < n and src[pos] == "^" and sup_omml is None:
                sup_raw, pos = _read_group(src, pos + 1)
                sup_omml = _parse_expr(sup_raw)
            else:
                break

        if sub_omml is not None and sup_omml is not None:
            out.append(
                f"<m:sSubSup><m:e>{base_omml}</m:e><m:sub>{sub_omml}</m:sub><m:sup>{sup_omml}</m:sup></m:sSubSup>"
            )
        elif sub_omml is not None:
            out.append(f"<m:sSub><m:e>{base_omml}</m:e><m:sub>{sub_omml}</m:sub></m:sSub>")
        elif sup_omml is not None:
            out.append(f"<m:sSup><m:e>{base_omml}</m:e><m:sup>{sup_omml}</m:sup></m:sSup>")
        else:
            out.append(base_omml)

    return "".join(out)


def latex_to_omml(latex: str, display: bool = False) -> str:
    """Convert a LaTeX math expression into validated Word OMML XML."""
    expr = latex.strip()
    if expr.startswith("$$") and expr.endswith("$$") and len(expr) >= 4:
        expr = expr[2:-2].strip()
        display = True
    elif expr.startswith("$") and expr.endswith("$") and len(expr) >= 2:
        expr = expr[1:-1].strip()

    if expr.count("{") != expr.count("}"):
        raise ValueError("Unbalanced curly braces in LaTeX expression.")

    inner_xml = _parse_expr(expr)
    if display:
        omml = f'<m:oMathPara xmlns:m="{OMML_NS}"><m:oMath>{inner_xml}</m:oMath></m:oMathPara>'
    else:
        omml = f'<m:oMath xmlns:m="{OMML_NS}">{inner_xml}</m:oMath>'
    ET.fromstring(omml)
    return omml


class LatexToOmmlConverter:
    """Object-oriented wrapper for LaTeX validation and OMML generation."""

    def convert(self, latex: str, display: bool = False) -> str:
        """Convert LaTeX formula string to Word OMML XML."""
        return latex_to_omml(latex, display=display)
