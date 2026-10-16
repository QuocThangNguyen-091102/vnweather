# Kết quả đo hiệu năng index

Môi trường: SQL Server 2022 Developer, máy cá nhân.
Dữ liệu: bảng `bench.weather_test` khoảng 4,9 triệu dòng **giả lập** (giá trị ngẫu nhiên),
không phải dữ liệu thời tiết thật. Số đo có dao động giữa các lần chạy.

| Truy vấn | Trạng thái | Số lần đọc | CPU | Elapsed |
|---|---|---|---|---|
| A (tra cứu 1 trạm, 1 năm) | Chưa có index | 19.352 | 671 ms | 105 ms |
| A | Nonclustered index (station_id, date_key) | 5 | 0 ms | 0 ms |
| B (tổng hợp toàn bảng) | Chưa có index | 19.352 | 1.328 - 2.060 ms | 178 - 293 ms |
| B | Nonclustered columnstore index | ~4.000 (lob) | 203 - 235 ms | 191 - 221 ms |

## Kết luận

- Nonclustered index giúp truy vấn tra cứu giảm từ 19.352 xuống 5 logical reads
  (khoảng 3.870 lần).
- Columnstore index giúp truy vấn tổng hợp giảm số lần đọc khoảng 4,8 lần và CPU khoảng
  6 đến 9 lần, nhưng thời gian thực gần như không đổi vì bản không index đã được chạy
  song song nhiều luồng.
- Dữ liệu giả lập ngẫu nhiên nén kém, nên lợi ích của columnstore trên dữ liệu thật
  có thể cao hơn.
