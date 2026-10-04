from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
import json
from pathlib import Path
from sqlalchemy.orm import Session

from api.database import SessionLocal
from api.database.models import Sector, WasteSite, MonitoringJob, Alert
from api.stac_pipeline import STACPipeline, get_pipeline
from api.anomaly_engine import AnomalyEngine, get_engine
from api.mock_data import filter_features_by_confidence, calculate_summary_stats
from api.shared import send_webhook_alerts, deduplicate_detections

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='UTC')
        _scheduler.start()
        logger.info("Background scheduler started")
    return _scheduler

def run_scheduled_analysis(job_id: int):
    """Execute a scheduled monitoring job."""
    db = SessionLocal()
    try:
        job = db.query(MonitoringJob).filter(MonitoringJob.id == job_id).first()
        if not job or not job.is_active:
            logger.warning(f"Job {job_id} not found or inactive")
            return

        logger.info(f"Running scheduled analysis for job {job_id}: {job.name}")
        job.last_run = datetime.utcnow()
        job.run_count += 1
        db.commit()

        pipeline = get_pipeline()
        engine = get_engine()

        item_t1, item_t0 = pipeline.get_latest_two_scenes(
            job.bbox, 
            (datetime.utcnow() - timedelta(days=job.lookback_days)).strftime('%Y-%m-%d'),
            datetime.utcnow().strftime('%Y-%m-%d')
        )

        if not item_t1 or not item_t0:
            logger.warning(f"Insufficient imagery for job {job_id}")
            job.last_error = "Insufficient satellite imagery"
            db.commit()
            return

        bands_t1 = pipeline.fetch_all_bands(item_t1)
        bands_t0 = pipeline.fetch_all_bands(item_t0)
        features = engine.process_scenes(bands_t0, bands_t1)
        filtered = filter_features_by_confidence(features, job.confidence_threshold)
        filtered = deduplicate_detections(filtered)

        new_sites = []
        for feat in filtered:
            props = feat["properties"]
            existing = db.query(WasteSite).filter(
                WasteSite.site_id == props["id"],
                WasteSite.sector_id == job.sector_id
            ).first()
            
            if not existing:
                ws = WasteSite(
                    site_id=props["id"],
                    sector_id=job.sector_id,
                    geometry=feat["geometry"],
                    centroid=props["centroid"],
                    area_m2=props["area_m2"],
                    estimated_tonnage=props["estimated_tonnage"],
                    confidence=props["confidence"],
                    risk_score=props["risk_score"],
                    threat_level=props["threat_level"],
                    waste_type=props.get("waste_type", "mixed"),
                    detection_date=datetime.utcnow(),
                    sensor=props.get("sensor", "Sentinel-2 L2A"),
                    ndvi_before=props.get("ndvi_before"),
                    ndvi_after=props.get("ndvi_after"),
                    delta_ndvi=props.get("delta_ndvi"),
                    swir_mean=props.get("swir_mean"),
                    distance_to_water_km=props.get("distance_to_water_km"),
                    distance_to_protected_km=props.get("distance_to_protected_km"),
                    scene_t0=item_t0.id,
                    scene_t1=item_t1.id,
                )
                db.add(ws)
                new_sites.append(props)
            else:
                existing.detection_date = datetime.utcnow()
                existing.confidence = props["confidence"]
                existing.risk_score = props["risk_score"]
                existing.threat_level = props["threat_level"]
                existing.area_m2 = props["area_m2"]
                existing.estimated_tonnage = props["estimated_tonnage"]

        db.commit()

        if new_sites:
            summary = calculate_summary_stats([{"properties": s, "geometry": {"type": "Point", "coordinates": s["centroid"]}} for s in new_sites])
            alert = Alert(
                job_id=job.id,
                sector_id=job.sector_id,
                severity="critical" if any(s["threat_level"] in ("Critical", "High") for s in new_sites) else "info",
                message=f"Scheduled analysis detected {len(new_sites)} new waste sites in {job.name}",
                sites_count=len(new_sites),
                total_area_m2=summary.get("total_area_m2", 0),
                max_threat_level=max((s["threat_level"] for s in new_sites), default="Low"),
                payload={"new_sites": new_sites, "summary": summary},
            )
            db.add(alert)
            db.commit()

            import asyncio
            asyncio.run(send_webhook_alerts(
                [{"properties": s, "geometry": {"type": "Point", "coordinates": s["centroid"]}} for s in new_sites],
                job.bbox,
                "scheduler@skydump.ai"
            ))

        job.last_error = None
        logger.info(f"Job {job_id} completed: {len(new_sites)} new sites detected")

    except Exception as e:
        logger.error(f"Scheduled analysis failed for job {job_id}: {e}")
        job = db.query(MonitoringJob).filter(MonitoringJob.id == job_id).first()
        if job:
            job.last_error = str(e)
            db.commit()
    finally:
        db.close()

def schedule_job(job: 'MonitoringJob'):
    """Add or update a job in the scheduler."""
    scheduler = get_scheduler()
    job_id_str = f"monitoring_{job.id}"

    scheduler.remove_job(job_id_str) if scheduler.get_job(job_id_str) else None

    if job.schedule_type == "cron" and job.cron_expression:
        trigger = CronTrigger.from_crontab(job.cron_expression, timezone='UTC')
    elif job.schedule_type == "interval" and job.interval_hours:
        trigger = IntervalTrigger(hours=job.interval_hours, timezone='UTC')
    else:
        trigger = IntervalTrigger(hours=24, timezone='UTC')

    scheduler.add_job(
        run_scheduled_analysis,
        trigger=trigger,
        args=[job.id],
        id=job_id_str,
        name=f"Monitoring: {job.name}",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info(f"Scheduled job {job_id_str} with trigger {trigger}")

def unschedule_job(job_id: int):
    """Remove a job from the scheduler."""
    scheduler = get_scheduler()
    job_id_str = f"monitoring_{job_id}"
    if scheduler.get_job(job_id_str):
        scheduler.remove_job(job_id_str)
        logger.info(f"Unscheduled job {job_id_str}")

def load_scheduled_jobs():
    """Load all active monitoring jobs into scheduler on startup."""
    db = SessionLocal()
    try:
        jobs = db.query(MonitoringJob).filter(MonitoringJob.is_active == True).all()
        for job in jobs:
            schedule_job(job)
        logger.info(f"Loaded {len(jobs)} scheduled monitoring jobs")
    finally:
        db.close()

def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Background scheduler stopped")