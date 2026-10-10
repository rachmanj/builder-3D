#!/usr/bin/env python3
"""Spike 001 tahap 2: plate 2 warna -> apakah slicer mengeluarkan gram PER WARNA
+ gram yang TERBUANG saat ganti warna (flush/purge)?

Caranya: ambil template.3mf hasil tahap 1, taruh objek kedua di plate,
kasih extruder 2 lewat Metadata/model_settings.config, lalu slice.
"""
import json
import os
import re
import shutil
import urllib.request
import zipfile

BASE = "http://localhost:8070"
MACHINE = "GM049"      # Bambu Lab P2S 0.4 nozzle (1 nozzle, AMS 4 slot)
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
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read().decode(errors='replace')[:1200]}") from None
    return payload if raw else json.loads(payload.decode())


def multipart(fields, files, boundary="----spike001b"):
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fname, content) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                f"filename=\"{fname}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def build_two_color(src, dst):
    """Tambah objek kedua ke plate + set extruder 2."""
    with zipfile.ZipFile(src) as z:
        items = {n: z.read(n) for n in z.namelist()}

    model = items["3D/3dmodel.model"].decode()

    # objek yang sudah ada di plate
    m = re.search(r'<build>\s*<item objectid="(\d+)"[^>]*/>', model)
    on_plate = m.group(1)
    # objek lain yang ada di resources tapi belum di plate
    all_objs = re.findall(r'<object id="(\d+)" type="model"', model)
    other = next(o for o in all_objs if o != on_plate)
    print(f"    objek di plate: {on_plate} | objek ke-2 dijadikan pasangan: {other}")

    # tambah item ke-2 di build, geser +45mm di X
    build_old = re.search(r'<build>.*?</build>', model, re.S).group(0)
    build_new = build_old.replace(
        "</build>",
        f'  <item objectid="{other}" transform="1 0 0 0 1 0 0 0 1 45 0 0" printable="1"/>\n </build>',
    )
    model = model.replace(build_old, build_new)
    items["3D/3dmodel.model"] = model.encode()

    # model_settings.config: objek ke-2 dapat extruder 2
    ms = items["Metadata/model_settings.config"].decode()
    blocks = re.findall(r'  <object id="(\d+)">.*?  </object>', ms, re.S)
    src_block = re.search(r'  <object id="' + on_plate + r'">.*?  </object>', ms, re.S).group(0)
    new_block = src_block.replace(f'<object id="{on_plate}">', f'<object id="{other}">')
    new_block = re.sub(r'(<metadata key="extruder" value=")\d+(")', r'\g<1>2\g<2>', new_block)
    new_block = new_block.replace('value="model-uji.stl"', f'value="pasangan-{other}"')
    ms = ms.replace("\n  <assemble>", "\n" + new_block + "\n  <assemble>")
    items["Metadata/model_settings.config"] = ms.encode()

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in items.items():
            z.writestr(n, c)
    return other


def slice_and_report(token, fil_ids, label, overrides=None):
    body = {
        "input_token": token, "machine_id": MACHINE, "process_id": PROCESS,
        "filament_settings_ids": fil_ids, "auto_center": True,
    }
    if overrides:
        body["process_overrides"] = overrides
    sl = http("POST", "/slice/v2", body)
    est = sl.get("estimate") or {}
    print(f"    [{label}] estimate: weight_g={est.get('weight_g')} "
          f"filament_used_m={est.get('filament_used_m')} time_s={est.get('time_seconds')}")
    out = sl["output_token"]
    blob = http("GET", f"/3mf/{out}", raw=True)
    path = os.path.join(DATA, f"sliced-{label}.3mf")
    open(path, "wb").write(blob)
    with zipfile.ZipFile(path) as z:
        si = z.read("Metadata/slice_info.config").decode()
    print(f"    [{label}] slice_info.config:")
    for line in si.splitlines():
        if any(k in line for k in ("filament ", "weight", "prediction", "flush", "filament_maps")):
            print("       ", line.strip())
    return est, si, path


def main():
    src = os.path.join(DATA, "template.3mf")
    dst = os.path.join(DATA, "dua-warna.3mf")
    print("[1] membuat 3MF 2 warna")
    build_two_color(src, dst)

    print("[2] upload 3MF ke slicer")
    body, hdrs = multipart({"machine_id": MACHINE, "process_id": PROCESS},
                           {"file": ("dua-warna.3mf", open(dst, "rb").read())})
    up = http("POST", "/3mf", body, hdrs)
    print("    upload ->", json.dumps(up)[:250])
    token = up.get("token") or up.get("input_token")

    insp = http("GET", f"/3mf/{token}/inspect")
    print("[3] inspect plate:", json.dumps(insp.get("plates"))[:400])
    print("    filaments:", json.dumps(insp.get("filaments"))[:300])

    print("[4] slice 2 warna (auto flush matrix)")
    est2, si2, _ = slice_and_report(token, [FIL_A, FIL_B], "2warna")

    print("[5] slice 2 warna + flush_multiplier dinaikkan ke 1.0")
    est3, si3, _ = slice_and_report(token, [FIL_A, FIL_B], "2warna-flush1", {"flush_multiplier": "1.0"})

    print()
    print("=== KESIMPULAN TAHAP 2 ===")
    for lbl, si in (("auto (0.3)", si2), ("multiplier 1.0", si3)):
        fils = re.findall(r'<filament id="(\d+)"[^>]*used_m="([\d.]+)" used_g="([\d.]+)"', si)
        print(f"  {lbl}: " + " | ".join(f"filamen#{i} {g}g" for i, _, g in fils))


if __name__ == "__main__":
    main()
