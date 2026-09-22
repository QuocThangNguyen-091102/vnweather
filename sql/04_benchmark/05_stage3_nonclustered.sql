/* Giai đoạn 3: HEAP + NONCLUSTERED index phủ (covering). Chạy rồi đo 02_queries.sql. */
USE VNDataPlatform;
GO
EXEC bench.usp_reset_indexes;
GO
CREATE NONCLUSTERED INDEX IX_weather_test_station_date
    ON bench.weather_test (station_id, date_key) INCLUDE (temp_max_c, precipitation_mm);
CREATE NONCLUSTERED INDEX IX_forecast_test_station_date
    ON bench.forecast_test (station_id, target_date_key) INCLUDE (horizon_days, predicted);
GO
