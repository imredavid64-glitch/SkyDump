"""Shared utilities for detection and alerting."""
from datetime import datetime
from typing import List, Dict, Any
import logging
import httpx
import asyncio

from api.config import settings

logger = logging.getLogger(__name__)

def deduplicate_detections(features: List[Dict], iou_threshold: float = 0.5) -> List[Dict]:
    """
    Deduplicate overlapping detections from multiple sensors using IoU.
    Keeps the detection with highest confidence when overlaps exceed threshold.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union
    
    if not features:
        return []
    
    # Sort by confidence descending
    sorted_features = sorted(features, key=lambda f: f["properties"].get("confidence", 0), reverse=True)
    
    kept = []
    for feat in sorted_features:
        geom = shape(feat["geometry"])
        is_duplicate = False
        
        for kept_feat in kept:
            kept_geom = shape(kept_feat["geometry"])
            
            # Calculate IoU
            intersection = geom.intersection(kept_geom).area
            union = geom.union(kept_geom).area
            iou = intersection / union if union > 0 else 0
            
            if iou > 0.5:  # Threshold for duplicate
                is_duplicate = True
                break
        
        if not is_duplicate:
            kept.append(feat)
    
    return kept

async def send_webhook_alerts(features: List[Dict], bbox: List[float], user_email: str):
    """Send webhook alerts for critical/high threat detections."""
    critical_sites = [f for f in features if f["properties"].get("threat_level") in ("Critical", "High")]
    if not critical_sites:
        return
    
    # Discord webhook
    if settings.DISCORD_WEBHOOK_URL:
        try:
            embeds = []
            for site in critical_sites[:5]:  # Limit to 5 sites
                props = site["properties"]
                color = 0xFF0000 if props.get("threat_level") == "Critical" else 0xFFA500
                embeds.append({
                    "title": f"🚨 {props.get('threat_level')} Waste Detection: {props.get('id')}",
                    "description": f"New waste site detected in sector",
                    "color": color,
                    "fields": [
                        {"name": "Area", "value": f"{props.get('area_m2', 0):,.0f} m²", "inline": True},
                        {"name": "Est. Tonnage", "value": f"{props.get('estimated_tonnage', 0):,.1f} t", "inline": True},
                        {"name": "Confidence", "value": f"{props.get('confidence', 0)*100:.1f}%", "inline": True},
                        {"name": "Coordinates", "value": f"{props.get('centroid', [0,0])[1]:.5f}, {props.get('centroid', [0,0])[0]:.5f}", "inline": True},
                        {"name": "Threat Level", "value": props.get('threat_level'), "inline": True},
                        {"name": "Waste Type", "value": props.get('waste_type', 'unknown'), "inline": True},
                    ],
                    "footer": {"text": f"Detected by {user_email} | SkyDump AI"},
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            async with httpx.AsyncClient() as client:
                await client.post(settings.DISCORD_WEBHOOK_URL, json={"embeds": embeds}, timeout=10)
        except Exception as e:
            logger.warning(f"Failed to send Discord webhook: {e}")
    
    # Slack webhook
    if settings.SLACK_WEBHOOK_URL:
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🚨 SkyDump Alert: {len(critical_sites)} Critical/High Detections"}
                }
            ]
            for site in critical_sites[:5]:
                props = site["properties"]
                blocks.append({
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Site:* {props.get('id')}"},
                        {"type": "mrkdwn", "text": f"*Threat:* {props.get('threat_level')}"},
                        {"type": "mrkdwn", "text": f"*Area:* {props.get('area_m2', 0):,.0f} m²"},
                        {"type": "mrkdwn", "text": f"*Confidence:* {props.get('confidence', 0)*100:.1f}%"},
                    ]
                })
            
            async with httpx.AsyncClient() as client:
                await client.post(settings.SLACK_WEBHOOK_URL, json={"blocks": blocks}, timeout=10)
        except Exception as e:
            logger.warning(f"Failed to send Slack webhook: {e}")

def detect_sar_changes(bands_t0: dict, bands_t1: dict, threshold: float) -> List[Dict]:
    """
    Detect changes using Sentinel-1 SAR coherence and backscatter difference.
    Returns list of detected waste site features.
    """
    import numpy as np
    import cv2
    from anomaly_engine import AnomalyEngine
    from shapely.geometry import Polygon, mapping
    from pyproj import Transformer
    
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