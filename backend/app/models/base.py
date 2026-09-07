from datetime import datetime, timezone

from sqlalchemy import Column, BigInteger, DateTime, String

from app.core.database import Base


class BaseModel(Base):
    __abstract__ = True

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_by = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by = Column(String(64), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )