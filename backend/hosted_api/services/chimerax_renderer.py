"""Structure visualization: headless PyMOL rendering to PNG.

On Medicine Bow the conda env 'chimerax-env' has pymol-open-source installed.
Set EFFECTOR_CHIMERAX_BIN to the full path of that env's Python binary so it
is used for rendering (default falls back to the system python3).

If rendering fails for any reason (missing binary, no display, etc.) the
function returns False and the rest of the job is unaffected.
"""

from __future__ import annotations

import logging
import subprocess
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimal PyMOL script: load PDB, colour by chain, ray-trace, save PNG, quit.
_PYMOL_SCRIPT = textwrap.dedent("""\
    import sys
    from pathlib import Path

    pdb_path  = sys.argv[1]
    out_png   = sys.argv[2]

    import pymol
    pymol.finish_launching(['pymol', '-cq'])   # headless, quiet
    from pymol import cmd

    cmd.load(pdb_path, 'structure')
    cmd.spectrum('count', 'rainbow', 'structure')
    cmd.show('cartoon', 'structure')
    cmd.hide('lines', 'structure')
    cmd.set('ray_shadows', 0)
    cmd.set('antialias', 2)
    cmd.orient('structure')
    cmd.zoom('structure', buffer=5)
    cmd.png(out_png, width=800, height=600, ray=1, quiet=1)
    cmd.quit()
""")


def render_structure_png(pdb_path: Path, output_png: Path, chimerax_bin: str = "python3") -> bool:
    """Render a PDB file to PNG using headless PyMOL.

    `chimerax_bin` is re-purposed here to point to the Python interpreter that
    has pymol-open-source installed (e.g. the conda-env python).

    Returns True on success, False on any failure (graceful degradation).
    """
    if not pdb_path.exists():
        logger.warning("Render skipped: PDB not found at %s", pdb_path)
        return False

    output_png.parent.mkdir(parents=True, exist_ok=True)

    # Write the helper script to a temp file alongside the output
    script_path = output_png.parent / "_pymol_render.py"
    script_path.write_text(_PYMOL_SCRIPT, encoding="utf-8")

    try:
        result = subprocess.run(
            [chimerax_bin, str(script_path), str(pdb_path), str(output_png)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(
                "PyMOL render exited %d: %s",
                result.returncode,
                (result.stderr or result.stdout or "")[:500],
            )
            return False
        if not output_png.exists():
            logger.warning("PyMOL ran but produced no PNG at %s", output_png)
            return False
        logger.info("Rendered %s → %s", pdb_path.name, output_png)
        return True
    except FileNotFoundError:
        logger.info("Python binary not found (%s) — skipping structure rendering", chimerax_bin)
        return False
    except subprocess.TimeoutExpired:
        logger.warning("PyMOL render timed out for %s", pdb_path.name)
        return False
    except Exception as exc:
        logger.warning("Render failed: %s", exc)
        return False
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass
