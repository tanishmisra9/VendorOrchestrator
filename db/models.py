from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Enum,
    JSON,
    ForeignKey,
    TIMESTAMP,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class VendorMaster(Base):
    __tablename__ = "vendor_master"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String(255), nullable=False)
    address = Column(String(500))
    city = Column(String(100))
    state = Column(String(100))
    zip = Column(String(20))
    country = Column(String(100), default="US")
    tax_id = Column(String(20))
    status = Column(
        Enum("active", "inactive", "duplicate", name="vendor_status"),
        default="active",
    )
    cluster_id = Column(Integer, index=True)
    source = Column(String(100))
    created_at = Column(TIMESTAMP, default=_utcnow)
    updated_at = Column(TIMESTAMP, default=_utcnow, onupdate=_utcnow)

    audit_logs = relationship("AuditLog", back_populates="vendor")
    overrides = relationship("AnalystOverride", back_populates="vendor")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "vendor_name": self.vendor_name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip": self.zip,
            "country": self.country,
            "tax_id": self.tax_id,
            "status": self.status,
            "cluster_id": self.cluster_id,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendor_master.id", ondelete="SET NULL"))
    details_json = Column(JSON)
    confidence = Column(Float)
    timestamp = Column(TIMESTAMP, default=_utcnow)

    vendor = relationship("VendorMaster", back_populates="audit_logs")


class AnalystOverride(Base):
    __tablename__ = "analyst_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(
        Integer, ForeignKey("vendor_master.id", ondelete="CASCADE"), nullable=False
    )
    original_action = Column(String(100), nullable=False)
    override_action = Column(String(100), nullable=False)
    reason = Column(Text)
    analyst_name = Column(String(100))
    timestamp = Column(TIMESTAMP, default=_utcnow)

    vendor = relationship("VendorMaster", back_populates="overrides")
