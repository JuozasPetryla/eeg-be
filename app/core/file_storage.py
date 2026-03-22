import os
from minio import Minio
from minio.error import S3Error

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio12345")
S3_BUCKET = os.getenv("S3_BUCKET", "eeg")

endpoint = S3_ENDPOINT.replace("http://", "").replace("https://", "")
secure = S3_ENDPOINT.startswith("https://")

minio_client = Minio(
    endpoint,
    access_key=S3_ACCESS_KEY,
    secret_key=S3_SECRET_KEY,
    secure=secure,
)

def ensure_bucket_exists() -> None:
    try:
        if not minio_client.bucket_exists(S3_BUCKET):
            minio_client.make_bucket(S3_BUCKET)
    except S3Error as e:
        raise RuntimeError(f"MinIO bucket init failed: {e}") from e
