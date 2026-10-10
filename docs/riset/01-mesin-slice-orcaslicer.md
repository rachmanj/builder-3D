# Spike 001 — OrcaSlicer headless sebagai mesin gramasi nyata

**Pertanyaan:** Bisakah kita menjalankan OrcaSlicer di backend (headless, tanpa GPU) dan
mengeluarkan angka filamen **nyata** — gram per warna + gram yang terbuang saat ganti
warna — dari **model berwarna per-facet**, bukan estimasi?

**Verdict: VALIDATED.** Semua yang dijual WujudTin sudah bisa kita hasilkan dari slice asli.

---

## Hasil akhir (semuanya dari slice nyata)

| Uji | Mesin | Total | Model | **Terbuang** | Per warna | Waktu | Ganti tool |
|---|---|---|---|---|---|---|---|
| STL 1 warna | P2S 0.4 | 12,69 g | 12,69 g | 0 | 12,69 g | 1370 s | 0 |
| Per-facet 2 warna | H2D Pro 0.4 (2 nozzle) | 20,60 g | 10,67 g | **9,93 g** | 11,09 / 9,51 g | 3284 s | 28 |
| Per-facet 2 warna | **P2S 0.4 (1 nozzle)** | 25,29 g | 18,39 g | **6,90 g** | 13,32 / 11,97 g | 4274 s | 25 |

Keluarannya: gram per filamen, gram model, gram terbuang, waktu cetak, jumlah ganti warna,
dan **G-code siap cetak** (1,3 MB untuk model 840 segitiga).

## Bagaimana caranya

1. **Jalankan engine** — `ghcr.io/leolobato/orcaslicer-headless:latest` (OrcaSlicer 2.3.2-53),
   1,74 GB, siap dalam 5 detik, REST API di port 8070, **tanpa GPU**.
   Katalog: 885 mesin / 2.562 proses / 4.521 filamen / 62 vendor.

2. **Beri warna per segitiga** lewat atribut `paint_color` di `3D/3dmodel.model`.
   Formatnya bitstream: `splitSides(2 bit) + leafState(2 bit)`, dibaca LSB-first dan string
   hex-nya dibalik (karakter terakhir = 4 bit pertama). Untuk filamen ke-N:

   | Filamen | paint_color |
   |---|---|
   | 1 | `4` |
   | 2 | `8` |
   | 3 | `0C` |
   | 4 | `1C` |

   Rumus umum: N ≤ 2 → nibble `N*4`; N ≥ 3 → nibble `0xC` lalu (N−3) dalam potongan 4 bit,
   `0xF` = +15 & lanjut.

3. **Bangun 3MF**: satu objek berisi seluruh mesh dengan `paint_color` per segitiga +
   `Metadata/model_settings.config` (objek, extruder default) + `Metadata/project_settings.config`
   (machine, process, filamen, `flush_volumes_matrix`). Logo `Application = BambuStudio-...`
   dan `BambuStudio:3mfVersion` **wajib** ada, kalau tidak `paint_color` diabaikan.

4. **Slice**: `POST /3mf` (upload) → `POST /slice/v2` dengan `filament_settings_ids` sepanjang
   jumlah filamen → `GET /3mf/{output_token}`.

5. **Baca hasil**: `estimate.weight_g` (total termasuk terbuang) dan `estimate.model_weight_g`
   (berat model saja). **Selisihnya = filamen terbuang.** Per warna di
   `Metadata/slice_info.config`: `<filament id="1" color="#FF0000" used_m="4.39" used_g="13.32"/>`
   (jumlahnya = total, jadi sudah termasuk bagian purge-nya).

6. **Verifikasi** di G-code: hitung baris `T<n>` (jumlah ganti tool) dan blok `FLUSH_START`.
   Catatan: purge dijalankan **firmware** lewat macro `M620.10 ... L[flush_length]`, jadi
   tidak muncul sebagai gerakan `G1 E` — angkanya ada di `flush_volumes_matrix` × `flush_multiplier`.

## Temuan penting untuk produk

- **Penghalang "multi-warna" di percobaan awal ternyata salah pendekatan.** Menugaskan filamen
  lewat *objek terpisah* (2 objek, `extruder` 1 & 2) ditolak `filament_printable`
  (`GCode/ToolOrdering.cpp`). Dengan **warna per-facet pada SATU objek**, slice jalan mulus —
  termasuk di **mesin 1 nozzle (P2S)** yang dipakai mayoritas pengguna. Jadi tidak ada
  penghalang; arsitektur per-facet memang yang benar.
- **Profil mesin sangat menentukan hasil.** Model yang sama: H2D Pro → 10,67 g model;
  P2S → 18,39 g model. Karena itu **pengguna wajib memilih printer dan nozzle-nya**; kalau
  tidak, angkanya salah dan itu merusak kepercayaan.
- **Hasil bisa lebih jujur dari kompetitor:** bukan "0,0 g contoh", tapi angka hasil slice
  lengkap dengan G-code yang benar-benar bisa dicetak.
- Waktu prepare: ~14 s untuk model sederhana, 315 s untuk project 8 warna yang berat.
  Untuk produksi perlu worker terpisah + antrean.

## Jebakan yang ketemu di jalan

1. **`setting_id` mesin bertabrakan antar vendor.** `GM001` = "Bambu Lab X1 Carbon 0.4 nozzle"
   DAN "Afinia H+1(HS) 0.4 nozzle". API memilih yang pertama **tanpa peringatan** → mesin salah,
   errornya menyesatkan. Wajib cek keunikan global: aman = `GM049` (P2S), `GM051` (H2D Pro),
   `GM020` (A1 mini).
2. **Filamen terikat mesin** (`compatible_printers`). PLA Basic @BBL X1C tidak boleh di P2S.
3. **Panjang matriks flush harus cocok dengan jumlah filamen.** Kalau tidak:
   `export_gcode: Flush volumes matrix do not match to the correct size!` — dan ini muncul
   **setelah** slicing selesai (60%), jadi tampak menggantung.
4. `filament_map` di request = peta filamen→**nozzle** (nilai 1..`nozzle_count`), bukan slot AMS.
5. Mesin H2S/H2D jalur **2 nozzle**; H2D Pro pernah segfault dengan 3MF rakitan yang cacat.
6. Vektor di `project_settings.config` harus diselaraskan panjangnya
   (`filament_colour`, `filament_type`, `filament_map`, `flush_multiplier`).

## Cara menjalankan ulang

```bash
docker run -d --name orca-spike -p 8070:8070 -v $PWD/data:/data \
  ghcr.io/leolobato/orcaslicer-headless:latest
python3 run_spike.py    # tahap 1: STL 1 warna
python3 run_spike2b.py  # tahap 2: varian penugasan per-objek (jalan buntu, sengaja disimpan)
python3 run_spike4.py   # tahap 3: project multi-warna asli OrcaSlicer
python3 run_spike5.py   # tahap 4: TARGET UTAMA — 3MF per-facet buatan sendiri
```

## Verdict: VALIDATED

Pembeda "slice asli, bukan estimasi" **bisa ditegakkan**: gram per warna, gram terbuang,
waktu cetak, dan G-code jadi — dari model berwarna per-facet, di mesin 1 nozzle, tanpa GPU,
dalam hitungan detik sampai beberapa menit.
