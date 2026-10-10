#!/usr/bin/env python3
"""Spike 003 langkah 4 — apa nilai flush ditentukan WARNA filamen, bukan matriks di file?

Uji terkendali: geometri, pemecahan warna, dan flush_multiplier SAMA. Yang diubah hanya
warna filamen. Kalau jumlah terbuang ikut berubah -> nilai flush dihitung slicer dari warna.
"""
import importlib.util
import io
import json
import os
import re
import sys
import zipfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TPL = os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "data", "template-p2s.3mf")
GLB = os.path.join(HERE, "data", "tripo-kucing.glb")
FILS = ["GFSA00_11", "GFSA01_12", "GFSA00_11"]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


g2p = load("g2p", os.path.join(os.path.dirname(HERE), "002-gltf-to-perfacet", "glb2perfacet.py"))
sm = load("sm", os.path.join(HERE, "segment_merge.py"))
s5 = g2p.load_s5()


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
    cfg["flush_multiplier"] = [str(mult)] * len(colors)
    items["Metadata/project_settings.config"] = json.dumps(cfg, indent=1).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in items.items():
            z.writestr(k, v)
    return g2p.slice_3mf(s5, path, "GM049", "GP155", FILS[:len(colors)])


def measure(label, colors, verts2, tris, tri_fil):
    r = build(os.path.join(DATA, f"warna-{label}-m1.3mf"), verts2, tris, tri_fil, colors, 0.3)
    if r.get("_err"):
        print(f"  {label}: GAGAL {r['msg'][:150]}"); return None
    r0 = build(os.path.join(DATA, f"warna-{label}-m0.3mf"), verts2, tris, tri_fil, colors, 0.0)
    if r0.get("_err"):
        print(f"  {label}: GAGAL m0 {r0['msg'][:150]}"); return None
    nT = len(re.findall(r"^T[0-9]+$", r["gc"], re.M))
    nFlush = len(re.findall(r";\s*FLUSH_START", r["gc"]))
    w1, w0 = r["est"]["weight_g"], r0["est"]["weight_g"]
    purge = w1 - w0
    per = purge / nT * 1000 / 1.26 if nT else 0        # mm3 per ganti warna
    print(f"  {label:22} warna={','.join(colors)}")
    print(f"      T={nT} FLUSH={nFlush} tercetak={w0:7.2f} g total={w1:7.2f} g "
          f"terbuang={purge:6.2f} g -> {per:6.1f} mm3/ganti")
    return purge, per


def main():
    verts, uvs, tris, tex = g2p.extract_geometry(GLB)
    img = Image.open(io.BytesIO(tex)).convert("RGB")
    cols = g2p.sample_triangle_colors(img, uvs, tris)
    pal = [tuple(int(round(c)) for c in p) for p in
           g2p.kmeans(cols[:: max(1, len(cols) // 4000)], 3)]
    adj = sm.build_adjacency(verts, tris)
    lab = sm.drop_small_regions(sm.mode_filter(g2p.assign(cols, pal), adj, 6), adj, 600)
    verts2, _ = g2p.scale_to(verts, uvs, tris, 80.0)
    tri_fil = [x + 1 for x in lab]
    print("geometri, pemecahan warna, multiplier, mesin, proses: SEMUA SAMA.")
    print("yang diubah HANYA warna filamen:\n")

    measure("terang-rendah-kontras", ["#FFFFFF", "#EEEEEE", "#DDDDDD"], verts2, tris, tri_fil)
    measure("gelap-terang-kontras", ["#000000", "#FFFFFF", "#FF0000"], verts2, tris, tri_fil)
    measure("asli-biru-grey", ["#1E4895", "#7D8590", "#B5B4AF"], verts2, tris, tri_fil)


if __name__ == "__main__":
    main()
