# -*- coding: utf-8 -*-
"""
fig_threshold.py
================
Ve "Hinh 4 - Phan bo diem chuan va vi tri nguong" cho bao cao NCKH AskCell.

Doc tep null_hist.npz (~5 KB) do compute_null.py sinh ra, nen script nay chay
duoc o BAT KY DAU — ke ca Google Colab — ma khong can lai file .fcs.
Chi can tai kem null_hist.npz.

    python fig_threshold.py

Xuat ra: fig_threshold.png (300 DPI) va fig_threshold.pdf

NGUON SO LIEU
-------------
1.117.835 diem khoang cach cua te bao khoe manh, do bang leave-one-out tren
20 mau tuy xuong (xem compute_null.py). Nguong tinh duoc 0,8735 khop tuyet doi
voi benchmark.json, ke ca ca 5 phan vi p50/p90/p99/p99.9/p99.99.

VI SAO HAI PANEL
----------------
Dinh histogram cao 25.488 te bao, trong khi ca phan duoi vuot nguong chi cao
toi da 227 te bao. Neu ve chung mot truc tung thi phan duoi — dung cho ta can
nhin — se bien mat hoan toan. Panel B phong to dung vung do.
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
NPZ = os.path.join(HERE, "null_hist.npz")

# --------------------------------------------------------------------------- #
# BANG MAU - dong bo voi cac hinh khac
# (cam = te bao bi giai doan 1 danh dau, giong y nghia trong Hinh 5)
# --------------------------------------------------------------------------- #
BLUE    = "#2a78d6"
ORANGE  = "#eb6834"
ORANGE_L= "#fdeae2"
NEUTRAL = "#e1e0d9"
INK     = "#0b0b0b"
INK2    = "#52514e"
MUTED   = "#898781"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
    "axes.edgecolor": NEUTRAL,
    "axes.labelcolor": INK2,
    "text.color": INK,
    "xtick.color": INK2,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def vn(n):
    return "{:,}".format(int(round(n))).replace(",", ".")


def dec(x, nd=2):
    return ("{:." + str(nd) + "f}").format(x).replace(".", ",")


# --------------------------------------------------------------------------- #
if not os.path.exists(NPZ):
    raise SystemExit(
        "Thieu null_hist.npz. Chay truoc:\n"
        "    cd backend && .venv/Scripts/python figures/compute_null.py"
    )

d = np.load(NPZ, allow_pickle=True)
counts = d["counts"]
edges = d["edges"]
THRESH = float(d["threshold"])
PCTILE = float(d["percentile"])
N_TOTAL = int(d["n_total"])
N_OVER = int(d["n_over"])
N_SPEC = int(d["n_specimens"])
QUANTS = json.loads(str(d["quantiles"].item()))

lefts = edges[:-1]
widths = np.diff(edges)
over = lefts >= THRESH
colors = np.where(over, ORANGE, BLUE)

ZOOM_FROM = 0.60

fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.8, 5.1))
fig.subplots_adjust(left=0.068, right=0.978, top=0.735, bottom=0.145, wspace=0.22)


def panel_title(ax, letter, text, sub):
    ax.text(0, 1.135, letter + ". " + text, transform=ax.transAxes,
            fontsize=10.5, fontweight="bold", color=INK, va="bottom")
    ax.text(0, 1.045, sub, transform=ax.transAxes, fontsize=8.4,
            color=MUTED, va="bottom")


# --------------------------------------------------------------------------- #
# A - Toan canh phan bo
# --------------------------------------------------------------------------- #
axA.bar(lefts, counts, width=widths, align="edge", color=colors, linewidth=0)
axA.set_xlim(0, edges[-1])
axA.set_ylim(0, counts.max() * 1.16)
axA.set_xlabel("điểm khoảng cách tới 15 tế bào khỏe mạnh gần nhất",
               fontsize=8.8, color=INK2)
axA.set_ylabel("số tế bào khỏe mạnh", fontsize=8.8, color=INK2)
axA.set_yticks([0, 10_000, 20_000])
axA.set_yticklabels(["0", "10.000", "20.000"], fontsize=8.5)
axA.yaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axA.set_axisbelow(True)

axA.axvline(THRESH, color=INK, lw=1.6, ls="--", zorder=5)
axA.text(THRESH - 0.03, counts.max() * 1.02,
         "ngưỡng " + dec(THRESH, 4).rstrip("0"),
         ha="right", va="top", fontsize=9.5, fontweight="bold", color=INK,
         zorder=6, bbox=dict(boxstyle="round,pad=0.25", facecolor=SURFACE,
                             edgecolor="none", alpha=0.85))

# Khung danh dau vung se duoc phong to o panel B
axA.add_patch(Rectangle((ZOOM_FROM, 0), edges[-1] - ZOOM_FROM,
                        counts.max() * 0.055,
                        facecolor=ORANGE_L, edgecolor=ORANGE,
                        linewidth=1.0, zorder=4))
axA.text(ZOOM_FROM - 0.02, counts.max() * 0.10, "vùng phóng to ở panel B →",
         ha="right", va="bottom", fontsize=8.2, color=ORANGE, fontweight="bold")

# Dat o vung TRONG (ben phai dinh, ngay duoi nhan nguong) thay vi de len cot
axA.text(0.62, counts.max() * 0.88,
         "Hầu hết tế bào khỏe mạnh\nnằm ở vùng điểm thấp\n(trung vị "
         + dec(QUANTS["p50"], 4).rstrip("0") + ")",
         fontsize=8.8, color=INK2, va="top", ha="left", linespacing=1.55,
         zorder=6, bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE,
                             edgecolor=NEUTRAL, linewidth=0.8))

panel_title(axA, "A", "Toàn bộ phân bố điểm của tế bào khỏe mạnh",
            vn(N_TOTAL) + " tế bào từ " + str(N_SPEC)
            + " mẫu, chấm bằng leave-one-out")


# --------------------------------------------------------------------------- #
# B - Phong to phan duoi
# --------------------------------------------------------------------------- #
m = lefts >= ZOOM_FROM
axB.bar(lefts[m], counts[m], width=widths[m], align="edge",
        color=colors[m], linewidth=0)
axB.set_xlim(ZOOM_FROM, edges[-1])
tail_max = counts[m].max()
axB.set_ylim(0, tail_max * 1.42)
axB.set_xlabel("điểm khoảng cách (phóng to phần đuôi)", fontsize=8.8, color=INK2)
axB.set_ylabel("số tế bào khỏe mạnh", fontsize=8.8, color=INK2)
axB.yaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axB.set_axisbelow(True)

axB.axvline(THRESH, color=INK, lw=1.6, ls="--", zorder=5)
axB.text(THRESH - 0.012, tail_max * 1.36, "ngưỡng\n" + dec(THRESH, 4).rstrip("0"),
         ha="right", va="top", fontsize=9.5, fontweight="bold", color=INK,
         linespacing=1.4, zorder=6,
         bbox=dict(boxstyle="round,pad=0.25", facecolor=SURFACE,
                   edgecolor="none", alpha=0.85))

axB.annotate(
    vn(N_OVER) + " tế bào vượt ngưỡng\n= " + dec(N_OVER / N_TOTAL * 100, 4)
    + "% số tế bào khỏe mạnh",
    xy=(THRESH + 0.075, tail_max * 0.16),
    xytext=(THRESH + 0.135, tail_max * 0.92),
    fontsize=9, color=ORANGE, fontweight="bold", linespacing=1.5,
    zorder=6,
    bbox=dict(boxstyle="round,pad=0.3", facecolor=SURFACE, edgecolor="none",
              alpha=0.85),
    arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.4,
                    connectionstyle="arc3,rad=-0.25"))

axB.legend(handles=[
    Patch(facecolor=BLUE, label="Dưới ngưỡng — không bị đánh dấu"),
    Patch(facecolor=ORANGE, label="Trên ngưỡng — giai đoạn 1 đánh dấu"),
], loc="lower right", frameon=False, fontsize=8.6,
    handlelength=1.2, handleheight=1.2, labelspacing=0.55,
    borderpad=1.1)

panel_title(axB, "B", "Phần đuôi: đúng 0,1% đã định trước",
            "Phần cam chính là tỷ lệ báo động nhầm mà nhóm chủ động chấp nhận")


# --------------------------------------------------------------------------- #
fig.suptitle("Ngưỡng phát hiện được ĐO, không phải được ĐOÁN",
             fontsize=13.5, fontweight="bold", color=INK, x=0.012, ha="left",
             y=0.965)
fig.text(0.012, 0.898,
         "Đặt tại phân vị " + dec(PCTILE, 1) + " của phân bố điểm chuẩn → "
         "tỷ lệ báo động nhầm là con số biết trước, không phải bất ngờ "
         "phát hiện về sau",
         fontsize=9, color=MUTED, ha="left", va="top")

fig.savefig("fig_threshold.png", dpi=300, bbox_inches="tight", facecolor=SURFACE)
fig.savefig("fig_threshold.pdf", bbox_inches="tight", facecolor=SURFACE)
print("Da xuat: fig_threshold.png va .pdf")
print(f"  nguong {THRESH:.4f} | vuot nguong {N_OVER:,}/{N_TOTAL:,} = "
      f"{N_OVER / N_TOTAL * 100:.4f}%")
