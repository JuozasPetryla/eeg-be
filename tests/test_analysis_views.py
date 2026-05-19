from datetime import datetime, timedelta
from types import SimpleNamespace

from app.core.analysis_views import build_result_json, summarize_batch_jobs


def make_job(**overrides):
    base_time = datetime(2026, 5, 19, 10, 0, 0)
    data = {
        "status": "completed",
        "queued_at": base_time,
        "started_at": base_time + timedelta(minutes=1),
        "finished_at": base_time + timedelta(minutes=5),
        "error_message": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_build_result_json_rewrites_png_asset_urls() -> None:
    result = build_result_json(
        42,
        {
            "hipnogram": "sleep.png",
            "summary": "ready",
            "nested": {"kept": "as-is"},
        },
    )

    assert result["hipnogram"] == "http://localhost:8000/analysis-jobs/42/assets/hipnogram"
    assert result["summary"] == "ready"
    assert result["nested"] == {"kept": "as-is"}


def test_build_result_json_returns_non_dict_values_unchanged() -> None:
    assert build_result_json(7, ["not", "a", "dict"]) == ["not", "a", "dict"]


def test_summarize_batch_jobs_marks_processing_over_other_states() -> None:
    jobs = [
        make_job(status="queued", started_at=None, finished_at=None),
        make_job(status="processing", finished_at=None),
        make_job(status="failed", error_message="bad data"),
    ]

    summary = summarize_batch_jobs(jobs)

    assert summary["status"] == "processing"
    assert summary["queued_jobs"] == 1
    assert summary["processing_jobs"] == 1
    assert summary["failed_jobs"] == 1
    assert summary["finished_at"] is None
    assert summary["error_message"] == "bad data"


def test_summarize_batch_jobs_marks_partial_failed_when_terminal_mix() -> None:
    jobs = [
        make_job(status="completed"),
        make_job(status="failed", error_message="first"),
        make_job(status="failed", error_message="second"),
        make_job(status="failed", error_message="third"),
        make_job(status="failed", error_message="fourth"),
    ]

    summary = summarize_batch_jobs(jobs)

    assert summary["status"] == "partial_failed"
    assert summary["completed_jobs"] == 1
    assert summary["failed_jobs"] == 4
    assert summary["finished_at"] is not None
    assert summary["error_message"] == "first; second; third"
