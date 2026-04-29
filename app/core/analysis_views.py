from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.core.models.analysis_job import AnalysisJob


def build_result_json(job_id: int, result_json: dict[str, Any] | Any) -> dict[str, Any] | Any:
    if not isinstance(result_json, dict):
        return result_json

    processed_result: dict[str, Any] = {}
    for key, value in result_json.items():
        if isinstance(value, str) and value.endswith(".png"):
            processed_result[key] = f"http://localhost:8000/analysis-jobs/{job_id}/assets/{key}"
        else:
            processed_result[key] = value

    return processed_result


def summarize_batch_jobs(jobs: Sequence[AnalysisJob]) -> dict[str, Any]:
    total = len(jobs)
    queued = sum(job.status == "queued" for job in jobs)
    processing = sum(job.status == "processing" for job in jobs)
    completed = sum(job.status == "completed" for job in jobs)
    failed = sum(job.status == "failed" for job in jobs)

    if processing > 0:
        status = "processing"
    elif queued > 0:
        status = "queued"
    elif failed > 0 and completed > 0:
        status = "partial_failed"
    elif failed > 0:
        status = "failed"
    else:
        status = "completed"

    started_times = [job.started_at for job in jobs if isinstance(job.started_at, datetime)]
    finished_times = [job.finished_at for job in jobs if isinstance(job.finished_at, datetime)]
    queued_times = [job.queued_at for job in jobs if isinstance(job.queued_at, datetime)]
    error_messages = [job.error_message for job in jobs if job.error_message]

    return {
        "status": status,
        "total_jobs": total,
        "queued_jobs": queued,
        "processing_jobs": processing,
        "completed_jobs": completed,
        "failed_jobs": failed,
        "queued_at": min(queued_times) if queued_times else None,
        "started_at": min(started_times) if started_times else None,
        "finished_at": max(finished_times) if finished_times and completed + failed == total else None,
        "error_message": "; ".join(error_messages[:3]) if error_messages else None,
    }
