import logging
import numpy as np
import cv2
from typing import Optional
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform as shapely_transform
from pyproj import Transformer
import json

from config import settings

logger = logging.getLogger(__name__)


class AnomalyEngine:
    def __init__(self):
        self.ndvi_threshold = settings.NDVI_DELTA_THRESHOLD
        self.swir_threshold = settings.SWIR_THRESHOLD
        self.min_contour_area = settings.MIN_CONTOUR_AREA

    def compute_delta_ndvi(self, ndvi_t0: np.ndarray, ndvi_t1: np.ndarray) -> np.ndarray:
        if ndvi_t0.shape != ndvi_t1.shape:
            raise ValueError(f"NDVI arrays must have same shape: {ndvi_t0.shape} vs {ndvi_t1.shape}")
        return ndvi_t1 - ndvi_t0

    def create_anomaly_mask(
        self,
        delta_ndvi: np.ndarray,
        swir11: np.ndarray
    ) -> np.ndarray:
        if delta_ndvi.shape != swir11.shape:
            swir11 = cv2.resize(swir11, (delta_ndvi.shape[1], delta_ndvi.shape[0]), interpolation=cv2.INTER_LINEAR)
        
        vegetation_loss = delta_ndvi < self.ndvi_threshold
        synthetic_material = swir11 > self.swir_threshold
        
        mask = vegetation_loss & synthetic_material
        return mask.astype(np.uint8) * 255

    def extract_polygons(
        self,
        mask: np.ndarray,
        transform: rasterio.Affine,
        crs: str
    ) -> list[dict]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        features = []
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        
        for contour in contours:
            area_px = cv2.contourArea(contour)
            if area_px < 10:
                continue
            
            epsilon = 0.01 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            
            coords = []
            for point in approx:
                x, y = point[0]
                lon, lat = transform * (x, y)
                coords.append((lon, lat))
            
            if len(coords) < 3:
                continue
            
            coords.append(coords[0])
            
            polygon = Polygon(coords)
            area_m2 = self._calculate_area_m2(polygon, crs)
            
            if area_m2 < self.min_contour_area:
                continue
            
            confidence = self._calculate_confidence(delta_ndvi=None, swir11=None, area_m2=area_m2)
            risk_score = self.calculate_risk_score(area_m2, confidence, 1.0)
            
            feature = {
                "type": "Feature",
                "geometry": mapping(polygon),
                "properties": {
                    "area_m2": round(area_m2, 2),
                    "confidence": round(confidence, 2),
                    "risk_score": risk_score,
                    "threat_level": self._get_threat_level(risk_score),
                    "estimated_tonnage": round(area_m2 * 0.15, 2),
                    "centroid": list(polygon.centroid.coords)[0]
                }
            }
            features.append(feature)
        
        return features

    def _calculate_area_m2(self, polygon: Polygon, crs: str) -> float:
        if crs != "EPSG:4326":
            transformer = Transformer.from_crs(crs, "EPSG:3857", always_xy=True)
            polygon = shapely_transform(transformer.transform, polygon)
        else:
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            polygon = shapely_transform(transformer.transform, polygon)
        return polygon.area

    def _calculate_confidence(self, delta_ndvi: Optional[np.ndarray], swir11: Optional[np.ndarray], area_m2: float) -> float:
        base_confidence = 0.6
        area_factor = min(area_m2 / 100000.0, 0.3)
        return min(base_confidence + area_factor, 0.95)

    def calculate_risk_score(self, area_m2: float, confidence: float, distance_to_water_km: float) -> int:
        area_norm = min(area_m2 / 500000.0, 1.0)
        conf_norm = confidence
        proximity_norm = max(1.0 - distance_to_water_km / 10.0, 0.0)
        
        score = (
            area_norm * settings.AREA_WEIGHT +
            conf_norm * settings.CONFIDENCE_WEIGHT +
            proximity_norm * settings.PROXIMITY_WEIGHT
        ) * 100
        
        return int(round(score))

    def _get_threat_level(self, risk_score: int) -> str:
        if risk_score >= 75:
            return "Critical"
        elif risk_score >= 50:
            return "High"
        elif risk_score >= 25:
            return "Moderate"
        else:
            return "Low"

    def process_scenes(
        self,
        bands_t0: dict,
        bands_t1: dict
    ) -> list[dict]:
        red_t0, transform_t0, crs_t0 = bands_t0["B04"]
        nir_t0, _, _ = bands_t0["B08"]
        swir_t0, _, _ = bands_t0["B11"]
        
        red_t1, transform_t1, crs_t1 = bands_t1["B04"]
        nir_t1, _, _ = bands_t1["B08"]
        swir_t1, _, _ = bands_t1["B11"]
        
        ndvi_t0 = self.compute_ndvi(nir_t0, red_t0)
        ndvi_t1 = self.compute_ndvi(nir_t1, red_t1)
        
        delta_ndvi = self.compute_delta_ndvi(ndvi_t0, ndvi_t1)
        
        mask = self.create_anomaly_mask(delta_ndvi, swir_t1)
        
        features = self.extract_polygons(mask, transform_t1, crs_t1)
        
        return features

    def compute_ndvi(self, nir: np.ndarray, red: np.ndarray) -> np.ndarray:
        denominator = nir + red + 1e-10
        ndvi = np.divide(nir - red, denominator, out=np.zeros_like(denominator), where=denominator != 0)
        return np.clip(ndvi, -1.0, 1.0)


def get_engine() -> AnomalyEngine:
    return AnomalyEngine()