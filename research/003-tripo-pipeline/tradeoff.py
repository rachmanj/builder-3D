#!/usr/bin/env python3
"""Spike 003 langkah 3 — kurva trade-off: kesetiaan warna vs filamen terbuang.

Perbaikan atas langkah sebelumnya:
  - JANGAN paksa flush_multiplier; pakai bawaan profil mesin (P2S = 0.3).
    Sebelumnya dipaksa 1.0 sehingga angka terbuang 3x lipat dari seharusnya.
  - ukur juga jumlah ganti warna PER LAPISAN, karena itu pemicu biayanya.

Pakai:  python3 tradeoff.py <iters> <minsize> <k>
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
FILS2 = ["GFSA00_11", "GFSA01_12"]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


g2p = load("g2p", os.path.join(os.path.dirname(HERE), "002-gltf-to-perfacet", "glb2perfacet.py"))
s5 = g2p.load_s5()
sm = load("sm", os.path.join(HERE, "segment_merge.py"))


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
    if mult is not None:                       # None = pakai bawaan profil (0.3)
        cfg["flush_multiplier"] = [str(mult)] * len(colors)
    items["Metadata/project_settings.config"] = json.dumps(cfg, indent=1).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in items.items():
            z.writestr(k, v)
    return g2p.slice_3mf(s5, path, "GM049", "GP155", FILS3[:len(colors)])


def per_layer_swaps(gc):
    layers = re.split(r";\s*LAYER_CHANGE", gc)
    per = [len(re.findall(r"^T[0-9]+$", b, re.M)) for b in layers]
    per = [n for n in per if n]
    return (max(per) if per else 0, len(per), dict(sorted(Counter(per).items())))


def main():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    minsize = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    k = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    verts, uvs, tris, tex = g2p.extract_geometry(GLB)
    img = Image.open(io.BytesIO(tex)).convert("RGB")
    cols = g2p.sample_triangle_colors(img, uvs, tris)
    pal = [tuple(int(round(c)) for c in p) for p in
           g2p.kmeans(cols[:: max(1, len(cols) // 4000)], k)]
    colors = ["#%02X%02X%02X" % p for p in pal]
    raw = g2p.assign(cols, pal)
    adj = sm.build_adjacency(verts, tris)

    c0 = len(sm.components(raw, adj))
    lab = sm.drop_small_regions(sm.mode_filter(raw, adj, iters), adj, minsize)
    c1 = len(sm.components(lab, adj))
    verts2, _ = g2p.scale_to(verts, uvs, tris, 80.0)
    tri_fil = [x + 1 for x in lab]

    print(f"### k={k} filter={iters}x min_wilayah={minsize} segitiga")
    print(f"    wilayah warna: {c0} -> {c1}")

    r = build(os.path.join(DATA, f"tr-m1.3mf"), verts2, tris, tri_fil, colors, None)
    if r.get("_err"): print("    slice-1 GAGAL:", r["msg"][:200]); return
    nT = len(re.findall(r"^T[0-9]+$", r["gc"], re.M))
    mx, nlay, dist = per_layer_swaps(r["gc"])
    w1 = r["est"]["weight_g"]
    print(f"    ganti warna total: {nT} · per lapisan maks {mx} · lapisan berwarna {nlay}")
    print(f"    total filamen    : {w1:.3f} g")

    r0 = build(os.path.join(DATA, f"tr-m0.3mf"), verts2, tris, tri_fil, colors, 0.0)
    if r0.get("_err"): print("    slice-2 GAGAL:", r0["msg"][:200]); return
    w0 = r0["est"]["weight_g"]
    print(f"    bahan tercetak   : {w0:.3f} g")
    print(f"    TERBUANG         : {w1-w0:.3f} g")
    print(f"    perkiraan waktu  : {r['est']['time_seconds']/3600:.1f} jam")


if __name__ == "__main__":
    main()
