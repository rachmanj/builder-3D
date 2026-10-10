#!/usr/bin/env python3
"""Spike 003 langkah 7 — perbaiki perlindungan aksen.

Masalah di langkah 6: melindungi warna aksen dengan mengembalikan wilayah MENTAH
mengembalikan juga kebisingannya -> filter lebih agresif justru lebih buruk (479 -> 623).

Perbaikan: setelah wilayah aksen dikembalikan, jalankan mode filter LAGI tetapi
segitiga milik aksen DIKUNCI (tidak boleh berpindah warna). Jadi aksen tetap luas,
tapi batasnya rapi. Ditambah operasi "isi lubang": segitiga yang seluruh tetangganya
satu warna dan tidak terkunci akan ikut warna itu.
"""
import importlib.util
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TPL = os.path.join(os.path.dirname(HERE), "001-orcaslicer-headless", "data", "template-p2s.3mf")
GLB = os.path.join(HERE, "data", "tripo-kucing.glb")
FILS3 = ["GFSA00_11", "GFSA01_12", "GFSA00_11"]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


g2p = load("g2p", os.path.join(os.path.dirname(HERE), "002-gltf-to-perfacet", "glb2perfacet.py"))
sm = load("sm", os.path.join(HERE, "segment_merge.py"))
am = load("am", os.path.join(HERE, "auto_measure.py"))
s5 = g2p.load_s5()


def restore_accent_areas(labels, adj, raw, raw_share, floor_ratio=0.5):
    """Kembalikan wilayah aksen yang tergerus, lalu TANDAI sebagai terkunci."""
    labels = list(labels)
    locked = [False] * len(labels)
    for g, rs in raw_share.items():
        target = max(1, int(rs * floor_ratio))
        cur = sum(1 for l in labels if l == g)
        if cur >= target:
            continue
        comps = sorted([(lab, c) for lab, c in sm.components(raw, adj) if lab == g],
                       key=lambda t: -len(t[1]))
        for _, comp in comps:
            if cur >= target:
                break
            for t in comp:
                if labels[t] != g:
                    labels[t] = g
                    cur += 1
                    locked[t] = True
    return labels, locked


def smooth_locked(labels, adj, locked, iterations=4):
    """Haluskan hanya segitiga yang tidak terkunci."""
    for _ in range(iterations):
        new = list(labels)
        for t, nbrs in enumerate(adj):
            if locked[t] or not nbrs:
                continue
            cnt = Counter(labels[n] for n in nbrs)
            cnt[labels[t]] += 1
            new[t] = max(cnt.items(), key=lambda kv: (kv[1], -kv[0]))[0]
        labels = new
    return labels


def fill_enclaves(labels, adj, locked, rounds=2):
    """Segitiga yang tidak terkunci dan semua tetangganya satu warna -> ikut warna itu."""
    for _ in range(rounds):
        new = list(labels)
        for t, nbrs in enumerate(adj):
            if locked[t] or not nbrs:
                continue
            s = {labels[n] for n in nbrs}
            if len(s) == 1 and labels[t] not in s:
                new[t] = s.pop()
        if new == labels:
            break
        labels = new
    return labels


def hitung(verts2, tris, tri_fil, colors, label):
    r = am.build(os.path.join(DATA, f"al7-{label}.3mf"), verts2, tris, tri_fil, colors, None)
    if r.get("_err"):
        print(f"  {label}: GAGAL {r['msg'][:150]}"); return None, None
    nT = len(re.findall(r"^T[0-9]+$", r["gc"], re.M))
    return nT, r["est"]["weight_g"]


def main():
    verts, uvs, tris, verts2, adj, raw, raw_share, colors = am.siapkan()
    n = len(raw)
    print("porsi warna asli: " + ", ".join(f"{g+1}: {100*v/n:.1f}%" for g, v in raw_share.items()))
    print()
    print("perbandingan (semua diukur sungguhan):")
    print(f"  {'setelan':34} {'porsi warna':28} {'ganti warna':>11} {'total':>10}")

    # acuan: tanpa perlindungan aksen (hasil terbaik sejauh ini)
    lab0 = sm.drop_small_regions(sm.mode_filter(raw, adj, 6), adj, 600)
    sh0 = Counter(lab0)
    nT0, w0 = hitung(verts2, tris, [x + 1 for x in lab0], colors, "acuan-noprotect")
    print(f"  {'filter 6 / min 600 (tanpa proteksi)':34} "
          f"{' '.join(f'{g+1}:{100*sh0[g]/n:.0f}%' for g in range(3)):28} {nT0:>11} {w0:>9.2f} g")

    for iters, minsize in ((6, 400), (6, 600), (8, 900)):
        lab = sm.drop_small_regions(sm.mode_filter(raw, adj, iters), adj, minsize) if minsize else \
            sm.mode_filter(raw, adj, iters)
        lab, locked = restore_accent_areas(lab, adj, raw, raw_share)
        lab = smooth_locked(lab, adj, locked, 4)
        lab = fill_enclaves(lab, adj, locked, 2)
        sh = Counter(lab)
        nT, w = hitung(verts2, tris, [x + 1 for x in lab], colors, f"{iters}-{minsize}")
        if nT is None:
            continue
        print(f"  {'filter %d / min %d + proteksi terkunci' % (iters, minsize):34} "
              f"{' '.join(f'{g+1}:{100*sh[g]/n:.0f}%' for g in range(3)):28} {nT:>11} {w:>9.2f} g")


if __name__ == "__main__":
    main()
