from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.analysis_job import AnalysisJob
from app.core.models.analysis_result import AnalysisResult

router = APIRouter(prefix="/analysis-jobs", tags=["analysis-results"])


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
            "result_json": result.result_json,
            "created_at": result.created_at,
        },
    }
