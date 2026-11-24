---
name: cobarag-svelte
description: Konvensi kode Svelte 5 + Vite untuk webui cobarag — gaya klasik tanpa runes (export let, $:, writable store), arsitektur api/state/components/views, pola SSE, AbortController, dan guard race. Gunakan setiap kali menulis atau mengubah file .svelte atau .js di webui/src, membuat komponen/controller/store baru, menangani stream SSE, atau saat user menyebut Svelte, store, komponen, reactive, props, fetch, stream, atau abort.
---

# Svelte — cobarag webui

## Stack nyata
Svelte 5.x (tanpa runes), Vite 7, `@sveltejs/vite-plugin-svelte` 6, `d3-force` 3. Tanpa TypeScript, tanpa test, tanpa linter, tanpa `svelte.config.js`.

## Aturan emas: jangan campur gaya
Kode saat ini **klasik (Svelte 4 style)** walau runtime Svelte 5:
- Props: `export let nama;`
- Reaktivitas: `$: turunan = ...`
- State bersama: `writable` store, diakses `$controller.field`
- Event DOM: sintaks baru (`onclick`, `onsubmit`) — ini sudah dipakai di semua view

**Dilarang** memakai `$state`, `$derived`, `$effect`, `$props`, `{#snippet}` di file yang masih klasik. Migrasi ke runes hanya dilakukan bila user memintanya eksplisit, per file utuh, sebagai commit terpisah.

## Arsitektur berlapis (arah impor satu arah)
```
api/  →  state/  →  components/ & views/  →  App.svelte
```
| Lapisan | Tanggung jawab | Tidak boleh |
|---|---|---|
| `lib/api/` | fetch, parse SSE, normalisasi error | menyentuh store/DOM |
| `lib/state/` | controller: `writable` + aksi, ekspor `{ subscribe, ...actions }` | mengimpor komponen |
| `lib/components/` | UI reusable, menerima props + callback | memanggil `fetch` langsung |
| `lib/views/` | merakit komponen, membaca `$controller` | logika bisnis berat |
| `App.svelte` | shell, nav, workspace, tema, membuat 3 controller sekali | state domain |

Pola controller yang harus dipertahankan:
```js
import { writable } from "svelte/store";
export function createXController(deps) {
  const { subscribe, update, set } = writable({ items: [], busy: false, error: "" });
  async function load(workspace) { /* ... */ }
  return { subscribe, load };
}
```
Komunikasi komponen ke atas lewat **callback prop** (bukan event dispatcher baru).

## Pola wajib untuk pekerjaan P1

### 1. Pembatalan + timeout stream
`consumeEventStream()` di `api/http.js` belum punya `AbortController`. Tambahkan parameter `signal`, teruskan ke `fetch`, dan bungkus `JSON.parse` dengan try/catch (frame rusak diabaikan atau dilaporkan sebagai error terkontrol, bukan crash).
```js
const ac = new AbortController();
const timer = setTimeout(() => ac.abort(new DOMException("timeout", "TimeoutError")), ms);
try { await consumeEventStream(url, opts, onEvent, ac.signal); }
finally { clearTimeout(timer); }
```
Controller menyimpan `ac` aktif; memulai request baru atau berganti workspace memanggil `ac.abort()` lebih dulu. Bedakan `AbortError` (disengaja, tidak tampil sebagai error) dari kegagalan jaringan.

### 2. Guard race (token generasi)
```js
let gen = 0;
async function load(ws) {
  const my = ++gen;
  const data = await fetchSomething(ws);
  if (my !== gen) return;   // hasil usang, buang
  update(s => ({ ...s, ...data }));
}
```

### 3. Error terpisah per konteks
Gunakan field berbeda (`listError`, `uploadError`) alih-alih satu `error` bersama.

### 4. Batasi pertumbuhan state
Log/riwayat memakai `.slice(-N)`. `ingestionLogs` saat ini tidak dibatasi: tambahkan batas.

### 5. Render `refused` dan sitasi
Pesan assistant punya `text`, `refused`, `sources`, `graph`. View wajib menangani `refused` (lihat skill brand guideline). Sitasi bisa diklik memakai `chunk_id`/`page_label`/`headings` yang sudah ada di payload.

## Kontrak backend yang dipakai UI
`GET /api/documents`, `POST /api/ingestions` (FormData, maks 250 MiB), `GET /api/ingestions/{id}/events` (SSE), `POST /api/chat/stream` (SSE), `GET /api/graph/stream` (SSE). Belum dipakai UI: `/api/health`, `GET /api/ingestions/{id}`, `POST /api/chat`, `GET /api/graph`. Jangan mengubah kontrak backend tanpa permintaan user; jika UI butuh endpoint baru (mis. DELETE dokumen), laporkan dulu sebagai ketergantungan backend.

## Aturan umum kode
- Tanpa dependensi baru tanpa persetujuan (Vitest untuk P2.16 adalah pengecualian bila tugasnya itu).
- JSDoc ringan boleh untuk tipe payload; jangan memperkenalkan TypeScript.
- `{#each}` selalu dengan key stabil (`id`), bukan indeks.
- Tidak ada side effect di body komponen selain inisialisasi; gunakan `onMount`/`onDestroy` dan bersihkan listener, timer, dan stream.
- Teks UI Indonesia, ikuti skill brand guideline.
- Hindari duplikasi: contoh yang sudah diketahui `prominentNodeIds` terduplikasi antara graph dan inline graph; ekstrak ke utilitas bersama bila menyentuhnya.
- Normalisasi payload tidak konsisten (`entity_name||name`, `src_id||source||entity1`): taruh di satu fungsi normalizer, jangan menyebarkannya.

## Checklist cepat
- [ ] Tidak ada runes/gaya Svelte 5 baru di file klasik
- [ ] Arah impor mengikuti api → state → components/views
- [ ] Stream bisa dibatalkan, timeout ditangani, race dijaga
- [ ] Listener/timer/stream dibersihkan saat unmount
- [ ] `npm --prefix webui run build` lolos