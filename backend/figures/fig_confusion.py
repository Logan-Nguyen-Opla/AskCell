# -*- coding: utf-8 -*-
"""
fig_confusion.py
================
Ve "Hinh 6 - Ma tran nham lan cap te bao" cho bao cao NCKH AskCell.

So lieu tu benchmark/benchmark.json: lan chay o do sau 500.000 su kien voi
ty le ac tinh 0,05%. Script chay duoc o Colab, khong can file .fcs.

    python fig_confusion.py

Xuat ra: fig_confusion.png (300 DPI) va fig_confusion.pdf

LUU Y VE CACH TO MAU
--------------------
So te bao binh thuong (465.606) lon gap hon 2.000 lan so te bao ac tinh (228).
Neu to mau theo SO LUONG tuyet doi thi ba o con lai deu trang toat, khong doc
duoc gi. Vi vay mau duoc to theo TY LE TRONG TUNG HANG (bao nhieu % te bao ac
tinh that su duoc bao dung, bao nhieu % bi bo sot) — day la cach chuan de doc
ma tran nham lan khi hai lop mat can bang nang.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# --------------------------------------------------------------------------- #
BLUE_D  = "#1c5cab"   # o dung, ty le cao
BLUE_L  = "#cde2fb"
RED_D   = "#d03b3b"   # o sai
RED_L   = "#fbecec"
NEUTRAL = "#e1e0d9"
INK     = "#0b0b0b"
INK2    = "#52514e"
MUTED   = "#898781"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "figure.facecolor": SURFACE,
    "text.color": INK,
})


def vn(n):
    return "{:,}".format(int(round(n))).replace(",", ".")


def dec(x, nd=2):
    return ("{:." + str(nd) + "f}").format(x).replace(".", ",")


def mix(c_light, c_dark, t):
    """Tron hai mau hex theo ty le t (0 = nhat, 1 = dam)."""
    a = [int(c_light[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c_dark[i:i + 2], 16) for i in (1, 3, 5)]
    r = [int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)]
    return "#{:02x}{:02x}{:02x}".format(*r)


# --------------------------------------------------------------------------- #
# SO LIEU - benchmark.json, mau 500.000 su kien, ty le ac tinh 0,05%
# --------------------------------------------------------------------------- #
TP, FN = 226, 2            # hang "ac tinh that"
FP, TN = 0, 465_606        # hang "binh thuong that"
N = TP + FN + FP + TN

row_tot = [TP + FN, FP + TN]
CELLS = [
    # (hang, cot, so luong, dung hay sai)
    (0, 0, TP, True), (0, 1, FN, False),
    (1, 0, FP, False), (1, 1, TN, True),
]

sens = TP / (TP + FN) * 100
prec = TP / (TP + FP) * 100 if (TP + FP) else 0.0

# --------------------------------------------------------------------------- #
fig, ax = plt.subplots(figsize=(9.2, 5.4))
fig.subplots_adjust(left=0.235, right=0.985, top=0.72, bottom=0.10)
ax.set_xlim(0, 2)
ax.set_ylim(0, 2)
ax.axis("off")

for r, c, n, correct in CELLS:
    pct = n / row_tot[r] * 100
    t = (pct / 100) ** 0.55                      # to dam theo ty le trong hang
    face = mix(BLUE_L, BLUE_D, t) if correct else mix(RED_L, RED_D, t)
    x, y = c, 1 - r                              # hang 0 nam tren
    ax.add_patch(Rectangle((x + 0.012, y + 0.012), 0.976, 0.976,
                           facecolor=face, edgecolor="none"))
    txt = "white" if t > 0.55 else INK
    ax.text(x + 0.5, y + 0.60, vn(n), ha="center", va="center",
            fontsize=21, fontweight="bold", color=txt)
    ax.text(x + 0.5, y + 0.35, dec(pct) + "% của hàng", ha="center", va="center",
            fontsize=10, color=txt)

# Nhan hang / cot
ROW_LBL = ["Thật sự là\nTẾ BÀO ÁC TÍNH", "Thật sự là\nTẾ BÀO BÌNH THƯỜNG"]
COL_LBL = ["Máy báo\nÁC TÍNH", "Máy báo\nBÌNH THƯỜNG"]

for r in range(2):
    ax.text(-0.06, 1.5 - r, ROW_LBL[r], ha="right", va="center",
            fontsize=9.5, fontweight="bold", color=INK2, linespacing=1.5)
    ax.text(-0.06, 1.5 - r - 0.28, "(" + vn(row_tot[r]) + " tế bào)",
            ha="right", va="center", fontsize=8.2, color=MUTED)

for c in range(2):
    ax.text(c + 0.5, 2.08, COL_LBL[c], ha="center", va="bottom",
            fontsize=9.5, fontweight="bold", color=INK2, linespacing=1.5)

# Ghi chu duoi ma tran
ax.text(0, -0.13,
        "Ô xanh = máy trả lời đúng · Ô đỏ = máy trả lời sai. "
        "Màu đậm nhạt theo tỷ lệ trong từng hàng.",
        fontsize=8.6, color=MUTED, va="top")
ax.text(0, -0.30,
        "Độ nhạy " + dec(sens) + "% (bắt được " + vn(TP) + "/" + vn(TP + FN)
        + " tế bào ác tính) · Độ chính xác " + dec(prec)
        + "% (không có tế bào bình thường nào bị gọi nhầm)",
        fontsize=9, color=INK, fontweight="bold", va="top")

fig.suptitle("Ma trận nhầm lẫn ở cấp tế bào: 2 tế bào bị bỏ sót, 0 tế bào báo nhầm",
             fontsize=13, fontweight="bold", color=INK, x=0.012, ha="left", y=0.965)
fig.text(0.012, 0.90,
         "Mẫu 500.000 sự kiện với tỷ lệ ác tính 0,05% · "
         + vn(N) + " tế bào được phân loại sau gate QC",
         fontsize=9, color=MUTED, ha="left", va="top")

fig.savefig("fig_confusion.png", dpi=300, bbox_inches="tight", facecolor=SURFACE)
fig.savefig("fig_confusion.pdf", bbox_inches="tight", facecolor=SURFACE)
print("Da xuat: fig_confusion.png va .pdf")
print(f"  TP={TP} FN={FN} FP={FP} TN={vn(TN)}  do nhay {sens:.2f}%  do chinh xac {prec:.2f}%")
