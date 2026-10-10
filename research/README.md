# Kode riset

Kode eksperimen yang membuktikan pipa Gramasi bisa jalan. **Bukan kode produksi** — sengaja
dibiarkan apa adanya supaya hasilnya bisa diperiksa dan dijalankan ulang.

| Folder | Isi |
|---|---|
| `001-orcaslicer-headless/` | Uji OrcaSlicer headless: REST API, format `paint_color`, matriks flush, akunting gram |
| `002-gltf-to-perfacet/` | `glb2perfacet.py` — pembaca GLB tanpa dependensi luar, kmeans palet warna, penulis 3MF, dua-slice untuk mengukur tercetak + terbuang |
| `003-tripo-pipeline/` | Pipa dari satu kalimat (Tripo V3), penggabungan wilayah warna, kurva trade-off, uji kontrol flush |

Ringkasan hasil tiap tahap ada di `../docs/riset/`.

**Yang akan dipakai jadi kode produksi:** `002-gltf-to-perfacet/glb2perfacet.py`
(pembaca GLB + penulis 3MF) dan `001-orcaslicer-headless/run_spike5.py`
(encoder `paint_color`). Sisanya acuan.

Katalog profil mesin (`machines.json`, `processes.json`, `filaments.json`) tidak disimpan di
repo — regenerasi dari container yang jalan, lihat README utama.
