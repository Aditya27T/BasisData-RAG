"""list — tampilkan semua dokumen yang sudah ter-ingest di workspace."""

from __future__ import annotations

import asyncio
import os
from typing import Optional


async def run(workspace: str | None = None) -> None:
    from app.providers_setup import configure
    configure()

    ws = workspace or os.getenv("WORKSPACE", "docs")

    from hybrid_rag.ingestion import workspace_pool
    from hybrid_rag.core.base import DocStatus

    try:
        async with workspace_pool.lease(ws) as rag:
            # Ambil semua dokumen yang sudah PROCESSED
            all_docs = await rag.doc_status.get_docs_by_statuses([
                DocStatus.PROCESSED,
                DocStatus.PROCESSING,
                DocStatus.FAILED,
                DocStatus.PENDING,
            ])
    except Exception as exc:
        print(f"✗ Gagal mengambil daftar dokumen: {exc}")
        raise SystemExit(1)

    if not all_docs:
        print(f"Workspace '{ws}': belum ada dokumen.")
        return

    print(f"Workspace: {ws}")
    print(f"Dokumen  : {len(all_docs)} item")
    print()

    # Header tabel
    print(f"{'No':>3}  {'Status':<12}  {'Doc ID':<20}  Nama File")
    print("─" * 70)

    for i, doc in enumerate(all_docs, 1):
        status = doc.get("status", "?")
        doc_id = doc.get("id", "?")
        short_id = doc_id[:18] + "…" if len(doc_id) > 18 else doc_id

        # Nama file bisa ada di field 'file_path' atau 'doc_name'
        file_name = (
            doc.get("file_path")
            or doc.get("doc_name")
            or doc.get("content_summary", "")[:40]
            or "?"
        )

        status_icon = {
            "PROCESSED": "✓",
            "FAILED": "✗",
            "PROCESSING": "⟳",
            "PENDING": "…",
        }.get(status, "?")

        print(f"{i:>3}  {status_icon} {status:<10}  {short_id:<20}  {file_name}")


def cmd_list(workspace: str | None = None) -> None:
    """Entry point dipanggil dari main.py."""
    asyncio.run(run(workspace=workspace))
