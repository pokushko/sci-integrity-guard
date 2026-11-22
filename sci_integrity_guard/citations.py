"""DOI extraction and CrossRef / OpenAlex semantic citation verification."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'|]+)")


def _clean_doi_candidate(raw: str) -> str:
    """Strip trailing punctuation while preserving valid internal DOI punctuation like `;2` or `<...>`."""
    candidate = raw.strip().rstrip(".,;:")
    for opener, closer in (("(", ")"), ("[", "]"), ("<", ">")):
        while candidate.endswith(closer) and candidate.count(closer) > candidate.count(opener):
            candidate = candidate[:-1].rstrip(".,;:")
    return candidate


def extract_dois(text: str) -> list[str]:
    """Extract unique DOIs preserving order and complex journal suffixes (e.g. `;2`)."""
    seen: set[str] = set()
    dois: list[str] = []
    for m in _DOI_RE.finditer(text):
        cleaned = _clean_doi_candidate(m.group(1))
        # Handle markdown link syntax like [doi](https://doi.org/10.1000/xyz)
        if "](" in cleaned:
            cleaned = cleaned.split("](")[0]
            cleaned = _clean_doi_candidate(cleaned)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            dois.append(cleaned)
    return dois


def _default_fetcher(doi: str) -> dict[str, Any] | None:
    """Query CrossRef API with OpenAlex fallback for DOI metadata."""
    quoted = urllib.parse.quote(doi, safe="/")
    crossref_url = f"https://api.crossref.org/works/{quoted}"
    headers = {"User-Agent": "sci-integrity-guard/1.0 (mailto:pokusko.roman@gmail.com)"}
    try:
        req = urllib.request.Request(crossref_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            msg = payload.get("message", {})
            titles = msg.get("title") or []
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in msg.get("author", [])
                if a.get("family") or a.get("given")
            ]
            return {
                "source": "crossref",
                "doi": doi,
                "title": titles[0] if titles else "",
                "authors": authors,
            }
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        pass

    openalex_url = f"https://api.openalex.org/works/https://doi.org/{quoted}"
    try:
        req = urllib.request.Request(openalex_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in payload.get("authorships", [])
                if a.get("author", {}).get("display_name")
            ]
            return {
                "source": "openalex",
                "doi": doi,
                "title": payload.get("title") or "",
                "authors": authors,
            }
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _token_overlap(expected: str, actual: str) -> float:
    """Compute Jaccard-style recall overlap of alphanumeric words >= 3 chars."""
    exp_tokens = {w for w in re.findall(r"[a-z0-9а-яё]{3,}", expected.lower())}
    if not exp_tokens:
        return 1.0
    act_tokens = {w for w in re.findall(r"[a-z0-9а-яё]{3,}", actual.lower())}
    return len(exp_tokens & act_tokens) / len(exp_tokens)


class CitationVerifier:
    """Verify DOI resolution and optional metadata alignment with disk caching."""

    def __init__(
        self,
        cache_path: str | None = None,
        fetcher: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        self.cache_path = Path(cache_path) if cache_path else None
        self.fetcher = fetcher or _default_fetcher
        self._cache: dict[str, dict[str, Any] | None] = {}
        if self.cache_path and self.cache_path.exists():
            try:
                loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._cache = loaded
            except (OSError, json.JSONDecodeError):
                self._cache = {}

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def resolve(self, doi: str) -> dict[str, Any] | None:
        """Resolve metadata for a DOI from cache or upstream registries."""
        key = doi.lower()
        if key in self._cache:
            return self._cache[key]
        meta = self.fetcher(doi)
        self._cache[key] = meta
        self._save_cache()
        return meta

    def verify_doi(
        self,
        doi: str,
        expected_title: str | None = None,
        expected_author: str | None = None,
    ) -> dict[str, Any]:
        """Validate a DOI resolves and optionally matches title and author fragments."""
        meta = self.resolve(doi)
        if not meta:
            return {
                "doi": doi,
                "valid": False,
                "source": None,
                "title": "",
                "authors": [],
                "issues": [f"DOI '{doi}' failed to resolve via CrossRef or OpenAlex."],
            }

        issues: list[str] = []
        actual_title = str(meta.get("title") or "")
        actual_authors = [str(a) for a in meta.get("authors") or []]

        if expected_title:
            overlap = _token_overlap(expected_title, actual_title)
            if overlap < 0.5:
                issues.append(
                    f"DOI '{doi}' title mismatch (overlap={overlap:.2f}): expected '{expected_title}', got '{actual_title}'."
                )

        if expected_author:
            author_blob = " ".join(actual_authors)
            if _token_overlap(expected_author, author_blob) < 0.5:
                issues.append(
                    f"DOI '{doi}' author mismatch: '{expected_author}' not found in {actual_authors}."
                )

        return {
            "doi": doi,
            "valid": len(issues) == 0,
            "source": meta.get("source"),
            "title": actual_title,
            "authors": actual_authors,
            "issues": issues,
        }
