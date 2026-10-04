import torch
import torch.nn as nn
import torchvision.models as models
from torchvision.models import MobileNet_V3_Small_Weights
import timm


class WasteDetectionModel(nn.Module):
    """
    Fine-tuned MobileNetV3 for satellite waste detection.
    
    Input: 6-channel tensor (B04, B08, B11, NDVI, ΔNDVI, SWIR-enhanced)
    Output: Probability map (1 channel) + confidence map (1 channel)
    """
    
    def __init__(
        self,
        in_channels: int = 6,
        num_classes: int = 2,
        pretrained: bool = True,
        freeze_backbone: bool = False,
        dropout: float = 0.3
    ):
        super().__init__()
        
        # Use MobileNetV3-Small as backbone (lightweight, fast)
        self.backbone = models.mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None)
        
        # Modify first layer for 6-channel input
        first_conv = self.backbone.features[0][0]
        self.backbone.features[0][0] = nn.Conv2d(
            in_channels,
            first_conv.out_channels,
            kernel_size=first_conv.kernel_size,
            stride=first_conv.stride,
            padding=first_conv.padding,
            bias=False
        )
        
        # Initialize new conv layer with pretrained weights (average across RGB)
        if pretrained:
            with torch.no_grad():
                # Average RGB weights for new channels
                avg_weights = first_conv.weight.mean(dim=1, keepdim=True).repeat(1, in_channels, 1, 1)
                self.backbone.features[0][0].weight.copy_(avg_weights)
        
        # Freeze backbone if specified
        if freeze_backbone:
            for param in self.backbone.parameters():
                param.requires_grad = False
        
        # Get feature dimension
        self.feature_dim = self.backbone.classifier[-1].in_features
        self.backbone.classifier = nn.Identity()
        
        # Detection head - outputs probability + confidence
        self.detection_head = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(self.feature_dim, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes)  # [waste_prob, confidence]
        )
        
        # Segmentation head - outputs probability map
        self.seg_head = nn.Sequential(
            nn.Conv2d(self.feature_dim, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.Conv2d(128, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 1, 1),  # Single channel probability map
            nn.Sigmoid()
        )
        
    def forward(self, x):
        # Backbone features
        features = self.backbone.features(x)
        
        # Global detection
        global_feat = features.mean(dim=[2, 3])  # Global average pooling
        detection_out = self.detection_head(global_feat)
        
        # Segmentation map
        seg_map = self.seg_head(features)
        seg_map = nn.functional.interpolate(
            seg_map, size=x.shape[2:], mode='bilinear', align_corners=False
        )
        
        return {
            'detection': detection_out,  # [batch, 2] - waste_prob, confidence
            'segmentation': seg_map,      # [batch, 1, H, W] - probability map
            'features': features
        }


class MultiScaleWasteDetector(nn.Module):
    """
    Multi-scale detector using feature pyramid for better small object detection.
    """
    
    def __init__(self, in_channels: int = 6, num_classes: int = 2):
        super().__init__()
        
        # EfficientNet-B0 as backbone (better feature extraction)
        self.backbone = timm.create_model('efficientnet_b0', pretrained=True, features_only=True)
        
        # Modify stem for 6-channel input
        old_conv = self.backbone.conv_stem
        self.backbone.conv_stem = nn.Conv2d(
            in_channels, old_conv.out_channels,
            kernel_size=old_conv.kernel_size,
            stride=old_conv.stride,
            padding=old_conv.padding,
            bias=False
        )
        
        # Feature pyramid channels
        fpn_channels = [24, 40, 112, 320]  # EfficientNet-B0 feature channels
        
        # Lateral connections
        self.lateral_convs = nn.ModuleList([
            nn.Conv2d(c, 128, 1) for c in fpn_channels
        ])
        
        # FPN output convs
        self.fpn_convs = nn.ModuleList([
            nn.Conv2d(128, 128, 3, padding=1) for _ in fpn_channels
        ])
        
        # Detection heads at each scale
        self.scale_heads = nn.ModuleList([
            nn.Sequential(
                nn.Conv2d(128, 64, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(64, num_classes, 1)
            ) for _ in fpn_channels
        ])
        
    def forward(self, x):
        # Extract multi-scale features
        features = self.backbone(x)
        
        # Build feature pyramid (top-down)
        pyramid = []
        for i, feat in enumerate(features):
            lateral = self.lateral_convs[i](feat)
            if i > 0:
                lateral = lateral + nn.functional.interpolate(
                    pyramid[-1], size=feat.shape[2:], mode='nearest'
                )
            pyramid.append(self.fpn_convs[i](lateral))
        
        # Predictions at each scale
        outputs = []
        for i, p in enumerate(pyramid):
            out = self.scale_heads[i](p)
            outputs.append(nn.functional.interpolate(
                out, size=x.shape[2:], mode='bilinear', align_corners=False
            ))
        
        # Fuse predictions (average)
        fused = torch.stack(outputs).mean(dim=0)
        
        return {
            'detection': fused[:, 0:1],  # Waste probability
            'confidence': fused[:, 1:2],  # Confidence
            'multi_scale': outputs
        }


def create_model(model_type: str = 'mobilenet', **kwargs):
    """Factory function to create model."""
    if model_type == 'mobilenet':
        return WasteDetectionModel(**kwargs)
    elif model_type == 'multiscale':
        return MultiScaleWasteDetector(**kwargs)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


if __name__ == "__main__":
    # Test model creation
    model = create_model('mobilenet', in_channels=6)
    x = torch.randn(2, 6, 256, 256)
    out = model(x)
    print(f"Detection shape: {out['detection'].shape}")
    print(f"Segmentation shape: {out['segmentation'].shape}")
    
    model_ms = create_model('multiscale', in_channels=6)
    out_ms = model_ms(x)
    print(f"Multi-scale detection: {out_ms['detection'].shape}")