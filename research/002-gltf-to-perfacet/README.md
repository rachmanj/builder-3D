# Spike 002 — GLB bertekstur → warna per-facet → slice

**Pertanyaan:** Bisa tidak mengubah GLB bertekstur (keluaran mesin 3D AI) menjadi penugasan
filamen per segitiga, lalu di-slice jadi angka gram per warna yang **bisa dipercaya**?

**Verdict: VALIDATED.** Pipa konversinya jalan, dan akunting gram-nya sudah bisa dipercaya —
dengan metode ukur yang diverifikasi tiga kali di tiga model berbeda.

---

## Rumus yang bisa dipakai (sudah diverifikasi)

```
bahan tercetak   = weight_g  pada flush_multiplier = 0
total dibutuhkan = weight_g  pada flush_multiplier = pemakaian normal
filamen TERBUANG = total - bahan tercetak
per warna        = used_g di slice_info.config  (jumlahnya = total)
```

Dua slice per model. Tidak perlu menebak apa pun.

### Verifikasi silang (terukur vs hitungan matriks)

| Model | Ganti warna | Terbuang terukur | Prediksi (n × 280 mm³ × 1,26) | Selisih |
|---|---|---|---|---|
| Spiral 2 warna | 25 | 8,669 g | 8,820 g | 1,7% |
| Avocado 3 warna | 213 | 77,098 g | 75,148 g | 2,6% |
| Kubus 3 warna | 597 | 212,795 g | 210,600 g | 1,0% |

**Kelinieran diuji langsung:** `flush_multiplier` 0 → 0,5 → 1 → 2 memberi
16,619 / 20,954 / 25,288 / 33,957 g — tepat linier, m=2 persis dua kali m=1.
Jadi tuas purge yang benar adalah **`flush_multiplier`**.

## Yang jalan

| Tahap | Hasil |
|---|---|
| Baca GLB tanpa dependensi luar | Avocado: 406 vertex / 682 segitiga, tekstur 2048×2048 |
| Sampel tekstur di titik berat tiap segitiga | berhasil |
| k-means → palet warna → filamen | Avocado: `#386112`, `#659C2D`, `#E4D863` |
| `paint_color` per segitiga → 3MF | terbentuk |
| Slice di P2S (1 nozzle, tanpa GPU) | berhasil, keluar gram per warna + G-code |

Contoh Avocado 80 mm, 3 warna:

```
bahan tercetak  =  39,373 g
total dibutuhkan= 116,471 g
filamen terbuang=  77,098 g   (213 ganti warna)
per warna       = 57,31 / 33,57 / 24,39 g
```

## Jebakan akunting yang hampir menipu

1. **`model_weight_g` tidak berarti "berat model"** di mode multi-warna. Kubus 60 mm:
   1 warna 59,31 g, 3 warna "model" 290,54 g — geometri identik.
2. **`weight_g − model_weight_g` BUKAN angka terbuang.** Di kubus 60 mm, selisih itu cuma
   40,655 g, padahal terbuang sebenarnya **212,795 g** — salah 5×. Ini kesalahan yang pernah
   Dea buat dan sudah ditarik kembali.
3. **`flush_volumes_matrix` yang kita tulis di `project_settings.config` diabaikan**
   (280 → 2000 → 0 tidak mengubah apa pun). Nilai efektif datang dari matriks otomatis
   slicer berdasarkan warna filamen (~280 mm³ per perubahan untuk pasangan warna di uji ini).
   Yang bisa dipakai sebagai tuas hanya **`flush_multiplier`**.
4. **`filament_used_m` hanya berisi satu nilai**, walau filamennya tiga — itu total lewat
   nozzle, bukan per filamen. Per filamen ada di `slice_info.config`.
5. **Perbandingan volume-mesh vs gram per warna TIDAK SAH** untuk mesh tertutup yang dipisah
   per warna permukaan: bagian dalamnya tidak ikut terbagi, jadi rasionya menyesatkan.
   Pemeriksaan ini sudah dibuang dari skrip.

## Temuan yang belum terjelaskan (perlu lanjut)

Model yang sama, **bahan tercetak** naik dari 59,31 g (1 warna) jadi 118,42 g (3 warna,
`flush_multiplier` 0). Artinya pembagian warna menambah bahan tercetak sekitar 2×, terpisah
dari purge. Sebab yang paling mungkin: slice menambah dinding dan infill padat di setiap
batas warna. **Konsekuensinya penting untuk produk:** cara kita memecah warna menentukan
biaya bahan hampir sebanyak purge — kalau terlalu banyak pecahan kecil, hasilnya boros.
Ini harus diukur dan jadi peringatan untuk pengguna, bukan dibiarkan tersembunyi.

## Catatan operasional

- Hasil antar-run bisa berbeda ±1% (urutan segitiga/palet bisa bergeser sedikit).
- Slicing satu model 682 segitiga: prepare ~14 s, selesai dalam hitungan menit di CPU.
  Dua slice per model = dua kali biaya. Bisa dioptimalkan nanti (slice pengukuran
  dengan kualitas lebih rendah).
- Jangan janjikan presisi lebih halus dari ±3% ke pengguna; itu batas yang Dea ukur.

## Cara menjalankan

```bash
python3 glb2perfacet.py data/BoxTextured.glb 3 60
python3 glb2perfacet.py data/Avocado.glb 3 80
```

Skrip menjalankan dua slice otomatis dan mencetak angka tercetak / total / terbuang.

## Verdict: VALIDATED

Rantai **GLB bertekstur → warna per-facet → 3MF → slice → gram per warna + terbuang**
terbukti jalan dan angkanya bisa dipertanggungjawabkan, dengan metode ukur yang diverifikasi
silang di tiga model. Sisa satu pertanyaan terbuka: overhead bahan akibat pembagian warna.
