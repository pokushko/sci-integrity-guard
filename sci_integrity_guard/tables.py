"""Cross-table numerical consistency and prose metric anchoring checks."""

from __future__ import annotations

import re
from typing import Any

_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*(?::?-{3,}:?\s*\|?)?\s*$")
_UNIT_PAREN_RE = re.compile(r"\s*\([^)]*\)")
_CLEAN_NUM_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_PREFIX_NUM_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*(?:%|ms|s|kcal/mol|da|g/mol)?$", re.IGNORECASE)
_PROSE_DECIMAL_RE = re.compile(r"(?<![.\w/])([+-]?\d+\.\d+)(?!\.\d)(?![\w/])")
_SECTION_HEADING_RE = re.compile(
    r"^\s{0,3}#{1,6}\s+(?:abstract|summary|conclusions?|аннотация|заключение|выводы)\b",
    re.IGNORECASE,
)
_ANY_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)


def _strip_markdown(text: str) -> str:
    """Remove inline Markdown formatting markers cleanly."""
    cleaned = re.sub(r"[*_`]", "", text)
    return " ".join(cleaned.strip().split())


def _canonical_key(text: str) -> str:
    """Normalize an entity name or metric header for comparison."""
    plain = _strip_markdown(text).lower()
    plain = _UNIT_PAREN_RE.sub("", plain)
    plain = re.sub(r"[^a-z0-9а-яё%]+", "_", plain, flags=re.IGNORECASE)
    return plain.strip("_")


def _parse_single_number(cell: str) -> float | None:
    """Parse a single scalar float from a Markdown table cell, skipping ranges."""
    raw = _strip_markdown(cell).replace(",", "").strip()
    if not raw or "±" in raw or "/" in raw and "kcal/mol" not in raw.lower():
        return None
    if re.search(r"\d\s*[-–]\s*\d", raw):
        return None
    m = _PREFIX_NUM_RE.match(raw) or _CLEAN_NUM_RE.match(raw)
    if not m:
        return None
    try:
        return float(m.group(1) if m.lastindex else raw)
    except ValueError:
        return None


def _split_row(line: str) -> list[str]:
    """Split a Markdown table row into stripped cells."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [_strip_markdown(c) for c in text.split("|")]


def extract_markdown_tables(markdown: str) -> list[dict[str, Any]]:
    """Parse all GFM Markdown tables into structured dictionaries."""
    clean_md = _FENCED_CODE_RE.sub("", markdown)
    lines = clean_md.splitlines()
    tables: list[dict[str, Any]] = []
    idx = 0
    table_num = 0

    while idx < len(lines) - 1:
        header_line = lines[idx]
        sep_line = lines[idx + 1]
        if "|" in header_line and _SEPARATOR_RE.match(sep_line):
            headers = _split_row(header_line)
            if len(headers) >= 2:
                table_num += 1
                rows: list[dict[str, Any]] = []
                idx += 2
                while idx < len(lines) and "|" in lines[idx] and lines[idx].strip():
                    cells = _split_row(lines[idx])
                    if len(cells) < len(headers):
                        cells.extend([""] * (len(headers) - len(cells)))
                    row_map: dict[str, str] = {}
                    numeric_map: dict[str, float] = {}
                    for h, val in zip(headers, cells):
                        row_map[h] = val
                        num = _parse_single_number(val)
                        if num is not None:
                            numeric_map[h] = num
                    rows.append(
                        {
                            "entity": cells[0],
                            "entity_key": _canonical_key(cells[0]),
                            "cells": row_map,
                            "numeric": numeric_map,
                        }
                    )
                    idx += 1
                tables.append({"table_index": table_num, "headers": headers, "rows": rows})
                continue
        idx += 1

    return tables


def check_cross_table_parity(markdown: str, tolerance: float = 0.05) -> list[dict[str, Any]]:
    """Verify matching (entity, metric) entries agree across tables within tolerance."""
    tables = extract_markdown_tables(markdown)
    seen: dict[tuple[str, str], list[tuple[int, float, str, str]]] = {}

    for tbl in tables:
        t_idx = int(tbl["table_index"])
        headers = tbl["headers"]
        for row in tbl["rows"]:
            e_key = row["entity_key"]
            if not e_key:
                continue
            for col in headers[1:]:
                if col not in row["numeric"]:
                    continue
                m_key = _canonical_key(col)
                if not m_key:
                    continue
                val = row["numeric"][col]
                seen.setdefault((e_key, m_key), []).append((t_idx, val, row["entity"], col))

    issues: list[dict[str, Any]] = []
    for (e_key, m_key), entries in seen.items():
        if len(entries) < 2:
            continue
        vals = [e[1] for e in entries]
        delta = max(vals) - min(vals)
        if delta > tolerance:
            issues.append(
                {
                    "code": "CROSS_TABLE_MISMATCH",
                    "severity": "error",
                    "entity": entries[0][2],
                    "metric": entries[0][3],
                    "entity_key": e_key,
                    "metric_key": m_key,
                    "values": [{"table": t, "value": v} for t, v, _, _ in entries],
                    "delta": round(delta, 6),
                    "message": (
                        f"Cross-table mismatch for '{entries[0][2]}' / '{entries[0][3]}': "
                        f"{[(t, v) for t, v, _, _ in entries]} (delta={delta:.4g} > {tolerance})."
                    ),
                }
            )
    return issues


def _extract_anchor_sections(markdown: str) -> str:
    """Collect text under Abstract/Summary/Conclusions headings."""
    lines = _FENCED_CODE_RE.sub("", markdown).splitlines()
    captured: list[str] = []
    active = False
    for line in lines:
        if _SECTION_HEADING_RE.match(line):
            active = True
            continue
        if _ANY_HEADING_RE.match(line):
            active = False
            continue
        if active and "|" not in line:
            captured.append(line)
    return "\n".join(captured)


def check_prose_metric_anchors(markdown: str, tolerance: float = 0.15) -> list[dict[str, Any]]:
    """Verify decimal metrics cited in Abstract/Conclusions appear in tables or derived deltas."""
    tables = extract_markdown_tables(markdown)
    prose = _extract_anchor_sections(markdown)
    if not tables or not prose.strip():
        return []

    table_vals: list[float] = []
    for tbl in tables:
        for row in tbl["rows"]:
            table_vals.extend(row["numeric"].values())

    if not table_vals:
        return []

    # Collect raw table numbers plus derived pairwise differences and relative percentages
    allowed: set[float] = {round(v, 4) for v in table_vals}
    for i, a in enumerate(table_vals):
        for j, b in enumerate(table_vals):
            if i == j:
                continue
            allowed.add(round(abs(a - b), 4))
            if abs(b) > 1e-9:
                allowed.add(round(abs(a - b) / abs(b) * 100.0, 4))

    # Strip URLs, DOIs, and explicit Table/Section/Eq identifiers before scanning decimals
    cleaned_prose = re.sub(r"https?://\S+|10\.\d{4,9}/\S+", " ", prose)
    cleaned_prose = re.sub(r"\b(?:Table|Figure|Section|Eq\.?|Equation)\s+\d+(?:\.\d+)*", " ", cleaned_prose, flags=re.IGNORECASE)

    issues: list[dict[str, Any]] = []
    seen_orphans: set[str] = set()
    for match in _PROSE_DECIMAL_RE.finditer(cleaned_prose):
        raw_num = match.group(1)
        val = float(raw_num)
        if any(abs(val - ref) <= tolerance or abs(abs(val) - abs(ref)) <= tolerance for ref in allowed):
            continue
        if raw_num in seen_orphans:
            continue
        seen_orphans.add(raw_num)
        issues.append(
            {
                "code": "ORPHANED_PROSE_METRIC",
                "severity": "warning",
                "value": val,
                "raw": raw_num,
                "message": (
                    f"Decimal metric '{raw_num}' in Abstract/Conclusions has no matching "
                    "anchor in parsed tables or derived pairwise deltas."
                ),
            }
        )
    return issues


class TableConsistencyGuard:
    """Facade running cross-table numerical parity and prose anchoring checks."""

    def __init__(self, tolerance: float = 0.05, anchor_tolerance: float = 0.15) -> None:
        self.tolerance = tolerance
        self.anchor_tolerance = anchor_tolerance

    def validate(self, markdown: str) -> list[dict[str, Any]]:
        """Return all cross-table and orphaned prose metric issues."""
        return check_cross_table_parity(markdown, tolerance=self.tolerance) + check_prose_metric_anchors(
            markdown, tolerance=self.anchor_tolerance
        )
