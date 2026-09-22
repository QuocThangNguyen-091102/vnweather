/* Giai đoạn 4: HEAP + NONCLUSTERED COLUMNSTORE index. Chạy rồi đo 02_queries.sql. */
USE VNDataPlatform;
GO
EXEC bench.usp_reset_indexes;
GO
CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_weather_test
    ON bench.weather_test (station_id, date_key, temp_max_c, temp_min_c, precipitation_mm);
CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_forecast_test
    ON bench.forecast_test (station_id, target_date_key, horizon_days, predicted);
GO
