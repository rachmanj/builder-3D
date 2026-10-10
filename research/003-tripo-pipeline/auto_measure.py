#!/usr/bin/env python3
"""Spike 003 langkah 6 — pemecahan warna otomatis, dengan PENGUKURAN bukan proksi.

Pelajaran dari langkah 5: proksi geometris salah jauh (prediksi 8 vs nyata 432 ganti warna).
Sebabnya: satu wilayah warna bisa terpotong jadi banyak bagian di setiap lapisan, dan slicer
berganti warna per bagian. Jadi proksi murah tidak bisa dipercaya.

Pendekatan sekarang:
  1. susun beberapa kandidat setelan (filter x ambang wilayah)
  2. LINDUNGI warna aksen: warna yang porsinya jatuh di bawah 50% porsi aslinya dikembalikan
  3. slice SUNGGUHAN tiap kandidat, hitung ganti warna terukur
  4. pilih yang paling sedikit ganti warna di antara kandidat yang semua warnanya selamat
  5. ukur bahan tercetak + terbuang untuk pemenangnya

Pakai:  python3 auto_measure.py rank     (ukur semua kandidat)
        python3 auto_measure.py purge    (ukur terbuang untuk pemenang)
"""
import importlib.util
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TPL = os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "data", "template-p2s.3mf")
GLB = os.path.join(HERE, "data", "tripo-kucing.glb")
FILS3 = ["GFSA00_11", "GFSA01_12", "GFSA00_11"]

# kandidat: (filter_x, ambang_wilayah_segitiga)
KANDIDAT = [(2, 0), (6, 400), (8, 800), (8, 1600)]
FLOOR_AKSEN = 0.5      # warna harus tahan >= 50% porsi aslinya


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


g2p = load("g2p", os.path.join(os.path.dirname(HERE), "002-gltf-to-perfacet", "glb2perfacet.py"))
sm = load("sm", os.path.join(HERE, "segment_merge.py"))
s5 = g2p.load_s5()


def protect(labels, adj, raw, n_fil_or_share, floor_ratio=FLOOR_AKSEN):
    """Jaga setiap warna agar tidak kehilangan lebih dari (1-floor_ratio) porsi aslinya."""
    labels = list(labels)
    for g, raw_share in n_fil_or_share.items():
        target = max(1, int(raw_share * floor_ratio))
        cur = sum(1 for l in labels if l == g)
        if cur >= target:
            continue
        comps = [(lab, c) for lab, c in sm.components(raw, adj) if lab == g]
        comps.sort(key=lambda t: -len(t[1]))
        for _, comp in comps:
            if cur >= target:
                break
            for t in comp:
                if labels[t] != g:
                    labels[t] = g
                    cur += 1
    return labels


def build(path, verts2, tris, tri_fil, colors, mult):
    with zipfile.ZipFile(TPL) as z:
        items = {n: z.read(n) for n in z.namelist()}
    vx = "\n".join(f'     <vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in verts2)
    tr = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{s5.encode_paint(f)}"/>'
                   for (a, b, c), f in zip(tris, tri_fil))
    items["3D/3dmodel.model"] = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">
 <metadata name="Application">BambuStudio-2.3.2</metadata>
 <metadata name="BambuStudio:3mfVersion">1</metadata>
 <resources><object id="1" type="model"><mesh><vertices>
{vx}
</vertices><triangles>
{tr}
</triangles></mesh></object></resources>
 <build><item objectid="1" transform="1 0 0 0 1 0 0 0 1 128 128 0" printable="1"/></build>
</model>
'''.encode()
    items["Metadata/model_settings.config"] = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="1">
    <metadata key="name" value="model-ai"/>
    <metadata key="extruder" value="1"/>
    <part id="1" subtype="normal_part">
      <metadata key="name" value="source.stl"/>
      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>
      <metadata key="source_file" value="source.stl"/>
      <metadata key="source_object_id" value="0"/>
      <metadata key="source_volume_id" value="0"/>
      <metadata key="source_offset_x" value="0"/>
      <metadata key="source_offset_y" value="0"/>
      <metadata key="source_offset_z" value="0"/>
      <mesh_stat edges_fixed="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>
    </part>
  </object>
  <assemble>
  </assemble>
</config>
'''.encode()
    cfg = json.loads(items["Metadata/project_settings.config"].decode())
    cfg["filament_colour"] = colors
    cfg["filament_type"] = ["PLA"] * len(colors)
    cfg["filament_map"] = ["1"] * len(colors)
    if mult is not None:
        cfg["flush_multiplier"] = [str(mult)] * len(colors)
    items["Metadata/project_settings.config"] = json.dumps(cfg, indent=1).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in items.items():
            z.writestr(k, v)
    return g2p.slice_3mf(s5, path, "GM049", "GP155", FILS3[:len(colors)])


def siapkan():
    verts, uvs, tris, tex = g2p.extract_geometry(GLB)
    img = Image.open(io.BytesIO(tex)).convert("RGB")
    cols = g2p.sample_triangle_colors(img, uvs, tris)
    pal = [tuple(int(round(c)) for c in p) for p in
           g2p.kmeans(cols[:: max(1, len(cols) // 4000)], 3)]
    raw = g2p.assign(cols, pal)
    adj = sm.build_adjacency(verts, tris)
    verts2, _ = g2p.scale_to(verts, uvs, tris, 80.0)
    raw_share = {g: sum(1 for r in raw if r == g) for g in range(3)}
    return verts, uvs, tris, verts2, adj, raw, raw_share, ["#%02X%02X%02X" % p for p in pal]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "rank"
    verts, uvs, tris, verts2, adj, raw, raw_share, colors = siapkan()
    n = len(raw)
    print("porsi warna asli: " + ", ".join(f"{g+1}: {100*v/n:.1f}%" for g, v in raw_share.items()))

    hasil = []
    for iters, minsize in KANDIDAT:
        lab = sm.drop_small_regions(sm.mode_filter(raw, adj, iters), adj, minsize) if minsize else \
            sm.mode_filter(raw, adj, iters)
        lab = protect(lab, adj, raw, raw_share)
        share = Counter(lab)
        selamat = all(share[g] >= max(1, int(raw_share[g] * FLOOR_AKSEN)) for g in range(3))
        porsi = " ".join(f"{g+1}:{100*share[g]/n:4.1f}%" for g in range(3))
        if mode == "rank":
            r = build(os.path.join(DATA, f"rk-{iters}-{minsize}.3mf"), verts2, tris,
                      [x + 1 for x in lab], colors, None)
            if r.get("_err"):
                print(f"  filter {iters} min {minsize}: GAGAL {r['msg'][:120]}"); continue
            nT = len(re.findall(r"^T[0-9]+$", r["gc"], re.M))
            hasil.append((iters, minsize, nT, r["est"]["weight_g"], selamat))
            print(f"  filter {iters:>2} min {minsize:>5} | porsi {porsi} | selamat={selamat} "
                  f"| ganti warna TERUKUR {nT:>4} | total {r['est']['weight_g']:7.2f} g")
        else:
            hasil.append((iters, minsize, None, None, selamat, lab))
            print(f"  filter {iters:>2} min {minsize:>5} | porsi {porsi} | selamat={selamat}")

    if mode == "rank":
        layak = [h for h in hasil if h[4]]
        if not layak:
            print("  tidak ada kandidat yang semua warnanya selamat"); return
        best = min(layak, key=lambda h: h[2])
        json.dump({"iters": best[0], "minsize": best[1], "swaps": best[2], "total": best[3]},
                  open(os.path.join(DATA, "auto-pilihan.json"), "w"), indent=1)
        print()
        print(f"  PILIHAN: filter {best[0]}x, min {best[1]} -> {best[2]} ganti warna, "
              f"total {best[3]:.2f} g")
        print("  (angka ini hasil slice sungguhan, bukan proksi)")
    else:
        print("pakai auto_measure.py rank dulu")


if __name__ == "__main__":
    main()
