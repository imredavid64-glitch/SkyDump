import os
import json
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import pytorch_lightning as pl
from pytorch_lightning.callbacks import ModelCheckpoint, EarlyStopping, LearningRateMonitor
from pytorch_lightning.loggers import TensorBoardLogger, WandbLogger
import albumentations as A
from albumentations.pytorch import ToTensorV2
import numpy as np
import rasterio
from rasterio.windows import Window
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import cv2


class WasteDataset(Dataset):
    """
    Dataset for satellite waste detection training.
    
    Expects directory structure:
    data/
    ├── images/
    │   ├── tile_001.npy (6 channels: B04, B08, B11, NDVI, dNDVI, SWIR_enhanced)
    │   ├── tile_002.npy
    │   └── ...
    └── masks/
        ├── tile_001.png (binary mask: 1=waste, 0=background)
        ├── tile_002.png
        └── ...
    """
    
    def __init__(
        self,
        image_dir: str,
        mask_dir: str,
        tile_size: int = 256,
        stride: int = 128,
        transform=None,
        augment: bool = True
    ):
        self.image_dir = Path(image_dir)
        self.mask_dir = Path(mask_dir)
        self.tile_size = tile_size
        self.stride = stride
        self.transform = transform
        self.augment = augment
        
        # Find all image files
        self.image_files = sorted(list(self.image_dir.glob("*.npy")))
        self.mask_files = {f.stem: f for f in self.mask_dir.glob("*.png")}
        
        # Generate tile coordinates for each image
        self.tiles = []
        for img_file in self.image_files:
            stem = img_file.stem
            if stem not in self.mask_files:
                continue
                
            # Load image to get dimensions
            img = np.load(img_file)
            h, w = img.shape[1], img.shape[2]
            
            # Generate tile coordinates
            for y in range(0, h - tile_size + 1, stride):
                for x in range(0, w - tile_size + 1, stride):
                    self.tiles.append((img_file, x, y, tile_size, tile_size))
        
        # Augmentation pipeline
        if augment:
            self.aug_pipeline = A.Compose([
                A.HorizontalFlip(p=0.5),
                A.VerticalFlip(p=0.5),
                A.RandomRotate90(p=0.5),
                A.RandomBrightnessContrast(p=0.3),
                A.GaussNoise(p=0.2),
                A.ElasticTransform(p=0.2, alpha=1, sigma=5),
                A.GridDistortion(p=0.2),
            ])
        else:
            self.aug_pipeline = None
    
    def __len__(self):
        return len(self.tiles)
    
    def __getitem__(self, idx):
        img_file, x, y, w, h = self.tiles[idx]
        stem = img_file.stem
        
        # Load image tile
        img = np.load(img_file)
        tile = img[:, y:y+h, x:x+w]  # [C, H, W]
        
        # Load mask tile
        mask = cv2.imread(str(self.mask_files[stem]), cv2.IMREAD_GRAYSCALE)
        mask_tile = mask[y:y+h, x:x+w]
        mask_tile = (mask_tile > 127).astype(np.float32)
        
        # Apply augmentations
        if self.aug_pipeline:
            augmented = self.aug_pipeline(image=tile.transpose(1, 2, 0), mask=mask_tile)
            tile = augmented['image'].transpose(2, 0, 1)
            mask_tile = augmented['mask']
        
        # Normalize image (per-channel statistics from Sentinel-2)
        # Mean/std for [B04, B08, B11, NDVI, dNDVI, SWIR_enhanced]
        mean = np.array([0.15, 0.25, 0.12, 0.0, 0.0, 0.15])
        std = np.array([0.1, 0.15, 0.08, 0.3, 0.2, 0.1])
        tile = (tile - mean[:, None, None]) / (std[:, None, None] + 1e-6)
        
        return {
            'image': torch.from_numpy(tile).float(),
            'mask': torch.from_numpy(mask_tile).float().unsqueeze(0),
            'coords': (x, y),
            'stem': stem
        }


class WasteDataModule(pl.LightningDataModule):
    """Lightning DataModule for waste detection."""
    
    def __init__(
        self,
        train_image_dir: str,
        train_mask_dir: str,
        val_image_dir: str,
        val_mask_dir: str,
        batch_size: int = 16,
        num_workers: int = 4,
        tile_size: int = 256,
        stride: int = 128
    ):
        super().__init__()
        self.train_image_dir = train_image_dir
        self.train_mask_dir = train_mask_dir
        self.val_image_dir = val_image_dir
        self.val_mask_dir = val_mask_dir
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.tile_size = tile_size
        self.stride = stride
    
    def setup(self, stage=None):
        self.train_dataset = WasteDataset(
            self.train_image_dir, self.train_mask_dir,
            tile_size=self.tile_size, stride=self.stride,
            augment=True
        )
        self.val_dataset = WasteDataset(
            self.val_image_dir, self.val_mask_dir,
            tile_size=self.tile_size, stride=self.stride,
            augment=False
        )
    
    def train_dataloader(self):
        return DataLoader(
            self.train_dataset,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=True,
            persistent_workers=True
        )
    
    def val_dataloader(self):
        return DataLoader(
            self.val_dataset,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=True,
            persistent_workers=True
        )


class DiceLoss(nn.Module):
    """Dice loss for segmentation."""
    
    def __init__(self, smooth=1e-6):
        super().__init__()
        self.smooth = smooth
    
    def forward(self, pred, target):
        pred = pred.view(-1)
        target = target.view(-1)
        intersection = (pred * target).sum()
        dice = (2. * intersection + self.smooth) / (pred.sum() + target.sum() + self.smooth)
        return 1 - dice


class FocalLoss(nn.Module):
    """Focal loss for handling class imbalance."""
    
    def __init__(self, alpha=0.25, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
    
    def forward(self, pred, target):
        bce = F.binary_cross_entropy_with_logits(pred, target, reduction='none')
        pt = torch.exp(-bce)
        focal = self.alpha * (1 - pt) ** self.gamma * bce
        return focal.mean()


class CombinedLoss(nn.Module):
    """Combined Dice + Focal + BCE loss."""
    
    def __init__(self, dice_weight=1.0, focal_weight=1.0, bce_weight=0.5):
        super().__init__()
        self.dice = DiceLoss()
        self.focal = FocalLoss()
        self.bce = nn.BCEWithLogitsLoss()
        self.dice_weight = dice_weight
        self.focal_weight = focal_weight
        self.bce_weight = bce_weight
    
    def forward(self, pred, target):
        # Apply sigmoid for dice loss
        pred_sigmoid = torch.sigmoid(pred)
        loss = (
            self.dice_weight * self.dice(pred_sigmoid, target) +
            self.focal_weight * self.focal(pred, target) +
            self.bce_weight * self.bce(pred, target)
        )
        return loss


class WasteDetectionLightning(pl.LightningModule):
    """Lightning module for waste detection training."""
    
    def __init__(
        self,
        model,
        learning_rate: float = 1e-4,
        weight_decay: float = 1e-4,
        loss_weights: dict = None
    ):
        super().__init__()
        self.model = model
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.loss_weights = loss_weights or {'dice': 1.0, 'focal': 1.0, 'bce': 0.5}
        
        # Loss functions
        self.seg_loss = CombinedLoss(
            dice_weight=self.loss_weights['dice'],
            focal_weight=self.loss_weights['focal'],
            bce_weight=self.loss_weights['bce']
        )
        self.det_loss = nn.BCEWithLogitsLoss()
        
        # Metrics
        self.train_iou = []
        self.val_iou = []
    
    def forward(self, x):
        return self.model(x)
    
    def training_step(self, batch, batch_idx):
        images = batch['image']
        masks = batch['mask']
        
        outputs = self.model(images)
        
        # Segmentation loss
        seg_loss = self.seg_loss(outputs['segmentation'], masks)
        
        # Detection loss (binary classification: any waste in tile)
        has_waste = (masks.sum(dim=[1, 2, 3]) > 0).float()
        det_loss = self.det_loss(outputs['detection'][:, 0], has_waste)
        
        # Combined loss
        total_loss = seg_loss + 0.5 * det_loss
        
        # Log metrics
        self.log('train/seg_loss', seg_loss, prog_bar=True)
        self.log('train/det_loss', det_loss, prog_bar=True)
        self.log('train/total_loss', total_loss, prog_bar=True)
        
        return total_loss
    
    def validation_step(self, batch, batch_idx):
        images = batch['image']
        masks = batch['mask']
        
        outputs = self.model(images)
        
        seg_loss = self.seg_loss(outputs['segmentation'], masks)
        has_waste = (masks.sum(dim=[1, 2, 3]) > 0).float()
        det_loss = self.det_loss(outputs['detection'][:, 0], has_waste)
        total_loss = seg_loss + 0.5 * det_loss
        
        # IoU metric
        pred_mask = (torch.sigmoid(outputs['segmentation']) > 0.5).float()
        intersection = (pred_mask * masks).sum(dim=[1, 2, 3])
        union = pred_mask.sum(dim=[1, 2, 3]) + masks.sum(dim=[1, 2, 3]) - intersection
        iou = (intersection / (union + 1e-6)).mean()
        
        self.log('val/seg_loss', seg_loss, prog_bar=True)
        self.log('val/det_loss', det_loss, prog_bar=True)
        self.log('val/total_loss', total_loss, prog_bar=True)
        self.log('val/iou', iou, prog_bar=True)
        
        return {'val_loss': total_loss, 'val_iou': iou}
    
    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay
        )
        
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=10, T_mult=2, eta_min=1e-6
        )
        
        return {
            'optimizer': optimizer,
            'lr_scheduler': {
                'scheduler': scheduler,
                'monitor': 'val/total_loss'
            }
        }


def train_model(
    model,
    data_module,
    max_epochs: int = 50,
    checkpoint_dir: str = "checkpoints",
    experiment_name: str = "waste_detection",
    use_wandb: bool = False
):
    """Train the waste detection model."""
    
    # Callbacks
    callbacks = [
        ModelCheckpoint(
            dirpath=checkpoint_dir,
            filename=f'{experiment_name}-{{epoch:02d}}-{{val/iou:.4f}}',
            monitor='val/iou',
            mode='max',
            save_top_k=3,
            save_last=True
        ),
        EarlyStopping(monitor='val/iou', mode='max', patience=15),
        LearningRateMonitor(logging_interval='epoch')
    ]
    
    # Logger
    if use_wandb:
        logger = WandbLogger(project="skydump", name=experiment_name)
    else:
        logger = TensorBoardLogger("logs", name=experiment_name)
    
    # Trainer
    trainer = pl.Trainer(
        max_epochs=max_epochs,
        accelerator='auto',
        devices='auto',
        precision='16-mixed',
        callbacks=callbacks,
        logger=logger,
        gradient_clip_val=1.0,
        accumulate_grad_batches=2,
        log_every_n_steps=10
    )
    
    trainer.fit(model, data_module)
    return trainer


def export_onnx(model, checkpoint_path, output_path, input_shape=(1, 6, 256, 256)):
    """Export model to ONNX for deployment."""
    model.load_state_dict(torch.load(checkpoint_path)['state_dict'])
    model.eval()
    
    dummy_input = torch.randn(input_shape)
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['detection', 'segmentation'],
        dynamic_axes={
            'input': {0: 'batch'},
            'detection': {0: 'batch'},
            'segmentation': {0: 'batch'}
        }
    )
    print(f"Model exported to {output_path}")


if __name__ == "__main__":
    # Example usage
    from model import create_model
    
    model = create_model('mobilenet', in_channels=6)
    lightning_model = WasteDetectionLightning(model)
    
    # Print model summary
    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")