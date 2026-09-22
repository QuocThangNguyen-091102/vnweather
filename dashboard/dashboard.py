"""
dashboard.py - Bảng điều khiển dữ liệu thời tiết Việt Nam (Streamlit).

Chạy:  streamlit run dashboard/dashboard.py
Đọc trực tiếp từ SQL Server (schema dwh, mart, staging). Cấu hình kết nối lấy từ .env (xem .env.example).

Một bộ lọc dùng chung cho toàn bộ dashboard (thanh bên): Địa điểm và Khoảng năm.
Mỗi tab ghi rõ bộ lọc nào áp dụng cho nó và bộ lọc nào không.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:           # chạy được cả khi chưa `pip install -e .`
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from weather_platform import analytics, config  # noqa: E402
from weather_platform.db import connect, rows_to_frame  # noqa: E402

PALETTE = px.colors.qualitative.Set2
ALL_LABEL = "Tất cả địa điểm"
MODEL_LABELS = {
    "persistence": "Lặp lại ngày cuối",
    "clim": "Đường khí hậu",
    "clim_ar1": "Khí hậu + hiệu chỉnh AR(1)",
    "open-meteo": "Open-Meteo",
}
MODEL_HELP = {
    "Lặp lại ngày cuối": "Các ngày sau có nhiệt độ bằng ngày cuối cùng đã biết. Dùng làm mốc so sánh đơn giản nhất.",
    "Đường khí hậu": "Nhiệt độ điển hình theo mùa và xu hướng nhiều năm (hồi quy sin/cos). Không dùng thông tin của những ngày gần nhất.",
    "Khí hậu + hiệu chỉnh AR(1)": "Dự báo = đường khí hậu + phần sai lệch của ngày cuối, giảm dần theo thời gian (hệ số AR(1) ước lượng từ dữ liệu).",
    "Open-Meteo": "Dự báo do Open-Meteo công bố tại thời điểm lưu, dùng để đối chiếu với thực tế.",
}


def label(model: str) -> str:
    return MODEL_LABELS.get(model, model)


st.set_page_config(page_title="Dữ liệu thời tiết Việt Nam", page_icon="🌦️", layout="wide")
st.markdown(
    """
    <style>
    div[data-testid="stMetric"] { background: rgba(128,128,128,0.08); padding: 12px 16px; border-radius: 10px; }
    div[data-testid="stMetricValue"] { font-size: 1.7rem; }
    div[data-testid="stMetricLabel"] p { white-space: normal; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Truy vấn
# ----------------------------------------------------------------------------
SQL_DAILY = """
    SELECT l.location_name, d.full_date, d.year_num, d.month_num,
           f.temp_max_c, f.temp_min_c, f.precipitation_mm, f.wind_max_kmh
    FROM dwh.fact_weather_daily AS f
    JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
    JOIN dwh.dim_location AS l ON l.location_key = f.location_key
"""
SQL_FC_MODEL = """
    SELECT target_date, predicted_temp_max_c
    FROM mart.forecast_daily
    WHERE location_name = ? AND model_name = 'clim_ar1'
      AND base_date = (SELECT MAX(base_date) FROM mart.forecast_daily
                       WHERE location_name = ? AND model_name = 'clim_ar1')
    ORDER BY target_date
"""
SQL_FC_API = """
    SELECT target_date, predicted_temp_max_c
    FROM staging.api_forecast_raw
    WHERE location_name = ?
      AND base_date = (SELECT MAX(base_date) FROM staging.api_forecast_raw WHERE location_name = ?)
    ORDER BY target_date
"""
SQL_EVAL = """
    SELECT location_name, model_name, horizon_days, mae_c, rmse_c, n_obs
    FROM mart.forecast_eval
    WHERE run_at = (SELECT MAX(run_at) FROM mart.forecast_eval)
    ORDER BY location_name, model_name, horizon_days
"""
SQL_EVAL_LEGACY = """
    SELECT 'ALL' AS location_name, model_name, horizon_days, mae_c, rmse_c, n_obs
    FROM mart.forecast_eval
    WHERE run_at = (SELECT MAX(run_at) FROM mart.forecast_eval)
    ORDER BY model_name, horizon_days
"""
SQL_LIVE_EVAL = """
    SELECT model_name, horizon_days, COUNT(*) AS n_obs,
           AVG(ABS(CAST(error_c AS FLOAT))) AS mae_c,
           SQRT(AVG(CAST(error_c AS FLOAT) * CAST(error_c AS FLOAT))) AS rmse_c
    FROM mart.v_forecast_vs_actual
    WHERE (? = 'ALL' OR location_name = ?)
    GROUP BY model_name, horizon_days
    ORDER BY model_name, horizon_days
"""
SQL_METRICS = "SELECT * FROM mart.v_data_quality_metrics"
SQL_DQ = """
    SELECT run_at, check_name, bad_rows, status
    FROM dwh.dq_check_log
    WHERE run_at = (SELECT MAX(run_at) FROM dwh.dq_check_log)
    ORDER BY check_id
"""
SQL_RUNS = """
    SELECT TOP 10 run_id, mode, started_at, finished_at, status,
           locations_ok, locations_total, rows_loaded, dq_fail_count
    FROM dwh.pipeline_run_log
    ORDER BY started_at DESC
"""
SQL_COUNTS = """
    SELECT N'staging.weather_daily_raw' AS bang, COUNT(*) AS so_dong FROM staging.weather_daily_raw
    UNION ALL SELECT N'staging.api_forecast_raw', COUNT(*) FROM staging.api_forecast_raw
    UNION ALL SELECT N'dwh.dim_date', COUNT(*) FROM dwh.dim_date
    UNION ALL SELECT N'dwh.dim_location', COUNT(*) FROM dwh.dim_location
    UNION ALL SELECT N'dwh.fact_weather_daily', COUNT(*) FROM dwh.fact_weather_daily
    UNION ALL SELECT N'mart.forecast_daily', COUNT(*) FROM mart.forecast_daily
    UNION ALL SELECT N'mart.forecast_eval', COUNT(*) FROM mart.forecast_eval
"""
SQL_DIM = """
    SELECT location_name, latitude, longitude, region_name, valid_from, valid_to, is_current
    FROM dwh.dim_location
    ORDER BY location_name, valid_from
"""


@st.cache_data(ttl=600, show_spinner=False)
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Chạy truy vấn, kết quả được lưu tạm 10 phút (nút "Làm mới dữ liệu" xóa bộ nhớ tạm)."""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, *params)
        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    return rows_to_frame(columns, rows)


def safe_query(sql: str, params: tuple = (), what: str = "dữ liệu") -> pd.DataFrame | None:
    """Truy vấn có báo lỗi đúng nguyên nhân: đây là lỗi SQL/kết nối, không phải 'chưa tạo bảng'."""
    try:
        return run_query(sql, params)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Không truy vấn được {what}: {exc}")
        return None


def object_exists(name: str) -> bool:
    df = run_query("SELECT OBJECT_ID(?) AS oid", (name,))
    return not pd.isna(df.iloc[0, 0])


def column_exists(table: str, column: str) -> bool:
    df = run_query("SELECT COL_LENGTH(?, ?) AS len", (table, column))
    return not pd.isna(df.iloc[0, 0])


def scope_note(text: str) -> None:
    st.caption("ℹ️ " + text)


def fmt_date(d) -> str:
    return pd.Timestamp(d).strftime("%d/%m/%Y")


# ----------------------------------------------------------------------------
# Dữ liệu chính và bộ lọc dùng chung
# ----------------------------------------------------------------------------
try:
    daily = run_query(SQL_DAILY)
except Exception as exc:  # noqa: BLE001
    st.error(
        f"Không kết nối được SQL Server hoặc truy vấn lỗi: {exc}\n\n"
        "Kiểm tra dịch vụ SQL Server đang chạy, file .env (xem .env.example) và ODBC Driver."
    )
    st.stop()

if daily.empty:
    st.warning("Kho dữ liệu chưa có dữ liệu. Hãy chạy `python -m weather_platform.load_history` trước.")
    st.stop()

daily["full_date"] = pd.to_datetime(daily["full_date"])
locations = sorted(daily["location_name"].unique())
years = sorted(int(y) for y in daily["year_num"].unique())

st.sidebar.title("🌦️ Bộ lọc")
options = [ALL_LABEL] + locations
default_index = options.index("Hà Nội") if "Hà Nội" in options else 1
choice = st.sidebar.selectbox("Địa điểm", options, index=default_index)
if len(years) > 1:
    y0, y1 = st.sidebar.select_slider("Khoảng năm", options=years, value=(years[0], years[-1]))
else:
    y0 = y1 = years[0]
if st.sidebar.button("🔄 Làm mới dữ liệu"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.divider()
st.sidebar.caption(
    f"Dữ liệu từ {fmt_date(daily['full_date'].min())} đến {fmt_date(daily['full_date'].max())}. "
    "Mỗi tab ghi rõ bộ lọc nào được áp dụng."
)

scope = locations if choice == ALL_LABEL else [choice]
scope_key = config.ALL_LOCATIONS if choice == ALL_LABEL else choice
sel = daily[daily["location_name"].isin(scope) & daily["year_num"].between(y0, y1)]

st.title("Dữ liệu thời tiết Việt Nam")
st.caption(
    "Nền tảng dữ liệu: Open-Meteo, Python, SQL Server (staging, dwh, mart). "
    "Số liệu là dữ liệu tái phân tích, không phải số đo từ một trạm cụ thể."
)

tab_overview, tab_trend, tab_extreme, tab_model, tab_quality = st.tabs(
    ["Tổng quan", "Xu hướng theo tháng & năm", "Thời tiết cực đoan", "Độ chính xác dự báo", "Chất lượng dữ liệu"]
)


PLOTLY_CONFIG = {
    "scrollZoom": True,   # cuộn chuột để phóng to/thu nhỏ tại chỗ con trỏ
    "displaylogo": False,
}


def style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), legend_title_text="",
        dragmode="pan",   # kéo chuột = di chuyển biểu đồ, không khoanh vùng để zoom
    )
    return fig


# ----------------------------------------------------------------------------
# Tổng quan
# ----------------------------------------------------------------------------
def overview_chart(d: pd.DataFrame, loc: str, last_date: pd.Timestamp) -> go.Figure:
    recent = d[d["full_date"] >= last_date - pd.Timedelta(days=45)]
    fc_model = run_query(SQL_FC_MODEL, (loc, loc))
    fc_api = run_query(SQL_FC_API, (loc, loc))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=recent["full_date"], y=recent["temp_max_c"], name="Thực tế (quan trắc)",
                             mode="lines+markers", line=dict(color=PALETTE[0])))
    ends = [last_date]
    if not fc_model.empty:
        x = pd.to_datetime(fc_model["target_date"])
        ends.append(x.max())
        fig.add_trace(go.Scatter(x=x, y=fc_model["predicted_temp_max_c"], name=label("clim_ar1"),
                                 mode="lines+markers", line=dict(color=PALETTE[1], dash="dash")))
    if not fc_api.empty:
        x = pd.to_datetime(fc_api["target_date"])
        ends.append(x.max())
        fig.add_trace(go.Scatter(x=x, y=fc_api["predicted_temp_max_c"], name=label("open-meteo"),
                                 mode="lines+markers", line=dict(color=PALETTE[2], dash="dot")))
    boundary = last_date.to_pydatetime()
    fig.add_shape(type="rect", xref="x", yref="paper", x0=boundary, x1=max(ends).to_pydatetime(), y0=0, y1=1,
                  fillcolor="rgba(255,180,84,0.08)", line_width=0, layer="below")
    fig.add_shape(type="line", xref="x", yref="paper", x0=boundary, x1=boundary, y0=0, y1=1,
                  line=dict(color="rgba(160,160,160,0.8)", dash="dash"))
    fig.add_annotation(x=boundary, y=0.98, yref="paper", text="Từ đây là dự báo →", showarrow=False,
                       xanchor="left", yanchor="top", xshift=6, font=dict(size=11, color="#9aa8ba"))
    fig.update_layout(title=f"Nhiệt độ cao nhất hằng ngày: {loc}", yaxis_title="Nhiệt độ (°C)",
                      hovermode="x unified", legend=dict(orientation="h", y=-0.18))
    return style(fig, 440)


def overview_one(loc: str, today: date) -> None:
    d = daily[daily["location_name"] == loc].dropna(subset=["temp_max_c"]).sort_values("full_date")
    kpi = analytics.summarize_location(d, today)
    if not kpi:
        st.info("Địa điểm này chưa có dữ liệu nhiệt độ.")
        return
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Ngày dữ liệu gần nhất", fmt_date(kpi["last_date"]))
    c2.metric("Độ trễ dữ liệu", f"{kpi['lag_days']} ngày",
              help="Dữ liệu tái phân tích của Open-Meteo về chậm khoảng 7 ngày. Đây là đặc điểm của nguồn dữ liệu, "
                   "không phải hệ thống ngừng cập nhật.")
    c3.metric("Nhiệt độ cao nhất (ngày cuối)", f"{kpi['temp_last']:.1f} °C",
              delta=f"{kpi['temp_last'] - kpi['temp_avg_30']:+.1f} °C so với TB 30 ngày", delta_color="off")
    c4.metric("Nhiệt độ cao nhất TB 30 ngày", f"{kpi['temp_avg_30']:.1f} °C")
    c5.metric("Tổng lượng mưa 30 ngày", f"{kpi['rain_30']:.1f} mm")
    st.plotly_chart(overview_chart(d, loc, pd.Timestamp(kpi["last_date"])), config=PLOTLY_CONFIG)
    st.caption(
        f"Nguồn: Open-Meteo. Dữ liệu quan trắc (tái phân tích) đến {fmt_date(kpi['last_date'])}. "
        "Dự báo của mô hình bắt đầu từ ngày kế tiếp; dự báo Open-Meteo bắt đầu từ ngày mai."
    )
    with st.expander("Ý nghĩa các đường dự báo"):
        for model in ("clim_ar1", "open-meteo"):
            st.markdown(f"**{label(model)}**: {MODEL_HELP[label(model)]}")


def overview_all(today: date) -> None:
    rows = []
    for loc in locations:
        kpi = analytics.summarize_location(daily[daily["location_name"] == loc], today)
        if kpi:
            rows.append({
                "Địa điểm": loc, "Ngày dữ liệu gần nhất": fmt_date(kpi["last_date"]),
                "Độ trễ (ngày)": kpi["lag_days"], "Nhiệt độ cao nhất ngày cuối (°C)": round(kpi["temp_last"], 1),
                "TB 30 ngày (°C)": round(kpi["temp_avg_30"], 1), "Mưa 30 ngày (mm)": round(kpi["rain_30"], 1),
            })
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    last = daily["full_date"].max()
    recent = daily[daily["full_date"] >= last - pd.Timedelta(days=45)]
    fig = px.line(recent, x="full_date", y="temp_max_c", color="location_name", color_discrete_sequence=PALETTE,
                  labels={"full_date": "Ngày", "temp_max_c": "Nhiệt độ cao nhất (°C)", "location_name": "Địa điểm"})
    fig.update_layout(title="Nhiệt độ cao nhất 45 ngày gần nhất, các địa điểm", hovermode="x unified")
    st.plotly_chart(style(fig, 420), config=PLOTLY_CONFIG)
    st.caption("Chọn một địa điểm ở thanh bên để xem dự báo của mô hình và của Open-Meteo.")


with tab_overview:
    scope_note(f"Áp dụng bộ lọc Địa điểm ({choice}). Khoảng năm không áp dụng vì tab này luôn hiển thị dữ liệu mới nhất.")
    if choice == ALL_LABEL:
        overview_all(date.today())
    else:
        overview_one(choice, date.today())

# ----------------------------------------------------------------------------
# Xu hướng theo tháng và năm
# ----------------------------------------------------------------------------
with tab_trend:
    scope_note(f"Áp dụng cả hai bộ lọc: Địa điểm ({choice}) và Khoảng năm ({y0} đến {y1}).")
    st.subheader("Nhiệt độ cao nhất trung bình theo tháng")
    fig = px.line(analytics.monthly_temperature(sel), x="month_num", y="temp_max_c", color="location_name",
                  markers=True, color_discrete_sequence=PALETTE,
                  labels={"month_num": "Tháng", "temp_max_c": "Nhiệt độ cao nhất TB (°C)", "location_name": "Địa điểm"})
    fig.update_xaxes(dtick=1)
    fig.update_traces(hovertemplate="%{y:.1f} °C")
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style(fig), config=PLOTLY_CONFIG)

    st.subheader("Lượng mưa trung bình mỗi tháng")
    fig = px.bar(analytics.monthly_rainfall(sel), x="month_num", y="total", color="location_name", barmode="group",
                 color_discrete_sequence=PALETTE,
                 labels={"month_num": "Tháng", "total": "Lượng mưa TB (mm)", "location_name": "Địa điểm"})
    fig.update_xaxes(dtick=1)
    st.plotly_chart(style(fig), config=PLOTLY_CONFIG)

    st.subheader("Nhiệt độ cao nhất trung bình theo năm")
    yearly = analytics.yearly_temperature(sel)
    if yearly.empty:
        st.info("Chưa có năm nào đủ dữ liệu trong khoảng năm đã chọn.")
    else:
        fig = px.line(yearly, x="year_num", y="temp", color="location_name", markers=True,
                      color_discrete_sequence=PALETTE,
                      labels={"year_num": "Năm", "temp": "Nhiệt độ cao nhất TB (°C)", "location_name": "Địa điểm"})
        fig.update_xaxes(dtick=1)
        fig.update_traces(hovertemplate="%{y:.1f} °C")
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(style(fig), config=PLOTLY_CONFIG)
        st.caption("Năm chưa đủ dữ liệu (như năm hiện tại) và tháng chưa đủ 28 ngày được bỏ qua để không làm lệch trung bình.")

# ----------------------------------------------------------------------------
# Thời tiết cực đoan
# ----------------------------------------------------------------------------
with tab_extreme:
    b0, b1 = config.BASELINE_START_YEAR, config.BASELINE_END_YEAR
    scope_note(
        f"Áp dụng cả hai bộ lọc cho phần đếm ngày: Địa điểm ({choice}) và Khoảng năm ({y0} đến {y1}). "
        f"Ngưỡng nóng bất thường dùng giai đoạn tham chiếu cố định {b0} đến {b1}, không đổi theo khoảng năm đã chọn."
    )
    heavy = st.number_input("Ngưỡng lượng mưa (mm/ngày)", min_value=10, max_value=300, step=10,
                            value=config.DEFAULT_HEAVY_RAIN_MM)
    st.markdown(
        f"- **Ngày nóng bất thường**: nhiệt độ cao nhất vượt phân vị 95% của cùng tháng, cùng địa điểm, "
        f"tính trong giai đoạn tham chiếu {b0} đến {b1}.\n"
        f"- **Ngày có lượng mưa ≥ {heavy} mm**: ngưỡng phân tích của đề tài, không phải phân loại chính thức "
        f"của cơ quan khí tượng."
    )
    thresholds = analytics.p95_thresholds(daily, b0, b1)
    if thresholds.empty:
        st.warning(f"Không có dữ liệu trong giai đoạn tham chiếu {b0} đến {b1} để tính ngưỡng nóng bất thường.")
    flagged = analytics.flag_extremes(sel, thresholds, heavy)
    by_year = analytics.extremes_by_year(flagged)

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.bar(by_year, x="year_num", y="hot_days", color="location_name", barmode="group",
                     title="Số ngày nóng bất thường theo năm", color_discrete_sequence=PALETTE,
                     labels={"year_num": "Năm", "hot_days": "Số ngày", "location_name": "Địa điểm"})
        fig.update_xaxes(dtick=1)
        st.plotly_chart(style(fig), config=PLOTLY_CONFIG)
    with col_b:
        fig = px.bar(by_year, x="year_num", y="heavy_rain_days", color="location_name", barmode="group",
                     title=f"Số ngày có lượng mưa ≥ {heavy} mm theo năm", color_discrete_sequence=PALETTE,
                     labels={"year_num": "Năm", "heavy_rain_days": "Số ngày", "location_name": "Địa điểm"})
        fig.update_xaxes(dtick=1)
        st.plotly_chart(style(fig), config=PLOTLY_CONFIG)
    st.caption("Năm hiện tại chưa đủ 12 tháng nên số ngày có thể thấp hơn thực tế cả năm.")

    st.subheader("10 ngày có nhiệt độ cao nhất trong khoảng đã chọn")
    top = sel.nlargest(10, "temp_max_c")[["location_name", "full_date", "temp_max_c", "precipitation_mm"]].copy()
    top["full_date"] = top["full_date"].dt.strftime("%d/%m/%Y")
    top["temp_max_c"] = top["temp_max_c"].round(1)
    top.columns = ["Địa điểm", "Ngày", "Nhiệt độ cao nhất (°C)", "Lượng mưa (mm)"]
    st.dataframe(top, hide_index=True)

# ----------------------------------------------------------------------------
# Độ chính xác dự báo
# ----------------------------------------------------------------------------
def accuracy_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["model_name"] = out["model_name"].map(label)
    out = out[["model_name", "horizon_days", "mae_c", "rmse_c", "n_obs"]]
    out.columns = ["Phương pháp", "Dự báo trước (ngày)", "MAE (°C)", "RMSE (°C)", "Số quan sát"]
    out["MAE (°C)"] = out["MAE (°C)"].round(2)
    out["RMSE (°C)"] = out["RMSE (°C)"].round(2)
    return out


def accuracy_chart(df: pd.DataFrame, metric_col: str, metric_name: str) -> go.Figure:
    plot = df.copy()
    plot["Phương pháp"] = plot["model_name"].map(label)
    fig = px.line(plot, x="horizon_days", y=metric_col, color="Phương pháp", markers=True,
                  color_discrete_sequence=PALETTE,
                  labels={"horizon_days": "Dự báo trước (ngày)", metric_col: f"{metric_name} (°C)"})
    fig.update_xaxes(dtick=1)
    fig.update_traces(hovertemplate="%{y:.2f} °C")
    fig.update_layout(hovermode="x unified")
    return style(fig)


with tab_model:
    scope_note(
        f"Áp dụng bộ lọc Địa điểm ({choice}). Khoảng năm không áp dụng vì kiểm thử ngược luôn dùng 2 năm gần nhất. "
        "\"Tất cả địa điểm\" là kết quả gộp mọi quan sát của cả 5 địa điểm."
    )
    st.subheader("Kiểm thử ngược (rolling-origin, bước 7 ngày, 2 năm gần nhất)")
    has_location = column_exists("mart.forecast_eval", "location_name")
    if not has_location:
        st.warning("Bảng mart.forecast_eval chưa có cột location_name (chưa chạy sql/01_setup/005). "
                   "Đang hiển thị kết quả gộp mọi địa điểm.")
    ev = safe_query(SQL_EVAL if has_location else SQL_EVAL_LEGACY, what="kết quả đánh giá mô hình")
    if ev is not None:
        target = scope_key if has_location else config.ALL_LOCATIONS
        ev_sel = ev[ev["location_name"] == target]
        if ev_sel.empty:
            st.info("Chưa có kết quả đánh giá cho lựa chọn này. Hãy chạy pipeline để mô hình được ước lượng lại.")
        else:
            k1, k2 = st.columns(2)
            for col, horizon in ((k1, 1), (k2, 7)):
                sub = ev_sel[ev_sel["horizon_days"] == horizon]
                if not sub.empty:
                    best = sub.loc[sub["mae_c"].idxmin()]
                    col.metric(f"MAE thấp nhất khi dự báo trước {horizon} ngày ({label(best['model_name'])})",
                               f"{best['mae_c']:.2f} °C")
            metric = st.radio("Chỉ số biểu đồ", ["MAE", "RMSE"], horizontal=True)
            st.plotly_chart(accuracy_chart(ev_sel, "mae_c" if metric == "MAE" else "rmse_c", metric), config=PLOTLY_CONFIG)
            st.dataframe(accuracy_table(ev_sel), hide_index=True)
            st.caption("MAE: sai số tuyệt đối trung bình. RMSE: căn bậc hai của sai số bình phương trung bình "
                       "(nhạy hơn với sai số lớn). Mỗi lần dự báo chỉ dùng dữ liệu đến trước mốc dự báo.")
            with st.expander("Ý nghĩa các phương pháp"):
                for model in ("persistence", "clim", "clim_ar1"):
                    st.markdown(f"**{label(model)}**: {MODEL_HELP[label(model)]}")

    st.subheader("So sánh dự báo đã lưu với số đo thực tế")
    if not object_exists("mart.v_forecast_vs_actual"):
        st.info("Chưa tạo view mart.v_forecast_vs_actual. Hãy chạy sql/03_views/v_forecast_vs_actual.sql.")
    else:
        live = safe_query(SQL_LIVE_EVAL, (scope_key, scope_key), what="view mart.v_forecast_vs_actual")
        if live is not None:
            if live.empty:
                st.info("Chưa đủ dữ liệu để đối chiếu. Dữ liệu quan trắc về chậm khoảng 7 ngày, nên sau khoảng một "
                        "tuần chạy pipeline hằng ngày, bảng này sẽ có số liệu so sánh dự báo Open-Meteo với mô hình.")
            else:
                st.plotly_chart(accuracy_chart(live, "mae_c", "MAE"), config=PLOTLY_CONFIG)
                st.dataframe(accuracy_table(live), hide_index=True)
                st.caption("Số quan sát càng ít thì kết quả càng chưa ổn định.")

# ----------------------------------------------------------------------------
# Chất lượng dữ liệu
# ----------------------------------------------------------------------------
with tab_quality:
    scope_note("Tab này dùng toàn bộ 5 địa điểm của hệ thống và không áp dụng bộ lọc ở thanh bên.")
    st.subheader("Chỉ số chất lượng")
    if not object_exists("mart.v_data_quality_metrics"):
        st.info("Chưa tạo view mart.v_data_quality_metrics. Hãy chạy sql/03_views/v_data_quality_metrics.sql.")
    else:
        m = safe_query(SQL_METRICS, what="view mart.v_data_quality_metrics")
        if m is not None and not m.empty:
            r = m.iloc[0]
            q1, q2, q3, q4, q5 = st.columns(5)
            q1.metric("Đầy đủ (completeness)", f"{r['completeness_pct']:.2f}%",
                      help="Tỷ lệ ô dữ liệu có giá trị trong 4 chỉ số đo (nhiệt độ cao, thấp, mưa, gió) của bảng fact.")
            q2.metric("Tỷ lệ thiếu", f"{r['missing_rate_pct']:.2f}%")
            q3.metric("Tỷ lệ trùng", f"{r['duplicate_rate_pct']:.2f}%",
                      help="Số dòng trùng khóa (địa điểm, ngày) ở staging trên tổng số dòng staging.")
            q4.metric("Phủ ngày", f"{r['date_coverage_pct']:.2f}%",
                      help="Tỷ lệ ngày có dữ liệu trên số ngày kỳ vọng giữa ngày đầu và ngày cuối của từng địa điểm.")
            q5.metric("Độ trễ dữ liệu", f"{int(r['freshness_days'])} ngày",
                      help="Độ trễ của địa điểm cũ nhất so với hôm nay. Nguồn tái phân tích luôn trễ khoảng 7 ngày.")
            st.caption(f"Phạm vi dữ liệu: {fmt_date(r['coverage_from'])} đến {fmt_date(r['coverage_to'])} "
                       f"({int(r['fact_rows']):,} dòng fact).")

    st.subheader("Các phép kiểm tra (lần chạy gần nhất)")
    dq = safe_query(SQL_DQ, what="nhật ký kiểm tra chất lượng")
    if dq is not None:
        if dq.empty:
            st.info("Chưa có kết quả kiểm tra. Hãy chạy pipeline hoặc EXEC dwh.usp_run_dq_checks.")
        else:
            n_pass = int((dq["status"] == "PASS").sum())
            st.metric("Kết quả", f"{n_pass}/{len(dq)} PASS")
            show = dq[["check_name", "bad_rows", "status"]].copy()
            show["status"] = show["status"].map(lambda s: "✅ PASS" if s == "PASS" else "❌ FAIL")
            show.columns = ["Phép kiểm tra", "Số dòng lỗi", "Kết quả"]
            st.dataframe(show, hide_index=True)
            st.caption(f"Chạy lúc {pd.to_datetime(dq['run_at'].iloc[0]):%d/%m/%Y %H:%M:%S}. "
                       "PASS chỉ có nghĩa là không phát hiện lỗi thuộc các loại đã được định nghĩa, "
                       "không đảm bảo dữ liệu đúng 100%.")

    st.subheader("Lịch sử các lần chạy pipeline")
    if not object_exists("dwh.pipeline_run_log"):
        st.info("Chưa tạo bảng dwh.pipeline_run_log. Hãy chạy sql/01_setup/003_dwh_tables.sql.")
    else:
        runs = safe_query(SQL_RUNS, what="nhật ký chạy pipeline")
        if runs is not None and not runs.empty:
            for col in ("started_at", "finished_at"):
                runs[col] = pd.to_datetime(runs[col]).dt.strftime("%d/%m/%Y %H:%M:%S")
            runs.columns = ["Mã lần chạy", "Chế độ", "Bắt đầu", "Kết thúc", "Trạng thái", "Địa điểm OK",
                            "Tổng địa điểm", "Dòng nạp", "Kiểm tra FAIL"]
            st.dataframe(runs, hide_index=True)
        elif runs is not None:
            st.info("Chưa có lần chạy nào được ghi lại.")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Số dòng theo bảng")
        counts = safe_query(SQL_COUNTS, what="số dòng các bảng")
        if counts is not None:
            counts.columns = ["Bảng", "Số dòng"]
            st.dataframe(counts, hide_index=True)
    with col_b:
        st.subheader("Lịch sử địa điểm (SCD2)")
        dim = safe_query(SQL_DIM, what="dim_location")
        if dim is not None:
            dim["is_current"] = dim["is_current"].map(lambda v: "Hiện hành" if v else "Đã đóng")
            dim["valid_from"] = dim["valid_from"].map(lambda v: "Ban đầu" if v.year <= 1900 else v.strftime("%d/%m/%Y"))
            dim["valid_to"] = dim["valid_to"].map(lambda v: "Hiện tại" if v.year >= 9999 else v.strftime("%d/%m/%Y"))
            dim.columns = ["Địa điểm", "Vĩ độ", "Kinh độ", "Vùng", "Hiệu lực từ", "Đến", "Trạng thái"]
            st.dataframe(dim, hide_index=True)