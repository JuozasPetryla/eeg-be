from sqlalchemy import String, BigInteger, ForeignKey, DateTime, func, CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class EEGFile(Base):
    __tablename__ = "eeg_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("file_type IN ('edf', 'csv')", name="ck_eeg_files_file_type"),
    )
