import os
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from minio.error import S3Error

from app.core.database import get_db
from app.core.file_storage import minio_client, S3_BUCKET
from app.core.models.eeg_file import EEGFile

from typing import Optional, List
from fastapi import Query

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {"edf", "csv"}


@router.post("/upload")
async def upload_eeg_file(
    uploaded_by_user_id: int = Form(...),
    patient_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    try:
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
        db.commit()
        db.refresh(eeg_file)

        return {
            "message": "File uploaded successfully",
            "file": {
                "id": eeg_file.id,
                "uploaded_by_user_id": eeg_file.uploaded_by_user_id,
                "patient_id": eeg_file.patient_id,
                "original_filename": eeg_file.original_filename,
                "file_type": eeg_file.file_type,
                "file_size_bytes": eeg_file.file_size_bytes,
                "object_storage_key": eeg_file.object_storage_key,
                "created_at": eeg_file.created_at,
            },
        }

    except S3Error as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"MinIO upload failed: {str(e)}")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    finally:
        await file.close()


@router.get("/{file_id}")
def get_eeg_file_metadata(file_id: int, db: Session = Depends(get_db)):
    eeg_file = db.query(EEGFile).filter(EEGFile.id == file_id).first()

    if not eeg_file:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "file": {
            "id": eeg_file.id,
            "uploaded_by_user_id": eeg_file.uploaded_by_user_id,
            "patient_id": eeg_file.patient_id,
            "original_filename": eeg_file.original_filename,
            "file_type": eeg_file.file_type,
            "file_size_bytes": eeg_file.file_size_bytes,
            "object_storage_key": eeg_file.object_storage_key,
            "created_at": eeg_file.created_at,
        }
    }


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

    files: List[EEGFile] = (
        query.order_by(EEGFile.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "files": [
            {
                "id": f.id,
                "uploaded_by_user_id": f.uploaded_by_user_id,
                "patient_id": f.patient_id,
                "original_filename": f.original_filename,
                "file_type": f.file_type,
                "file_size_bytes": f.file_size_bytes,
                "object_storage_key": f.object_storage_key,
                "created_at": f.created_at,
            }
            for f in files
        ],
    }
