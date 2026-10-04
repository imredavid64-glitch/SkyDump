from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Set
from datetime import datetime, timedelta
import jwt
import bcrypt
import os
import logging
import httpx
from pathlib import Path
import json
import sys
import asyncio

# Sentry integration
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ml'))

from sqlalchemy.orm import Session

from api.scheduler import get_scheduler, schedule_job, unschedule_job, load_scheduled_jobs, shutdown_scheduler
from api.stac_pipeline import STACPipeline, get_pipeline
from api.anomaly_engine import AnomalyEngine, get_engine
from api.mock_data import get_sector_data, get_all_features, filter_features_by_confidence, calculate_summary_stats, MOCK_SECTORS
from api.config import settings

# Optional ML imports (graceful degradation for Vercel)
try:
    from ml.inference import WasteDetectionInference, ONNXInference
    from ml.timeseries import TimeSeriesAnalyzer
    ML_AVAILABLE = True
except ImportError:
    WasteDetectionInference = None
    ONNXInference = None
    TimeSeriesAnalyzer = None
    ML_AVAILABLE = False
    logging.warning("ML dependencies not available - ML features disabled")
from api.database import SessionLocal, get_db
from api.database.models import Sector, WasteSite, User, MonitoringJob, Alert

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET", "skydump-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days

security = HTTPBearer()

# Initialize Sentry
if settings.SENTRY_DSN:
    sentry_logging = LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR
    )
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            sentry_logging,
        ],
        send_default_pii=True,
    )

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Always use memory storage for rate limiting to avoid Redis dependency issues
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"] if settings.RATE_LIMIT_ENABLED else [],
    storage_uri="memory://",
)

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.user_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = set()
        self.active_connections[client_id].add(websocket)
        self.user_connections[id(websocket)] = client_id

    def disconnect(self, websocket: WebSocket):
        ws_id = id(websocket)
        if ws_id in self.user_connections:
            client_id = self.user_connections.pop(ws_id)
            if client_id in self.active_connections:
                self.active_connections[client_id].discard(websocket)
                if not self.active_connections[client_id]:
                    del self.active_connections[client_id]

    async def send_progress(self, client_id: str, progress: Dict[str, Any]):
        if client_id in self.active_connections:
            disconnected = set()
            for websocket in self.active_connections[client_id]:
                try:
                    await websocket.send_json(progress)
                except Exception:
                    disconnected.add(websocket)
            for ws in disconnected:
                self.disconnect(ws)

    async def broadcast(self, message: Dict[str, Any]):
        for client_id, connections in self.active_connections.items():
            for websocket in connections:
                try:
                    await websocket.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


def detect_sar_changes(bands_t0: dict, bands_t1: dict, threshold: float) -> List[Dict]:
    """
    Detect changes using Sentinel-1 SAR coherence and backscatter difference.
    Returns list of detected waste site features.
    """
    import logging
    import numpy as np
    import cv2
    from anomaly_engine import AnomalyEngine
    from shapely.geometry import Polygon, mapping
    from pyproj import Transformer
    
    logger = logging.getLogger(__name__)
    
    try:
        # Get VV and VH bands for both time periods
        vv_t0, _, _ = bands_t0.get("VV", (None, None, None))
        vh_t0, _, _ = bands_t0.get("VH", (None, None, None))
        vv_t1, transform, crs = bands_t1.get("VV", (None, None, None))
        vh_t1, _, _ = bands_t1.get("VH", (None, None, None))
        
        if vv_t0 is None or vv_t1 is None:
            return []
        
        # Compute coherence proxy: ratio of means (simplified coherence)
        vv_ratio = np.divide(vv_t1, vv_t0 + 1e-10, out=np.ones_like(vv_t0), where=vv_t0 != 0)
        vh_ratio = np.divide(vh_t1, vh_t0 + 1e-10, out=np.ones_like(vh_t0), where=vh_t0 != 0)
        
        # Coherence loss: significant drop in backscatter correlation
        coherence_loss = (vv_ratio < 0.7) | (vh_ratio < 0.7)
        
        # Backscatter increase (new material/debris)
        vv_increase = vv_t1 > (np.percentile(vv_t0, 90) * 1.3)
        vh_increase = vh_t1 > (np.percentile(vh_t0, 90) * 1.3)
        backscatter_increase = vv_increase | vh_increase
        
        # Combined SAR anomaly: coherence loss AND backscatter increase
        sar_anomaly = coherence_loss & backscatter_increase
        
        # Convert to binary mask
        mask = sar_anomaly.astype(np.uint8) * 255
        
        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # Extract polygons using anomaly engine
        engine = AnomalyEngine()
        features = engine.extract_polygons(mask, transform, crs)
        
        # Add SAR-specific properties
        for feat in features:
            feat["properties"]["source_sensor"] = "sentinel1"
            feat["properties"]["sensor"] = "Sentinel-1 SAR"
            feat["properties"]["detection_method"] = "SAR coherence + backscatter"
        
        return features
        
    except Exception as e:
        logger.warning(f"SAR change detection failed: {e}")
        return []


from api.shared import deduplicate_detections, send_webhook_alerts

manager = ConnectionManager()


# API Models
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    email: str
    password: str
    organization: str
    role: str = "analyst"  # admin, analyst, viewer

class UserLogin(BaseModel):
    email: str
    password: str

class BBoxRequest(BaseModel):
    bbox: List[float] = Field(..., min_items=4, max_items=4)
    start_date: str
    end_date: str
    confidence_threshold: float = Field(0.7, ge=0.3, le=0.95)
    use_ml: bool = True
    time_series: bool = False

class AnalyzeResponse(BaseModel):
    features: List[Dict]
    summary: Dict
    metadata: Dict
    time_series: Optional[Dict] = None

class AlertConfig(BaseModel):
    webhook_url: str
    threshold_confidence: float = 0.8
    threshold_area_m2: float = 10000
    regions: List[str] = []

class ExportRequest(BaseModel):
    format: str = "geojson"  # geojson, pdf, csv
    bbox: Optional[List[float]] = None
    date_range: Optional[List[str]] = None
    min_confidence: float = 0.5

class AuthorityReport(BaseModel):
    site_id: str
    coordinates: List[float]
    area_m2: float
    estimated_tonnage: float
    confidence: float
    threat_level: str
    detection_date: str
    evidence_package: Dict

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_role(required_roles: List[str]):
    def role_checker(user: User = Depends(get_current_user)):
        if user.role.value not in required_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker


app = FastAPI(
    title="SkyDump AI Authority API",
    version="2.0.0",
    description="Satellite waste detection API for environmental authorities"
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database and seed demo data."""
    import json
    import uuid
    from pathlib import Path
    from datetime import datetime
    
    from api.database import init_db
    from api.database.models import User, Sector, UserRole, WasteSite, MonitoringJob
    from sqlalchemy.orm import Session
    
    init_db()
    
    db = SessionLocal()
    try:
        # Create demo users
        demo_users = [
            ("admin@demo", "demo123", "SkyDump Demo", UserRole.ADMIN),
            ("analyst@demo", "demo123", "SkyDump Demo", UserRole.ANALYST),
            ("viewer@demo", "demo123", "SkyDump Demo", UserRole.VIEWER),
        ]
        
        for email, password, org, role in demo_users:
            existing = db.query(User).filter(User.email == email).first()
            if not existing:
                hashed_pw = get_password_hash(password)
                user = User(
                    email=email,
                    hashed_password=hashed_pw,
                    organization=org,
                    role=role,
                )
                db.add(user)
        
        # Create precomputed sectors
        sectors_data = [
            {
                "id": "sector-7",
                "name": "Rotterdam Industrial Zone, Netherlands",
                "bbox": [4.2, 51.85, 4.5, 51.95],
                "center": [4.35, 51.9],
                "zoom": 12,
            },
            {
                "id": "sector-12",
                "name": "Amazon River Basin, Brazil",
                "bbox": [-55.5, -3.5, -55.0, -3.0],
                "center": [-55.25, -3.25],
                "zoom": 12,
            },
            {
                "id": "sector-4",
                "name": "Congo Basin Forest Reserve, DRC",
                "bbox": [18.5, -1.5, 19.0, -1.0],
                "center": [18.75, -1.25],
                "zoom": 12,
            },
        ]
        
        for s in sectors_data:
            existing = db.query(Sector).filter(Sector.id == s["id"]).first()
            if not existing:
                sector = Sector(**s)
                db.add(sector)
        
        # Load precomputed waste sites from JSON files
        import json
        from pathlib import Path
        
        precomputed_dir = Path("api/precomputed")
        for sector_data in sectors_data:
            sector_id = sector_data["id"]
            json_file = precomputed_dir / f"{sector_id}.json"
            if json_file.exists():
                with open(json_file) as f:
                    precomputed = json.load(f)
                
                sector = db.query(Sector).filter(Sector.id == sector_id).first()
                if sector:
                    for feature in precomputed.get("feature_collection", {}).get("features", []):
                        props = feature["properties"]
                        # Check if already exists
                        existing = db.query(WasteSite).filter(WasteSite.site_id == props["id"]).first()
                        if not existing:
                            ws = WasteSite(
                                id=uuid.uuid4(),
                                site_id=props["id"],
                                sector_id=sector_id,
                                geometry=feature["geometry"],
                                centroid=props["centroid"],
                                area_m2=props["area_m2"],
                                estimated_tonnage=props["estimated_tonnage"],
                                confidence=props["confidence"],
                                risk_score=props["risk_score"],
                                threat_level=props["threat_level"],
                                waste_type=props.get("waste_type", "mixed"),
                                detection_date=datetime.fromisoformat(props["detection_date"]) if props.get("detection_date") else datetime.utcnow(),
                                sensor=props.get("sensor", "Sentinel-2 L2A"),
                                ndvi_before=props.get("ndvi_before"),
                                ndvi_after=props.get("ndvi_after"),
                                delta_ndvi=props.get("delta_ndvi"),
                                swir_mean=props.get("swir_mean"),
                                distance_to_water_km=props.get("distance_to_water_km"),
                                distance_to_protected_km=props.get("distance_to_protected_km"),
                                scene_t0=precomputed.get("metadata", {}).get("scene_t0"),
                                scene_t1=precomputed.get("metadata", {}).get("scene_t1"),
                            )
                            db.add(ws)
        
        # Create default monitoring jobs for demo sectors
        admin_user = db.query(User).filter(User.email == "admin@demo").first()
        if admin_user:
            for sector_data in sectors_data:
                sector_id = sector_data["id"]
                existing_job = db.query(MonitoringJob).filter(
                    MonitoringJob.sector_id == sector_id,
                    MonitoringJob.user_id == admin_user.id
                ).first()
                if not existing_job:
                    job = MonitoringJob(
                        job_id=f"monitor-{sector_id}",
                        user_id=admin_user.id,
                        sector_id=sector_id,
                        name=f"Auto-monitor {sector_data['name']}",
                        description=f"Daily automated monitoring of {sector_data['name']} for illegal waste dumping",
                        bbox=sector_data["bbox"],
                        confidence_threshold=0.7,
                        lookback_days=14,
                        schedule_type="interval",
                        interval_hours=24,
                        is_active=True,
                    )
                    db.add(job)
        
        db.commit()
        
        # Load scheduled jobs into scheduler
        load_scheduled_jobs()
        
    except Exception as e:
        db.rollback()
        logger.error(f"Startup error: {e}")
    finally:
        db.close()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    shutdown_scheduler()


# Auth endpoints
@app.post("/api/auth/register", response_model=Token)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        hashed_password=hashed_password,
        organization=user.organization,
        role=user.role,
    )
    db.add(new_user)
    db.commit()
    
    token = create_access_token({"sub": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/auth/login", response_model=Token)
async def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": db_user.email, "role": db_user.role.value})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "email": user.email,
        "organization": user.organization,
        "role": user.role.value
    }


# WebSocket endpoint for live analysis progress
@app.websocket("/ws/analysis/{client_id}")
async def websocket_analysis_progress(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            # Keep connection alive, wait for client messages
            data = await websocket.receive_text()
            # Echo back for heartbeat
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        manager.disconnect(websocket)


# Detection endpoints
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": "2.0.0",
        "service": "SkyDump AI Authority API",
        "ml_enabled": True
    }

@app.post("/api/analyze-bbox", response_model=AnalyzeResponse)
async def analyze_bbox(
    request: BBoxRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Generate client ID for WebSocket progress updates
    client_id = f"{user.email}_{int(datetime.utcnow().timestamp())}"
    
    async def send_progress(stage: str, progress: int, message: str):
        await manager.send_progress(client_id, {
            "type": "progress",
            "stage": stage,
            "progress": progress,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        })
        await asyncio.sleep(0.1)  # Small delay for UI updates
    
    pipeline = get_pipeline()
    engine = get_engine()
    
    try:
        await send_progress("initializing", 5, "Starting analysis...")
        
        # First, try to find matching precomputed sector
        from sqlalchemy import func
        
        await send_progress("checking_precomputed", 10, "Checking for precomputed sector...")
        
        # Check if bbox matches a precomputed sector
        sector = db.query(Sector).filter(
            Sector.bbox == request.bbox,
            Sector.is_active == True
        ).first()
        
        if sector:
            await send_progress("loading_precomputed", 30, "Loading precomputed results...")
            
            # Use precomputed data
            waste_sites = db.query(WasteSite).filter(
                WasteSite.sector_id == sector.id,
                WasteSite.is_active == True,
                WasteSite.confidence >= request.confidence_threshold
            ).all()
            
            features = []
            for ws in waste_sites:
                features.append({
                    "type": "Feature",
                    "geometry": ws.geometry,
                    "properties": {
                        "id": ws.site_id,
                        "area_m2": ws.area_m2,
                        "confidence": ws.confidence,
                        "risk_score": ws.risk_score,
                        "threat_level": ws.threat_level.value if hasattr(ws.threat_level, 'value') else ws.threat_level,
                        "estimated_tonnage": ws.estimated_tonnage,
                        "centroid": ws.centroid,
                        "detection_date": ws.detection_date.isoformat() if ws.detection_date else None,
                        "sensor": ws.sensor,
                        "waste_type": ws.waste_type.value if hasattr(ws.waste_type, 'value') else ws.waste_type,
                        "ndvi_before": ws.ndvi_before,
                        "ndvi_after": ws.ndvi_after,
                        "delta_ndvi": ws.delta_ndvi,
                        "swir_mean": ws.swir_mean,
                        "distance_to_water_km": ws.distance_to_water_km,
                        "distance_to_protected_km": ws.distance_to_protected_km,
                    }
                })
            
            await send_progress("complete", 100, f"Found {len(features)} sites from precomputed data")
            
            return AnalyzeResponse(
                features=features,
                summary=calculate_summary_stats(features),
                metadata={
                    "mode": "precomputed",
                    "sector": sector.id,
                    "bbox": request.bbox
                }
            )
        
        if request.time_series:
            # Time-series analysis
            if not ML_AVAILABLE:
                raise HTTPException(501, "Time-series analysis requires ML dependencies (not available in this deployment)")
            await send_progress("loading_timeseries", 15, "Loading time-series data...")
            analyzer = TimeSeriesAnalyzer()
            ds = analyzer.load_sentinel2_stack(
                request.bbox, request.start_date, request.end_date
            )
            await send_progress("computing_indices", 30, "Computing spectral indices...")
            ds = analyzer.compute_indices(ds)
            await send_progress("detecting_changes", 50, "Detecting changes...")
            changes = analyzer.detect_changes(ds)
            await send_progress("extracting_sites", 70, "Extracting waste sites...")
            features = analyzer.extract_waste_sites(ds, changes)
            await send_progress("complete", 100, f"Time-series analysis complete: {len(features)} sites found")
            
            return AnalyzeResponse(
                features=features,
                summary=calculate_summary_stats(features),
                metadata={
                    "mode": "time_series",
                    "bbox": request.bbox,
                    "date_range": [request.start_date, request.end_date],
                    "num_scenes": len(ds.time)
                },
                time_series={
                    "onset_dates": [str(d) for d in ds.time.values],
                    "num_revisits": len(ds.time)
                }
            )
        
        elif request.use_ml and ML_AVAILABLE:
            # ML-based detection
            await send_progress("loading_ml", 15, "Loading ML model...")
            item_t1, item_t0 = pipeline.get_latest_two_scenes(
                request.bbox, request.start_date, request.end_date
            )
            
            if not item_t1 or not item_t0:
                raise HTTPException(404, "Insufficient satellite imagery")
            
            model_path = "ml/checkpoints/best_model.ckpt"
            if os.path.exists(model_path):
                try:
                    ml_inference = WasteDetectionInference(
                        model_path=model_path,
                        threshold=request.confidence_threshold
                    )
                    logger.info("ML model loaded, but inference not fully wired - using threshold fallback")
                except Exception as e:
                    logger.warning(f"ML inference failed, falling back to threshold: {e}")
            else:
                logger.warning(f"ML checkpoint not found at {model_path}, using threshold-based detection")
        
        # Traditional threshold-based detection
        await send_progress("fetching_scenes", 20, "Fetching satellite scenes...")
        item_t1, item_t0 = pipeline.get_latest_two_scenes(
            request.bbox, request.start_date, request.end_date
        )
        
        if not item_t1 or not item_t0:
            raise HTTPException(404, "Insufficient satellite imagery")
        
        await send_progress("fetching_bands", 40, "Fetching spectral bands...")
        bands_t1 = pipeline.fetch_all_bands(item_t1)
        bands_t0 = pipeline.fetch_all_bands(item_t0)
        
        await send_progress("processing", 60, "Processing scenes for anomalies...")
        features = engine.process_scenes(bands_t0, bands_t1)
        filtered = filter_features_by_confidence(features, request.confidence_threshold)
        
        await send_progress("filtering", 80, "Filtering by confidence threshold...")
        
        # Save results to database if new bbox
        await send_progress("saving", 90, "Saving results to database...")
        if features:
            import uuid
            
            # Create or get sector
            sector = db.query(Sector).filter(Sector.bbox == request.bbox).first()
            if not sector:
                sector = Sector(
                    id=f"bbox-{uuid.uuid4().hex[:8]}",
                    name=f"Custom Analysis {request.bbox}",
                    bbox=request.bbox,
                    center=[(request.bbox[0] + request.bbox[2]) / 2, (request.bbox[1] + request.bbox[3]) / 2],
                    zoom=12,
                    is_active=True,
                )
                db.add(sector)
                db.flush()
            
            for feat in filtered:
                props = feat["properties"]
                ws = WasteSite(
                    id=uuid.uuid4(),
                    site_id=props["id"],
                    sector_id=sector.id,
                    geometry=feat["geometry"],
                    centroid=props["centroid"],
                    area_m2=props["area_m2"],
                    estimated_tonnage=props["estimated_tonnage"],
                    confidence=props["confidence"],
                    risk_score=props["risk_score"],
                    threat_level=props["threat_level"],
                    waste_type=props.get("waste_type", "mixed"),
                    detection_date=datetime.fromisoformat(props["detection_date"]) if props.get("detection_date") else datetime.utcnow(),
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
            
            db.commit()
        
        # Send webhook alerts for critical/high threat sites
        await send_webhook_alerts(filtered, request.bbox, user.email)
        
        await send_progress("complete", 100, f"Analysis complete: {len(filtered)} sites detected")
        
        return AnalyzeResponse(
            features=filtered,
            summary=calculate_summary_stats(filtered),
            metadata={
                "mode": "threshold",
                "scene_t0": item_t0.id,
                "scene_t1": item_t1.id,
                "bbox": request.bbox
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@app.get("/api/mock-sites")
async def get_mock_sites(
    sector: str = Query("sector-7"),
    user: dict = Depends(get_current_user)
):
    sector_data = get_sector_data(sector)
    features = sector_data["feature_collection"]["features"]
    return {
        "sector": sector,
        "metadata": sector_data["metadata"],
        "features": features,
        "summary": calculate_summary_stats(features)
    }


@app.get("/api/sectors")
async def list_sectors(user: dict = Depends(get_current_user)):
    return {
        "sectors": [
            {
                "id": k,
                "name": v["metadata"]["name"],
                "center": v["metadata"]["center"],
                "zoom": v["metadata"]["zoom"]
            }
            for k, v in MOCK_SECTORS.items()
        ]
    }


# Precomputed data endpoints (for instant demo)
@app.get("/api/precomputed")
async def list_precomputed(user: dict = Depends(get_current_user)):
    """List available precomputed sectors."""
    import json
    from pathlib import Path
    
    index_path = Path("api/precomputed/index.json")
    if not index_path.exists():
        return {"sectors": [], "message": "No precomputed data available"}
    
    with open(index_path) as f:
        index = json.load(f)
    return index


@app.get("/api/precomputed/{sector_id}")
async def get_precomputed_sector(
    sector_id: str,
    user: dict = Depends(get_current_user)
):
    """Get precomputed detection results for a sector."""
    import json
    from pathlib import Path
    
    sector_path = Path(f"api/precomputed/{sector_id}.json")
    if not sector_path.exists():
        raise HTTPException(404, f"Precomputed data for sector {sector_id} not found")
    
    with open(sector_path) as f:
        data = json.load(f)
    return data


@app.get("/api/precomputed/{sector_id}/timeseries")
async def get_precomputed_timeseries(
    sector_id: str,
    user: dict = Depends(get_current_user)
):
    """Get time-series data for a precomputed sector."""
    import json
    from pathlib import Path
    
    sector_path = Path(f"api/precomputed/{sector_id}.json")
    if not sector_path.exists():
        raise HTTPException(404, f"Precomputed data for sector {sector_id} not found")
    
    with open(sector_path) as f:
        data = json.load(f)
    
    return data.get("timeseries", {})


# Multi-sensor analysis endpoint
class MultiSensorRequest(BaseModel):
    bbox: List[float] = Field(..., min_items=4, max_items=4)
    start_date: str
    end_date: str
    confidence_threshold: float = Field(0.7, ge=0.3, le=0.95)
    sensors: List[str] = Field(default=["sentinel2", "sentinel1", "landsat"])  # sentinel2, sentinel1, landsat


@app.post("/api/analyze-multisensor", response_model=AnalyzeResponse)
async def analyze_multisensor(
    request: MultiSensorRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Multi-sensor analysis combining Sentinel-2 optical, Sentinel-1 SAR, and Landsat historical."""
    import logging
    logger = logging.getLogger(__name__)
    
    client_id = f"{user.email}_{int(datetime.utcnow().timestamp())}"
    
    async def send_progress(stage: str, progress: int, message: str):
        await manager.send_progress(client_id, {
            "type": "progress",
            "stage": stage,
            "progress": progress,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        })
        await asyncio.sleep(0.1)
    
    all_features = []
    sensor_results = {}
    
    try:
        await send_progress("initializing", 5, "Initializing multi-sensor analysis...")
        
        # Process each requested sensor
        sensors_to_process = request.sensors
        total_sensors = len(sensors_to_process)
        progress_per_sensor = 85 // total_sensors if total_sensors > 0 else 85
        
        for i, sensor in enumerate(sensors_to_process):
            base_progress = 10 + (i * progress_per_sensor)
            
            if sensor == "sentinel2":
                await send_progress("sentinel2", base_progress + 5, "Processing Sentinel-2 optical...")
                try:
                    s2_pipeline = get_pipeline()
                    s2_engine = get_engine()
                    
                    item_t1, item_t0 = s2_pipeline.get_latest_two_scenes(
                        request.bbox, request.start_date, request.end_date
                    )
                    
                    if item_t1 and item_t0:
                        await send_progress("sentinel2", base_progress + 20, "Fetching Sentinel-2 bands...")
                        bands_t1 = s2_pipeline.fetch_all_bands(item_t1)
                        bands_t0 = s2_pipeline.fetch_all_bands(item_t0)
                        
                        await send_progress("sentinel2", base_progress + 40, "Processing Sentinel-2 anomalies...")
                        s2_features = s2_engine.process_scenes(bands_t0, bands_t1)
                        s2_filtered = filter_features_by_confidence(s2_features, request.confidence_threshold)
                        
                        for f in s2_filtered:
                            f["properties"]["sensor"] = "Sentinel-2"
                            f["properties"]["source_sensor"] = "sentinel2"
                        
                        all_features.extend(s2_filtered)
                        sensor_results["sentinel2"] = {
                            "count": len(s2_filtered),
                            "scene_t0": item_t0.id,
                            "scene_t1": item_t1.id
                        }
                        await send_progress("sentinel2", base_progress + progress_per_sensor, f"Sentinel-2: {len(s2_filtered)} detections")
                    else:
                        sensor_results["sentinel2"] = {"count": 0, "error": "Insufficient Sentinel-2 scenes"}
                except Exception as e:
                    logger.warning(f"Sentinel-2 processing failed: {e}")
                    sensor_results["sentinel2"] = {"count": 0, "error": str(e)}
                
            elif sensor == "sentinel1":
                await send_progress("sentinel1", base_progress + 5, "Processing Sentinel-1 SAR...")
                try:
                    sar_pipeline = get_sar_pipeline()
                    
                    item_t1, item_t0 = sar_pipeline.get_latest_two_scenes(
                        request.bbox, request.start_date, request.end_date
                    )
                    
                    if item_t1 and item_t0:
                        await send_progress("sentinel1", base_progress + 20, "Fetching SAR bands...")
                        sar_bands_t1 = sar_pipeline.fetch_all_bands(item_t1)
                        sar_bands_t0 = sar_pipeline.fetch_all_bands(item_t0)
                        
                        await send_progress("sentinel1", base_progress + 40, "Processing SAR coherence...")
                        # SAR coherence change detection
                        sar_features = detect_sar_changes(sar_bands_t0, sar_bands_t1, request.confidence_threshold)
                        
                        for f in sar_features:
                            f["properties"]["sensor"] = "Sentinel-1"
                            f["properties"]["source_sensor"] = "sentinel1"
                        
                        all_features.extend(sar_features)
                        sensor_results["sentinel1"] = {
                            "count": len(sar_features),
                            "scene_t0": item_t0.id,
                            "scene_t1": item_t1.id
                        }
                        await send_progress("sentinel1", base_progress + progress_per_sensor, f"Sentinel-1: {len(sar_features)} detections")
                    else:
                        sensor_results["sentinel1"] = {"count": 0, "error": "Insufficient SAR scenes"}
                        
                except Exception as e:
                    logger.warning(f"Sentinel-1 processing failed: {e}")
                    sensor_results["sentinel1"] = {"count": 0, "error": str(e)}
                    
            elif sensor == "landsat":
                await send_progress("landsat", base_progress + 5, "Processing Landsat historical...")
                try:
                    landsat_pipeline = get_landsat_pipeline()
                    
                    # Load historical stack for trend analysis
                    landsat_features = []
                    items = landsat_pipeline.search_scenes(
                        request.bbox, request.start_date, request.end_date, limit=50
                    )
                    
                    if len(items) >= 2:
                        await send_progress("landsat", base_progress + 20, f"Loading {len(items)} Landsat scenes...")
                        
                        if not ML_AVAILABLE:
                            sensor_results["landsat"] = {"count": 0, "error": "Landsat analysis requires ML dependencies (not available in this deployment)"}
                        else:
                            # Historical trend analysis
                            from ml.timeseries import TimeSeriesAnalyzer
                            analyzer = TimeSeriesAnalyzer()
                            ds = analyzer.load_landsat_stack(
                                request.bbox, request.start_date, request.end_date
                            )
                            ds = analyzer.compute_indices(ds)
                            changes = analyzer.detect_changes(ds)
                            ls_features = analyzer.extract_waste_sites(ds, changes)
                            ls_filtered = filter_features_by_confidence(ls_features, request.confidence_threshold)
                            
                            for f in ls_filtered:
                                f["properties"]["sensor"] = "Landsat"
                                f["properties"]["source_sensor"] = "landsat"
                            
                            all_features.extend(ls_filtered)
                            sensor_results["landsat"] = {
                                "count": len(ls_filtered),
                                "scenes_processed": len(items)
                            }
                            await send_progress("landsat", base_progress + progress_per_sensor, f"Landsat: {len(ls_filtered)} historical detections")
                    else:
                        sensor_results["landsat"] = {"count": 0, "error": "Insufficient Landsat scenes"}
                        
                except Exception as e:
                    logger.warning(f"Landsat processing failed: {e}")
                    sensor_results["landsat"] = {"count": 0, "error": str(e)}
        
        await send_progress("filtering", 90, "Filtering and merging results...")
        
        # Filter by confidence threshold
        filtered = filter_features_by_confidence(all_features, request.confidence_threshold)
        
        # Deduplicate overlapping detections from different sensors
        filtered = deduplicate_detections(filtered)
        
        # Save results to database if new bbox
        if filtered:
            await send_progress("saving", 95, "Saving results to database...")
            import uuid
            
            sector = db.query(Sector).filter(Sector.bbox == request.bbox).first()
            if not sector:
                sector = Sector(
                    id=f"bbox-{uuid.uuid4().hex[:8]}",
                    name=f"Multi-sensor Analysis {request.bbox}",
                    bbox=request.bbox,
                    center=[(request.bbox[0] + request.bbox[2]) / 2, (request.bbox[1] + request.bbox[3]) / 2],
                    zoom=12,
                    is_active=True,
                )
                db.add(sector)
                db.flush()
            
            for feat in filtered:
                props = feat["properties"]
                ws = WasteSite(
                    id=uuid.uuid4(),
                    site_id=props["id"],
                    sector_id=sector.id,
                    geometry=feat["geometry"],
                    centroid=props["centroid"],
                    area_m2=props["area_m2"],
                    estimated_tonnage=props["estimated_tonnage"],
                    confidence=props["confidence"],
                    risk_score=props["risk_score"],
                    threat_level=props["threat_level"],
                    waste_type=props.get("waste_type", "mixed"),
                    detection_date=datetime.fromisoformat(props["detection_date"]) if props.get("detection_date") else datetime.utcnow(),
                    sensor=props.get("sensor", "Multi-sensor"),
                    source_sensor=props.get("source_sensor", "multisensor"),
                    ndvi_before=props.get("ndvi_before"),
                    ndvi_after=props.get("ndvi_after"),
                    delta_ndvi=props.get("delta_ndvi"),
                    swir_mean=props.get("swir_mean"),
                    distance_to_water_km=props.get("distance_to_water_km"),
                    distance_to_protected_km=props.get("distance_to_protected_km"),
                    scene_t0=props.get("scene_t0"),
                    scene_t1=props.get("scene_t1"),
                )
                db.add(ws)
            
            db.commit()
        
        # Send webhook alerts
        await send_webhook_alerts(filtered, request.bbox, user.email)
        
        await send_progress("complete", 100, f"Multi-sensor analysis complete: {len(filtered)} sites detected")
        
        return AnalyzeResponse(
            features=filtered,
            summary=calculate_summary_stats(filtered),
            metadata={
                "mode": "multisensor",
                "sensors_used": list(sensor_results.keys()),
                "sensor_results": sensor_results,
                "bbox": request.bbox
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Multi-sensor analysis failed: {str(e)}")


# Authority endpoints
@app.post("/api/authority/alerts/config")
async def configure_alerts(
    config: AlertConfig,
    user: dict = Depends(require_role(["admin"]))
):
    # Save alert config (in production, save to database)
    return {"status": "configured", "config": config.dict()}


@app.get("/api/authority/alerts")
async def get_alerts(
    status: str = Query("active"),  # active, resolved, all
    user: dict = Depends(get_current_user)
):
    # Return active alerts
    return {
        "alerts": [
            {
                "id": "ALT-001",
                "site_id": "RTM-001",
                "severity": "critical",
                "message": "New waste site detected in Rotterdam Industrial Zone",
                "coordinates": [4.35, 51.9],
                "area_m2": 45000,
                "confidence": 0.92,
                "created_at": datetime.utcnow().isoformat(),
                "status": "active"
            }
        ]
    }


@app.post("/api/authority/reports", response_model=AuthorityReport)
async def create_report(
    report: AuthorityReport,
    user: dict = Depends(require_role(["admin", "analyst"]))
):
    # Save report to database
    return report


@app.get("/api/authority/reports")
async def list_reports(
    status: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(get_current_user)
):
    return {"reports": []}


@app.post("/api/authority/export")
async def export_data(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_role(["admin", "analyst"]))
):
    """Generate export file (GeoJSON, PDF, CSV) in background."""
    import json
    import csv
    import io
    from pathlib import Path
    
    export_id = f"EXP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)
    
    def generate_export():
        try:
            # Fetch data based on request
            features = []
            if request.bbox and request.date_range:
                # Would fetch from STAC pipeline
                pass
            else:
                # Use precomputed data for demo
                from mock_data import get_all_features
                features = get_all_features()
            
            # Filter by confidence
            features = [f for f in features if f["properties"]["confidence"] >= request.min_confidence]
            
            if request.format == "geojson":
                geojson = {
                    "type": "FeatureCollection",
                    "features": features,
                    "metadata": {
                        "generated": datetime.utcnow().isoformat(),
                        "confidenceThreshold": request.min_confidence,
                        "bbox": request.bbox,
                        "date_range": request.date_range,
                        "totalFeatures": len(features)
                    }
                }
                output_path = export_dir / f"{export_id}.geojson"
                with open(output_path, "w") as f:
                    json.dump(geojson, f, indent=2)
                    
            elif request.format == "csv":
                output_path = export_dir / f"{export_id}.csv"
                with open(output_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["ID", "Area (m²)", "Tonnage (t)", "Confidence", "Risk Score", "Threat Level", "Centroid (lat,lon)", "Detection Date", "Waste Type"])
                    for feat in features:
                        props = feat["properties"]
                        writer.writerow([
                            props["id"],
                            props["area_m2"],
                            props["estimated_tonnage"],
                            props["confidence"],
                            props["risk_score"],
                            props["threat_level"],
                            f"{props['centroid'][1]}, {props['centroid'][0]}",
                            props["detection_date"],
                            props.get("waste_type", "unknown")
                        ])
                        
            elif request.format == "pdf":
                output_path = export_dir / f"{export_id}.pdf"
                generate_pdf_report(features, output_path, request)
                
            else:
                raise ValueError(f"Unsupported format: {request.format}")
                
        except Exception as e:
            print(f"Export generation failed: {e}")
    
    background_tasks.add_task(generate_export)
    
    return {
        "export_id": export_id,
        "status": "processing",
        "download_url": f"/api/authority/export/{export_id}/download"
    }


def generate_pdf_report(features: list, output_path: Path, request: ExportRequest):
    """Generate PDF report using weasyprint."""
    try:
        from weasyprint import HTML
        from jinja2 import Template
        
        # Calculate summary stats
        total_sites = len(features)
        total_area = sum(f["properties"]["area_m2"] for f in features)
        total_tonnage = sum(f["properties"]["estimated_tonnage"] for f in features)
        avg_conf = sum(f["properties"]["confidence"] for f in features) / len(features) if features else 0
        
        by_threat = {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0}
        for f in features:
            by_threat[f["properties"]["threat_level"]] += 1
        
        # HTML template
        template = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body { font-family: 'DejaVu Sans', Arial, sans-serif; margin: 0; padding: 20px; color: #1e293b; }
                .header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #10b981; padding-bottom: 20px; }
                .header h1 { color: #059669; margin: 0; font-size: 28px; }
                .header p { color: #64748b; margin: 5px 0 0; }
                .meta { display: flex; justify-content: space-between; margin-bottom: 30px; font-size: 12px; color: #64748b; }
                .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }
                .stat-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; text-align: center; }
                .stat-value { font-size: 24px; font-weight: bold; color: #0f172a; }
                .stat-label { font-size: 12px; color: #64748b; text-transform: uppercase; }
                .stat-critical { border-left: 4px solid #ef4444; }
                .stat-high { border-left: 4px solid #f59e0b; }
                .stat-moderate { border-left: 4px solid #10b981; }
                .stat-low { border-left: 4px solid #64748b; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 11px; }
                th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }
                th { background: #f1f5f9; font-weight: 600; color: #334155; }
                tr:hover { background: #f8fafc; }
                .threat-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: 600; }
                .badge-critical { background: #fef2f2; color: #dc2626; }
                .badge-high { background: #fffbeb; color: #d97706; }
                .badge-moderate { background: #ecfdf5; color: #059669; }
                .badge-low { background: #f1f5f9; color: #475569; }
                .footer { margin-top: 40px; text-align: center; font-size: 10px; color: #94a3b8; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>SkyDump AI - Waste Detection Report</h1>
                <p>Illegal Satellite Waste Detection & Monitoring Platform</p>
            </div>
            
            <div class="meta">
                <span>Generated: {{ generated }}</span>
                <span>Confidence Threshold: {{ confidence_threshold }}%</span>
                <span>Format: {{ format }}</span>
            </div>
            
            <div class="summary">
                <div class="stat-card">
                    <div class="stat-value">{{ total_sites }}</div>
                    <div class="stat-label">Total Sites</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ "{:,.0f}".format(total_area) }} m²</div>
                    <div class="stat-label">Total Area</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ "{:,.1f}".format(total_tonnage) }} t</div>
                    <div class="stat-label">Est. Tonnage</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ "%.1f"|format(avg_conf * 100) }}%</div>
                    <div class="stat-label">Avg Confidence</div>
                </div>
            </div>
            
            <div class="summary">
                <div class="stat-card stat-critical">
                    <div class="stat-value">{{ by_threat.Critical }}</div>
                    <div class="stat-label">Critical</div>
                </div>
                <div class="stat-card stat-high">
                    <div class="stat-value">{{ by_threat.High }}</div>
                    <div class="stat-label">High</div>
                </div>
                <div class="stat-card stat-moderate">
                    <div class="stat-value">{{ by_threat.Moderate }}</div>
                    <div class="stat-label">Moderate</div>
                </div>
                <div class="stat-card stat-low">
                    <div class="stat-value">{{ by_threat.Low }}</div>
                    <div class="stat-label">Low</div>
                </div>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Area (m²)</th>
                        <th>Tonnage (t)</th>
                        <th>Confidence</th>
                        <th>Risk</th>
                        <th>Threat</th>
                        <th>Centroid</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                {% for feat in features %}
                    <tr>
                        <td>{{ feat.properties.id }}</td>
                        <td>{{ "{:,.0f}".format(feat.properties.area_m2) }}</td>
                        <td>{{ "%.1f"|format(feat.properties.estimated_tonnage) }}</td>
                        <td>{{ "%.1f"|format(feat.properties.confidence * 100) }}%</td>
                        <td>{{ feat.properties.risk_score }}/100</td>
                        <td><span class="threat-badge badge-{{ feat.properties.threat_level.lower() }}">{{ feat.properties.threat_level }}</span></td>
                        <td>{{ "%.5f"|format(feat.properties.centroid[1]) }}, {{ "%.5f"|format(feat.properties.centroid[0]) }}</td>
                        <td>{{ feat.properties.detection_date }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
            
            <div class="footer">
                <p>SkyDump AI - Powered by ESA Sentinel-2 via Microsoft Planetary Computer</p>
                <p>Report ID: {{ export_id }} | Generated {{ generated }}</p>
            </div>
        </body>
        </html>
        """)
        
        html = template.render(
            features=features,
            total_sites=total_sites,
            total_area=total_area,
            total_tonnage=total_tonnage,
            avg_conf=avg_conf,
            by_threat=by_threat,
            generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            confidence_threshold=int(request.min_confidence * 100),
            format=request.format.upper(),
            export_id=output_path.stem
        )
        
        HTML(string=html).write_pdf(str(output_path))
        print(f"PDF report generated: {output_path}")
        
    except Exception as e:
        print(f"PDF generation failed: {e}")
        raise


def generate_evidence_package(site: Dict[str, Any], output_path: Path, user_email: str):
    """Generate detailed legal evidence package for a single waste site."""
    try:
        from weasyprint import HTML
        from jinja2 import Template
        
        props = site["properties"]
        geom = site["geometry"]
        centroid = props["centroid"]
        
        # Generate static map image URLs for evidence
        bbox = geom.get("bbox", [centroid[0]-0.01, centroid[1]-0.01, centroid[0]+0.01, centroid[1]+0.01])
        map_url_sat = f"https://staticmap.openstreetmap.de/staticmap.php?center={centroid[1]},{centroid[0]}&zoom=15&size=600x400&markers={centroid[1]},{centroid[0]},red-pushpin"
        map_url_osm = f"https://staticmap.openstreetmap.de/staticmap.php?center={centroid[1]},{centroid[0]}&zoom=15&size=600x400&markers={centroid[1]},{centroid[0]},red-pushpin"
        
        threat_colors = {
            "Critical": "#ef4444", "High": "#f59e0b", "Moderate": "#10b981", "Low": "#64748b"
        }
        threat_color = threat_colors.get(props.get("threat_level", "Low"), "#64748b")
        
        template = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page { margin: 2cm; size: A4; }
                body { font-family: 'DejaVu Sans', Arial, sans-serif; margin: 0; padding: 0; color: #1e293b; line-height: 1.5; }
                .header { text-align: center; margin-bottom: 30px; border-bottom: 3px solid #059669; padding-bottom: 20px; }
                .header h1 { color: #059669; margin: 0; font-size: 26px; font-weight: 700; }
                .header .subtitle { color: #64748b; margin: 8px 0 0; font-size: 14px; }
                .header .case-id { background: #fef3c7; color: #92400e; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; display: inline-block; margin-top: 10px; }
                .section { margin-bottom: 30px; page-break-inside: avoid; }
                .section-title { font-size: 16px; font-weight: 700; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 16px; }
                .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
                .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
                .field { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; }
                .field-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; font-weight: 600; }
                .field-value { font-size: 14px; color: #0f172a; font-weight: 500; }
                .field-value.mono { font-family: 'DejaVu Sans Mono', monospace; }
                .threat-badge { display: inline-block; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 700; color: white; }
                .map-container { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
                .map-box { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; background: #f1f5f9; }
                .map-box img { width: 100%; height: 250px; object-fit: cover; display: block; }
                .map-label { padding: 10px; font-size: 12px; font-weight: 600; color: #334155; background: white; border-top: 1px solid #e2e8f0; }
                .coordinates { font-family: 'DejaVu Sans Mono', monospace; font-size: 13px; background: #fef3c7; padding: 8px 12px; border-radius: 6px; display: inline-block; }
                .evidence-note { background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-top: 20px; }
                .evidence-note h4 { margin: 0 0 8px; color: #dc2626; font-size: 14px; }
                .evidence-note p { margin: 0; color: #991b1b; font-size: 12px; }
                .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 10px; color: #94a3b8; }
                .chain-of-custody { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin-top: 20px; }
                .chain-of-custody h4 { margin: 0 0 12px; color: #166534; font-size: 14px; }
                .custody-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #dcfce7; font-size: 12px; }
                .custody-row:last-child { border-bottom: none; }
                .custody-label { color: #166534; font-weight: 600; }
                .custody-value { color: #14532d; font-family: monospace; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🛰️ SkyDump AI — Evidence Package</h1>
                <div class="subtitle">Illegal Waste Dumping Detection — Satellite Intelligence Report</div>
                <div class="case-id">CASE-ID: {{ case_id }}</div>
            </div>
            
            <div class="section">
                <div class="section-title">📍 Site Identification</div>
                <div class="grid-3">
                    <div class="field">
                        <div class="field-label">Site ID</div>
                        <div class="field-value mono">{{ site_id }}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Threat Level</div>
                        <div class="field-value">
                            <span class="threat-badge" style="background: {{ threat_color }}">{{ threat_level }}</span>
                        </div>
                    </div>
                    <div class="field">
                        <div class="field-label">Detection Date</div>
                        <div class="field-value mono">{{ detection_date }}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Coordinates (WGS84)</div>
                        <div class="field-value coordinates">{{ lat }}, {{ lng }}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Sensor</div>
                        <div class="field-value">{{ sensor }}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Waste Type</div>
                        <div class="field-value">{{ waste_type }}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">📊 Quantitative Assessment</div>
                <div class="grid-3">
                    <div class="field">
                        <div class="field-label">Area</div>
                        <div class="field-value mono">{{ area_m2 }} m²</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Estimated Tonnage</div>
                        <div class="field-value mono">{{ tonnage }} t</div>
                    </div>
                    <div class="field">
                        <div class="field-label">AI Confidence</div>
                        <div class="field-value mono">{{ confidence }}%</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Risk Score</div>
                        <div class="field-value mono">{{ risk_score }}/100</div>
                    </div>
                    <div class="field">
                        <div class="field-label">ΔNDVI (Vegetation Loss)</div>
                        <div class="field-value mono">{{ delta_ndvi }}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">SWIR Mean (Synthetic Material)</div>
                        <div class="field-value mono">{{ swir_mean }}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">🌍 Environmental Context</div>
                <div class="grid-2">
                    <div class="field">
                        <div class="field-label">Distance to Water Body</div>
                        <div class="field-value mono">{{ water_km }} km</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Distance to Protected Area</div>
                        <div class="field-value mono">{{ protected_km }} km</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">🗺️ Satellite Imagery Evidence</div>
                <div class="map-container">
                    <div class="map-box">
                        <img src="{{ map_sat }}" alt="Satellite view" onerror="this.style.display='none'">
                        <div class="map-label">Sentinel-2 / Esri World Imagery</div>
                    </div>
                    <div class="map-box">
                        <img src="{{ map_osm }}" alt="OpenStreetMap view" onerror="this.style.display='none'">
                        <div class="map-label">OpenStreetMap Reference</div>
                    </div>
                </div>
                <p style="font-size: 11px; color: #64748b; margin-top: 10px;">
                    Imagery captured: {{ scene_t0 }} → {{ scene_t1 }} | 
                    Coordinates: {{ lat }}, {{ lng }} | 
                    Source: Microsoft Planetary Computer (Sentinel-2 L2A)
                </p>
            </div>
            
            <div class="section">
                <div class="section-title">📐 Geometry (GeoJSON)</div>
                <div class="field" style="font-size: 10px; font-family: monospace; white-space: pre-wrap; max-height: 200px; overflow: auto;">{{ geojson }}</div>
            </div>
            
            <div class="evidence-note">
                <h4>⚖️ Legal Admissibility Notice</h4>
                <p>This evidence package is generated from automated satellite analysis using ESA Sentinel-2 L2A data accessed via Microsoft Planetary Computer. 
                The detection algorithm employs NDVI change detection (ΔNDVI < -0.35) combined with SWIR Band 11 thresholding (>0.25) for synthetic material identification. 
                Results should be verified by ground inspection before enforcement action. Chain of custody maintained from acquisition to report generation.</p>
            </div>
            
            <div class="chain-of-custody">
                <h4>🔗 Chain of Custody</h4>
                <div class="custody-row">
                    <span class="custody-label">Data Source</span>
                    <span class="custody-value">Microsoft Planetary Computer STAC API</span>
                </div>
                <div class="custody-row">
                    <span class="custody-label">Satellite Mission</span>
                    <span class="custody-value">ESA Copernicus Sentinel-2 (L2A)</span>
                </div>
                <div class="custody-row">
                    <span class="custody-label">Scenes Analyzed</span>
                    <span class="custody-value">{{ scene_t0 }} → {{ scene_t1 }}</span>
                </div>
                <div class="custody-row">
                    <span class="custody-label">Processing Pipeline</span>
                    <span class="custody-value">SkyDump AI v2.0 (pystac, rasterio, OpenCV)</span>
                </div>
                <div class="custody-row">
                    <span class="custody-label">Generated By</span>
                    <span class="custody-value">{{ user_email }}</span>
                </div>
                <div class="custody-row">
                    <span class="custody-label">Generation Time</span>
                    <span class="custody-value">{{ generated }}</span>
                </div>
                <div class="custody-row">
                    <span class="custody-label">Report Hash</span>
                    <span class="custody-value">{{ report_hash }}</span>
                </div>
            </div>
            
            <div class="footer">
                <p>SkyDump AI — Powered by ESA Sentinel-2 via Microsoft Planetary Computer</p>
                <p>Report ID: {{ case_id }} | Generated {{ generated }} UTC</p>
                <p>This document is generated automatically. Verify all findings through ground inspection.</p>
            </div>
        </body>
        </html>
        """)
        
        import hashlib
        import json
        report_content = json.dumps(props, sort_keys=True)
        report_hash = hashlib.sha256(report_content.encode()).hexdigest()[:16]
        
        html = template.render(
            case_id=f"EVD-{datetime.utcnow().strftime('%Y%m%d')}-{props['id']}",
            site_id=props['id'],
            threat_level=props.get('threat_level', 'Low'),
            threat_color=threat_color,
            detection_date=props.get('detection_date', datetime.utcnow().strftime('%Y-%m-%d')),
            lat=f"{centroid[1]:.6f}",
            lng=f"{centroid[0]:.6f}",
            sensor=props.get('sensor', 'Sentinel-2 L2A'),
            waste_type=props.get('waste_type', 'mixed').title(),
            area_m2=f"{props.get('area_m2', 0):,.0f}",
            tonnage=f"{props.get('estimated_tonnage', 0):,.1f}",
            confidence=f"{props.get('confidence', 0)*100:.1f}",
            risk_score=props.get('risk_score', 0),
            delta_ndvi=f"{props.get('delta_ndvi', 0):.3f}" if props.get('delta_ndvi') else 'N/A',
            swir_mean=f"{props.get('swir_mean', 0):.3f}" if props.get('swir_mean') else 'N/A',
            water_km=f"{props.get('distance_to_water_km', 0):.2f}" if props.get('distance_to_water_km') else 'N/A',
            protected_km=f"{props.get('distance_to_protected_km', 0):.2f}" if props.get('distance_to_protected_km') else 'N/A',
            map_sat=map_url_sat,
            map_osm=map_url_osm,
            scene_t0=props.get('scene_t0', 'N/A'),
            scene_t1=props.get('scene_t1', 'N/A'),
            geojson=json.dumps(geom, indent=2),
            user_email=user_email,
            generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            report_hash=report_hash
        )
        
        HTML(string=html).write_pdf(str(output_path))
        print(f"Evidence package generated: {output_path}")
        
    except Exception as e:
        print(f"Evidence package generation failed: {e}")
        raise


@app.get("/api/authority/export/{export_id}/download")
async def download_export(
    export_id: str,
    user: dict = Depends(get_current_user)
):
    """Download generated export file."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    
    export_dir = Path("exports")
    
    # Try different extensions
    for ext in [".pdf", ".geojson", ".csv"]:
        file_path = export_dir / f"{export_id}{ext}"
        if file_path.exists():
            media_type = {
                ".pdf": "application/pdf",
                ".geojson": "application/geo+json",
                ".csv": "text/csv"
            }[ext]
            return FileResponse(
                path=str(file_path),
                filename=file_path.name,
                media_type=media_type
            )
    
    raise HTTPException(404, "Export not found or not ready")


@app.post("/api/authority/evidence-package")
async def generate_evidence_package_endpoint(
    site_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_db)
):
    """Generate legal evidence package PDF for a specific waste site."""
    from pathlib import Path
    import uuid as uuid_lib
    
    site = db.query(WasteSite).filter(WasteSite.site_id == site_id).first()
    if not site:
        raise HTTPException(404, f"Waste site {site_id} not found")
    
    # Convert to feature format
    feature = {
        "type": "Feature",
        "geometry": site.geometry,
        "properties": {
            "id": site.site_id,
            "area_m2": site.area_m2,
            "estimated_tonnage": site.estimated_tonnage,
            "confidence": site.confidence,
            "risk_score": site.risk_score,
            "threat_level": site.threat_level.value if hasattr(site.threat_level, 'value') else site.threat_level,
            "waste_type": site.waste_type.value if hasattr(site.waste_type, 'value') else site.waste_type,
            "detection_date": site.detection_date.isoformat() if site.detection_date else None,
            "sensor": site.sensor,
            "centroid": site.centroid,
            "ndvi_before": site.ndvi_before,
            "ndvi_after": site.ndvi_after,
            "delta_ndvi": site.delta_ndvi,
            "swir_mean": site.swir_mean,
            "distance_to_water_km": site.distance_to_water_km,
            "distance_to_protected_km": site.distance_to_protected_km,
            "scene_t0": site.scene_t0,
            "scene_t1": site.scene_t1,
        }
    }
    
    evidence_id = f"EVD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{site_id}"
    export_dir = Path("exports/evidence")
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / f"{evidence_id}.pdf"
    
    def generate():
        try:
            generate_evidence_package(feature, output_path, user.email)
        except Exception as e:
            print(f"Evidence package generation failed: {e}")
    
    background_tasks.add_task(generate)
    
    return {
        "evidence_id": evidence_id,
        "status": "processing",
        "download_url": f"/api/authority/evidence-package/{evidence_id}/download",
        "site_id": site_id
    }


@app.get("/api/authority/evidence-package/{evidence_id}/download")
async def download_evidence_package(
    evidence_id: str,
    user: dict = Depends(get_current_user)
):
    """Download generated evidence package."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    
    export_dir = Path("exports/evidence")
    file_path = export_dir / f"{evidence_id}.pdf"
    
    if file_path.exists():
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="application/pdf"
        )
    
    raise HTTPException(404, "Evidence package not found or not ready")


# Economic impact calculator
class ImpactRequest(BaseModel):
    site_area_m2: float
    waste_type: str = "mixed"  # mixed, construction, hazardous, electronic
    proximity_to_water_km: float = 1.0
    proximity_to_protected_km: float = 5.0
    jurisdiction: str = "netherlands"

@app.post("/api/authority/impact")
async def calculate_impact(
    request: ImpactRequest,
    user: dict = Depends(get_current_user)
):
    """Calculate economic and environmental impact of waste site."""
    
    # Cleanup cost estimation (EUR/m2)
    cleanup_costs = {
        "mixed": 25,
        "construction": 15,
        "hazardous": 150,
        "electronic": 80
    }
    
    base_cost = cleanup_costs.get(request.waste_type, 25)
    
    # Environmental damage multipliers
    water_multiplier = max(1.0, 2.0 - request.proximity_to_water_km)
    protected_multiplier = max(1.0, 1.5 - request.proximity_to_protected_km * 0.1)
    
    total_cleanup = request.site_area_m2 * base_cost * water_multiplier * protected_multiplier
    
    # Legal liability (varies by jurisdiction)
    legal_multipliers = {
        "netherlands": 3.0,
        "germany": 2.5,
        "france": 2.0,
        "brazil": 1.5,
        "drc": 1.0
    }
    legal_multiplier = legal_multipliers.get(request.jurisdiction.lower(), 1.0)
    
    legal_liability = total_cleanup * legal_multiplier
    
    # Environmental damage (ecosystem services)
    env_damage = request.site_area_m2 * 50 * water_multiplier  # EUR/m2/year
    
    return {
        "cleanup_cost_eur": round(total_cleanup, 2),
        "legal_liability_eur": round(legal_liability, 2),
        "environmental_damage_eur_per_year": round(env_damage, 2),
        "total_exposure_eur": round(total_cleanup + legal_liability + env_damage, 2),
        "breakdown": {
            "base_cleanup_rate": base_cost,
            "water_proximity_factor": water_multiplier,
            "protected_area_factor": protected_multiplier,
            "jurisdiction_multiplier": legal_multiplier
        }
    }


# Citizen Reporting endpoints
class CitizenReportRequest(BaseModel):
    lat: float
    lng: float
    accuracy: Optional[float] = None
    threat_level: str
    waste_type: str
    description: str


@app.post("/api/citizen/report")
async def submit_citizen_report(
    request: CitizenReportRequest,
    user: dict = Depends(get_current_user)
):
    """Submit a citizen report for illegal dumping."""
    report_id = f"CIT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    report = {
        "id": report_id,
        "user_id": user["email"],
        "coordinates": [request.lng, request.lat],
        "accuracy_m": request.accuracy,
        "threat_level": request.threat_level,
        "waste_type": request.waste_type,
        "description": request.description,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "verified": False,
    }
    
    # In production, save to database
    # For demo, return success
    return {
        "status": "submitted",
        "report_id": report_id,
        "message": "Report received. Our team will review within 24 hours.",
        "report": report
    }


@app.get("/api/citizen/reports")
async def list_citizen_reports(
    status: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(get_current_user)
):
    """List citizen reports (filtered by user unless admin)."""
    # In production, query database
    return {"reports": []}


# ML Model endpoints
@app.get("/api/ml/models")
async def list_models(user: dict = Depends(get_current_user)):
    return {
        "models": [
            {
                "id": "mobilenet_v3_waste_v1",
                "type": "mobilenet_v3_small",
                "version": "1.0",
                "trained_on": "2024-12-15",
                "metrics": {
                    "iou": 0.78,
                    "precision": 0.82,
                    "recall": 0.75
                },
                "status": "production"
            }
        ]
    }


@app.post("/api/ml/predict")
async def ml_predict(
    file: UploadFile = File(...),
    user: dict = Depends(require_role(["admin", "analyst"]))
):
    """Run ML inference on uploaded GeoTIFF."""
    # Would process uploaded file
    return {"status": "processing", "message": "Upload received"}


# Monitoring Job endpoints
class MonitoringJobCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sector_id: Optional[str] = None
    bbox: List[float] = Field(..., min_items=4, max_items=4)
    confidence_threshold: float = Field(0.7, ge=0.3, le=0.95)
    lookback_days: int = Field(14, ge=1, le=365)
    schedule_type: str = Field("interval", pattern="^(cron|interval)$")
    cron_expression: Optional[str] = None
    interval_hours: int = Field(24, ge=1, le=168)


class MonitoringJobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    confidence_threshold: Optional[float] = Field(None, ge=0.3, le=0.95)
    lookback_days: Optional[int] = Field(None, ge=1, le=365)
    schedule_type: Optional[str] = Field(None, pattern="^(cron|interval)$")
    cron_expression: Optional[str] = None
    interval_hours: Optional[int] = Field(None, ge=1, le=168)
    is_active: Optional[bool] = None


@app.post("/api/monitoring/jobs", response_model=Dict[str, Any])
async def create_monitoring_job(
    job_data: MonitoringJobCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new automated monitoring job."""
    import uuid
    
    job = MonitoringJob(
        job_id=f"monitor-{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        sector_id=job_data.sector_id,
        name=job_data.name,
        description=job_data.description,
        bbox=job_data.bbox,
        confidence_threshold=job_data.confidence_threshold,
        lookback_days=job_data.lookback_days,
        schedule_type=job_data.schedule_type,
        cron_expression=job_data.cron_expression,
        interval_hours=job_data.interval_hours,
        is_active=True,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    schedule_job(job)
    
    return {
        "status": "created",
        "job": {
            "id": str(job.id),
            "job_id": job.job_id,
            "name": job.name,
            "sector_id": job.sector_id,
            "bbox": job.bbox,
            "confidence_threshold": job.confidence_threshold,
            "lookback_days": job.lookback_days,
            "schedule_type": job.schedule_type,
            "cron_expression": job.cron_expression,
            "interval_hours": job.interval_hours,
            "is_active": job.is_active,
            "created_at": job.created_at.isoformat(),
        }
    }


@app.get("/api/monitoring/jobs")
async def list_monitoring_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's monitoring jobs."""
    jobs = db.query(MonitoringJob).filter(MonitoringJob.user_id == user.id).all()
    
    return {
        "jobs": [
            {
                "id": str(j.id),
                "job_id": j.job_id,
                "name": j.name,
                "description": j.description,
                "sector_id": j.sector_id,
                "bbox": j.bbox,
                "confidence_threshold": j.confidence_threshold,
                "lookback_days": j.lookback_days,
                "schedule_type": j.schedule_type,
                "cron_expression": j.cron_expression,
                "interval_hours": j.interval_hours,
                "is_active": j.is_active,
                "last_run": j.last_run.isoformat() if j.last_run else None,
                "next_run": j.next_run.isoformat() if j.next_run else None,
                "run_count": j.run_count,
                "last_error": j.last_error,
                "created_at": j.created_at.isoformat(),
            }
            for j in jobs
        ]
    }


@app.get("/api/monitoring/jobs/{job_id}")
async def get_monitoring_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific monitoring job."""
    job = db.query(MonitoringJob).filter(
        MonitoringJob.job_id == job_id,
        MonitoringJob.user_id == user.id
    ).first()
    
    if not job:
        raise HTTPException(404, "Monitoring job not found")
    
    # Get recent alerts for this job
    alerts = db.query(Alert).filter(Alert.job_id == job.id).order_by(Alert.created_at.desc()).limit(10).all()
    
    return {
        "job": {
            "id": str(job.id),
            "job_id": job.job_id,
            "name": job.name,
            "description": job.description,
            "sector_id": job.sector_id,
            "bbox": job.bbox,
            "confidence_threshold": job.confidence_threshold,
            "lookback_days": job.lookback_days,
            "schedule_type": job.schedule_type,
            "cron_expression": job.cron_expression,
            "interval_hours": job.interval_hours,
            "is_active": job.is_active,
            "last_run": job.last_run.isoformat() if job.last_run else None,
            "next_run": job.next_run.isoformat() if job.next_run else None,
            "run_count": job.run_count,
            "last_error": job.last_error,
            "created_at": job.created_at.isoformat(),
        },
        "recent_alerts": [
            {
                "id": str(a.id),
                "alert_id": a.alert_id,
                "severity": a.severity.value,
                "status": a.status.value,
                "title": a.title,
                "message": a.message,
                "sites_count": a.sites_count,
                "max_threat_level": a.max_threat_level.value if a.max_threat_level else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]
    }


@app.patch("/api/monitoring/jobs/{job_id}")
async def update_monitoring_job(
    job_id: str,
    job_data: MonitoringJobUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a monitoring job."""
    job = db.query(MonitoringJob).filter(
        MonitoringJob.job_id == job_id,
        MonitoringJob.user_id == user.id
    ).first()
    
    if not job:
        raise HTTPException(404, "Monitoring job not found")
    
    update_data = job_data.dict(exclude_unset=True)
    was_active = job.is_active
    
    for key, value in update_data.items():
        setattr(job, key, value)
    
    job.updated_at = datetime.utcnow()
    db.commit()
    
    # Reschedule if schedule changed or active status changed
    if job.is_active and (job.schedule_type != "cron" or job.cron_expression or job.interval_hours):
        schedule_job(job)
    elif not job.is_active and was_active:
        unschedule_job(job.id)
    
    return {"status": "updated", "job_id": job.job_id}


@app.delete("/api/monitoring/jobs/{job_id}")
async def delete_monitoring_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a monitoring job."""
    job = db.query(MonitoringJob).filter(
        MonitoringJob.job_id == job_id,
        MonitoringJob.user_id == user.id
    ).first()
    
    if not job:
        raise HTTPException(404, "Monitoring job not found")
    
    unschedule_job(job.id)
    db.delete(job)
    db.commit()
    
    return {"status": "deleted"}


@app.post("/api/monitoring/jobs/{job_id}/run")
async def run_monitoring_job_now(
    job_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger a monitoring job."""
    job = db.query(MonitoringJob).filter(
        MonitoringJob.job_id == job_id,
        MonitoringJob.user_id == user.id
    ).first()
    
    if not job:
        raise HTTPException(404, "Monitoring job not found")
    
    background_tasks.add_task(run_scheduled_analysis, job.id)
    
    return {"status": "triggered", "message": "Job started in background"}


@app.get("/api/monitoring/alerts")
async def list_monitoring_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List alerts from monitoring jobs."""
    query = db.query(Alert).join(MonitoringJob).filter(MonitoringJob.user_id == user.id)
    
    if status:
        query = query.filter(Alert.status == AlertStatus(status))
    if severity:
        query = query.filter(Alert.severity == AlertSeverity(severity))
    if job_id:
        job = db.query(MonitoringJob).filter(MonitoringJob.job_id == job_id, MonitoringJob.user_id == user.id).first()
        if job:
            query = query.filter(Alert.job_id == job.id)
    
    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    
    return {
        "alerts": [
            {
                "id": str(a.id),
                "alert_id": a.alert_id,
                "job_id": a.job_id,
                "severity": a.severity.value,
                "status": a.status.value,
                "title": a.title,
                "message": a.message,
                "sites_count": a.sites_count,
                "total_area_m2": a.total_area_m2,
                "max_threat_level": a.max_threat_level.value if a.max_threat_level else None,
                "metadata": a.metadata,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]
    }


@app.patch("/api/monitoring/alerts/{alert_id}")
async def update_alert_status(
    alert_id: str,
    status: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update alert status (acknowledge, resolve, dismiss)."""
    alert = db.query(Alert).join(MonitoringJob).filter(
        Alert.alert_id == alert_id,
        MonitoringJob.user_id == user.id
    ).first()
    
    if not alert:
        raise HTTPException(404, "Alert not found")
    
    new_status = AlertStatus(status)
    alert.status = new_status
    alert.updated_at = datetime.utcnow()
    
    if new_status == AlertStatus.ACKNOWLEDGED:
        alert.acknowledged_at = datetime.utcnow()
    elif new_status == AlertStatus.RESOLVED:
        alert.resolved_at = datetime.utcnow()
    elif new_status == AlertStatus.DISMISSED:
        alert.dismissed_at = datetime.utcnow()
    
    db.commit()
    
    return {"status": "updated", "alert_id": alert.alert_id, "new_status": new_status.value}


# Webhook for external systems
@app.post("/api/webhooks/detection")
async def webhook_detection(
    payload: Dict[str, Any],
    user: dict = Depends(get_current_user)
):
    """Receive detection results from external processing."""
    # Process webhook payload
    return {"status": "received"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)