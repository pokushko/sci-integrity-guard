# Sci Integrity Guard

[![CI](https://github.com/pokushko/sci-integrity-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/pokushko/sci-integrity-guard/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![EvoNova Labs Ecosystem](https://img.shields.io/badge/EvoNova_Labs-Resilience_Stack-00F0FF)](https://github.com/pokushko/awesome-autonomous-agent-resilience)

**Zero-dependency neuro-symbolic integrity linter for AI-assisted manuscripts, technical reports, and grant proposals.**

Catches silent hallucinations before peer review or publication:
1. **Cross-Table Numerical Parity:** Flags matching `(entity, metric)` discrepancies across Markdown tables.
2. **Prose-to-Table Metric Anchoring:** Ensures decimal numbers in `Abstract` / `Conclusions` tie directly to tables or derived pairwise deltas (`|% diff|`).
3. **CrossRef & OpenAlex DOI Verification:** Preserves complex suffixes (including `<...>`, `(year)`, and `;2`) and validates DOI resolution + title/author overlap with disk caching.
4. **LaTeX Escape Guard & Word OMML Compiler:** Catches Python string-escape corruptions (`\x0crac` -> `\frac`) and converts LaTeX formulas into validated Microsoft Word `<m:oMath>` / `<m:oMathPara>` XML.
5. **Internal Artifact Anti-Leak:** Flags local OS paths and `.py`/`.log` filenames left in academic prose.

---

## Quickstart

```bash
git clone https://github.com/pokushko/sci-integrity-guard.git
cd sci-integrity-guard
pip install -e .
```

### CLI Usage

```bash
# Run offline structural, table parity, LaTeX, and anti-leak checks
sci-guard check manuscript.md

# Also verify all extracted DOIs against CrossRef / OpenAlex
sci-guard check manuscript.md --verify-dois --json

# Convert LaTeX equation to validated Word OMML XML
sci-guard omml "\Delta G_{bind} = \frac{\alpha + \beta}{2}" --display
```

### Python API

```python
from sci_integrity_guard import SciIntegrityGuard, latex_to_omml

guard = SciIntegrityGuard(tolerance=0.05)
report = guard.check_markdown(open("manuscript.md", encoding="utf-8").read())

if not report.passed:
    print(report.to_json())

omml_xml = latex_to_omml(r"\frac{1}{\sigma \sqrt{2\pi}}")
```

---

## Verification & Tests

```bash
pip install pytest ruff
ruff check --select E,F --ignore E501 .
pytest -v
```

---

## 🌐 EvoNova Labs Open-Source Ecosystem

Part of the **[EvoNova Labs](https://pokushko.github.io)** open-source AI resilience & scientific integrity stack by **[Roman Pokushko](https://github.com/pokushko)**:

| Project | Role in Stack | Link |
| :--- | :--- | :--- |
| **Awesome Agent Resilience** | Curated index (`160` entries), MAST/OWASP Failure Taxonomy & `F01–F10` chaos benchmark | [pokushko/awesome-autonomous-agent-resilience](https://github.com/pokushko/awesome-autonomous-agent-resilience) |
| **AgentBunker** | 24/7 WAL intent journal, RSS memory ceiling watchdog & tri-state circuit breakers | [pokushko/agent-bunker](https://github.com/pokushko/agent-bunker) |
| **Orchestration Engine** | Zero-dependency `asyncio` MAS router, Kahn DAG waves & consensus reducers | [pokushko/orchestration-engine](https://github.com/pokushko/orchestration-engine) |
| **Agent Security Sandbox** | Pre-flight Python AST guard against dunder escapes & prompt-injection sanitizer | [pokushko/agent-security-sandbox](https://github.com/pokushko/agent-security-sandbox) |
| **Agentic Vector Memory** | Dual-store episodic & semantic memory with exponential decay & SQLite persistence | [pokushko/agentic-vector-memory](https://github.com/pokushko/agentic-vector-memory) |
| **EvoNova Causal Guard** | Pearl *do*-calculus DAG verifier, Tabu memory & multi-agent debate arbiter | [pokushko/evonova-causal-guard](https://github.com/pokushko/evonova-causal-guard) |
| **Sci Integrity Guard** | Cross-table numeric parity linter, CrossRef/OpenAlex DOI checker & LaTeX-to-OMML | [pokushko/sci-integrity-guard](https://github.com/pokushko/sci-integrity-guard) |
| **KTK ELOU-AVT Core** | Industrial cybernetic digital twin prototype for crude oil ELOU-AVT units | [pokushko/ktk_elou_avt_core](https://github.com/pokushko/ktk_elou_avt_core) |
| **EvoNova Chem Core** | RDKit molecular descriptor screening core for physical constraint enforcement | [pokushko/evonova-chem-core](https://github.com/pokushko/evonova-chem-core) |

---

## License

MIT License. Copyright (c) 2026 [Roman Pokushko](mailto:pokusko.roman@gmail.com). See [LICENSE](LICENSE).
