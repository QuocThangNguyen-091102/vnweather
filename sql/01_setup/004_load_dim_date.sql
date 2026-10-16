/* =====================================================================
   004 - Nạp bảng ngày dim_date cho giai đoạn 2020-2030 (4.018 dòng)
   Chỉ nạp khi bảng còn rỗng.
   Thứ trong tuần tính từ 01/01/1900 (Thứ Hai) nên không phụ thuộc cài đặt
   ngôn ngữ hay ngày đầu tuần của máy.
   ===================================================================== */
USE VNDataPlatform;
GO

IF NOT EXISTS (SELECT 1 FROM dwh.dim_date)
BEGIN
    ;WITH d AS (
        SELECT CAST('2020-01-01' AS DATE) AS dt
        UNION ALL
        SELECT DATEADD(DAY, 1, dt) FROM d WHERE dt < '2030-12-31'
    )
    INSERT INTO dwh.dim_date
        (date_key, full_date, year_num, quarter_num, month_num, month_name,
         day_of_month, day_of_week, day_name, is_weekend)
    SELECT
        CONVERT(INT, CONVERT(CHAR(8), dt, 112)),
        dt,
        YEAR(dt),
        DATEPART(QUARTER, dt),
        MONTH(dt),
        N'Tháng ' + CAST(MONTH(dt) AS NVARCHAR(2)),
        DAY(dt),
        x.dow,
        CHOOSE(x.dow, N'Thứ Hai', N'Thứ Ba', N'Thứ Tư', N'Thứ Năm',
                      N'Thứ Sáu', N'Thứ Bảy', N'Chủ Nhật'),
        CASE WHEN x.dow >= 6 THEN 1 ELSE 0 END
    FROM d
    CROSS APPLY (SELECT (DATEDIFF(DAY, '19000101', dt) % 7) + 1 AS dow) AS x
    OPTION (MAXRECURSION 0);
END
GO

SELECT COUNT(*) AS so_dong_dim_date FROM dwh.dim_date;   -- kỳ vọng: 4018
GO
