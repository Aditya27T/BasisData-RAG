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
