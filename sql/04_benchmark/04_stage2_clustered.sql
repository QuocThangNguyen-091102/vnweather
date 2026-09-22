/* Giai đoạn 2: CLUSTERED index theo khóa tra cứu. Chạy rồi đo 02_queries.sql. */
USE VNDataPlatform;
GO
EXEC bench.usp_reset_indexes;
GO
CREATE CLUSTERED INDEX CIX_weather_test ON bench.weather_test (station_id, date_key);
CREATE CLUSTERED INDEX CIX_forecast_test ON bench.forecast_test (station_id, target_date_key, horizon_days);
GO
