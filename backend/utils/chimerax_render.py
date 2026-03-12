"""
ChimeraX protein visualization renderer.

Renders PDB files to PNG images using ChimeraX in headless mode.
Uses software rendering to bypass OpenGL/GPU issues on Windows.
"""

import subprocess
import pathlib
import tempfile
import os
import logging
import hashlib

from config.chimerax import (
    get_chimerax_path,
    get_chimerax_env,
    CHIMERAX_TIMEOUT,
    IMAGE_SUPERSAMPLE
)

# Try to import Python API renderer as fallback
try:
    from utils.chimerax_python_api import render_pdb_via_python_api
    PYTHON_API_AVAILABLE = True
except ImportError:
    PYTHON_API_AVAILABLE = False
    def render_pdb_via_python_api(*args, **kwargs):
        return False

logger = logging.getLogger(__name__)


def render_pdb_to_image(pdb_path: str, output_path: str) -> bool:
    """
    Uses ChimeraX headlessly to render a PNG from a PDB.
    
    Args:
        pdb_path: Absolute path to the PDB file
        output_path: Absolute path where the PNG image should be saved
    
    Returns:
        True on success, False on failure
    
    Raises:
        FileNotFoundError: If PDB file doesn't exist
        RuntimeError: If ChimeraX execution fails
    """
    # Validate input file
    pdb_path_obj = pathlib.Path(pdb_path)
    if not pdb_path_obj.exists():
        raise FileNotFoundError(f"PDB file not found: {pdb_path}")
    
    if not pdb_path_obj.suffix.lower() == '.pdb':
        logger.warning(f"File does not have .pdb extension: {pdb_path}")
    
    # Ensure output directory exists
    output_path_obj = pathlib.Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # Try Python API first (may work better on Windows)
    if PYTHON_API_AVAILABLE:
        logger.info(f"Attempting to render via ChimeraX Python API: {pdb_path} -> {output_path}")
        if render_pdb_via_python_api(pdb_path, output_path):
            logger.info(f"Successfully rendered via Python API: {output_path}")
            return True
        else:
            logger.warning("Python API failed, falling back to subprocess method")
    
    # Fallback to subprocess method
    try:
        chimerax_path = get_chimerax_path()
    except FileNotFoundError as e:
        logger.error(f"ChimeraX not available: {e}")
        return False
    
    # Create temporary ChimeraX script
    # Use absolute paths and ensure proper formatting
    pdb_abs = str(pdb_path_obj.resolve()).replace('\\', '/')
    output_abs = str(output_path_obj.resolve()).replace('\\', '/')
    
    script_content = f"""open {pdb_abs}
cartoon
color bychain
view
save {output_abs} supersample {IMAGE_SUPERSAMPLE}
exit
"""
    
    # Write script to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cxc', delete=False) as script_file:
        script_file.write(script_content)
        script_path = script_file.name
    
    try:
        logger.info(f"Rendering PDB with ChimeraX subprocess: {pdb_path} -> {output_path}")
        
        # Run ChimeraX
        # On Windows, --nogui breaks OpenGL, so run without it
        # The window will appear briefly but OpenGL will work
        import platform
        if platform.system() == "Windows":
            # On Windows, don't use --nogui to allow OpenGL access
            cmd = [
                chimerax_path,
                "--script",
                str(script_path)
            ]
        else:
            # On Linux, --nogui should work
            cmd = [
                chimerax_path,
                "--nogui",
                "--offscreen",
                "--script",
                str(script_path)
            ]
        
        # Use minimal environment - let ChimeraX handle OpenGL
        env = os.environ.copy()
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=CHIMERAX_TIMEOUT,
            check=False
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"ChimeraX failed (exit {result.returncode}): {error_msg[:500]}")
            if result.stdout:
                logger.error(f"ChimeraX stdout:\n{result.stdout}")
            if result.stderr:
                logger.error(f"ChimeraX stderr:\n{result.stderr}")
            return False
        
        # Verify image was created
        if not output_path_obj.exists():
            logger.error(f"ChimeraX script completed but image not found: {output_path}")
            logger.error(f"ChimeraX return code: {result.returncode}")
            if result.stdout:
                logger.error(f"ChimeraX stdout:\n{result.stdout}")
            if result.stderr:
                logger.error(f"ChimeraX stderr:\n{result.stderr}")
            return False
        
        # Verify image has content
        if output_path_obj.stat().st_size == 0:
            logger.error(f"ChimeraX created empty image file: {output_path}")
            return False
        
        logger.info(f"Successfully rendered visualization: {output_path}")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error(f"ChimeraX rendering timed out after {CHIMERAX_TIMEOUT} seconds")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during ChimeraX rendering: {e}", exc_info=True)
        return False
    finally:
        # Clean up temporary script
        if os.path.exists(script_path):
            try:
                os.unlink(script_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp script: {e}")


def render_protein(pdb_path: str, output_dir: str) -> dict:
    """
    Render a PDB file to PNG using ChimeraX in headless mode.
    Includes caching based on file hash.
    
    Args:
        pdb_path: Absolute path to the PDB file
        output_dir: Directory where output images will be saved
    
    Returns:
        Dictionary with:
        {
            "image": "/static/visualizations/<id>.png",
            "success": True/False,
            "error": "error message" (if failed),
            "cached": True/False
        }
    """
    # Validate input file
    pdb_path_obj = pathlib.Path(pdb_path)
    if not pdb_path_obj.exists():
        return {
            "image": None,
            "success": False,
            "error": f"PDB file not found: {pdb_path}"
        }
    
    # Create output directory if it doesn't exist
    output_dir_obj = pathlib.Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    
    # Generate unique ID based on file hash and name
    file_hash = hashlib.md5(pdb_path.encode()).hexdigest()[:8]
    file_stem = pdb_path_obj.stem
    image_id = f"{file_stem}_{file_hash}"
    image_filename = f"{image_id}.png"
    image_path = output_dir_obj / image_filename
    
    # Check if image already exists (caching)
    if image_path.exists() and image_path.stat().st_size > 0:
        logger.info(f"Using cached visualization: {image_path}")
        return {
            "image": f"/static/visualizations/{image_filename}",
            "success": True,
            "cached": True
        }
    
    # Render the image
    success = render_pdb_to_image(str(pdb_path_obj.resolve()), str(image_path.resolve()))
    
    if success:
        return {
            "image": f"/static/visualizations/{image_filename}",
            "success": True,
            "cached": False
        }
    else:
        return {
            "image": None,
            "success": False,
            "error": "Failed to render protein visualization"
        }
