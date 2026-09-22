import re
from datetime import date

import pytest

from weather_platform import forecast, ingestion, pipeline, warehouse
from weather_platform.data_quality import CheckResult
from weather_platform.ingestion import IngestResult
from weather_platform.pipeline import RunReport, decide_status, new_run_id


def report(**kw):
    return RunReport(run_id="R", mode="incremental", **kw)


def test_run_id_has_timestamp_format():
    assert re.fullmatch(r"\d{8}_\d{6}", new_run_id())


def test_success_when_nothing_failed():
    r = report(observations=IngestResult(total=5, loaded=["a"] * 5),
               api_forecast=IngestResult(total=5, loaded=["a"] * 5),
               dq_results=[CheckResult("x", 0, "PASS")])
    assert decide_status(r) == "SUCCESS" and r.exit_code == 0


def test_partial_when_one_location_fails_but_others_load():
    r = report(observations=IngestResult(total=5, loaded=["a"] * 4, failed={"b": "lỗi"}))
    assert decide_status(r) == "PARTIAL" and r.exit_code == 1
    assert "4/5" in r.message()


def test_partial_when_a_data_quality_check_fails():
    r = report(observations=IngestResult(total=1, loaded=["a"]), dq_results=[CheckResult("x", 3, "FAIL")])
    assert decide_status(r) == "PARTIAL" and r.dq_fail_count == 1


def test_partial_when_model_step_fails():
    r = report(observations=IngestResult(total=1, loaded=["a"]), step_errors={"Mô hình dự báo": "lỗi"})
    assert decide_status(r) == "PARTIAL"


def test_failed_when_warehouse_load_fails():
    r = report(observations=IngestResult(total=1, loaded=["a"]), step_errors={"Nạp kho dữ liệu": "lỗi"})
    assert decide_status(r) == "FAILED" and r.exit_code == 2


def test_failed_when_no_location_could_be_ingested():
    r = report(observations=IngestResult(total=2, failed={"a": "x", "b": "y"}))
    assert decide_status(r) == "FAILED"


# --------------------------------------------------------------------------- chạy cả pipeline với các bước giả
@pytest.fixture
def wired(monkeypatch, fake_conn):
    calls = []
    monkeypatch.setattr(ingestion, "get_locations", lambda c: [("A", 1.0, 2.0), ("B", 3.0, 4.0)])
    monkeypatch.setattr(ingestion, "ingest_observations",
                        lambda c, locs, run_id, mode, today: calls.append(("obs", mode)) or
                        IngestResult(total=2, loaded=["A", "B"], rows=10))
    monkeypatch.setattr(ingestion, "store_api_forecast",
                        lambda c, locs, run_id, today: calls.append(("api",)) or IngestResult(total=2, loaded=["A", "B"]))
    monkeypatch.setattr(warehouse, "load_warehouse", lambda c: calls.append(("dwh",)) or {})
    monkeypatch.setattr(pipeline, "run_sql_checks", lambda c, run_id: [CheckResult("x", 0, "PASS")])
    monkeypatch.setattr(pipeline, "fetch_quality_metrics", lambda c: {"freshness_days": 7})
    monkeypatch.setattr(forecast, "run", lambda c, run_id: calls.append(("model",)) or forecast.ForecastSummary(locations_ok=2))
    return calls


def test_pipeline_runs_steps_in_order_and_logs_the_run(wired, fake_conn, tmp_path):
    code = pipeline.run_daily("incremental", date(2026, 9, 21), connect=lambda: fake_conn, log_dir=tmp_path)
    assert code == 0
    assert [c[0] for c in wired] == ["obs", "api", "dwh", "model"]          # SCD2/fact nạp trước khi chạy mô hình
    assert fake_conn.closed
    start = fake_conn.sql_containing("INSERT INTO dwh.pipeline_run_log")
    end = fake_conn.sql_containing("UPDATE dwh.pipeline_run_log")
    assert len(start) == 1 and len(end) == 1
    assert end[0][1][0] == "SUCCESS"
    assert (tmp_path / "daily_update.log").read_text(encoding="utf-8").count("Bắt đầu pipeline") == 1


def test_pipeline_history_mode_is_passed_to_ingestion(wired, fake_conn, tmp_path):
    pipeline.run_daily("history", date(2026, 9, 21), connect=lambda: fake_conn, log_dir=tmp_path)
    assert ("obs", "history") in wired


def test_pipeline_continues_after_a_failing_step_and_reports_partial(wired, monkeypatch, fake_conn, tmp_path):
    def boom(conn, run_id):
        raise RuntimeError("mô hình lỗi")

    monkeypatch.setattr(forecast, "run", boom)
    code = pipeline.run_daily("incremental", date(2026, 9, 21), connect=lambda: fake_conn, log_dir=tmp_path)
    assert code == 1 and fake_conn.rollbacks >= 1
    assert fake_conn.sql_containing("UPDATE dwh.pipeline_run_log")[0][1][0] == "PARTIAL"


def test_pipeline_returns_failed_when_warehouse_load_breaks(wired, monkeypatch, fake_conn, tmp_path):
    def boom(conn):
        raise RuntimeError("MERGE lỗi")

    monkeypatch.setattr(warehouse, "load_warehouse", boom)
    code = pipeline.run_daily("incremental", date(2026, 9, 21), connect=lambda: fake_conn, log_dir=tmp_path)
    assert code == 2


def test_pipeline_returns_failed_when_database_is_unreachable(tmp_path):
    def no_connect():
        raise OSError("không kết nối được")

    assert pipeline.run_daily("incremental", connect=no_connect, log_dir=tmp_path) == 2
