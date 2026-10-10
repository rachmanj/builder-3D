#!/usr/bin/env python3
"""Spike 001 tahap 2b: cari cara BENAR menugaskan filamen ke objek ke-2.

Menguji beberapa varian secara empiris, bukan menebak:
  A. 2 objek, extruder 1 & 1, 1 filamen          -> baseline struktur
  B. 2 objek, extruder 1 & 2, 2 filamen          -> (sudah gagal: 'right nozzle')
  C. B + filament_map [1,1]
  D. B + filament_map [0,0]
  E. 2 objek extruder 1 & 1, 2 filamen, map [1,2]
"""
import json
import os
import re
import urllib.request
import zipfile

BASE = "http://localhost:8070"
MACHINE = "GM049"      # Bambu Lab P2S 0.4 nozzle
PROCESS = "GP155"      # 0.20mm Standard @BBL P2S
FIL_A = "GFSA00_11"    # Bambu PLA Basic @BBL P2S
FIL_B = "GFSA01_12"    # Bambu PLA Matte @BBL P2S
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def http(method, path, body=None, headers=None, raw=False):
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        else:
            data = body
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            payload = r.read()
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode(errors="replace")[:400]}
    return payload if raw else json.loads(payload.decode())


def multipart(fields, files, boundary="----spike001c"):
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fname, content) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                f"filename=\"{fname}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def make_2obj_3mf(src, dst, ext_first=1, ext_second=2):
    with zipfile.ZipFile(src) as z:
        items = {n: z.read(n) for n in z.namelist()}
    model = items["3D/3dmodel.model"].decode()
    on_plate = re.search(r'<build>\s*<item objectid="(\d+)"', model).group(1)
    other = next(o for o in re.findall(r'<object id="(\d+)" type="model"', model) if o != on_plate)

    build_old = re.search(r"<build>.*?</build>", model, re.S).group(0)
    model = model.replace(build_old, build_old.replace(
        "</build>", f'  <item objectid="{other}" transform="1 0 0 0 1 0 0 0 1 45 0 0" printable="1"/>\n </build>'))
    items["3D/3dmodel.model"] = model.encode()

    ms = items["Metadata/model_settings.config"].decode()
    src_block = re.search(r'  <object id="' + on_plate + r'">.*?  </object>', ms, re.S).group(0)
    src_block = re.sub(r'(<metadata key="extruder" value=")\d+(")', rf'\g<1>{ext_first}\g<2>', src_block)
    new_block = src_block.replace(f'<object id="{on_plate}">', f'<object id="{other}">')
    new_block = re.sub(r'(<metadata key="extruder" value=")\d+(")', rf'\g<1>{ext_second}\g<2>', new_block)
    ms = ms.replace("\n  <assemble>", "\n" + new_block + "\n  <assemble>")
    items["Metadata/model_settings.config"] = ms.encode()

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in items.items():
            z.writestr(n, c)
    return on_plate, other


def upload(path):
    body, hdrs = multipart({"machine_id": MACHINE, "process_id": PROCESS},
                           {"file": ("v.3mf", open(path, "rb").read())})
    r = http("POST", "/3mf", body, hdrs)
    if "_http_error" in r:
        raise RuntimeError(f"upload gagal: {r}")
    return r["token"]


def attempt(label, fil_ids, filament_map=None, ext_first=1, ext_second=2, overrides=None):
    path = os.path.join(DATA, f"var-{label}.3mf")
    make_2obj_3mf(os.path.join(DATA, "template.3mf"), path, ext_first, ext_second)
    tok = upload(path)
    body = {"input_token": tok, "machine_id": MACHINE, "process_id": PROCESS,
            "filament_settings_ids": fil_ids, "auto_center": True}
    if filament_map is not None:
        body["filament_map"] = filament_map
    if overrides:
        body["process_overrides"] = overrides
    r = http("POST", "/slice/v2", body)
    if "_http_error" in r:
        msg = r["_body"]
        m = re.search(r'"message":"([^"]+)"', msg)
        print(f"  [{label}] GAGAL -> {m.group(1) if m else msg[:160]}")
        return None
    est = r.get("estimate", {})
    blob = http("GET", f"/3mf/{r['output_token']}", raw=True)
    open(os.path.join(DATA, f"slice-{label}.3mf"), "wb").write(blob)
    with zipfile.ZipFile(os.path.join(DATA, f"slice-{label}.3mf")) as z:
        si = z.read("Metadata/slice_info.config").decode()
    fils = re.findall(r'<filament id="(\d+)"[^>]*used_m="([\d.]+)" used_g="([\d.]+)"', si)
    plate_w = re.search(r'<metadata key="weight" value="([\d.]+)"', si)
    print(f"  [{label}] OK -> plate={plate_w.group(1) if plate_w else '?'}g | "
          f"per filamen: " + ", ".join(f"#{i}={g}g({mm}m)" for i, mm, g in fils))
    return {"label": label, "si": si, "est": est, "fils": fils}


if __name__ == "__main__":
    print("menguji varian penugasan filamen:")
    results = []
    results.append(attempt("A-1fil", [FIL_A], ext_first=1, ext_second=1))
    results.append(attempt("B-2fil", [FIL_A, FIL_B], ext_first=1, ext_second=2))
    results.append(attempt("C-map11", [FIL_A, FIL_B], filament_map=[1, 1], ext_first=1, ext_second=2))
    results.append(attempt("D-map00", [FIL_A, FIL_B], filament_map=[0, 0], ext_first=1, ext_second=2))
    results.append(attempt("E-map12", [FIL_A, FIL_B], filament_map=[1, 2], ext_first=1, ext_second=1))
    print()
    print("=== RINGKASAN ===")
    for r in results:
        if r:
            print(f"  BERHASIL: {r['label']} -> {r['fils']}")
        else:
            print("  gagal")
