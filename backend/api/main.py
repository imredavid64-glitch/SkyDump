from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging

from .config import settings
from .stac_pipeline import STACPipeline, get_pipeline
from .anomaly_engine import AnomalyEngine, get_engine
from .mock_data import get_sector_data, get_all_features, filter_features_by_confidence, calculate_summary_stats, MOCK_SECTORS

logger = logging.getLogger(__name__)

pipeline: Optional[STACPipeline] = None
engine: Optional[AnomalyEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, engine
    pipeline = get_pipeline()
    engine = get_engine()
    logger.info("SkyDump AI backend started")
    yield
    logger.info("SkyDump AI backend shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BBoxRequest(BaseModel):
    bbox: list[float] = Field(..., min_items=4, max_items=4, description="[min_lon, min_lat, max_lon, max_lat]")
    start_date: str = Field(..., description="ISO date string (YYYY-MM-DD)")
    end_date: str = Field(..., description="ISO date string (YYYY-MM-DD)")
    confidence_threshold: float = Field(0.7, ge=0.3, le=0.95)


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str


class AnalyzeResponse(BaseModel):
    features: list[dict]
    summary: dict
    metadata: dict


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        service=settings.APP_NAME
    )


@app.post("/api/analyze-bbox", response_model=AnalyzeResponse)
async def analyze_bbox(request: BBoxRequest):
    try:
        logger.info(f"Analyzing bbox: {request.bbox}, dates: {request.start_date} to {request.end_date}")
        
        item_t1, item_t0 = pipeline.get_latest_two_scenes(
            request.bbox, request.start_date, request.end_date
        )
        
        if not item_t1 or not item_t0:
            raise HTTPException(
                status_code=404,
                detail="Insufficient satellite imagery for the given bbox and date range. Need at least 2 scenes."
            )
        
        bands_t1 = pipeline.fetch_all_bands(item_t1)
        bands_t0 = pipeline.fetch_all_bands(item_t0)
        
        features = engine.process_scenes(bands_t0, bands_t1)
        
        filtered = filter_features_by_confidence(features, request.confidence_threshold)
        
        summary = calculate_summary_stats(filtered)
        
        return AnalyzeResponse(
            features=filtered,
            summary=summary,
            metadata={
                "scene_t0": item_t0.id,
                "scene_t1": item_t1.id,
                "date_t0": item_t0.datetime.isoformat() if item_t0.datetime else None,
                "date_t1": item_t1.datetime.isoformat() if item_t1.datetime else None,
                "bbox": request.bbox,
                "confidence_threshold": request.confidence_threshold
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/api/mock-sites")
async def get_mock_sites(sector: str = Query("sector-7", description="Sector ID: sector-7, sector-12, sector-4")):
    sector_data = get_sector_data(sector)
    features = sector_data["feature_collection"]["features"]
    summary = calculate_summary_stats(features)
    
    return {
        "sector": sector,
        "metadata": sector_data["metadata"],
        "features": features,
        "summary": summary
    }


@app.get("/api/sectors")
async def list_sectors():
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)