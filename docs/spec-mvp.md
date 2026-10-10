# Spec — Gramasi MVP

**Status:** draf untuk disetujui Iwan
**Tanggal:** 10 Oktober 2026
**Domain:** `gramasi.sbs` (Hostinger, NS masih parking — belum diarahkan)

---

## 1. Goal

Gramasi adalah layanan pembuat model 3D dari teks atau foto untuk kreator Indonesia, dengan
pembeda tunggal yang tidak dimiliki pesaing: **angka gramasi dari hasil slice NYATA**, bukan
estimasi.

Setiap model yang dibuat pengguna langsung dijawab:

- butuh berapa gram filamen, **per warna**
- berapa gram yang **terbuang** saat printer berganti warna
- berapa lama waktu cetaknya
- berapa kali printer berganti warna
- plus **G-code siap cetak** — bukan cuma model

Dan karena kesetiaan motif tidak bisa dimaksimalkan bersamaan dengan hemat bahan, pengguna
**diberi pilihan** dengan angka di tangan, bukan diberi satu angka dan peringatan.

**Ukuran keberhasilan MVP:** 10–20 pengguna pertama berhasil membuat model, melihat angka
gramasi, dan minimal 3 di antaranya mencetak hasilnya.

---

## 2. Scope

### Masuk MVP

1. Daftar/masuk akun (email + password)
2. Studio: satu kalimat atau satu foto → model 3D
3. Pipa lengkap: GLB → warna per-facet → 3MF → slice OrcaSlicer → gram + terbuang + waktu + G-code
4. **Pemilih printer dan nozzle** — wajib, karena profil mesin sangat menentukan angka
5. Tiga tingkat pemecahan warna (setia / seimbang / hemat) — **hasil pengukuran, bukan prediksi**
6. Halaman hasil dengan rincian per warna + unduh STL / 3MF / G-code
7. Koleksi model pengguna
8. Kredit: jatah gratis awal + pembelian kredit sekali pakai yang tidak hangus
9. Riwayat pemakaian kredit yang bisa dilihat pengguna

### Di luar MVP (tahap 2)

- Multiview (3 foto) dan sketsa PDF
- Animasi & rigging
- Galeri publik / komunitas
- Langganan bulanan
- API publik untuk pihak ketiga
- Self-host mesin 3D di GPU sendiri (sekarang pakai Tripo)
- Cetak langsung ke printer pengguna

---

## 3. Keputusan teknis

| Bagian | Keputusan | Alasan |
|---|---|---|
| Backend | **Laravel** (API + queue + auth) | Sesuai kebiasaan operasi Iwan; satu tumpukan dengan aplikasi lain |
| Worker slice | **Container OrcaSlicer headless** (`ghcr.io/leolobato/orcaslicer-headless`) di VPS yang sama | Butuh binary + CPU; tidak bisa serverless |
| Mesin 3D | **Tripo API V3** (`v3.1-20260211`) | 20 kredit/model (±Rp3.300), hasil sukses ±154 detik |
| Antrean | Laravel queue; **job generate** dan **job slice** dipisah statusnya | Waktu proses berbeda; slicing CPU-berat |
| Penyimpanan | Disk lokal VPS | File 4–8 MB per model; hindari egress |
| Frontend | Blade + Alpine dulu; SPA menyusul kalau UI perlu lebih kaya | Satu tumpukan, cepat, sesuai standar antislop Iwan |
| Domain | `gramasi.sbs` | Sudah dibeli; perlakukan sebagai penunjuk saja |
| Host | **dea-geekom** (mesin ini) + **Cloudflare Tunnel** | 16 core, hidup 4 minggu tanpa putus, 158 GB bebas, Docker ada, dan tunnel-nya sudah jalan untuk `vasia.sbs`. saphire-six cuma 2 core (tidak layak untuk slicing), saphire-two tidak ada akses kunci |

**Aturan yang tidak boleh dilanggar:** nama domain tidak boleh masuk ke nama database,
nama container, atau kode. Hanya di konfigurasi. Supaya pindah ke `gramasi.id` nanti cukup
ganti DNS.

---

## 4. Basis data (tabel inti)

- `users` — akun
- `credits` — saldo per pengguna (jumlah, terpakai, sisa)
- `credit_ledger` — mutasi: `user_id, delta, reason, ref_type, ref_id, created_at`
- `models` — `id, user_id, source_type(teks|foto), prompt, tripo_task_id, status, glb_path, thumb_path, tripo_credits, error`
- `slices` — `id, model_id, machine_setting_id, machine_name, process_setting_id, filament_setting_ids(json), segmentation_level, layer_height, grams_total, grams_model, grams_waste, print_seconds, color_swaps, stl_path, three_mf_path, gcode_path, status`
- `slice_colors` — `slice_id, slot, hex, grams, is_base`
- `printers` — cache katalog dari worker: `setting_id, name, vendor, nozzle_diameter, is_unique` (**hanya yang `setting_id`-nya unik global**)
- `orders` — `id, user_id, package, amount, gateway_ref, status` (kalau pembayaran sudah masuk)

Catatan: `printers.is_unique` wajib ada — lihat Risiko #1.

---

## 5. Halaman (UI/UX)

1. **Beranda** — satu kalimat contoh, tiga contoh hasil, tombol "Mulai gratis"
2. **Studio** — prompt / unggah foto; pilih printer + nozzle; pilih tingkat pemecahan warna; tombol buat
3. **Proses** — progres dua tahap (membuat model → menghitung gramasi)
4. **Hasil** — kartu angka: total, **per warna**, terbuang, waktu, jumlah ganti warna; tombol unduh STL / 3MF / G-code; pengalih tingkat setia-seimbang-hemat (memicu slice ulang)
5. **Koleksi** — daftar model + status
6. **Harga & Kredit** — paket, riwayat pemakaian

Ketentuan tampilan (standar Iwan): antislop 38 aturan, angka ringkas (juta/ribu), grafik
minimal, **tanpa teks Mandarin**, tema bukan AntD biru bawaan.

---

## 6. Endpoint

```
POST   /api/models                     {prompt | image} -> model_id
GET    /api/models/{id}                status + progres
POST   /api/models/{id}/slice          {machine, process, filaments[], segmentation}
GET    /api/slices/{id}                gram per warna, total, terbuang, waktu, swaps
GET    /api/slices/{id}/download/{stl|3mf|gcode}
GET    /api/printers                   katalog mesin (unik global saja)
GET    /api/credits                    saldo + riwayat
GET    /api/packages                   daftar paket kredit
POST   /api/checkout                   buat pembayaran
POST   /api/hooks/tripo                webhook status task Tripo
```

---

## 7. Risiko

1. **`setting_id` mesin bertabrakan antar vendor.** `GM001` = Bambu X1 Carbon **dan** Afinia
   H+1. API memilih yang pertama tanpa peringatan dan errornya menyesatkan. → `printers` hanya
   boleh memuat `setting_id` yang unik global.
2. **Margin biaya.** Tripo 20 kredit (±Rp3.300)/model + CPU slice. Harga paket harus dihitung
   ulang setelah tahu biaya sewa VPS per model. Jangan tetapkan harga sebelum ini dihitung.
3. **Beban CPU slice.** Model padat bisa 315 detik. Butuh batas konkurensi; kalau nanti pakai
   rumus lantai (`max(101,6 ; 280 × multiplier)`) bisa hemat satu slice per permintaan setelah
   lantai divalidasi per profil mesin.
4. **Ukuran file.** GLB 4–8 MB, G-code 1–6 MB per model. Hitung disk dan batas unduhan.
5. **Kesetiaan vs limbah tidak bisa otomatis optimal.** Sudah diputuskan jadi pilihan pengguna.
   Jangan pernah janji "hemat tanpa mengubah motif".
6. **Akurasi ±3%**, variasi antar-run ±1%. Jangan janji lebih halus.
7. **Hak dan lisensi.** Model jadi milik pengguna — tapi klaim ini harus diverifikasi dulu di
   ToS Tripo sebelum ditulis di halaman jualan.
8. **Kredit gagal generate.** Tripo mengembalikan kredit kalau task gagal; kredit pengguna juga
   harus dikembalikan, otomatis.

---

## 8. Ekonomi — temuan yang menentukan strategi

Biaya mesin 3D per model (Tripo, 20 kredit) = **$0,20 ≈ Rp3.260**. Slicing Rp0 (mesin sendiri).

| Paket | Model | Biaya mesin | Fee gateway | Margin | % |
|---|---|---|---|---|---|
| Rp19.000 | 3 | Rp9.780 | Rp2.551 | Rp6.669 | 35% |
| Rp29.000 | 5 | Rp16.300 | Rp2.841 | Rp9.859 | 34% |
| Rp29.000 | 8 | Rp26.080 | Rp2.841 | Rp79 | **0%** |
| Rp99.000 | 25 | Rp81.500 | Rp4.871 | Rp12.629 | **13%** |
| Rp199.000 | 60 | Rp195.600 | Rp7.771 | **-Rp4.371** | **rugi** |

**Kesimpulan: margin ada di mesinnya, bukan di harganya.** Selama pakai Tripo, paket besar
justru rugi — biaya mesin tumbuh linear sementara fee gateway tetap.

Kalau mesin 3D di-host sendiri (±Rp250/model di GPU sewa, pakai Hunyuan3D / TRELLIS):

| Paket | Model | Biaya mesin | Margin | % |
|---|---|---|---|---|
| Rp29.000 | 5 | Rp1.250 | Rp24.909 | **86%** |
| Rp99.000 | 25 | Rp6.250 | Rp87.879 | **89%** |

Itu bedanya **13×**. Karena itu peta jalannya: **rilis pakai Tripo untuk membuktikan ada
permintaan, lalu pindah ke mesin sendiri untuk mengambil margin.** Jangan jual paket besar
selama masih pakai Tripo.

**Usul harga tahap awal (pakai Tripo, margin sehat):**
- Rp19.000 — 3 model · Rp29.000 — 5 model · Rp79.000 — 15 model (margin ~18%, jangan lebih besar)
- Jatah gratis: **2 model** (biaya kita Rp6.520/orang), wajib verifikasi email

## 9. Yang perlu diputuskan sebelum mulai bangun

1. ~~Host~~ → **dea-geekom + Cloudflare Tunnel** (rekomendasi Dea, sudah didukung bukti)
2. **Frontend Blade+Alpine atau SPA** — Dea usul Blade+Alpine dulu
3. **Harga final** — Dea usul sesuai tabel di atas; jangan buka paket besar selama pakai Tripo
4. **Gateway pembayaran** (Affiliate.id seperti WujudTin / Midtrans / Xendit)
