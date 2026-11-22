# BasisData-RAG

Aplikasi RAG lokal untuk mengingest materi kuliah dan bertanya dengan sitasi. Backend menyediakan CLI dan API FastAPI; frontend memakai Svelte. Data disimpan per workspace di ParadeDB dan Neo4j.

## Prasyarat

- Python 3.11 atau 3.12, `uv`, Docker Compose, dan Node.js/npm.
- Ollama aktif dengan model embedding `bge-m3`.
- LLM API kompatibel OpenAI, misalnya 9router.
- API key LlamaParse untuk PDF dan dokumen Office.
- API key Google Gemini untuk VLM dan ekstraksi knowledge graph.

## Setup lokal

1. Salin konfigurasi dan isi key yang diperlukan:

   ```bash
   cp .env.example .env
   ```

   Atur `LLM_BINDING_HOST`, `LLM_BINDING_API_KEY`, dan `LLM_MODEL` ke endpoint/model LLM yang dipakai untuk chat. Isi `LLAMA_CLOUD_API_KEY` dan `VLM_BINDING_API_KEY`. Template memakai `gemini-3.5-flash-lite` untuk VLM dan ekstraksi graph.

2. Install dependency Python dan model embedding:

   ```bash
   uv sync
   ollama pull bge-m3
   ```

   Pastikan service Ollama berjalan pada `http://localhost:11434`.

3. Jalankan ParadeDB dan Neo4j:

   ```bash
   docker compose --profile graph up -d
   docker compose ps
   ```

   Compose menjalankan ParadeDB pada port `5432`, Neo4j Browser pada `7474`, dan Bolt pada `7687`. Data database tersimpan di named volumes Compose.

## Ingest dan tanya lewat CLI

Taruh dokumen di `data/originals/`. CLI mengingest semua file di sana, atau satu file yang diberikan:

```bash
uv run python -m app.main ingest
uv run python -m app.main ingest "data/originals/Modul 2 - SQL.docx"
uv run python -m app.main list
uv run python -m app.main ask "Apa isi dokumen ini?"
```

Gunakan `--force` untuk mengulang ingest sebuah file. Perintah `delete` menghapus dokumen dari workspace. Jalankan `uv run python -m app.main --help` untuk daftar perintah.

## Web UI dan API

Jalankan frontend dan API bersama-sama:

```bash
make webui
```

Buka:

- Web UI: <http://127.0.0.1:5173/>
- Swagger UI: <http://127.0.0.1:8000/docs>
- Health API: <http://127.0.0.1:8000/api/health>

API menyediakan upload dan status ingest, chat, serta graph. Endpoint stream mengirim event pipeline yang benar-benar terjadi. Kode Svelte memisahkan pemanggilan API, state, komponen, dan views di `webui/src/lib/`.

## Provider dan data

- Ollama menjalankan embedding `bge-m3` secara lokal.
- ParadeDB menyimpan chunk, status dokumen, dan vektor. Neo4j menyimpan graph.
- LLM chat memakai endpoint OpenAI-compatible dari `LLM_BINDING_*`.
- LlamaParse menerima PDF dan dokumen Office untuk diparse.
- Gemini menerima gambar untuk analisis VLM serta teks hasil parse untuk ekstraksi graph. Pastikan dokumen boleh dikirim ke layanan tersebut.

Simpan dokumen sumber di `data/originals/`; cache hasil parse LlamaParse berada di `data/parsed/`. Jangan commit `.env` atau key API.

## Evaluasi berikutnya

Langkah berikut dari PRD adalah membuat `eval/questions.yaml` dengan 20 sampai 30 pertanyaan nyata, jawaban rujukan dan sumbernya, termasuk setidaknya lima pertanyaan yang jawabannya tidak ada di dokumen. Validasi dataset tanpa panggilan layanan eksternal:

```bash
uv run python -m app.main eval --validate-only
```

Sesudah dataset tersedia, bandingkan baseline A (seluruh dokumen), B (hybrid tanpa graph), dan C (hybrid dengan Neo4j). Tetapkan ambang keberhasilan sebelum membandingkan hasil B dan C. Lihat `docs/prd.md` dan `docs/SYSTEM_ANALYSIS.md` untuk detail.
