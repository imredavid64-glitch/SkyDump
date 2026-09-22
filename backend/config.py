import os
import logging
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "SkyDump AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api"
    
    # STAC API
    STAC_API_URL: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    SENTINEL2_COLLECTION: str = "sentinel-2-l2a"
    MAX_CLOUD_COVER: int = 20
    
    # Anomaly detection thresholds
    NDVI_DELTA_THRESHOLD: float = -0.35
    SWIR_THRESHOLD: float = 0.25
    MIN_CONTOUR_AREA: float = 10000.0  # m^2
    
    # Risk scoring weights
    AREA_WEIGHT: float = 0.4
    CONFIDENCE_WEIGHT: float = 0.3
    PROXIMITY_WEIGHT: float = 0.3
    
    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "https://skydump.vercel.app"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)