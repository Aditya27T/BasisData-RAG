---
name: cobarag-frontend-workflow
description: Alur kerja pengerjaan frontend webui cobarag dari awal sampai selesai — setup dev, urutan prioritas P0-P3, rencana sebelum ubah file, verifikasi, definisi selesai, dan batas yang tidak boleh disentuh. Gunakan setiap kali user meminta mengerjakan, memperbaiki, menambah fitur, atau me-review apa pun di webui cobarag (chat, dokumen, graph, upload, SSE), atau menyebut "task frontend", "P1", "backlog", "improvement", walaupun tidak menyebut kata workflow.
---

# Workflow Pengerjaan Frontend — cobarag

Skill pendamping: `cobarag-svelte` (kode), `cobarag-styling` (CSS), `cobarag-brand-guideline` (teks & UX). Baca yang relevan sebelum mengubah file.

## 0. Setup dev (P0.1)
Jalankan manual agar tidak kena race `make webui`:
```bash
# terminal 1
make api
# terminal 2
npm --prefix webui run dev      # http://127.0.0.1:5173, proxy /api → :8000
```
Catatan lingkungan: repo berada di `/mnt/d` → set `UV_LINK_MODE=copy` di `.env` agar venv tidak korup. `vite preview` tidak punya proxy `/api`, jadi build production belum bisa dipakai apa adanya.

## 1. Urutan prioritas
- **P0 (blocker):** stabilkan dev workflow; `eval/questions.yaml` (20-30 soal, ≥5 penolakan); isi `data/originals/` dengan dokumen nyata; tetapkan ambang C vs B; amankan `.env` (jangan pernah menampilkan/commit isinya).
- **P1 (fungsional frontend), kerjakan berurutan:**
  6. AbortController + token generasi (batalkan stream, timeout, race saat ganti workspace)
  7. Render `refused` + sitasi yang bisa diklik
  8. Reset riwayat chat saat workspace berubah + tombol "Obrolan baru" + label workspace per pesan
  9. Health indicator (`/api/health`), fallback ke `/api/chat` & `/api/graph` bila SSE gagal, pemulihan job via `GET /api/ingestions/{id}`
  10. Pisahkan error list vs upload, batasi `ingestionLogs`, tambah mapping `completed` di `statusLabel()`
  11. Hapus dokumen (butuh endpoint DELETE backend: laporkan sebagai dependensi)
- **P2 (kualitas):** graph interaktif, upload UX (multi-file, drag-drop, validasi 250 MiB di client), cari/filter/sort dokumen, routing hash + simpan workspace, Vitest untuk `state/*.js` dan parser SSE `api/http.js`, pecah `app.css`.
- **P3 (utang backend/engine):** di luar lingkup frontend; hanya catat, jangan kerjakan tanpa diminta.

## 2. Siklus kerja per task
1. **Pahami & baca.** Buka file terkait (jangan mengandalkan ringkasan audit; nomor baris bisa bergeser). Konfirmasi kontrak endpoint yang disentuh.
2. **Rencana singkat sebelum mengubah file.** Tulis: tujuan, file yang disentuh, pendekatan, risiko, cara verifikasi. Untuk task >3 file atau yang menyentuh kontrak backend, **tunggu persetujuan user**. Task kecil dan jelas boleh langsung dikerjakan.
3. **Implementasi kecil dan terfokus.** Satu task = satu perubahan koheren. Jangan sekalian merapikan hal lain. Temuan sampingan dicatat di akhir, bukan dikerjakan diam-diam.
4. **Verifikasi** (lihat bagian 3).
5. **Laporan:** apa yang diubah (per file), cara mencoba, apa yang belum diverifikasi, dan temuan sampingan.

## 3. Verifikasi (tidak ada test saat ini)
Minimum untuk setiap task:
- `npm --prefix webui run build` lolos tanpa warning baru
- Uji manual jalur utama + jalur gagal: API mati, stream terputus, workspace diganti saat request jalan, jawaban `refused`, payload graph kosong
- Cek light, dark, dan lebar 360px
- Cek navigasi keyboard dan fokus pada elemen baru
- Jika menyentuh SSE: tes dengan stream yang diabort di tengah dan frame JSON rusak

Bila task P2.16 (Vitest) sudah ada, tambahkan test untuk logika yang diubah. Jangan klaim "sudah diuji" untuk hal yang tidak benar-benar dijalankan; nyatakan apa adanya.

## 4. Definisi selesai
- Perilaku sesuai tujuan task dan lolos verifikasi di atas
- Tidak ada regresi pada alur ingest → tanya → graph
- Mengikuti ketiga skill pendamping
- Tidak ada dependensi baru, kunci, atau file `.env` yang tersentuh
- Laporan jujur mencantumkan batasan dan sisa pekerjaan

## 5. Batas (jangan disentuh tanpa diminta)
- `hybrid-rag/` dan seluruh `app/` (backend). Jika UI butuh perubahan di sana, tulis sebagai permintaan terpisah dengan kontrak yang diusulkan.
- `.env`, kunci API, `docker-compose.yml`, data di `data/`.
- Skema respons SSE/JSON yang sudah ada: UI harus toleran, bukan memaksa backend berubah.
- Struktur direktori `lib/{api,state,components,views}`.

## 6. Hal yang sudah diketahui rawan (periksa dulu saat menyentuh area terkait)
`message.refused` tidak dirender; sitasi tidak interaktif; riwayat chat menempel antar workspace; `navigate()`/`loadWorkspace()` tidak menyentuh chat; brand link `<a href="/">` memicu reload penuh; satu `error` dipakai bersama di DocumentsView; `ingestionLogs` tak terbatas; job ingest hilang saat refresh (di backend hanya di memori proses); mini graph tidak tampil bila ada entity tanpa edge; limit graph 80 dan batas 24/36 hardcoded.