import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, ForeignKey, 
    Text, Boolean, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from api.database.base import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class ThreatLevel(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MODERATE = "Moderate"
    LOW = "Low"


class WasteType(str, enum.Enum):
    MIXED = "mixed"
    CONSTRUCTION = "construction"
    HAZARDOUS = "hazardous"
    ELECTRONIC = "electronic"
    PLASTIC = "plastic"
    ORGANIC = "organic"
    MEDICAL = "medical"
    OTHER = "other"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class AlertSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.ANALYST, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    reports = relationship("CitizenReport", back_populates="reporter", foreign_keys="CitizenReport.reporter_id")
    assigned_reports = relationship("CitizenReport", back_populates="assignee", foreign_keys="CitizenReport.assignee_id")
    alerts = relationship("Alert", back_populates="assignee", foreign_keys="Alert.assignee_id")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


class Sector(Base):
    __tablename__ = "sectors"
    
    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    bbox = Column(JSON, nullable=False)
    center = Column(JSON, nullable=False)
    zoom = Column(Integer, default=12)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    waste_sites = relationship("WasteSite", back_populates="sector")
    
    def __repr__(self):
        return f"<Sector(id={self.id}, name={self.name})>"


class WasteSite(Base):
    __tablename__ = "waste_sites"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(String(50), unique=True, index=True, nullable=False)
    sector_id = Column(String(50), ForeignKey("sectors.id"), nullable=False)
    
    geometry = Column(JSON, nullable=False)
    centroid = Column(JSON, nullable=False)
    area_m2 = Column(Float, nullable=False)
    estimated_tonnage = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    risk_score = Column(Integer, nullable=False)
    threat_level = Column(Enum(ThreatLevel), nullable=False)
    waste_type = Column(Enum(WasteType), default=WasteType.MIXED)
    
    detection_date = Column(DateTime, nullable=False)
    sensor = Column(String(100), nullable=True)
    
    ndvi_before = Column(Float, nullable=True)
    ndvi_after = Column(Float, nullable=True)
    delta_ndvi = Column(Float, nullable=True)
    swir_mean = Column(Float, nullable=True)
    
    distance_to_water_km = Column(Float, nullable=True)
    distance_to_protected_km = Column(Float, nullable=True)
    
    scene_t0 = Column(String(100), nullable=True)
    scene_t1 = Column(String(100), nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    sector = relationship("Sector", back_populates="waste_sites")
    time_series = relationship("WasteSiteTimeSeries", back_populates="waste_site", cascade="all, delete-orphan")
    citizen_reports = relationship("CitizenReport", back_populates="waste_site")
    alerts = relationship("Alert", back_populates="waste_site")
    
    __table_args__ = (
        Index("ix_waste_sites_sector_active", "sector_id", "is_active"),
        Index("ix_waste_sites_threat_level", "threat_level"),
        Index("ix_waste_sites_detection_date", "detection_date"),
    )
    
    def __repr__(self):
        return f"<WasteSite(id={self.site_id}, threat={self.threat_level}, area={self.area_m2})>"


class WasteSiteTimeSeries(Base):
    __tablename__ = "waste_site_time_series"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    waste_site_id = Column(UUID(as_uuid=True), ForeignKey("waste_sites.id"), nullable=False)
    
    date = Column(DateTime, nullable=False, index=True)
    area_m2 = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    ndvi = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    waste_site = relationship("WasteSite", back_populates="time_series")
    
    __table_args__ = (
        Index("ix_timeseries_site_date", "waste_site_id", "date"),
        UniqueConstraint("waste_site_id", "date", name="uq_site_date"),
    )


class CitizenReport(Base):
    __tablename__ = "citizen_reports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(String(50), unique=True, index=True, nullable=False)
    
    reporter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    waste_site_id = Column(UUID(as_uuid=True), ForeignKey("waste_sites.id"), nullable=True)
    
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy_m = Column(Float, nullable=True)
    
    threat_level = Column(Enum(ThreatLevel), nullable=False)
    waste_type = Column(Enum(WasteType), nullable=True)
    description = Column(Text, nullable=False)
    
    photos = Column(JSON, default=list)
    audio_url = Column(String(500), nullable=True)
    
    status = Column(Enum(ReportStatus), default=ReportStatus.PENDING, nullable=False, index=True)
    verified = Column(Boolean, default=False)
    verification_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    reporter = relationship("User", back_populates="reports", foreign_keys=[reporter_id])
    assignee = relationship("User", back_populates="assigned_reports", foreign_keys=[assignee_id])
    waste_site = relationship("WasteSite", back_populates="citizen_reports")
    
    __table_args__ = (
        Index("ix_reports_status_created", "status", "created_at"),
        Index("ix_reports_location", "latitude", "longitude"),
    )
    
    def __repr__(self):
        return f"<CitizenReport(id={self.report_id}, status={self.status})>"


class MonitoringJob(Base):
    __tablename__ = "monitoring_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(String(50), unique=True, index=True, nullable=False)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sector_id = Column(String(50), ForeignKey("sectors.id"), nullable=True)
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    bbox = Column(JSON, nullable=False)
    confidence_threshold = Column(Float, default=0.7)
    lookback_days = Column(Integer, default=30)
    
    schedule_type = Column(String(20), default="interval")
    cron_expression = Column(String(100), nullable=True)
    interval_hours = Column(Integer, default=24)
    
    is_active = Column(Boolean, default=True)
    
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User")
    sector = relationship("Sector")
    
    __table_args__ = (
        Index("ix_monitoring_jobs_user_active", "user_id", "is_active"),
    )
    
    def __repr__(self):
        return f"<MonitoringJob(id={self.job_id}, name={self.name}, active={self.is_active})>"


class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(String(50), unique=True, index=True, nullable=False)
    
    job_id = Column(UUID(as_uuid=True), ForeignKey("monitoring_jobs.id"), nullable=True)
    sector_id = Column(String(50), ForeignKey("sectors.id"), nullable=True)
    waste_site_id = Column(UUID(as_uuid=True), ForeignKey("waste_sites.id"), nullable=True)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    severity = Column(Enum(AlertSeverity), nullable=False, index=True)
    status = Column(Enum(AlertStatus), default=AlertStatus.ACTIVE, nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    sites_count = Column(Integer, default=0)
    total_area_m2 = Column(Float, default=0)
    max_threat_level = Column(Enum(ThreatLevel), nullable=True)
    
    metadata = Column(JSON, default=dict)
    
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    job = relationship("MonitoringJob")
    sector = relationship("Sector")
    waste_site = relationship("WasteSite", back_populates="alerts")
    assignee = relationship("User", back_populates="alerts", foreign_keys=[assignee_id])
    
    __table_args__ = (
        Index("ix_alerts_status_severity", "status", "severity"),
        Index("ix_alerts_job_created", "job_id", "created_at"),
    )
    
    def __repr__(self):
        return f"<Alert(id={self.alert_id}, severity={self.severity}, status={self.status})>"


class ExportJob(Base):
    __tablename__ = "export_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    export_id = Column(String(50), unique=True, index=True, nullable=False)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    format = Column(String(20), nullable=False)
    bbox = Column(JSON, nullable=True)
    date_range = Column(JSON, nullable=True)
    min_confidence = Column(Float, default=0.5)
    
    status = Column(String(20), default="pending", index=True)
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ExportJob(id={self.export_id}, format={self.format}, status={self.status})>"


class ApiKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String(255), unique=True, index=True, nullable=False)
    key_prefix = Column(String(20), nullable=False)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    
    scopes = Column(JSON, default=list)
    rate_limit = Column(Integer, default=1000)
    
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ApiKey(prefix={self.key_prefix}, name={self.name})>"