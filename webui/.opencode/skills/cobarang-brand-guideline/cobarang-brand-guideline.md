---
name: cobarag-brand-guideline
description: Panduan brand, suara, dan prinsip UX untuk webui cobarag (aplikasi RAG lokal untuk materi kuliah). Gunakan setiap kali menulis atau mengubah teks UI, label status, pesan error, empty state, tampilan sitasi, tampilan penolakan jawaban (refused), nama fitur, atau memutuskan "seharusnya UI-nya terasa seperti apa". Pakai juga saat membuat komponen baru agar konsisten secara identitas, walaupun user tidak menyebut kata "brand".
---

# Brand Guideline — cobarag webui

## Identitas produk
cobarag adalah alat bantu belajar lokal: mengingest materi kuliah, menjawab pertanyaan **dengan sitasi yang bisa diverifikasi**, dan **menolak menjawab bila konteks tidak cukup**. Semua keputusan visual dan teks harus memperkuat tiga hal: dapat dipercaya, jujur soal proses, dan tenang dipakai lama.

## Prinsip inti
1. **Verifiabilitas di atas kefasihan.** Sitasi adalah elemen kelas satu, bukan hiasan. Format label: `[nama_file, hal. N]` atau `[nama_file, "judul"]`. Sitasi harus terlihat jelas, dan idealnya bisa diklik ke dokumen/chunk (`chunk_id`, `page_label`, `headings` sudah dikirim backend).
2. **Penolakan adalah fitur, bukan error.** Jawaban `refused` ditampilkan sebagai keadaan sah dengan gaya netral/informatif (bukan merah alarm). Jelaskan singkat: konteks materi tidak cukup untuk menjawab dengan sitasi.
3. **Progres jujur.** Tampilkan tahap nyata dari backend lewat SSE. Dilarang persentase palsu atau animasi "pura-pura loading" (keputusan DECISIONS.md:213-221). Progress determinat hanya bila backend benar-benar memberi angkanya.
4. **Lokal dan privat.** Tidak ada telemetri, font/CDN eksternal, atau tracker. Jangan menampilkan kunci/isi `.env` di UI.
5. **Tenang dan fungsional.** Ini alat belajar: kepadatan informasi sedang, tanpa dekorasi berlebihan, animasi minimal dan menghormati `prefers-reduced-motion`.

## Suara dan bahasa
- Bahasa UI: **Bahasa Indonesia** (`<html lang="id">`). Istilah teknis yang lazim boleh tetap Inggris (workspace, chunk, graph, SSE) bila belum ada padanan yang natural.
- Nada: lugas, sopan, netral. Tanpa tanda seru, tanpa emoji di teks sistem, tanpa bahasa gaul.
- Kalimat error = **apa yang gagal + apa yang bisa dilakukan**. Contoh: "Daftar dokumen gagal dimuat. Periksa apakah API berjalan, lalu coba lagi."
- Satu sumber error per konteks: jangan menampilkan "Daftar dokumen gagal dimuat" untuk error upload (bug yang ada sekarang, lihat DocumentsView).
- Label status dokumen memakai pemetaan Indonesia di `statusLabel()` (pastikan semua status backend terpetakan, termasuk `completed`).
- Tombol memakai kata kerja ringkas: "Unggah", "Tanya", "Obrolan baru", "Hapus", "Coba lagi".
- Konfirmasi untuk aksi destruktif (hapus dokumen) wajib menyebut nama dokumen dan dampaknya.

## Komponen identitas
- **Sitasi:** badge bernomor + `file_path` + halaman/heading. Konsisten di ChatView dan di mana pun sitasi muncul.
- **Workspace:** selalu tampak aktif di header; pesan chat sebaiknya berlabel workspace asalnya.
- **Status/progres:** log tahap bergaya teks monospace ringan, dibatasi jumlahnya (chat 12, ingest 8).
- **Graph:** node = entity, edge = relasi; label edge harus terbaca; jangan menampilkan graph bila hanya ada entity tanpa relasi tanpa penjelasan.

## Aksesibilitas (bagian dari brand)
`lang="id"`, `aria-current` pada navigasi, `role="log"` + `aria-live` untuk riwayat dan progres, `:focus-visible` jelas, kontras cukup di light & dark, layout nyaman sampai lebar 360px. Jangan menghapus fondasi ini saat refactor.

## Token visual (WAJIB diverifikasi dulu)
Skill ini tidak memuat nilai warna/font karena nilai pastinya hidup di `webui/src/app.css`. Sebelum membuat UI baru:
1. Baca bagian `:root` / variabel tema di `app.css` dan catat token warna, spasi, radius, font, bayangan yang sudah ada.
2. Pakai token itu. Jika perlu token baru, tambahkan di tempat yang sama untuk light dan dark sekaligus.
3. Jangan pernah menebak hex atau memperkenalkan palet baru tanpa persetujuan user.

## Checklist cepat sebelum selesai
- [ ] Semua teks baru berbahasa Indonesia dan bernada netral
- [ ] Error menyebut penyebab + langkah berikutnya
- [ ] Tidak ada progres/angka palsu
- [ ] Sitasi dan `refused` tampil sesuai prinsip di atas
- [ ] Light, dark, dan 360px sudah dicek