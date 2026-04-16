import os
import threading
import time

from minio import Minio
from minio.error import S3Error

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio12345")
S3_BUCKET = os.getenv("S3_BUCKET", "eeg")
MINIO_INIT_MAX_ATTEMPTS = int(os.getenv("MINIO_INIT_MAX_ATTEMPTS", "10"))
MINIO_INIT_RETRY_SECONDS = float(os.getenv("MINIO_INIT_RETRY_SECONDS", "1"))

endpoint = S3_ENDPOINT.replace("http://", "").replace("https://", "")
secure = S3_ENDPOINT.startswith("https://")

minio_client = Minio(
    endpoint,
    access_key=S3_ACCESS_KEY,
    secret_key=S3_SECRET_KEY,
    secure=secure,
)

_bucket_init_lock = threading.Lock()
_bucket_ready = False


def ensure_bucket_exists() -> None:
    global _bucket_ready

    if _bucket_ready:
        return

    with _bucket_init_lock:
        if _bucket_ready:
            return

        last_error: Exception | None = None
        for attempt in range(1, MINIO_INIT_MAX_ATTEMPTS + 1):
            try:
                if not minio_client.bucket_exists(S3_BUCKET):
                    minio_client.make_bucket(S3_BUCKET)
                _bucket_ready = True
                return
            except S3Error as e:
                if e.code in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    _bucket_ready = True
                    return
                last_error = e
            except Exception as e:
                last_error = e

            if attempt < MINIO_INIT_MAX_ATTEMPTS:
                time.sleep(MINIO_INIT_RETRY_SECONDS)

        raise RuntimeError(f"MinIO bucket init failed: {last_error}") from last_error
