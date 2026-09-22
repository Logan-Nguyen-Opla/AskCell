# -*- coding: utf-8 -*-
"""
compute_null.py
===============
Tinh PHAN BO DIEM CHUAN (null distribution) bang leave-one-out tren 20 mau
tuy xuong khoe manh, roi luu lai duoi dang histogram nho gon de ve Hinh 4.

Vi sao can script rieng: benchmark.json chi luu 5 phan vi (p50, p90, p99,
p99.9, p99.99) chu khong luu ca mang diem. Muon ve histogram thi phai chay
lai dung buoc hieu chuan trong app/flow/reference.py.

CHAY O MAY LOCAL (can .venv da cai flowkit + anndata):
    cd backend
    .venv/Scripts/python figures/compute_null.py

Xuat ra: figures/null_hist.npz  (~vai KB) — sau do fig_threshold.py doc tep nay
va ve duoc o bat ky dau, ke ca Google Colab, ma khong can lai file .fcs.

Script lap lai DUNG vong lap leave-one-out trong _fit_from_matrices() va tu
kiem tra lai nguong tinh duoc co khop voi benchmark.json hay khong.
"""

from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

from app.flow import read_fcs                       # noqa: E402
from app.flow.qc import gate, marker_matrix         # noqa: E402
from app.flow.reference import (                    # noqa: E402
    DEFAULT_CLOUD_CAP, DEFAULT_K, DEFAULT_PERCENTILE, _subsample,
)

SAMPLE_DIR = os.path.join(BACKEND, "sample_data")
OUT = os.path.join(HERE, "null_hist.npz")


def main() -> None:
    paths = sorted(glob.glob(os.path.join(SAMPLE_DIR, "normal_bm_*.fcs")))
    if len(paths) < 2:
        raise SystemExit(
            "Chua co fixtures. Chay truoc: python make_mock_fcs.py"
        )
    print(f"Doc {len(paths)} mau khoe manh...")

    mats = []
    for i, p in enumerate(paths, 1):
        adata = read_fcs(p, filename=os.path.basename(p))
        gated, _ = gate(adata)
        X, names = marker_matrix(gated)
        mats.append(X)
        print(f"  [{i:>2}/{len(paths)}] {os.path.basename(p)}  "
              f"{X.shape[0]:,} te bao sau gate QC")

    # ---- lap lai DUNG buoc hieu chuan trong _fit_from_matrices() ---------- #
    k, cloud_cap, percentile = DEFAULT_K, DEFAULT_CLOUD_CAP, DEFAULT_PERCENTILE
    per_specimen_cap = max(500, cloud_cap // len(mats))
    capped = [_subsample(m, per_specimen_cap, seed=42 + j)
              for j, m in enumerate(mats)]
    pooled = np.vstack(capped)
    center = pooled.mean(axis=0)
    scale = pooled.std(axis=0)
    scale[scale < 1e-6] = 1.0

    print("\nChay leave-one-out (bo tung mau ra, cham diem bang cac mau con lai)...")
    null_parts = []
    for i in range(len(mats)):
        others_z = np.vstack(
            [(capped[j] - center) / scale for j in range(len(mats)) if j != i]
        )
        held_z = (mats[i] - center) / scale
        tree = cKDTree(others_z)
        kk = min(k, others_z.shape[0])
        dist, _ = tree.query(held_z, k=kk, workers=-1)
        null_parts.append(dist.mean(axis=1) if dist.ndim > 1 else dist)
        print(f"  bo mau {i + 1:>2} -> cham {held_z.shape[0]:,} te bao")

    null = np.concatenate(null_parts)
    threshold = float(np.percentile(null, percentile))
    quants = {f"p{p}": float(np.percentile(null, p))
              for p in (50, 90, 99, 99.9, 99.99)}

    # ---- doi chieu voi benchmark.json ------------------------------------- #
    print(f"\nSo te bao trong phan bo chuan : {null.size:,}")
    print(f"Nguong tinh duoc (phan vi {percentile}) : {threshold:.4f}")
    bj = os.path.join(BACKEND, "benchmark", "benchmark.json")
    if os.path.exists(bj):
        ref = json.load(open(bj, encoding="utf-8"))["reference"]
        print(f"Nguong trong benchmark.json          : {ref['threshold']:.4f}")
        d = abs(threshold - ref["threshold"])
        print("  -> KHOP" if d < 0.005 else f"  -> LECH {d:.4f} (kiem tra lai)")
        print("\nDoi chieu tung phan vi:")
        for key, val in quants.items():
            r = ref["null_quantiles"].get(key)
            mark = "ok" if r is not None and abs(val - r) < 0.005 else "!!"
            print(f"  {key:>7}: tinh {val:.4f} | benchmark {r}  [{mark}]")

    # ---- luu histogram gon nhe -------------------------------------------- #
    hi = float(np.percentile(null, 99.999)) * 1.05
    counts, edges = np.histogram(null, bins=420, range=(0.0, hi))
    n_over = int((null > threshold).sum())

    np.savez_compressed(
        OUT,
        counts=counts.astype(np.int64),
        edges=edges.astype(np.float64),
        threshold=np.float64(threshold),
        percentile=np.float64(percentile),
        n_total=np.int64(null.size),
        n_over=np.int64(n_over),
        n_specimens=np.int64(len(mats)),
        quantiles=np.array(json.dumps(quants), dtype=object),
    )
    size_kb = os.path.getsize(OUT) / 1024
    print(f"\nDa luu {OUT} ({size_kb:.1f} KB)")
    print(f"  Vuot nguong: {n_over:,}/{null.size:,} = "
          f"{n_over / null.size * 100:.4f}%  (thiet ke: {100 - percentile}%)")


if __name__ == "__main__":
    main()
