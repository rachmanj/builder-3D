#!/usr/bin/env python3
"""Spike 001 tahap 2c: matikan 'Auto For Flush' (bikin pemetaan keliru ke nozzle kanan),
pakai filament_map_mode = Manual. Uji beberapa kombinasi."""
import json
import os
import re
import urllib.request
import zipfile

BASE = "http://localhost:8070"
MACHINE, PROCESS = "GM049", "GP155"
FIL_A, FIL_B = "GFSA00_11", "GFSA01_12"
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
        return {"_err": e.code, "_body": e.read().decode(errors="replace")[:500]}
    return p if raw else json.loads(p.decode())


def mp(fields, files, boundary="----spk2c"):
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fn, c) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + c + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def make(path, ext2=2):
    with zipfile.ZipFile(os.path.join(DATA, "template.3mf")) as z:
        items = {n: z.read(n) for n in z.namelist()}
    model = items["3D/3dmodel.model"].decode()
    on_plate = re.search(r'<build>\s*<item objectid="(\d+)"', model).group(1)
    other = next(o for o in re.findall(r'<object id="(\d+)" type="model"', model) if o != on_plate)
    b = re.search(r"<build>.*?</build>", model, re.S).group(0)
    model = model.replace(b, b.replace("</build>",
        f'  <item objectid="{other}" transform="1 0 0 0 1 0 0 0 1 45 0 0" printable="1"/>\n </build>'))
    items["3D/3dmodel.model"] = model.encode()
    ms = items["Metadata/model_settings.config"].decode()
    blk = re.search(r'  <object id="' + on_plate + r'">.*?  </object>', ms, re.S).group(0)
    nb = blk.replace(f'<object id="{on_plate}">', f'<object id="{other}">')
    nb = re.sub(r'(<metadata key="extruder" value=")\d+(")', rf'\g<1>{ext2}\g<2>', nb)
    ms = ms.replace("\n  <assemble>", "\n" + nb + "\n  <assemble>")
    items["Metadata/model_settings.config"] = ms.encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in items.items():
            z.writestr(n, c)


def run(label, fil_ids, overrides=None, filament_map=None, ext2=2):
    p = os.path.join(DATA, f"v2-{label}.3mf")
    make(p, ext2)
    body_b, hdrs = mp({"machine_id": MACHINE, "process_id": PROCESS},
                      {"file": ("v.3mf", open(p, "rb").read())})
    up = http("POST", "/3mf", body_b, hdrs)
    if "_err" in up:
        print(f"  [{label}] upload gagal {up['_body'][:150]}"); return None
    req = {"input_token": up["token"], "machine_id": MACHINE, "process_id": PROCESS,
           "filament_settings_ids": fil_ids, "auto_center": True}
    if overrides: req["process_overrides"] = overrides
    if filament_map is not None: req["filament_map"] = filament_map
    r = http("POST", "/slice/v2", req)
    if "_err" in r:
        m = re.search(r'"message":"([^"]+)"', r["_body"])
        print(f"  [{label}] GAGAL -> {m.group(1) if m else r['_body'][:200]}")
        return None
    blob = http("GET", f"/3mf/{r['output_token']}", raw=True)
    f = os.path.join(DATA, f"slice-{label}.3mf"); open(f, "wb").write(blob)
    with zipfile.ZipFile(f) as z:
        si = z.read("Metadata/slice_info.config").decode()
    fils = re.findall(r'<filament id="(\d+)"[^>]*used_m="([\d.]+)" used_g="([\d.]+)"', si)
    w = re.search(r'<metadata key="weight" value="([\d.]+)"', si)
    t = re.search(r'<metadata key="prediction" value="(\d+)"', si)
    print(f"  [{label}] OK -> plate={w.group(1) if w else '?'}g waktu={t.group(1) if t else '?'}s | "
          + ", ".join(f"fil#{i}={g}g" for i, _, g in fils))
    return f


if __name__ == "__main__":
    print("varian dengan filament_map_mode Manual:")
    run("F-manual-nomap", [FIL_A, FIL_B], {"filament_map_mode": "Manual"})
    run("G-manual-map11", [FIL_A, FIL_B], {"filament_map_mode": "Manual"}, [1, 1])
    run("H-objext1-manual", [FIL_A, FIL_B], {"filament_map_mode": "Manual"}, [1, 1], ext2=1)
