#!/usr/bin/env python3
"""Spike 003 langkah 2 — perbaiki pemecahan warna: mode filter + buang pulau kecil.

Masalah yang diperbaiki: menugaskan warna per segitiga mentah menghasilkan pola
salt-and-pepper -> ratusan ganti warna -> filamen terbuang berlipat.

Yang dilakukan:
  1. sampel warna tekstur per segitiga (sama seperti sebelumnya)
  2. mode filter di atas graf ketetanggaan segitiga (haluskan batas warna)
  3. buang wilayah kecil: komponen di bawah ambang dikembalikan ke tetangga dominan
  4. tulis 3MF, slice, ukur jumlah ganti warna + bahan tercetak + terbuang

Ukuran keberhasilan: jumlah ganti warna (dari G-code) dan gram terbuang.
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
SPIKE2 = os.path.join(os.path.dirname(HERE), "002-gltf-to-perfacet")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


g2p = load("g2p", os.path.join(SPIKE2, "glb2perfacet.py"))
s5 = g2p.load_s5()
TPL = os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "data", "template-p2s.3mf")
FILS = ["GFSA00_11", "GFSA01_12", "GFSA00_11"]


# ---------- graf ketetanggaan segitiga ----------
def build_adjacency(verts, tris):
    """Segitiga bersebelahan kalau berbagi rusuk. Vertex digabung berdasarkan posisi
    (GLB menduplikasi vertex di batas UV)."""
    key = {}
    canon = []
    for v in verts:
        k = (round(v[0], 5), round(v[1], 5), round(v[2], 5))
        if k not in key:
            key[k] = len(key)
        canon.append(key[k])
    edge = defaultdict(list)
    for ti, (a, b, c) in enumerate(tris):
        for u, w in ((a, b), (b, c), (c, a)):
            ku, kw = canon[u], canon[w]
            e = (min(ku, kw), max(ku, kw))
            edge[e].append(ti)
    adj = [set() for _ in tris]
    for e, ts in edge.items():
        if len(ts) < 2:
            continue
        for i in ts:
            for j in ts:
                if i != j:
                    adj[i].add(j)
    return [sorted(a) for a in adj]


# ---------- haluskan & bersihkan ----------
def mode_filter(labels, adj, iterations):
    for _ in range(iterations):
        new = list(labels)
        for t, nbrs in enumerate(adj):
            if not nbrs:
                continue
            cnt = Counter(labels[n] for n in nbrs)
            cnt[labels[t]] += 1          # bobot sendiri sama dengan satu tetangga
            best = max(cnt.items(), key=lambda kv: (kv[1], -kv[0]))[0]
            new[t] = best
        labels = new
    return labels


def components(labels, adj):
    seen = [False] * len(labels)
    out = []
    for i in range(len(labels)):
        if seen[i]:
            continue
        lab = labels[i]
        stack, comp = [i], []
        seen[i] = True
        while stack:
            t = stack.pop()
            comp.append(t)
            for n in adj[t]:
                if not seen[n] and labels[n] == lab:
                    seen[n] = True
                    stack.append(n)
        out.append((lab, comp))
    return out


def drop_small_regions(labels, adj, min_size, rounds=3):
    """Wilayah kecil dikembalikan ke warna mayoritas di sekelilingnya."""
    labels = list(labels)
    for _ in range(rounds):
        comps = components(labels, adj)
        small = [c for lab, c in comps if len(c) < min_size]
        if not small:
            break
        changed = 0
        for comp in small:
            if len(comp) == 0:
                continue
            nbr_count = Counter()
            inside = set(comp)
            for t in comp:
                for n in adj[t]:
                    if n not in inside:
                        nbr_count[labels[n]] += 1
            if not nbr_count:
                continue
            newlab = nbr_count.most_common(1)[0][0]
            if newlab != labels[comp[0]]:
                for t in comp:
                    labels[t] = newlab
                changed += 1
        if not changed:
            break
    return labels


# ---------- tulis 3MF + slice ----------
def build_and_slice(verts2, tris, tri_fil, colors, mult, out_path):
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
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in items.items():
            z.writestr(k, v)
    r = g2p.slice_3mf(s5, out_path, "GM049", "GP155", FILS[:len(colors)])
    return r


def main():
    glb = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(HERE), "003-tripo-pipeline", "data", "tripo-kucing.glb")
    n_fil = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    target = float(sys.argv[3]) if len(sys.argv) > 3 else 80.0
    iters = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    minsize = int(sys.argv[5]) if len(sys.argv) > 5 else 150

    print(f"[1] {os.path.basename(glb)} · {n_fil} warna · target {target} mm · "
          f"mode_filter={iters} · min_wilayah={minsize}")
    verts, uvs, tris, tex = g2p.extract_geometry(glb)
    img = Image.open(io.BytesIO(tex)).convert("RGB")
    cols = g2p.sample_triangle_colors(img, uvs, tris)
    pal = [tuple(int(round(c)) for c in p) for p in
           g2p.kmeans(cols[:: max(1, len(cols) // 4000)], n_fil)]
    colors = ["#%02X%02X%02X" % p for p in pal]
    raw = g2p.assign(cols, pal)
    print(f"    {len(tris)} segitiga · palet {colors}")

    print("[2] graf ketetanggaan")
    adj = build_adjacency(verts, tris)
    nbr = sum(len(a) for a in adj) / max(1, len(adj))
    print(f"    rata-rata tetangga/segitiga: {nbr:.2f}")

    comp_before = len(components(raw, adj))
    print(f"[3] sebelum dibersihkan: {comp_before} wilayah warna")

    sm = mode_filter(raw, adj, iters)
    after_filter = len(components(sm, adj))
    print(f"    setelah mode filter {iters}x: {after_filter} wilayah")

    fin = drop_small_regions(sm, adj, minsize)
    after_drop = len(components(fin, adj))
    print(f"    setelah buang wilayah < {minsize} segitiga: {after_drop} wilayah")

    verts2, _ = g2p.scale_to(verts, uvs, tris, target)

    print()
    print("[4] slice: hasil akhir (mode filter + buang pulau kecil)")
    tri_fil = [x + 1 for x in fin]
    r = build_and_slice(verts2, tris, tri_fil, colors, 1.0, os.path.join(DATA, "bersih-m1.3mf"))
    if r.get("_err"):
        print("    GAGAL ->", r["msg"][:300]); return
    nT = len(re.findall(r'^T[0-9]+$', r["gc"], re.M))
    w1 = r["est"]["weight_g"]
    print(f"    ganti warna: {nT} (baseline mentah: 766)")
    print(f"    total filamen: {w1:.3f} g")

    print("[5] slice pembanding: flush_multiplier 0 -> bahan tercetak")
    r0 = build_and_slice(verts2, tris, tri_fil, colors, 0.0, os.path.join(DATA, "bersih-m0.3mf"))
    if r0.get("_err"):
        print("    GAGAL ->", r0["msg"][:300]); return
    w0 = r0["est"]["weight_g"]
    print()
    print("=== HASIL AKHIR ===")
    print(f"  wilayah warna    : {comp_before} -> {after_drop}  (turun {100*(1-after_drop/comp_before):.0f}%)")
    print(f"  ganti warna      : 766 -> {nT}  (turun {100*(1-nT/766):.0f}%)")
    print(f"  bahan tercetak   : {w0:.3f} g")
    print(f"  total dibutuhkan : {w1:.3f} g")
    print(f"  TERBUANG         : {w1-w0:.3f} g   (baseline mentah: 273,135 g)")


if __name__ == "__main__":
    main()
