#!/usr/bin/env python3
"""Spike 002 — GLB bertekstur  ->  warna per-facet  ->  3MF  ->  slice OrcaSlicer.

Ini mata rantai yang belum terbukti: mengubah tekstur model (hasil AI nanti) menjadi
penugasan filamen per segitiga yang bisa di-slice.

Langkah:
  1. baca GLB (glTF 2.0 binary) tanpa dependensi luar
  2. ambil POSITION, TEXCOORD_0, indices, dan gambar baseColorTexture
  3. sampel tekstur di titik berat tiap segitiga -> warna RGB
  4. kelompokkan warna jadi K palet (k-means) -> filamen ke-N
  5. tulis 3MF dengan paint_color per segitiga
  6. slice di OrcaSlicer headless, baca gram per warna
Pemeriksaan independen: volume mesh per kelompok warna dibandingkan rasio gram dari slicer.
"""
import importlib.util
import io
import json
import math
import os
import re
import struct
import sys
import urllib.request
import zipfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


# ================== 1-2. pembaca GLB ==================
COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    with open(path, "rb") as f:
        blob = f.read()
    magic, ver, _ = struct.unpack("<4sII", blob[:12])
    assert magic == b"glTF", "bukan GLB"
    off, js, bin_ = 12, None, None
    while off < len(blob):
        clen, ctype = struct.unpack("<II", blob[off:off + 8])
        chunk = blob[off + 8:off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            bin_ = chunk
        off += 8 + clen + ((4 - clen % 4) % 4 if clen % 4 else 0)
    return js, bin_


def read_accessor(g, bin_, idx):
    a = g["accessors"][idx]
    fmt, size = COMP[a["componentType"]]
    n = NCOMP[a["type"]]
    out = []
    if "bufferView" not in a:
        return [tuple([0.0] * n) for _ in range(a["count"])] if a["count"] else []
    bv = g["bufferViews"][a["bufferView"]]
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride") or (size * n)
    for i in range(a["count"]):
        o = base + i * stride
        out.append(tuple(struct.unpack_from("<" + fmt * n, bin_, o)))
    return out


def extract_geometry(path):
    """Gabungkan semua primitive jadi satu mesh + UV."""
    g, bin_ = read_glb(path)
    verts, uvs, tris, tex_bytes = [], [], [], None
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4:
                continue
            pos = read_accessor(g, bin_, prim["attributes"]["POSITION"])
            base = len(verts)
            verts.extend(pos)
            if "TEXCOORD_0" in prim["attributes"]:
                uvs.extend(read_accessor(g, bin_, prim["attributes"]["TEXCOORD_0"]))
            else:
                uvs.extend([(0.0, 0.0)] * len(pos))
            if "indices" in prim:
                ix = [t[0] for t in read_accessor(g, bin_, prim["indices"])]
                for k in range(0, len(ix) - 2, 3):
                    tris.append((ix[k] + base, ix[k + 1] + base, ix[k + 2] + base))
            else:
                for k in range(base, len(verts) - 2, 3):
                    tris.append((k, k + 1, k + 2))
            if tex_bytes is None:
                mat = g.get("materials", [{}])[prim.get("material", 0)]
                pbr = mat.get("pbrMetallicRoughness", {})
                if "baseColorTexture" in pbr:
                    ti = pbr["baseColorTexture"]["index"]
                    src = g["textures"][ti].get("source")
                    if src is not None and "bufferView" in g["images"][src]:
                        bv = g["bufferViews"][g["images"][src]["bufferView"]]
                        o = bv.get("byteOffset", 0)
                        tex_bytes = bin_[o:o + bv["byteLength"]]
    return verts, uvs, tris, tex_bytes


# ================== 3-4. warna per segitiga ==================
def sample_triangle_colors(img, uvs, tris):
    """Warna tekstur di titik berat tiap segitiga."""
    W, H = img.size
    px = img.load()
    out = []
    for (a, b, c) in tris:
        u = (uvs[a][0] + uvs[b][0] + uvs[c][0]) / 3.0
        v = (uvs[a][1] + uvs[b][1] + uvs[c][1]) / 3.0
        # tekstur glTF: origin kiri-bawah, PIL kiri-atas -> v dibalik
        x = min(W - 1, max(0, int(u % 1.0 * (W - 1))))
        y = min(H - 1, max(0, int((1.0 - v % 1.0) * (H - 1))))
        r, gg, bb = px[x, y][:3]
        out.append((r, gg, bb))
    return out


def kmeans(samples, k, iters=12, seed=7):
    """k-means sederhana, deterministik."""
    pts = samples[:]
    # inisialisasi: pilih titik yang tersebar
    pts_sorted = sorted(pts, key=lambda p: (p[0], p[1], p[2]))
    cent = [pts_sorted[int((i + 0.5) * len(pts_sorted) / k)] for i in range(k)]
    for _ in range(iters):
        groups = [[] for _ in range(k)]
        for p in pts:
            j = min(range(k), key=lambda c: sum((p[d] - cent[c][d]) ** 2 for d in range(3)))
            groups[j].append(p)
        new = []
        for i, gp in enumerate(groups):
            if gp:
                new.append(tuple(sum(p[d] for p in gp) / len(gp) for d in range(3)))
            else:
                new.append(cent[i])
        if new == cent:
            break
        cent = new
    return cent


def assign(samples, palette):
    return [min(range(len(palette)),
                key=lambda c: sum((p[d] - palette[c][d]) ** 2 for d in range(3)))
            for p in samples]


# ================== ukuran & volume ==================
def scale_to(verts, uvs, tris, target_mm):
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
    w = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) or 1.0
    s = target_mm / w
    nv = tuple(((v[0] - min(xs)) * s, (v[1] - min(ys)) * s, (v[2] - min(zs)) * s) for v in verts)
    return nv, s


def volume_per_group(verts, tris, grp, k):
    vol = [0.0] * k
    for (a, b, c), gi in zip(tris, grp):
        A, B, C = verts[a], verts[b], verts[c]
        cr = (B[1] * C[2] - B[2] * C[1], B[2] * C[0] - B[0] * C[2], B[0] * C[1] - B[1] * C[0])
        vol[gi] += abs(A[0] * cr[0] + A[1] * cr[1] + A[2] * cr[2]) / 6.0
    return vol


# ================== 5. bangun 3MF ==================
def load_s5():
    spec = importlib.util.spec_from_file_location(
        "s5", os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "run_spike5.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def build_3mf(s5, tpl, out, verts, tris, tri_fil, n_fil, colors, flush, center=(128, 128), mult=1.0):
    """Sama seperti spike 5 tapi menerima mesh dari GLB (mesh sudah dalam mm)."""
    with zipfile.ZipFile(tpl) as z:
        items = {n: z.read(n) for n in z.namelist()}
    vx = "\n".join(f'     <vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in verts)
    tr = "\n".join(
        f'     <triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{s5.encode_paint(f)}"/>'
        for (a, b, c), f in zip(tris, tri_fil))
    items["3D/3dmodel.model"] = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">
 <metadata name="Application">BambuStudio-2.3.2</metadata>
 <metadata name="BambuStudio:3mfVersion">1</metadata>
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices>
{vx}
    </vertices>
    <triangles>
{tr}
    </triangles>
   </mesh>
  </object>
 </resources>
 <build>
  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 {center[0]} {center[1]} 0" printable="1"/>
 </build>
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
    cfg["filament_type"] = ["PLA"] * n_fil
    cfg["filament_map"] = ["1"] * n_fil
    cfg["flush_multiplier"] = [str(mult)] * n_fil
    n = n_fil
    mat = []
    for i in range(n):
        for j in range(n):
            mat.append("0" if i == j else "280")
    cfg["flush_volumes_matrix"] = mat
    items["Metadata/project_settings.config"] = json.dumps(cfg, indent=1).encode()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in items.items():
            z.writestr(k, v)
    return out


# ================== 6. slice ==================
def slice_3mf(s5, path, machine, process, fil_ids, overrides=None):
    b, h = s5.mp({"machine_id": machine, "process_id": process},
                 {"file": ("m.3mf", open(path, "rb").read())})
    up = s5.http("POST", "/3mf", b, h)
    if "_err" in up:
        return {"_err": True, "msg": up["_body"][:300]}
    req = {"input_token": up["token"], "machine_id": machine, "process_id": process,
           "filament_settings_ids": fil_ids, "auto_center": True}
    if overrides:
        req["process_overrides"] = overrides
    sl = s5.http("POST", "/slice/v2", req)
    if "_err" in sl:
        return {"_err": True, "msg": sl["_body"][:400]}
    blob = s5.http("GET", f"/3mf/{sl['output_token']}", raw=True)
    out = path.replace(".3mf", "-SLICED.3mf")
    open(out, "wb").write(blob)
    with zipfile.ZipFile(out) as z:
        si = z.read("Metadata/slice_info.config").decode()
        gcs = [n for n in z.namelist() if n.endswith(".gcode")]
        gc = z.read(gcs[0]).decode(errors="replace") if gcs else ""
    return {"est": sl.get("estimate", {}), "si": si, "gc": gc, "out": out}


def main():
    s5 = load_s5()
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, "Avocado.glb")
    n_fil = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    target_mm = float(sys.argv[3]) if len(sys.argv) > 3 else 80.0

    print(f"[1] baca GLB: {os.path.basename(source)}")
    verts, uvs, tris, tex = extract_geometry(source)
    print(f"    {len(verts)} vertex, {len(tris)} segitiga, tekstur {len(tex) if tex else 0} byte")

    img = Image.open(io.BytesIO(tex)).convert("RGB") if tex else None
    print(f"    ukuran tekstur: {img.size if img else '-'}")

    print(f"[2] sampel warna tiap segitiga -> k-means k={n_fil}")
    cols = sample_triangle_colors(img, uvs, tris)
    sub = cols[:: max(1, len(cols) // 4000)]
    pal = [tuple(int(round(c)) for c in p) for p in kmeans(sub, n_fil)]
    grp = assign(cols, pal)
    from collections import Counter
    print(f"    palet: {['#%02X%02X%02X' % p for p in pal]}")
    print(f"    sebaran segitiga per kelompok: {dict(Counter(grp))}")

    print(f"[3] skala ke {target_mm} mm + hitung volume per kelompok (pemeriksaan independen)")
    verts2, s = scale_to(verts, uvs, tris, target_mm)
    vol = volume_per_group(verts2, tris, grp, n_fil)
    tot = sum(vol) or 1.0
    print(f"    faktor skala {s:.2f} ; volume total {tot:.1f} mm3")
    for i, v in enumerate(vol):
        print(f"      kelompok {i+1}: {v:.1f} mm3 ({100*v/tot:.1f}%)")

    print("[4] bangun 3MF + slice (mesin 1 nozzle P2S)")
    tri_fil = [g + 1 for g in grp]
    colors = ["#%02X%02X%02X" % p for p in pal]
    path = os.path.join(DATA, "glb-perfacet.3mf")
    build_3mf(s5, os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "data", "template-p2s.3mf"),
              path, verts2, tris, tri_fil, n_fil, colors, None)

    FILS = ["GFSA00_11", "GFSA01_12", "GFSA00_11"][:n_fil]
    tpl = os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "data", "template-p2s.3mf")

    # --- slice ke-1: seperti pemakaian normal (multiplier 1)
    build_3mf(s5, tpl, path, verts2, tris, tri_fil, n_fil, colors, None, mult=1.0)
    r = slice_3mf(s5, path, "GM049", "GP155", FILS)
    if r.get("_err"):
        print("    GAGAL ->", r["msg"]); return
    est = r["est"]
    print(f"    total={est.get('weight_g'):.3f} g  model={est.get('model_weight_g'):.3f} g  "
          f"terbuang={est.get('weight_g')-est.get('model_weight_g'):.3f} g  waktu={est.get('time_seconds'):.0f}s")
    gram = []
    for line in r["si"].splitlines():
        m = re.search(r'<filament id="(\d+)"[^>]*color="(#[0-9A-Fa-f]+)"[^>]*used_g="([\d.]+)"', line)
        if m:
            gram.append((int(m.group(1)), m.group(2), float(m.group(3))))
            print("      ", line.strip())
    print(f"    ganti tool di gcode: {len(re.findall(r'^T[0-9]+$', r['gc'], re.M))}")

    print()
    print()
    print("=== slice ke-2: flush_multiplier = 0 (tanpa ganti-warna boros) -> bahan tercetak ===")
    path0 = os.path.join(DATA, "glb-perfacet-m0.3mf")
    build_3mf(s5, tpl, path0, verts2, tris, tri_fil, n_fil, colors, None, mult=0.0)
    r0 = slice_3mf(s5, path0, "GM049", "GP155", FILS)
    if r0.get("_err"):
        print("    slice ke-2 GAGAL ->", r0["msg"]); return
    w1, w0 = est["weight_g"], r0["est"]["weight_g"]
    print()
    print("=== ANGKA YANG BISA DIPERCAYA ===")
    print(f"  bahan tercetak          = {w0:8.3f} g   (weight_g pada multiplier 0)")
    print(f"  total filamen dibutuhkan= {w1:8.3f} g   (weight_g pada multiplier 1)")
    print(f"  filamen TERBUANG        = {w1 - w0:8.3f} g   (selisih keduanya)")
    print("  per warna: pakai used_g di slice_info.config (jumlahnya = total)")
    print("  CATATAN: weight_g - model_weight_g BUKAN angka terbuang;")
    print(f"           di sini hanya {(w1 - est.get('model_weight_g', 0)):.3f} g, padahal terbuang {w1 - w0:.3f} g.")


if __name__ == "__main__":
    main()
