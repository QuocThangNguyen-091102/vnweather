import sys
import pyodbc
import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def run():
    with pyodbc.connect(config.CONN_STR) as conn:
        cursor = conn.cursor()
        
        print("=== 1. TỔNG QUAN CÁC BẢNG TRONG DATABASE ===")
        tables = [
            ("dwh.dim_location", "Bảng địa điểm SCD Type 2"),
            ("dwh.dim_date", "Bảng chiều thời gian (2015 - 2030)"),
            ("dwh.fact_weather_daily", "Bảng fact quan trắc hàng ngày"),
            ("mart.forecast_daily", "Bảng dự báo 7 ngày từ mô hình ML/baseline"),
            ("mart.forecast_eval", "Bảng đánh giá sai số mô hình (MAE, RMSE)"),
            ("dwh.dq_check_log", "Log kiểm tra chất lượng dữ liệu (Data Quality)"),
            ("staging.openmeteo_daily_raw", "Bảng staging quan trắc thô"),
            ("staging.openmeteo_forecast_raw", "Bảng staging dự báo từ Open-Meteo"),
        ]
        
        for table, desc in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  • {table:<32}: {count:>6} dòng ({desc})")
            except Exception as e:
                print(f"  • {table:<32}: Chưa tồn tại hoặc lỗi")
                
        print("\n=== 2. DỮ LIỆU QUAN TRẮC MỚI NHẤT (dwh.fact_weather_daily) ===")
        cursor.execute("""
            SELECT TOP 5 
                l.location_name,
                d.full_date,
                w.temp_max_c,
                w.temp_min_c,
                w.precipitation_mm,
                w.wind_max_kmh
            FROM dwh.fact_weather_daily w
            JOIN dwh.dim_location l ON w.location_key = l.location_key
            JOIN dwh.dim_date d ON w.date_key = d.date_key
            ORDER BY d.full_date DESC, l.location_name ASC
        """)
        rows = cursor.fetchall()
        print(f"  {'Địa điểm':<12} | {'Ngày':<10} | {'T_max (°C)':<10} | {'T_min (°C)':<10} | {'Mưa (mm)':<10} | {'Gió (km/h)':<10}")
        print("  " + "-" * 75)
        for r in rows:
            p_val = f"{r[4]:.1f}" if r[4] is not None else "-"
            w_val = f"{r[5]:.1f}" if r[5] is not None else "-"
            print(f"  {r[0]:<12} | {str(r[1]):<10} | {r[2]:<10.1f} | {r[3]:<10.1f} | {p_val:<10} | {w_val:<10}")

        print("\n=== 3. KẾT QUẢ DỰ BÁO 7 NGÀY MỚI NHẤT (mart.forecast_daily) ===")
        cursor.execute("""
            SELECT TOP 10 
                location_name,
                target_date,
                horizon_days,
                model_name,
                predicted_temp_max_c
            FROM mart.forecast_daily
            ORDER BY created_at DESC, horizon_days ASC, location_name ASC
        """)
        rows = cursor.fetchall()
        print(f"  {'Địa điểm':<12} | {'Ngày dự báo':<12} | {'Horizon':<8} | {'Mô hình':<12} | {'Nhiệt độ max (°C)':<18}")
        print("  " + "-" * 70)
        for r in rows:
            print(f"  {r[0]:<12} | {str(r[1]):<12} | {r[2]:<8} | {r[3]:<12} | {r[4]:<18.1f}")

        print("\n=== 4. ĐÁNH GIÁ ĐỘ CHÍNH XÁC MÔ HÌNH (mart.forecast_eval) ===")
        cursor.execute("""
            SELECT TOP 6
                model_name,
                horizon_days,
                mae_c,
                rmse_c,
                n_obs
            FROM mart.forecast_eval
            ORDER BY run_at DESC, horizon_days ASC, model_name ASC
        """)
        rows = cursor.fetchall()
        print(f"  {'Mô hình':<12} | {'Horizon':<8} | {'MAE (°C)':<10} | {'RMSE (°C)':<10} | {'Số mẫu test':<12}")
        print("  " + "-" * 60)
        for r in rows:
            print(f"  {r[0]:<12} | {r[1]:<8} | {r[2]:<10.2f} | {r[3]:<10.2f} | {r[4]:<12}")

        print("\n=== 5. NHẬT KÝ KIỂM TRA CHẤT LƯỢNG GẦN NHẤT (dwh.dq_check_log) ===")
        cursor.execute("""
            SELECT TOP 5 
                check_name,
                status,
                bad_rows,
                run_at
            FROM dwh.dq_check_log
            ORDER BY run_at DESC, check_id DESC
        """)
        rows = cursor.fetchall()
        print(f"  {'Tên bài kiểm tra':<35} | {'Trạng thái':<10} | {'Lỗi':<6} | {'Thời gian':<20}")
        print("  " + "-" * 78)
        for r in rows:
            print(f"  {r[0]:<35} | {r[1]:<10} | {r[2]:<6} | {str(r[3])[:19]:<20}")

if __name__ == "__main__":
    run()
