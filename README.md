# Gramasi

Dari **satu kalimat atau satu foto** jadi model 3D siap cetak — dengan jawaban yang paling
dicari orang sebelum mencetak: **butuh berapa gram filamen?**

Bukan estimasi. Angkanya dari **slice sungguhan** oleh OrcaSlicer:

- gram filamen **per warna**
- gram yang **terbuang** saat printer berganti warna
- waktu cetak dan jumlah pergantian warna
- plus **G-code siap cetak** — bukan cuma model

Domain: `gramasi.sbs`

---

## Kenapa ini berbeda

Kompetitor (WujudTin, Meshy) memberi **satu** angka dan sebuah peringatan. Gramasi memberi
**pilihan dengan angkanya** — karena kesetiaan motif dan hemat bahan memang tidak bisa
dimaksimalkan bersamaan, dan itu bukan sesuatu yang boleh disembunyikan dari pengguna:

| Pilihan | Ganti warna | Total | Terbuang | Waktu | Motif |
|---|---|---|---|---|---|
| Setia pada motif | ~485 | 146 g | ~59 g | ~13 jam | warna aksen aman |
| Seimbang | ~373 | 124 g | ~48 g | ~11 jam | aksen menyusut |
| Hemat | ~33 | 55 g | ~4 g | 2,7 jam | motif hilang |

Angka di atas terukur pada model uji 80 mm, 3 warna, printer P2S. Semuanya hasil slice nyata.

---

## Status

**Riset selesai. MVP belum dibangun.**

Yang sudah terbukti jalan (lihat `research/` dan `docs/riset/`):

- OrcaSlicer jalan headless di Docker, **tanpa GPU**, siap dalam 5 detik
- GLB bertekstur → warna per segitiga (`paint_color`) → 3MF → slice → gram per warna + G-code
- Pipa lengkap dari satu kalimat: Tripo V3 → GLB → slice → angka gramasi
- Akunting filamen terverifikasi (galat maksimum 2,5%), termasuk lantai minimum per ganti warna

---

## Arsitektur yang direncanakan

```
pengguna ── kalimat/foto
   │
   ▼
[ Laravel: API + auth + queue + kredit ]        ← aplikasi
   │
   ├── job 1: Tripo V3 API ──► GLB
   │
   └── job 2: worker slice (Docker)
                 GLB → sampel tekstur per segitiga → palet warna
                     → 3MF dengan paint_color per segitiga
                     → OrcaSlicer /slice/v2
                     → gram per warna + terbuang + waktu + gcode
   │
   ▼
halaman hasil + unduh STL / 3MF / G-code
```

- **Host sementara:** satu mesin (16 core) + Cloudflare Tunnel
- **Mesin 3D:** Tripo API V3 untuk rilis awal; self-host (Hunyuan3D / TRELLIS) untuk margin
- **Mesin slice:** `ghcr.io/leolobato/orcaslicer-headless`

Spesifikasi lengkap: [`docs/spec-mvp.md`](docs/spec-mvp.md)

---

## Struktur repo

```
docs/
  spec-mvp.md              spesifikasi MVP
  riset/
    01-mesin-slice-orcaslicer.md
    02-glb-ke-warna-per-facet.md
    03-pipa-tripo-dan-ekonomi.md
research/                  kode riset (bukan kode produksi)
  001-orcaslicer-headless/
  002-gltf-to-perfacet/    glb2perfacet.py — pipa inti GLB → 3MF
  003-tripo-pipeline/
```

Kode di `research/` adalah kode eksperimen: berguna sebagai acuan dan bisa dijalankan ulang,
tapi **bukan** kode produksi. Pipa produksi akan tumbuh dari `glb2perfacet.py`.

---

## Pelajaran mahal dari riset (jangan diulang)

Enam kesalahan yang sudah memakan waktu, semuanya sudah terverifikasi:

1. **`weight_g − model_weight_g` bukan angka "terbuang".** Salah sampai **5×**. Yang benar:
   slice dua kali — bahan tercetak = `weight_g` pada `flush_multiplier` 0, terbuang = selisihnya.
2. **Jangan paksa `flush_multiplier`.** Bawaan profil 0,3. Memaksa 1,0 membuat angka terbuang
   **3× terlalu besar**.
3. **Proksi geometris untuk jumlah ganti warna tidak bisa dipercaya.** Prediksi 8, kenyataan
   432. Selalu slice untuk mengukur.
4. **`setting_id` mesin bertabrakan antar vendor.** `GM001` = Bambu X1 Carbon **dan** Afinia
   H+1. API memilih yang pertama tanpa peringatan dan errornya menyesatkan.
5. **Pengguna wajib memilih printer + nozzle.** Model yang sama: 10,67 g di H2D Pro, 18,39 g
   di P2S. Salah pilih mesin = angka salah.
6. **Ada lantai minimum per ganti warna** (terukur 101,6 mm³). Menurunkan `flush_multiplier`
   di bawah ~0,36 tidak memberi manfaat apa pun. Satu-satunya tuas adalah mengurangi jumlah
   ganti warna — yaitu menyederhanakan motif.

---

## Ekonomi (menentukan harga)

Biaya mesin 3D = 20 kredit Tripo = $0,20 ≈ **Rp3.260/model**. Selama pakai API, paket besar
mendekati rugi:

| Paket | Model | Biaya mesin | Fee gateway | Margin |
|---|---|---|---|---|
| Rp19.000 | 3 | Rp9.780 | Rp2.551 | 35% |
| Rp29.000 | 5 | Rp16.300 | Rp2.841 | 34% |
| Rp99.000 | 25 | Rp81.500 | Rp4.871 | 13% |
| Rp199.000 | 60 | Rp195.600 | Rp7.771 | **rugi** |

Self-host mesin 3D (±Rp250/model di GPU sewa) menaikkan margin ke **~88%**. Bedanya 13×.
**Margin ada di mesinnya, bukan di harganya.**

---

## Menjalankan ulang riset

```bash
# 1. mesin slice
docker run -d --name orca-spike -p 8070:8070 -v $PWD/data:/data \
  ghcr.io/leolobato/orcaslicer-headless:latest

# 2. pipa inti: GLB -> warna per-facet -> 3MF -> slice (dua kali, ukur tercetak + terbuang)
python3 research/002-gltf-to-perfacet/glb2perfacet.py contoh.glb 3 80

# 3. dari kalimat (perlu kunci Tripo)
python3 research/003-tripo-pipeline/submit_tripo.py
```

Katalog profil mesin tidak disimpan di repo (ukurannya besar). Ambil ulang dari container
yang jalan:

```bash
curl -s localhost:8070/profiles/machines   > machines.json
curl -s localhost:8070/profiles/processes   > processes.json
curl -s localhost:8070/profiles/filaments   > filaments.json
```

---

## Batas kejujuran

- Akurasi gramasi **±3%**; variasi antar-run ±1%. Jangan janji lebih halus.
- Jangan janji "hemat tanpa mengubah motif" — motif yang tersebar memang butuh banyak ganti
  warna. Itu pilihan pengguna.
- Hak atas model hasil AI masih perlu diverifikasi di ToS penyedia sebelum dijanjikan ke
  pengguna.
