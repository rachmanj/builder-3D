#!/usr/bin/env python3
"""Spike 003 langkah 5 — pemecahan warna OTOMATIS per model.

Masalah yang dipecahkan:
  - ambang tetap (min_size) bisa menghapus motif pada satu model, dan tidak cukup
    menghaluskan pada model lain.
  - warna aksen (yang areanya kecil, mis. aksen emas) mudah ikut melebur.

Pendekatan:
  1. sampel warna + k-means seperti biasa
  2. hitung proksi JUMLAH GANTI WARNA langsung dari geometri, tanpa perlu slice
     proksi: untuk setiap lapisan Z, berapa banyak potongan warna (komponen) yang melintasinya
  3. cari setelan terbaik di tangga (mode filter x ambang wilayah) dengan SYARAT
     setiap warna palet tetap punya porsi minimum -> warna aksen terlindungi
  4. menurut pilihan itu, slice SUNGGUHAN, dan bandingkan proksi vs hasil nyata

Ukuran keberhasilan: proksi harus mengurutkan setelan dengan benar (diuji pada 3 setelan).
"""
import importlib.util
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TPL = os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "data", "template-p2s.3mf")
GLB = os.path.join(HERE, "data", "tripo-kucing.glb")
FILS3 = ["GFSA00_11", "GFSA01_12", "GFSA00_11"]
LAYER = 0.2


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


g2p = load("g2p", os.path.join(os.path.dirname(HERE), "002-gltf-to-perfacet", "glb2perfacet.py"))
sm = load("sm", os.path.join(HERE, "segment_merge.py"))
s5 = g2p.load_s5()


def triangle_z(verts, tris):
    return [((verts[a][2] + verts[b][2] + verts[c][2]) / 3.0, (verts[a][2] + verts[b][2] + verts[c][2]) / 3.0)
            for a, b, c in tris]


def proxy_swaps(labels, adj, tz):
    """Perkiraan jumlah ganti warna tanpa slice.

    Setiap komponen warna punya rentang Z. Untuk tiap lapisan, hitung berapa komponen
    yang muncul; kelebihannya di atas 1 adalah ganti warna di lapisan itu."""
    n_layers = int(max(z for _, z in tz) / LAYER) + 2
    per_layer = [0] * n_layers
    for lab, comp in sm.components(labels, adj):
        zlo = min(tz[t][0] for t in comp)
        zhi = max(tz[t][1] for t in comp)
        i0 = max(0, int(zlo / LAYER))
        i1 = min(n_layers - 1, int(zhi / LAYER))
        for i in range(i0, i1 + 1):
            per_layer[i] += 1
    return sum(max(0, c - 1) for c in per_layer), per_layer


def protect_accents(labels, adj, raw, n_fil, floor_share):
    """Kalau ada warna yang porsinya jatuh di bawah floor_share, kembalikan wilayah
    mentahnya untuk warna itu (supaya aksen tidak hilang)."""
    labels = list(labels)
    n = len(labels)
    for g in range(n_fil):
        raw_idx = [i for i, r in enumerate(raw) if r == g]
        if not raw_idx:
            continue
        target = max(1, int(floor_share * n))
        cur = sum(1 for l in labels if l == g)
        if cur >= target:
            continue
        # kembalikan yang paling dekat: ambil wilayah mentah warna g yang terbesar,
        # pulihkan sampai porsinya cukup
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


def main():
    verts, uvs, tris, tex = g2p.extract_geometry(GLB)
    img = Image.open(io.BytesIO(tex)).convert("RGB")
    cols = g2p.sample_triangle_colors(img, uvs, tris)
    pal = [tuple(int(round(c)) for c in p) for p in
           g2p.kmeans(cols[:: max(1, len(cols) // 4000)], 3)]
    colors = ["#%02X%02X%02X" % p for p in pal]
    raw = g2p.assign(cols, pal)
    adj = sm.build_adjacency(verts, tris)
    tz = triangle_z(verts, tris)
    verts2, _ = g2p.scale_to(verts, uvs, tris, 80.0)

    share = Counter(raw)
    n = len(raw)
    print(f"model {len(tris)} segitiga · palet {colors}")
    print("  porsi warna mentah: " + ", ".join(f"{i+1}:{100*share[i]/n:.1f}%" for i in range(3)))
    print()

    print("mencari setelan terbaik (proksi, tanpa slice):")
    print(f"  {'filter':>6} {'min':>6} {'wilayah':>8} {'proksi ganti':>13} {'aksen aman':>11}")
    best = None
    for iters in (2, 4, 6, 8, 10):
        for minsize in (0, 150, 400, 800):
            lab = sm.drop_small_regions(sm.mode_filter(raw, adj, iters), adj, minsize) if minsize else \
                sm.mode_filter(raw, adj, iters)
            lab = protect_accents(lab, adj, raw, 3, 0.03)
            nc = len(sm.components(lab, adj))
            pr, _ = proxy_swaps(lab, adj, tz)
            ok = all(sum(1 for l in lab if l == g) >= max(1, int(0.03 * n)) for g in range(3))
            if ok and (best is None or pr < best[2]):
                best = (iters, minsize, pr, lab)
            print(f"  {iters:>6} {minsize:>6} {nc:>8} {pr:>13} {str(ok):>11}")
    print()
    it, ms, pr, lab = best
    print(f"pilihan: filter {it}x, ambang {ms} segitiga  (proksi {pr} ganti warna)")

    tri_fil = [x + 1 for x in lab]
    print()
    print("slice sunGGUHAN untuk pilihan ini:")
    r = build(os.path.join(DATA, "auto-m1.3mf"), verts2, tris, tri_fil, colors, None)
    if r.get("_err"):
        print("  GAGAL:", r["msg"][:200]); return
    nT = len(re.findall(r"^T[0-9]+$", r["gc"], re.M))
    print(f"  ganti warna terukur: {nT}  (proksi: {pr})")

    r0 = build(os.path.join(DATA, "auto-m0.3mf"), verts2, tris, tri_fil, colors, 0.0)
    w0 = r0["est"]["weight_g"]
    w1 = r["est"]["weight_g"]
    print()
    print("=== HASIL AKHIR (setelan otomatis) ===")
    print(f"  bahan tercetak   : {w0:.3f} g")
    print(f"  total dibutuhkan : {w1:.3f} g")
    print(f"  TERBUANG         : {w1-w0:.3f} g  = {100*(w1-w0)/w0:.1f}% dari bahan tercetak")
    print(f"  waktu            : {r['est']['time_seconds']/3600:.1f} jam")
    print(f"  bandingkan: manual (filter 6/min 600) = 375 ganti, 47,6 g, 10,6 jam")


if __name__ == "__main__":
    main()
