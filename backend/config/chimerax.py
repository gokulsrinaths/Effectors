"""
ChimeraX configuration for headless rendering on Windows.

This module provides:
- Absolute path to ChimeraX executable
- Environment variables to force software rendering (bypass OpenGL/GPU issues)
- Configuration constants for ChimeraX operations
"""

import os
import pathlib

# Absolute path to ChimeraX executable
# Update this if ChimeraX is installed in a different location
# NOTE: Use lowercase 'chimerax.exe' (not 'ChimeraX.exe')
CHIMERAX_PATH = r"C:\Program Files\ChimeraX 1.11\bin\chimerax.exe"

# Environment variables for headless rendering on Windows
# NOTE: ChimeraX on Windows requires OpenGL to save images, but --nogui mode
# may not have OpenGL available. This is a known limitation.
# 
# Possible solutions:
# 1. Use ChimeraX Python API directly (complex)
# 2. Use a virtual display driver (e.g., VirtualGL, Xvfb for Windows)
# 3. Run without --nogui in a hidden window (may require display)
# 4. Use alternative rendering tool (PyMOL, VMD) with better headless support
#
# For now, we use minimal environment and let ChimeraX try to use Windows OpenGL
CHIMERAX_ENV = {
    # Minimal environment - no OpenGL-blocking variables
}

# Timeout for ChimeraX operations (seconds)
CHIMERAX_TIMEOUT = 30

# Image output settings
IMAGE_SUPERSAMPLE = 3  # Higher quality rendering
IMAGE_WIDTH = 1200
IMAGE_HEIGHT = 1200


def get_chimerax_path() -> str:
    """
    Get the absolute path to ChimeraX executable.
    
    Returns:
        Absolute path string to chimerax.exe
        
    Raises:
        FileNotFoundError: If ChimeraX is not found at the configured path
    """
    # Try lowercase first (as specified), then try actual case
    chimerax_path = pathlib.Path(CHIMERAX_PATH)
    if not chimerax_path.exists():
        # Try with actual case (ChimeraX.exe)
        alt_path = pathlib.Path(r"C:\Program Files\ChimeraX 1.11\bin\ChimeraX.exe")
        if alt_path.exists():
            chimerax_path = alt_path
        else:
            raise FileNotFoundError(
                f"ChimeraX not found at: {CHIMERAX_PATH}\n"
                f"Also tried: {alt_path}\n"
                f"Please verify ChimeraX is installed at this location."
            )
    return str(chimerax_path.resolve())


def get_chimerax_env() -> dict:
    """
    Get environment variables for ChimeraX headless execution.
    
    Returns:
        Dictionary of environment variables to pass to subprocess
    """
    # Start with current environment and update with ChimeraX-specific vars
    env = os.environ.copy()
    env.update(CHIMERAX_ENV)
    return env


def is_chimerax_available() -> bool:
    """
    Check if ChimeraX is available at the configured path.
    
    Returns:
        True if ChimeraX executable exists, False otherwise
    """
    try:
        chimerax_path = pathlib.Path(CHIMERAX_PATH)
        return chimerax_path.exists()
    except Exception:
        return False

