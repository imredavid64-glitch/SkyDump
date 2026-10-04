import logging
from typing import Optional, List
from datetime import datetime
import numpy as np
import rasterio
from rasterio.windows import Window
from pystac_client import Client
from pystac import Item

from .config import settings
from .cache import stac_cache, get_cached_stac_search

logger = logging.getLogger(__name__)

# Sentinel-2 bands
BAND_ASSETS = {
    "B04": "red",
    "B08": "nir",
    "B11": "swir16"
}

SENTINEL2_RESOLUTION = {
    "B04": 10,
    "B08": 10,
    "B11": 20
}

# Sentinel-1 SAR bands
SAR_BAND_ASSETS = {
    "VV": "vv",
    "VH": "vh"
}

# Landsat bands (8-9)
LANDSAT_BAND_ASSETS = {
    "B4": "red",
    "B5": "nir",
    "B6": "swir1",
    "B7": "swir2"
}

# STAC Collections
SENTINEL2_COLLECTION = "sentinel-2-l2a"
SENTINEL1_COLLECTION = "sentinel-1-grd"
LANDSAT_COLLECTION = "landsat-c2-l2"


class STACPipeline:
    def __init__(self):
        self.client = Client.open(settings.STAC_API_URL)
        self.collection = settings.SENTINEL2_COLLECTION

    def search_scenes(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str,
        max_cloud_cover: Optional[int] = None,
        limit: int = 10
    ) -> list[Item]:
        max_cloud = max_cloud_cover or settings.MAX_CLOUD_COVER
        
        def _fetch():
            search = self.client.search(
                collections=[self.collection],
                bbox=bbox,
                datetime=f"{start_date}/{end_date}",
                query={"eo:cloud_cover": {"lt": max_cloud}},
                limit=limit
            )
            return [item.to_dict() for item in search.items()]
        
        # Try cache first (sync fallback if in event loop)
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # In event loop - skip cache to avoid deadlock
                cached = None
            except RuntimeError:
                # No running loop - safe to use asyncio.run
                cached = asyncio.run(get_cached_stac_search(
                    bbox, start_date, end_date, max_cloud, limit, _fetch
                ))
            
            if cached:
                items = [Item.from_dict(d) for d in cached]
                logger.info(f"Cache hit: {len(items)} Sentinel-2 scenes for bbox={bbox}")
                return items
        except Exception as e:
            logger.warning(f"Cache lookup failed, falling back to direct search: {e}")
        
        # Direct search
        search = self.client.search(
            collections=[self.collection],
            bbox=bbox,
            datetime=f"{start_date}/{end_date}",
            query={"eo:cloud_cover": {"lt": max_cloud}},
            limit=limit
        )
        
        items = list(search.items())
        logger.info(f"Found {len(items)} Sentinel-2 scenes for bbox={bbox}, dates={start_date}/{end_date}")
        return items

    def get_latest_two_scenes(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str
    ) -> tuple[Optional[Item], Optional[Item]]:
        items = self.search_scenes(bbox, start_date, end_date, limit=20)
        
        if len(items) < 2:
            logger.warning(f"Only {len(items)} scenes found, need at least 2 for change detection")
            return (items[0] if items else None, None)
        
        items_sorted = sorted(items, key=lambda x: x.datetime or datetime.min, reverse=True)
        return items_sorted[0], items_sorted[1]

    def fetch_band_data(self, item: Item, band: str) -> tuple[np.ndarray, rasterio.Affine, str]:
        if band not in BAND_ASSETS:
            raise ValueError(f"Band {band} not supported. Available: {list(BAND_ASSETS.keys())}")
        
        # Try cache first (sync fallback if in event loop)
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # In event loop - skip cache to avoid deadlock
                cached = None
            except RuntimeError:
                # No running loop - safe to use asyncio.run
                cached = asyncio.run(stac_cache.get_band_data(item.id, band))
            
            if cached:
                import numpy as np
                data = np.array(cached["data"], dtype=np.float32)
                from rasterio import Affine
                transform = Affine(*cached["transform"])
                crs = cached["crs"]
                logger.debug(f"Cache hit for band {band} of item {item.id}")
                return data, transform, crs
        except Exception as e:
            logger.warning(f"Band cache lookup failed: {e}")
        
        if band not in BAND_ASSETS:
            raise ValueError(f"Band {band} not supported. Available: {list(BAND_ASSETS.keys())}")
        
        asset_key = BAND_ASSETS[band]
        if asset_key not in item.assets:
            raise ValueError(f"Asset {asset_key} not found in item {item.id}")
        
        asset = item.assets[asset_key]
        with rasterio.open(asset.href) as src:
            data = src.read(1).astype(np.float32)
            transform = src.transform
            crs = str(src.crs)
        
        # Cache the band data (sync fallback)
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(stac_cache.set_band_data(item.id, band, {
                    "data": data.tolist(),
                    "transform": list(transform),
                    "crs": crs
                }))
        except Exception as e:
            logger.warning(f"Band cache set failed: {e}")
            
        return data, transform, crs

    def fetch_all_bands(self, item: Item) -> dict[str, tuple[np.ndarray, rasterio.Affine, str]]:
        bands = {}
        for band in BAND_ASSETS.keys():
            try:
                bands[band] = self.fetch_band_data(item, band)
            except Exception as e:
                logger.error(f"Failed to fetch {band} for item {item.id}: {e}")
                raise
        return bands

    @staticmethod
    def compute_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
        denominator = nir + red + 1e-10
        ndvi = np.divide(nir - red, denominator, out=np.zeros_like(denominator), where=denominator != 0)
        return np.clip(ndvi, -1.0, 1.0)

    @staticmethod
    def resample_to_match(source: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
        import cv2
        return cv2.resize(source, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_LINEAR)


def get_pipeline() -> STACPipeline:
    return STACPipeline()


class SARPipeline:
    """Sentinel-1 SAR pipeline for all-weather detection."""
    
    def __init__(self):
        self.client = Client.open(settings.STAC_API_URL)
        self.collection = SENTINEL1_COLLECTION
    
    def search_scenes(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str,
        max_cloud_cover: Optional[int] = None,  # SAR doesn't use cloud cover
        limit: int = 10
    ) -> list[Item]:
        search = self.client.search(
            collections=[self.collection],
            bbox=bbox,
            datetime=f"{start_date}/{end_date}",
            query={"sat:orbit_state": {"eq": "descending"}},  # Prefer descending for consistency
            limit=limit
        )
        
        items = list(search.items())
        logger.info(f"Found {len(items)} Sentinel-1 SAR scenes for bbox={bbox}, dates={start_date}/{end_date}")
        return items
    
    def get_latest_two_scenes(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str
    ) -> tuple[Optional[Item], Optional[Item]]:
        items = self.search_scenes(bbox, start_date, end_date, limit=20)
        
        if len(items) < 2:
            logger.warning(f"Only {len(items)} SAR scenes found, need at least 2 for change detection")
            return (items[0] if items else None, None)
        
        items_sorted = sorted(items, key=lambda x: x.datetime or datetime.min, reverse=True)
        return items_sorted[0], items_sorted[1]
    
    def fetch_band_data(self, item: Item, band: str) -> tuple[np.ndarray, rasterio.Affine, str]:
        if band not in SAR_BAND_ASSETS:
            raise ValueError(f"SAR Band {band} not supported. Available: {list(SAR_BAND_ASSETS.keys())}")
        
        asset_key = SAR_BAND_ASSETS[band]
        if asset_key not in item.assets:
            raise ValueError(f"Asset {asset_key} not found in item {item.id}")
        
        asset = item.assets[asset_key]
        with rasterio.open(asset.href) as src:
            data = src.read(1).astype(np.float32)
            transform = src.transform
            crs = str(src.crs)
        
        return data, transform, crs
    
    def fetch_all_bands(self, item: Item) -> dict[str, tuple[np.ndarray, rasterio.Affine, str]]:
        bands = {}
        for band in SAR_BAND_ASSETS.keys():
            try:
                bands[band] = self.fetch_band_data(item, band)
            except Exception as e:
                logger.error(f"Failed to fetch SAR {band} for item {item.id}: {e}")
                raise
        return bands


class LandsatPipeline:
    """Landsat 8/9 pipeline for historical baseline (30+ years)."""
    
    def __init__(self):
        self.client = Client.open(settings.STAC_API_URL)
        self.collection = LANDSAT_COLLECTION
    
    def search_scenes(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str,
        max_cloud_cover: Optional[int] = 20,
        limit: int = 10
    ) -> list[Item]:
        max_cloud = max_cloud_cover or settings.MAX_CLOUD_COVER
        
        search = self.client.search(
            collections=[self.collection],
            bbox=bbox,
            datetime=f"{start_date}/{end_date}",
            query={"eo:cloud_cover": {"lt": max_cloud}},
            limit=limit
        )
        
        items = list(search.items())
        logger.info(f"Found {len(items)} Landsat scenes for bbox={bbox}, dates={start_date}/{end_date}")
        return items
    
    def get_latest_two_scenes(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str
    ) -> tuple[Optional[Item], Optional[Item]]:
        items = self.search_scenes(bbox, start_date, end_date, limit=20)
        
        if len(items) < 2:
            logger.warning(f"Only {len(items)} Landsat scenes found, need at least 2")
            return (items[0] if items else None, None)
        
        items_sorted = sorted(items, key=lambda x: x.datetime or datetime.min, reverse=True)
        return items_sorted[0], items_sorted[1]
    
    def fetch_band_data(self, item: Item, band: str) -> tuple[np.ndarray, rasterio.Affine, str]:
        if band not in LANDSAT_BAND_ASSETS:
            raise ValueError(f"Landsat Band {band} not supported. Available: {list(LANDSAT_BAND_ASSETS.keys())}")
        
        asset_key = LANDSAT_BAND_ASSETS[band]
        if asset_key not in item.assets:
            raise ValueError(f"Asset {asset_key} not found in item {item.id}")
        
        asset = item.assets[asset_key]
        with rasterio.open(asset.href) as src:
            data = src.read(1).astype(np.float32)
            transform = src.transform
            crs = str(src.crs)
        
        return data, transform, crs
    
    def fetch_all_bands(self, item: Item) -> dict[str, tuple[np.ndarray, rasterio.Affine, str]]:
        bands = {}
        for band in LANDSAT_BAND_ASSETS.keys():
            try:
                bands[band] = self.fetch_band_data(item, band)
            except Exception as e:
                logger.error(f"Failed to fetch Landsat {band} for item {item.id}: {e}")
                raise
        return bands


def get_sar_pipeline() -> SARPipeline:
    return SARPipeline()


def get_landsat_pipeline() -> LandsatPipeline:
    return LandsatPipeline()