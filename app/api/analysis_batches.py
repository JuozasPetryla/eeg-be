from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.analysis_views import build_result_json, summarize_batch_jobs
from app.core.database import get_db
from app.core.models.analysis_batch import AnalysisBatch
from app.core.models.analysis_job import AnalysisJob
from app.core.models.analysis_result import AnalysisResult
from app.core.models.eeg_file import EEGFile

router = APIRouter(prefix="/analysis-batches", tags=["analysis-batches"])


@router.get("/{batch_id}")
def get_analysis_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(AnalysisBatch).filter(AnalysisBatch.id == batch_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Analysis batch not found")

    rows = (
        db.query(AnalysisJob, EEGFile, AnalysisResult)
        .join(EEGFile, EEGFile.id == AnalysisJob.eeg_file_id)
        .outerjoin(AnalysisResult, AnalysisResult.analysis_job_id == AnalysisJob.id)
        .filter(AnalysisJob.batch_id == batch_id)
        .order_by(AnalysisJob.queued_at.asc(), AnalysisJob.id.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Analysis batch has no jobs")

    jobs = [job for job, _, _ in rows]
    summary = summarize_batch_jobs(jobs)

    return {
        "batch": {
            "id": batch.id,
            "uploaded_by_user_id": batch.uploaded_by_user_id,
            "analysis_type": batch.analysis_type,
            "created_at": batch.created_at,
            **summary,
        },
        "jobs": [
            {
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
                "result_url": f"/analysis-jobs/{job.id}/result",
                "file": {
                    "id": eeg_file.id,
                    "original_filename": eeg_file.original_filename,
                    "created_at": eeg_file.created_at,
                    "uploaded_by_user_id": eeg_file.uploaded_by_user_id,
                    "patient_id": eeg_file.patient_id,
                },
                "result": (
                    {
                        "id": result.id,
                        "analysis_job_id": result.analysis_job_id,
                        "result_json": build_result_json(job.id, result.result_json),
                        "created_at": result.created_at,
                    }
                    if result is not None
                    else None
                ),
            }
            for job, eeg_file, result in rows
        ],
    }
