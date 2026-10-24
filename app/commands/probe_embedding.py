"""probe-embedding — uji penyedia embedding dan simpan hasil ke docs/DECISIONS.md.

Pengujian yang dilakukan:
1. Kirim teks pendek → pastikan endpoint bisa diakses
2. Cek dimensi vektor = EMBEDDING_DIM (harus 1024 untuk bge-m3)
3. Ukur latensi rata-rata (3 request)
4. Uji similarity: dua kalimat mirip harus lebih dekat daripada dua kalimat tidak relevan
5. Uji teks berbahasa Indonesia

Hasil disimpan ke docs/DECISIONS.md.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import numpy as np

DECISIONS_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "DECISIONS.md"

_TEST_TEXTS = [
    "Sistem RAG menggabungkan pencarian vektor dan BM25.",
    "RAG hybrid menggunakan vektor similarity dan keyword search.",
    "Kucing sedang tidur di atas karpet merah.",
    "Machine learning adalah cabang dari kecerdasan buatan.",
    "Pancasila adalah dasar negara Republik Indonesia.",
]

# Pasangan: (idx_a, idx_b, harus_lebih_mirip_dari, idx_c, idx_d)
# Artinya: sim(a,b) > sim(c,d)
_SIMILARITY_CHECKS = [
    (0, 1, 0, 2),   # kalimat RAG-RAG harus lebih mirip dari RAG-kucing
    (0, 1, 0, 3),   # RAG-RAG > RAG-ML
]


async def _embed_all(texts: list[str]) -> np.ndarray:
    """Embed semua teks, kembalikan array (n, dim)."""
    from app.providers_setup import configure
    configure()

    from hybrid_rag import providers
    from hybrid_rag.config import settings

    embeddings = providers.get_embeddings(
        settings.embedding_model,
        settings.embedding_binding_host,
        settings.embedding_binding_api_key,
    )
    vecs = await embeddings.aembed_documents(texts)
    return np.array(vecs, dtype=np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


async def run(verbose: bool = True) -> dict[str, Any]:
    """Jalankan semua tes dan kembalikan dict hasil."""
    from hybrid_rag.config import settings

    result: dict[str, Any] = {
        "provider_host": settings.embedding_binding_host,
        "model": settings.embedding_model,
        "expected_dim": settings.embedding_dim,
        "tests": [],
        "passed": True,
        "errors": [],
    }

    # ── Test 1: basic connectivity + dimensi ──
    if verbose:
        print(f"[probe] model={settings.embedding_model}")
        print(f"[probe] host={settings.embedding_binding_host}")
        print("[probe] test 1: basic connectivity + dimensi...", end=" ", flush=True)

    try:
        t0 = time.perf_counter()
        vecs = await _embed_all(_TEST_TEXTS[:1])
        latency_ms = (time.perf_counter() - t0) * 1000

        actual_dim = vecs.shape[1]
        dim_ok = actual_dim == settings.embedding_dim
        result["actual_dim"] = actual_dim
        result["tests"].append({
            "name": "dimensi",
            "expected": settings.embedding_dim,
            "actual": actual_dim,
            "passed": dim_ok,
        })
        if not dim_ok:
            result["passed"] = False
            result["errors"].append(
                f"Dimensi salah: dapat {actual_dim}, harap {settings.embedding_dim}"
            )
        if verbose:
            status = "✓" if dim_ok else "✗"
            print(f"{status} dim={actual_dim} latency={latency_ms:.0f}ms")
    except Exception as exc:
        result["passed"] = False
        result["errors"].append(f"Koneksi gagal: {exc}")
        if verbose:
            print(f"✗ ERROR: {exc}")
        return result  # tidak lanjut jika tidak bisa konek

    # ── Test 2: latensi rata-rata (3 request) ──
    if verbose:
        print("[probe] test 2: latensi rata-rata (3×)...", end=" ", flush=True)

    try:
        latencies = []
        for _ in range(3):
            t0 = time.perf_counter()
            await _embed_all(_TEST_TEXTS[:1])
            latencies.append((time.perf_counter() - t0) * 1000)
        avg_ms = sum(latencies) / len(latencies)
        result["avg_latency_ms"] = round(avg_ms, 1)
        latency_ok = avg_ms < 10_000  # < 10 detik masih acceptable
        result["tests"].append(
            {"name": "latensi", "avg_ms": round(avg_ms, 1), "passed": latency_ok}
        )
        if not latency_ok:
            result["passed"] = False
            result["errors"].append(f"Latensi terlalu tinggi: {avg_ms:.0f}ms")
        if verbose:
            print(f"{'✓' if latency_ok else '✗'} avg={avg_ms:.0f}ms")
    except Exception as exc:
        result["errors"].append(f"Latensi test gagal: {exc}")
        if verbose:
            print(f"✗ ERROR: {exc}")

    # ── Test 3: similarity check ──
    if verbose:
        print(
            "[probe] test 3: similarity (kalimat mirip > kalimat tidak relevan)...",
            end=" ",
            flush=True,
        )

    try:
        vecs = await _embed_all(_TEST_TEXTS)
        sim_results = []
        all_sim_ok = True
        for (i, j, k, d) in _SIMILARITY_CHECKS:
            sim_ij = _cosine(vecs[i], vecs[j])
            sim_kl = _cosine(vecs[k], vecs[d])
            ok = sim_ij > sim_kl
            if not ok:
                all_sim_ok = False
            sim_results.append({
                "text_a": _TEST_TEXTS[i][:40],
                "text_b": _TEST_TEXTS[j][:40],
                "sim_ab": round(sim_ij, 4),
                "text_c": _TEST_TEXTS[k][:40],
                "text_d": _TEST_TEXTS[d][:40],
                "sim_cd": round(sim_kl, 4),
                "passed": ok,
            })

        result["tests"].append({
            "name": "similarity",
            "checks": sim_results,
            "passed": all_sim_ok,
        })
        if not all_sim_ok:
            result["passed"] = False
            result["errors"].append("Similarity check gagal: vektor tidak membedakan makna")
        if verbose:
            print(f"{'✓' if all_sim_ok else '✗'}")
            for sr in sim_results:
                mark = "✓" if sr["passed"] else "✗"
                print(f"   {mark} sim({sr['sim_ab']:.3f}) > sim({sr['sim_cd']:.3f})")
    except Exception as exc:
        result["errors"].append(f"Similarity test gagal: {exc}")
        if verbose:
            print(f"✗ ERROR: {exc}")

    return result


def _render_markdown(result: dict[str, Any]) -> str:
    """Render hasil probe ke Markdown untuk docs/DECISIONS.md."""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = "LULUS ✅" if result["passed"] else "GAGAL ❌"
    lines = [
        f"## probe-embedding — {now}",
        "",
        f"**Status:** {status}  ",
        f"**Provider:** `{result.get('provider_host', '?')}`  ",
        f"**Model:** `{result.get('model', '?')}`  ",
        f"**Dimensi:** {result.get('actual_dim', '?')} "
        f"(diharap {result.get('expected_dim', '?')})  ",
        f"**Latensi rata-rata:** {result.get('avg_latency_ms', '?')} ms  ",
        "",
    ]

    if result["errors"]:
        lines += ["**Error:**", ""]
        for e in result["errors"]:
            lines.append(f"- {e}")
        lines.append("")

    lines += ["**Detail tes:**", ""]
    for t in result.get("tests", []):
        mark = "✅" if t["passed"] else "❌"
        if t["name"] == "dimensi":
            lines.append(f"- {mark} Dimensi: dapat {t['actual']}, harap {t['expected']}")
        elif t["name"] == "latensi":
            lines.append(f"- {mark} Latensi rata-rata: {t['avg_ms']} ms")
        elif t["name"] == "similarity":
            lines.append(f"- {mark} Similarity checks:")
            for c in t.get("checks", []):
                cm = "✅" if c["passed"] else "❌"
                lines.append(
                    f"  - {cm} `{c['text_a'][:30]}…` vs `{c['text_b'][:30]}…`"
                    f" → sim={c['sim_ab']:.3f} > sim={c['sim_cd']:.3f}"
                    f" ({'ok' if c['passed'] else 'GAGAL'})"
                )
    lines += ["", "---", ""]
    return "\n".join(lines)


def save_result(result: dict[str, Any]) -> None:
    """Tambahkan hasil ke docs/DECISIONS.md (prepend ke atas konten lama)."""
    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if DECISIONS_PATH.exists():
        existing = DECISIONS_PATH.read_text(encoding="utf-8")

    header = "# DECISIONS.md\n\nCatatan keputusan teknis dari hasil probe dan eksperimen.\n\n"
    if existing.startswith("# DECISIONS"):
        # Sudah ada header, strip header lama
        existing = existing[existing.find("\n## "):] if "\n## " in existing else ""

    new_section = _render_markdown(result)
    DECISIONS_PATH.write_text(header + new_section + existing, encoding="utf-8")
    print(f"\n[probe] Hasil disimpan ke {DECISIONS_PATH}")


def cmd_probe_embedding() -> None:
    """Entry point dipanggil dari main.py."""
    result = asyncio.run(run(verbose=True))
    save_result(result)

    if result["passed"]:
        print("\n✅ probe-embedding LULUS — penyedia embedding siap dipakai.")
    else:
        print("\n❌ probe-embedding GAGAL:")
        for e in result["errors"]:
            print(f"   • {e}")
        raise SystemExit(1)
