"""Sitasi: label sumber yang dapat diverifikasi dari chunk hasil retrieval.

Engine mengembalikan referensi per berkas (`[1] nama.md`), tanpa nomor halaman
dan tanpa heading. PRD mensyaratkan sitasi `berkas, halaman`; untuk md dipakai
heading terdekat. Modul ini menurunkan label itu dari isi chunk dan sidecar
halaman (page_start/page_end) yang benar-benar diambil, lalu menyuapkannya ke
LLM dan mencetaknya ke pengguna.
"""

from __future__ import annotations

import re
from typing import Iterable

_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


def headings_in(content: str) -> list[str]:
    """Heading markdown yang muncul di dalam chunk, urut kemunculan."""
    found: list[str] = []
    for raw in _HEADING_RE.findall(content or ""):
        heading = raw.strip()
        if heading and heading not in found:
            found.append(heading)
    return found


def page_label(page_start: int | None, page_end: int | None) -> str | None:
    """Label halaman 1-based dari sidecar chunk (page_start/page_end 0-based)."""
    if page_start is None:
        return None
    try:
        first = int(page_start) + 1
    except (TypeError, ValueError):
        return None

    if page_end is None:
        return f"hal. {first}"
    try:
        last = int(page_end) + 1
    except (TypeError, ValueError):
        return f"hal. {first}"

    return f"hal. {first}" if last <= first else f"hal. {first}–{last}"


def build_sources(
    chunks: list[dict],
    pages_by_chunk: dict[str, dict] | None = None,
) -> list[dict]:
    """Satu entri per chunk yang diambil: reference_id, berkas, heading, halaman."""
    pages_by_chunk = pages_by_chunk or {}
    sources: list[dict] = []
    seen: set[tuple[str, tuple[str, ...], str | None]] = set()

    for chunk in chunks:
        ref = str(chunk.get("reference_id") or "?")
        headings = tuple(headings_in(chunk.get("content") or ""))

        sidecar = pages_by_chunk.get(str(chunk.get("chunk_id") or "")) or {}
        label = page_label(sidecar.get("page_start"), sidecar.get("page_end"))

        key = (ref, headings, label)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "reference_id": ref,
                "file_path": chunk.get("file_path") or "unknown_source",
                "headings": list(headings),
                "page_label": label,
                "page_first": _one_based(sidecar.get("page_start")),
                "page_last": _one_based(sidecar.get("page_end"))
                or _one_based(sidecar.get("page_start")),
                "chunk_id": chunk.get("chunk_id"),
            }
        )
    return sources


def render_sources(sources: list[dict]) -> str:
    """Blok teks sumber untuk prompt dan untuk ditampilkan setelah jawaban."""
    if not sources:
        return ""

    lines = ["Sumber yang diambil (nomor hanya indeks, bukan format sitasi):"]
    for source in sources:
        line = f"- ({source['reference_id']}) {source['file_path']}"
        details: list[str] = []
        if source.get("page_label"):
            details.append(source["page_label"])
        if source["headings"]:
            details.append("bagian: " + "; ".join(f'"{h}"' for h in source["headings"]))
        if details:
            line += " — " + ", ".join(details)
        lines.append(line)
    return "\n".join(lines)


def _one_based(value: object) -> int | None:
    """Konversi indeks halaman 0-based (sidecar) ke nomor halaman 1-based."""
    if value is None:
        return None
    try:
        return int(value) + 1
    except (TypeError, ValueError):
        return None


def chunk_ids(chunks: Iterable[dict]) -> list[str]:
    """ID chunk unik dari hasil retrieval."""
    ids: list[str] = []
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id and chunk_id not in ids:
            ids.append(chunk_id)
    return ids
