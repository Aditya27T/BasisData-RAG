# DECISIONS.md

Catatan keputusan teknis dari hasil probe dan eksperimen.

## VLM gratis melalui OpenRouter — 2026-10-29

**VLM:** `nvidia/nemotron-3.5-super-vl:free`. Katalog OpenRouter mencatat input
gambar, `response_format`, dan `structured_outputs` dengan harga prompt serta
completion nol. Probe nyata membaca teks `RAG 42` dan warna persegi panjang dari
gambar PNG ke skema Pydantic tanpa error.

VLM memakai host dan API key OpenRouter dari `LLM_BINDING_*`; tidak ada provider
fallback. Konkurensi dibatasi satu karena model gratis memiliki rate limit dan
ketersediaannya dapat berubah. Model berjalan di provider, sehingga tidak menambah
beban model pada laptop RAM 8 GB.

---

## Keputusan embedding lokal — 2026-10-29

**Embedding: Ollama lokal** (`http://localhost:11434/v1`, `bge-m3`, 1024d).
Hugging Face membutuhkan kredit dan OpenRouter tetap merupakan layanan berbayar,
sehingga embedding dipindahkan ke runtime lokal tanpa biaya per request. OpenRouter
tetap dapat dipakai untuk LLM jawaban, tetapi bukan untuk embedding.

Tidak ada fallback embedding otomatis. Mengganti runtime atau model mewajibkan
penghapusan tabel vektor lama dan ingest ulang agar vektor dari penyedia berbeda
tidak tercampur. Konkurensi embedding dibatasi satu untuk mesin RAM 8 GB.

---

## Kerangka evaluasi M3 — 2026-10-29

CLI `cobarag eval` menjalankan baseline A (seluruh dokumen), baseline B
(hybrid retrieval tanpa graf), dan baseline C (hybrid retrieval dengan Neo4j)
secara serial. Satu panggilan judge per jawaban non-penolakan menilai correctness
dan faithfulness; panggilan jawaban dan judge dihitung terpisah. Laporan JSON dan
Markdown disimpan di `eval/reports/`.

Dataset resmi tetap harus ditulis pemilik sebelum evaluasi pertama: 20-30 pertanyaan,
minimal lima kasus penolakan, jawaban acuan, dan sumber heading atau halaman.
Kerangka tersedia, tetapi M3/M4 belum selesai sampai `eval/questions.yaml` tersedia,
dokumen di-ingest ulang dengan graf aktif, dan laporan A/B/C berhasil dibuat.
Jumlah token embedding dilaporkan sebagai tidak tersedia karena engine belum
mengekspos metrik tersebut.

---

## Neo4j aktif dan baseline C — 2026-10-29

Neo4j dipakai untuk ekstraksi entitas/relasi saat ingest dan untuk retrieval normal.
`NEO4J_URI` menjadi gerbang runtime. Endpoint Aura lama tidak lagi dapat di-resolve
melalui DNS, sehingga konfigurasi aktif dan `.env.example` memakai service lokal
dari profile Docker `graph`.

`QueryParam.include_graph` memisahkan eksperimen tanpa mengubah konfigurasi global:
baseline B memaksakan graf mati per query, baseline C memakai Neo4j, dan `ask` normal
memakai graf. Laporan evaluasi mencatat jumlah entitas dan relasi yang dikembalikan
serta selisih C terhadap B.

Dokumen harus di-ingest ulang setelah graf diaktifkan. Tanpa re-ingest, Neo4j tidak
memiliki node dan relasi untuk baseline C.

---

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

**Embedding: OpenRouter (digantikan 2026-10-29).**
Endpoint lama Hugging Face (`api-inference.huggingface.co`) tidak lagi resolve (DNS),
dan router HF membalas 402 (kredit). OpenRouter lulus probe saat itu, sebelum keputusan
beralih ke Ollama lokal. Satu runtime embedding dipakai untuk ingest dan query.

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
