#!/usr/bin/env python3
"""Spike 004: bisakah slicer mengukur PURGE pada project multi-warna asli?

Pakai 3MF asli buatan OrcaSlicer (auto_pa_line_dual.3mf, 8 filamen, mesin H2D).
Kalau ini jalan, terbukti angka 'terbuang saat ganti warna' bisa kita ukur.
"""
import json
import os
import re
import urllib.request
import zipfile

BASE = "http://localhost:8070"
MACHINE, PROCESS = "GM051", "GP130"          # H2D Pro 0.4 (2 nozzle), 0.20mm Standard
FIL_A, FIL_B = "GFSA00_17", "GFSA01_17"      # Bambu PLA Basic / PLA Matte @BBL H2DP
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


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
        return {"_err": e.code, "_body": e.read().decode(errors="replace")[:700]}
    return p if raw else json.loads(p.decode())


def mp(fields, files, boundary="----spk4"):
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fn, c) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + c + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def upload(path, name="x.3mf"):
    b, h = mp({"machine_id": MACHINE, "process_id": PROCESS}, {"file": (name, open(path, "rb").read())})
    r = http("POST", "/3mf", b, h)
    if "_err" in r:
        raise RuntimeError(f"upload gagal: {r['_body'][:300]}")
    return r["token"]


def show_result(sl, label):
    est = sl.get("estimate", {})
    print(f"  [{label}] estimate:")
    for k in ("weight_g", "filament_used_m", "model_weight_g", "time_seconds", "prepare_seconds"):
        print(f"      {k} = {est.get(k)}")
    blob = http("GET", f"/3mf/{sl['output_token']}", raw=True)
    f = os.path.join(DATA, f"slice-{label}.3mf"); open(f, "wb").write(blob)
    with zipfile.ZipFile(f) as z:
        names = z.namelist()
        gcs = [n for n in names if n.endswith(".gcode")]
        si = z.read("Metadata/slice_info.config").decode()
        gc = z.read(gcs[0]).decode(errors="replace") if gcs else ""
    print(f"  [{label}] slice_info.config:")
    for line in si.splitlines():
        if any(k in line for k in ("filament ", "weight", "prediction", "filament_maps")):
            print("      ", line.strip())
    for pat in (r"^; total filament weight \[g\] = (.*)$", r"^; total filament length \[mm\] = (.*)$",
                r"^; total filament cost = (.*)$", r"^; model printing time: (.*)$"):
        for m in re.findall(pat, gc, re.M)[:2]:
            print(f"      gcode: {pat.split('= ')[-1][:40]} -> {str(m)[:120]}")
    print(f"  [{label}] jumlah perubahan tool (baris ^T<n>) di gcode: {len(re.findall(r'^T\d+$', gc, re.M))}")
    return est


if __name__ == "__main__":
    src = os.path.join(DATA, "contoh-dual.3mf")

    print("[1] upload 3MF multi-warna asli OrcaSlicer")
    tok = upload(src, "dual.3mf")
    insp = http("GET", f"/3mf/{tok}/inspect")
    print("    plate  :", json.dumps(insp.get("plates"))[:400])
    print("    filamen:", json.dumps(insp.get("filaments"))[:400])
    print("    warnings:", json.dumps(insp.get("warnings"))[:200])

    print("[2] slice 2 filamen (H2D Pro, 2 nozzle)")
    sl = http("POST", "/slice/v2", {"input_token": tok, "machine_id": MACHINE,
                                    "process_id": PROCESS,
                                    "filament_settings_ids": [FIL_A, FIL_B], "auto_center": True})
    if "_err" in sl:
        print("    GAGAL ->", sl["_body"][:500])
    else:
        show_result(sl, "dual-2fil")

    print("[3] slice apa adanya (tanpa ganti filamen)")
    sl2 = http("POST", "/slice/v2", {"input_token": tok, "machine_id": MACHINE,
                                     "process_id": PROCESS, "auto_center": True})
    if "_err" in sl2:
        print("    GAGAL ->", sl2["_body"][:300])
    else:
        show_result(sl2, "dual-asli")
