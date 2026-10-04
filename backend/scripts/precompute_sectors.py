#!/usr/bin/env python
"""
Pre-compute detection results for 3 demo sectors.
Generates realistic GeoJSON features that can be served instantly for demos.
Run offline to avoid rate limits during live demos.
"""
import json
import random
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

# Reproducible randomness
random.seed(42)
np.random.seed(42)

# Sector definitions (matching mock_data.py)
SECTORS = {
    "sector-7": {
        "id": "sector-7",
        "name": "Rotterdam Industrial Zone, Netherlands",
        "bbox": [4.2, 51.85, 4.5, 51.95],
        "center": [4.35, 51.9],
        "zoom": 12,
        "site_prefix": "RTM",
        "num_sites": 7,
        "base_lat": 51.9,
        "base_lon": 4.35,
    },
    "sector-12": {
        "id": "sector-12",
        "name": "Amazon River Basin, Brazil",
        "bbox": [-55.5, -3.5, -55.0, -3.0],
        "center": [-55.25, -3.25],
        "zoom": 12,
        "site_prefix": "AMZ",
        "num_sites": 6,
        "base_lat": -3.25,
        "base_lon": -55.25,
    },
    "sector-4": {
        "id": "sector-4",
        "name": "Congo Basin Forest Reserve, DRC",
        "bbox": [18.5, -1.5, 19.0, -1.0],
        "center": [18.75, -1.25],
        "zoom": 12,
        "site_prefix": "CGO",
        "num_sites": 8,
        "base_lat": -1.25,
        "base_lon": 18.75,
    }
}

THREAT_LEVELS = ["Critical", "High", "Moderate", "Low"]
THREAT_WEIGHTS = [0.15, 0.25, 0.35, 0.25]  # More moderate/low for realism

WASTE_TYPES = ["mixed", "construction", "hazardous", "electronic"]
WASTE_TYPE_WEIGHTS = [0.5, 0.3, 0.15, 0.05]

SENSORS = ["Sentinel-2A L2A", "Sentinel-2B L2A"]


def create_polygon_geometry(center_lon: float, center_lat: float, area_m2: float) -> list:
    """Create a realistic polygon geometry for a waste site."""
    # Approximate: 1 degree ≈ 111km at equator
    # For a given area in m², compute radius in degrees
    # area = π * r² → r = sqrt(area/π)
    radius_m = np.sqrt(area_m2 / np.pi)
    radius_deg = radius_m / 111000  # rough conversion
    
    # Create irregular polygon (8-12 vertices)
    num_vertices = random.randint(8, 12)
    coords = []
    for i in range(num_vertices):
        angle = 2 * np.pi * i / num_vertices
        # Add some randomness to radius
        r = radius_deg * random.uniform(0.7, 1.3)
        # Add some noise to angle
        angle += random.uniform(-0.1, 0.1)
        coords.append([
            center_lon + r * np.cos(angle),
            center_lat + r * np.sin(angle)
        ])
    coords.append(coords[0])  # Close polygon
    return [coords]


def generate_site(sector: dict, site_idx: int) -> dict:
    """Generate a single waste site feature."""
    prefix = sector["site_prefix"]
    site_id = f"{prefix}-{site_idx+1:03d}"
    
    # Random position within sector bbox
    bbox = sector["bbox"]
    lon = random.uniform(bbox[0] + 0.02, bbox[2] - 0.02)
    lat = random.uniform(bbox[1] + 0.02, bbox[3] - 0.02)
    
    # Area: 5,000 to 500,000 m²
    area_m2 = random.uniform(5000, 500000)
    
    # Confidence: 0.6 to 0.98
    confidence = random.uniform(0.6, 0.98)
    
    # Threat level based on area and confidence
    risk_base = (area_m2 / 500000) * 0.4 + confidence * 0.3 + random.uniform(0.2, 0.8) * 0.3
    risk_score = int(min(100, risk_base * 100))
    
    if risk_score >= 75:
        threat = "Critical"
    elif risk_score >= 50:
        threat = "High"
    elif risk_score >= 25:
        threat = "Moderate"
    else:
        threat = "Low"
    
    # Estimated tonnage (rough: 0.15 t/m² for mixed waste)
    waste_type = random.choices(WASTE_TYPES, weights=WASTE_TYPE_WEIGHTS)[0]
    density = {"mixed": 0.15, "construction": 0.3, "hazardous": 0.1, "electronic": 0.05}[waste_type]
    estimated_tonnage = area_m2 * density
    
    # Detection date: within last 30 days
    days_ago = random.randint(0, 30)
    detection_date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    
    # Spectral properties (simulated)
    ndvi_before = random.uniform(0.3, 0.8)
    ndvi_after = ndvi_before + random.uniform(-0.5, -0.15)
    swir_mean = random.uniform(0.15, 0.45)
    
    geometry = create_polygon_geometry(lon, lat, area_m2)
    
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": geometry
        },
        "properties": {
            "id": site_id,
            "area_m2": round(area_m2, 2),
            "confidence": round(confidence, 3),
            "risk_score": risk_score,
            "threat_level": threat,
            "estimated_tonnage": round(estimated_tonnage, 2),
            "centroid": [lon, lat],
            "detection_date": detection_date,
            "sensor": random.choice(SENSORS),
            "waste_type": waste_type,
            "ndvi_before": round(ndvi_before, 3),
            "ndvi_after": round(ndvi_after, 3),
            "delta_ndvi": round(ndvi_after - ndvi_before, 3),
            "swir_mean": round(swir_mean, 3),
            "distance_to_water_km": round(random.uniform(0.1, 10.0), 2),
            "distance_to_protected_km": round(random.uniform(0.5, 50.0), 2),
        }
    }


def generate_timeseries(sector: dict, features: list) -> dict:
    """Generate time-series data for a sector."""
    num_steps = 12  # Monthly for 1 year
    end_date = datetime.utcnow()
    dates = [(end_date - timedelta(days=30*i)).strftime("%Y-%m-%d") for i in range(num_steps)]
    dates.reverse()  # Oldest first
    
    # For each site, generate temporal evolution
    site_timeseries = {}
    for feat in features:
        site_id = feat["properties"]["id"]
        area_final = feat["properties"]["area_m2"]
        # Simulate growth from 0 to final area
        growth_curve = np.random.gamma(2, 1, num_steps)
        growth_curve = growth_curve / growth_curve.max() * area_final
        # Add some noise
        growth_curve = np.maximum.accumulate(growth_curve)  # Monotonic growth
        growth_curve += np.random.normal(0, area_final * 0.05, num_steps)
        growth_curve = np.clip(growth_curve, 0, area_final * 1.1)
        
        site_timeseries[site_id] = {
            "dates": dates,
            "area_m2": [round(a, 1) for a in growth_curve.tolist()],
            "confidence": [round(random.uniform(0.5, 0.95), 2) for _ in range(num_steps)],
            "ndvi": [round(random.uniform(-0.1, 0.3), 3) for _ in range(num_steps)],
        }
    
    return {
        "dates": dates,
        "sites": site_timeseries,
        "summary": {
            "total_area_m2": [round(sum(site_timeseries[s]["area_m2"][i] for s in site_timeseries), 1) 
                             for i in range(num_steps)],
            "num_active_sites": [sum(1 for s in site_timeseries if site_timeseries[s]["area_m2"][i] > 1000) 
                                for i in range(num_steps)],
        }
    }


def compute_summary(features: list) -> dict:
    """Compute summary statistics for a feature collection."""
    if not features:
        return {
            "total_sites": 0,
            "total_area_m2": 0,
            "total_tonnage": 0,
            "by_threat": {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0},
            "by_waste_type": {"mixed": 0, "construction": 0, "hazardous": 0, "electronic": 0},
            "avg_confidence": 0,
            "avg_risk_score": 0,
        }
    
    total_area = sum(f["properties"]["area_m2"] for f in features)
    total_tonnage = sum(f["properties"]["estimated_tonnage"] for f in features)
    avg_conf = sum(f["properties"]["confidence"] for f in features) / len(features)
    avg_risk = sum(f["properties"]["risk_score"] for f in features) / len(features)
    
    by_threat = {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0}
    by_waste = {"mixed": 0, "construction": 0, "hazardous": 0, "electronic": 0}
    
    for f in features:
        by_threat[f["properties"]["threat_level"]] += 1
        by_waste[f["properties"]["waste_type"]] += 1
    
    return {
        "total_sites": len(features),
        "total_area_m2": round(total_area, 2),
        "total_tonnage": round(total_tonnage, 2),
        "by_threat": by_threat,
        "by_waste_type": by_waste,
        "avg_confidence": round(avg_conf, 3),
        "avg_risk_score": round(avg_risk, 1),
    }


def main():
    output_dir = Path("api/precomputed")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    all_results = {}
    
    for sector_id, sector in SECTORS.items():
        print(f"Generating data for {sector['name']}...")
        
        # Generate features
        features = [generate_site(sector, i) for i in range(sector["num_sites"])]
        
        # Generate timeseries
        timeseries = generate_timeseries(sector, features)
        
        # Compute summary
        summary = compute_summary(features)
        
        # Create metadata
        metadata = {
            "id": sector_id,
            "name": sector["name"],
            "bbox": sector["bbox"],
            "center": sector["center"],
            "zoom": sector["zoom"],
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "scene_t0": f"S2A_MSIL2A_{datetime.utcnow().strftime('%Y%m%d')}T100000_R008_T31UFU_20240101",
            "scene_t1": f"S2B_MSIL2A_{datetime.utcnow().strftime('%Y%m%d')}T100000_R008_T31UFU_20240101",
            "processing_mode": "precomputed_demo",
        }
        
        # Create feature collection
        feature_collection = {
            "type": "FeatureCollection",
            "features": features,
        }
        
        # Save individual sector file
        sector_data = {
            "metadata": metadata,
            "feature_collection": feature_collection,
            "summary": summary,
            "timeseries": timeseries,
        }
        
        output_file = output_dir / f"{sector_id}.json"
        with open(output_file, "w") as f:
            json.dump(sector_data, f, indent=2)
        
        print(f"  Saved {len(features)} sites to {output_file}")
        
        all_results[sector_id] = sector_data
    
    # Create index file
    index = {
        "sectors": [
            {
                "id": k,
                "name": v["metadata"]["name"],
                "center": v["metadata"]["center"],
                "zoom": v["metadata"]["zoom"],
                "num_sites": v["summary"]["total_sites"],
                "total_area_m2": v["summary"]["total_area_m2"],
            }
            for k, v in all_results.items()
        ],
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
    }
    
    with open(output_dir / "index.json", "w") as f:
        json.dump(index, f, indent=2)
    
    print(f"\nGenerated index.json with {len(all_results)} sectors")
    print("Done!")


if __name__ == "__main__":
    main()