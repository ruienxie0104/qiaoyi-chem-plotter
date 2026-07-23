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

# 用 session_state 儲存每個片段的生成結果
if "plot_results" not in st.session_state:
    st.session_state.plot_results = {}

# ============================================================
# 用 tabs 分頁減少同時渲染的 widget 數（記憶體優化）
# ============================================================
cat_names = list(categories.keys())
tabs = st.tabs(cat_names)

for tab, cat in zip(tabs, cat_names):
    items = categories[cat]

    for item in items:
        plot_id = item["id"]
        plot_name = item["name"]
        plot_desc = item["description"]
        needs = item["needs_files"]
        key_prefix = f"{plot_id}"

        with tab:
            with st.expander(f"{plot_id}  {plot_name}", expanded=False):
                st.caption(plot_desc)
                if plot_id == "B-08":
                    st.markdown("📁 **需要上傳 3 個檔案：SIFT-MS + 空品站×2**")
                else:
                    st.markdown(f"📁 **需要上傳 {needs} 個檔案**")

                # --- 上傳區 ---
                uploaded_files = []
                cols = st.columns(needs)
                for i in range(needs):
                    with cols[i]:
                        label = "SIFT-MS" if (plot_id == "B-08" and i == 0) else \
                                f"空品站 {i}" if plot_id == "B-08" else f"檔案 {i+1}"
                        f = st.file_uploader(
                            label,
                            type=["xlsx", "xls", "csv"],
                            key=f"file_{key_prefix}_{i}"
                        )
                        if f is not None:
                            uploaded_files.append(f)

                # B-06: 可選第二個檔案
                if plot_id == "B-06":
                    f2 = st.file_uploader(
                        "檔案 2（可選）",
                        type=["xlsx", "xls", "csv"],
                        key=f"file2_{key_prefix}"
                    )
                    if f2 is not None:
                        uploaded_files.append(f2)

                # B-07: 可選第二個檔案
                if plot_id == "B-07":
                    f2 = st.file_uploader(
                        "檔案 2（可選）",
                        type=["xlsx", "xls", "csv"],
                        key=f"file2_{key_prefix}"
                    )
                    if f2 is not None:
                        uploaded_files.append(f2)

                # --- 參數區 ---
                params = {}
                param_cols = st.columns([1, 1, 1])

                with param_cols[0]:
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

                    if plot_id == "A-09":
                        species_options_a09 = ["CO", "NMHC", "O3", "NO", "NO2", "PM2.5", "PM10"]
                        params["species"] = st.selectbox(
                            "選擇物種", species_options_a09, index=0,
                            key=f"species_{key_prefix}"
                        )
                        y_max_a09 = st.number_input(
                            "Y軸上限（0=預設）", value=0.0, step=0.1,
                            key=f"ymax_a09_{key_prefix}"
                        )
                        if y_max_a09 > 0:
                            params["y_max"] = y_max_a09

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
                    if plot_id == "A-09":
                        y_tick_a09 = st.number_input(
                            "Y軸刻度間距（0=預設）", value=0.0, step=0.1,
                            key=f"ytick_a09_{key_prefix}"
                        )
                        if y_tick_a09 > 0:
                            params["y_tick"] = y_tick_a09
                    if plot_id in ("B-06", "B-07"):
                        y_tick_b06 = st.number_input(
                            "Y軸刻度間距（0=預設）", value=0.0, step=0.1,
                            key=f"ytick_b06_{key_prefix}"
                        )
                        if y_tick_b06 > 0:
                            params["y_tick"] = y_tick_b06
                with param_cols2[1]:
                    scale = st.slider(
                        "圖表縮放", min_value=0.8, max_value=2.0, value=1.4, step=0.1,
                        key=f"scale_{key_prefix}"
                    )
                    params["scale"] = scale
                with param_cols2[2]:
                    if plot_id in ("B-06", "B-07"):
                        species_options = [
                            "1,3-butadiene", "acetaldehyde", "benzene", "formaldehyde",
                            "isoprene", "MACR", "MEK", "MVK", "toluene", "total_monoterpene",
                            "PM2.5", "PM10", "CO", "O3", "NO", "NO2", "NMHC"
                        ]
                        params["species"] = st.selectbox(
                            "物種", species_options, index=4,
                            key=f"species_{key_prefix}"
                        )
                        y_max_b06 = st.number_input(
                            "Y軸上限（0=預設）", value=0.0, step=0.1,
                            key=f"ymax_b06_{key_prefix}"
                        )
                        if y_max_b06 > 0:
                            params["y_max"] = y_max_b06
                    if plot_id == "B-07":
                        params["remove_anthro"] = st.checkbox(
                            "排除人為源異常值（3σ 篩選）",
                            value=False,
                            help="依月份計算 1,3-butadiene、toluene、benzene、CO、NMHC 的平均值±3σ，超出的整列排除"
                        )
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
                        st.info("📋 B-01 會自動讀取所有工作表，每個 sheet 視為一個物種")

                # --- 生成按鈕 ---
                btn_label = "📥 合併並篩選" if plot_id == "B-08" else "🎨 生成圖表"
                btn_clicked = st.button(
                    btn_label,
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
                                        file_bytes = f.getvalue()
                                        sheet = params.get("sheet_name", None)
                                        try:
                                            if sheet:
                                                df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, engine="openpyxl")
                                            else:
                                                df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
                                        except Exception as excel_err:
                                            try:
                                                df = pd.read_excel(io.BytesIO(file_bytes), engine="xlrd")
                                            except Exception:
                                                try:
                                                    df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8", sep=None, engine="python")
                                                except Exception:
                                                    try:
                                                        df = pd.read_csv(io.BytesIO(file_bytes), encoding="big5", sep=None, engine="python")
                                                    except Exception:
                                                        raise ValueError(f"無法讀取檔案 {f.name}：{excel_err}")
                                    dfs.append(df)

                                # B-01: 讀取所有 sheet，傳給函數
                                if plot_id == "B-01":
                                    try:
                                        all_sheets = pd.read_excel(io.BytesIO(uploaded_files[0].getvalue()), sheet_name=None, engine="openpyxl")
                                        params["all_sheets"] = all_sheets
                                    except Exception:
                                        params["all_sheets"] = None

                                plot_info = get_plot_by_id(plot_id)
                                result = plot_info["func"](dfs, params)

                                if isinstance(result, tuple):
                                    fig, excel_bytes = result
                                    st.session_state[result_key] = ("fig_excel", fig, excel_bytes)
                                else:
                                    fig = result
                                    st.session_state[result_key] = ("fig", fig)

                                if plot_id == "B-08":
                                    st.success("✅ 合併並篩選完成！可下載 Excel 檔案。")
                                else:
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