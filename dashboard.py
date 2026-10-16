"""
dashboard.py - Bảng điều khiển dữ liệu thời tiết Việt Nam (Streamlit).

Chạy:  streamlit run dashboard.py
Đọc trực tiếp từ SQL Server (schema dwh, mart, staging), không cần file trung gian.
"""
from decimal import Decimal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pyodbc
import streamlit as st

from config import CONN_STR
PALETTE = px.colors.qualitative.Set2
HEAVY_RAIN_MM = 50  # ngưỡng "mưa rất to" trong một ngày (mm)

st.set_page_config(page_title="Dữ liệu thời tiết Việt Nam", page_icon="🌦️", layout="wide")
st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background: rgba(128, 128, 128, 0.08);
        padding: 12px 16px;
        border-radius: 10px;
    }
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
      AND base_date = (SELECT MAX(base_date) FROM staging.api_forecast_raw
                       WHERE location_name = ?)
    ORDER BY target_date
"""

SQL_EVAL = """
    SELECT model_name, horizon_days, mae_c
    FROM mart.forecast_eval
    WHERE run_at = (SELECT MAX(run_at) FROM mart.forecast_eval)
    ORDER BY model_name, horizon_days
"""

SQL_LIVE_EVAL = """
    SELECT model_name, horizon_days, COUNT(*) AS n_obs,
           AVG(ABS(error_c)) AS mae_c
    FROM mart.v_forecast_vs_actual
    GROUP BY model_name, horizon_days
    ORDER BY model_name, horizon_days
"""

SQL_DQ = """
    SELECT run_at, check_name, bad_rows, status
    FROM dwh.dq_check_log
    WHERE run_at = (SELECT MAX(run_at) FROM dwh.dq_check_log)
    ORDER BY check_id
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
    SELECT location_name, latitude, longitude, region_name,
           valid_from, valid_to, is_current
    FROM dwh.dim_location
    ORDER BY location_name, valid_from
"""


@st.cache_data(ttl=600, show_spinner=False)
def run_query(sql, params=()):
    """Chạy truy vấn, trả về DataFrame (kiểu DECIMAL của SQL Server đổi sang float)."""
    conn = pyodbc.connect(CONN_STR)
    try:
        cur = conn.cursor()
        cur.execute(sql, *params)
        cols = [c[0] for c in cur.description]
        rows = [tuple(r) for r in cur.fetchall()]
    finally:
        conn.close()
    df = pd.DataFrame.from_records(rows, columns=cols)
    for c in df.columns:
        if df[c].map(lambda v: isinstance(v, Decimal)).any():
            df[c] = df[c].map(lambda v: float(v) if isinstance(v, Decimal) else v).astype(float)
    return df


# ----------------------------------------------------------------------------
# Tải dữ liệu chính
# ----------------------------------------------------------------------------
try:
    daily = run_query(SQL_DAILY)
except Exception as exc:  # noqa: BLE001
    st.error(f"Không kết nối được SQL Server hoặc truy vấn lỗi: {exc}")
    st.stop()

if daily.empty:
    st.warning("Kho dữ liệu chưa có dữ liệu. Hãy chạy load_history.py và các procedure nạp fact trước.")
    st.stop()

daily["full_date"] = pd.to_datetime(daily["full_date"])
locations = sorted(daily["location_name"].unique())
years = sorted(int(y) for y in daily["year_num"].unique())

# ----------------------------------------------------------------------------
# Thanh bên
# ----------------------------------------------------------------------------
st.sidebar.title("🌦️ Bộ lọc")
locs = st.sidebar.multiselect("Địa điểm", locations, default=locations)
if len(years) > 1:
    y0, y1 = st.sidebar.select_slider("Khoảng năm", options=years, value=(years[0], years[-1]))
else:
    y0 = y1 = years[0]
st.sidebar.divider()
st.sidebar.caption(
    f"Dữ liệu từ {daily['full_date'].min():%d/%m/%Y} đến {daily['full_date'].max():%d/%m/%Y}. "
    "Bộ lọc áp dụng cho các thẻ Xu hướng theo mùa và Thời tiết cực đoan."
)

if not locs:
    st.warning("Hãy chọn ít nhất một địa điểm ở thanh bên.")
    st.stop()

sel = daily[daily["location_name"].isin(locs) & daily["year_num"].between(y0, y1)]

st.title("Dữ liệu thời tiết Việt Nam")
st.caption(
    "Nền tảng dữ liệu: Open-Meteo, Python, SQL Server (staging, dwh, mart). "
    "Số liệu là dữ liệu tái phân tích, không phải số đo từ một trạm cụ thể."
)

tab_overview, tab_season, tab_extreme, tab_model, tab_quality = st.tabs(
    ["Tổng quan", "Xu hướng theo mùa", "Thời tiết cực đoan", "Độ chính xác dự báo", "Chất lượng dữ liệu"]
)

# ----------------------------------------------------------------------------
# Tổng quan
# ----------------------------------------------------------------------------
with tab_overview:
    loc = st.selectbox("Địa điểm", locations, key="loc_overview")
    d = (
        daily[daily["location_name"] == loc]
        .dropna(subset=["temp_max_c"])
        .sort_values("full_date")
    )
    last = d.iloc[-1]
    last30 = d.tail(30)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dữ liệu mới nhất", f"{last['full_date']:%d/%m/%Y}")
    c2.metric(
        "Nhiệt độ cao nhất (ngày cuối)",
        f"{last['temp_max_c']:.1f} °C",
        delta=f"{last['temp_max_c'] - last30['temp_max_c'].mean():+.1f} °C so với TB 30 ngày",
        delta_color="off",
    )
    c3.metric("Nhiệt độ cao nhất TB 30 ngày", f"{last30['temp_max_c'].mean():.1f} °C")
    c4.metric("Tổng lượng mưa 30 ngày", f"{last30['precipitation_mm'].sum():.1f} mm")

    fc_model = run_query(SQL_FC_MODEL, (loc, loc))
    fc_api = run_query(SQL_FC_API, (loc, loc))

    recent = d[d["full_date"] >= d["full_date"].max() - pd.Timedelta(days=45)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=recent["full_date"], y=recent["temp_max_c"], name="Thực tế",
        mode="lines+markers", line=dict(color=PALETTE[0]),
    ))
    if not fc_model.empty:
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(fc_model["target_date"]), y=fc_model["predicted_temp_max_c"],
            name="Mô hình clim_ar1", mode="lines+markers",
            line=dict(color=PALETTE[1], dash="dash"),
        ))
    if not fc_api.empty:
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(fc_api["target_date"]), y=fc_api["predicted_temp_max_c"],
            name="Dự báo Open-Meteo", mode="lines+markers",
            line=dict(color=PALETTE[2], dash="dot"),
        ))
    fig.update_layout(
        title=f"Nhiệt độ cao nhất hằng ngày: {loc}",
        yaxis_title="Nhiệt độ (°C)",
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.15),
        height=430,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig)
    st.caption(
        "Số liệu quan trắc về chậm khoảng 7 ngày, nên dự báo của mô hình bắt đầu từ ngày kế tiếp "
        "ngày dữ liệu cuối, còn dự báo Open-Meteo bắt đầu từ ngày mai."
    )

# ----------------------------------------------------------------------------
# Xu hướng theo mùa
# ----------------------------------------------------------------------------
with tab_season:
    st.subheader("Nhiệt độ cao nhất trung bình theo tháng")
    monthly_temp = (
        sel.groupby(["location_name", "month_num"])["temp_max_c"].mean().reset_index()
    )
    fig = px.line(
        monthly_temp, x="month_num", y="temp_max_c", color="location_name", markers=True,
        labels={"month_num": "Tháng", "temp_max_c": "Nhiệt độ cao nhất TB (°C)",
                "location_name": "Địa điểm"},
        color_discrete_sequence=PALETTE,
    )
    fig.update_xaxes(dtick=1)
    fig.update_layout(hovermode="x unified", height=380, margin=dict(l=10, r=10, t=20, b=10))
    fig.update_traces(hovertemplate="%{y:.1f} °C")
    st.plotly_chart(fig)

    st.subheader("Lượng mưa trung bình mỗi tháng")
    monthly_rain = (
        sel.groupby(["location_name", "year_num", "month_num"])
        .agg(total=("precipitation_mm", "sum"), days=("full_date", "count"))
        .reset_index()
    )
    monthly_rain = monthly_rain[monthly_rain["days"] >= 28]  # bỏ tháng chưa đủ dữ liệu
    rain = (
        monthly_rain.groupby(["location_name", "month_num"])["total"].mean().reset_index()
    )
    fig = px.bar(
        rain, x="month_num", y="total", color="location_name", barmode="group",
        labels={"month_num": "Tháng", "total": "Lượng mưa TB (mm)", "location_name": "Địa điểm"},
        color_discrete_sequence=PALETTE,
    )
    fig.update_xaxes(dtick=1)
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig)

    st.subheader("Nhiệt độ cao nhất trung bình theo năm")
    yearly = (
        sel.groupby(["location_name", "year_num"])
        .agg(temp=("temp_max_c", "mean"), days=("full_date", "count"))
        .reset_index()
    )
    yearly = yearly[yearly["days"] >= 360]  # chỉ giữ năm đủ dữ liệu
    if yearly.empty:
        st.info("Chưa có năm nào đủ dữ liệu trong khoảng năm đã chọn.")
    else:
        fig = px.line(
            yearly, x="year_num", y="temp", color="location_name", markers=True,
            labels={"year_num": "Năm", "temp": "Nhiệt độ cao nhất TB (°C)",
                    "location_name": "Địa điểm"},
            color_discrete_sequence=PALETTE,
        )
        fig.update_xaxes(dtick=1)
        fig.update_layout(hovermode="x unified", height=380, margin=dict(l=10, r=10, t=20, b=10))
        fig.update_traces(hovertemplate="%{y:.1f} °C")
        st.plotly_chart(fig)
        st.caption("Năm chưa đủ dữ liệu (như năm hiện tại) được bỏ qua để không làm lệch trung bình.")

# ----------------------------------------------------------------------------
# Thời tiết cực đoan
# ----------------------------------------------------------------------------
with tab_extreme:
    st.markdown(
        "**Ngày nóng bất thường**: nhiệt độ cao nhất vượt mức phân vị 95% của chính tháng đó, "
        f"tại địa điểm đó. **Ngày mưa rất to**: lượng mưa từ {HEAVY_RAIN_MM} mm trở lên."
    )
    thr = (
        daily.groupby(["location_name", "month_num"])["temp_max_c"]
        .quantile(0.95).rename("p95").reset_index()
    )
    ext = sel.merge(thr, on=["location_name", "month_num"])
    ext["hot_day"] = ext["temp_max_c"] > ext["p95"]
    ext["heavy_rain"] = ext["precipitation_mm"] >= HEAVY_RAIN_MM
    by_year = (
        ext.groupby(["location_name", "year_num"])
        .agg(hot_days=("hot_day", "sum"), heavy_rain_days=("heavy_rain", "sum"))
        .reset_index()
    )

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.bar(
            by_year, x="year_num", y="hot_days", color="location_name", barmode="group",
            title="Số ngày nóng bất thường theo năm",
            labels={"year_num": "Năm", "hot_days": "Số ngày", "location_name": "Địa điểm"},
            color_discrete_sequence=PALETTE,
        )
        fig.update_xaxes(dtick=1)
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig)
    with col_b:
        fig = px.bar(
            by_year, x="year_num", y="heavy_rain_days", color="location_name", barmode="group",
            title="Số ngày mưa rất to theo năm",
            labels={"year_num": "Năm", "heavy_rain_days": "Số ngày", "location_name": "Địa điểm"},
            color_discrete_sequence=PALETTE,
        )
        fig.update_xaxes(dtick=1)
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig)
    st.caption("Năm hiện tại chưa đủ 12 tháng nên số ngày có thể thấp hơn thực tế cả năm.")

    st.subheader("10 ngày nóng nhất trong khoảng đã chọn")
    top = sel.nlargest(10, "temp_max_c")[
        ["location_name", "full_date", "temp_max_c", "precipitation_mm"]
    ].copy()
    top["full_date"] = top["full_date"].dt.strftime("%d/%m/%Y")
    top["temp_max_c"] = top["temp_max_c"].round(1)
    top.columns = ["Địa điểm", "Ngày", "Nhiệt độ cao nhất (°C)", "Lượng mưa (mm)"]
    st.dataframe(top, hide_index=True)

# ----------------------------------------------------------------------------
# Độ chính xác dự báo
# ----------------------------------------------------------------------------
with tab_model:
    st.subheader("Kiểm thử ngược trên 2 năm gần nhất")
    ev = run_query(SQL_EVAL)
    if ev.empty:
        st.info("Chưa có kết quả đánh giá. Hãy chạy forecast.py.")
    else:
        fig = px.line(
            ev, x="horizon_days", y="mae_c", color="model_name", markers=True,
            labels={"horizon_days": "Dự báo trước (ngày)", "mae_c": "Sai số MAE (°C)",
                    "model_name": "Phương pháp"},
            color_discrete_sequence=PALETTE,
        )
        fig.update_xaxes(dtick=1)
        fig.update_layout(hovermode="x unified", height=380, margin=dict(l=10, r=10, t=20, b=10))
        fig.update_traces(hovertemplate="%{y:.2f} °C")
        st.plotly_chart(fig)
        st.caption(
            "persistence: lặp lại ngày cuối. clim: đường khí hậu theo mùa. "
            "clim_ar1: đường khí hậu cộng phần lệch hiện tại giảm dần."
        )

    st.subheader("So sánh dự báo đã lưu với số đo thực tế")
    try:
        live = run_query(SQL_LIVE_EVAL)
    except Exception:  # noqa: BLE001
        live = None
        st.info("Chưa tạo view mart.v_forecast_vs_actual. Hãy chạy đoạn SQL ở bước 6.1.")
    if live is not None:
        if live.empty:
            st.info(
                "Chưa đủ dữ liệu để đối chiếu. Dữ liệu quan trắc về chậm khoảng 7 ngày, "
                "nên sau khoảng một tuần chạy pipeline hằng ngày, bảng này sẽ có số liệu "
                "so sánh dự báo Open-Meteo với mô hình của dự án."
            )
        else:
            fig = px.line(
                live, x="horizon_days", y="mae_c", color="model_name", markers=True,
                labels={"horizon_days": "Dự báo trước (ngày)", "mae_c": "Sai số MAE (°C)",
                        "model_name": "Phương pháp"},
                color_discrete_sequence=PALETTE,
            )
            fig.update_xaxes(dtick=1)
            fig.update_layout(hovermode="x unified", height=380,
                              margin=dict(l=10, r=10, t=20, b=10))
            fig.update_traces(hovertemplate="%{y:.2f} °C")
            st.plotly_chart(fig)
            st.caption("Số quan sát càng ít thì kết quả càng chưa ổn định.")

# ----------------------------------------------------------------------------
# Chất lượng dữ liệu
# ----------------------------------------------------------------------------
with tab_quality:
    dq = run_query(SQL_DQ)
    st.subheader("Kiểm tra chất lượng dữ liệu (lần chạy gần nhất)")
    if dq.empty:
        st.info("Chưa có kết quả kiểm tra. Hãy chạy EXEC dwh.usp_run_dq_checks.")
    else:
        n_pass = int((dq["status"] == "PASS").sum())
        st.metric("Kết quả", f"{n_pass}/{len(dq)} PASS")
        show = dq[["check_name", "bad_rows", "status"]].copy()
        show["status"] = show["status"].map(lambda s: "✅ PASS" if s == "PASS" else "❌ FAIL")
        show.columns = ["Phép kiểm tra", "Số dòng lỗi", "Kết quả"]
        st.dataframe(show, hide_index=True)
        st.caption(f"Chạy lúc {pd.to_datetime(dq['run_at'].iloc[0]):%d/%m/%Y %H:%M:%S}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Số dòng theo bảng")
        counts = run_query(SQL_COUNTS)
        counts.columns = ["Bảng", "Số dòng"]
        st.dataframe(counts, hide_index=True)
    with col_b:
        st.subheader("Lịch sử địa điểm (SCD2)")
        dim = run_query(SQL_DIM)
        dim["is_current"] = dim["is_current"].map(lambda v: "Hiện hành" if v else "Đã đóng")
        dim["valid_from"] = dim["valid_from"].map(
            lambda v: "Ban đầu" if v.year <= 1900 else v.strftime("%d/%m/%Y")
        )
        dim["valid_to"] = dim["valid_to"].map(
            lambda v: "Hiện tại" if v.year >= 9999 else v.strftime("%d/%m/%Y")
        )
        dim.columns = ["Địa điểm", "Vĩ độ", "Kinh độ", "Vùng", "Hiệu lực từ", "Đến", "Trạng thái"]
        st.dataframe(dim, hide_index=True)
