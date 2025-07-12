#!/usr/bin/env python3
"""
Script to download the Phi-3-mini model from HuggingFace.
This script downloads the GGUF model file for use with ctransformers.
"""

import os
import sys
from pathlib import Path
from huggingface_hub import hf_hub_download

def download_model():
    """Download the Phi-3-mini model from HuggingFace"""
    
    # Create model directory if it doesn't exist
    model_dir = Path("model")
    model_dir.mkdir(exist_ok=True)
    
    print("Downloading Phi-3-mini model from HuggingFace...")
    print(f"Model will be saved to: {model_dir.absolute()}")
    
    try:
        # Download the model file
        model_path = hf_hub_download(
            repo_id="microsoft/Phi-3-mini-4k-instruct-GGUF",
            filename="phi-3-mini-4k-instruct.Q4_K_M.gguf",
            local_dir="model",
            local_dir_use_symlinks=False
        )
        
        print(f"✅ Model downloaded successfully!")
        print(f"📁 Model path: {model_path}")
        print(f"📊 Model size: {Path(model_path).stat().st_size / (1024*1024):.1f} MB")
        
        # Verify the file exists
        if Path(model_path).exists():
            print("✅ Model file verified!")
        else:
            print("❌ Model file not found!")
            return False
            
    except Exception as e:
        print(f"❌ Error downloading model: {e}")
        return False
    
    return True

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import huggingface_hub
        print("✅ huggingface_hub is installed")
        return True
    except ImportError:
        print("❌ huggingface_hub is not installed")
        print("Please install it with: pip install huggingface_hub")
        return False

def main():
    """Main function"""
    print("=== Phi-3-mini Model Downloader ===")
    
    # Check dependencies
    if not check_dependencies():
        return
    
    # Download model
    if download_model():
        print("\n🎉 Model download completed successfully!")
        print("\nNext steps:")
        print("1. The model is now available in the 'model' directory")
        print("2. You can use it in your Docker container")
        print("3. Update your Dockerfile to copy the model to the container")
    else:
        print("\n❌ Model download failed!")

if __name__ == "__main__":
    main() 