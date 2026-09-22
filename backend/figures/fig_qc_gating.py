# -*- coding: utf-8 -*-
"""
fig_qc_gating.py
================
Ve "Hinh 3 - Gate QC theo tung buoc" cho bao cao NCKH AskCell.

Chay duoc o ca Google Colab lan may local, KHONG can file .fcs va KHONG can
cai flowkit: moi con so deu suy ra truc tiep tu logic trong app/flow/qc.py.

    python fig_qc_gating.py

Xuat ra: fig_qc_gating.png (300 DPI, chen vao Word) va fig_qc_gating.pdf.

VI SAO CON SO NAY DUNG
----------------------
Ca ba cong QC deu la CAT THEO PHAN VI, nen ty le loai bo la tat dinh chu khong
phai uoc luong:
    - manh vo   : giu fsc_a > quantile(fsc_a, 0.02)          -> loai dung 2%
    - dinh doi  : giu ratio trong [q(0.01), q(0.99)]         -> loai dung 2%
    - te bao chet: giu via <= quantile(via, 0.97)            -> loai dung 3%

Ba bien nay doc lap nhau theo dung cach make_mock_fcs.py sinh du lieu:
FSC-H = FSC-A * normal(0.94, 0.02) nen ty le FSC-H/FSC-A doc lap voi FSC-A;
con te bao chet duoc danh dau bang rng.random() < 0.03, doc lap hoan toan.

=> ty le giu lai = 0.98 x 0.98 x 0.97 = 93,159%

DOI CHIEU: benchmark.json ghi nhan pct_kept trung binh 93,16% qua 19 lan chay
thuc te (dao dong 93,15-93,18%). Suy luan KHOP voi so do that.

qc.py bao cao "removed" cua moi cong la so su kien TRUOT cong do VA da qua cac
cong truoc no, nen ba con so khong bang nhau du ty le cat la 2/2/3%.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --------------------------------------------------------------------------- #
# BANG MAU - dong bo voi fig_dataset.py de ca bo hinh doc nhu mot he thong
# --------------------------------------------------------------------------- #
BLUE    = "#2a78d6"   # su kien duoc giu lai (chu the cua hinh)
SLATE   = "#7f8c99"   # su kien bi loai (vai tro nen, 3.35:1 tren nen sang)
NEUTRAL = "#e1e0d9"   # duong luoi
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
    """Dinh dang so kieu Viet Nam: 55895 -> '55.895'."""
    return "{:,}".format(int(round(n))).replace(",", ".")


def dec(x, nd=2):
    """Dau thap phan kieu Viet Nam: 93.16 -> '93,16'."""
    return ("{:." + str(nd) + "f}").format(x).replace(".", ",")


# --------------------------------------------------------------------------- #
# SO LIEU - suy ra tu app/flow/qc.py (xem docstring)
# --------------------------------------------------------------------------- #
N0 = 60_000                              # so su kien mot mau thu thap
P_DEBRIS, P_DOUBLET, P_DEAD = 0.02, 0.02, 0.03

r_debris = round(N0 * P_DEBRIS)
after1 = N0 - r_debris
r_doublet = round(N0 * P_DOUBLET * (1 - P_DEBRIS))
after2 = after1 - r_doublet
r_dead = round(N0 * P_DEAD * (1 - P_DEBRIS) * (1 - P_DOUBLET))
after3 = after2 - r_dead

pct_kept = after3 / N0 * 100.0
total_removed = N0 - after3

# Cot cua bieu do thac nuoc: (nhan, chan cot, dinh cot, co phai cot tong khong)
STEPS = [
    ("Sự kiện\nthu thập",   0,      N0,     True),
    ("Loại\nmảnh vỡ",       after1, N0,     False),
    ("Loại\ndính đôi",      after2, after1, False),
    ("Loại\ntế bào chết",   after3, after2, False),
    ("Sự kiện\nphân tích",  0,      after3, True),
]

# Thanh phan phan bi loai
REMOVED = [
    ("Mảnh vỡ tế bào", r_debris),
    ("Tế bào dính đôi", r_doublet),
    ("Tế bào chết", r_dead),
]


# --------------------------------------------------------------------------- #
# BO CUC
# --------------------------------------------------------------------------- #
fig = plt.figure(figsize=(11.4, 5.0))
gs = fig.add_gridspec(1, 2, width_ratios=[1.55, 1.0], wspace=0.30,
                      left=0.065, right=0.975, top=0.775, bottom=0.145)
axA = fig.add_subplot(gs[0, 0])
axB = fig.add_subplot(gs[0, 1])


def panel_title(ax, letter, text, sub):
    ax.text(0, 1.115, letter + ". " + text, transform=ax.transAxes,
            fontsize=10.5, fontweight="bold", color=INK, va="bottom")
    ax.text(0, 1.035, sub, transform=ax.transAxes, fontsize=8,
            color=MUTED, va="bottom")


# --------------------------------------------------------------------------- #
# A - Bieu do thac nuoc
# --------------------------------------------------------------------------- #
BAR_W = 0.60
for i, (label, base, top, is_total) in enumerate(STEPS):
    axA.bar(i, top - base, bottom=base, width=BAR_W,
            color=BLUE if is_total else SLATE)

# Duong noi giua cac cot (net dut, mo)
levels = [N0, after1, after2, after3]
for i, lv in enumerate(levels):
    axA.plot([i + BAR_W / 2, i + 1 - BAR_W / 2], [lv, lv],
             color=MUTED, lw=1.0, ls=(0, (3, 3)), zorder=1)

# Nhan tren tung cot
for i, (label, base, top, is_total) in enumerate(STEPS):
    if is_total:
        axA.text(i, top + 1_400, vn(top), ha="center", va="bottom",
                 fontsize=11, fontweight="bold", color=BLUE)
    else:
        axA.text(i, top + 1_400, "−" + vn(top - base), ha="center", va="bottom",
                 fontsize=10, fontweight="bold", color=SLATE)

# Ty le % duoi cot cuoi
axA.text(4, after3 / 2, dec(pct_kept) + "%", ha="center", va="center",
         fontsize=11, fontweight="bold", color="white")
axA.text(0, N0 / 2, "100%", ha="center", va="center",
         fontsize=11, fontweight="bold", color="white")

axA.set_xticks(range(len(STEPS)))
axA.set_xticklabels([s[0] for s in STEPS], fontsize=8.6, linespacing=1.45)
axA.set_ylim(0, 70_000)
axA.set_yticks([0, 20_000, 40_000, 60_000])
axA.set_yticklabels(["0", "20k", "40k", "60k"], fontsize=8)
axA.set_ylabel("số sự kiện", fontsize=8.5, color=INK2)
axA.yaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axA.set_axisbelow(True)

from matplotlib.patches import Patch
axA.legend(handles=[
    Patch(facecolor=BLUE, label="Sự kiện được giữ lại"),
    Patch(facecolor=SLATE, label="Sự kiện bị loại"),
], loc="lower center", bbox_to_anchor=(0.5, 0.02), ncol=2,
    frameon=False, fontsize=8.5, handlelength=1.2, handleheight=1.2)

panel_title(axA, "A", "Ba cổng loại trừ, áp dụng tuần tự",
            "Trục tung giữ nguyên gốc 0 — phần bị loại thật sự nhỏ so với tổng")


# --------------------------------------------------------------------------- #
# B - Thanh phan phan bi loai (phong to)
# --------------------------------------------------------------------------- #
rn = [r[0] for r in REMOVED][::-1]
rv = [r[1] for r in REMOVED][::-1]

axB.barh(range(len(rv)), rv, height=0.58, color=SLATE)
axB.set_yticks(range(len(rn)))
axB.set_yticklabels(rn, fontsize=8.8)
axB.set_xlim(0, 2_600)
axB.set_xlabel("số sự kiện bị loại", fontsize=8.5, color=INK2)
axB.set_xticks([0, 500, 1_000, 1_500, 2_000])
axB.set_xticklabels(["0", "500", "1.000", "1.500", "2.000"], fontsize=8)
axB.xaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axB.set_axisbelow(True)

for i, v in enumerate(rv):
    axB.text(v + 60, i, vn(v) + "  (" + dec(v / N0 * 100) + "%)", va="center",
             fontsize=9, color=INK, fontweight="bold")

axB.text(0, -0.92, "Tổng loại bỏ " + vn(total_removed) + " sự kiện ("
         + dec(total_removed / N0 * 100) + "% số thu thập)",
         fontsize=8.6, color=INK2, fontweight="bold", va="center")

panel_title(axB, "B", "Mỗi cổng loại bỏ bao nhiêu",
            "Ba cổng cắt 2% / 2% / 3%, áp dụng lần lượt nên số tuyệt đối giảm dần")


# --------------------------------------------------------------------------- #
fig.suptitle("Gate QC: giữ lại tế bào nguyên vẹn, đơn lẻ và còn sống",
             fontsize=13, fontweight="bold", color=INK, x=0.012, ha="left", y=0.968)
fig.text(0.012, 0.905,
         "Một mẫu 60.000 sự kiện · tỷ lệ giữ lại đo được trên 19 lần chạy: "
         "93,16% (dao động 93,15–93,18%)",
         fontsize=8.5, color=MUTED, ha="left", va="top")

fig.savefig("fig_qc_gating.png", dpi=300, bbox_inches="tight", facecolor=SURFACE)
fig.savefig("fig_qc_gating.pdf", bbox_inches="tight", facecolor=SURFACE)
print("Da xuat: fig_qc_gating.png (300 DPI) va fig_qc_gating.pdf")
print(f"  {vn(N0)} -> {vn(after3)} su kien ({dec(pct_kept)}%)")
