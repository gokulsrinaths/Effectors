"""
ChimeraX Python API integration.

Uses ChimeraX's embedded Python to render images, which may work better
than subprocess calls on Windows.
"""

import subprocess
import pathlib
import tempfile
import logging
import os

logger = logging.getLogger(__name__)

# Path to ChimeraX's embedded Python
CHIMERAX_PYTHON = r"C:\Program Files\ChimeraX 1.11\bin\python.exe"


def render_pdb_via_python_api(pdb_path: str, output_path: str) -> bool:
    """
    Render PDB using ChimeraX's embedded Python API.
    
    This approach uses ChimeraX's own Python interpreter which has
    access to all ChimeraX modules and may work better on Windows.
    """
    if not pathlib.Path(CHIMERAX_PYTHON).exists():
        logger.error(f"ChimeraX Python not found at: {CHIMERAX_PYTHON}")
        return False
    
    pdb_abs = str(pathlib.Path(pdb_path).resolve())
    output_abs = str(pathlib.Path(output_path).resolve())
    
    # Create Python script that uses ChimeraX API
    # Use raw strings and proper escaping for Windows paths
    pdb_escaped = pdb_abs.replace('\\', '\\\\')
    output_escaped = output_abs.replace('\\', '\\\\')
    
    python_script = f"""
import sys
sys.path.insert(0, r'C:\\\\Program Files\\\\ChimeraX 1.11\\\\bin\\\\Lib\\\\site-packages')

from chimerax.core.session import Session
from chimerax.core.commands import run
from chimerax.core.logger import PlainTextLog

# Create a headless session
log = PlainTextLog()
session = Session('headless', log)

try:
    # Open PDB - use raw string for Windows paths
    run(session, r'open {pdb_escaped}')
    
    # Set up visualization
    run(session, 'cartoon')
    run(session, 'color bychain')
    run(session, 'view')
    
    # Save image - use raw string for Windows paths
    run(session, r'save {output_escaped} supersample 3')
    
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as script_file:
        script_file.write(python_script)
        script_path = script_file.name
    
    try:
        result = subprocess.run(
            [CHIMERAX_PYTHON, script_path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )
        
        if "SUCCESS" in result.stdout and pathlib.Path(output_path).exists():
            return True
        else:
            logger.error(f"Python API failed: {result.stdout}")
            logger.error(f"Stderr: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Python API exception: {e}")
        return False
    finally:
        if os.path.exists(script_path):
            os.unlink(script_path)

