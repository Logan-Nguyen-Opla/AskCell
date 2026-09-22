# -*- coding: utf-8 -*-
"""
fig_two_stage.py
================
Ve "Hinh 5 - Giai doan 1 so voi giai doan 2" cho bao cao NCKH AskCell.

Moi con so lay truc tiep tu benchmark/benchmark.json (cac lan chay o do sau
500.000 su kien), nen script chay duoc o Colab ma khong can file .fcs.

    python fig_two_stage.py

Xuat ra: fig_two_stage.png (300 DPI) va fig_two_stage.pdf
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

# --------------------------------------------------------------------------- #
# BANG MAU - dong bo voi cac hinh khac trong bao cao
# --------------------------------------------------------------------------- #
BLUE    = "#2a78d6"   # giai doan 2 - ket qua dung
ORANGE  = "#eb6834"   # giai doan 1 - phong dai
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
# SO LIEU - benchmark.json, cac lan chay o do sau 500.000 su kien
# (ten, ty le that %, so te bao that, giai doan 1 bao, giai doan 2 bao)
# --------------------------------------------------------------------------- #
ROWS = [
    ("5,11%", 5.10879, 23_796, 24_240, 23_796),
    ("1,02%", 1.02216,  4_761,  5_199,  4_761),
    ("0,10%", 0.10026,    467,    924,    462),
    ("0,05%", 0.04894,    228,    645,    226),
    ("0,01%", 0.00988,     46,    519,     44),
]

labels = [r[0] for r in ROWS]
truth = [r[2] for r in ROWS]
stage1 = [r[3] for r in ROWS]
stage2 = [r[4] for r in ROWS]
ratio = [s / t for s, t in zip(stage1, truth)]

# --------------------------------------------------------------------------- #
fig, ax = plt.subplots(figsize=(10.4, 5.6))
fig.subplots_adjust(left=0.085, right=0.975, top=0.775, bottom=0.145)

W = 0.34
xs = list(range(len(ROWS)))

for i in xs:
    ax.bar(i - W / 2 - 0.015, stage1[i], width=W, color=ORANGE, zorder=3)
    ax.bar(i + W / 2 + 0.015, stage2[i], width=W, color=BLUE, zorder=3)
    # Vach danh dau SO THAT, keo ngang ca nhom
    ax.plot([i - W - 0.10, i + W + 0.10], [truth[i], truth[i]],
            color=INK, lw=2.0, solid_capstyle="butt", zorder=5)

ax.set_yscale("log")
ax.set_ylim(20, 260_000)
ax.set_xlim(-0.65, len(ROWS) - 0.35)
ax.set_xticks(xs)
ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
ax.set_xlabel("tỷ lệ tế bào ác tính thật trong mẫu", fontsize=9, color=INK2)
ax.set_ylabel("số tế bào (thang logarit)", fontsize=9, color=INK2)
ax.yaxis.grid(True, color=NEUTRAL, linewidth=0.8)
ax.set_axisbelow(True)

# Nhan so tren tung cot
for i in xs:
    ax.text(i - W / 2 - 0.015, stage1[i] * 1.13, vn(stage1[i]), ha="center",
            va="bottom", fontsize=8.4, fontweight="bold", color=ORANGE)
    ax.text(i + W / 2 + 0.015, stage2[i] * 1.13, vn(stage2[i]), ha="center",
            va="bottom", fontsize=8.4, fontweight="bold", color=BLUE)
    # Muc phong dai cua giai doan 1 - dat NGAY TREN nhan so cua cot cam
    big = ratio[i] > 1.5
    ax.text(i - W / 2 - 0.015, stage1[i] * 1.75, "×" + dec(ratio[i], 1),
            ha="center", va="bottom",
            fontsize=12 if big else 9.5, fontweight="bold",
            color=ORANGE if big else MUTED)

ax.legend(handles=[
    Line2D([0], [0], color=INK, lw=2.0, label="Số tế bào ác tính THẬT"),
    Patch(facecolor=ORANGE, label="Giai đoạn 1 báo (chỉ đánh dấu tế bào lạ)"),
    Patch(facecolor=BLUE, label="Giai đoạn 2 báo (sau khi phân cụm)"),
], loc="upper right", frameon=False, fontsize=9,
    handlelength=1.5, handleheight=1.2, labelspacing=0.65)

ax.set_title("Giai đoạn 1 phóng đại khi bệnh còn ít; giai đoạn 2 đưa về đúng",
             loc="left", fontsize=13, fontweight="bold", color=INK, pad=26)
ax.text(0, 1.045, "Cùng một mẫu 500.000 sự kiện · vạch đen là con số thật cần tìm được",
        transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")

fig.savefig("fig_two_stage.png", dpi=300, bbox_inches="tight", facecolor=SURFACE)
fig.savefig("fig_two_stage.pdf", bbox_inches="tight", facecolor=SURFACE)
print("Da xuat: fig_two_stage.png va .pdf")
for i in xs:
    print(f"  {labels[i]}: that {truth[i]:>6} | gd1 {stage1[i]:>6} ({ratio[i]:.1f}x) | gd2 {stage2[i]:>6}")
