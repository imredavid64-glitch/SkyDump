import torch
import torch.nn.functional as F
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.transform import from_bounds
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import cv2
from model import create_model


class WasteDetectionInference:
    """Inference pipeline for waste detection on Sentinel-2 imagery."""
    
    def __init__(
        self,
        model_path: str,
        model_type: str = 'mobilenet',
        device: str = 'auto',
        tile_size: int = 256,
        stride: int = 128,
        threshold: float = 0.5
    ):
        self.tile_size = tile_size
        self.stride = stride
        self.threshold = threshold
        
        # Device
        if device == 'auto':
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        # Load model
        self.model = create_model(model_type, in_channels=6)
        checkpoint = torch.load(model_path, map_location=self.device)
        if 'state_dict' in checkpoint:
            self.model.load_state_dict(checkpoint['state_dict'])
        else:
            self.model.load_state_dict(checkpoint)
        self.model.to(self.device)
        self.model.eval()
        
        # Normalization stats (must match training)
        self.mean = np.array([0.15, 0.25, 0.12, 0.0, 0.0, 0.15], dtype=np.float32)
        self.std = np.array([0.1, 0.15, 0.08, 0.3, 0.2, 0.1], dtype=np.float32)
    
    def preprocess_tile(self, tile: np.ndarray) -> torch.Tensor:
        """Normalize and convert tile to tensor."""
        # tile shape: [C, H, W]
        normalized = (tile - self.mean[:, None, None]) / (self.std[:, None, None] + 1e-6)
        return torch.from_numpy(normalized).float().unsqueeze(0).to(self.device)
    
    def predict_tile(self, tile: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Run inference on a single tile."""
        with torch.no_grad():
            input_tensor = self.preprocess_tile(tile)
            outputs = self.model(input_tensor)
            
            # Get probability map
            prob_map = torch.sigmoid(outputs['segmentation']).squeeze().cpu().numpy()
            confidence = torch.sigmoid(outputs['detection'][:, 1]).item()
            
            return prob_map, confidence
    
    def sliding_window_predict(self, image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Run sliding window inference on large image.
        
        Args:
            image: [C, H, W] array
        Returns:
            prob_map: [H, W] probability map
            confidence_map: [H, W] confidence map
        """
        C, H, W = image.shape
        prob_map = np.zeros((H, W), dtype=np.float32)
        confidence_map = np.zeros((H, W), dtype=np.float32)
        count_map = np.zeros((H, W), dtype=np.float32)
        
        # Generate tile coordinates
        y_coords = list(range(0, H - self.tile_size + 1, self.stride))
        x_coords = list(range(0, W - self.tile_size + 1, self.stride))
        
        # Add final tiles to cover edges
        if y_coords[-1] + self.tile_size < H:
            y_coords.append(H - self.tile_size)
        if x_coords[-1] + self.tile_size < W:
            x_coords.append(W - self.tile_size)
        
        for y in y_coords:
            for x in x_coords:
                tile = image[:, y:y+self.tile_size, x:x+self.tile_size]
                prob, conf = self.predict_tile(tile)
                
                prob_map[y:y+self.tile_size, x:x+self.tile_size] += prob
                confidence_map[y:y+self.tile_size, x:x+self.tile_size] += conf
                count_map[y:y+self.tile_size, x:x+self.tile_size] += 1
        
        # Average overlapping predictions
        prob_map = np.divide(prob_map, count_map, out=np.zeros_like(prob_map), where=count_map > 0)
        confidence_map = np.divide(confidence_map, count_map, out=np.zeros_like(confidence_map), where=count_map > 0)
        
        return prob_map, confidence_map
    
    def detect_from_sentinel2(
        self,
        red_path: str,
        nir_path: str,
        swir_path: str,
        output_dir: str
    ) -> Dict:
        """
        Run detection on Sentinel-2 bands.
        
        Args:
            red_path: Path to B04 (Red) band
            nir_path: Path to B08 (NIR) band
            swir_path: Path to B11 (SWIR) band
            output_dir: Directory to save outputs
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Read bands
        with rasterio.open(red_path) as src:
            red = src.read(1).astype(np.float32)
            transform = src.transform
            crs = src.crs
            profile = src.profile
        
        with rasterio.open(nir_path) as src:
            nir = src.read(1).astype(np.float32)
        
        with rasterio.open(swir_path) as src:
            swir = src.read(1).astype(np.float32)
        
        # Resample SWIR to match Red/NIR resolution (10m)
        if swir.shape != red.shape:
            swir = cv2.resize(swir, (red.shape[1], red.shape[0]), interpolation=cv2.INTER_LINEAR)
        
        # Compute indices
        ndvi = (nir - red) / (nir + red + 1e-10)
        ndvi = np.clip(ndvi, -1, 1)
        
        # SWIR enhanced (highlight synthetic materials)
        swir_enhanced = np.clip(swir / (swir.max() + 1e-10), 0, 1)
        
        # Stack channels: [B04, B08, B11, NDVI, dNDVI_placeholder, SWIR_enhanced]
        # For single-time inference, dNDVI is zero
        dndvi = np.zeros_like(ndvi)
        
        image_stack = np.stack([red, nir, swir, ndvi, dndvi, swir_enhanced], axis=0)
        
        # Run sliding window inference
        prob_map, confidence_map = self.sliding_window_predict(image_stack)
        
        # Threshold to get binary mask
        binary_mask = (prob_map > self.threshold).astype(np.uint8)
        
        # Save probability map
        prob_profile = profile.copy()
        prob_profile.update(dtype=rasterio.float32, count=1, compress='lzw')
        with rasterio.open(output_path / 'probability_map.tif', 'w', **prob_profile) as dst:
            dst.write(prob_map.astype(np.float32), 1)
        
        # Save confidence map
        with rasterio.open(output_path / 'confidence_map.tif', 'w', **prob_profile) as dst:
            dst.write(confidence_map.astype(np.float32), 1)
        
        # Save binary mask
        mask_profile = profile.copy()
        mask_profile.update(dtype=rasterio.uint8, count=1, compress='lzw')
        with rasterio.open(output_path / 'binary_mask.tif', 'w', **mask_profile) as dst:
            dst.write(binary_mask, 1)
        
        # Extract polygons from mask
        polygons = self.mask_to_polygons(binary_mask, transform, crs)
        
        # Save GeoJSON
        import json
        geojson = {
            "type": "FeatureCollection",
            "features": polygons
        }
        with open(output_path / 'detections.geojson', 'w') as f:
            json.dump(geojson, f, indent=2)
        
        return {
            'probability_map': str(output_path / 'probability_map.tif'),
            'confidence_map': str(output_path / 'confidence_map.tif'),
            'binary_mask': str(output_path / 'binary_mask.tif'),
            'geojson': str(output_path / 'detections.geojson'),
            'num_detections': len(polygons),
            'stats': self.compute_stats(prob_map, binary_mask)
        }
    
    def mask_to_polygons(self, mask: np.ndarray, transform, crs) -> List[Dict]:
        """Convert binary mask to GeoJSON polygons."""
        from shapely.geometry import Polygon, mapping
        from shapely.ops import transform as shapely_transform
        from pyproj import Transformer
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        features = []
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 100:  # Minimum area filter
                continue
            
            # Simplify contour
            epsilon = 0.005 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            
            # Convert to geographic coordinates
            coords = []
            for point in approx:
                x, y = point[0]
                lon, lat = transform * (x, y)
                coords.append((lon, lat))
            
            if len(coords) < 3:
                continue
            
            coords.append(coords[0])  # Close polygon
            
            polygon = Polygon(coords)
            # Transform to WGS84
            polygon = shapely_transform(transformer.transform, polygon)
            
            feature = {
                "type": "Feature",
                "geometry": mapping(polygon),
                "properties": {
                    "area_m2": polygon.area * 111000 * 111000 * np.cos(np.radians(polygon.centroid.y)),  # Approximate
                    "confidence": float(confidence_map[
                        int(contour[:, 0, 1].mean()), 
                        int(contour[:, 0, 0].mean())
                    ]) if 'confidence_map' in locals() else 0.5
                }
            }
            features.append(feature)
        
        return features
    
    def compute_stats(self, prob_map: np.ndarray, binary_mask: np.ndarray) -> Dict:
        """Compute detection statistics."""
        return {
            'total_area_px': int(binary_mask.sum()),
            'max_probability': float(prob_map.max()),
            'mean_probability': float(prob_map[binary_mask > 0].mean()) if binary_mask.sum() > 0 else 0.0,
            'num_connected_components': int(cv2.connectedComponents(binary_mask)[0]) - 1
        }


class ONNXInference:
    """ONNX Runtime inference for faster deployment."""
    
    def __init__(self, onnx_path: str, device: str = 'cpu'):
        import onnxruntime as ort
        
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if device == 'cuda' else ['CPUExecutionProvider']
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
    
    def predict(self, tile: np.ndarray) -> Dict:
        """Run inference on preprocessed tile."""
        input_tensor = tile.astype(np.float32)
        outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        return dict(zip(self.output_names, outputs))


def create_training_data_from_sentinel2(
    sentinel2_dir: str,
    output_dir: str,
    tile_size: int = 256,
    stride: int = 128
):
    """
    Create training tiles from Sentinel-2 imagery.
    This is a helper to prepare data for training.
    """
    from stac_pipeline import STACPipeline
    import json
    
    output_path = Path(output_dir)
    (output_path / 'images').mkdir(parents=True, exist_ok=True)
    (output_path / 'masks').mkdir(parents=True, exist_ok=True)
    
    pipeline = STACPipeline()
    
    # This would be run offline to prepare training data
    # For now, it's a template
    print(f"Training data preparation template ready at {output_dir}")
    print("Run this offline with labeled data to create training tiles")


if __name__ == "__main__":
    # Test inference setup
    print("Inference module ready")
    print("Usage:")
    print("  inference = WasteDetectionInference('model.ckpt')")
    print("  results = inference.detect_from_sentinel2('B04.tif', 'B08.tif', 'B11.tif', 'output/')")