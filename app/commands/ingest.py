"""ingest — masukkan file dari data/originals/ ke workspace.

Alur:
1. Hitung sha256 isi file → doc_id (idempoten: file yang sama tidak diproses ulang)
2. Cek doc_id sudah ada di doc_status → skip jika PROCESSED
3. Untuk .md/.txt: baca langsung
4. Untuk .pdf/.docx/.pptx: via LlamaParse (M2, belum diimplementasi)
5. insert_content_list() → chunking + embedding + simpan ke ParadeDB

PRD F1: ingest berkas yang sama dua kali tidak menggandakan chunk.
PRD F3: md ter-ingest tanpa LLAMA_CLOUD_API_KEY.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

from app.parsing.llamaparse import LlamaQuotaError as _LlamaQuotaError

ORIGINALS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "originals"
PARSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "parsed"

# Ekstensi yang diproses lokal (tanpa cloud)
_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
# Ekstensi yang butuh LlamaParse
_LLAMAPARSE_EXTENSIONS = {".pdf", ".docx", ".pptx", ".doc", ".ppt"}


def _sha256_file(path: Path) -> str:
    """Hitung sha256 hex dari isi file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_text_as_content_list(path: Path) -> list[dict]:
    """Baca file teks/md → content_list format hybrid_rag."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [{"type": "text", "text": text, "page_idx": 0}]


async def _parse_with_llamaparse(path: Path, doc_id: str) -> list[dict]:
    """Parse PDF/Office lewat LlamaParse; hasil di-cache di data/parsed/."""
    from hybrid_rag.config import settings

    from app.parsing.llamaparse import parse_to_content_list

    return await parse_to_content_list(
        path,
        sha256=doc_id.removeprefix("doc-"),
        parsed_dir=PARSED_DIR,
        api_key=settings.llama_cloud_api_key,
        tier=settings.llama_parse_tier,
        version=settings.llama_parse_version,
    )


async def _is_already_processed(doc_id: str, workspace: str) -> bool:
    """Cek apakah doc_id sudah PROCESSED di storage."""
    try:
        from hybrid_rag.core.base import DocStatus
        from hybrid_rag.ingestion import workspace_pool

        async with workspace_pool.lease(workspace) as rag:
            doc = await rag.doc_status.get_by_id(doc_id)
            if doc and doc.get("status") == DocStatus.PROCESSED:
                return True
    except Exception:
        pass
    return False


async def _ingest_one(
    path: Path,
    workspace: str,
    force: bool = False,
) -> dict:
    """Ingest satu file. Kembalikan dict status."""
    ext = path.suffix.lower()
    result = {
        "file": path.name,
        "doc_id": None,
        "status": "unknown",
        "message": "",
    }

    # ── Cek dukungan ekstensi ──
    if ext not in _TEXT_EXTENSIONS and ext not in _LLAMAPARSE_EXTENSIONS:
        result["status"] = "skip"
        result["message"] = f"Ekstensi {ext} tidak didukung"
        return result

    # ── Hitung doc_id dari sha256 isi file ──
    doc_id = "doc-" + _sha256_file(path)
    result["doc_id"] = doc_id

    # ── Cek duplikat ──
    if not force and await _is_already_processed(doc_id, workspace):
        result["status"] = "skip"
        result["message"] = "Sudah ter-ingest (doc_id sama)"
        return result

    # ── Parse ──
    try:
        if ext in _TEXT_EXTENSIONS:
            content_list = _read_text_as_content_list(path)
        else:
            content_list = await _parse_with_llamaparse(path, doc_id)
    except _LlamaQuotaError as exc:
        result["status"] = "quota"
        result["message"] = str(exc)
        return result
    except Exception as exc:
        result["status"] = "error"
        result["message"] = f"Parse gagal: {exc}"
        return result

    # ── --force: hapus dulu supaya pipeline tidak mencatat baris dup- FAILED ──
    # Pipeline memperlakukan doc_id yang sudah ada sebagai duplikat (membuat
    # record "dup-" berstatus FAILED). Re-ingest harus menghapus yang lama dulu.
    if force:
        from hybrid_rag.ingestion import delete_document

        await delete_document(doc_id=doc_id, workspace=workspace, delete_llm_cache=False)

    # ── Insert ke storage ──
    try:
        from hybrid_rag.core.base import DocStatus
        from hybrid_rag.ingestion import workspace_pool

        async with workspace_pool.lease(workspace) as rag:
            await rag.insert_content_list(
                content_list,
                file_path=path.name,
                doc_id=doc_id,
                save_parent=True,
            )
            # Pipeline menelan kegagalan per-dokumen dan menandainya FAILED;
            # baca status akhir supaya CLI tidak melaporkan "berhasil" palsu.
            status_doc = await rag.doc_status.get_by_id(doc_id) or {}

        final_status = status_doc.get("status")
        if final_status == DocStatus.FAILED:
            error_msg = status_doc.get("error_msg") or "tahap pipeline gagal"
            result["status"] = "error"
            result["message"] = f"Pipeline FAILED: {error_msg}"
            return result

        result["status"] = "ok"
        result["message"] = f"Berhasil ({len(content_list)} blok konten)"
    except Exception as exc:
        result["status"] = "error"
        result["message"] = f"Insert gagal: {exc}"

    return result


async def run(
    files: list[str] | None = None,
    workspace: str | None = None,
    force: bool = False,
) -> None:
    """Ingest satu atau beberapa file. Jika files=None, proses semua di data/originals/."""
    from app.providers_setup import configure
    configure()

    ws = workspace or os.getenv("WORKSPACE", "docs")

    # Tentukan file yang akan diproses
    if files:
        paths = [Path(f).expanduser().resolve() for f in files]
    else:
        paths = sorted(ORIGINALS_DIR.glob("*"))
        paths = [p for p in paths if p.is_file() and not p.name.startswith(".")]

    if not paths:
        print("Tidak ada file untuk diproses.")
        return

    print(f"Workspace : {ws}")
    print(f"File      : {len(paths)} item")
    print()

    ok = skip = error = quota = 0
    for path in paths:
        if not path.exists():
            print(f"  ✗ {path.name} — file tidak ditemukan")
            error += 1
            continue

        print(f"  ⟳ {path.name}...", end=" ", flush=True)
        result = await _ingest_one(path, ws, force=force)

        if result["status"] == "ok":
            print(f"✓  {result['message']}")
            if result["doc_id"]:
                print(f"     doc_id: {result['doc_id']}")
            ok += 1
        elif result["status"] == "skip":
            print(f"⏭  {result['message']}")
            skip += 1
        elif result["status"] == "quota":
            # PRD prinsip 5: berhenti, jangan ulang tanpa batas. Sisa file
            # menunggu kredit/kuota tersedia; cache parse tetap dipakai.
            print(f"⛔ {result['message']}", file=sys.stderr)
            quota += 1
            break
        else:
            print(f"✗  {result['message']}", file=sys.stderr)
            error += 1

    print()
    print(f"Selesai: {ok} berhasil, {skip} dilewati, {error} gagal")
    if quota:
        print("Dihentikan karena kuota LlamaParse habis; jalankan ingest lagi nanti.")


def cmd_ingest(
    files: list[str] | None = None,
    workspace: str | None = None,
    force: bool = False,
) -> None:
    """Entry point dipanggil dari main.py."""
    asyncio.run(run(files=files, workspace=workspace, force=force))
