import os
import uuid
from collections.abc import Sequence
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.file_storage import S3_BUCKET, ensure_bucket_exists, minio_client
from app.core.models.analysis_batch import AnalysisBatch
from app.core.models.analysis_job import AnalysisJob
from app.core.models.eeg_file import EEGFile

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {"edf", "csv"}


def _validate_analysis_type(analysis_type: str) -> None:
    if analysis_type not in {"day", "night"}:
        raise HTTPException(status_code=400, detail="analysis_type must be 'day' or 'night'")


def _validate_file(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    return ext


def _serialize_file(eeg_file: EEGFile) -> dict:
    return {
        "id": eeg_file.id,
        "uploaded_by_user_id": eeg_file.uploaded_by_user_id,
        "patient_id": eeg_file.patient_id,
        "original_filename": eeg_file.original_filename,
        "file_type": eeg_file.file_type,
        "file_size_bytes": eeg_file.file_size_bytes,
        "object_storage_key": eeg_file.object_storage_key,
        "created_at": eeg_file.created_at,
    }


def _serialize_job(analysis_job: AnalysisJob) -> dict:
    return {
        "id": analysis_job.id,
        "eeg_file_id": analysis_job.eeg_file_id,
        "batch_id": analysis_job.batch_id,
        "analysis_type": analysis_job.analysis_type,
        "status": analysis_job.status,
        "model_version": analysis_job.model_version,
        "error_message": analysis_job.error_message,
        "queued_at": analysis_job.queued_at,
        "started_at": analysis_job.started_at,
        "finished_at": analysis_job.finished_at,
        "result_url": f"/analysis-jobs/{analysis_job.id}/result",
    }


def _serialize_batch(batch: AnalysisBatch, jobs: Sequence[AnalysisJob]) -> dict:
    return {
        "id": batch.id,
        "uploaded_by_user_id": batch.uploaded_by_user_id,
        "analysis_type": batch.analysis_type,
        "created_at": batch.created_at,
        "child_job_count": len(jobs),
    }


async def _store_file_and_job(
    *,
    uploaded_by_user_id: int,
    patient_id: int | None,
    analysis_type: str,
    file: UploadFile,
    db: Session,
    batch_id: int | None = None,
) -> tuple[EEGFile, AnalysisJob]:
    ext = _validate_file(file)

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    object_name = f"uploads/{uuid.uuid4()}.{ext}"
    minio_client.put_object(
        bucket_name=S3_BUCKET,
        object_name=object_name,
        data=file.file,
        length=file_size,
        content_type=file.content_type or "application/octet-stream",
    )

    eeg_file = EEGFile(
        uploaded_by_user_id=uploaded_by_user_id,
        patient_id=patient_id,
        original_filename=file.filename,
        file_type=ext,
        file_size_bytes=file_size,
        object_storage_key=object_name,
    )
    db.add(eeg_file)
    db.flush()

    analysis_job = AnalysisJob(
        eeg_file_id=eeg_file.id,
        batch_id=batch_id,
        analysis_type=analysis_type,
        status="queued",
    )
    db.add(analysis_job)
    db.flush()

    return eeg_file, analysis_job


@router.post("/upload")
async def upload_eeg_file(
    uploaded_by_user_id: int = Form(...),
    patient_id: int | None = Form(None),
    analysis_type: str = Form("day"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _validate_analysis_type(analysis_type)

    try:
        ensure_bucket_exists()
        eeg_file, analysis_job = await _store_file_and_job(
            uploaded_by_user_id=uploaded_by_user_id,
            patient_id=patient_id,
            analysis_type=analysis_type,
            file=file,
            db=db,
        )
        db.commit()
        db.refresh(eeg_file)
        db.refresh(analysis_job)

        return {
            "message": "File uploaded successfully and analysis job created",
            "file": _serialize_file(eeg_file),
            "analysis_job": _serialize_job(analysis_job),
        }
    except S3Error as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"MinIO upload failed: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        await file.close()


@router.post("/upload-batch")
async def upload_eeg_batch(
    uploaded_by_user_id: int = Form(...),
    patient_id: int | None = Form(None),
    analysis_type: str = Form("day"),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Batch upload requires at least 2 files")

    _validate_analysis_type(analysis_type)

    try:
        ensure_bucket_exists()

        batch = AnalysisBatch(
            uploaded_by_user_id=uploaded_by_user_id,
            analysis_type=analysis_type,
        )
        db.add(batch)
        db.flush()

        stored_files: list[EEGFile] = []
        analysis_jobs: list[AnalysisJob] = []
        for upload_file in files:
            eeg_file, analysis_job = await _store_file_and_job(
                uploaded_by_user_id=uploaded_by_user_id,
                patient_id=patient_id,
                analysis_type=analysis_type,
                file=upload_file,
                db=db,
                batch_id=batch.id,
            )
            stored_files.append(eeg_file)
            analysis_jobs.append(analysis_job)

        db.commit()
        db.refresh(batch)
        for eeg_file in stored_files:
            db.refresh(eeg_file)
        for analysis_job in analysis_jobs:
            db.refresh(analysis_job)

        return {
            "message": "Batch uploaded successfully and analysis jobs created",
            "batch": _serialize_batch(batch, analysis_jobs),
            "files": [_serialize_file(eeg_file) for eeg_file in stored_files],
            "analysis_jobs": [_serialize_job(job) for job in analysis_jobs],
        }
    except S3Error as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"MinIO upload failed: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        for upload_file in files:
            await upload_file.close()


@router.get("/{file_id}")
def get_eeg_file_metadata(file_id: int, db: Session = Depends(get_db)):
    eeg_file = db.query(EEGFile).filter(EEGFile.id == file_id).first()
    if not eeg_file:
        raise HTTPException(status_code=404, detail="File not found")

    return {"file": _serialize_file(eeg_file)}


@router.get("/{file_id}/download")
def download_eeg_file(file_id: int, db: Session = Depends(get_db)):
    eeg_file = db.query(EEGFile).filter(EEGFile.id == file_id).first()
    if not eeg_file:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        obj = minio_client.get_object(S3_BUCKET, eeg_file.object_storage_key)
        return StreamingResponse(
            obj,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{eeg_file.original_filename}"'
            },
        )
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"MinIO download failed: {str(e)}")


@router.delete("/{file_id}")
def delete_eeg_file(file_id: int, db: Session = Depends(get_db)):
    eeg_file = db.query(EEGFile).filter(EEGFile.id == file_id).first()
    if not eeg_file:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        minio_client.remove_object(S3_BUCKET, eeg_file.object_storage_key)
        db.delete(eeg_file)
        db.commit()
        return {"message": "File deleted successfully", "file_id": file_id}
    except S3Error as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"MinIO delete failed: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/")
def list_eeg_files(
    patient_id: Optional[int] = Query(None),
    uploaded_by_user_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(EEGFile)

    if patient_id is not None:
        query = query.filter(EEGFile.patient_id == patient_id)

    if uploaded_by_user_id is not None:
        query = query.filter(EEGFile.uploaded_by_user_id == uploaded_by_user_id)

    total = query.count()
    files = (
        query.order_by(EEGFile.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "files": [_serialize_file(eeg_file) for eeg_file in files],
    }
