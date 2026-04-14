#!/usr/bin/env python3
"""
Setup script for AI Study Tutor
"""

import subprocess
import sys
from pathlib import Path


def install_requirements():
    """Install required packages from requirements.txt"""
    print("Installing dependencies...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✅ Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing dependencies: {e}")
        return False


def create_directories():
    """Create necessary directories"""
    print("Creating directories...")
    directories = ["pdfs", "logs"]
    
    for directory in directories:
        dir_path = Path(directory)
        dir_path.mkdir(exist_ok=True)
        print(f"✅ Created {directory}/ directory")


def main():
    """Main setup function"""
    print("AI Study Tutor Setup")
    print("=" * 40)
    
    # Install dependencies
    if not install_requirements():
        print("\n❌ Setup failed. Please install dependencies manually:")
        print("   pip install -r requirements.txt")
        return
    
    # Create directories
    create_directories()
    
    print("\n✅ Setup complete!")
    print("\nNext steps:")
    print("1. Place your PDF textbooks in the 'pdfs/' directory")
    print("2. Run: python main.py pdfs/your_textbook.pdf")
    print("3. Or run: python main.py path/to/any/pdf")


if __name__ == "__main__":
    main()
