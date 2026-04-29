from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.analysis_views import build_result_json, summarize_batch_jobs
from app.core.database import get_db
from app.core.file_storage import S3_BUCKET, minio_client
from app.core.models.analysis_batch import AnalysisBatch
from app.core.models.analysis_job import AnalysisJob
from app.core.models.analysis_result import AnalysisResult
from app.core.models.eeg_file import EEGFile

router = APIRouter(prefix="/analysis-jobs", tags=["analysis-results"])


def _serialize_grouped_batch(batch: AnalysisBatch, jobs: list[AnalysisJob]) -> dict:
    summary = summarize_batch_jobs(jobs)
    return {
        "id": batch.id,
        "kind": "batch",
        "batch_id": batch.id,
        "eeg_file_id": None,
        "analysis_type": batch.analysis_type,
        "status": summary["status"],
        "model_version": None,
        "error_message": summary["error_message"],
        "queued_at": batch.created_at,
        "started_at": summary["started_at"],
        "finished_at": summary["finished_at"],
        "result_url": f"/analysis-batches/{batch.id}",
        "child_job_count": summary["total_jobs"],
        "queued_child_count": summary["queued_jobs"],
        "processing_child_count": summary["processing_jobs"],
        "completed_child_count": summary["completed_jobs"],
        "failed_child_count": summary["failed_jobs"],
        "file": {
            "id": None,
            "original_filename": f"{summary['total_jobs']} failu paketas",
            "created_at": batch.created_at,
            "uploaded_by_user_id": batch.uploaded_by_user_id,
            "patient_id": None,
        },
    }


def _serialize_single_job(job: AnalysisJob, eeg_file: EEGFile) -> dict:
    return {
        "id": job.id,
        "kind": "job",
        "batch_id": job.batch_id,
        "eeg_file_id": job.eeg_file_id,
        "analysis_type": job.analysis_type,
        "status": job.status,
        "model_version": job.model_version,
        "error_message": job.error_message,
        "queued_at": job.queued_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result_url": f"/analysis-jobs/{job.id}/result",
        "child_job_count": 1,
        "queued_child_count": 1 if job.status == "queued" else 0,
        "processing_child_count": 1 if job.status == "processing" else 0,
        "completed_child_count": 1 if job.status == "completed" else 0,
        "failed_child_count": 1 if job.status == "failed" else 0,
        "file": {
            "id": eeg_file.id,
            "original_filename": eeg_file.original_filename,
            "created_at": eeg_file.created_at,
            "uploaded_by_user_id": eeg_file.uploaded_by_user_id,
            "patient_id": eeg_file.patient_id,
        },
    }


@router.get("/")
def list_analysis_jobs(
    analysis_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    uploaded_by_user_id: Optional[int] = Query(None),
    grouped: bool = Query(False),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(AnalysisJob, EEGFile).join(EEGFile, EEGFile.id == AnalysisJob.eeg_file_id)

    if analysis_type is not None:
        query = query.filter(AnalysisJob.analysis_type == analysis_type)

    if status is not None:
        query = query.filter(AnalysisJob.status == status)

    if uploaded_by_user_id is not None:
        query = query.filter(EEGFile.uploaded_by_user_id == uploaded_by_user_id)

    if not grouped:
        rows = (
            query.order_by(
                AnalysisJob.queued_at.desc(),
                AnalysisJob.id.desc(),
            )
            .limit(limit)
            .all()
        )
        return {"jobs": [_serialize_single_job(job, eeg_file) for job, eeg_file in rows]}

    standalone_rows = (
        query.filter(AnalysisJob.batch_id.is_(None))
        .order_by(AnalysisJob.queued_at.desc(), AnalysisJob.id.desc())
        .limit(limit)
        .all()
    )

    batch_query = db.query(AnalysisBatch)
    if analysis_type is not None:
        batch_query = batch_query.filter(AnalysisBatch.analysis_type == analysis_type)
    if uploaded_by_user_id is not None:
        batch_query = batch_query.filter(AnalysisBatch.uploaded_by_user_id == uploaded_by_user_id)

    batches = batch_query.order_by(AnalysisBatch.created_at.desc(), AnalysisBatch.id.desc()).limit(limit).all()

    entries = [_serialize_single_job(job, eeg_file) for job, eeg_file in standalone_rows]
    for batch in batches:
        jobs = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.batch_id == batch.id)
            .order_by(AnalysisJob.queued_at.asc(), AnalysisJob.id.asc())
            .all()
        )
        if not jobs:
            continue

        batch_entry = _serialize_grouped_batch(batch, jobs)
        if status is not None and batch_entry["status"] != status:
            continue
        entries.append(batch_entry)

    entries.sort(
        key=lambda entry: (
            entry["queued_at"] or entry["started_at"] or entry["finished_at"],
            entry["id"],
        ),
        reverse=True,
    )

    return {"jobs": entries[:limit]}


@router.get("/{job_id}/result")
def get_analysis_result(job_id: int, db: Session = Depends(get_db)):
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    result = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.analysis_job_id == job_id)
        .first()
    )

    if not result:
        return {
            "job": {
                "id": job.id,
                "batch_id": job.batch_id,
                "eeg_file_id": job.eeg_file_id,
                "analysis_type": job.analysis_type,
                "status": job.status,
                "model_version": job.model_version,
                "error_message": job.error_message,
                "queued_at": job.queued_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
            },
            "result": None,
            "message": "Result not available yet",
        }

    return {
        "job": {
            "id": job.id,
            "batch_id": job.batch_id,
            "eeg_file_id": job.eeg_file_id,
            "analysis_type": job.analysis_type,
            "status": job.status,
            "model_version": job.model_version,
            "error_message": job.error_message,
            "queued_at": job.queued_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        },
        "result": {
            "id": result.id,
            "analysis_job_id": result.analysis_job_id,
            "result_json": build_result_json(job.id, result.result_json),
            "created_at": result.created_at,
        },
    }


@router.get("/{job_id}/assets/{asset_name}")
def get_analysis_asset(job_id: int, asset_name: str, db: Session = Depends(get_db)):
    result = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.analysis_job_id == job_id)
        .first()
    )

    if not result or not isinstance(result.result_json, dict):
        raise HTTPException(status_code=404, detail="Analysis result not found")

    object_key = result.result_json.get(asset_name)
    if not isinstance(object_key, str):
        raise HTTPException(status_code=404, detail="Asset not found")

    try:
        obj = minio_client.get_object(S3_BUCKET, object_key)
        return StreamingResponse(obj, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch asset: {e}")
