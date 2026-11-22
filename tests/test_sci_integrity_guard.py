"""Deterministic offline test suite for sci-integrity-guard."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from sci_integrity_guard import (
    CitationVerifier,
    LatexToOmmlConverter,
    SciIntegrityGuard,
    check_cross_table_parity,
    check_prose_metric_anchors,
    detect_escape_corruptions,
    extract_dois,
    extract_markdown_tables,
    latex_to_omml,
)
from sci_integrity_guard.cli import main as cli_main


CLEAN_MANUSCRIPT = """
# Abstract
Our neuro-symbolic pipeline achieved a 94.50% accuracy score with an error reduction of 12.10% over baseline.

## Table 1: Primary Evaluation
| Model | Accuracy (%) | Latency (ms) |
| :--- | :---: | :---: |
| HardenedAgent | 94.50 | 42.10 |
| BaselineAgent | 84.30 | 31.00 |

## Table 2: Replication Split
| Model | Accuracy | Throughput |
| :--- | :---: | :---: |
| HardenedAgent | 94.52 | 120.0 |
| BaselineAgent | 84.30 | 95.0 |

The binding score satisfies $\\Delta G_{bind} = \\frac{\\alpha + \\beta}{2}$ with DOI https://doi.org/10.3390/a16100460.
"""


def test_cross_table_parity_passes_within_tolerance() -> None:
    issues = check_cross_table_parity(CLEAN_MANUSCRIPT, tolerance=0.05)
    assert issues == []


def test_cross_table_parity_detects_mismatch() -> None:
    bad_md = """
| Candidate | Score |
| :--- | :---: |
| ModelA | 91.20 |

| Candidate | Score |
| :--- | :---: |
| ModelA | 87.40 |
"""
    issues = check_cross_table_parity(bad_md, tolerance=0.05)
    assert len(issues) == 1
    assert issues[0]["code"] == "CROSS_TABLE_MISMATCH"
    assert issues[0]["delta"] == pytest.approx(3.8, abs=1e-4)


def test_extract_markdown_tables_handles_bold_and_units() -> None:
    tables = extract_markdown_tables(CLEAN_MANUSCRIPT)
    assert len(tables) == 2
    assert tables[0]["rows"][0]["numeric"]["Accuracy (%)"] == pytest.approx(94.5)


def test_prose_metric_anchors_accept_direct_and_derived_delta() -> None:
    # 94.50 appears directly; |94.50 - 84.30| / 84.30 * 100 = 12.10% appears as relative improvement
    issues = check_prose_metric_anchors(CLEAN_MANUSCRIPT)
    assert issues == []


def test_prose_metric_anchors_flag_orphaned_number() -> None:
    orphan_md = """
# Abstract
We achieved 99.87% precision across benchmarks.

| Method | Precision |
| :--- | :---: |
| MethodA | 88.10 |
"""
    issues = check_prose_metric_anchors(orphan_md)
    assert len(issues) == 1
    assert issues[0]["code"] == "ORPHANED_PROSE_METRIC"
    assert issues[0]["raw"] == "99.87"


def test_extract_dois_preserves_internal_semicolon_and_parens() -> None:
    text = (
        "See Lorenz (10.1175/1520-0469(1963)020<0130:DNF>2.0.CO;2), "
        "Pokushko (https://doi.org/10.3390/a16100460), and duplicate 10.3390/a16100460."
    )
    dois = extract_dois(text)
    assert dois == [
        "10.1175/1520-0469(1963)020<0130:DNF>2.0.CO;2",
        "10.3390/a16100460",
    ]


def test_citation_verifier_valid_404_and_mismatch(tmp_path) -> None:
    mock_db = {
        "10.3390/a16100460": {
            "source": "crossref",
            "doi": "10.3390/a16100460",
            "title": "Algorithm for Application of a Basic Model for the Data Envelopment Analysis Method in Technical Systems",
            "authors": ["Mariia Pokushko", "Roman Pokushko"],
        }
    }
    cache_file = tmp_path / "doi_cache.json"
    verifier = CitationVerifier(cache_path=str(cache_file), fetcher=lambda d: mock_db.get(d))

    ok = verifier.verify_doi("10.3390/a16100460", expected_title="Data Envelopment Analysis Method Technical Systems", expected_author="Roman Pokushko")
    assert ok["valid"] is True
    assert cache_file.exists()

    missing = verifier.verify_doi("10.9999/does-not-exist")
    assert missing["valid"] is False
    assert "failed to resolve" in missing["issues"][0]

    mismatch = verifier.verify_doi("10.3390/a16100460", expected_title="Quantum Gravity Black Holes")
    assert mismatch["valid"] is False
    assert "title mismatch" in mismatch["issues"][0]


def test_escape_corruption_detector_catches_broken_python_literals() -> None:
    broken = "Formula: $\x0crac{1}{2} \x09imes \x07lpha + \x08eta$"
    issues = detect_escape_corruptions(broken)
    assert len(issues) == 1
    assert issues[0]["code"] == "LATEX_ESCAPE_CORRUPTION"


def test_omml_conversion_produces_valid_xml_for_frac_greek_sub_sup() -> None:
    converter = LatexToOmmlConverter()
    omml = converter.convert(r"\Delta G_{bind}^{0} = \frac{\alpha + \beta}{\sqrt{2}} \times \Sigma_i")
    root = ET.fromstring(omml)
    assert root.tag.endswith("oMath")
    assert "<m:f>" in omml
    assert "<m:rad>" in omml
    assert "<m:sSubSup>" in omml
    assert "Δ" in omml and "α" in omml and "×" in omml

    display_omml = latex_to_omml(r"E = m c^2", display=True)
    droot = ET.fromstring(display_omml)
    assert droot.tag.endswith("oMathPara")


def test_omml_rejects_unbalanced_braces() -> None:
    with pytest.raises(ValueError, match="Unbalanced"):
        latex_to_omml(r"\frac{a}{b")


def test_guard_catches_local_path_leak_and_bad_math() -> None:
    leaky = r"Generated from D:\secret\run_model.py with $x = \frac{1{2}$."
    guard = SciIntegrityGuard()
    report = guard.check_markdown(leaky)
    codes = {i.code for i in report.issues}
    assert report.passed is False
    assert "INTERNAL_ARTIFACT_LEAK" in codes
    assert "INVALID_LATEX_SYNTAX" in codes


def test_cli_check_json_and_omml_subcommands(tmp_path, capsys) -> None:
    md_file = tmp_path / "paper.md"
    md_file.write_text(CLEAN_MANUSCRIPT, encoding="utf-8")

    rc = cli_main(["check", str(md_file), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert payload["summary"]["dois_found"] == 1

    rc_omml = cli_main(["omml", r"\frac{x^2}{y_1}"])
    assert rc_omml == 0
    xml_out = capsys.readouterr().out.strip()
    ET.fromstring(xml_out)
