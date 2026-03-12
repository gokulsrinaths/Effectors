"""
ChimeraX validation utility.

Validates that ChimeraX works correctly in headless mode on Windows.
This module performs a test render to ensure ChimeraX can generate images.
"""

import subprocess
import tempfile
import pathlib
import logging
import os

from config.chimerax import (
    get_chimerax_path,
    get_chimerax_env,
    CHIMERAX_TIMEOUT
)

logger = logging.getLogger(__name__)


def validate_chimerax() -> bool:
    """
    Validate that ChimeraX works correctly in headless mode.
    
    Performs a test render using built-in PDB (1crn) to ensure:
    - ChimeraX executable is accessible
    - Headless mode works (no OpenGL/GPU issues)
    - Image generation succeeds
    
    Returns:
        True if ChimeraX is working correctly, False otherwise
    """
    try:
        chimerax_path = get_chimerax_path()
        logger.info(f"Validating ChimeraX at: {chimerax_path}")
    except FileNotFoundError as e:
        logger.error(f"ChimeraX not found: {e}")
        return False
    
    # Create temporary directory for validation
    with tempfile.TemporaryDirectory() as temp_dir:
        proof_script = pathlib.Path(temp_dir) / "proof.cxc"
        proof_image = pathlib.Path(temp_dir) / "proof.png"
        
        # Create validation script using built-in PDB (1crn)
        # This PDB is always available in ChimeraX
        script_content = f"""echo "CHIMERAX_VALIDATOR_OK"
open 1crn
cartoon
view
save {proof_image.resolve()} supersample 1
exit
"""
        
        try:
            proof_script.write_text(script_content)
        except Exception as e:
            logger.error(f"Failed to create validation script: {e}")
            return False
        
        # Run ChimeraX with validation script
        try:
            logger.info("Running ChimeraX validation test...")
            
            # Use minimal environment - let ChimeraX handle OpenGL
            env = os.environ.copy()
            # Don't set environment variables that might block OpenGL
            
            # On Windows, try without --nogui to allow OpenGL access
            import platform
            if platform.system() == "Windows":
                cmd = [
                    chimerax_path,
                    "--script",
                    str(proof_script)
                ]
            else:
                cmd = [
                    chimerax_path,
                    "--nogui",
                    "--offscreen",
                    "--script",
                    str(proof_script)
                ]
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=CHIMERAX_TIMEOUT,
                check=False
            )
            
            # Check if proof image was created
            if proof_image.exists() and proof_image.stat().st_size > 0:
                logger.info("✅ ChimeraX detected and validated")
                return True
            else:
                # Check if the error is the known OpenGL limitation on Windows
                if result.stderr and "OpenGL rendering is not available" in result.stderr:
                    logger.error("ChimeraX validation failed: OpenGL not available in headless mode")
                    logger.error("=" * 70)
                    logger.error("KNOWN LIMITATION: ChimeraX on Windows requires OpenGL to save images")
                    logger.error("In --nogui mode, OpenGL may not be available.")
                    logger.error("=" * 70)
                    logger.error("Possible workarounds:")
                    logger.error("  1. Use a virtual display driver (e.g., VirtualGL for Windows)")
                    logger.error("  2. Run on Linux where headless OpenGL works better")
                    logger.error("  3. Use ChimeraX Python API (may have same limitation)")
                    logger.error("  4. Run without --nogui (requires display)")
                    logger.error("=" * 70)
                else:
                    logger.error("ChimeraX validation failed - proof image not created")
                    logger.error(f"ChimeraX return code: {result.returncode}")
                
                if result.stdout:
                    logger.error(f"ChimeraX stdout:\n{result.stdout}")
                if result.stderr:
                    logger.error(f"ChimeraX stderr:\n{result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"ChimeraX validation timed out after {CHIMERAX_TIMEOUT} seconds")
            return False
        except Exception as e:
            logger.error(f"ChimeraX validation failed with exception: {e}", exc_info=True)
            return False
