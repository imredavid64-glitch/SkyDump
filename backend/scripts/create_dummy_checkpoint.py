#!/usr/bin/env python
"""
Create a dummy model checkpoint for demo purposes.
This exports an untrained MobileNetV3 model to .ckpt format.
"""
import torch
import sys
sys.path.insert(0, '.')

from ml.model import create_model

def create_dummy_checkpoint():
    """Create a dummy checkpoint for demo mode."""
    model = create_model('mobilenet', in_channels=6)
    
    checkpoint = {
        'state_dict': model.state_dict(),
        'hyper_parameters': {
            'in_channels': 6,
            'model_type': 'mobilenet',
            'num_classes': 2,
            'pretrained': True,
            'freeze_backbone': False,
            'dropout': 0.3
        },
        'epoch': 0,
        'global_step': 0,
        'pytorch-lightning_version': '2.3.0'
    }
    
    ckpt_path = 'ml/checkpoints/best_model.ckpt'
    torch.save(checkpoint, ckpt_path)
    print(f"Dummy checkpoint saved to {ckpt_path}")
    print("Note: This is an UNTRAINED model for demo purposes only!")
    print("For real inference, train the model using train.py")
    print("ONNX export skipped (requires model fixes) - using .ckpt for demo")

if __name__ == '__main__':
    create_dummy_checkpoint()