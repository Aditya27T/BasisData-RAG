"""ask — tanya-jawab bersitasi berdasarkan dokumen yang sudah di-ingest.

Alur:
1. retrieve_context() → konteks dari hybrid search (vektor + BM25)
2. Jika konteks kosong → tolak, jawab "tidak ditemukan di dokumen"
3. Panggil LLM dengan system prompt yang melarang mengarang
4. Cetak jawaban + sitasi (berkas, halaman)

PRD F6: retrieval hybrid tanpa Neo4j
PRD F7: jawaban bersitasi berkas, halaman
PRD F8: penolakan bila konteks kosong atau tidak relevan
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

_SYSTEM_PROMPT = """\
Kamu adalah asisten yang menjawab pertanyaan HANYA berdasarkan dokumen yang \
diberikan dalam konteks di bawah ini. 

Aturan wajib:
1. Jawab HANYA dari informasi yang ada di konteks. Jangan menambah informasi \
dari pengetahuanmu sendiri.
2. Jika informasi tidak ada di konteks, jawab dengan tepat: \
"Informasi tersebut tidak ditemukan di dokumen."
3. Setiap klaim dalam jawaban HARUS disertai sitasi. Pilih format yang datanya \
tersedia, jangan mengarang nomor halaman:
   - [nama_berkas, "bagian"] bila nama bagian/heading tersedia
   - [nama_berkas, hal. N] bila nomor halaman tersedia di konteks
   - [nama_berkas] bila keduanya tidak tersedia
4. Jika konteks kosong atau tidak relevan dengan pertanyaan, jawab: \
"Informasi tersebut tidak ditemukan di dokumen."

Konteks dokumen:
{context}
"""


async def _call_llm(question: str, context: str) -> str:
    """Panggil LLM dengan konteks dan pertanyaan."""
    from hybrid_rag import providers
    from hybrid_rag.config import settings

    llm = providers.get_llm(
        model_id=settings.llm_model,
        max_tokens=2048,
        base_url=settings.llm_binding_host,
        api_key=settings.llm_binding_api_key,
        temperature=0.0,
    )

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT.format(context=context)),
        HumanMessage(content=question),
    ]

    response = await llm.ainvoke(messages)
    return response.content


_DEGENERATE_RE = re.compile(r"^\s*(user\s+safety|safety)\s*:", re.IGNORECASE)


def _is_degenerate(answer: str) -> bool:
    """Jawaban kosong atau stub keamanan, bukan jawaban dokumen."""
    text = (answer or "").strip()
    return not text or bool(_DEGENERATE_RE.match(text))


async def _answer_with_guard(question: str, context: str) -> str:
    """Satu retry terbatas bila model membalas stub/kosong (PRD prinsip 5)."""
    answer = await _call_llm(question, context)
    if not _is_degenerate(answer):
        return answer

    print("(jawaban model tidak valid, mencoba sekali lagi)", file=sys.stderr)
    answer = await _call_llm(question, context)
    if _is_degenerate(answer):
        raise RuntimeError(
            "Model LLM mengembalikan jawaban tidak valid (stub keamanan/kosong) "
            "dua kali. Ganti LLM_MODEL ke model yang mendukung chat biasa."
        )
    return answer


async def run(
    question: str,
    workspace: str | None = None,
    return_parent: bool = False,
    verbose: bool = False,
) -> None:
    """Jawab satu pertanyaan dari dokumen di workspace."""
    from app.providers_setup import configure
    configure()

    ws = workspace or os.getenv("WORKSPACE", "docs")

    print(f"Pertanyaan : {question}")
    print(f"Workspace  : {ws}")
    print()

    # ── Retrieval ──
    try:
        from hybrid_rag.retrieval import retrieve_context

        result = await retrieve_context(
            question,
            workspace=ws,
            return_parent=return_parent,
            include_raw_data=True,
        )
    except Exception as exc:
        print(f"✗ Retrieval gagal: {exc}", file=sys.stderr)
        raise SystemExit(1)

    context = result.context.strip()
    chunks = (result.raw_data.get("data") or {}).get("chunks") or []

    from app.citations import build_sources, chunk_ids, render_sources

    # Sidecar chunk menyimpan page_start/page_end; engine tidak membawanya ke
    # hasil retrieval, jadi dibaca langsung dari text_chunks untuk sitasi halaman.
    pages_by_chunk: dict[str, dict] = {}
    ids = chunk_ids(chunks)
    if ids:
        try:
            from hybrid_rag.retrieval import workspace_pool

            async with workspace_pool.lease(ws) as retriever:
                rows = await retriever.text_chunks.get_by_ids(ids)
            for row in rows or []:
                sidecar = row.get("sidecar") if isinstance(row, dict) else None
                if isinstance(sidecar, dict):
                    pages_by_chunk[str(row.get("id"))] = sidecar
        except Exception as exc:
            print(f"[peringatan] gagal membaca metadata halaman: {exc}", file=sys.stderr)

    sources = build_sources(chunks, pages_by_chunk)
    sources_block = render_sources(sources)

    if verbose:
        print(f"[debug] chunk ditemukan: {len(chunks)}")
        for i, c in enumerate(chunks[:3], 1):
            fp = c.get("file_path", "?")
            print(f"  [{i}] {fp} — {c.get('content','')[:60]}…")
        print()

    # ── Penolakan dini ──
    if not context:
        print("─" * 60)
        print("Jawaban:\nInformasi tersebut tidak ditemukan di dokumen.")
        print("─" * 60)
        return

    # ── Generate jawaban ──
    print("Menyusun jawaban...", end=" ", flush=True)
    try:
        answer = await _answer_with_guard(
            question, f"{context}\n\n{sources_block}".strip()
        )
        print("✓")
    except Exception as exc:
        print(f"✗ LLM gagal: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print()
    print("─" * 60)
    print("Jawaban:")
    print(answer)
    print("─" * 60)

    if sources_block:
        print()
        print(sources_block)

    # ── Cetak path gambar jika ada ──
    if result.image_paths:
        print(f"\n[gambar] {', '.join(result.image_paths)}")


def cmd_ask(
    question: str,
    workspace: str | None = None,
    return_parent: bool = False,
    verbose: bool = False,
) -> None:
    """Entry point dipanggil dari main.py."""
    asyncio.run(run(
        question=question,
        workspace=workspace,
        return_parent=return_parent,
        verbose=verbose,
    ))
