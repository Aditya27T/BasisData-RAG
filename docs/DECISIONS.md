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

