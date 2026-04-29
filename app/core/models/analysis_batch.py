from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnalysisBatch(Base):
    __tablename__ = "analysis_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="day")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
