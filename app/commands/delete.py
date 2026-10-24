"""delete — hapus dokumen dari workspace.

Menghapus dari: PGVectorStorage, PGKVStorage, PGDocStatusStorage,
                Neo4JStorage (jika aktif), dan cache parse di disk.

PRD F9: delete menghapus data di Postgres, Neo4j (bila aktif), dan cache parse.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional


PARSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "parsed"


async def run(
    doc_id: str,
    workspace: str | None = None,
    yes: bool = False,
) -> None:
    from app.providers_setup import configure
    configure()

    ws = workspace or os.getenv("WORKSPACE", "docs")

    # ── Konfirmasi ──
    if not yes:
        confirm = input(
            f"Hapus doc_id={doc_id!r} dari workspace={ws!r}? [y/N] "
        ).strip().lower()
        if confirm != "y":
            print("Dibatalkan.")
            return

    print(f"Menghapus {doc_id!r} dari workspace '{ws}'...", end=" ", flush=True)

    try:
        from hybrid_rag.ingestion import delete_document

        await delete_document(doc_id=doc_id, workspace=ws)
        print("✓")
    except Exception as exc:
        print(f"✗\nGagal: {exc}", file=sys.stderr)
        raise SystemExit(1)

    # ── Hapus cache parse di disk (jika ada) ──
    # Cache disimpan sebagai data/parsed/<sha256>.json
    # doc_id biasanya "doc-<sha256>", strip prefix "doc-"
    raw_hash = doc_id.removeprefix("doc-")
    cache_file = PARSED_DIR / f"{raw_hash}.json"
    if cache_file.exists():
        cache_file.unlink()
        print(f"Cache parse dihapus: {cache_file.name}")

    print("Selesai.")


def cmd_delete(
    doc_id: str,
    workspace: str | None = None,
    yes: bool = False,
) -> None:
    """Entry point dipanggil dari main.py."""
    asyncio.run(run(doc_id=doc_id, workspace=workspace, yes=yes))
