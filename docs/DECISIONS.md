# DECISIONS.md

Catatan keputusan teknis dari hasil probe dan eksperimen.

## probe-embedding — 2026-10-24 15:00

**Status:** LULUS ✅  
**Provider:** `https://openrouter.ai/api/v1`  
**Model:** `BAAI/bge-m3`  
**Dimensi:** 1024 (diharap 1024)  
**Latensi rata-rata:** 1115.2 ms  

**Detail tes:**

- ✅ Dimensi: dapat 1024, harap 1024
- ✅ Latensi rata-rata: 1115.2 ms
- ✅ Similarity checks:
  - ✅ `Sistem RAG menggabungkan penca…` vs `RAG hybrid menggunakan vektor …` → sim=0.741 > sim=0.259 (ok)
  - ✅ `Sistem RAG menggabungkan penca…` vs `RAG hybrid menggunakan vektor …` → sim=0.741 > sim=0.386 (ok)

---

## probe-embedding — 2026-10-24 15:00

**Status:** GAGAL ❌  
**Provider:** `https://api-inference.huggingface.co/models/BAAI/bge-m3`  
**Model:** `BAAI/bge-m3`  
**Dimensi:** ? (diharap 1024)  
**Latensi rata-rata:** ? ms  

**Error:**

- Koneksi gagal: Connection error.

**Detail tes:**


---

## Keputusan implementasi — 2026-10-24

**Embedding: OpenRouter** (`https://openrouter.ai/api/v1`, `BAAI/bge-m3`, 1024d).
Endpoint lama Hugging Face (`api-inference.huggingface.co`) tidak lagi resolve (DNS),
dan router HF membalas 402 (kredit). OpenRouter lulus seluruh uji probe. Satu penyedia
dipakai untuk ingest dan query.

**Graf mati secara default.** `NEO4J_URI` kosong → `NullGraphStorage` (no-op); ekstraksi
KG dan merge dilewati, sementara ingestion/retrieval/deletion tetap berjalan. Diuji
end-to-end (ingest + ask) tanpa Neo4j.

**Contextualize per child dimatikan** (`ENABLE_CONTEXTUALIZE=false`) sesuai PRD v1.

**Parser.** md dibaca lokal; PDF/Office via LlamaParse dengan cache
`data/parsed/<sha256>.json`. Jalur cache diuji dengan cache sintetis; panggilan
LlamaParse live belum diuji karena API key masih placeholder.

**LLM.** `openrouter/free` (router model gratis) kadang membalas stub `User Safety: safe`.
`ask` melakukan satu retry lalu gagal dengan pesan jelas. Ekstraksi KG dengan model ini
masih gagal (butuh model yang patuh structured output); keputusan model milik pemilik proyek.


## M0.3b — dependensi LangGraph — 2026-10-24

**Versi di-pin:** `langgraph==1.2.17` (terbaru saat verifikasi).

**Kesesuaian dependensi:** `langgraph 1.2.17` butuh `langchain-core>=1.4.7,<2`; terpasang
`langchain-core 1.7.0`. Entry point `hybrid-rag` hanya memakai `langchain-core`, sehingga
tidak ada bentrok.

**Paket tambahan yang tertarik:** `langgraph-checkpoint`, `langgraph-prebuilt`,
`langgraph-sdk`, `xxhash`. Ukuran/waktu instalasi bertambah, tidak ada layanan baru.

**Penempatan:** LangGraph dipakai di aplikasi host (`app/graph/`) dan tidak ditambahkan
sebagai dependensi `hybrid-rag`, supaya engine tetap ringan dan bisa dipakai tanpa graf.

**Catatan implementasi:**
- `ask()` (fungsi biasa) dan `ask_graph()` memakai fungsi yang sama di `app/answer.py`;
  uji paritas `eval/parity.py` lulus 3/3 pada dokumen uji.
- Anggaran panggilan LLM terverifikasi: `attempts = 1 + LANGGRAPH_MAX_RETRIES`
  (diuji untuk 0, 1, 2 retry; sama pada kedua implementasi).
- `RETRIEVAL_MIN_SCORE` belum diaktifkan: `retrieve_context` tidak mengekspos skor per
  chunk, jadi `decide` memakai heuristik konteks kosong sampai eval M3 menetapkan ambang.
- `retrieve` memakai `return_parent` dari flag CLI (bukan dipaksa `True`) agar paritas
  `ask()` vs `ask_graph()` tetap terjaga untuk parameter yang sama.

## Migrasi LlamaParse ke Parse API v2 — 2026-10-24

**Sebab:** Parse API v1 menolak akun ini dengan HTTP 410 ("The v1 Parse API is not available
for this account"). Endpoint lama `api/parsing/upload|job/...` tidak bisa dipakai lagi.

**v2 yang dipakai:**
- `POST https://api.cloud.llamaindex.ai/api/v2/parse/upload` (multipart `file` +
  `configuration` JSON berisi `tier` dan `version`)
- `GET /api/v2/parse/{job_id}` untuk polling (`job.status`: `COMPLETED`/`FAILED`/`CANCELLED`)
- `GET /api/v2/parse/{job_id}?expand=markdown` untuk hasil per halaman
  (`markdown.pages[]` dengan `page_number`, `success`, `markdown`)

**Tier:** `cost_effective` + `version=latest` (default), bisa diubah lewat
`LLAMA_PARSE_TIER`/`LLAMA_PARSE_VERSION`. Dokumen uji 2 halaman berhasil (5 blok konten).

**Cache:** selalu dipakai untuk isi berkas yang sama (sha256); `--force` hanya menghapus
dokumen lama lalu ingest ulang, tidak memanggil LlamaParse lagi (PRD prinsip 4).

**Bug yang ditemukan dan diperbaiki:** pipeline memperlakukan doc_id yang sudah ada sebagai
duplikat dan menulis baris `dup-…` berstatus FAILED saat re-ingest. `ingest --force` kini
memanggil `delete_document(..., delete_llm_cache=False)` lebih dulu.
