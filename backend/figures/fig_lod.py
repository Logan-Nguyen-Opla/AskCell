# -*- coding: utf-8 -*-
"""
fig_lod.py
==========
Ve "Hinh 7 - Gioi han phat hien theo do sau thu thap" cho bao cao NCKH AskCell.

So lieu tu benchmark/benchmark.json (truong limit_of_detection_pct va so te bao
that tuong ung cua tung lan chay). Chay duoc o Colab, khong can file .fcs.

    python fig_lod.py

Xuat ra: fig_lod.png (300 DPI) va fig_lod.pdf

Y DO CUA HINH
-------------
Hai panel canh nhau de lam bat luan diem cot loi cua de tai:
  (A) TY LE phat hien duoc thay doi toi 10 lan khi thu thap nhieu hon.
  (B) SO TE BAO toi thieu thi gan nhu khong doi (46-96 te bao).
=> Gioi han phat hien la mot SO LUONG TE BAO, khong phai mot TY LE PHAN TRAM.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --------------------------------------------------------------------------- #
BLUE    = "#2a78d6"
BLUE_L  = "#cde2fb"
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
    return ("{:." + str(nd) + "f}").format(x).replace(".", ",").rstrip("0").rstrip(",")


# --------------------------------------------------------------------------- #
# SO LIEU - benchmark.json
# (so su kien thu thap, ty le thap nhat phat hien duoc %, so te bao tuong ung)
# --------------------------------------------------------------------------- #
DEPTHS = [50_000, 200_000, 500_000]
PCTS = [0.1, 0.05, 0.01]
CELLS = [46, 96, 46]

MIN_C, MAX_C = min(CELLS), max(CELLS)

fig, (axA, axB) = plt.subplots(1, 2, figsize=(11.4, 4.9))
fig.subplots_adjust(left=0.075, right=0.975, top=0.735, bottom=0.155, wspace=0.28)


def panel_title(ax, letter, text, sub):
    ax.text(0, 1.135, letter + ". " + text, transform=ax.transAxes,
            fontsize=10.5, fontweight="bold", color=INK, va="bottom")
    ax.text(0, 1.045, sub, transform=ax.transAxes, fontsize=8.4,
            color=MUTED, va="bottom")


# --------------------------------------------------------------------------- #
# A - Ty le phat hien duoc: thay doi 10 lan
# --------------------------------------------------------------------------- #
axA.plot(DEPTHS, PCTS, color=BLUE, lw=2.2, marker="o", markersize=10,
         markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=2,
         zorder=3)
axA.set_xscale("log")
axA.set_yscale("log")
axA.set_xlim(35_000, 800_000)
axA.set_ylim(0.006, 0.22)
axA.set_xticks(DEPTHS)
axA.set_xticklabels(["50k", "200k", "500k"], fontsize=9)
axA.set_yticks(PCTS)
axA.set_yticklabels(["0,1%", "0,05%", "0,01%"], fontsize=9)
axA.set_xlabel("số sự kiện thu thập", fontsize=9, color=INK2)
axA.set_ylabel("tỷ lệ thấp nhất phát hiện được", fontsize=9, color=INK2)
axA.grid(True, color=NEUTRAL, linewidth=0.8)
axA.set_axisbelow(True)

# Can le theo vi tri diem de nhan khong tran mep truc
ALIGN = ["left", "center", "right"]
for d, p, al in zip(DEPTHS, PCTS, ALIGN):
    axA.text(d, p * 1.32, dec(p) + "%", ha=al, va="bottom",
             fontsize=11, fontweight="bold", color=BLUE)

axA.annotate("", xy=(295_000, 0.0163), xytext=(52_000, 0.088),
             arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.3,
                             connectionstyle="arc3,rad=0.20"))
axA.text(122_000, 0.0180, "tốt lên\n10 lần", ha="center", va="center",
         fontsize=8.6, color=MUTED, fontweight="bold", linespacing=1.4)

panel_title(axA, "A", "Tỷ lệ phát hiện được: thay đổi 10 lần",
            "Thu thập càng nhiều, tỷ lệ nhỏ nhất tìm được càng thấp")


# --------------------------------------------------------------------------- #
# B - So te bao toi thieu: gan nhu khong doi
# --------------------------------------------------------------------------- #
axB.axhspan(MIN_C, MAX_C, color=BLUE_L, zorder=1)
axB.plot(DEPTHS, CELLS, color=BLUE, lw=2.2, marker="o", markersize=10,
         markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=2,
         zorder=3)
axB.set_xscale("log")
axB.set_xlim(35_000, 800_000)
axB.set_ylim(0, 160)
axB.set_xticks(DEPTHS)
axB.set_xticklabels(["50k", "200k", "500k"], fontsize=9)
axB.set_yticks([0, 30, 50, 100, 150])
axB.set_yticklabels(["0", "30", "50", "100", "150"], fontsize=9)
axB.set_xlabel("số sự kiện thu thập", fontsize=9, color=INK2)
axB.set_ylabel("số tế bào ác tính tối thiểu tìm được", fontsize=9, color=INK2)
axB.yaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axB.set_axisbelow(True)

# Diem thap (46) ghi nhan BEN DUOI, diem cao (96) ghi BEN TREN
# -> nhan khong bao gio nam de len duong noi cac diem
for d, c in zip(DEPTHS, CELLS):
    above = c == MAX_C
    axB.text(d, c + (10 if above else -8), vn(c) + " tế bào", ha="center",
             va="bottom" if above else "top",
             fontsize=10.5, fontweight="bold", color=BLUE)

# Nhan cua vung to mau dat PHIA TREN dai, tranh de len duong va nhan diem
axB.text(37_000, MAX_C + 6, "vùng 46–96 tế bào", ha="left", va="bottom",
         fontsize=8.6, color="#1c5cab", fontweight="bold")

axB.axhline(30, color=INK2, lw=1.2, ls="--", zorder=2)
axB.text(37_000, 24, "sàn 30 sự kiện (min_cluster)", ha="left", va="top",
         fontsize=8, color=INK2, fontweight="bold")

panel_title(axB, "B", "Số tế bào tối thiểu: gần như không đổi",
            "Máy luôn cần khoảng 46–96 tế bào mới nhận ra một quần thể")


# --------------------------------------------------------------------------- #
fig.suptitle("Giới hạn phát hiện là một SỐ LƯỢNG TẾ BÀO, không phải một TỶ LỆ",
             fontsize=13, fontweight="bold", color=INK, x=0.012, ha="left", y=0.965)
fig.text(0.012, 0.90,
         "Muốn tìm được quần thể có tỷ lệ càng nhỏ thì phải thu thập càng nhiều sự kiện — "
         "đúng cách các xét nghiệm MRD lâm sàng đang làm",
         fontsize=9, color=MUTED, ha="left", va="top")

fig.savefig("fig_lod.png", dpi=300, bbox_inches="tight", facecolor=SURFACE)
fig.savefig("fig_lod.pdf", bbox_inches="tight", facecolor=SURFACE)
print("Da xuat: fig_lod.png va .pdf")
for d, p, c in zip(DEPTHS, PCTS, CELLS):
    print(f"  {d:>7,} su kien -> {p}%  (~{c} te bao)")
