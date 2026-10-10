#!/usr/bin/env python3
"""Spike 005 — TARGET UTAMA: mesh satu objek dengan warna PER-FACET -> 3MF -> slice
-> gram per warna + jumlah ganti warna (purge).

Format paint_color (dari spesifikasi komunitas Bambu/Orca, TriangleSelector):
  bitstream dibaca LSB-first, string hex-nya dibalik (karakter terakhir = 4 bit pertama)
  record   := splitSides(2 bit) body
  body     := leafState                        bila splitSides == 0
  leafState:= state(2 bit)                     bila state < 3
            | 0b11 lalu ext(4 bit)*            state = 3 + jumlah(ext), 0xF = +15 & lanjut
  state 0 = tidak dicat (warisi extruder objek), state N >= 1 = filamen ke-N (1-based)
"""
import json
import math
import os
import re
import urllib.request
import zipfile

BASE = "http://localhost:8070"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ---------- encoder paint_color ----------
def encode_paint(state: int) -> str:
    """state 0 = unpainted, >=1 = filamen ke-N."""
    if state == 0:
        return "0"
    if state <= 2:
        nibbles = [state * 4]
    else:
        ext = state - 3
        nibbles = [0xC]
        while ext >= 15:
            nibbles.append(0xF)
            ext -= 15
        nibbles.append(ext)
    return "".join(f"{n:X}" for n in nibbles)[::-1]


def self_test_encoder():
    expect = {1: "4", 2: "8", 3: "0C", 4: "1C"}
    for st, want in expect.items():
        got = encode_paint(st)
        assert got == want, f"state {st}: dapat {got}, harusnya {want}"
    print("    encoder paint_color lulus uji:", expect)


# ---------- mesh: prisma 20 sisi, dinding berpita selang-seling ----------
def build_mesh(radius=15.0, bands=20, band_h=2.0, sides=20):
    """Pita horizontal bergantian filamen 1 / 2 -> banyak ganti warna."""
    verts, tris, tri_fil = [], [], []
    idx = {}

    def V(x, y, z):
        key = (round(x, 5), round(y, 5), round(z, 5))
        if key not in idx:
            idx[key] = len(verts)
            verts.append((x, y, z))
        return idx[key]

    # dinding: tiap pita = 1 quad = 2 segitiga
    for b in range(bands):
        z0, z1 = b * band_h, (b + 1) * band_h
        fil = 1 if b % 2 == 0 else 2
        for s in range(sides):
            a0 = 2 * math.pi * s / sides
            a1 = 2 * math.pi * (s + 1) / sides
            x0, y0 = radius * math.cos(a0), radius * math.sin(a0)
            x1, y1 = radius * math.cos(a1), radius * math.sin(a1)
            v00, v10 = V(x0, y0, z0), V(x1, y1, z0)
            v11, v01 = V(x1, y1, z1), V(x0, y0, z1)
            tris += [(v00, v10, v11), (v00, v11, v01)]
            tri_fil += [fil, fil]

    # tutup bawah & atas (filamen 1)
    zb, zt = 0.0, bands * band_h
    cb, ct = V(0, 0, zb), V(0, 0, zt)
    for s in range(sides):
        a0 = 2 * math.pi * s / sides
        a1 = 2 * math.pi * (s + 1) / sides
        x0, y0 = radius * math.cos(a0), radius * math.sin(a0)
        x1, y1 = radius * math.cos(a1), radius * math.sin(a1)
        w0, w1 = V(x0, y0, zb), V(x1, y1, zb)
        tris.append((cb, w1, w0))
        tri_fil.append(1)
        w2, w3 = V(x0, y0, zt), V(x1, y1, zt)
        tris.append((ct, w2, w3))
        tri_fil.append(1)
    return verts, tris, tri_fil


# ---------- 3MF ----------
def build_3mf(tpl_path, out_path, verts, tris, tri_fil, n_fil, colors, flush_matrix):
    with zipfile.ZipFile(tpl_path) as z:
        items = {n: z.read(n) for n in z.namelist()}

    # 1) model: satu objek, triangle dengan paint_color
    vx = "\n".join(f'     <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in verts)
    tr = "\n".join(
        (f'     <triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{encode_paint(f)}"/>'
         if f else f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>')
        for (a, b, c), f in zip(tris, tri_fil))
    model = f'''<?xml version="1.0" encoding="UTF-8"?>
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
  <item objectid="1" transform="1 0 0 0 1 0 0 0 1 128 128 0" printable="1"/>
 </build>
</model>
'''
    items["3D/3dmodel.model"] = model.encode()

    # 2) model_settings: satu objek, extruder default 1
    items["Metadata/model_settings.config"] = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="1">
    <metadata key="name" value="model-berwarna"/>
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
      <mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>
    </part>
  </object>
  <assemble>
  </assemble>
</config>
'''.encode()

    # 3) project_settings: selaraskan panjang semua vektor + matriks flush N x N
    cfg = json.loads(items["Metadata/project_settings.config"].decode())
    for key, val in (("filament_colour", colors),
                     ("filament_type", ["PLA"] * n_fil),
                     ("filament_map", ["1"] * n_fil),
                     ("flush_multiplier", ["1"] * n_fil)):
        cfg[key] = val
    cfg["flush_volumes_matrix"] = flush_matrix
    items["Metadata/project_settings.config"] = json.dumps(cfg, indent=1).encode()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in items.items():
            z.writestr(n, c)
    return out_path


# ---------- HTTP ----------
def http(method, path, body=None, headers=None, raw=False):
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode(); hdrs["Content-Type"] = "application/json"
        else:
            data = body
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            p = r.read()
    except urllib.error.HTTPError as e:
        return {"_err": e.code, "_body": e.read().decode(errors="replace")[:600]}
    return p if raw else json.loads(p.decode())


def mp(fields, files, boundary="----spk5"):
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fn, c) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + c + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


if __name__ == "__main__":
    self_test_encoder()

    verts, tris, tri_fil = build_mesh()
    from collections import Counter
    print(f"    mesh: {len(verts)} vertex, {len(tris)} segitiga, sebaran filamen={dict(Counter(tri_fil))}")

    path = os.path.join(DATA, "buatan-2warna.3mf")
    flush = ["0", "280", "280", "0"]           # matriks 2x2
    build_3mf(os.path.join(DATA, "template-h2dp.3mf"), path, verts, tris, tri_fil, 2,
              ["#FF0000", "#0000FF"], flush)
    print(f"    3MF dibuat: {path} ({os.path.getsize(path)} byte)")

    # --- uji 1: mesin 2 nozzle (H2D Pro)
    MACHINE, PROCESS = "GM051", "GP130"
    FILS = ["GFSA00_17", "GFSA01_17"]
    b, h = mp({"machine_id": MACHINE, "process_id": PROCESS}, {"file": ("m.3mf", open(path, "rb").read())})
    up = http("POST", "/3mf", b, h)
    if "_err" in up:
        print("upload gagal:", up["_body"][:300]); raise SystemExit
    tok = up["token"]
    insp = http("GET", f"/3mf/{tok}/inspect")
    print("    inspect plate:", json.dumps(insp.get("plates"))[:300])

    for lbl, ov in (("tanpa-override", None), ("printable-3", {"filament_printable": "3,3"})):
        req = {"input_token": tok, "machine_id": MACHINE, "process_id": PROCESS,
               "filament_settings_ids": FILS, "auto_center": True}
        if ov: req["process_overrides"] = ov
        sl = http("POST", "/slice/v2", req)
        if "_err" in sl:
            print(f"  [{lbl}] GAGAL -> {re.search(r'\"(?:message|detail)\":\"?([^\"]{0,160})', sl['_body']).group(1)}")
            continue
        est = sl.get("estimate", {})
        blob = http("GET", f"/3mf/{sl['output_token']}", raw=True)
        f = os.path.join(DATA, f"slice-buatan-{lbl}.3mf"); open(f, "wb").write(blob)
        with zipfile.ZipFile(f) as z:
            si = z.read("Metadata/slice_info.config").decode()
            gcs = [n for n in z.namelist() if n.endswith(".gcode")]
            gc = z.read(gcs[0]).decode(errors="replace") if gcs else ""
        print(f"  [{lbl}] BERHASIL")
        print(f"      weight_g={est.get('weight_g')} time_s={est.get('time_seconds')}")
        for line in si.splitlines():
            if "<filament " in line or 'key="weight"' in line or 'key="prediction"' in line:
                print("      ", line.strip())
        print(f"      ganti tool di gcode: {len(re.findall(r'^T[0-9]+$', gc, re.M))} | "
              f"flush_length: {len(re.findall('flush_length', gc))} | lapisan: "
              f"{re.search(r'; total layer number: (\\d+)', gc).group(1) if re.search(r'; total layer number: (\\d+)', gc) else '?'}")
