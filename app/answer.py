"""Fungsi biasa untuk alur tanya-jawab bersitasi.

Semua logika ada di sini sebagai fungsi biasa; `app/graph/ask_graph.py` hanya
membungkusnya menjadi graf (PRD v0.3 F14). `ask()` dan `ask_graph()` memakai
fungsi yang sama supaya keputusan dan sitasinya setara.

Simpul (SYSTEM_ANALYSIS bagian 16):
  retrieve → decide → generate → verify → (selesai | generate | refuse)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

REFUSAL = "Informasi tersebut tidak ditemukan di dokumen."

_SYSTEM_PROMPT = """\
Kamu adalah asisten yang menjawab pertanyaan HANYA berdasarkan dokumen yang \
diberikan dalam konteks di bawah ini. 

Aturan wajib:
1. Jawab HANYA dari informasi yang ada di konteks. Jangan menambah informasi \
dari pengetahuanmu sendiri.
2. Jika informasi tidak ada di konteks, jawab dengan tepat: \
"Informasi tersebut tidak ditemukan di dokumen."
3. Setiap klaim dalam jawaban HARUS disertai sitasi memakai NAMA BERKAS \
(bukan nomor indeks seperti [1]). Pilih format yang datanya tersedia, jangan \
mengarang nomor halaman:
   - [nama_berkas, "bagian"] bila nama bagian/heading tersedia
   - [nama_berkas, hal. N] bila nomor halaman tersedia di konteks
   - [nama_berkas] bila keduanya tidak tersedia
4. Jika konteks kosong atau tidak relevan dengan pertanyaan, jawab: \
"Informasi tersebut tidak ditemukan di dokumen."

Konteks dokumen:
{context}
"""

_DEGENERATE_RE = re.compile(r"^\s*(user\s+safety|safety)\s*:", re.IGNORECASE)
_CITATION_RE = re.compile(r"\[([^\[\]]+)\]")
_PAGE_RE = re.compile(r"hal\.?\s*(\d+)(?:\s*[–-]\s*(\d+))?", re.IGNORECASE)


@dataclass
class Retrieved:
    """Hasil simpul retrieve."""

    context: str = ""
    chunks: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    sources_block: str = ""
    image_paths: list[str] = field(default_factory=list)


@dataclass
class Answer:
    """Kontrak hasil yang sama untuk `ask()` dan `ask_graph()`."""

    question: str
    text: str
    refused: bool
    sources: list[dict] = field(default_factory=list)
    sources_block: str = ""
    chunks: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    attempts: int = 0
    llm_calls: int = 0
    image_paths: list[str] = field(default_factory=list)


def is_degenerate(text: str) -> bool:
    """Jawaban kosong atau stub keamanan, bukan jawaban dokumen."""
    stripped = (text or "").strip()
    return not stripped or bool(_DEGENERATE_RE.match(stripped))


def is_refusal(text: str) -> bool:
    """True bila jawaban persis kalimat penolakan yang diwajibkan prompt."""
    return (text or "").strip().rstrip(".") == REFUSAL.rstrip(".")


def is_context_sufficient(contexts: list[dict], min_score: float | None = None) -> bool:
    """Heuristik decide: konteks kosong → tidak cukup.

    Engine belum mengekspos skor per chunk, jadi `min_score` hanya dipakai bila
    suatu saat field `score` tersedia. Ambangnya baru ditetapkan setelah eval.
    """
    if not contexts:
        return False
    if min_score is None:
        return True

    scores = [
        float(chunk["score"])
        for chunk in contexts
        if isinstance(chunk.get("score"), (int, float))
    ]
    return bool(scores) and max(scores) >= min_score


async def retrieve(
    question: str,
    workspace: str | None = None,
    return_parent: bool = False,
) -> Retrieved:
    """Ambil konteks hybrid (vektor + BM25) dan label sumber yang bisa disitasi."""
    from hybrid_rag.retrieval import retrieve_context

    from app.citations import build_sources, chunk_ids, render_sources

    ws = workspace or os.getenv("WORKSPACE", "docs")
    result = await retrieve_context(
        question,
        workspace=ws,
        return_parent=return_parent,
        include_raw_data=True,
    )

    chunks = list((result.raw_data or {}).get("data", {}).get("chunks") or [])
    pages_by_chunk = await _load_page_sidecars(chunk_ids(chunks), ws)
    sources = build_sources(chunks, pages_by_chunk)

    return Retrieved(
        context=(result.context or "").strip(),
        chunks=chunks,
        sources=sources,
        sources_block=render_sources(sources),
        image_paths=list(result.image_paths or []),
    )


async def _load_page_sidecars(ids: list[str], ws: str) -> dict[str, dict]:
    """Baca page_start/page_end dari text_chunks (engine tidak membawanya)."""
    if not ids:
        return {}

    from hybrid_rag.retrieval import workspace_pool

    pages: dict[str, dict] = {}
    try:
        async with workspace_pool.lease(ws) as retriever:
            rows = await retriever.text_chunks.get_by_ids(ids)
        for row in rows or []:
            sidecar = row.get("sidecar") if isinstance(row, dict) else None
            if isinstance(sidecar, dict):
                pages[str(row.get("id"))] = sidecar
    except Exception:
        return {}
    return pages


async def generate_answer(question: str, context: str, sources_block: str) -> str:
    """Satu panggilan LLM dengan konteks bersumber."""
    from hybrid_rag import providers
    from hybrid_rag.config import settings
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = providers.get_llm(
        model_id=settings.llm_model,
        max_tokens=2048,
        base_url=settings.llm_binding_host,
        api_key=settings.llm_binding_api_key,
        temperature=0.0,
    )
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT.format(context=f"{context}\n\n{sources_block}".strip())),
        HumanMessage(content=question),
    ]
    response = await llm.ainvoke(messages)
    return response.content if isinstance(response.content, str) else str(response.content)


def citations_in(text: str) -> list[str]:
    """Semua sitasi `[...]` di dalam jawaban, urut kemunculan."""
    return _CITATION_RE.findall(text or "")


def verify_citations(answer: str, sources: list[dict]) -> list[str]:
    """Periksa jawaban terhadap sumber yang benar-benar diambil.

    Mengembalikan daftar masalah; kosong berarti lolos. Yang diperiksa:
    jawaban tidak kosong/stub, ada sitasi, berkas dikenal, halaman dan heading
    yang disebut memang ada di sumber.
    """
    if is_degenerate(answer):
        return ["jawaban kosong atau stub keamanan"]

    if is_refusal(answer):
        return []

    citations = citations_in(answer)
    if not citations:
        return ["jawaban tidak memuat sitasi"]

    by_file: dict[str, list[dict]] = {}
    for source in sources:
        by_file.setdefault(_basename(source["file_path"]), []).append(source)

    problems: list[str] = []
    for citation in citations:
        problem = _check_citation(citation, by_file)
        if problem and problem not in problems:
            problems.append(problem)
    return problems


def _check_citation(citation: str, by_file: dict[str, list[dict]]) -> str | None:
    parts = [part.strip() for part in citation.split(",", 1)]
    file_name = parts[0].strip().strip('"').strip("'")
    candidates = by_file.get(_basename(file_name))
    if not candidates:
        return f"sitasi merujuk berkas yang tidak diambil: {file_name}"
    if len(parts) == 1:
        return None

    detail = parts[1].strip().strip('"').strip("'")
    page = _PAGE_RE.search(detail)
    if page:
        wanted = int(page.group(1))
        upper = int(page.group(2)) if page.group(2) else wanted
        for source in candidates:
            first = source.get("page_first")
            last = source.get("page_last")
            if first is None:
                continue
            if first <= wanted and upper <= (last or first):
                return None
        return f"sitasi halaman di luar sumber: {citation}"

    headings = {
        heading.lower()
        for source in candidates
        for heading in source.get("headings") or []
    }
    if headings and detail.lower() not in headings:
        return f"sitasi bagian tidak ada di sumber: {citation}"
    return None


def _basename(file_path: str) -> str:
    return file_path.replace("\\", "/").rsplit("/", 1)[-1]


def build_refusal(
    question: str,
    *,
    sources: list[dict] | None = None,
    sources_block: str = "",
    chunks: list[dict] | None = None,
    problems: list[str] | None = None,
    attempts: int = 0,
    llm_calls: int = 0,
    image_paths: list[str] | None = None,
) -> Answer:
    """Jawaban penolakan dengan metadata yang sama seperti jawaban biasa."""
    return Answer(
        question=question,
        text=REFUSAL,
        refused=True,
        sources=list(sources or []),
        sources_block=sources_block,
        chunks=list(chunks or []),
        problems=list(problems or []),
        attempts=attempts,
        llm_calls=llm_calls,
        image_paths=list(image_paths or []),
    )


def max_retries_default() -> int:
    """`LANGGRAPH_MAX_RETRIES` — jumlah percobaan ulang generate setelah verify gagal."""
    raw = os.getenv("LANGGRAPH_MAX_RETRIES", "1")
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def min_score_default() -> float | None:
    """`RETRIEVAL_MIN_SCORE` — opsional, no-op sampai engine mengekspos skor."""
    raw = os.getenv("RETRIEVAL_MIN_SCORE", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def answer_question(
    question: str,
    workspace: str | None = None,
    return_parent: bool = False,
    max_retries: int | None = None,
    min_score: float | None = None,
) -> Answer:
    """Implementasi fungsi biasa (pembanding paritas untuk `ask_graph`)."""
    if max_retries is None:
        max_retries = max_retries_default()
    if min_score is None:
        min_score = min_score_default()

    retrieved = await retrieve(question, workspace=workspace, return_parent=return_parent)

    if not is_context_sufficient(retrieved.chunks, min_score):
        return build_refusal(
            question,
            sources=retrieved.sources,
            sources_block=retrieved.sources_block,
            chunks=retrieved.chunks,
            image_paths=retrieved.image_paths,
        )

    problems: list[str] = []
    attempts = 0
    for _ in range(max_retries + 1):
        answer = await generate_answer(question, retrieved.context, retrieved.sources_block)
        attempts += 1
        problems = verify_citations(answer, retrieved.sources)
        if not problems:
            return Answer(
                question=question,
                text=answer.strip(),
                refused=is_refusal(answer),
                sources=retrieved.sources,
                sources_block=retrieved.sources_block,
                chunks=retrieved.chunks,
                attempts=attempts,
                llm_calls=attempts,
                image_paths=retrieved.image_paths,
            )

    return build_refusal(
        question,
        sources=retrieved.sources,
        sources_block=retrieved.sources_block,
        chunks=retrieved.chunks,
        problems=problems,
        attempts=attempts,
        llm_calls=attempts,
        image_paths=retrieved.image_paths,
    )
