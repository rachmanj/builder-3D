#!/usr/bin/env python3
"""Spike 003 langkah 1: kirim satu perintah teks ke Tripo V3, tunggu, unduh GLB.

Kunci dibaca dari ~/.hermes/secrets/tripo_api_key.txt — TIDAK pernah dicetak.
"""
import json
import os
import sys
import time
import urllib.request

KEY_FILE = os.path.expanduser("~/.hermes/secrets/tripo_api_key.txt")
BASE = "https://openapi.tripo3d.ai/v3"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

PROMPT = ("A small ceramic sitting cat figurine, glossy white body with blue batik "
          "patterns and gold accents on the ears and tail")
NEG = "blurry, low quality, broken mesh, extra limbs"


def key():
    with open(KEY_FILE) as f:
        return f.read().strip()


def api(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode(errors="replace")[:400]}


def balance():
    b = api("GET", "/account/balance")
    return b.get("data", {})


def main():
    os.makedirs(DATA, exist_ok=True)
    b0 = balance()
    print(f"[1] saldo awal: balance={b0.get('balance')} frozen={b0.get('frozen')}")

    payload = {
        "prompt": PROMPT,
        "model": "v3.1-20260211",
        "negative_prompt": NEG,
        "face_limit": 30000,
        "texture": True,
        "pbr": True,
    }
    print("[2] kirim /v3/generation/text-to-model")
    print("    prompt:", PROMPT)
    r = api("POST", "/generation/text-to-model", payload)
    if r.get("code") != 0:
        print("    GAGAL:", json.dumps(r)[:400]); return
    tid = r["data"]["task_id"]
    print("    task_id:", tid)

    b1 = balance()
    print(f"    saldo setelah kirim: balance={b1.get('balance')} frozen={b1.get('frozen')}")

    print("[3] tunggu hasilnya")
    t0 = time.time()
    last = None
    while time.time() - t0 < 600:
        s = api("GET", f"/tasks/{tid}")
        d = s.get("data", {})
        st = d.get("status")
        if (st, d.get("progress")) != last:
            print(f"    [{int(time.time()-t0):4d}s] {st} progress={d.get('progress')}")
            last = (st, d.get("progress"))
        if st in ("success", "failed", "cancelled"):
            print("    hasil:", json.dumps({k: v for k, v in d.items() if k != "output"})[:300])
            if st != "success":
                print("    output/error:", json.dumps(d)[:400])
                return
            print("    output:", json.dumps(d.get("output", {}))[:400])
            url = (d.get("output") or {}).get("model_url") or (d.get("output") or {}).get("pbr_model")
            if not url:
                print("    tidak ada model_url; seluruh output:", json.dumps(d)[:600]); return
            out = os.path.join(DATA, "tripo-kucing.glb")
            with urllib.request.urlopen(url, timeout=300) as resp, open(out, "wb") as fh:
                fh.write(resp.read())
            print(f"    GLB tersimpan: {out} ({os.path.getsize(out)} byte)")
            json.dump(d, open(os.path.join(DATA, "tripo-kucing.task.json"), "w"), indent=1)
            break
        time.sleep(8)
    else:
        print("    waktu habis menunggu")
    b2 = balance()
    print(f"[4] saldo akhir: balance={b2.get('balance')} frozen={b2.get('frozen')}")


if __name__ == "__main__":
    main()
