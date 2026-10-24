"""LlamaParse: parse PDF/Office menjadi content list, dengan cache di disk.

Alur:
1. `data/parsed/<sha256>.json` ada → pakai cache, tidak memanggil LlamaParse (PRD F2).
2. Belum ada → unggah ke LlamaCloud, tunggu job selesai, ambil hasil per halaman.
3. Simpan hasil ke cache secara atomik, lalu kembalikan content list.

Error kuota (402/429) dilempar sebagai :class:`LlamaQuotaError` — pemanggil
berhenti dan melanjutkan nanti, bukan retry tanpa batas (PRD prinsip 5).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

LLAMA_BASE_URL = "https://api.cloud.llamaindex.ai/api/v2/parse"
POLL_INTERVAL_SECONDS = 3.0
POLL_TIMEOUT_SECONDS = 900.0

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")


class LlamaParseError(RuntimeError):
    """Kegagalan umum saat memanggil LlamaParse."""


class LlamaQuotaError(LlamaParseError):
    """Kredit/kuota habis (402/429). Jangan diulang tanpa batas."""


class LlamaAuthError(LlamaParseError):
    """API key tidak valid atau tidak punya akses."""


def cache_path(parsed_dir: Path, sha256: str) -> Path:
    return parsed_dir / f"{sha256}.json"


def read_cache(parsed_dir: Path, sha256: str) -> list[dict] | None:
    """Kembalikan content list dari cache, atau None bila tidak ada/rusak."""
    path = cache_path(parsed_dir, sha256)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    content_list = payload.get("content_list")
    if isinstance(content_list, list) and content_list:
        return content_list
    return None


def write_cache(
    parsed_dir: Path,
    sha256: str,
    *,
    file_name: str,
    pages: list[dict[str, Any]],
    content_list: list[dict],
) -> Path:
    """Tulis cache secara atomik (tmp lalu rename)."""
    parsed_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(parsed_dir, sha256)
    tmp = path.with_suffix(".json.tmp")
    payload = {
        "file_name": file_name,
        "sha256": sha256,
        "page_count": len(pages),
        "pages": pages,
        "content_list": content_list,
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def markdown_to_content_list(pages: list[dict[str, Any]]) -> list[dict]:
    """Ubah markdown per halaman menjadi content list bergaya MinerU.

    Heading (`#..######`) menjadi item teks dengan ``text_level`` supaya engine
    membangun breadcrumb bagian; teks biasa menjadi item ``text``. ``page_idx``
    0-based mengikuti konvensi content list.
    """
    content_list: list[dict] = []

    for index, page in enumerate(pages):
        if page.get("success") is False:
            continue
        page_number = page.get("page_number") or page.get("page") or (index + 1)
        try:
            page_idx = max(0, int(page_number) - 1)
        except (TypeError, ValueError):
            page_idx = index

        markdown = str(page.get("markdown") or page.get("md") or "")
        buffer: list[str] = []

        def flush() -> None:
            text = "\n".join(buffer).strip()
            buffer.clear()
            if text:
                content_list.append({"type": "text", "text": text, "page_idx": page_idx})

        for line in markdown.splitlines():
            match = _HEADING_RE.match(line)
            if match:
                flush()
                content_list.append(
                    {
                        "type": "text",
                        "text": match.group(2).strip(),
                        "text_level": len(match.group(1)),
                        "page_idx": page_idx,
                    }
                )
            else:
                buffer.append(line)
        flush()

    return content_list


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    api_key: str,
    **kwargs: Any,
) -> httpx.Response:
    response = await client.request(
        method,
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        **kwargs,
    )
    if response.status_code in (402, 429):
        raise LlamaQuotaError(
            f"Kuota LlamaParse habis (HTTP {response.status_code}). "
            "Ingest dihentikan; lanjutkan setelah kredit/kuota tersedia."
        )
    if response.status_code in (401, 403):
        raise LlamaAuthError(
            f"LlamaParse menolak API key (HTTP {response.status_code}). "
            "Periksa LLAMA_CLOUD_API_KEY."
        )
    return response


async def _upload(
    client: httpx.AsyncClient, path: Path, api_key: str, tier: str, version: str
) -> str:
    configuration = json.dumps({"tier": tier, "version": version})
    with open(path, "rb") as handle:
        response = await _request(
            client,
            "POST",
            f"{LLAMA_BASE_URL}/upload",
            api_key=api_key,
            files={"file": (path.name, handle, "application/octet-stream")},
            data={"configuration": configuration},
        )
    if response.status_code >= 400:
        raise LlamaParseError(
            f"Upload LlamaParse gagal (HTTP {response.status_code}): {response.text[:300]}"
        )
    job_id = (response.json() or {}).get("id")
    if not job_id:
        raise LlamaParseError("LlamaParse tidak mengembalikan job id")
    return str(job_id)


async def _wait_for_job(client: httpx.AsyncClient, job_id: str, api_key: str) -> None:
    elapsed = 0.0
    while elapsed < POLL_TIMEOUT_SECONDS:
        response = await _request(
            client, "GET", f"{LLAMA_BASE_URL}/{job_id}", api_key=api_key
        )
        if response.status_code >= 400:
            raise LlamaParseError(
                f"Polling LlamaParse gagal (HTTP {response.status_code}): {response.text[:300]}"
            )
        job = (response.json() or {}).get("job") or {}
        status = str(job.get("status", "")).upper()
        if status == "COMPLETED":
            return
        if status in {"FAILED", "CANCELLED"}:
            detail = job.get("error_message") or ""
            raise LlamaParseError(
                f"Job LlamaParse berakhir dengan status {status}: {detail[:300]}"
            )
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS
    raise LlamaParseError(
        f"Job LlamaParse melewati batas tunggu {int(POLL_TIMEOUT_SECONDS)} detik"
    )


async def _fetch_pages(client: httpx.AsyncClient, job_id: str, api_key: str) -> list[dict]:
    response = await _request(
        client,
        "GET",
        f"{LLAMA_BASE_URL}/{job_id}",
        api_key=api_key,
        params={"expand": "markdown"},
    )
    if response.status_code >= 400:
        raise LlamaParseError(
            f"Mengambil hasil LlamaParse gagal (HTTP {response.status_code}): "
            f"{response.text[:300]}"
        )

    payload = response.json() or {}
    markdown_block = payload.get("markdown") or {}
    pages = markdown_block.get("pages")
    if isinstance(pages, list) and pages:
        return [page for page in pages if isinstance(page, dict)]

    markdown = payload.get("markdown_full")
    if isinstance(markdown, str) and markdown.strip():
        return [{"page_number": 1, "markdown": markdown, "success": True}]

    raise LlamaParseError("Hasil LlamaParse tidak memuat halaman markdown")


async def parse_to_content_list(
    path: Path,
    *,
    sha256: str,
    parsed_dir: Path,
    api_key: str | None,
    tier: str = "cost_effective",
    version: str = "latest",
) -> list[dict]:
    """Parse satu berkas PDF/Office.

    Cache selalu dipakai untuk isi berkas yang sama (sha256): PRD prinsip 4
    melarang memanggil LlamaParse dua kali. `--force` di CLI hanya memaksa
    ingest ulang, bukan parse ulang.
    """
    cached = read_cache(parsed_dir, sha256)
    if cached is not None:
        return cached

    if not api_key:
        raise LlamaParseError(
            "LLAMA_CLOUD_API_KEY belum diset. Berkas PDF/Office butuh LlamaParse; "
            "berkas .md/.txt tidak."
        )

    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        job_id = await _upload(client, path, api_key, tier, version)
        await _wait_for_job(client, job_id, api_key)
        pages = await _fetch_pages(client, job_id, api_key)

    content_list = markdown_to_content_list(pages)
    if not content_list:
        raise LlamaParseError("LlamaParse tidak menghasilkan teks apa pun")

    write_cache(
        parsed_dir,
        sha256,
        file_name=path.name,
        pages=pages,
        content_list=content_list,
    )
    return content_list
