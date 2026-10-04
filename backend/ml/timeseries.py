import os
import json
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.transform import from_bounds
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import cv2
from datetime import datetime, timedelta
import geopandas as gpd
from shapely.geometry import Polygon, mapping, box
from shapely.ops import transform as shapely_transform
from pyproj import Transformer
import xarray as xr
import dask.array as da


class TimeSeriesAnalyzer:
    """
    Time-series analysis for Sentinel-2 revisits.
    Detects onset, progression, and seasonal patterns of waste dumping.
    """
    
    def __init__(
        self,
        min_revisits: int = 3,
        max_cloud_cover: float = 0.3,
        change_threshold: float = 0.15
    ):
        self.min_revisits = min_revisits
        self.max_cloud_cover = max_cloud_cover
        self.change_threshold = change_threshold
    
    def load_sentinel2_stack(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        bands: List[str] = ['B04', 'B08', 'B11']
    ) -> xr.Dataset:
        """
        Load Sentinel-2 time series as xarray Dataset.
        
        Returns:
            xr.Dataset with dimensions (time, band, y, x)
        """
        from stac_pipeline import STACPipeline
        
        pipeline = STACPipeline()
        items = pipeline.search_scenes(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=int(self.max_cloud_cover * 100),
            limit=50
        )
        
        if len(items) < self.min_revisits:
            raise ValueError(f"Insufficient scenes: {len(items)} < {self.min_revisits}")
        
        # Sort by date
        items = sorted(items, key=lambda x: x.datetime or datetime.min)
        
        # Load first item to get reference grid
        ref_item = items[0]
        ref_bands = pipeline.fetch_all_bands(ref_item)
        ref_red, transform, crs = ref_bands['B04']
        h, w = ref_red.shape
        
        # Initialize arrays
        n_time = len(items)
        n_bands = len(bands)
        data = np.full((n_time, n_bands, h, w), np.nan, dtype=np.float32)
        dates = []
        cloud_covers = []
        
        for t, item in enumerate(items):
            try:
                bands_data = pipeline.fetch_all_bands(item)
                for b, band_name in enumerate(bands):
                    band_data, _, _ = bands_data[band_name]
                    # Resample to reference resolution if needed
                    if band_data.shape != (h, w):
                        band_data = cv2.resize(band_data, (w, h), interpolation=cv2.INTER_LINEAR)
                    data[t, b] = band_data
                dates.append(item.datetime)
                cloud_covers.append(item.properties.get('eo:cloud_cover', 0))
            except Exception as e:
                print(f"Failed to load {item.id}: {e}")
                continue
        
        # Create xarray Dataset
        ds = xr.Dataset(
            {
                band: (['time', 'y', 'x'], data[:, i])
                for i, band in enumerate(bands)
            },
            coords={
                'time': dates,
                'y': np.arange(h),
                'x': np.arange(w),
                'cloud_cover': ('time', cloud_covers)
            },
            attrs={
                'transform': transform,
                'crs': str(crs),
                'bbox': bbox
            }
        )
        
        return ds
    
    def compute_indices(self, ds: xr.Dataset) -> xr.Dataset:
        """Compute spectral indices for each time step."""
        # NDVI
        ndvi = (ds['B08'] - ds['B04']) / (ds['B08'] + ds['B04'] + 1e-10)
        ndvi = ndvi.clip(-1, 1)
        ds['NDVI'] = ndvi
        
        # SWIR enhanced
        swir_enhanced = (ds['B11'] / (ds['B11'].max() + 1e-10)).clip(0, 1)
        ds['SWIR_ENHANCED'] = swir_enhanced
        
        # NBR (Normalized Burn Ratio) - good for detecting burnt/disturbed areas
        nbr = (ds['B08'] - ds['B11']) / (ds['B08'] + ds['B11'] + 1e-10)
        ds['NBR'] = nbr
        
        return ds
    
    def detect_changes(self, ds: xr.Dataset) -> Dict:
        """
        Detect changes in time series.
        
        Returns:
            Dict with change maps, onset dates, progression rates
        """
        # Compute NDVI differences between consecutive time steps
        ndvi = ds['NDVI']
        n_time = len(ds.time)
        
        # Temporal differences
        ndvi_diff = ndvi.diff('time')
        ndvi_diff.name = 'NDVI_DIFF'
        
        # Significant negative changes (vegetation loss)
        significant_loss = ndvi_diff < -self.change_threshold
        
        # SWIR increase (synthetic material appearance)
        swir_diff = ds['SWIR_ENHANCED'].diff('time')
        swir_increase = swir_diff > self.change_threshold
        
        # Combined anomaly: vegetation loss AND synthetic material
        anomaly = significant_loss & swir_increase
        
        # Onset detection: first time anomaly appears
        onset = anomaly.argmax('time')  # Index of first True
        onset = onset.where(anomaly.any('time'), -1)  # -1 if never
        
        # Progression rate: how fast anomaly grows
        anomaly_cumsum = anomaly.cumsum('time')
        progression = anomaly_cumsum.diff('time')
        
        # Persistence: how long anomaly lasts
        persistence = anomaly.sum('time')
        
        return {
            'ndvi_diff': ndvi_diff,
            'significant_loss': significant_loss,
            'swir_increase': swir_increase,
            'anomaly': anomaly,
            'onset': onset,
            'progression': progression,
            'persistence': persistence,
            'anomaly_cumsum': anomaly_cumsum
        }
    
    def extract_waste_sites(
        self,
        ds: xr.Dataset,
        changes: Dict,
        min_area_px: int = 50,
        min_persistence: int = 2
    ) -> List[Dict]:
        """
        Extract waste site polygons from time-series changes.
        
        Returns:
            List of waste site dictionaries with temporal metadata
        """
        anomaly = changes['anomaly']
        persistence = changes['persistence']
        onset = changes['onset']
        
        # Filter by persistence
        persistent_anomaly = anomaly.where(persistence >= min_persistence, False)
        
        # Get last time step mask
        final_mask = persistent_anomaly.isel(time=-1).values
        
        # Convert to polygons
        from anomaly_engine import AnomalyEngine
        engine = AnomalyEngine()
        
        # Get transform and CRS from dataset
        transform = ds.attrs.get('transform')
        crs = ds.attrs.get('crs')
        
        if transform and crs:
            features = engine.extract_polygons(
                (persistent_anomaly.isel(time=-1).values * 255).astype(np.uint8),
                transform, crs
            )
            
            # Add temporal metadata
            for feat in features:
                # Get onset date for this polygon centroid
                centroid = feat['geometry']['coordinates'][0][0]
                # Would need to map centroid to pixel coordinates
                # For now, add generic temporal info
                feat['properties']['temporal'] = {
                    'first_detected': str(ds.time.values[0]),
                    'last_detected': str(ds.time.values[-1]),
                    'persistence_days': int(persistence.max().values),
                    'progression_rate': float(changes['progression'].mean().values)
                }
            
            return features
        
        return []
    
    def compute_site_statistics(
        self,
        ds: xr.Dataset,
        changes: Dict,
        site_polygons: List[Dict]
    ) -> List[Dict]:
        """Compute detailed statistics for each detected site."""
        stats = []
        
        for site in site_polygons:
            # Would extract time series for each polygon
            # For now, return template
            site_stats = {
                'site_id': site['properties'].get('id', 'unknown'),
                'onset_date': site['properties'].get('temporal', {}).get('first_detected'),
                'total_area_m2': site['properties'].get('area_m2', 0),
                'growth_velocity_m2_per_day': 0.0,
                'peak_intensity': 0.0,
                'current_status': 'active',
                'confidence': site['properties'].get('confidence', 0.5)
            }
            stats.append(site_stats)
        
        return stats


class MultiSatelliteFusion:
    """
    Fuse Sentinel-2 (optical) + Sentinel-1 (SAR) + Landsat (historical).
    """
    
    def __init__(self):
        self.sentinel2_processor = TimeSeriesAnalyzer()
        # Sentinel-1 and Landsat processors would be added here
    
    def fuse_optical_sar(
        self,
        s2_ds: xr.Dataset,
        s1_ds: xr.Dataset
    ) -> xr.Dataset:
        """
        Fuse Sentinel-2 optical with Sentinel-1 SAR.
        SAR provides all-weather capability.
        """
        # Resample SAR to match optical grid
        # Combine features for detection
        # SAR VH/VV ratio for surface roughness
        # Coherence for change detection
        pass
    
    def create_composite(
        self,
        s2_ds: xr.Dataset,
        s1_ds: Optional[xr.Dataset] = None,
        landsat_ds: Optional[xr.Dataset] = None
    ) -> xr.Dataset:
        """
        Create multi-sensor composite for robust detection.
        """
        # This would be implemented with proper resampling and alignment
        pass


def create_training_labels_from_osm(
    bbox: List[float],
    output_path: str
) -> gpd.GeoDataFrame:
    """
    Create training labels from OpenStreetMap landuse=landfill data.
    """
    import requests
    from shapely.geometry import shape
    
    # Query OSM Overpass API for landfill sites
    overpass_query = f"""
    [out:json][timeout:25];
    (
      way["landuse"="landfill"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
      relation["landuse"="landfill"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
    );
    out body;
    >;
    out skel qt;
    """
    
    response = requests.post(
        'https://overpass-api.de/api/interpreter',
        data={'data': overpass_query}
    )
    
    if response.status_code != 200:
        raise Exception(f"OSM query failed: {response.status_code}")
    
    data = response.json()
    
    # Convert to GeoDataFrame
    features = []
    for element in data['elements']:
        if element['type'] == 'way':
            coords = [(data['elements'][i]['lon'], data['elements'][i]['lat']) 
                      for i in element['nodes'] if i in {e['id']: e for e in data['elements'] if e['type'] == 'node'}]
            if len(coords) >= 4:
                features.append({
                    'geometry': Polygon(coords),
                    'source': 'OSM',
                    'label': 1  # Waste site
                })
    
    gdf = gpd.GeoDataFrame(features, crs='EPSG:4326')
    gdf.to_file(output_path, driver='GeoJSON')
    
    return gdf


def generate_training_chips(
    bbox: List[float],
    start_date: str,
    end_date: str,
    labels_gdf: gpd.GeoDataFrame,
    output_dir: str,
    chip_size: int = 256,
    stride: int = 128
):
    """
    Generate training chips (image + mask) from Sentinel-2 and OSM labels.
    """
    from stac_pipeline import STACPipeline
    
    pipeline = STACPipeline()
    output_path = Path(output_dir)
    (output_path / 'images').mkdir(parents=True, exist_ok=True)
    (output_path / 'masks').mkdir(parents=True, exist_ok=True)
    
    # Load labels
    labels = labels_gdf.to_crs('EPSG:4326')
    
    # Get Sentinel-2 scenes
    items = pipeline.search_scenes(bbox, start_date, end_date, max_cloud_cover=20, limit=20)
    
    for item in items:
        try:
            bands = pipeline.fetch_all_bands(item)
            red, transform, crs = bands['B04']
            nir, _, _ = bands['B08']
            swir, _, _ = bands['B11']
            
            # Compute indices
            ndvi = (nir - red) / (nir + red + 1e-10)
            swir_enhanced = (swir / (swir.max() + 1e-10)).clip(0, 1)
            dndvi = np.zeros_like(ndvi)  # Single time
            
            # Stack
            image_stack = np.stack([red, nir, swir, ndvi, dndvi, swir_enhanced], axis=0)
            
            # Rasterize labels
            from rasterio.features import rasterize
            mask = rasterize(
                [(geom, 1) for geom in labels.geometry],
                out_shape=red.shape,
                transform=transform,
                fill=0,
                dtype=np.uint8
            )
            
            # Generate chips
            h, w = red.shape
            for y in range(0, h - chip_size + 1, stride):
                for x in range(0, w - chip_size + 1, stride):
                    chip_img = image_stack[:, y:y+chip_size, x:x+chip_size]
                    chip_mask = mask[y:y+chip_size, x:x+chip_size]
                    
                    # Only save chips with some positive labels
                    if chip_mask.sum() > 0 or np.random.random() < 0.1:  # 10% negative samples
                        chip_id = f"{item.id}_y{y}_x{x}"
                        np.save(output_path / 'images' / f'{chip_id}.npy', chip_img)
                        cv2.imwrite(str(output_path / 'masks' / f'{chip_id}.png'), chip_mask * 255)
        
        except Exception as e:
            print(f"Failed to process {item.id}: {e}")
            continue


if __name__ == "__main__":
    print("Time-series analysis module ready")
    print("Usage:")
    print("  analyzer = TimeSeriesAnalyzer()")
    print("  ds = analyzer.load_sentinel2_stack(bbox, '2024-01-01', '2024-12-31')")
    print("  ds = analyzer.compute_indices(ds)")
    print("  changes = analyzer.detect_changes(ds)")
    print("  sites = analyzer.extract_waste_sites(ds, changes)")