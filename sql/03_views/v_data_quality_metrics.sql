/* =====================================================================
   View chỉ số chất lượng dữ liệu (một dòng)
   completeness_pct   : % ô có giá trị trong 4 chỉ số đo của fact (nhiệt độ cao, thấp, mưa, gió)
   missing_rate_pct   : 100 - completeness_pct
   duplicate_rate_pct : % dòng trùng khóa (địa điểm, ngày) trên tổng số dòng staging
   date_coverage_pct  : % ngày có dữ liệu trên số ngày kỳ vọng giữa ngày đầu và ngày cuối của từng địa điểm
   freshness_days     : độ trễ (ngày) của địa điểm CŨ NHẤT so với hôm nay.
                        Nguồn tái phân tích của Open-Meteo luôn trễ khoảng 7 ngày, đây là đặc điểm của nguồn.
   coverage_from/to   : ngày đầu, và ngày mà TẤT CẢ địa điểm đều đã có dữ liệu đến
   ===================================================================== */
USE VNDataPlatform;
GO

CREATE OR ALTER VIEW mart.v_data_quality_metrics
AS
WITH fact_stats AS (
    SELECT COUNT(*) AS fact_rows,
           COUNT(temp_max_c) + COUNT(temp_min_c) + COUNT(precipitation_mm) + COUNT(wind_max_kmh) AS non_null_cells
    FROM dwh.fact_weather_daily
),
staging_stats AS (
    SELECT COUNT(*) AS staging_rows FROM staging.weather_daily_raw
),
dup_stats AS (
    SELECT COALESCE(SUM(t.c - 1), 0) AS dup_rows
    FROM (SELECT COUNT(*) AS c FROM staging.weather_daily_raw
          GROUP BY location_name, obs_date HAVING COUNT(*) > 1) AS t
),
per_location AS (
    SELECT location_name, MIN(obs_date) AS first_date, MAX(obs_date) AS last_date,
           COUNT(DISTINCT obs_date) AS day_count
    FROM staging.weather_daily_raw
    GROUP BY location_name
),
range_stats AS (
    SELECT SUM(DATEDIFF(DAY, first_date, last_date) + 1)             AS expected_days,
           SUM(DATEDIFF(DAY, first_date, last_date) + 1 - day_count) AS missing_days,
           MAX(DATEDIFF(DAY, last_date, CAST(SYSDATETIME() AS DATE))) AS worst_lag_days,
           MIN(first_date) AS coverage_from,
           MIN(last_date)  AS coverage_to
    FROM per_location
)
SELECT
    fact_stats.fact_rows,
    staging_stats.staging_rows,
    CAST(100.0 * fact_stats.non_null_cells / NULLIF(4 * fact_stats.fact_rows, 0) AS DECIMAL(6,3)) AS completeness_pct,
    CAST(100.0 - 100.0 * fact_stats.non_null_cells / NULLIF(4 * fact_stats.fact_rows, 0) AS DECIMAL(6,3)) AS missing_rate_pct,
    CAST(100.0 * dup_stats.dup_rows / NULLIF(staging_stats.staging_rows, 0) AS DECIMAL(6,3)) AS duplicate_rate_pct,
    CAST(100.0 * (range_stats.expected_days - range_stats.missing_days) / NULLIF(range_stats.expected_days, 0) AS DECIMAL(6,3)) AS date_coverage_pct,
    range_stats.worst_lag_days AS freshness_days,
    range_stats.coverage_from,
    range_stats.coverage_to
FROM fact_stats
CROSS JOIN staging_stats
CROSS JOIN dup_stats
CROSS JOIN range_stats;
GO
