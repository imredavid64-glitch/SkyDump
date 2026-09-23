import random
import numpy as np
from typing import Dict, Any

random.seed(42)

SECTOR_7_INDUSTRIAL = {
    "name": "Sector 7 - Rotterdam Industrial Zone",
    "bbox": [4.2, 51.85, 4.5, 51.95],
    "center": [4.35, 51.9],
    "zoom": 12
}

SECTOR_12_RIVER = {
    "name": "Sector 12 - Amazon River Basin",
    "bbox": [-55.5, -3.5, -55.0, -3.0],
    "center": [-55.25, -3.25],
    "zoom": 12
}

SECTOR_4_FOREST = {
    "name": "Sector 4 - Congo Basin Forest Reserve",
    "bbox": [18.5, -1.5, 19.0, -1.0],
    "center": [18.75, -1.25],
    "zoom": 12
}


def create_polygon_features(base_lon: float, base_lat: float, count: int, prefix: str) -> list[Dict[str, Any]]:
    
    features = []
    for i in range(count):
        size = random.uniform(0.001, 0.005)
        lon_offset = random.uniform(-0.02, 0.02)
        lat_offset = random.uniform(-0.02, 0.02)
        
        center_lon = base_lon + lon_offset
        center_lat = base_lat + lat_offset
        
        coords = []
        for j in range(8):
            angle = j * (360 / 8) * 3.14159 / 180
            r = size * random.uniform(0.8, 1.2)
            coords.append([center_lon + r * np.cos(angle), center_lat + r * np.sin(angle)])
        coords.append(coords[0])
        
        area_m2 = random.uniform(5000, 200000)
        confidence = random.uniform(0.65, 0.95)
        risk_score = int(min(100, (area_m2 / 500000 * 0.4 + confidence * 0.3 + random.uniform(0.2, 0.8) * 0.3) * 100))
        
        if risk_score >= 75:
            threat = "Critical"
        elif risk_score >= 50:
            threat = "High"
        elif risk_score >= 25:
            threat = "Moderate"
        else:
            threat = "Low"
        
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords]
            },
            "properties": {
                "id": f"{prefix}-{i+1:03d}",
                "area_m2": round(area_m2, 2),
                "confidence": round(confidence, 2),
                "risk_score": risk_score,
                "threat_level": threat,
                "estimated_tonnage": round(area_m2 * 0.15, 2),
                "centroid": [center_lon, center_lat],
                "detection_date": "2024-12-15",
                "sensor": "Sentinel-2 L2A"
            }
        })
    return features


def get_mock_sectors() -> Dict[str, Dict[str, Any]]:
    
    sector_7_features = create_polygon_features(4.35, 51.9, 7, "RTM")
    sector_12_features = create_polygon_features(-55.25, -3.25, 6, "AMZ")
    sector_4_features = create_polygon_features(18.75, -1.25, 8, "CGO")
    
    return {
        "sector-7": {
            "metadata": SECTOR_7_INDUSTRIAL,
            "feature_collection": {
                "type": "FeatureCollection",
                "features": sector_7_features
            }
        },
        "sector-12": {
            "metadata": SECTOR_12_RIVER,
            "feature_collection": {
                "type": "FeatureCollection",
                "features": sector_12_features
            }
        },
        "sector-4": {
            "metadata": SECTOR_4_FOREST,
            "feature_collection": {
                "type": "FeatureCollection",
                "features": sector_4_features
            }
        }
    }


MOCK_SECTORS = get_mock_sectors()


def get_sector_data(sector_id: str) -> Dict[str, Any]:
    return MOCK_SECTORS.get(sector_id, MOCK_SECTORS["sector-7"])


def get_all_features() -> list[Dict[str, Any]]:
    all_features = []
    for sector_data in MOCK_SECTORS.values():
        all_features.extend(sector_data["feature_collection"]["features"])
    return all_features


def filter_features_by_confidence(features: list[Dict[str, Any]], threshold: float) -> list[Dict[str, Any]]:
    return [f for f in features if f["properties"]["confidence"] >= threshold]


def calculate_summary_stats(features: list[Dict[str, Any]]) -> Dict[str, Any]:
    if not features:
        return {
            "total_sites": 0,
            "total_area_m2": 0,
            "total_tonnage": 0,
            "by_threat": {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0},
            "avg_confidence": 0
        }
    
    total_area = sum(f["properties"]["area_m2"] for f in features)
    total_tonnage = sum(f["properties"]["estimated_tonnage"] for f in features)
    avg_conf = sum(f["properties"]["confidence"] for f in features) / len(features)
    
    by_threat = {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0}
    for f in features:
        by_threat[f["properties"]["threat_level"]] += 1
    
    return {
        "total_sites": len(features),
        "total_area_m2": round(total_area, 2),
        "total_tonnage": round(total_tonnage, 2),
        "by_threat": by_threat,
        "avg_confidence": round(avg_conf, 3)
    }