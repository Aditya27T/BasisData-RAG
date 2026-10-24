"""ask — tanya-jawab bersitasi berdasarkan dokumen yang sudah di-ingest.

Dua implementasi dengan kontrak sama (`app.answer.Answer`):
- `answer_question()`: fungsi biasa
- `ask_graph()`: dibungkus LangGraph (PRD v0.3 F14)

PRD F6: retrieval hybrid tanpa Neo4j
PRD F7: jawaban bersitasi berkas, halaman
PRD F8: penolakan bila konteks kosong atau tidak relevan
"""

from __future__ import annotations

import asyncio
import os
import sys


def _friendly_error(exc: Exception) -> str:
    """Pesan kuota yang jelas untuk 402/429 (PRD prinsip 5: berhenti, jangan ulang)."""
    message = str(exc)
    if "429" in message or "402" in message:
        return (
            "Kuota model LLM habis (HTTP 402/429). Tunggu reset kuota, "
            "tambah kredit, atau ganti LLM_MODEL. Detail: " + message[:200]
        )
    return message


async def run(
    question: str,
    workspace: str | None = None,
    return_parent: bool = False,
    verbose: bool = False,
    use_graph: bool = False,
) -> None:
    """Jawab satu pertanyaan dari dokumen di workspace."""
    from app.answer import answer_question
    from app.providers_setup import configure

    configure()

    ws = workspace or os.getenv("WORKSPACE", "docs")

    print(f"Pertanyaan : {question}")
    print(f"Workspace  : {ws}")
    print(f"Orkestrasi : {'langgraph' if use_graph else 'fungsi biasa'}")
    print()

    print("Menyusun jawaban...", end=" ", flush=True)
    try:
        if use_graph:
            from app.graph.ask_graph import ask_graph

            result = await ask_graph(question, workspace=ws, return_parent=return_parent)
        else:
            result = await answer_question(
                question, workspace=ws, return_parent=return_parent
            )
        print("✓")
    except Exception as exc:
        print(f"✗ Gagal: {_friendly_error(exc)}", file=sys.stderr)
        raise SystemExit(1) from exc

    if verbose:
        print(f"\n[debug] chunk ditemukan: {len(result.chunks)}")
        for i, chunk in enumerate(result.chunks[:3], 1):
            file_path = chunk.get("file_path", "?")
            print(f"  [{i}] {file_path} — {str(chunk.get('content', ''))[:60]}…")
        print(f"[debug] percobaan generate: {result.attempts}, panggilan LLM: {result.llm_calls}")
        print()

    if result.refused and result.problems:
        print(f"[tolak] {', '.join(result.problems)}", file=sys.stderr)

    print()
    print("─" * 60)
    print("Jawaban:")
    print(result.text)
    print("─" * 60)

    if result.sources_block:
        print()
        print(result.sources_block)

    if result.image_paths:
        print(f"\n[gambar] {', '.join(result.image_paths)}")


def cmd_ask(
    question: str,
    workspace: str | None = None,
    return_parent: bool = False,
    verbose: bool = False,
    use_graph: bool = False,
) -> None:
    """Entry point dipanggil dari main.py."""
    asyncio.run(
        run(
            question=question,
            workspace=workspace,
            return_parent=return_parent,
            verbose=verbose,
            use_graph=use_graph,
        )
    )
