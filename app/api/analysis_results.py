from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.file_storage import minio_client, S3_BUCKET
from app.core.models.analysis_job import AnalysisJob
from app.core.models.analysis_result import AnalysisResult
from app.core.models.eeg_file import EEGFile

router = APIRouter(prefix="/analysis-jobs", tags=["analysis-results"])


def _build_result_json(job_id: int, result_json: dict) -> dict:
    if not isinstance(result_json, dict):
        return result_json

    image_result = {}
    is_image_map = True

    for key, value in result_json.items():
        if not isinstance(value, str) or not value.endswith(".png"):
            is_image_map = False
            break
        image_result[key] = f"http://localhost:8000/analysis-jobs/{job_id}/assets/{key}"

    return image_result if is_image_map else result_json


@router.get("/")
def list_analysis_jobs(
    analysis_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    uploaded_by_user_id: Optional[int] = Query(None),
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

    rows = (
        query.order_by(
            AnalysisJob.queued_at.desc(),
            AnalysisJob.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return {
        "jobs": [
            {
                "id": job.id,
                "eeg_file_id": job.eeg_file_id,
                "analysis_type": job.analysis_type,
                "status": job.status,
                "model_version": job.model_version,
                "error_message": job.error_message,
                "queued_at": job.queued_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "result_url": f"/analysis-jobs/{job.id}/result",
                "file": {
                    "id": eeg_file.id,
                    "original_filename": eeg_file.original_filename,
                    "created_at": eeg_file.created_at,
                    "uploaded_by_user_id": eeg_file.uploaded_by_user_id,
                    "patient_id": eeg_file.patient_id,
                },
            }
            for job, eeg_file in rows
        ]
    }


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
            "result_json": _build_result_json(job.id, result.result_json),
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
