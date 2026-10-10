#!/usr/bin/env python3
"""Spike 001: bisakah OrcaSlicer headless (image ghcr.io/leolobato/orcaslicer-headless)
memberi angka filamen NYATA (gram per filamen + terbuang saat ganti warna) untuk model 3D?

Tahap yang diuji:
  1. STL mentah -> /stl/import -> /stl/{draft}/3mf -> /slice/v2 -> baca slice_info.config
  2. 3MF 2 objek dengan 2 extruder berbeda -> /slice/v2 -> baca gram per warna + flush
"""
import json
import os
import struct
import urllib.request
import zipfile

BASE = "http://localhost:8070"
MACHINE = "GM049"          # Bambu Lab P2S 0.4 nozzle (1 nozzle, AMS 4 slot)
PROCESS = "GP155"          # 0.20mm Standard @BBL P2S
FIL_A = "GFSA00_11"        # Bambu PLA Basic @BBL P2S
FIL_B = "GFSA01_12"        # Bambu PLA Matte @BBL P2S
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def http(method, path, body=None, headers=None, raw=False):
    url = BASE + path
    data = None
    hdrs = headers or {}
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail[:1500]}") from None
    if raw:
        return payload
    return json.loads(payload.decode())


def multipart(fields, files):
    """Bangun body multipart/form-data tanpa dependensi luar."""
    boundary = "----spike001boundary"
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fname, content) in files.items():
        out += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
            f"filename=\"{fname}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
        ).encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def box_stl(x0, y0, z0, sx, sy, sz):
    """Balok kotak solid sebagai binary STL (tanpa library)."""
    x1, y1, z1 = x0 + sx, y0 + sy, z0 + sz
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [  # urutan titik luar (CCW dilihat dari luar)
        (0, 3, 2, 1),  # bawah
        (4, 5, 6, 7),  # atas
        (0, 1, 5, 4),  # depan (y0)
        (2, 3, 7, 6),  # belakang (y1)
        (1, 2, 6, 5),  # kanan (x1)
        (3, 0, 4, 7),  # kiri (x0)
    ]
    tris = []
    for a, b, c, d in quads:
        tris.append((v[a], v[b], v[c]))
        tris.append((v[a], v[c], v[d]))
    return tris


def write_stl(path, tris):
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80)
        fh.write(struct.pack("<I", len(tris)))
        for t in tris:
            fh.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for pt in t:
                fh.write(struct.pack("<3f", *pt))
            fh.write(struct.pack("<H", 0))


def write_ascii_stl(path, tris, name="box"):
    with open(path, "w") as fh:
        fh.write(f"solid {name}\n")
        for t in tris:
            fh.write("facet normal 0 0 0\n outer loop\n")
            for pt in t:
                fh.write(f"  vertex {pt[0]:.4f} {pt[1]:.4f} {pt[2]:.4f}\n")
            fh.write(" endloop\nendfacet\n")
        fh.write(f"endsolid {name}\n")


def make_model(path, ascii_fmt=False):
    """Model uji: balok 30x30x40 bertingkat (2 tumpuk) + tiang kecil 8x8x55."""
    tris = []
    tris += box_stl(0, 0, 0, 30, 30, 20)
    tris += box_stl(0, 0, 20, 22, 22, 20)
    tris += box_stl(31, 5, 0, 8, 8, 55)
    if ascii_fmt:
        write_ascii_stl(path, tris)
    else:
        write_stl(path, tris)
    return tris


def main():
    os.makedirs(DATA, exist_ok=True)
    stl = os.path.join(DATA, "model-uji.stl")
    tris = make_model(stl)
    print(f"[1] STL dibuat: {stl} ({len(tris)} triangle, {os.path.getsize(stl)} byte)")

    # --- import STL -> draft token
    body, hdrs = multipart(
        {"machine_id": MACHINE, "process_id": PROCESS, "auto_orient": "true", "arrange": "true"},
        {"file": ("model-uji.stl", open(stl, "rb").read())},
    )
    imp = http("POST", "/stl/import", body, hdrs)
    print("[2] /stl/import ->", json.dumps(imp)[:300])
    draft = imp.get("draft_token") or imp.get("token")

    # --- materialize draft -> 3mf token
    mat = http("POST", f"/stl/{draft}/3mf", {})
    print("[3] materialize ->", json.dumps(mat)[:300])
    token = mat.get("input_token") or mat.get("token") or mat.get("output_token")

    # --- inspect 3mf
    insp = http("GET", f"/3mf/{token}/inspect")
    print("[4] inspect ->", json.dumps(insp)[:600])

    # --- simpan 3mf sbg template
    with open(os.path.join(DATA, "template.3mf"), "wb") as fh:
        fh.write(http("GET", f"/3mf/{token}", raw=True))
    with zipfile.ZipFile(os.path.join(DATA, "template.3mf")) as z:
        print("[5] isi 3mf:", z.namelist())

    # --- slice 1 warna
    sl = http("POST", "/slice/v2", {
        "input_token": token, "machine_id": MACHINE, "process_id": PROCESS,
        "filament_settings_ids": [FIL_A], "auto_center": True,
    })
    print("[6] slice 1 warna ->", json.dumps(sl)[:400])
    out = sl.get("output_token") or sl.get("token")
    with open(os.path.join(DATA, "sliced-1warna.3mf"), "wb") as fh:
        fh.write(http("GET", f"/3mf/{out}", raw=True))

    with zipfile.ZipFile(os.path.join(DATA, "sliced-1warna.3mf")) as z:
        print("[7] isi hasil slice:", z.namelist())
        for n in z.namelist():
            if "slice_info" in n:
                print("---", n, "---")
                print(z.read(n).decode(errors="replace")[:3000])
        for n in z.namelist():
            if n.endswith(".gcode"):
                txt = z.read(n).decode(errors="replace")
                print(f"[8] gcode {n}: {len(txt)} char")
                # ringkasan dari header gcode
                for line in txt.splitlines()[:2000]:
                    if any(k in line.lower() for k in
                           ("total filament", "filament used", "model printing time",
                            "total estimated time", "flush", "filament_length")):
                        print("   ", line.strip())


if __name__ == "__main__":
    main()
