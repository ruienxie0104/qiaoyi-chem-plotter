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
st.markdown("上傳 Excel → 生成圖表。點展開對應的片段即可操作。")
st.markdown("---")

# ============================================================
# 取得片段列表，按分類分組
# ============================================================
registry = get_registry()
categories = {}
for item in registry:
    cat = item["category"]
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(item)

# ============================================================
# 每個片段一個 accordion（st.expander）
# ============================================================

# 用 session_state 儲存每個片段的生成結果
if "plot_results" not in st.session_state:
    st.session_state.plot_results = {}

for cat, items in categories.items():
    st.markdown(f"## {cat}")
    for item in items:
        plot_id = item["id"]
        plot_name = item["name"]
        plot_desc = item["description"]
        needs = item["needs_files"]
        key_prefix = f"{plot_id}"

        with st.expander(f"{plot_id}  {plot_name}", expanded=False):
            st.caption(plot_desc)
            st.markdown(f"📁 **需要上傳 {needs} 個檔案**")

            # --- 上傳區 ---
            uploaded_files = []
            cols = st.columns(needs)
            for i in range(needs):
                with cols[i]:
                    f = st.file_uploader(
                        f"檔案 {i+1}",
                        type=["xlsx", "xls", "csv"],
                        key=f"file_{key_prefix}_{i}"
                    )
                    if f is not None:
                        uploaded_files.append(f)

            # --- 參數區 ---
            params = {}
            param_cols = st.columns([1, 1, 1])

            with param_cols[0]:
                # 日期範圍（A 系列用 + B-05）
                if cat == "空氣品質" or plot_id == "B-05":
                    start_date = st.date_input(
                        "開始日期", value=pd.to_datetime("2025-05-01"),
                        key=f"start_{key_prefix}"
                    )
                    params["start_date"] = pd.to_datetime(start_date)

            with param_cols[1]:
                if cat == "空氣品質" or plot_id == "B-05":
                    end_date = st.date_input(
                        "結束日期", value=pd.to_datetime("2026-05-31"),
                        key=f"end_{key_prefix}"
                    )
                    params["end_date"] = pd.to_datetime(end_date)

            with param_cols[2]:
                if cat == "空氣品質" and plot_id != "A-09":
                    y_max = st.number_input(
                        "Y軸上限（0=預設）", value=0.0, step=0.1,
                        key=f"ymax_{key_prefix}"
                    )
                    if y_max > 0:
                        params["y_max"] = y_max

            # 第二行參數
            param_cols2 = st.columns([1, 1, 1])
            with param_cols2[0]:
                if cat == "空氣品質" and plot_id != "A-09":
                    y_tick = st.number_input(
                        "Y軸刻度間距（0=預設）", value=0.0, step=0.1,
                        key=f"ytick_{key_prefix}"
                    )
                    if y_tick > 0:
                        params["y_tick"] = y_tick
            with param_cols2[1]:
                scale = st.slider(
                    "圖表縮放", min_value=0.8, max_value=2.0, value=1.4, step=0.1,
                    key=f"scale_{key_prefix}"
                )
                params["scale"] = scale
            with param_cols2[2]:
                # B-06: 物種選擇
                if plot_id == "B-06":
                    species_options = [
                        "1,3-butadiene", "acetaldehyde", "benzene", "formaldehyde",
                        "isoprene", "MACR", "MEK", "MVK", "toluene", "total_monoterpene",
                        "PM2.5", "PM10", "CO", "O3", "NO", "NO2", "NMHC"
                    ]
                    params["species"] = st.selectbox(
                        "物種", species_options, index=13,
                        key=f"species_{key_prefix}"
                    )
                # B-01: 圖表類型選擇 + 工作表選擇
                if plot_id == "B-01":
                    plot_type_options = ["自動判斷", "線性 (Linearity R²)", "回收率 (Recovery %)", "%RSD"]
                    selected_type = st.selectbox(
                        "圖表類型",
                        plot_type_options,
                        index=0,
                        key=f"ptype_{key_prefix}"
                    )
                    type_map = {
                        "自動判斷": "",
                        "線性 (Linearity R²)": "線性",
                        "回收率 (Recovery %)": "回收率",
                        "%RSD": "%RSD"
                    }
                    params["plot_type"] = type_map.get(selected_type, "")
                    
                    # 工作表選擇
                    if uploaded_files:
                        try:
                            import io as _io
                            file_bytes = uploaded_files[0].getvalue()
                            xl = pd.ExcelFile(_io.BytesIO(file_bytes), engine="openpyxl")
                            sheet_names = xl.sheet_names
                            xl.close()
                            if len(sheet_names) > 1:
                                selected_sheet = st.selectbox(
                                    "選擇工作表",
                                    sheet_names,
                                    key=f"sheet_{key_prefix}"
                                )
                                params["sheet_name"] = selected_sheet
                        except Exception:
                            pass

            # --- 生成按鈕 ---
            btn_clicked = st.button(
                "🎨 生成圖表",
                key=f"btn_{key_prefix}",
                type="primary"
            )

            # --- 結果區 ---
            result_key = f"result_{key_prefix}"
            if btn_clicked:
                if len(uploaded_files) < needs:
                    st.warning(f"請上傳 {needs} 個檔案（目前已上傳 {len(uploaded_files)} 個）")
                else:
                    with st.spinner("處理中..."):
                        try:
                            # 讀取檔案
                            dfs = []
                            for f in uploaded_files:
                                if f.name.endswith(".csv"):
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
                                    # 如果有指定工作表，讀取該工作表
                                    sheet = params.get("sheet_name", None)
                                    if sheet:
                                        df = pd.read_excel(f, sheet_name=sheet, engine="openpyxl")
                                    else:
                                        df = pd.read_excel(f, engine="openpyxl")
                                dfs.append(df)

                            # 執行繪圖
                            plot_info = get_plot_by_id(plot_id)
                            result = plot_info["func"](dfs, params)

                            if isinstance(result, tuple):
                                fig, excel_bytes = result
                                st.session_state[result_key] = ("fig_excel", fig, excel_bytes)
                            else:
                                fig = result
                                st.session_state[result_key] = ("fig", fig)

                            st.success("✅ 圖表生成完成！")

                        except Exception as e:
                            st.error(f"❌ 生成失敗：{str(e)}")
                            st.code(f"片段編號: {plot_id}\n錯誤: {repr(e)}")

            # 顯示已存的結果
            if result_key in st.session_state:
                stored = st.session_state[result_key]
                if stored[0] == "fig":
                    fig = stored[1]
                    st.pyplot(fig)
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
                    buf.seek(0)
                    st.download_button(
                        label="📥 下載圖片 PNG",
                        data=buf,
                        file_name=f"{plot_id}_{plot_name}.png",
                        mime="image/png",
                        key=f"dl_{key_prefix}"
                    )
                elif stored[0] == "fig_excel":
                    fig, excel_bytes = stored[1], stored[2]
                    st.pyplot(fig)
                    dl_cols = st.columns(2)
                    with dl_cols[0]:
                        buf = io.BytesIO()
                        fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
                        buf.seek(0)
                        st.download_button(
                            label="📥 下載圖片 PNG",
                            data=buf,
                            file_name=f"{plot_id}_{plot_name}.png",
                            mime="image/png",
                            key=f"dl_png_{key_prefix}"
                        )
                    with dl_cols[1]:
                        st.download_button(
                            label="📥 下載統計表 Excel",
                            data=excel_bytes,
                            file_name=f"{plot_id}_統計表.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_xlsx_{key_prefix}"
                        )

        st.markdown("")  # 間距

st.markdown("---")
st.markdown("### 📝 使用說明")
st.markdown("""
1. 找到你要的圖表編號，點展開
2. 上傳 Excel/CSV 檔案
3. 調整參數（日期範圍、Y軸等，可留空用預設值）
4. 點「生成圖表」
5. 圖片下方可下載 PNG

**需要新增圖表或修改既有片段？** 跟 Rosia 說編號 + 需求即可。
""")