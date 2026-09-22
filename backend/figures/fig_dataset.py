# -*- coding: utf-8 -*-
"""
fig_dataset.py
==============
Ve "Hinh 4 - Bieu do the hien bo du lieu AskCell" cho bao cao NCKH.

Chay duoc o ca Google Colab lan may local, KHONG can file .fcs:
moi con so duoi day la hang so lay truc tiep tu make_mock_fcs.py,
nen script tu chay doc lap.

    python fig_dataset.py

Xuat ra: fig_dataset.png (300 DPI, chen vao Word) va fig_dataset.pdf (vector).
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Patch

# --------------------------------------------------------------------------- #
# BANG MAU - da kiem dinh bang validator (dat moi tieu chi mu mau, nen sang)
# --------------------------------------------------------------------------- #
BLUE    = "#2a78d6"   # te bao binh thuong / khoi luong du lieu
AQUA    = "#1baf7a"   # hematogones - lanh tinh nhung de nham voi B-ALL
RED     = "#d03b3b"   # blast ac tinh (mau trang thai "critical")
CHIP_BG = "#cde2fb"   # nen chip dau an
CHIP_TX = "#0d366b"
NEUTRAL = "#e1e0d9"   # nen chip kenh phu tro / duong luoi
INK     = "#0b0b0b"   # chu chinh
INK2    = "#52514e"   # chu phu
MUTED   = "#898781"   # nhan truc
SURFACE = "#fcfcfb"   # nen bieu do

plt.rcParams.update({
    "font.family": "DejaVu Sans",   # co day du dau tieng Viet
    "font.size": 9,
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
    "axes.edgecolor": NEUTRAL,
    "axes.labelcolor": INK2,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": INK2,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def vn(n):
    """Dinh dang so kieu Viet Nam: 1200000 -> '1.200.000'."""
    return "{:,}".format(n).replace(",", ".")


def dec(x):
    """Dau thap phan kieu Viet Nam: 0.05 -> '0,05'."""
    return str(x).replace(".", ",")


# --------------------------------------------------------------------------- #
# DU LIEU - hang so tu make_mock_fcs.py
# --------------------------------------------------------------------------- #
# Thanh phan quan the trong mot mau tuy xuong khoe manh (% tong te bao co nhan)
POPULATIONS = [
    ("Bạch cầu hạt", 52.0),
    ("Lympho T", 15.0),
    ("Bạch cầu mono", 8.0),
    ("Hematogones", 8.0),            # <-- nhan vat chinh cua bai toan
    ("Dòng hồng cầu và khác", 7.0),
    ("Lympho B trưởng thành", 5.0),
    ("Tế bào NK", 3.0),
    ("Blast dòng tủy bình thường", 2.0),
]

# Cau truc bo du lieu: (ten, so event)
FILES = [
    ("20 mẫu khỏe mạnh\n(normal_bm_01..20)", 20 * 60_000),
    ("patient_overt.fcs", 60_000),
    ("patient_mrd.fcs", 400_000),
    ("patient_normal.fcs", 60_000),
]

# Ganh nang blast trong 3 mau kiem thu: (ten, so blast, %)
BURDEN = [
    ("patient_overt\n(bệnh bùng phát)", 15_000, 25.0),
    ("patient_mrd\n(tồn dư sau điều trị)", 200, 0.05),
    ("patient_normal\n(nhóm chứng khỏe mạnh)", 0, 0.0),
]

MIN_CLUSTER = 30   # DEFAULT_MIN_CLUSTER trong detect.py

MARKERS = ["CD45", "CD34", "CD19", "CD10", "CD20", "CD3", "CD5",
           "CD7", "CD13", "CD33", "CD117", "HLA-DR", "CD38"]
VIABILITY = ["Live/Dead"]
SCATTER = ["FSC-A", "FSC-H", "SSC-A"]


# --------------------------------------------------------------------------- #
# BO CUC
# --------------------------------------------------------------------------- #
fig = plt.figure(figsize=(12.6, 8.8))
gs = fig.add_gridspec(2, 2, hspace=0.55, wspace=0.42,
                      left=0.155, right=0.975, top=0.845, bottom=0.065)
axA = fig.add_subplot(gs[0, 0])
axB = fig.add_subplot(gs[0, 1])
axC = fig.add_subplot(gs[1, 0])
axD = fig.add_subplot(gs[1, 1])


def panel_title(ax, letter, text, sub):
    """Tieu de + phu de ve bang ax.text de kiem soat chinh xac khoang cach."""
    ax.text(0, 1.135, letter + ". " + text, transform=ax.transAxes,
            fontsize=10.5, fontweight="bold", color=INK, va="bottom")
    ax.text(0, 1.045, sub, transform=ax.transAxes, fontsize=8,
            color=MUTED, va="bottom")


# --------------------------------------------------------------------------- #
# A - Thanh phan quan the trong tuy xuong khoe manh
# --------------------------------------------------------------------------- #
names = [p[0] for p in POPULATIONS][::-1]
vals = [p[1] for p in POPULATIONS][::-1]
cols = [AQUA if n == "Hematogones" else BLUE for n in names]

axA.barh(range(len(vals)), vals, height=0.68, color=cols)
axA.set_yticks(range(len(vals)))
axA.set_yticklabels(names, fontsize=8.5)
axA.set_xlim(0, 62)
axA.set_xlabel("% tổng số tế bào có nhân", fontsize=8.5, color=INK2)
axA.xaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axA.set_axisbelow(True)

for i, v in enumerate(vals):
    axA.text(v + 1.2, i, dec(v).rstrip("0").rstrip(",") + "%", va="center",
             fontsize=8.5, color=INK, fontweight="bold")

# Chu giai mau - thay cho mui ten chu thich
axA.legend(handles=[
    Patch(facecolor=BLUE, label="Quần thể bình thường"),
    Patch(facecolor=AQUA, label="Hematogones — tế bào B non bình thường,\n"
                                "dễ nhầm với lymphoblast ác tính"),
], loc="lower right", frameon=False, fontsize=8, labelspacing=0.9,
    handlelength=1.1, handleheight=1.1, borderpad=0.9)

panel_title(axA, "A", "Thành phần một mẫu tủy xương khỏe mạnh",
            "8 quần thể tế bào, mô phỏng theo tỷ lệ trong tủy xương thật")


# --------------------------------------------------------------------------- #
# B - Cau truc bo du lieu
# --------------------------------------------------------------------------- #
fnames = [f[0] for f in FILES][::-1]
fvals = [f[1] for f in FILES][::-1]

axB.barh(range(len(fvals)), fvals, height=0.62, color=BLUE)
axB.set_yticks(range(len(fvals)))
axB.set_yticklabels(fnames, fontsize=8)
axB.set_xlim(0, 2_800_000)
axB.set_xlabel("số sự kiện thu thập được (mỗi sự kiện = 1 tế bào)",
               fontsize=8.5, color=INK2)
axB.xaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axB.set_axisbelow(True)
axB.set_xticks([0, 400_000, 800_000, 1_200_000])
axB.set_xticklabels(["0", "400k", "800k", "1,2tr"], fontsize=8)

for i, v in enumerate(fvals):
    if v >= 800_000:
        # Thanh du dai -> dat nhan BEN TRONG, chu trang, de danh cho nhan nhom
        axB.text(v - 35_000, i, vn(v), va="center", ha="right", fontsize=8.5,
                 color="white", fontweight="bold")
    else:
        axB.text(v + 40_000, i, vn(v), va="center", fontsize=8.5,
                 color=INK, fontweight="bold")

# Nhan nhom dat BEN TRONG vung ve, can phai - khong tran sang panel A
axB.text(2_760_000, 3, "TẬP THAM CHIẾU\ndựng đám mây “bình thường”\n+ hiệu chuẩn leave-one-out",
         fontsize=7.4, color=BLUE, fontweight="bold",
         va="center", ha="right", linespacing=1.45)
axB.text(2_760_000, 1, "TẬP KIỂM THỬ\nkhông tham gia\ndựng mô hình",
         fontsize=7.4, color=RED, fontweight="bold",
         va="center", ha="right", linespacing=1.45)
axB.axhline(2.5, color=NEUTRAL, lw=1.2, ls="--")

panel_title(axB, "B", "Cấu trúc bộ dữ liệu: 23 mẫu, 1.720.000 sự kiện",
            "Tập kiểm thử tách hoàn toàn khỏi tập dựng mô hình")


# --------------------------------------------------------------------------- #
# C - Ganh nang blast trong 3 mau kiem thu (thang log)
# --------------------------------------------------------------------------- #
bnames = [b[0] for b in BURDEN][::-1]
bcount = [b[1] for b in BURDEN][::-1]
bpct = [b[2] for b in BURDEN][::-1]

for i, (c, p) in enumerate(zip(bcount, bpct)):
    if c > 0:
        axC.barh(i, c, height=0.55, color=RED)
        axC.text(c * 1.4, i, vn(c) + " tế bào  (" + dec(p) + "%)",
                 va="center", fontsize=8.5, color=INK, fontweight="bold")
    else:
        # Dat sau duong ke min_cluster (x=30) de duong ke khong cat ngang chu
        axC.text(46, i, "0 tế bào ác tính — nhưng vẫn chứa hematogones",
                 va="center", fontsize=8.5, color=INK2, style="italic")

axC.set_xscale("log")
axC.set_xlim(1, 300_000)
axC.set_ylim(-1.30, 2.6)
axC.set_yticks(range(len(bnames)))
axC.set_yticklabels(bnames, fontsize=8)
axC.set_xlabel("số lymphoblast ác tính trong mẫu (thang logarit)",
               fontsize=8.5, color=INK2)
axC.xaxis.grid(True, color=NEUTRAL, linewidth=0.8)
axC.set_axisbelow(True)

# vlines (khong phai axvline): duong ke DUNG LAI truoc dong chu chu thich
axC.vlines(MIN_CLUSTER, -0.62, 2.55, color=INK2, lw=1.3, ls="--")
axC.text(MIN_CLUSTER, -0.78, "sàn " + str(MIN_CLUSTER) + " sự kiện — cụm nhỏ hơn bị xem là nhiễu",
         fontsize=7.8, color=INK2, va="top", ha="center", fontweight="bold")

panel_title(axC, "C", "Gánh nặng tế bào ác tính trong 3 mẫu kiểm thử",
            "Từ 25% xuống 0,05% — chênh 500 lần về tỷ lệ, 75 lần về số tế bào")


# --------------------------------------------------------------------------- #
# D - Bang mau 14 kenh (ban kiem ke, khong phai bieu do)
# --------------------------------------------------------------------------- #
axD.set_xlim(0, 10)
axD.set_ylim(0, 10)
axD.axis("off")


def chips(items, y, fill, txt, per_row=5, x0=0.1, w=1.95, h=0.78):
    for k, name in enumerate(items):
        r, c = divmod(k, per_row)
        x = x0 + c * w
        yy = y - r * (h + 0.28)
        axD.add_patch(FancyBboxPatch(
            (x, yy), w * 0.88, h,
            boxstyle="round,pad=0.02,rounding_size=0.14",
            facecolor=fill, edgecolor="none"))
        axD.text(x + w * 0.44, yy + h / 2, name, ha="center", va="center",
                 fontsize=8.2, color=txt, fontweight="bold")
    return y - ((len(items) - 1) // per_row) * (h + 0.28)


axD.text(0.1, 9.35, "13 DẤU ẤN KHÁNG NGUYÊN — dùng để so sánh kiểu hình",
         fontsize=8.2, color=INK2, fontweight="bold")
bottom = chips(MARKERS, 8.25, CHIP_BG, CHIP_TX)

axD.text(0.1, bottom - 1.05, "1 KÊNH SỐNG/CHẾT",
         fontsize=8.2, color=INK2, fontweight="bold")
chips(VIABILITY, bottom - 2.00, NEUTRAL, INK2, x0=0.1)

axD.text(4.35, bottom - 1.05, "3 KÊNH TÁN XẠ (dùng cho gate QC)",
         fontsize=8.2, color=INK2, fontweight="bold")
chips(SCATTER, bottom - 2.00, NEUTRAL, INK2, per_row=3, x0=4.35, w=1.85)

axD.text(0.1, bottom - 3.45,
         "Mỗi tế bào là một điểm trong không gian 13 chiều.\n"
         "Cả 23 mẫu dùng chung một bảng màu — cường độ dấu ấn không\n"
         "so sánh được giữa hai bảng màu khác nhau.",
         fontsize=8, color=MUTED, va="top", linespacing=1.6)

panel_title(axD, "D", "Bảng màu 14 kênh sàng lọc B-ALL",
            "Tái tạo đúng bảng màu dùng trong thực hành lâm sàng — 17 kênh đo")


# --------------------------------------------------------------------------- #
fig.suptitle("Bộ dữ liệu mô phỏng flow cytometry dùng trong AskCell",
             fontsize=13.5, fontweight="bold", color=INK, x=0.012, ha="left", y=0.982)
fig.text(0.012, 0.944,
         "23 mẫu .fcs từ bộ tạo dữ liệu mô phỏng (make_mock_fcs.py, seed 42 — "
         "tái lập được từng bit) · mỗi tế bào kèm nhãn đúng để chấm điểm",
         fontsize=8.5, color=MUTED, ha="left", va="top")

fig.savefig("fig_dataset.png", dpi=300, bbox_inches="tight", facecolor=SURFACE)
fig.savefig("fig_dataset.pdf", bbox_inches="tight", facecolor=SURFACE)
print("Da xuat: fig_dataset.png (300 DPI) va fig_dataset.pdf")
