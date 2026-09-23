import logging
from typing import Optional
from datetime import datetime
import numpy as np
import rasterio
from rasterio.windows import Window
from pystac_client import Client
from pystac import Item

from .config import settings

logger = logging.getLogger(__name__)

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
        
        asset_key = BAND_ASSETS[band]
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