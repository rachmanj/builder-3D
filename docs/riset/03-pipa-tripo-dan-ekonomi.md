# Spike 003 — satu kalimat → GLB AI → slice → angka gramasi

**Pertanyaan:** Bisakah seluruh pipa jalan dari satu kalimat sampai angka gramasi yang bisa
dipercaya, dan berapa biaya bahan kalau warnanya banyak?

**Verdict: VALIDATED** untuk pipa dan pengukuran. Satu koreksi penting ditemukan di tengah
jalan — angka "terbuang" di versi pertama laporan ini **3× terlalu besar** karena kesalahan
setelan di kode Dea sendiri. Sudah diperbaiki; semua angka di bawah memakai setelan yang benar.

---

## Pipa-nya jalan, dari satu kalimat

Perintah yang dikirim ke Tripo V3 (`v3.1-20260211`):

> *A small ceramic sitting cat figurine, glossy white body with blue batik patterns and
> gold accents on the ears and tail*

| Tahap | Hasil |
|---|---|
| Tripo text-to-3D | task `d5cc18f6…`, sukses **154 detik**, 20 kredit (saldo 100 → 80) |
| GLB | `tripo-kucing.glb`, 4.207.264 byte |
| Isi mesh | 16.416 vertex · 28.434 segitiga · tekstur 2048×2048 |
| Konversi per-facet | 3 kelompok: `#1E4895` (batik), `#7D8590`, `#B5B4AF` |
| Slice di P2S | berhasil |

## Koreksi: multiplier flush

Profil P2S bawaan memakai **`flush_multiplier = 0.3`** dan matriks 280 mm³ per pasangan warna
(`flush_volumes_vector = 140,140`). Kode Dea sebelumnya **memaksa 1.0**, jadi angka terbuang
yang dilaporkan pertama kali (273 g) **tiga kali lipat dari seharusnya** (~98 g realistis).

## Kurva trade-off warna vs bahan (kucing 80 mm, 3 warna)

| Pemecahan warna | Wilayah | Ganti warna | Bahan tercetak | Total | **Terbuang** | Waktu | Motif |
|---|---|---|---|---|---|---|---|
| mentah (per segitiga) | 1.452 | 766 | 125,2 g | 222,8 g | **97,6 g** | 21,2 jam | berisik (salt-and-pepper) |
| **halus (filter 6×, min 600)** | **4** | **375** | 77,6 g | 125,2 g | **47,6 g** | 10,6 jam | motif bertahan |
| terlalu kasar (filter 8×, min 2000) | 1 | 33 | 50,5 g | 54,7 g | 4,2 g | 2,7 jam | **motif hilang** |

Titik tengahnya jelas: **filter 6× + min 600** mempertahankan motif dengan terbuang 47,6 g
(61% dari bahan tercetak). Yang paling kanan memang hemat, tapi modelnya jadi satu warna —
tidak berguna untuk pengguna yang minta batik.

## Selisih 1,2× — SUDAH TERJELASKAN, dan temuannya lebih penting

Dugaan pertama Dea (nilai flush ditentukan warna filamen) **salah** — diuji terkendali:
geometri, pemecahan, mesin, dan multiplier semuanya sama, hanya warna filamen diubah:

| Warna filamen | mm³ per ganti warna |
|---|---|
| putih / krem / abu-terang | 102,1 |
| hitam / putih / merah | 102,6 |
| biru / kelabu / putih-tulang (asli) | 102,2 |

Warna tidak berpengaruh. Yang berpengaruh: **ada lantai minimum per ganti warna.**

### Model flush yang terverifikasi (galat maks 2,5%)

```
terbuang per ganti warna = max(101,6 mm³ , 280 mm³ × flush_multiplier)
```

| multiplier | terukur (mm³/ganti) | model | selisih |
|---|---|---|---|
| 0,15 | 101,8 | 101,6 | +0,2% |
| 0,30 | 102,9 | 101,6 | +1,3% |
| 0,60 | 172,2 | 168,0 | +2,5% |
| 1,00 | 287,0 | 280,0 | +2,5% |
| 2,00 | 570,6 | 560,0 | +1,9% |

### Konsekuensi untuk produk (ini yang harus disampaikan ke pengguna)

- **Menurunkan `flush_multiplier` di bawah ~0,36 tidak ada gunanya.** Lantai 101,6 mm³ tetap
  kena. Titik potongnya di multiplier ≈ 0,36.
- **Satu-satunya tuas nyata adalah mengurangi JUMLAH ganti warna** — artinya menyederhanakan
  motif, bukan menyetel slicer.
- Untuk model kucing ini: 376 ganti warna × 0,128 g = **minimum 48 g terbuang**, tidak bisa
  dihindari apa pun setelannya. Angka itu yang harus diberitahukan lebih dulu.

## Yang ini justru fitur, bukan cacat

Trade-off-nya nyata dan tidak bisa dihilangkan: motif halus memang butuh banyak ganti warna.
Yang bisa kita lakukan — dan tidak dilakukan WujudTin — adalah **menampakkannya sebelum
mencetak, lengkap dengan angkanya**:

> "Motif aslinya butuh 375 ganti warna → 47,6 g filamen terbuang (61% dari model), 10,6 jam.
> Kalau motifnya disederhanakan jadi … g dan … jam, tapi bentuk motifnya berubah."

WujudTin hanya **memperingatkan** kalau terbuang lebih berat dari modelnya. Kita bisa
**menawarkan pilihannya sekaligus angkanya** — bedanya antara peringatan dan keputusan.

## Jebakan teknis yang ketemu

1. **`flush_multiplier` bawaan profil 0.3 — jangan dipaksa 1.0.** Kesalahan ini membuat angka
   Dea salah 3×. Sama juga: matriks bawaan 280 mm³, `flush_into_support = 1`.
2. Pemicu biaya bukan jumlah wilayah warna, tapi **berapa potongan warna muncul per lapisan.**
   Wilayah turun 1.452 → 4 (99%), tapi ganti warna cuma 766 → 375, karena motif batik tetap
   muncul di hampir setiap lapisan.
3. Ambang `min_size` terlalu besar **menghapus motif**, bukan menyederhanakannya. Batasnya
   harus dicari per model, bukan satu angka untuk semua.
4. Kredit Tripo: 1 kredit = $0.01; teks-3D bertekstur v3.1 = 20 kredit (±Rp3.300). Dibekukan
   saat task dibuat, dipotong hanya kalau sukses — gagal/batal dikembalikan.
5. Pakai V3 (`https://openapi.tripo3d.ai/v3`) — V2 berhenti total 1 November 2026.
6. Kunci API: `~/.hermes/secrets/tripo_api_key.txt` (mode 600), dibaca skrip, tidak pernah
   ditampilkan.

## Cara menjalankan ulang

```bash
python3 submit_tripo.py                 # kalimat -> GLB (20 kredit)
python3 ../002-gltf-to-perfacet/glb2perfacet.py data/tripo-kucing.glb 3 80
python3 segment_merge.py                # gabung wilayah + buang pulau kecil
python3 tradeoff.py <filter_x> <min_wilayah> <jumlah_warna>
```

## Pemecahan warna otomatis — hasil jujurnya

Dua pendekatan dicoba, keduanya memberi pelajaran:

**1. Proksi geometris (tanpa slice) — GAGAL.** Proksi menghitung berapa komponen warna
melintasi tiap lapisan Z. Hasil: diprediksi **8** ganti warna, kenyataan **432**. Sebabnya, satu
wilayah warna bisa terpotong jadi banyak bagian di tiap lapisan, dan slicer berganti warna per
bagian — bukan per wilayah. Proksi murah tidak bisa dipercaya. **Kesimpulan: harus diukur.**

**2. Cari + ukur — jalan, tapi tidak monoton.** Empat kandidat, semuanya di-slice sungguhan:

| Setelan | Porsi warna akhir | Ganti warna (terukur) | Total |
|---|---|---|---|
| filter 2 / min 0 | 17% / 21% / 62% | 763 | 219,60 g |
| **filter 6 / min 400** | 7,6% / 11,1% / 81,3% | **479** | **144,99 g** |
| filter 8 / min 800 | 7,2% / 11,2% / 81,6% | 623 | 172,99 g |
| filter 8 / min 1600 | 7,2% / 11,0% / 81,9% | 630 | 174,36 g |

Perhatikan: **filter lebih agresif justru lebih buruk** (479 → 623 → 630). Penyebabnya
perlindungan aksen mengembalikan wilayah mentah beserta kebisingannya.

**3. Perbaikan perlindungan aksen (kunci + haluskan ulang + isi lubang) — tetap lebih mahal:**

| Setelan | Porsi warna | Ganti warna | Total |
|---|---|---|---|
| filter 6 / min 600 **tanpa** proteksi | 2% / 9% / 88% | **373** | 124,04 g |
| filter 6 / min 400 + proteksi terkunci | 8% / 11% / 81% | 485 | 145,98 g |
| filter 6 / min 600 + proteksi terkunci | 8% / 12% / 80% | 595 | 166,58 g |

**Kesimpulan yang harus diterima:** motif batik itu **memang tersebar** di seluruh permukaan.
Setiap usaha mempertahankannya menambah ganti warna. Jadi ini **bukan bug algoritma — ini
sifat motifnya.** Tidak ada solusi yang memberi kesetiaan penuh sekaligus limbah kecil.

Karena itu rancangan yang benar bukan "pilih satu setelan otomatis", tapi:
**ukur 2–3 titik di spektrum, lalu biarkan pengguna memilih dengan angka di tangan.**

| Pilihan pengguna | Ganti warna | Total | Terbuang | Waktu | Motif |
|---|---|---|---|---|---|
| setia pada motif | ~485 | 146 g | ~59 g | ~13 jam | warna aksen aman (8/11/81%) |
| seimbang | ~373 | 124 g | ~48 g | ~11 jam | aksen menyusut jadi 2% |
| hemat | ~33 | 55 g | ~4 g | 2,7 jam | motif hilang |

## Verdict: VALIDATED

Pipa **kalimat → AI → GLB → warna per-facet → slice → gram + terbuang** terbukti jalan,
terukur, dan **angkanya sudah bisa dipertanggungjawabkan sampai satuan gram**: model flush-nya
terverifikasi dengan galat maksimum 2,5%, dan lantai 101,6 mm³ per ganti warna menjelaskan
seluruh perilakunya.

Sisa pekerjaan (tidak lagi soal akurasi, tapi soal kegunaan): pemilihan pemecahan warna
otomatis per model, dan penyajian trade-off itu ke pengguna sebagai pilihan berangka.
