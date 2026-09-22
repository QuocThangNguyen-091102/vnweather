# Mô hình dữ liệu

## Star schema của kho dữ liệu

Grain của `fact_weather_daily`: **một dòng = một địa điểm trong một ngày**.

```mermaid
erDiagram
    dim_date ||--o{ fact_weather_daily : "date_key"
    dim_location ||--o{ fact_weather_daily : "location_key"

    dim_date {
        int date_key PK "yyyymmdd"
        date full_date UK
        smallint year_num
        tinyint quarter_num
        tinyint month_num
        nvarchar month_name
        tinyint day_of_month
        tinyint day_of_week
        nvarchar day_name
        bit is_weekend
    }
    dim_location {
        int location_key PK "surrogate key"
        nvarchar location_name
        decimal latitude
        decimal longitude
        nvarchar region_name
        date valid_from
        date valid_to
        bit is_current
    }
    fact_weather_daily {
        int date_key PK,FK
        int location_key PK,FK
        decimal temp_max_c
        decimal temp_min_c
        decimal precipitation_mm
        decimal wind_max_kmh
        datetime2 created_at
        datetime2 updated_at
    }
```

`dim_location` áp dụng **SCD Type 2**: khi tọa độ hoặc vùng của một địa điểm đổi, phiên bản cũ được đóng
(`valid_to` = ngày hiệu lực trừ 1, `is_current` = 0) và một phiên bản mới được mở. Mỗi dòng fact trỏ về phiên bản
địa điểm có hiệu lực tại ngày quan sát.

## Các bảng khác

```mermaid
flowchart TB
    subgraph staging
        R["weather_daily_raw<br/>UNIQUE(location_name, obs_date)"]
        AF["api_forecast_raw<br/>UNIQUE(location_name, base_date, target_date)"]
        LR["location_ref"]
    end
    subgraph dwh
        DD[dim_date]
        DL["dim_location (SCD2)"]
        FT[fact_weather_daily]
        DQ[dq_check_log]
        PR[pipeline_run_log]
    end
    subgraph mart
        FE[forecast_eval]
        FD[forecast_daily]
        V1[v_forecast_vs_actual]
        V2[v_data_quality_metrics]
        V3[v_monthly_weather]
    end
    R --> FT
    LR --> DL
    DD --> FT
    DL --> FT
    FT --> FE
    FT --> FD
    FD --> V1
    AF --> V1
    FT --> V1
    FT --> V2
    R --> V2
    FT --> V3
```

## Vì sao thiết kế như vậy

| Câu hỏi | Trả lời |
|---|---|
| Vì sao có staging, dwh và mart? | Tách việc lấy dữ liệu khỏi việc xử lý: lỗi ở bước biến đổi thì chạy lại từ staging, không phải gọi lại API. Mart có thể dựng lại từ dwh |
| Grain của fact là gì? | Một địa điểm trong một ngày. Mọi phép tổng hợp đều đi từ grain này |
| Vì sao dùng surrogate key? | Tên địa điểm có thể đổi hoặc trùng; khóa số nhỏ, join nhanh, và cho phép lưu nhiều phiên bản lịch sử của cùng một địa điểm (SCD2) |
| Vì sao cần SCD2 cho địa điểm? | Tọa độ đại diện có thể được chỉnh lại. Dữ liệu cũ vẫn phải gắn đúng với tọa độ đã dùng lúc lấy dữ liệu |
| Nếu tọa độ Vũng Tàu đổi thì dữ liệu lịch sử ra sao? | Các dòng fact cũ giữ nguyên, vẫn trỏ về phiên bản cũ. Chỉ dữ liệu từ ngày hiệu lực trở đi trỏ về phiên bản mới. Xem `sql/05_demo/scd2_demo.sql` |
