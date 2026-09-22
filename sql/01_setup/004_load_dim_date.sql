/* =====================================================================
   004 - Nạp bảng ngày dim_date từ 2020-01-01 đến @end_date (mặc định 2035-12-31)
   Chỉ thêm các ngày CHƯA có nên chạy lại an toàn. Muốn mở rộng lịch, tăng @end_date rồi chạy lại.
   Thứ trong tuần tính từ 01/01/1900 (Thứ Hai) nên không phụ thuộc cài đặt ngôn ngữ hay ngày đầu tuần.
   Giới hạn: fact chỉ nạp được các ngày có trong dim_date. Nếu ngày dữ liệu vượt @end_date, phép kiểm tra
   "Staging không khớp dimension" sẽ báo FAIL.
   ===================================================================== */
USE VNDataPlatform;
GO

DECLARE @start_date DATE = '2020-01-01';
DECLARE @end_date   DATE = '2035-12-31';

;WITH d AS (
    SELECT @start_date AS dt
    UNION ALL
    SELECT DATEADD(DAY, 1, dt) FROM d WHERE dt < @end_date
)
INSERT INTO dwh.dim_date
    (date_key, full_date, year_num, quarter_num, month_num, month_name,
     day_of_month, day_of_week, day_name, is_weekend)
SELECT
    CONVERT(INT, CONVERT(CHAR(8), d.dt, 112)),
    d.dt,
    YEAR(d.dt),
    DATEPART(QUARTER, d.dt),
    MONTH(d.dt),
    N'Tháng ' + CAST(MONTH(d.dt) AS NVARCHAR(2)),
    DAY(d.dt),
    x.dow,
    CHOOSE(x.dow, N'Thứ Hai', N'Thứ Ba', N'Thứ Tư', N'Thứ Năm',
                  N'Thứ Sáu', N'Thứ Bảy', N'Chủ Nhật'),
    CASE WHEN x.dow >= 6 THEN 1 ELSE 0 END
FROM d
CROSS APPLY (SELECT (DATEDIFF(DAY, '19000101', d.dt) % 7) + 1 AS dow) AS x
WHERE NOT EXISTS (SELECT 1 FROM dwh.dim_date AS t
                  WHERE t.date_key = CONVERT(INT, CONVERT(CHAR(8), d.dt, 112)))
OPTION (MAXRECURSION 0);
GO

SELECT COUNT(*) AS so_dong_dim_date, MIN(full_date) AS tu_ngay, MAX(full_date) AS den_ngay
FROM dwh.dim_date;   -- kỳ vọng: 5844 dòng, 2020-01-01 đến 2035-12-31
GO
