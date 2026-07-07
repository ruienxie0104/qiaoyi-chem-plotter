import streamlit as st
import pandas as pd
import io
import matplotlib
matplotlib.use("Agg")

from plot_modules import get_registry, get_plot_by_id

# ============================================================
# 頁面設定
# ============================================================
st.set_page_config(
    page_title="鳳凰谷化學繪圖平台",
    page_icon="📊",
    layout="wide",
)

st.title("📊 鳳凰谷化學繪圖平台")
st.markdown("---")

# ============================================================
# 取得片段列表
# ============================================================
registry = get_registry()
categories = {}
for item in registry:
    cat = item["category"]
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(item)

# ============================================================
# 側邊欄：選擇片段
# ============================================================
st.sidebar.title("🔧 選擇圖表")

# 按分類列出
all_ids = []
for cat, items in categories.items():
    st.sidebar.markdown(f"### {cat}")
    for item in items:
        label = f"{item['id']}  {item['name']}"
        all_ids.append(label)

selected_label = st.sidebar.radio("選擇繪圖片段", all_ids)

# 解析選擇
selected_id = selected_label.split("  ")[0].strip()
plot_info = get_plot_by_id(selected_id)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**編號：** {plot_info['id']}")
st.sidebar.markdown(f"**名稱：** {plot_info['name']}")
st.sidebar.markdown(f"**分類：** {plot_info['category']}")
st.sidebar.markdown(f"**說明：** {plot_info['description']}")
st.sidebar.markdown(f"**需要檔案數：** {plot_info['needs_files']}")

# ============================================================
# 主區域：上傳檔案 + 參數 + 生成
# ============================================================
st.header(f"{plot_info['id']} — {plot_info['name']}")

col1, col2 = st.columns([2, 1])

with col1:
    needs = plot_info["needs_files"]
    uploaded_files = []
    for i in range(needs):
        f = st.file_uploader(
            f"上傳 Excel 檔案 {i+1}",
            type=["xlsx", "xls", "csv"],
            key=f"file_{plot_info['id']}_{i}"
        )
        if f is not None:
            uploaded_files.append(f)

with col2:
    st.subheader("參數設定")
    params = {}

    # 日期範圍（A 系列用）
    if plot_info["category"] == "空氣品質" or plot_info["id"] == "B-05":
        col_a, col_b = st.columns(2)
        with col_a:
            start_date = st.date_input("開始日期", value=pd.to_datetime("2025-05-01"))
            params["start_date"] = pd.to_datetime(start_date)
        with col_b:
            end_date = st.date_input("結束日期", value=pd.to_datetime("2026-05-31"))
            params["end_date"] = pd.to_datetime(end_date)

    # y 軸設定（A 系列）
    if plot_info["category"] == "空氣品質" and plot_info["id"] != "A-09":
        y_max = st.number_input("Y軸上限（留空=自動）", value=0.0, step=0.1, help="設為 0 表示使用預設值")
        if y_max > 0:
            params["y_max"] = y_max
        y_tick = st.number_input("Y軸刻度間距", value=0.0, step=0.1, help="設為 0 表示使用預設值")
        if y_tick > 0:
            params["y_tick"] = y_tick

    # SCALE
    scale = st.slider("圖表縮放比例", min_value=0.8, max_value=2.0, value=1.4, step=0.1)
    params["scale"] = scale

    # B-06: 物種選擇
    if plot_info["id"] == "B-06":
        species_options = [
            "1,3-butadiene", "acetaldehyde", "benzene", "formaldehyde",
            "isoprene", "MACR", "MEK", "MVK", "toluene", "total_monoterpene",
            "PM2.5", "PM10", "CO", "O3", "NO", "NO2", "NMHC"
        ]
        params["species"] = st.selectbox("選擇物種", species_options, index=13)

    # B-01: sheet 名稱提示
    if plot_info["id"] == "B-01":
        params["sheet_name"] = st.text_input("工作表名稱（含「線性」「回收」或「RSD」）", value="")

# ============================================================
# 生成按鈕
# ============================================================
st.markdown("---")

if st.button("🎨 生成圖表", type="primary"):
    if len(uploaded_files) < needs:
        st.warning(f"請上傳 {needs} 個檔案（目前已上傳 {len(uploaded_files)} 個）")
    else:
        with st.spinner("處理中..."):
            try:
                # 讀取檔案
                dfs = []
                for f in uploaded_files:
                    if f.name.endswith(".csv"):
                        # 嘗試不同編碼
                        try:
                            df = pd.read_csv(f, encoding="utf-8")
                        except UnicodeDecodeError:
                            f.seek(0)
                            try:
                                df = pd.read_csv(f, encoding="big5")
                            except UnicodeDecodeError:
                                f.seek(0)
                                df = pd.read_csv(f, encoding="cp950")
                    else:
                        df = pd.read_excel(f, engine="openpyxl")
                    dfs.append(df)

                # 執行繪圖
                result = plot_info["func"](dfs, params)

                # 處理回傳（可能是 fig, 或 fig + excel_bytes）
                if isinstance(result, tuple):
                    fig, excel_bytes = result
                    st.pyplot(fig)
                    st.download_button(
                        label="📥 下載統計表 Excel",
                        data=excel_bytes,
                        file_name=f"{plot_info['id']}_統計表.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    fig = result
                    st.pyplot(fig)

                # 下載圖片
                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
                buf.seek(0)
                st.download_button(
                    label="📥 下載圖片 PNG",
                    data=buf,
                    file_name=f"{plot_info['id']}_{plot_info['name']}.png",
                    mime="image/png"
                )

                st.success("✅ 圖表生成完成！")

            except Exception as e:
                st.error(f"❌ 生成失敗：{str(e)}")
                st.markdown("**除錯資訊：**")
                st.code(f"片段編號: {plot_info['id']}\n錯誤: {repr(e)}")

# ============================================================
# 底部：片段列表總覽
# ============================================================
st.markdown("---")
st.markdown("## 📋 所有片段列表")

for cat, items in categories.items():
    with st.expander(f"{cat}（{len(items)} 個片段）"):
        for item in items:
            st.markdown(f"**{item['id']}** — {item['name']}")
            st.markdown(f"　{item['description']}")
            st.markdown("")