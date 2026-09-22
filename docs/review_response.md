# Đối chiếu góp ý với việc đã làm

Ký hiệu: **Xong** = đã làm và có cách kiểm chứng; **Một phần** = làm được một phần, nêu rõ phần còn lại;
**Chưa** = chưa làm, nêu lý do. Cột "Kiểm chứng" nói rõ đã kiểm chứng bằng cách nào.

## Phase 1: bắt buộc

| # | Góp ý | Trạng thái | Đã làm | Kiểm chứng |
|---|---|---|---|---|
| 14 | `.gitinore` sai tên; `venv/`, `__pycache__/`, `logs/` nằm trong archive | Xong | Có `.gitignore` đúng tên (`venv/`, `__pycache__/`, `*.py[cod]`, `logs/`, `.env`...). Bản giao không chứa `venv`, `__pycache__`, `logs` | Liệt kê nội dung file zip |
| 12 | README không khớp cấu trúc thực | Xong | README viết lại theo đúng cây thư mục bàn giao | Đối chiếu README với cây thư mục |
| 13 | README dẫn ảnh `docs/dashboard_overview.png` không tồn tại | Một phần | Bỏ liên kết ảnh hỏng; sơ đồ dùng Mermaid (GitHub tự vẽ). **Chưa có ảnh chụp dashboard**: ảnh phải chụp từ dữ liệu thật của bạn, có chỗ sẵn ở `docs/screenshots/` | Kiểm tra cú pháp Mermaid |
| 1 | Hai hệ thống chọn địa điểm (sidebar và tab Tổng quan) | Xong | Một bộ lọc chung ở thanh bên (Địa điểm gồm "Tất cả địa điểm", Khoảng năm). Mỗi tab ghi rõ bộ lọc nào áp dụng | Chạy dashboard bằng bộ kiểm thử của Streamlit với DB giả, đổi bộ lọc, không lỗi |
| 5 | Ngưỡng P95 tính trên toàn bộ dữ liệu, không thống nhất với khoảng năm chọn | Xong | Ngưỡng tính từ giai đoạn tham chiếu cố định 2020 đến 2025 (`config.py`), hiển thị trên giao diện | `tests/test_analytics.py` (đổi dữ liệu ngoài giai đoạn tham chiếu thì ngưỡng không đổi; bản cũ bị FAIL khi thử làm hỏng có chủ đích) |
| 6 | "Mưa rất to ≥ 50 mm" là thuật ngữ chuyên môn | Xong | Đổi thành "Ngày có lượng mưa ≥ X mm", ghi rõ là ngưỡng phân tích của đề tài; người dùng chỉnh được ngưỡng | Đọc giao diện; kiểm thử ngưỡng bao gồm biên (≥) |
| 7 | Tab "Xu hướng theo mùa" không phân tích mùa | Xong | Đổi tên thành "Xu hướng theo tháng & năm" | Đọc giao diện |
| 8 | "Huấn luyện AI/mô hình" sai thuật ngữ | Xong | Đổi thành "ước lượng mô hình" ở README, docs, docstring, log | Tìm chuỗi trong mã |
| 31 | KPI "Dữ liệu mới nhất" gây hiểu nhầm | Xong | "Ngày dữ liệu gần nhất" cộng KPI "Độ trễ dữ liệu" (kèm chú thích: nguồn trễ khoảng 7 ngày) | Chạy dashboard với DB giả |

## Phase 2: Data Engineering

| # | Góp ý | Trạng thái | Đã làm | Kiểm chứng |
|---|---|---|---|---|
| 3, 10 | Đối soát staging và fact theo khóa, không chỉ so số dòng | Xong (SQL chưa chạy thử) | Ba phép kiểm tra: thiếu ở fact, dư ở fact, giá trị khác nhau (so cả 4 chỉ số, an toàn với NULL) | **Chưa chạy trên SQL Server** (không có trong môi trường phát triển). Cần chạy `sql/05_demo/dq_break_test.sql` để thấy FAIL đúng chỗ |
| 4 | Thiếu chỉ số chất lượng (completeness, freshness, coverage...) | Xong (SQL chưa chạy thử) | View `mart.v_data_quality_metrics` và hiển thị ở tab "Chất lượng dữ liệu"; độ trễ nguồn là chỉ số riêng | Dashboard kiểm tra với DB giả; view SQL chưa chạy trên SQL Server |
| 22 | Thiếu kiểm tra SCD2 | Xong (SQL chưa chạy thử) | Ba phép kiểm tra: đúng 1 bản ghi hiện hành, không chồng lấn, `valid_from <= valid_to`. Use case Vũng Tàu nằm trong `docs/decisions.md` | Chưa chạy trên SQL Server |
| 19, 27 | Thiếu run id, lineage | Xong | `RUN_ID` trong log, staging, bảng dự báo, `dq_check_log` và bảng mới `pipeline_run_log`. Fact chưa lưu `run_id` | `tests/test_pipeline.py`, `tests/test_ingestion.py` |
| 20 | Staging không ràng buộc duy nhất | Xong (SQL chưa chạy thử) | `UNIQUE (location_name, obs_date)`, kèm giải thích vì sao vẫn giữ phép kiểm tra trùng khóa | Chưa chạy trên SQL Server |
| 16, 36 | Chuỗi kết nối lặp ở 4 nơi | Xong | `config.py` và `db.py`, đọc từ biến môi trường hoặc `.env`; có `.env.example` | `tests/test_config.py` |
| 35 | `requirements.txt` quá lỏng | Xong | Ghim phiên bản lấy từ `venv` thật của bạn (Python 3.11.9) | Cài mới toàn bộ từ file này và chạy kiểm thử |
| 17 | `load_history.py` trùng logic với `daily_update.py` | Xong | Chọn cách 2: hai điểm vào, một hàm nạp chung; khác nhau ở chế độ `history` và `incremental` | `tests/test_ingestion.py` (hai chế độ) |
| 18 | Staging chưa thật sự "raw" | Một phần | Ghi rõ trong tài liệu đây là landing/staging có cấu trúc, không lưu JSON. Giữ nguyên tên bảng để không phá database đang chạy | Đọc `docs/decisions.md` |
| 21 | MERGE cần hiểu đánh đổi | Xong | Giữ MERGE, thêm `HOLDLOCK`, ghi đánh đổi và khi nào nên đổi sang UPDATE + INSERT | Chưa chạy trên SQL Server |
| 23 | `dim_date` cứng đến 2030 | Xong | Đến 2035, chạy lại chỉ thêm ngày còn thiếu; nêu trong giới hạn; ngày vượt phạm vi bị phép kiểm tra bắt | Chưa chạy trên SQL Server |

## Phase 3: dự báo

| # | Góp ý | Trạng thái | Đã làm | Kiểm chứng |
|---|---|---|---|---|
| 2 | Đánh giá không gắn với bộ lọc địa điểm | Xong | Hướng B: lưu đánh giá theo từng địa điểm và một dòng gộp `ALL`; dashboard lọc theo địa điểm | `tests/test_forecast.py` (từng địa điểm và gộp) |
| 11 | Chỉ hiện MAE | Xong | Bảng Mô hình, Ngày dự báo trước, MAE, RMSE, số quan sát; biểu đồ chọn MAE hoặc RMSE | Dashboard kiểm tra với DB giả; công thức RMSE có kiểm thử |
| 9 | Ca biên: `phi = NaN`, chuỗi ngắn, thiếu dữ liệu | Xong | `estimate_phi` trả về 0 khi không xác định; chuỗi ngắn ném lỗi rõ ràng; ngày thiếu số đo bị bỏ qua; mỗi địa điểm lỗi riêng, không ảnh hưởng nơi khác | `tests/test_forecast.py`, `tests/test_ingestion.py` (giá trị null từ API) |
| 10 | Tài liệu hóa kiểm thử ngược | Xong | `docs/forecast_methodology.md` với sơ đồ, bước 7 ngày, kiểm soát rò rỉ | Kiểm thử rò rỉ có sẵn, đã thử làm hỏng có chủ đích để chắc nó bắt được lỗi |

## Phase 4: engineering

| # | Góp ý | Trạng thái | Đã làm | Kiểm chứng |
|---|---|---|---|---|
| 34 | Thiếu kiểm thử tự động | Xong (phần Python) | 96 kiểm thử pytest cho ingestion, chất lượng dữ liệu, dự báo, phân tích, pipeline, cấu hình. **Không bao phủ mã SQL** | `python -m pytest` |
| 15 | `run_daily.bat` hard-code đường dẫn | Xong | `scripts\run_daily.bat` dùng `%~dp0`, cho phép đổi Python qua `PYTHON_EXE` | Đọc file; **chưa chạy thử trên Windows** |
| 26 | Lỗi từng phần chưa rõ | Xong | Mỗi địa điểm một transaction, log `n/5 địa điểm thành công`, trạng thái SUCCESS/PARTIAL/FAILED và mã thoát 0/1/2 | `tests/test_ingestion.py`, `tests/test_pipeline.py` |
| 28 | Cache 10 phút, thiếu nút làm mới | Xong | Nút "Làm mới dữ liệu" | Chạy dashboard với DB giả |
| 29 | Dashboard nuốt lỗi | Xong | Phân biệt: chưa tạo view / cột, và lỗi truy vấn thật (hiện nguyên nhân) | Kiểm thử Streamlit với DB giả cho từng tình huống |
| 37 | Cấu trúc thư mục | Xong (gần đúng) | `src/weather_platform/`, `dashboard/`, `sql/`, `tests/`, `docs/`, `scripts/`. Sơ đồ dùng Mermaid trong Markdown thay cho ảnh PNG | Đối chiếu cây thư mục |
| 24 | Benchmark chưa gần workload thật | Một phần | Có truy vấn A đến D và bốn cấu trúc (heap, clustered, nonclustered, columnstore), kèm script dựng. **Số đo mới chưa có**: `notes.md` ghi rõ ô nào đã đo, ô nào chưa | Cần chạy trên SQL Server |
| 25 | "Nhanh X lần" quá mạnh | Xong | Diễn đạt lại: logical reads giảm mạnh trên khối lượng thử nghiệm, thời gian thực cần đánh giá thêm | Đọc README và `notes.md` |

## Phase 5: giao diện

| # | Góp ý | Trạng thái | Đã làm |
|---|---|---|---|
| 30 | Thứ bậc thông tin | Một phần | KPI xếp lại theo mức quan trọng, mỗi tab có ghi chú phạm vi bộ lọc. Chưa thiết kế lại toàn bộ bố cục |
| 32 | Ranh giới thực tế/dự báo | Xong | Vạch đứng và vùng tô màu từ ngày dữ liệu cuối, chú thích "Từ đây là dự báo" |
| 33 | Tên mô hình thân thiện | Xong | "Khí hậu + hiệu chỉnh AR(1)" v.v., kèm giải thích; tên trong database giữ nguyên |
| 38, 39 | Sơ đồ mô hình dữ liệu, từ điển dữ liệu | Xong | `docs/data_model.md` (Mermaid) và `docs/data_dictionary.md` |

## Các mục không làm (theo chính góp ý)

Mục 40 và 41 (không thêm học sâu, animation, dark mode, chatbot, deploy đám mây chỉ để có link) được giữ nguyên:
dự án không có những thứ này.

## Những việc bạn cần tự làm

1. Chạy các file SQL trên database (nâng cấp theo `sql/README.md`) và xác nhận không lỗi cú pháp: đây là phần **chưa
   được chạy thử** trong quá trình sửa.
2. Chạy pipeline một lần (`python -m weather_platform.daily_update`), kiểm tra 14 phép kiểm tra PASS.
3. Chạy `sql/05_demo/dq_break_test.sql` để thấy các phép đối soát FAIL đúng chỗ.
4. Chụp ảnh dashboard từ dữ liệu thật, đặt vào `docs/screenshots/` và thêm vào README.
5. Nếu đã từng `git add` thư mục `venv`: chạy `git rm -r --cached venv` trước khi commit bản mới.
