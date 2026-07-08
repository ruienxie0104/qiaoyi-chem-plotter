"""
繪圖片段模組 — 每個 function 對應一個編號 + 名稱
所有 function 接收 (dfs, params) 並回傳 matplotlib Figure

dfs: list[pd.DataFrame] — 上傳的 Excel 檔案列表（每個檔案一個 DataFrame）
params: dict — 可調參數（時間範圍、y軸等）
"""

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.transforms as mtransforms
from matplotlib.lines import Line2D
import seaborn as sns
from pathlib import Path

# ============================================================
# 共用工具函數
# ============================================================

def _norm_colname(s: str) -> str:
    return str(s).strip().lower().replace(" ", "").replace("_", "").replace(".", "")

def resolve_value_col(df: pd.DataFrame, preferred: str) -> str:
    """支援欄位名稱變體"""
    if preferred in df.columns:
        return preferred
    target = _norm_colname(preferred)
    norm_map = {_norm_colname(c): c for c in df.columns}
    if target in norm_map:
        return norm_map[target]
    candidates = []
    for c in df.columns:
        nc = _norm_colname(c)
        if target in ["nmhc", "nonmethanehydrocarbons", "nonmethanehc"]:
            if ("nmhc" in nc) or ("非甲烷" in str(c)):
                candidates.append(c)
            continue
        if target == "co":
            if (nc == "co") or nc.startswith("co(") or nc.startswith("co[") or ("一氧化碳" in str(c)):
                candidates.append(c)
            continue
        if target in ["pm2.5", "pm25", "pm2_5"]:
            if ("pm25" in nc) or ("pm2.5" in nc) or ("pm2_5" in nc) or ("細懸浮微粒" in str(c)):
                candidates.append(c)
            continue
        if target == "pm10":
            if nc == "pm10" or nc.startswith("pm10(") or ("懸浮微粒" in str(c) and "pm2" not in nc):
                candidates.append(c)
            continue
        if target == "no2":
            if ("二氧化氮" in str(c)) or (nc == "no2") or nc.startswith("no2("):
                if "nox" not in nc:
                    candidates.append(c)
            continue
        if target == "no":
            if (nc == "no") or nc.startswith("no(") or ("一氧化氮" in str(c)):
                if "no2" not in nc and "nox" not in nc:
                    candidates.append(c)
            continue
        if target == "o3":
            if (nc == "o3") or nc.startswith("o3(") or ("臭氧" in str(c)):
                candidates.append(c)
            continue
        if target == nc:
            candidates.append(c)
    if candidates:
        return sorted(set(candidates), key=lambda x: (len(str(x)), str(x)))[0]
    raise KeyError(f"找不到欄位：'{preferred}'。檔案欄位有：{list(df.columns)}")

def read_excel_dfs(dfs: list[pd.DataFrame], time_col: str, value_col: str) -> pd.DataFrame:
    """合併多個 DataFrame，去重、排序"""
    processed = []
    for d in dfs:
        d = d.copy()
        if time_col not in d.columns:
            # 嘗試模糊匹配
            for c in d.columns:
                if "時間" in str(c) or "time" in str(c).lower():
                    d = d.rename(columns={c: time_col})
                    break
        d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
        real_col = resolve_value_col(d, value_col)
        d[real_col] = pd.to_numeric(d[real_col], errors="coerce")
        d = d[[time_col, real_col]].rename(columns={real_col: value_col})
        processed.append(d)
    df = (pd.concat(processed, ignore_index=True)
          .dropna(subset=[time_col])
          .drop_duplicates(subset=[time_col], keep="last")
          .sort_values(time_col)
          .reset_index(drop=True))
    return df

def month_to_season(m):
    if m in [3, 4, 5]: return "春"
    elif m in [6, 7, 8]: return "夏"
    elif m in [9, 10, 11]: return "秋"
    else: return "冬"

# ============================================================
# 片段登錄表 — 每個片段的 metadata
# ============================================================

PLOT_REGISTRY = []
PALETTE = sns.color_palette("Set2")
SEASON_COLORS = {"春": PALETTE[0], "夏": PALETTE[1], "秋": PALETTE[2], "冬": PALETTE[3]}

def register(id: str, name: str, category: str, description: str, func, needs_files: int = 2):
    PLOT_REGISTRY.append({
        "id": id,
        "name": name,
        "category": category,
        "description": description,
        "func": func,
        "needs_files": needs_files,
    })

# ============================================================
# A 系列：空氣品質逐時濃度圖
# ============================================================

def _plot_hourly_trend(dfs, params, value_col, ylabel, y_max_fixed, y_tick_step, y_min_max, title_prefix):
    """共用逐時濃度圖邏輯"""
    TIME_COL = "時間"
    SCALE = params.get("scale", 1.4)
    start_date = pd.to_datetime(params.get("start_date", "2025-05-01"))
    end_date = pd.to_datetime(params.get("end_date", "2026-05-11 23:59:59"))
    y_max_fixed = params.get("y_max", y_max_fixed)
    y_tick_step = params.get("y_tick", y_tick_step)

    matplotlib.rcParams['font.family'] = ['Microsoft JhengHei', 'DejaVu Sans', 'Arial Unicode MS']
    matplotlib.rcParams['axes.unicode_minus'] = False

    BASE = 16 * SCALE
    TITLE_FS = 24 * SCALE
    LABEL_FS = 18 * SCALE
    TICK_FS = 14 * SCALE
    LEGEND_FS = 13 * SCALE
    MEAN_FS = 13 * SCALE
    MAX_FS = 13 * SCALE
    matplotlib.rcParams['font.size'] = BASE

    palette = PALETTE

    df = read_excel_dfs(dfs, TIME_COL, value_col)
    df_period = df[(df[TIME_COL] >= start_date) & (df[TIME_COL] <= end_date)].copy()
    df_period.loc[df_period[value_col] < 0, value_col] = np.nan

    val_mean = df_period[value_col].mean(skipna=True)
    df_period["Month"] = df_period[TIME_COL].dt.to_period("M")
    unique_months = sorted(df_period["Month"].dropna().unique())

    if y_max_fixed is None:
        q = df_period[value_col].quantile(0.995)
        if pd.isna(q) or q <= 0:
            Y_MAX = y_min_max
        else:
            Y_MAX = float(np.ceil((q * 1.20) / 0.1) * 0.1)
            Y_MAX = max(Y_MAX, y_min_max)
    else:
        Y_MAX = float(y_max_fixed)

    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.22, top=0.82)
    TEXT_BBOX = dict(facecolor="white", alpha=0.80, edgecolor="none", pad=1.2 * SCALE)

    pad_left = pd.Timedelta(days=10)
    pad_right = pd.Timedelta(days=35)
    ax.set_xlim(start_date - pad_left, end_date + pad_right)
    ax.set_ylim(0, Y_MAX)
    ax.set_yticks(np.arange(0, Y_MAX + 1e-9, y_tick_step))

    for month in unique_months:
        ms = month.to_timestamp()
        me = (month + 1).to_timestamp() - pd.Timedelta(seconds=1)
        mdata = df_period[(df_period[TIME_COL] >= ms) & (df_period[TIME_COL] <= me)].sort_values(TIME_COL)
        if mdata[value_col].dropna().empty:
            continue
        c = SEASON_COLORS.get(month_to_season(month.month), "gray")
        ax.plot(mdata[TIME_COL], mdata[value_col],
                marker="o", linestyle="-", markersize=3.5 * SCALE,
                linewidth=1.3 * SCALE, color=c, zorder=4)

    # Monthly mean
    monthly_stats = df_period.groupby("Month", dropna=True, as_index=False)[value_col].mean()
    for _, row in monthly_stats.iterrows():
        if pd.isna(row[value_col]):
            continue
        ms = row["Month"].to_timestamp()
        me = (row["Month"] + 1).to_timestamp() - pd.Timedelta(seconds=1)
        mid = ms + (me - ms) / 2
        ax.hlines(row[value_col], ms, me, colors="#800080", linestyles="--",
                  alpha=0.75, linewidth=1.4 * SCALE, zorder=5)
        fmt = f"{row[value_col]:.2f}" if Y_MAX < 5 else f"{row[value_col]:.1f}"
        ax.text(mid, min(row[value_col] + 0.10 * Y_MAX, Y_MAX - 0.12 * Y_MAX),
                fmt, color="#800080", fontsize=MEAN_FS, ha="center", fontweight="bold",
                bbox=TEXT_BBOX, zorder=10, clip_on=True)

    # Overall mean
    if not np.isnan(val_mean):
        ax.axhline(val_mean, color="green", linestyle="--", linewidth=1.8 * SCALE, zorder=3)
        fmt = f"{val_mean:.2f}" if Y_MAX < 5 else f"{val_mean:.1f}"
        ax.text(end_date - pd.Timedelta(days=5),
                min(val_mean + 0.10 * Y_MAX, Y_MAX - 0.12 * Y_MAX),
                fmt, color="green", fontsize=MEAN_FS, ha="right", va="bottom", fontweight="bold",
                bbox=TEXT_BBOX, zorder=10, clip_on=True)

    # Legend 1
    legend_elements = [
        Line2D([0], [0], marker="D", linestyle="None", markeredgecolor="black",
               markerfacecolor="orange", markersize=8 * SCALE, label="Monthly maximum"),
        Line2D([0], [0], color="#800080", linestyle="--", linewidth=2 * SCALE, label="Monthly mean"),
        Line2D([0], [0], color="green", linestyle="--", linewidth=2 * SCALE, label="Overall mean"),
    ]
    legend1 = ax.legend(handles=legend_elements, loc="upper center", bbox_to_anchor=(0.5, 1.0),
                        ncol=3, frameon=False, fontsize=LEGEND_FS)
    ax.add_artist(legend1)

    # Legend 2: Seasons
    season_handles = [
        Line2D([0], [0], marker='o', linestyle='-', color=SEASON_COLORS["春"],
               markerfacecolor=SEASON_COLORS["春"], markersize=6*SCALE, linewidth=1.8*SCALE, label="Spring (3–5)"),
        Line2D([0], [0], marker='o', linestyle='-', color=SEASON_COLORS["夏"],
               markerfacecolor=SEASON_COLORS["夏"], markersize=6*SCALE, linewidth=1.8*SCALE, label="Summer (6–8)"),
        Line2D([0], [0], marker='o', linestyle='-', color=SEASON_COLORS["秋"],
               markerfacecolor=SEASON_COLORS["秋"], markersize=6*SCALE, linewidth=1.8*SCALE, label="Autumn (9–11)"),
        Line2D([0], [0], marker='o', linestyle='-', color=SEASON_COLORS["冬"],
               markerfacecolor=SEASON_COLORS["冬"], markersize=6*SCALE, linewidth=1.8*SCALE, label="Winter (12–2)"),
    ]
    ax.legend(handles=season_handles, loc="upper right", frameon=True, framealpha=0.85, fontsize=LEGEND_FS)

    # Monthly maxima
    monthly_max_points = []
    for month in unique_months:
        g = df_period[df_period["Month"] == month].dropna(subset=[value_col])
        if g.empty:
            continue
        idx = g[value_col].idxmax()
        monthly_max_points.append(df_period.loc[idx])
    monthly_max = (pd.DataFrame(monthly_max_points).sort_values(TIME_COL).reset_index(drop=True)
                   if monthly_max_points else pd.DataFrame())

    DEFAULT_OFFSET = {5: (0,15), 6: (-15,30), 7: (0,15), 8: (-45,15), 9: (-15,30),
                      10: (0,30), 11: (-45,7), 12: (-15,30), 1: (0,30), 2: (0,15),
                      3: (0,15), 4: (-15,15)}
    if not monthly_max.empty:
        for _, row in monthly_max.iterrows():
            x = row[TIME_COL]
            y = row[value_col]
            ax.plot(x, y, "D", color="orange", markersize=6*SCALE, markeredgecolor="black", zorder=6)
            fmt = f"{y:.2f}" if Y_MAX < 5 else f"{y:.1f}"
            label = f"{fmt}\n{x.strftime('%m/%d %H:%M')}"
            dx, dy = DEFAULT_OFFSET.get(x.month, (0, 15))
            ax.annotate(label, xy=(x, y), xycoords="data",
                        xytext=(dx * SCALE, dy * SCALE), textcoords="offset points",
                        ha="left", va="bottom", color="orange", fontsize=MAX_FS, fontweight="bold",
                        bbox=TEXT_BBOX,
                        arrowprops=dict(arrowstyle="-", color="orange", lw=1.0*SCALE, alpha=0.7,
                                        shrinkA=10*SCALE, shrinkB=3*SCALE),
                        zorder=10, clip_on=True)

    ax.set_title(f'{title_prefix} ({start_date.strftime("%Y/%m/%d")}–{end_date.strftime("%Y/%m/%d")})',
                 fontsize=TITLE_FS, fontweight='bold', pad=10)
    ax.set_xlabel('Time', fontsize=LABEL_FS)
    ax.set_ylabel(ylabel, fontsize=LABEL_FS, fontweight='bold')
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
    ax.tick_params(axis='both', which='major', labelsize=TICK_FS)
    plt.xticks(rotation=45)
    ax.grid(color='gray', alpha=0.25)

    return fig

# --- A-01: NMHC 逐時濃度圖 ---
def plot_a01_nmhc(dfs, params):
    return _plot_hourly_trend(dfs, params, "NMHC", "NMHC (ppmC)", 1.2, 0.2, 1.0, "Hourly NMHC Concentration")

register("A-01", "NMHC 逐時濃度圖", "空氣品質", "NMHC 小時值趨勢圖，含月均值、季節配色、月最大值標注", plot_a01_nmhc)

# --- A-02: CO 逐時濃度圖（全範圍）---
def plot_a02_co_full(dfs, params):
    return _plot_hourly_trend(dfs, params, "CO", "CO (ppmv)", 4.0, 1.0, 1.0, "Hourly CO Concentration")

register("A-02", "CO 逐時濃度圖（全範圍 0-4）", "空氣品質", "CO 小時值趨勢圖，y軸 0-4 ppmv", plot_a02_co_full)

# --- A-03: CO 逐時濃度圖（放大）---
def plot_a03_co_zoom(dfs, params):
    return _plot_hourly_trend(dfs, params, "CO", "CO (ppmv)", 1.0, 0.2, 1.0, "Hourly CO Concentration (Zoomed)")

register("A-03", "CO 逐時濃度圖（放大 0-1）", "空氣品質", "CO 小時值趨勢圖，y軸 0-1 ppmv 放大版", plot_a03_co_zoom)

# --- A-04: PM2.5 逐時濃度圖 ---
def plot_a04_pm25(dfs, params):
    return _plot_hourly_trend(dfs, params, "PM2.5", r"$PM_{2.5}$ ($\mu g/m^{3}$)", 80, 20.0, 40, r"Hourly $PM_{2.5}$ Concentration")

register("A-04", "PM2.5 逐時濃度圖", "空氣品質", "PM2.5 小時值趨勢圖，含月均值、季節配色、月最大值標注", plot_a04_pm25)

# --- A-05: PM10 逐時濃度圖 ---
def plot_a05_pm10(dfs, params):
    return _plot_hourly_trend(dfs, params, "PM10", r"$PM_{10}$ ($\mu g/m^3$)", 160, 40.0, 100, r"Hourly $PM_{10}$ Concentration")

register("A-05", "PM10 逐時濃度圖", "空氣品質", "PM10 小時值趨勢圖，含月均值、季節配色、月最大值標注", plot_a05_pm10)

# --- A-06: NO2 逐時濃度圖 ---
def plot_a06_no2(dfs, params):
    return _plot_hourly_trend(dfs, params, "NO2", r"$NO_{2}$ (ppbv)", 20, 5.0, 15, r"Hourly $NO_{2}$ Concentration")

register("A-06", "NO2 逐時濃度圖", "空氣品質", "NO2 小時值趨勢圖，含月均值、季節配色、月最大值標注", plot_a06_no2)

# --- A-07: O3 逐時濃度圖 ---
def plot_a07_o3(dfs, params):
    return _plot_hourly_trend(dfs, params, "O3", r"$O_{3}$ (ppbv)", 120, 30.0, 60, r"Hourly $O_{3}$ Concentration")

register("A-07", "O3 逐時濃度圖", "空氣品質", "O3 小時值趨勢圖，含月均值、季節配色、月最大值標注", plot_a07_o3)

# --- A-08: NO 逐時濃度圖 ---
def plot_a08_no(dfs, params):
    return _plot_hourly_trend(dfs, params, "NO", "NO (ppbv)", 25, 5.0, 15, "Hourly NO Concentration")

register("A-08", "NO 逐時濃度圖", "空氣品質", "NO 小時值趨勢圖", plot_a08_no)

# --- A-09: 七測項統一版趨勢圖 ---
def plot_a09_unified(dfs, params):
    """統一版趨勢圖 — 使用者選擇物種"""
    TIME_COL = "時間"
    SCALE = params.get("scale", 1.8)
    start_date = pd.to_datetime(params.get("start_date", "2025-05-01"))
    end_date = pd.to_datetime(params.get("end_date", "2026-05-31 23:59:59"))

    # 使用者選擇的物種
    selected_species = params.get("species", "CO")

    matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "DejaVu Sans", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    BASE = 18 * SCALE
    LABEL_FS = 20 * SCALE
    TICK_FS = 15 * SCALE
    LEGEND_FS = 18
    matplotlib.rcParams["font.size"] = BASE

    PLOT_ITEMS = {
        "CO": ("CO (ppmv)", 3.0, 1.0),
        "NMHC": ("NMHC (ppmC)", 1.0, 0.2),
        "O3": (r"$O_{3}$ (ppbv)", 120, 30),
        "NO": ("NO (ppbv)", 25, 5),
        "NO2": (r"$NO_{2}$ (ppbv)", 20, 5),
        "PM2.5": (r"$PM_{2.5}$ (μg/m³)", 50, 10),
        "PM10": (r"$PM_{10}$ (μg/m³)", 150, 30),
    }

    if selected_species not in PLOT_ITEMS:
        raise ValueError(f"不支援的物種：{selected_species}。可選：{list(PLOT_ITEMS.keys())}")

    ylabel, default_ymax, default_ytick = PLOT_ITEMS[selected_species]

    # 使用者自訂 Y 軸
    ymax = params.get("y_max", 0)
    if ymax and ymax > 0:
        default_ymax = ymax
    ytick = params.get("y_tick", 0)
    if ytick and ytick > 0:
        default_ytick = ytick

    MONTH_LABEL = {1:"J",2:"F",3:"M",4:"A",5:"M",6:"J",7:"J",8:"A",9:"S",10:"O",11:"N",12:"D"}
    season_colors = {"春": "#4F81BD", "夏": "#FF7F0E", "秋": "#2CA02C", "冬": "#D62728"}

    value_col = selected_species
    df = read_excel_dfs(dfs, TIME_COL, value_col)
    df_period = df[(df[TIME_COL] >= start_date) & (df[TIME_COL] <= end_date)].copy()
    df_period.loc[df_period[value_col] <= 0, value_col] = np.nan
    df_period["Month"] = df_period[TIME_COL].dt.to_period("M")
    unique_months = sorted(df_period["Month"].dropna().unique())

    month_start_idx = []
    month_labels = []
    first_year = None
    for (year, month), group in df_period.groupby([df_period[TIME_COL].dt.year, df_period[TIME_COL].dt.month]):
        month_start_idx.append(group[TIME_COL].iloc[0])
        if first_year != year:
            month_labels.append(f"{MONTH_LABEL[month]}\n{year}")
            first_year = year
        else:
            month_labels.append(MONTH_LABEL[month])

    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.22, top=0.78)
    ax.set_xlim(start_date - pd.Timedelta(days=10), end_date)
    ax.set_ylim(0, default_ymax)
    ax.set_yticks(np.arange(0, default_ymax + 1e-9, default_ytick))

    for month in unique_months:
        ms = month.to_timestamp()
        me = (month + 1).to_timestamp() - pd.Timedelta(seconds=1)
        mdata = df_period[(df_period[TIME_COL] >= ms) & (df_period[TIME_COL] <= me)].sort_values(TIME_COL)
        if mdata[value_col].dropna().empty:
            continue
        c = season_colors.get(month_to_season(month.month), "gray")
        ax.plot(mdata[TIME_COL], mdata[value_col], marker="o", linestyle="-",
                markersize=2.5, linewidth=1.0, color=c, markerfacecolor=c,
                markeredgecolor=c, alpha=0.85, zorder=4)

    season_handles = [
        Line2D([0],[0], marker="o", linestyle="-", color=season_colors["春"],
               markerfacecolor=season_colors["春"], markeredgecolor=season_colors["春"],
               markersize=6, linewidth=1.5, label="Spring (Mar–May)"),
        Line2D([0],[0], marker="o", linestyle="-", color=season_colors["夏"],
               markerfacecolor=season_colors["夏"], markeredgecolor=season_colors["夏"],
               markersize=6, linewidth=1.5, label="Summer (Jun–Aug)"),
        Line2D([0],[0], marker="o", linestyle="-", color=season_colors["秋"],
               markerfacecolor=season_colors["秋"], markeredgecolor=season_colors["秋"],
               markersize=6, linewidth=1.5, label="Autumn (Sep–Nov)"),
        Line2D([0],[0], marker="o", linestyle="-", color=season_colors["冬"],
               markerfacecolor=season_colors["冬"], markeredgecolor=season_colors["冬"],
               markersize=6, linewidth=1.5, label="Winter (Dec–Feb)"),
    ]
    ax.legend(handles=season_handles, loc="lower center", bbox_to_anchor=(0.5, 1.02),
              ncol=4, frameon=False, fontsize=LEGEND_FS, columnspacing=1.5, handlelength=2.0)
    ax.set_xlabel("Date", fontsize=LABEL_FS)
    ax.set_ylabel(ylabel, fontsize=LABEL_FS, fontweight="bold")
    ax.set_xticks(month_start_idx)
    ax.set_xticklabels(month_labels, fontsize=TICK_FS, linespacing=1.5)
    ax.tick_params(axis="x", pad=10)
    ax.tick_params(axis="y", labelsize=TICK_FS)
    ax.grid(color="gray", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return fig

register("A-09", "七測項統一版趨勢圖", "空氣品質", "CO/NMHC/O3/NO/NO2/PM2.5/PM10 統一版趨勢圖（只有季節配色線）", plot_a09_unified)

# ============================================================
# B 系列：儀器QC + 統計
# ============================================================

# --- B-01: 檢量盒鬚圖 ---
def plot_b01_calibration_boxplot(dfs, params):
    """檢量盒鬚圖（線性R²/回收率/%RSD）"""
    FIGSIZE = (12, 7)
    DPI = 300
    LABEL_FS = 24
    TICK_FS = 20
    COLORS = ["#1D4E89", "#4F81BD", "#6C8EBF", "#9DC3E6", "#B7C9E2"]

    matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "Arial", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["font.size"] = TICK_FS

    PLOT_SETTINGS = {
        "線性": {"ylabel": "Linearity (R²)", "xlabel": "Target Compounds", "ylim": (0.995, 1.0005), "qc_lines": [0.995]},
        "回收率": {"ylabel": "Recovery (%)", "xlabel": "Target Compounds", "ylim": (80, 120), "qc_lines": [85, 115]},
        "%RSD": {"ylabel": "RSD (%)", "xlabel": "Target Compounds", "ylim": (0, 10), "qc_lines": [10]},
    }

    df = dfs[0].copy()

    # 自動判斷圖類型
    sheet_name = params.get("sheet_name", "")
    plot_type = params.get("plot_type", "")  # 可從 UI 下拉選單指定
    if not plot_type:
        if "線性" in sheet_name:
            plot_type = "線性"
        elif "回收" in sheet_name:
            plot_type = "回收率"
        elif "RSD" in sheet_name or "rsd" in sheet_name:
            plot_type = "%RSD"
        else:
            # 嘗試從欄位判斷（更寬鬆的匹配）
            cols_norm = [_norm_colname(str(c)) for c in df.columns]
            if any("linearity" in c or "r2" in c or "r²" in c.lower() for c in cols_norm):
                plot_type = "線性"
            elif any("10ppb" in c or "15ppb" in c or "20ppb" in c or "25ppb" in c or "30ppb" in c for c in cols_norm):
                plot_type = "回收率"
            elif any("rsd" in c for c in cols_norm):
                plot_type = "%RSD"

    if plot_type is None:
        raise ValueError("無法判斷圖表類型，請在參數中選擇圖表類型")

    setting = PLOT_SETTINGS[plot_type]

    # 找物種欄位
    possible_cols = ["物種", "Species", "species", "Compound", "compound", "化合物"]
    species_col = None
    for col in possible_cols:
        if col in df.columns:
            species_col = col
            break
    if species_col is None:
        raise ValueError("找不到物種欄位")

    if plot_type == "線性":
        value_col = "Linearity"
        if value_col not in df.columns:
            candidates = [c for c in df.columns if "line" in str(c).lower() or "r2" in str(c).lower() or "r²" in str(c).lower()]
            if candidates:
                value_col = candidates[0]
            else:
                raise ValueError("找不到 Linearity 欄位")
        df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
        df = df.dropna(subset=[species_col, value_col])
        species_order = df[species_col].drop_duplicates().tolist()
        data_list = [df.loc[df[species_col] == sp, value_col].dropna() for sp in species_order]
    else:
        # 回收率/%RSD：找 10-30 ppb 濃度欄位（模糊匹配）
        conc_cols = []
        for target in ["10 ppb", "15 ppb", "20 ppb", "25 ppb", "30 ppb"]:
            tn = _norm_colname(target)
            for c in df.columns:
                if _norm_colname(c) == tn:
                    conc_cols.append(c)
                    break
        if not conc_cols:
            # 更寬鬆：找任何含 ppb 的欄位
            conc_cols = [c for c in df.columns if "ppb" in str(c).lower()]
            conc_cols = sorted(conc_cols)
        if not conc_cols:
            raise ValueError(f"找不到濃度欄位（10-30 ppb）。現有欄位：{list(df.columns)}")
        species_order = df[species_col].drop_duplicates().tolist()
        data_list = []
        for sp in species_order:
            sub_df = df[df[species_col] == sp]
            values = []
            for col in conc_cols:
                vals = pd.to_numeric(sub_df[col], errors="coerce").dropna()
                values.extend(vals.tolist())
            data_list.append(values)
        # 檢查是否有抓到資料
        total_points = sum(len(d) for d in data_list)
        if total_points == 0:
            raise ValueError(f"所有物種都沒有有效數值。濃度欄位：{conc_cols}，物種：{species_order}")

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    bp = ax.boxplot(data_list, tick_labels=species_order, patch_artist=True, widths=0.55,
                    showfliers=False, medianprops=dict(color="black", linewidth=2.4),
                    boxprops=dict(linewidth=2.0), whiskerprops=dict(linewidth=2.0), capprops=dict(linewidth=2.0))
    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(COLORS[i % len(COLORS)])
        patch.set_alpha(0.9)

    for line in setting["qc_lines"]:
        color = "#C00000" if plot_type == "線性" else "gray"
        ax.axhline(line, color=color, linestyle="--", linewidth=2.4, alpha=0.9)

    ax.set_ylabel(setting["ylabel"], fontsize=LABEL_FS, fontweight="bold", labelpad=14)
    ax.set_ylim(setting["ylim"])
    ax.set_xlabel(setting["xlabel"], fontsize=LABEL_FS, fontweight="bold", labelpad=18)
    ax.tick_params(axis="x", labelsize=TICK_FS, rotation=20, width=1.8, length=6)
    ax.tick_params(axis="y", labelsize=TICK_FS, width=1.8, length=6)
    ax.grid(axis="y", linestyle="--", linewidth=1.2, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.8)
    ax.spines["bottom"].set_linewidth(1.8)
    plt.tight_layout()

    return fig

register("B-01", "檢量盒鬚圖（線性/回收率/RSD）", "儀器QC",
        "依物種分組的盒鬚圖，自動判斷線性R²/回收率/%RSD，需要單一Excel檔（含物種欄位）", plot_b01_calibration_boxplot, needs_files=1)

# --- B-02: SIFT-MS 離子源強度圖 ---
def plot_b02_ion_source(dfs, params):
    """SIFT-MS 三個離子源強度 bar chart"""
    from matplotlib.ticker import MultipleLocator
    DPI = 300
    LABEL_FS = 24
    TICK_FS = 20
    TEXT_FS = 18
    QC_TEXT_FS = 16
    ION_COLORS = ["#8FB9E3", "#B7D3EE", "#D6E6F5"]
    QC_COLOR = "#B00000"

    matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "Arial", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["font.size"] = 18

    H3O_LIMIT = 1.5e6
    NO_LIMIT = 2.8e6
    O2_LIMIT = 2.8e6

    df = dfs[0].copy()
    date_col = None
    for c in df.columns:
        if "DATE" in str(c).upper() or "date" in str(c).lower() or "日期" in str(c):
            date_col = c
            break
    if date_col is None:
        raise ValueError("找不到日期欄位")

    # 找離子源欄位
    h3o_col = no_col = o2_col = None
    for c in df.columns:
        cl = str(c).lower()
        if "h3o" in cl or "19" in cl:
            h3o_col = c
        elif "no+" in cl or "30" in cl:
            no_col = c
        elif "o2+" in cl or "32" in cl:
            o2_col = c

    if not all([h3o_col, no_col, o2_col]):
        raise ValueError(f"找不到離子源欄位。現有欄位：{list(df.columns)}")

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    for col in [h3o_col, no_col, o2_col]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=[date_col]).copy()

    ion_labels = [r"H$_3$O$^+$", r"NO$^+$", r"O$_2^+$"]
    ion_cols = [h3o_col, no_col, o2_col]
    ion_limits = [H3O_LIMIT, NO_LIMIT, O2_LIMIT]
    ion_means = [df[col].mean() / 1e6 for col in ion_cols]
    ion_stds = [df[col].std(ddof=1) / 1e6 for col in ion_cols]
    ion_limits_million = [v / 1e6 for v in ion_limits]

    x = np.arange(len(ion_labels))
    fig, ax = plt.subplots(figsize=(10, 6), dpi=DPI)
    ax.bar(x, ion_means, yerr=ion_stds, capsize=6, color=ION_COLORS, edgecolor="black",
           linewidth=1.5, width=0.55, zorder=3,
           error_kw=dict(ecolor="black", elinewidth=1.6, capthick=1.6))

    for i, limit in enumerate(ion_limits_million):
        ax.hlines(y=limit, xmin=i-0.32, xmax=i+0.32, color=QC_COLOR, linestyle="--", linewidth=2.5, zorder=4)
        ax.text(i, limit-0.35, f"{limit:.1f}×10$^6$", ha="center", va="top",
                fontsize=QC_TEXT_FS, color=QC_COLOR, fontweight="bold")

    for i, (mean, std) in enumerate(zip(ion_means, ion_stds)):
        ax.text(i, mean+std+0.35, f"{mean:.2f} ± {std:.2f}", ha="center", va="bottom",
                fontsize=TEXT_FS, fontweight="bold")

    ax.set_ylabel("Ion Count Intensity (×10$^6$ cps)", fontsize=LABEL_FS, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(ion_labels, fontsize=TICK_FS)
    ax.set_xlabel("Reagent Ions", fontsize=LABEL_FS, fontweight="bold", labelpad=12)
    ax.set_ylim(0, 12)
    ax.yaxis.set_major_locator(MultipleLocator(2))
    ax.tick_params(axis="both", labelsize=TICK_FS, width=1.3, length=6)
    ax.grid(axis="y", linestyle="--", alpha=0.30, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.5)
    ax.spines["bottom"].set_linewidth(1.5)
    plt.tight_layout()

    return fig

register("B-02", "SIFT-MS 離子源強度圖", "儀器QC",
        "H3O+/NO+/O2+ 離子源強度 bar chart，含 QC 下限線", plot_b02_ion_source, needs_files=1)

# --- B-03: Ethylene 濃度查核圖 ---
def plot_b03_ethylene(dfs, params):
    """Ethylene 濃度查核 bar chart"""
    from matplotlib.ticker import MultipleLocator
    DPI = 300
    LABEL_FS = 24
    TICK_FS = 20
    LEGEND_FS = 18
    ETH_COLOR = "#9DC3E6"
    QC_COLOR = "#B00000"

    matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "Arial", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["font.size"] = 18

    ETHYLENE_TARGET = 100
    ETHYLENE_LOW = 95
    ETHYLENE_HIGH = 105

    df = dfs[0].copy()
    date_col = None
    eth_col = None
    for c in df.columns:
        if "DATE" in str(c).upper() or "date" in str(c).lower():
            date_col = c
        if "ethylene" in str(c).lower() or "ETHYLENE" in str(c):
            eth_col = c

    if not date_col:
        raise ValueError("找不到日期欄位")
    if not eth_col:
        raise ValueError("找不到 Ethylene 欄位")

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[eth_col] = pd.to_numeric(df[eth_col], errors="coerce")
    df = df.dropna(subset=[date_col]).copy()
    df = df.sort_values(date_col).reset_index(drop=True)
    plot_df = df[[date_col, eth_col]].dropna().copy().sort_values(date_col).reset_index(drop=True)

    if plot_df.empty:
        raise ValueError("Ethylene 欄位沒有可繪製的有效數據")

    x = np.arange(len(plot_df))
    fig, ax = plt.subplots(figsize=(10, 6), dpi=DPI)
    ax.axhspan(ETHYLENE_LOW, ETHYLENE_HIGH, color="#EAF4EA", alpha=0.60, zorder=0)
    ax.bar(x, plot_df[eth_col], color=ETH_COLOR, edgecolor="black", linewidth=1.1, width=0.65, zorder=3)
    ax.axhline(ETHYLENE_TARGET, color="black", linestyle="-", linewidth=2.0, label="Target = 100 ppbv", zorder=4)
    ax.axhline(ETHYLENE_LOW, color=QC_COLOR, linestyle="--", linewidth=2.3, label="Acceptance = 100 ± 5%", zorder=4)
    ax.axhline(ETHYLENE_HIGH, color=QC_COLOR, linestyle="--", linewidth=2.3, zorder=4)

    ax.set_ylabel("Ethylene (ppbv)", fontsize=LABEL_FS, fontweight="bold")
    ax.set_xlabel("Date", fontsize=LABEL_FS, fontweight="bold", labelpad=10)
    ax.set_ylim(90, 110)
    ax.yaxis.set_major_locator(MultipleLocator(5))

    tick_interval = params.get("eth_x_tick_interval", 4)
    tick_positions = list(range(0, len(plot_df), tick_interval))
    tick_labels = [plot_df.loc[p, date_col].strftime("%m/%d") for p in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=35, ha="right", rotation_mode="anchor", fontsize=16)
    ax.set_xlim(-0.7, len(plot_df) - 0.3)
    ax.tick_params(axis="y", labelsize=TICK_FS, width=1.3, length=6)
    ax.tick_params(axis="x", labelsize=16, width=1.3, length=6, pad=8)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, fontsize=LEGEND_FS, frameon=False,
              handlelength=2.3, columnspacing=1.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.5)
    ax.spines["bottom"].set_linewidth(1.5)
    plt.tight_layout()

    return fig

register("B-03", "Ethylene 濃度查核圖", "儀器QC",
        "Ethylene 濃度 bar chart，含 100±5% 合格範圍", plot_b03_ethylene, needs_files=1)

# --- B-04: 每月濃度統計表 ---
def plot_b04_monthly_stats(dfs, params):
    """每月濃度統計表 — 輸出 Excel"""
    TIME_COL = "Time"
    df = dfs[0].copy()

    # 找時間欄位
    for c in df.columns:
        if "time" in str(c).lower() or "時間" in str(c) or "date" in str(c).lower():
            TIME_COL = c
            break

    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
    df = df.dropna(subset=[TIME_COL]).copy()

    EXCLUDE_COLS = [TIME_COL, "Hour", "File", "ID", "Unnamed: 14", "測站"]
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    species_cols = [col for col in numeric_cols if col not in EXCLUDE_COLS]

    for col in species_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    hourly_df = (df[[TIME_COL] + species_cols].set_index(TIME_COL).sort_index()
                 .resample("1h").mean(numeric_only=True).reset_index())
    hourly_df["Month"] = hourly_df[TIME_COL].dt.to_period("M").astype(str)

    monthly_stats = hourly_df.groupby("Month")[species_cols].agg(["count", "max", "mean", "median"])
    monthly_stats.columns = [f"{sp}_{st}" for sp, st in monthly_stats.columns]
    monthly_stats = monthly_stats.reset_index()

    # 用 Excel 格式回傳（Streamlit 可下載）
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        monthly_stats.to_excel(writer, sheet_name="每月統計", index=False)
        hourly_df.to_excel(writer, sheet_name="逐時平均", index=False)
        # 整體統計
        overall = hourly_df[species_cols].agg(["count", "max", "mean", "median"]).T.reset_index()
        overall.columns = ["Species", "N", "Max", "Mean", "Median"]
        overall.to_excel(writer, sheet_name="整體統計", index=False)
    output.seek(0)

    # 也畫一個簡單的月份筆數圖
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(range(len(monthly_stats)), monthly_stats.iloc[:, 1].astype(int), color="#4F81BD")
    ax.set_xlabel("Month", fontsize=14)
    ax.set_ylabel("Count", fontsize=14)
    ax.set_title("Monthly Data Count", fontsize=16)
    ax.set_xticks(range(len(monthly_stats)))
    ax.set_xticklabels(monthly_stats["Month"], rotation=45, fontsize=10)
    plt.tight_layout()

    return fig, output

register("B-04", "每月濃度統計表", "統計",
        "逐時平均 → 每月 N/Max/Mean/Median 統計表，輸出 Excel + 筆數圖", plot_b04_monthly_stats, needs_files=1)

# --- B-05: O3 八小時平均趨勢圖 ---
def plot_b05_o3_8hr(dfs, params):
    """O3 八小時平均趨勢圖"""
    TIME_COL = "時間"
    SCALE = params.get("scale", 1.8)
    start_date = pd.to_datetime(params.get("start_date", "2025-05-01"))
    end_date = pd.to_datetime(params.get("end_date", "2026-05-31 23:59:59"))

    matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "DejaVu Sans", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    BASE = 18 * SCALE
    LABEL_FS = 20 * SCALE
    TICK_FS = 15 * SCALE
    LEGEND_FS = 18
    MEAN_FS = 15 * SCALE
    matplotlib.rcParams["font.size"] = BASE

    df = read_excel_dfs(dfs, TIME_COL, "O3")
    df_period = df[(df[TIME_COL] >= start_date) & (df[TIME_COL] <= end_date)].copy().sort_values(TIME_COL)
    df_period["O3"] = df_period["O3"].clip(lower=0)
    df_period["O3_8hr"] = df_period["O3"].rolling(window=8, min_periods=1).mean()

    MONTH_LABEL = {1:"J",2:"F",3:"M",4:"A",5:"M",6:"J",7:"J",8:"A",9:"S",10:"O",11:"N",12:"D"}
    month_start_idx = []
    month_labels = []
    first_year = None
    for (year, month), group in df_period.groupby([df_period[TIME_COL].dt.year, df_period[TIME_COL].dt.month]):
        tick_date = group[TIME_COL].iloc[0] + pd.Timedelta(days=5)
        month_start_idx.append(tick_date)
        if first_year != year:
            month_labels.append(f"{MONTH_LABEL[month]}\n{year}")
            first_year = year
        else:
            month_labels.append(MONTH_LABEL[month])

    STD = 60
    STD_COLOR = "#D62728"

    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.22, top=0.68)

    ax.plot(df_period[TIME_COL], df_period["O3_8hr"], color="black", linewidth=1.0, alpha=0.85, zorder=4,
            label=r"8-hr Avg $O_{3}$")
    ax.axhline(y=STD, color=STD_COLOR, linestyle="--", linewidth=1.5, zorder=3)
    ax.annotate("60", xy=(1.0, STD), xycoords=("axes fraction", "data"), xytext=(-8, 4),
                textcoords="offset points", ha="right", va="bottom", color=STD_COLOR,
                fontsize=MEAN_FS, fontweight="bold", clip_on=False, zorder=10)

    ax.set_xlabel("Date", fontsize=LABEL_FS)
    ax.set_ylabel(r"$O_{3}$ (ppbv)", fontsize=LABEL_FS, fontweight="bold")
    ax.set_xlim(start_date - pd.Timedelta(days=5), end_date)
    ax.set_ylim(0, 80)
    ax.set_xticks(month_start_idx)
    ax.set_xticklabels(month_labels, fontsize=TICK_FS, linespacing=1.5)
    ax.tick_params(axis="x", pad=10)
    ax.tick_params(axis="y", labelsize=TICK_FS)
    plt.setp(ax.get_xticklabels(), ha="center")
    ax.grid(color="gray", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    legend_handles = [
        Line2D([0],[0], color="black", linewidth=1.0, alpha=0.85, label=r"8hr Avg $O_{3}$"),
        Line2D([0],[0], color=STD_COLOR, linestyle="--", linewidth=1.5, label="60 ppb standard"),
    ]
    ax.legend(handles=legend_handles, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2,
              frameon=False, fontsize=LEGEND_FS, handlelength=1.8, handletextpad=0.5, columnspacing=1.5)

    return fig

register("B-05", "O3 八小時平均趨勢圖", "空氣品質",
        "O3 八小時 rolling average 趨勢圖，含 60 ppb 標準線", plot_b05_o3_8hr)

# --- B-06: 季節 Diurnal 比較圖 ---
def plot_b06_diurnal(dfs, params):
    """季節 Diurnal 比較圖"""
    SCALE = params.get("scale", 1.8)
    species = params.get("species", "O3")

    matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "DejaVu Sans", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    BASE = 18 * SCALE
    LABEL_FS = 20 * SCALE
    TICK_FS = 15 * SCALE
    LEGEND_FS = 18
    LINE_WIDTH = 2.0
    MARKER_SIZE = 7
    matplotlib.rcParams["font.size"] = BASE

    SEASON_ORDER = ["Spring 2025", "Summer 2025", "Autumn 2025", "Winter 2025-2026", "Spring 2026", "Summer 2026"]
    SEASON_COLORS = {
        "Spring 2025": "#AFCBE3", "Summer 2025": "#FF7F0E",
        "Autumn 2025": "#2CA02C", "Winter 2025-2026": "#D62728", "Spring 2026": "#1F77B4",
        "Summer 2026": "#9467BD"
    }
    SEASON_MARKERS = {
        "Spring 2025": "o", "Summer 2025": "s", "Autumn 2025": "^",
        "Winter 2025-2026": "D", "Spring 2026": "P", "Summer 2026": "X"
    }

    def assign_season(dt):
        y, m = dt.year, dt.month
        if y == 2025:
            if m in [3,4,5]: return "Spring 2025"
            elif m in [6,7,8]: return "Summer 2025"
            elif m in [9,10,11]: return "Autumn 2025"
            elif m in [12]: return "Winter 2025-2026"
        elif y == 2026:
            if m in [1,2]: return "Winter 2025-2026"
            elif m in [3,4,5]: return "Spring 2026"
            elif m in [6,7,8]: return "Summer 2026"
        return np.nan

    YLABEL_DICT = {
        "1,3-butadiene": "1,3-Butadiene (ppbv)", "acetaldehyde": "Acetaldehyde (ppbv)",
        "benzene": "Benzene (ppbv)", "formaldehyde": "Formaldehyde (ppbv)",
        "isoprene": "Isoprene (ppbv)", "MACR": "MACR (ppbv)", "MEK": "MEK (ppbv)",
        "MVK": "MVK (ppbv)", "toluene": "Toluene (ppbv)", "total_monoterpene": "Monoterpene (ppbv)",
        "PM2.5": r"$PM_{2.5}$ (μg/m³)", "PM10": r"$PM_{10}$ (μg/m³)",
        "CO": "CO (ppmv)", "O3": r"$O_{3}$ (ppbv)", "NO": "NO (ppbv)",
        "NO2": r"$NO_{2}$ (ppbv)", "NMHC": "NMHC (ppmC)"
    }
    YLIM_DICT = {
        "1,3-butadiene": (0, 0.05, 0.01), "acetaldehyde": (0, 8, 2.0),
        "benzene": (0, 0.6, 0.2), "formaldehyde": (0, 6, 2.0),
        "isoprene": (0, 2.5, 0.5), "MACR": (0, 1.2, 0.4),
        "MEK": (0, 1.6, 0.4), "MVK": (0, 1.2, 0.4),
        "toluene": (0, 5.0, 1.0), "total_monoterpene": (0, 1.5, 0.3),
        "PM2.5": (0, 30, 5), "PM10": (0, 60, 10),
        "CO": (0, 0.4, 0.1), "O3": (0, 80, 20),
        "NO": (0, 4, 1), "NO2": (0, 12, 3), "NMHC": (0, 0.06, 0.02)
    }

    # 處理 SIFT-MS 格式：第一行是標題，第二行才是欄位名
    raw_df = pd.concat([d.copy() for d in dfs], ignore_index=True)
    # 檢查是否為 SIFT-MS 格式（第一欄叫 'Analyte concentrations (ppb)' 之類）
    if any("analyte" in str(c).lower() for c in raw_df.columns):
        # 用第一行當 header
        new_header = raw_df.iloc[0].tolist()
        df = raw_df[1:].copy()
        df.columns = new_header
        df = df.reset_index(drop=True)
    else:
        df = raw_df

    # 找時間欄位
    time_col = None
    for c in df.columns:
        cl = str(c).lower()
        if "time" in cl or "date" in cl or "時間" in str(c) or "日期" in str(c):
            time_col = c
            break
    if time_col is None:
        raise ValueError(f"找不到時間欄位。現有欄位：{list(df.columns)}")

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col]).copy()

    # 找物種欄位
    target_norm = _norm_colname(species)
    sp_col = None
    for c in df.columns:
        if _norm_colname(c) == target_norm:
            sp_col = c
            break
    if sp_col is None:
        for c in df.columns:
            if target_norm in _norm_colname(c):
                sp_col = c
                break
    if sp_col is None:
        raise ValueError(f"找不到物種欄位：{species}。現有欄位：{list(df.columns)}")

    df[sp_col] = pd.to_numeric(df[sp_col], errors="coerce")
    df["hour"] = df[time_col].dt.hour
    df["season"] = df[time_col].apply(assign_season)
    df = df.dropna(subset=["season"]).copy()
    df["season"] = pd.Categorical(df["season"], categories=SEASON_ORDER, ordered=True)

    results = df.groupby(["season", "hour"], observed=True)[sp_col].agg(["mean", "std", "count"]).reset_index()
    results = results.sort_values(["season", "hour"])

    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.subplots_adjust(left=0.08, right=0.78, bottom=0.18, top=0.92)

    plot_seasons = [s for s in SEASON_ORDER if s in results["season"].dropna().astype(str).unique()]
    for season in plot_seasons:
        sub = results[results["season"].astype(str) == season].copy()
        if sub.empty or sub["mean"].dropna().empty:
            continue
        ax.errorbar(sub["hour"], sub["mean"], yerr=sub["std"],
                    marker=SEASON_MARKERS.get(season, "o"), markersize=MARKER_SIZE,
                    linewidth=LINE_WIDTH, elinewidth=1.2, capsize=3.5, capthick=1.2,
                    color=SEASON_COLORS.get(season, "black"), label=season, zorder=4)

    ax.set_xlabel("Hour of day", fontsize=LABEL_FS)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 2))
    ax.set_ylabel(YLABEL_DICT.get(species, species), fontsize=LABEL_FS, fontweight="bold")
    # Y軸自訂
    y_max_custom = params.get("y_max", 0)
    y_tick_custom = params.get("y_tick", 0)
    if y_max_custom and y_max_custom > 0:
        ax.set_ylim(0, y_max_custom)
        if y_tick_custom and y_tick_custom > 0:
            ax.set_yticks(np.arange(0, y_max_custom + y_tick_custom, y_tick_custom))
    elif species in YLIM_DICT:
        ymin, ymax, ytick = YLIM_DICT[species]
        ax.set_ylim(ymin, ymax)
        ax.set_yticks(np.arange(ymin, ymax + ytick, ytick))
    ax.tick_params(axis="both", which="major", labelsize=TICK_FS)
    ax.grid(True, color="gray", alpha=0.25)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.00), frameon=False,
              framealpha=0.9, fontsize=LEGEND_FS, borderpad=0.4, labelspacing=0.5)

    return fig

register("B-06", "季節 Diurnal 比較圖", "統計",
        "各季節小時均值±標準差比較圖，需指定物種名稱，可上傳1-2個檔案", plot_b06_diurnal, needs_files=1)

# --- B-07: 時間序列趨勢圖（均值±標準差）---
def plot_b07_timeseries(dfs, params):
    """時間序列趨勢圖 — X軸是完整日期時間，Y軸是濃度"""
    import matplotlib.dates as mdates

    SCALE = params.get("scale", 1.8)
    species = params.get("species", "isoprene")

    matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "DejaVu Sans", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    BASE = 18 * SCALE
    LABEL_FS = 20 * SCALE
    TICK_FS = 15 * SCALE
    LINE_WIDTH = 1.5
    MARKER_SIZE = 4
    matplotlib.rcParams["font.size"] = BASE

    YLABEL_DICT = {
        "1,3-butadiene": "1,3-Butadiene (ppbv)", "acetaldehyde": "Acetaldehyde (ppbv)",
        "benzene": "Benzene (ppbv)", "formaldehyde": "Formaldehyde (ppbv)",
        "isoprene": "Isoprene (ppbv)", "MACR": "MACR (ppbv)", "MEK": "MEK (ppbv)",
        "MVK": "MVK (ppbv)", "toluene": "Toluene (ppbv)", "total_monoterpene": "Monoterpene (ppbv)",
        "PM2.5": r"$PM_{2.5}$ (μg/m³)", "PM10": r"$PM_{10}$ (μg/m³)",
        "CO": "CO (ppmv)", "O3": r"$O_{3}$ (ppbv)", "NO": "NO (ppbv)",
        "NO2": r"$NO_{2}$ (ppbv)", "NMHC": "NMHC (ppmC)"
    }

    # 處理 SIFT-MS 格式
    raw_df = pd.concat([d.copy() for d in dfs], ignore_index=True)
    if any("analyte" in str(c).lower() for c in raw_df.columns):
        new_header = raw_df.iloc[0].tolist()
        df = raw_df[1:].copy()
        df.columns = new_header
        df = df.reset_index(drop=True)
    else:
        df = raw_df

    # 找時間欄位
    time_col = None
    for c in df.columns:
        cl = str(c).lower()
        if "time" in cl or "date" in cl or "時間" in str(c) or "日期" in str(c):
            time_col = c
            break
    if time_col is None:
        raise ValueError(f"找不到時間欄位。現有欄位：{list(df.columns)}")

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col]).copy()
    df = df.sort_values(time_col).reset_index(drop=True)

    # 找物種欄位
    target_norm = _norm_colname(species)
    sp_col = None
    for c in df.columns:
        if _norm_colname(c) == target_norm:
            sp_col = c
            break
    if sp_col is None:
        for c in df.columns:
            if target_norm in _norm_colname(c):
                sp_col = c
                break
    if sp_col is None:
        raise ValueError(f"找不到物種欄位：{species}。現有欄位：{list(df.columns)}")

    df[sp_col] = pd.to_numeric(df[sp_col], errors="coerce")
    df = df.dropna(subset=[time_col, sp_col]).copy()

    # 異常值篩選：依月份計算判定物種 mean±3σ，超出的整列排除
    remove_anthro = params.get("remove_anthro", False)
    ANTHRO_SPECIES = ["1,3-butadiene", "toluene", "benzene", "CO", "NMHC"]
    remove_biogenic = params.get("remove_biogenic", False)
    BIOGENIC_SPECIES = ["MVK", "MEK", "MACR", "total_monoterpene", "isoprene", "formaldehyde", "acetaldehyde"]

    if remove_anthro or remove_biogenic:
        df["_month"] = df[time_col].dt.to_period("M").astype(str)
        filter_species = []
        if remove_anthro:
            filter_species += ANTHRO_SPECIES
        if remove_biogenic:
            filter_species += BIOGENIC_SPECIES
        for sp in filter_species:
            sp_norm = _norm_colname(sp)
            col = None
            for c in df.columns:
                if _norm_colname(c) == sp_norm:
                    col = c
                    break
            if col is None:
                continue
            df[col] = pd.to_numeric(df[col], errors="coerce")
            for mon, grp in df.groupby("_month"):
                mu = grp[col].mean()
                sigma = grp[col].std()
                if pd.isna(mu) or pd.isna(sigma) or sigma == 0:
                    continue
                lower = mu - 3 * sigma
                upper = mu + 3 * sigma
                mask = (df["_month"] == mon) & ((df[col] < lower) | (df[col] > upper))
                df = df[~mask].copy()
        df = df.drop(columns=["_month"])
        df = df.dropna(subset=[time_col, sp_col]).copy()

    if df.empty:
        raise ValueError("沒有有效的數據（篩選後可能全部被排除）")

    # Y軸設定
    ylabel = YLABEL_DICT.get(species, species)
    y_max_custom = params.get("y_max", 0)
    y_tick_custom = params.get("y_tick", 0)

    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.22, top=0.92)

    # 缺值不連線：把 NaN 處插入 NaN 來中斷線條
    plot_df = df[[time_col, sp_col]].copy()
    plot_df = plot_df.sort_values(time_col).reset_index(drop=True)
    # 偵測大間隔（超過中位數間隔的 3 倍視為缺值）
    if len(plot_df) > 2:
        diffs = plot_df[time_col].diff().dt.total_seconds().dropna()
        median_gap = diffs.median()
        if median_gap and median_gap > 0:
            gap_threshold = median_gap * 3
            for i in range(1, len(plot_df)):
                gap = (plot_df[time_col].iloc[i] - plot_df[time_col].iloc[i-1]).total_seconds()
                if gap > gap_threshold:
                    # 在缺值處插入 NaN 行
                    nan_row = pd.DataFrame({time_col: pd.NaT, sp_col: np.nan}, index=[i - 0.5])
                    plot_df = pd.concat([plot_df.iloc[:i], nan_row, plot_df.iloc[i:]]).reset_index(drop=True)

    ax.plot(plot_df[time_col], plot_df[sp_col], marker="o", linestyle="-",
            markersize=MARKER_SIZE, linewidth=LINE_WIDTH, color="#1F77B4",
            alpha=0.8, zorder=4)

    ax.set_xlabel("Date & Time", fontsize=LABEL_FS)
    ax.set_ylabel(ylabel, fontsize=LABEL_FS, fontweight="bold")

    # Y軸
    if y_max_custom and y_max_custom > 0:
        ax.set_ylim(0, y_max_custom)
        if y_tick_custom and y_tick_custom > 0:
            ax.set_yticks(np.arange(0, y_max_custom + y_tick_custom, y_tick_custom))
    else:
        ymax_data = df[sp_col].max()
        ax.set_ylim(0, ymax_data * 1.15)

    # X軸格式
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d\n%H:%M"))
    ax.tick_params(axis="x", labelsize=TICK_FS, rotation=0)
    ax.tick_params(axis="y", labelsize=TICK_FS)
    ax.grid(True, color="gray", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return fig

register("B-07", "時間序列趨勢圖（均值±標準差）", "統計",
        "X軸為完整日期時間的濃度趨勢圖，需指定物種名稱，可上傳1-2個檔案", plot_b07_timeseries, needs_files=1)


# ============================================================
# 取得所有片段的 metadata（不含 func）
# ============================================================
def get_registry():
    return [{k: v for k, v in item.items() if k != "func"} for item in PLOT_REGISTRY]

def get_plot_by_id(plot_id: str):
    for item in PLOT_REGISTRY:
        if item["id"] == plot_id:
            return item
    return None