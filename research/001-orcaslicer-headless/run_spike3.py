#!/usr/bin/env python3
"""Spike 001 tahap 3: mesin 2 nozzle (Bambu H2D Pro). Kalau ini memberi gram per warna
+ jumlah terbuang, maka kemampuan inti terbukti ada."""
import json
import os
import re
import urllib.request
import zipfile

BASE = "http://localhost:8070"
MACHINE, PROCESS = "GM051", "GP130"     # H2D Pro 0.4 nozzle (2 nozzle), 0.20mm Standard
FIL_A, FIL_B = "GFSA00_17", "GFSA01_17"  # Bambu PLA Basic / PLA Matte @BBL H2DP
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
        return {"_err": e.code, "_body": e.read().decode(errors="replace")[:600]}
    return p if raw else json.loads(p.decode())


def mp(fields, files, boundary="----spk3"):
    out = b""
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fn, c) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + c + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def make_template(dst):
    stl = os.path.join(DATA, "model-uji.stl")
    b, h = mp({"machine_id": MACHINE, "process_id": PROCESS, "auto_orient": "true", "arrange": "true"},
              {"file": ("model-uji.stl", open(stl, "rb").read())})
    imp = http("POST", "/stl/import", b, h)
    if "_err" in imp:
        raise RuntimeError(f"import gagal {imp['_body'][:300]}")
    mat = http("POST", f"/stl/{imp['draft_token']}/3mf", {})
    tok = mat["input_token"]
    open(dst, "wb").write(http("GET", f"/3mf/{tok}", raw=True))
    return tok


def make_2obj(src, dst, ext2=2):
    with zipfile.ZipFile(src) as z:
        items = {n: z.read(n) for n in z.namelist()}
    model = items["3D/3dmodel.model"].decode()
    on_plate = re.search(r'<build>\s*<item objectid="(\d+)"', model).group(1)
    other = next(o for o in re.findall(r'<object id="(\d+)" type="model"', model) if o != on_plate)
    b = re.search(r"<build>.*?</build>", model, re.S).group(0)
    model = model.replace(b, b.replace("</build>",
        f'  <item objectid="{other}" transform="1 0 0 0 1 0 0 0 1 55 0 0" printable="1"/>\n </build>'))
    items["3D/3dmodel.model"] = model.encode()
    ms = items["Metadata/model_settings.config"].decode()
    blk = re.search(r'  <object id="' + on_plate + r'">.*?  </object>', ms, re.S).group(0)
    nb = re.sub(r'(<metadata key="extruder" value=")\d+(")', rf'\g<1>{ext2}\g<2>', blk)
    nb = nb.replace(f'<object id="{on_plate}">', f'<object id="{other}">')
    ms = ms.replace("\n  <assemble>", "\n" + nb + "\n  <assemble>")
    items["Metadata/model_settings.config"] = ms.encode()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in items.items():
            z.writestr(n, c)
    return on_plate, other


def report(sl, label):
    est = sl.get("estimate", {})
    blob = http("GET", f"/3mf/{sl['output_token']}", raw=True)
    f = os.path.join(DATA, f"slice-{label}.3mf"); open(f, "wb").write(blob)
    with zipfile.ZipFile(f) as z:
        si = z.read("Metadata/slice_info.config").decode()
        gc = z.read("Metadata/plate_1.gcode").decode(errors="replace")
    print(f"  [{label}] estimate JSON:")
    for k in ("weight_g", "filament_used_m", "model_weight_g", "time_seconds"):
        print(f"      {k} = {est.get(k)}")
    print(f"  [{label}] slice_info.config:")
    for line in si.splitlines():
        if any(k in line for k in ("filament ", "weight", "prediction", "filament_maps", "flush")):
            print("      ", line.strip())
    flushes = re.findall(r"^; flush_volumes_matrix = (.*)$", gc, re.M)
    print(f"  [{label}] flush_volumes_matrix di gcode: {flushes[:1]}")
    print(f"  [{label}] jumlah ganti filamen di gcode (T0/T1): {len(re.findall(r'^T[0-9]$', gc, re.M))}")
    tot = re.findall(r"^; total filament (weight|length) \[g\] = (.*)$", gc, re.M)
    print(f"  [{label}] header total filament: {tot}")
    return est, si


if __name__ == "__main__":
    tpl = os.path.join(DATA, "template-h2dp.3mf")
    if not os.path.exists(tpl):
        make_template(tpl)
        print("[1] template H2D Pro dibuat")
    t1 = http("POST", "/3mf", *mp({"machine_id": MACHINE, "process_id": PROCESS},
                                 {"file": ("t.3mf", open(tpl, "rb").read())}))
    print("[2] inspect:", json.dumps(http("GET", f"/3mf/{t1['token']}/inspect").get("filaments"))[:200])

    p2 = os.path.join(DATA, "h2dp-2obj.3mf")
    op, ot = make_2obj(tpl, p2, ext2=2)
    print(f"[3] 3MF 2 objek dibuat (objek plate={op}, objek ke-2={ot})")
    t2 = http("POST", "/3mf", *mp({"machine_id": MACHINE, "process_id": PROCESS},
                                 {"file": ("p.3mf", open(p2, "rb").read())}))
    print("    inspect plate:", json.dumps(http("GET", f"/3mf/{t2['token']}/inspect")["plates"])[:350])

    print("[4] slice 2 objek / 2 filamen / 2 nozzle")
    sl = http("POST", "/slice/v2", {"input_token": t2["token"], "machine_id": MACHINE,
                                    "process_id": PROCESS,
                                    "filament_settings_ids": [FIL_A, FIL_B], "auto_center": True})
    if "_err" in sl:
        print("    GAGAL ->", sl["_body"][:400])
    else:
        report(sl, "h2dp-2warna")
