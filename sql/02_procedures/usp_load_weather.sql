/* =====================================================================
   usp_load_weather
   Nạp fact_weather_daily từ staging bằng MERGE (nạp tăng dần):
   - Dòng chưa có           : INSERT
   - Dòng có, giá trị đổi   : UPDATE (so sánh bằng EXCEPT nên xử lý đúng NULL)
   - Dòng có, không đổi     : bỏ qua
   Mỗi dòng gắn với phiên bản địa điểm có hiệu lực tại ngày quan sát.
   Thứ tự chạy: usp_load_dim_location_scd2 TRƯỚC, usp_load_weather SAU.
   Kết quả trả về: số dòng INSERT / UPDATE (chạy lại khi dữ liệu không đổi
   thì không trả về dòng nào).
   ===================================================================== */
USE VNDataPlatform;
GO

CREATE OR ALTER PROCEDURE dwh.usp_load_weather
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @changes TABLE (action NVARCHAR(10));

    MERGE dwh.fact_weather_daily AS tgt
    USING (
        SELECT d.date_key, l.location_key,
               s.temp_max_c, s.temp_min_c, s.precipitation_mm, s.wind_max_kmh
        FROM staging.weather_daily_raw AS s
        JOIN dwh.dim_date     AS d ON d.full_date = s.obs_date
        JOIN dwh.dim_location AS l ON l.location_name = s.location_name
                                  AND s.obs_date BETWEEN l.valid_from AND l.valid_to
    ) AS src
        ON  tgt.date_key = src.date_key AND tgt.location_key = src.location_key
    WHEN MATCHED AND EXISTS (
            SELECT src.temp_max_c, src.temp_min_c, src.precipitation_mm, src.wind_max_kmh
            EXCEPT
            SELECT tgt.temp_max_c, tgt.temp_min_c, tgt.precipitation_mm, tgt.wind_max_kmh)
        THEN UPDATE SET
            tgt.temp_max_c       = src.temp_max_c,
            tgt.temp_min_c       = src.temp_min_c,
            tgt.precipitation_mm = src.precipitation_mm,
            tgt.wind_max_kmh     = src.wind_max_kmh,
            tgt.updated_at       = SYSDATETIME()
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (date_key, location_key, temp_max_c, temp_min_c, precipitation_mm, wind_max_kmh)
        VALUES (src.date_key, src.location_key, src.temp_max_c, src.temp_min_c,
                src.precipitation_mm, src.wind_max_kmh)
    OUTPUT $action INTO @changes (action);

    SELECT action, COUNT(*) AS so_dong FROM @changes GROUP BY action;
END;
GO
