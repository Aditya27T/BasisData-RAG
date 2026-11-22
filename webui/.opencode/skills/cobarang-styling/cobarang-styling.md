---
name: cobarag-styling
description: Aturan styling CSS untuk webui cobarag (Svelte 5 + Vite, satu app.css global 1202 baris). Gunakan setiap kali menambah atau mengubah gaya, kelas CSS, layout, dark mode, responsif, animasi, focus state, atau memecah app.css. Pakai juga bila user menyebut tampilan, spacing, warna, tema, mobile, atau "rapikan CSS", walaupun tidak menyebut kata styling.
---

# Styling — cobarag webui

## Kondisi saat ini (fakta dari audit)
- Satu-satunya stylesheet global: `webui/src/app.css` (~1202 baris), diimpor di `main.js`.
- Tidak ada Tailwind, tidak ada CSS-in-JS, tidak ada `svelte.config.js`, tidak ada linter CSS.
- Tema (light/dark) disimpan di `localStorage` dan dibaca di `onMount` di `App.svelte` → ada potensi *flash* tema saat load.
- Responsif sudah dijaga sampai 360px; ada `focus-visible` dan penanganan `prefers-reduced-motion`.
- Beberapa dimensi hardcoded: canvas graph 780×560, mini graph 720×360.

## Aturan utama
1. **Ikuti konvensi yang sudah ada.** Buka `app.css`, pelajari pola penamaan kelas, urutan seksi, dan variabel tema sebelum menulis apa pun. Jangan memperkenalkan framework CSS atau metodologi baru.
2. **Token dulu, nilai mentah dilarang.** Warna, spasi, radius, bayangan, font diambil dari custom properties (`var(--...)`). Tidak ada hex/px sihir baru di aturan komponen. Token baru ditambahkan untuk light **dan** dark sekaligus.
3. **Satu perubahan, satu area.** Taruh aturan baru di seksi yang relevan dengan komponennya, jangan di akhir file secara acak. Beri komentar seksi bila membuat seksi baru.
4. **Specificity rendah.** Selector kelas tunggal. Hindari `!important`, selector ID, dan rantai selector dalam.
5. **Mobile-first yang aman.** Setiap perubahan layout harus tetap benar di 360px: tanpa scroll horizontal, target sentuh nyaman, teks tidak terpotong tanpa alasan.
6. **Dark mode bukan opsional.** Setiap elemen baru dicek di kedua tema. Kontras teks memenuhi WCAG AA.
7. **Focus dan gerak.** Elemen interaktif baru wajib punya `:focus-visible` yang terlihat. Transisi/animasi baru dibungkus agar mati di `@media (prefers-reduced-motion: reduce)`.
8. **Jangan menghapus fondasi a11y** (outline fokus, ukuran teks minimum, area klik).
9. **Hindari angka ajaib untuk layout.** Untuk ukuran graph/canvas, utamakan `viewBox` + CSS responsif daripada piksel tetap, kecuali tugasnya memang mempertahankannya.
10. **CSS dinamis lewat variabel**, bukan inline style panjang. Inline style hanya untuk nilai yang dihitung runtime (posisi node graph).

## Pola yang direkomendasikan
```css
/* Komponen: tombol sekunder (contoh pola, sesuaikan nama token dengan app.css) */
.btn-secondary {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
}
.btn-secondary:hover { background: var(--surface-hover); }
.btn-secondary:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.btn-secondary[disabled] { opacity: .55; cursor: not-allowed; }

@media (prefers-reduced-motion: reduce) {
  .btn-secondary { transition: none; }
}
```
Nama token di atas hanyalah ilustrasi. Gunakan nama token yang benar-benar ada di `app.css`.

## Mencegah flash tema
Jika diminta memperbaikinya: set atribut tema sedini mungkin lewat skrip kecil inline di `index.html` (baca `localStorage`, set atribut di `<html>`), lalu pertahankan logika `App.svelte` agar tetap sinkron. Jangan menunggu `onMount`.

## Memecah app.css (hanya jika tugas P2.17)
Pecah per area: `base.css` (reset + token + tema), `layout.css`, `components/*.css`, `views/*.css`. Impor berurutan di `main.js`. Pastikan urutan cascade tidak berubah (bandingkan tampilan sebelum/sesudah di light, dark, dan 360px). Lakukan dalam commit terpisah tanpa perubahan visual.

## Checklist cepat
- [ ] Tidak ada warna/ukuran mentah baru, semua lewat token
- [ ] Light, dark, dan 360px dicek
- [ ] `:focus-visible` dan reduced-motion ditangani
- [ ] Tidak ada `!important` / selector berlapis baru
- [ ] Perubahan berada di seksi `app.css` yang tepat