# PRD: RAG hybrid lokal dengan LlamaParse

> Versi 0.2. Ditulis untuk dibaca manusia dan agent AI lokal. Bagian 0 adalah ringkasan wajib baca.
>
> **Perubahan dari 0.1:** embedding memakai API inference (bukan model lokal); Neo4j mati secara default karena RAM 8 GB; kebutuhan "dapat berjalan offline" dihapus; penyedia embedding diputuskan lewat uji di M0.

## 0. Ringkasan untuk agent

**Apa ini:** program tanya-jawab atas dokumen pribadi (md, PDF digital, docx, pptx). Pengguna mengunggah dokumen, lalu bertanya lewat CLI. Sistem menjawab hanya berdasarkan isi dokumen, dengan sitasi `berkas, halaman`.

**Mengapa dibuat:** pemilik proyek ingin mempelajari dan menguji alur RAG hybrid (vektor + BM25, parent-child, knowledge graph opsional) pada dokumennya sendiri, dengan sumber daya gratis. Penyimpanan data berjalan lokal; parsing, embedding, dan LLM memakai layanan eksternal.

**Batas perangkat keras:** laptop pemilik berRAM 8 GB. Tidak ada model ML yang dijalankan lokal. Komponen lokal hanya aplikasi Python dan ParadeDB. Neo4j hanya dijalankan bila eksperimen graf dimulai.

**Prinsip yang tidak boleh dilanggar:**
1. Jawaban hanya boleh berasal dari konteks yang diambil. Jika konteks kosong atau tidak relevan, jawab bahwa informasinya tidak ditemukan di dokumen. Jangan mengarang.
2. Setiap klaim dalam jawaban punya sitasi yang dapat diverifikasi ke chunk yang benar-benar diambil.
3. Graf (Neo4j) adalah eksperimen opsional. Sistem harus berfungsi penuh dengan graf mati.
4. Hasil parse LlamaParse selalu di-cache di disk. Jangan memanggil LlamaParse dua kali untuk berkas yang sama.
5. Error kuota (402, 429) tidak boleh diulang tanpa batas.
6. Jangan memilih LLM atau penyedia API sendiri. Buat konfigurasi yang bisa diganti. Pemilik proyek yang memutuskan.
7. **Satu penyedia embedding untuk ingest dan query.** Jangan mencampur penyedia atau model tanpa membuat ulang seluruh tabel vektor.
8. Jangan menganggap path atau nama fungsi di `SYSTEM_ANALYSIS.md` bagian 9 pasti benar. Verifikasi di kode lebih dulu.

**Keputusan terkunci:** LlamaParse sebagai parser pdf/office, model embedding `bge-m3` (1024 dimensi) lewat API inference, ParadeDB, CLI, satu workspace bernama `docs`, graf mati secara default.
**Belum diputuskan:** (a) penyedia embedding, diputuskan oleh uji di M0; (b) LLM untuk jawaban dan ekstraksi graf.

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
- Menjalankan model ML secara lokal.
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
| LlamaParse + cache hasil parse | Model embedding atau LLM lokal |
| Embedding `bge-m3` lewat API inference | Rerank (aktifkan hanya bila eval menuntut) |
| Hybrid retrieval, chunking parent-child | Contextualize per child (dimatikan di v1) |
| Jawaban bersitasi dan penolakan | Multi-replica, multi-user |
| Eval dengan 3 baseline | UI chat (P2) |
| Graf Neo4j sebagai opsi | Excel, gambar |

## 4. Kebutuhan fungsional

| ID | Kebutuhan | Kriteria penerimaan | P |
|---|---|---|---|
| F1 | Ingest berkas dari `data/originals/`. `doc_id` = sha256 isi berkas. | Ingest berkas yang sama dua kali tidak menggandakan chunk dan tidak memanggil LlamaParse maupun API embedding lagi. | P0 |
| F2 | Parse pdf/docx/pptx via LlamaParse. Hasil per halaman disimpan di `data/parsed/<sha256>.json`. | File cache ada setelah ingest. Parse ulang membaca cache. | P0 |
| F3 | Berkas md dibaca langsung tanpa cloud. | md ter-ingest tanpa `LLAMA_CLOUD_API_KEY`. | P0 |
| F4 | Hasil parse diubah ke content list `{"type":"text","text":...,"page_idx":n}` lalu dimasukkan lewat `insert_content_list`. | Chunk di database memuat halaman asal. | P0 |
| F5 | Chunking parent-child. | Query mengembalikan parent, sitasi tetap menunjuk child. | P0 |
| F6 | Retrieval hybrid vektor + BM25 + RRF, tanpa graf. | `ask` mengembalikan konteks dengan graf mati dan Neo4j tidak berjalan. | P0 |
| F7 | Jawaban bersitasi `berkas, halaman`. | Setiap klaim punya sitasi yang bisa dibuka kembali ke chunk asal. | P0 |
| F8 | Penolakan bila konteks kosong atau tidak relevan. | Pertanyaan yang jawabannya tidak ada di dokumen menghasilkan "tidak ditemukan di dokumen". | P0 |
| F9 | CLI: `ingest`, `ask`, `list`, `delete`, `eval`, `probe-embedding`. | `delete` menghapus data di Postgres, Neo4j (bila aktif), dan cache parse. | P0 |
| F10 | Eval otomatis dengan tiga baseline: A (tempel seluruh dokumen), B (hybrid tanpa graf), C (hybrid + graf). | Laporan perbandingan per pertanyaan. | P0 |
| F11 | Ekstraksi dan retrieval graf lewat flag `ENABLE_GRAPH`. | Flag mati: Neo4j tidak diperlukan dan tidak dijalankan. Flag hidup: graf terbentuk dan dipakai. | P1 |
| F12 | `probe-embedding` menguji penyedia embedding (lihat `SYSTEM_ANALYSIS.md` bagian 8). | Menghasilkan laporan lulus/gagal yang disimpan di `docs/DECISIONS.md`. | P0 |
| F13 | UI chat sederhana. | – | P2 |

## 5. Kebutuhan non-fungsional

- **Jaringan:** ingest dan query membutuhkan internet (embedding, LLM, dan LlamaParse untuk pdf/office). Mode offline tidak didukung di v1.
- **Memori (RAM 8 GB):** hanya ParadeDB yang berjalan secara default. Beri batas memori pada container. Neo4j hanya dijalankan saat eksperimen graf, dan sebaiknya setelah container lain dimatikan bila RAM tidak cukup.
- **Privasi:** dokumen dikirim ke LlamaCloud, penyedia embedding, dan API LLM. Hanya dokumen non-rahasia. Tier gratis sebagian penyedia dapat memakai konten untuk meningkatkan produk mereka; periksa syarat penyedia yang dipilih.
- **Kuota:** error 402/429 diperlakukan sebagai kondisi berhenti-dan-lanjutkan, bukan retry tanpa batas. Ingest mencatat tahap terakhir yang selesai dan dapat dilanjutkan.
- **Biaya:** setiap ingest mencatat jumlah halaman yang diparse, token embedding, dan jumlah panggilan LLM.
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
| Penyedia embedding | Hugging Face Inference Providers lebih dulu; OpenRouter sebagai cadangan | **Terbuka, diputuskan oleh uji M0** | Hugging Face: kredit gratis bulanan kecil dan berhenti saat habis, ketersediaan `bge-m3` harus dikonfirmasi. OpenRouter: API kompatibel OpenAI, berbayar tetapi sangat murah, butuh saldo. Cek harga dan syarat terkini sebelum memilih. |
| Penyimpanan | ParadeDB (pgvector + pg_search) | Terkunci | Postgres biasa tidak punya BM25 yang dibutuhkan. |
| Graf | Neo4j Community, opsional | Terkunci sebagai opsi | Default mati. Berbasis JVM, boros memori di mesin 8 GB. |
| Rerank | Mati | Terkunci untuk v1 | |
| LLM | Belum diputuskan | **Terbuka** | Syarat: kompatibel OpenAI, kuota cukup untuk beberapa panggilan per pertanyaan. |
| Antarmuka | CLI | Terkunci | |

## 7. Eval dan metrik

- Set uji: 20–30 pertanyaan nyata dengan jawaban dan halaman rujukan, ditulis oleh pemilik **sebelum** kode, di `eval/questions.yaml`. Sertakan minimal 5 pertanyaan yang jawabannya tidak ada di dokumen.
- Baseline: **A** seluruh dokumen ditempel ke konteks, **B** hybrid tanpa graf, **C** hybrid + graf.
- Metrik: jawaban benar, halaman sitasi benar, penolakan benar, faithfulness (tidak ada klaim di luar konteks), jumlah panggilan LLM, token embedding, dan halaman parse per ingest.
- Cara membaca hasil: bila A sudah menjawab semuanya, RAG belum terbukti diperlukan pada korpus ini. Graf dipertahankan hanya bila C mengungguli B pada pertanyaan lintas dokumen. Tetapkan ambang selisih **sebelum** menjalankan perbandingan. Diagram keputusan ada di `SYSTEM_ANALYSIS.md` bagian 12.

## 8. Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Kredit LlamaParse habis | Ingest gagal dengan 402 | Cache parse, catat kredit, tangani 402 sebagai berhenti-dan-lanjutkan |
| `bge-m3` tidak tersedia atau kuotanya tipis di penyedia gratis | Embedding gagal atau terhenti di tengah ingest | `probe-embedding` di M0 sebagai gerbang. Siapkan penyedia cadangan. Batch kecil dan resume |
| Mencampur penyedia antara ingest dan query | Vektor tidak sebanding, hasil retrieval buruk tanpa error | Catat penyedia dan model di database, tolak ketidakcocokan. Uji kesamaan vektor antar penyedia bila perlu berpindah |
| Embedding bergantung jaringan | Query gagal bila offline atau penyedia down | Pesan galat jelas. Tidak ada fallback lokal di v1 |
| RAM 8 GB tidak cukup untuk ParadeDB + Neo4j + Docker | Sistem lambat atau macet | Graf mati default. Batas memori container. Jalankan Neo4j hanya saat eksperimen |
| Halaman docx tidak jelas | Sitasi halaman salah untuk Word | Uji. Fallback ke judul bagian atau nomor chunk |
| md tidak punya halaman | Sitasi tanpa halaman | Pakai heading terdekat sebagai label |
| Tabel markdown terpotong chunking (parent 2500, child 310 karakter) | Konteks tabel rusak | Periksa chunk halaman bertabel, sesuaikan ukuran |
| Kuota LLM gratis terbatas | Jawaban atau ekstraksi gagal | Batasi jumlah panggilan, jeda antar retry, ingest dapat dilanjutkan |
| Prompt ekstraksi graf bawaan bernuansa regulasi Indonesia | Graf salah arah untuk domain lain | Ganti entity types sebelum mengaktifkan graf |
| Repo asal tanpa bukti tes | Regresi tidak terdeteksi | Eval sebagai pagar pengaman, tes untuk parser dan sitasi |
| Hook embedding `hybrid-rag` belum diverifikasi menerima endpoint kompatibel OpenAI | Embedding gagal dipasang | Verifikasi di M0.3 sebelum lanjut |

## 9. Milestone

| M | Isi | Selesai bila |
|---|---|---|
| M0 | Docker (ParadeDB; Neo4j di profile `graph`), `.env`, bootstrap skema, **gerbang embedding** (`probe-embedding` lulus), perubahan `hybrid-rag` butir 1–3 dan 5 | Satu teks pendek ter-ingest dan ter-query tanpa Neo4j, dan hasil probe tercatat di `docs/DECISIONS.md` |
| M1 | Parser md, ingest, `ask` bersitasi, penolakan | F3–F8 lolos untuk md |
| M2 | LlamaParse, cache, pdf dan Office | Ingest ulang tidak memanggil LlamaParse. Lima halaman bertabel diperiksa manual |
| M3 | Set eval, baseline A dan B | Laporan perbandingan tersedia |
| M4 | Graf (F11) dan baseline C | Keputusan go/no-go graf sesuai ambang yang ditetapkan sebelumnya |
| M5 | UI chat (opsional) | – |

## 10. Pertanyaan terbuka

1. LLM dan penyedia API mana untuk jawaban (dan ekstraksi graf bila aktif)? Harus diputuskan sebelum M1.
2. Penyedia embedding: Hugging Face atau OpenRouter? Diputuskan oleh hasil `probe-embedding`. Apakah pemilik bersedia top-up kecil sekali bila jalur gratis tidak lolos uji?
3. "1–10 halaman": per dokumen atau total, dan berapa dokumen? Menentukan apakah M4 bermakna.

## 11. Glosarium

- **Hybrid retrieval:** pencarian gabungan vektor (makna) dan BM25 (kata kunci), digabung dengan RRF.
- **RRF:** Reciprocal Rank Fusion, penggabungan peringkat dari beberapa pencarian.
- **Parent-child chunking:** teks dipecah menjadi child kecil (untuk dicari) dan parent besar (untuk disajikan sebagai konteks).
- **Contextualize:** langkah memanggil LLM untuk menambah konteks pada setiap child. Mahal. Dimatikan di v1.
- **Content list:** daftar elemen hasil parse dengan tipe, teks, dan nomor halaman, format masukan `hybrid-rag`.
- **Sitasi:** rujukan `berkas, halaman` yang bisa dibuka kembali ke chunk asal.
- **Gerbang penyedia:** uji di M0 yang harus lulus sebelum penyedia embedding dikunci.