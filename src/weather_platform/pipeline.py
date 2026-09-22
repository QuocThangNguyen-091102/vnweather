"""
pipeline.py - Điều phối toàn bộ quy trình cập nhật và ghi lại lịch sử mỗi lần chạy.

Mỗi lần chạy có một RUN_ID (yyyymmdd_HHMMSS) xuất hiện trong log, trong cột pipeline_run_id của các bảng
staging và mart, trong dwh.dq_check_log và dwh.pipeline_run_log, để truy ra dòng dữ liệu do lần chạy nào nạp.

Mã thoát: 0 = SUCCESS, 1 = PARTIAL (chạy được nhưng có địa điểm/bước lỗi hoặc có phép kiểm tra FAIL),
2 = FAILED (kho dữ liệu không được cập nhật).
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from . import config, db, forecast, ingestion, warehouse
from .data_quality import CheckResult, fetch_quality_metrics, run_sql_checks
from .ingestion import IngestResult

log = logging.getLogger("weather_platform.pipeline")

EXIT_OK, EXIT_PARTIAL, EXIT_FAILED = 0, 1, 2
CRITICAL_STEPS = ("Danh sách địa điểm", "Nạp kho dữ liệu")


def new_run_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


class _RunIdFilter(logging.Filter):
    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


def setup_logging(run_id: str, log_dir: Path = config.LOG_DIR, level: int = logging.INFO) -> None:
    """Ghi log ra màn hình và file logs/daily_update.log, mỗi dòng có RUN_ID."""
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_weather_platform", False):
            root.removeHandler(handler)
            handler.close()
    formatter = logging.Formatter("%(asctime)s [%(run_id)s] %(levelname)s %(message)s")
    for handler in (logging.FileHandler(log_dir / "daily_update.log", encoding="utf-8"), logging.StreamHandler()):
        handler._weather_platform = True  # type: ignore[attr-defined]
        handler.setFormatter(formatter)
        handler.addFilter(_RunIdFilter(run_id))
        root.addHandler(handler)


@dataclass
class RunReport:
    run_id: str
    mode: str
    observations: IngestResult | None = None
    api_forecast: IngestResult | None = None
    dq_results: list[CheckResult] = field(default_factory=list)
    forecast_failed: dict[str, str] = field(default_factory=dict)
    step_errors: dict[str, str] = field(default_factory=dict)

    @property
    def dq_fail_count(self) -> int:
        return sum(1 for r in self.dq_results if not r.passed)

    @property
    def status(self) -> str:
        return decide_status(self)

    @property
    def exit_code(self) -> int:
        return {"SUCCESS": EXIT_OK, "PARTIAL": EXIT_PARTIAL}.get(self.status, EXIT_FAILED)

    def message(self) -> str:
        parts = []
        if self.observations:
            parts.append("Quan trắc: " + self.observations.summary())
        if self.api_forecast:
            parts.append("Dự báo API: " + self.api_forecast.summary())
        if self.dq_results:
            parts.append(f"DQ: {len(self.dq_results) - self.dq_fail_count}/{len(self.dq_results)} PASS")
        if self.forecast_failed:
            parts.append("Mô hình lỗi: " + ", ".join(self.forecast_failed))
        for step, err in self.step_errors.items():
            parts.append(f"{step}: {err}")
        return " | ".join(parts)[:1000]


def decide_status(report: RunReport) -> str:
    """FAILED nếu kho không được cập nhật; PARTIAL nếu có bất kỳ lỗi nào khác; ngược lại SUCCESS."""
    if any(step in report.step_errors for step in CRITICAL_STEPS):
        return "FAILED"
    obs = report.observations
    if obs and obs.total > 0 and obs.ok_count == 0:
        return "FAILED"
    if report.step_errors or report.dq_fail_count or report.forecast_failed:
        return "PARTIAL"
    for result in (report.observations, report.api_forecast):
        if result and result.failed:
            return "PARTIAL"
    return "SUCCESS"


# ----------------------------------------------------------------------------- nhật ký lần chạy
def _log_run_start(conn: Any, run_id: str, mode: str) -> None:
    try:
        conn.cursor().execute(
            "INSERT INTO dwh.pipeline_run_log (run_id, mode, started_at, status) "
            "VALUES (?, ?, SYSDATETIME(), 'RUNNING')", run_id, mode,
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - thiếu bảng nhật ký không được làm dừng pipeline
        conn.rollback()
        log.warning("Không ghi được dwh.pipeline_run_log (đã chạy sql/01_setup/003?): %s", exc)


def _log_run_end(conn: Any, report: RunReport) -> None:
    obs = report.observations
    try:
        conn.cursor().execute(
            "UPDATE dwh.pipeline_run_log SET finished_at = SYSDATETIME(), status = ?, locations_ok = ?, "
            "locations_total = ?, rows_loaded = ?, dq_fail_count = ?, message = ? WHERE run_id = ?",
            report.status, obs.ok_count if obs else None, obs.total if obs else None,
            obs.rows if obs else None, report.dq_fail_count, report.message(), report.run_id,
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        log.warning("Không cập nhật được dwh.pipeline_run_log: %s", exc)


def _step(report: RunReport, conn: Any, name: str, func: Callable[[], Any]) -> Any:
    """Chạy một bước; lỗi được ghi log, hoàn tác phần dang dở và không làm sập các bước sau."""
    try:
        return func()
    except Exception as exc:  # noqa: BLE001
        log.exception("Bước lỗi: %s", name)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        report.step_errors[name] = f"{type(exc).__name__}: {exc}"
        return None


# ----------------------------------------------------------------------------- pipeline
def run_daily(
    mode: str = "incremental",
    today: date | None = None,
    connect: Callable[[], Any] = db.connect,
    log_dir: Path | None = None,
) -> int:
    """Chạy toàn bộ pipeline và trả về mã thoát (0, 1 hoặc 2)."""
    run_id = new_run_id()
    setup_logging(run_id, log_dir or config.LOG_DIR)
    report = RunReport(run_id=run_id, mode=mode)
    log.info("===== Bắt đầu pipeline, chế độ %s =====", mode)
    try:
        conn = connect()
    except Exception:  # noqa: BLE001
        log.exception("Không kết nối được SQL Server")
        return EXIT_FAILED
    try:
        _log_run_start(conn, run_id, mode)
        locations = _step(report, conn, "Danh sách địa điểm", lambda: ingestion.get_locations(conn))
        if locations:
            report.observations = _step(
                report, conn, "Nạp quan trắc",
                lambda: ingestion.ingest_observations(conn, locations, run_id, mode, today),
            )
            report.api_forecast = _step(
                report, conn, "Lưu dự báo Open-Meteo",
                lambda: ingestion.store_api_forecast(conn, locations, run_id, today),
            )
            _step(report, conn, "Nạp kho dữ liệu", lambda: warehouse.load_warehouse(conn))
            results = _step(report, conn, "Kiểm tra chất lượng", lambda: run_sql_checks(conn, run_id))
            report.dq_results = results or []
            for r in report.dq_results:
                if not r.passed:
                    log.error("Kiểm tra FAIL: %s (%d dòng lỗi)", r.check_name, r.bad_rows)
            log.info("Kiểm tra chất lượng: %d/%d PASS",
                     len(report.dq_results) - report.dq_fail_count, len(report.dq_results))
            metrics = _step(report, conn, "Chỉ số chất lượng", lambda: fetch_quality_metrics(conn))
            if metrics:
                log.info("Chỉ số chất lượng: %s", {k: str(v) for k, v in metrics.items()})
            summary = _step(report, conn, "Mô hình dự báo", lambda: forecast.run(conn, run_id))
            if summary is not None:
                report.forecast_failed = summary.failed
                if summary.mae_table is not None:
                    log.info("Sai số MAE (độ C, gộp mọi địa điểm) theo số ngày dự báo trước:\n%s",
                             summary.mae_table.to_string())
        _log_run_end(conn, report)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    log.info("===== Kết thúc: %s (%s) =====", report.status, report.message() or "không có ghi chú")
    return report.exit_code


def main(mode: str = "incremental") -> int:
    return run_daily(mode)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
