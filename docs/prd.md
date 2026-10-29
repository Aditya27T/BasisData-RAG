# PRD: RAG hybrid lokal dengan LlamaParse

> Versi 0.5. Ditulis untuk dibaca manusia dan agent AI lokal. Bagian 0 adalah ringkasan wajib baca.
>
> **Perubahan dari 0.4:** Neo4j diaktifkan untuk ingest dan retrieval; evaluator menambahkan baseline C dengan pemisahan graf per query.

## 0. Ringkasan untuk agent

**Apa ini:** program tanya-jawab atas dokumen pribadi (md, PDF digital, docx, pptx). Pengguna mengunggah dokumen, lalu bertanya lewat CLI. Sistem menjawab hanya berdasarkan isi dokumen, dengan sitasi `berkas, halaman`.

**Mengapa dibuat:** pemilik proyek ingin mempelajari dan menguji alur RAG hybrid (vektor + BM25, parent-child, dan knowledge graph) pada dokumennya sendiri, dengan sumber daya gratis. Penyimpanan, embedding, dan knowledge graph berjalan lokal; parsing PDF/Office dan LLM memakai layanan eksternal.

**Batas perangkat keras:** laptop pemilik berRAM 8 GB. Model lokal hanya `bge-m3` melalui Ollama dengan konkurensi satu. Komponen lokal adalah aplikasi Python, Ollama, ParadeDB, dan Neo4j Community; container Neo4j dibatasi 1,2 GB dan hanya dijalankan saat ingest, query, atau evaluasi membutuhkan graf.

**Prinsip yang tidak boleh dilanggar:**
1. Jawaban hanya boleh berasal dari konteks yang diambil. Jika konteks kosong atau tidak relevan, jawab bahwa informasinya tidak ditemukan di dokumen. Jangan mengarang.
2. Setiap klaim dalam jawaban punya sitasi yang dapat diverifikasi ke chunk yang benar-benar diambil.
3. Neo4j dipakai untuk retrieval normal dan baseline C. Baseline B harus tetap mematikan graf per query agar perbandingan sah.
4. Hasil parse LlamaParse selalu di-cache di disk. Jangan memanggil LlamaParse dua kali untuk berkas yang sama.
5. Error kuota (402, 429) tidak boleh diulang tanpa batas.
6. Jangan memilih LLM atau penyedia API sendiri. Buat konfigurasi yang bisa diganti. Pemilik proyek yang memutuskan.
7. **Satu penyedia embedding untuk ingest dan query.** Jangan mencampur penyedia atau model tanpa membuat ulang seluruh tabel vektor.
8. Jangan menganggap path atau nama fungsi di `SYSTEM_ANALYSIS.md` bagian 9 pasti benar. Verifikasi di kode lebih dulu.

**Keputusan terkunci:** LlamaParse untuk PDF/Office, embedding `bge-m3` 1024 dimensi melalui Ollama, ParadeDB, Neo4j aktif, CLI, dan satu workspace `docs`.
**Belum diputuskan:** LLM untuk jawaban dan ekstraksi graf.

Dokumen pendamping: `SYSTEM_ANALYSIS.md`.

### Tambahan v0.3

- **Ruang lingkup (masuk):** orkestrasi `ask` dengan LangGraph sebagai pembungkus fungsi biasa. **Keluar:** checkpointer Postgres, memori percakapan, agent otonom, sub-agent.
- **F14 (P1):** `ask_graph()` menjalankan retrieve → decide → generate → verify dengan batas retry. Kriteria penerimaan: lolos uji paritas terhadap `ask()` pada set eval, dan tidak menambah panggilan LLM per pertanyaan di atas 1 + `LANGGRAPH_MAX_RETRIES`.
- **Keputusan teknologi:** LangGraph, versi di-pin setelah verifikasi di M0.3b. Status: terkunci sebagai pilihan belajar; manfaat teknisnya tidak diklaim.
- **Risiko:** (1) Perubahan API LangGraph antar versi → pin versi. (2) Loop retry menghabiskan kuota LLM gratis → batas retry dan hitung panggilan. (3) Dependensi `hybrid-rag` pada LangChain bisa menarik paket tambahan → periksa di M0.3b. (4) Abstraksi menyembunyikan bug → logika tetap di fungsi biasa, ada uji paritas.
- **Milestone:** M1b setelah M1: bungkus dengan LangGraph, lolos uji paritas.
- **Pertanyaan terbuka tambahan:** apakah memori percakapan diperlukan? Bila ya, itu mengubah M5 (checkpointer, tabel tambahan, RAM).

## 1. Latar belakang dan tujuan

**Tujuan**
1. Mempelajari dan membuktikan alur RAG hybrid end-to-end pada dokumen pemilik.
2. Menghasilkan jawaban berbasis dokumen dengan sitasi yang dapat diverifikasi.
3. Mengukur apakah hybrid retrieval dan graf memberi nilai tambah dibanding baseline sederhana.

**Non-tujuan (v1)**
- Multi-user, login, UI web, deployment produksi.
- Excel dan gambar, sistem audit, pembuatan laporan PDF.
- Menjalankan LLM generatif secara lokal.
- Mengejar kualitas graf. Graf adalah eksperimen.

**Catatan jujur tentang skala:** korpus saat ini kecil (1–10 halaman). Pada skala ini seluruh dokumen muat dalam konteks satu panggilan LLM, sehingga RAG mungkin tidak terbukti diperlukan. Itu hasil eval yang sah, bukan kegagalan proyek. Karena itu eval memuat baseline "tempel semua dokumen".

## 2. Pengguna dan kasus pakai

Satu pengguna, satu workspace.

| Kasus | Contoh | Status |
|---|---|---|
| Pertanyaan faktual | "Apa syarat X di dokumen Y?" | Utama |
| Pertanyaan tidak terjawab | Hal yang tidak ada di dokumen | Utama (harus ditolak) |
| Pertanyaan lintas dokumen | "Bandingkan A dan B" | Eksperimen. Bermakna hanya bila dokumen minimal 3 dan saling merujuk |

## 3. Ruang lingkup

| Masuk | Keluar |
|---|---|
| Ingest md, PDF digital, docx, pptx | S3, AWS Textract, Redis |
| LlamaParse + cache hasil parse | LLM generatif lokal |
| Embedding `bge-m3` melalui Ollama lokal | Rerank (aktifkan hanya bila eval menuntut) |
| Hybrid retrieval, chunking parent-child | Contextualize per child (dimatikan di v1) |
| Jawaban bersitasi dan penolakan | Multi-replica, multi-user |
| Eval dengan 3 baseline | UI chat (P2) |
| Graf Neo4j aktif | Excel, gambar |

## 4. Kebutuhan fungsional

| ID | Kebutuhan | Kriteria penerimaan | P |
|---|---|---|---|
| F1 | Ingest berkas dari `data/originals/`. `doc_id` = sha256 isi berkas. | Ingest berkas yang sama dua kali tidak menggandakan chunk, tidak memanggil LlamaParse, dan tidak membuat embedding ulang. | P0 |
| F2 | Parse pdf/docx/pptx via LlamaParse. Hasil per halaman disimpan di `data/parsed/<sha256>.json`. | File cache ada setelah ingest. Parse ulang membaca cache. | P0 |
| F3 | Berkas md dibaca langsung tanpa cloud. | md ter-ingest tanpa `LLAMA_CLOUD_API_KEY`. | P0 |
| F4 | Hasil parse diubah ke content list `{"type":"text","text":...,"page_idx":n}` lalu dimasukkan lewat `insert_content_list`. | Chunk di database memuat halaman asal. | P0 |
| F5 | Chunking parent-child. | Query mengembalikan parent, sitasi tetap menunjuk child. | P0 |
| F6 | Retrieval hybrid vektor + BM25 + RRF tanpa graf untuk baseline B. | `cobarag eval --baseline B` tidak membaca entitas atau relasi Neo4j meskipun `NEO4J_URI` aktif. | P0 |
| F7 | Jawaban bersitasi `berkas, halaman`. | Setiap klaim punya sitasi yang bisa dibuka kembali ke chunk asal. | P0 |
| F8 | Penolakan bila konteks kosong atau tidak relevan. | Pertanyaan yang jawabannya tidak ada di dokumen menghasilkan "tidak ditemukan di dokumen". | P0 |
| F9 | CLI: `ingest`, `ask`, `list`, `delete`, `eval`, `probe-embedding`. | `delete` menghapus data di Postgres, Neo4j (bila aktif), dan cache parse. | P0 |
| F10 | Eval otomatis dengan tiga baseline: A (tempel seluruh dokumen), B (hybrid tanpa graf), C (hybrid + graf). | Laporan perbandingan per pertanyaan, termasuk selisih C terhadap B dan jumlah entitas/relasi. | P0 |
| F11 | Ekstraksi dan retrieval graf melalui Neo4j. | `NEO4J_URI` aktif memicu ekstraksi saat ingest; `QueryParam.include_graph` mengontrol penggunaan graf per query. | P1 |
| F12 | `probe-embedding` menguji penyedia embedding (lihat `SYSTEM_ANALYSIS.md` bagian 8). | Menghasilkan laporan lulus/gagal yang disimpan di `docs/DECISIONS.md`. | P0 |
| F13 | UI chat sederhana. | – | P2 |

## 5. Kebutuhan non-fungsional

- **Jaringan:** embedding berjalan lokal. Query tetap membutuhkan internet untuk LLM; ingest PDF/Office membutuhkan internet untuk LlamaParse, sedangkan ingest md tidak.
- **Memori (RAM 8 GB):** ParadeDB dan Ollama `bge-m3` berjalan lokal dengan konkurensi embedding satu. Neo4j Community juga lokal, dibatasi 1,2 GB oleh Docker Compose, dan dapat dihentikan saat graf tidak dipakai.
- **Privasi:** teks chunk tidak dikirim ke penyedia embedding. Dokumen PDF/Office tetap dikirim ke LlamaCloud dan konteks hasil retrieval dikirim ke API LLM; gunakan hanya dokumen yang sesuai dengan kebijakan layanan tersebut.
- **Kuota:** error 402/429 dari LlamaParse atau LLM diperlakukan sebagai kondisi berhenti-dan-lanjutkan, bukan retry tanpa batas.
- **Biaya:** setiap ingest mencatat jumlah halaman yang diparse dan jumlah chunk yang di-embedding; setiap pertanyaan mencatat jumlah panggilan LLM.
- **Konsistensi embedding:** model, penyedia, dan dimensi dicatat di database. Aplikasi menolak berjalan bila konfigurasi tidak cocok dengan yang tercatat.
- **Reprodusibilitas:** satu `docker compose up` dan satu perintah bootstrap skema.
- **Keterlacakan:** setiap jawaban menyimpan daftar chunk yang dipakai, untuk debugging dan eval.
- **Satu proses:** v1 dijalankan sebagai satu proses. Jangan menambah worker paralel.

## 6. Keputusan teknologi

| Area | Keputusan | Status | Catatan |
|---|---|---|---|
| Parser pdf/office | LlamaParse + cache | Terkunci | Paket gratis punya kuota kredit bulanan. Setelah habis, request gagal dengan 402. Cek halaman harga resmi untuk angka terkini. |
| Parser md | Pembaca md lokal | Terkunci | Tanpa halaman. Sitasi memakai heading terdekat. |
| Model embedding | `bge-m3`, 1024 dimensi | Terkunci | Multibahasa, mendukung bahasa Indonesia. |
| Penyedia embedding | Ollama lokal, endpoint OpenAI-compatible | **Terkunci** | Model `bge-m3`; tanpa biaya per request. Tidak ada fallback otomatis ke API agar ruang vektor tidak tercampur. |
| Penyimpanan | ParadeDB (pgvector + pg_search) | Terkunci | Postgres biasa tidak punya BM25 yang dibutuhkan. |
| Graf | Neo4j Community lokal melalui profile Docker `graph` | **Aktif** | `NEO4J_URI` mengaktifkan ekstraksi dan retrieval. Baseline B mematikan graf melalui parameter query, bukan dengan mengubah environment. |
| Rerank | Mati | Terkunci untuk v1 | |
| LLM | Belum diputuskan | **Terbuka** | Syarat: kompatibel OpenAI, kuota cukup untuk beberapa panggilan per pertanyaan. |
| Antarmuka | CLI | Terkunci | |

## 7. Eval dan metrik

- Set uji: 20-30 pertanyaan nyata dengan jawaban dan halaman rujukan, ditulis oleh pemilik sebelum evaluasi pertama di `eval/questions.yaml`. Sertakan minimal 5 pertanyaan yang jawabannya tidak ada di dokumen. Kerangka evaluator boleh dibuat lebih dulu, tetapi M3 belum selesai tanpa set ini.
- Baseline: **A** seluruh dokumen ditempel ke konteks, **B** hybrid tanpa graf, **C** hybrid + graf.
- Metrik: jawaban benar dan faithfulness dinilai satu panggilan LLM judge per hasil non-penolakan; sitasi dan penolakan diperiksa deterministik. Laporan juga mencatat panggilan LLM, latensi, jumlah halaman cache parse, dan metrik yang belum diekspos engine.
- Perintah: `cobarag eval --validate-only` memvalidasi kontrak dataset tanpa layanan eksternal; `cobarag eval` menjalankan A/B/C dan menulis JSON serta Markdown ke `eval/reports/`.
- Cara membaca hasil: bila A sudah menjawab semuanya, RAG belum terbukti diperlukan pada korpus ini. Graf dipertahankan hanya bila C mengungguli B pada pertanyaan lintas dokumen. Tetapkan ambang selisih **sebelum** menjalankan perbandingan. Diagram keputusan ada di `SYSTEM_ANALYSIS.md` bagian 12.

## 8. Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Kredit LlamaParse habis | Ingest gagal dengan 402 | Cache parse, catat kredit, tangani 402 sebagai berhenti-dan-lanjutkan |
| Ollama atau model `bge-m3` tidak tersedia | Ingest dan query gagal membuat embedding | Jalankan `ollama pull bge-m3`, lalu gunakan `probe-embedding` sebagai gerbang |
| Mencampur runtime atau model antara ingest dan query | Vektor tidak sebanding, hasil retrieval buruk tanpa error | Gunakan satu konfigurasi; hapus tabel vektor dan ingest ulang saat konfigurasi berubah |
| Ollama lokal berhenti | Ingest dan query gagal dengan pesan koneksi | Periksa runtime sebelum proses; jangan fallback otomatis ke provider API |
| RAM 8 GB tidak cukup untuk ParadeDB + Ollama + Neo4j lokal | Sistem lambat atau macet | Jalankan hanya service yang diperlukan; hentikan Neo4j setelah operasi graf atau pindahkan kembali ke Aura yang aktif |
| Halaman docx tidak jelas | Sitasi halaman salah untuk Word | Uji. Fallback ke judul bagian atau nomor chunk |
| md tidak punya halaman | Sitasi tanpa halaman | Pakai heading terdekat sebagai label |
| Tabel markdown terpotong chunking (parent 2500, child 310 karakter) | Konteks tabel rusak | Periksa chunk halaman bertabel, sesuaikan ukuran |
| Kuota LLM gratis terbatas | Jawaban atau ekstraksi gagal | Batasi jumlah panggilan, jeda antar retry, ingest dapat dilanjutkan |
| Prompt ekstraksi graf bawaan bernuansa regulasi Indonesia | Graf salah arah untuk domain lain | Ganti entity types sebelum mengaktifkan graf |
| Repo asal tanpa bukti tes | Regresi tidak terdeteksi | Eval sebagai pagar pengaman, tes untuk parser dan sitasi |
| Endpoint Ollama tidak kompatibel dengan client embedding | Embedding gagal dipasang | Uji endpoint `/v1/embeddings`, dimensi, latensi, dan similarity melalui `probe-embedding` |

## 9. Milestone

| M | Isi | Selesai bila |
|---|---|---|
| M0 | Docker (ParadeDB; Neo4j di profile `graph`), `.env`, bootstrap skema, **gerbang embedding** (`probe-embedding` lulus), perubahan `hybrid-rag` butir 1–3 dan 5 | Satu teks pendek ter-ingest dan ter-query tanpa Neo4j, dan hasil probe tercatat di `docs/DECISIONS.md` |
| M1 | Parser md, ingest, `ask` bersitasi, penolakan | F3–F8 lolos untuk md |
| M2 | LlamaParse, cache, pdf dan Office | Ingest ulang tidak memanggil LlamaParse. Lima halaman bertabel diperiksa manual |
| M3 | Set eval, baseline A dan B | Kerangka selesai; milestone selesai setelah dataset owner-authored tersedia dan laporan A/B berhasil dibuat |
| M4 | Graf (F11) dan baseline C | Kerangka baseline C selesai; milestone selesai setelah re-ingest membentuk graf dan laporan C dibandingkan dengan B |
| M5 | UI chat (opsional) | – |

## 10. Pertanyaan terbuka

1. LLM dan penyedia API mana yang cukup andal untuk jawaban dan structured output ekstraksi graf?
2. "1-10 halaman": per dokumen atau total, dan berapa dokumen? Menentukan kekuatan kesimpulan baseline C.

## 11. Glosarium

- **Hybrid retrieval:** pencarian gabungan vektor (makna) dan BM25 (kata kunci), digabung dengan RRF.
- **RRF:** Reciprocal Rank Fusion, penggabungan peringkat dari beberapa pencarian.
- **Parent-child chunking:** teks dipecah menjadi child kecil (untuk dicari) dan parent besar (untuk disajikan sebagai konteks).
- **Contextualize:** langkah memanggil LLM untuk menambah konteks pada setiap child. Mahal. Dimatikan di v1.
- **Content list:** daftar elemen hasil parse dengan tipe, teks, dan nomor halaman, format masukan `hybrid-rag`.
- **Sitasi:** rujukan `berkas, halaman` yang bisa dibuka kembali ke chunk asal.
- **Gerbang penyedia:** uji di M0 yang harus lulus sebelum penyedia embedding dikunci.