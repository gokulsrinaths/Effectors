# ChimeraX Usage In This Project

This project uses ChimeraX only for protein visualization. BLAST and TM-align do
not depend on it.

## What ChimeraX does here

- Takes a `.pdb` file
- Renders a PNG image
- Stores the image in `static/visualizations/`
- Returns the image URL to the frontend

The implementation lives in:

- `backend/utils/chimerax_render.py`
- `backend/utils/validate_chimerax.py`
- `backend/config/chimerax.py`

## Current configured path

The repository is currently configured for:

```text
C:\Program Files\ChimeraX 1.11\bin\chimerax.exe
```

That path is defined in `backend/config/chimerax.py`.

## Step 1: Install ChimeraX

1. Download ChimeraX for Windows from UCSF.
2. Install it.
3. If you install it somewhere else, update `backend/config/chimerax.py`.

## Step 2: Verify the executable exists

PowerShell:

```powershell
Test-Path "C:\Program Files\ChimeraX 1.11\bin\chimerax.exe"
```

Expected:

```text
True
```

If it fails:

- Check the actual install directory
- Update `backend/config/chimerax.py`

## Step 3: Validate ChimeraX with this repo

From the repo root:

```powershell
py -3 backend\utils\validate_chimerax.py
```

What it does:

- creates a temporary ChimeraX script
- opens a known test structure
- tries to save an image
- reports success or failure

If it fails:

- ChimeraX path is wrong
- OpenGL startup failed
- ChimeraX cannot write the output file

## Step 4: Run the backend and let startup detect it

From `backend/`:

```powershell
py -3 -m uvicorn main:app --reload
```

On startup the backend checks:

- BLAST
- makeblastdb
- WSL
- TM-align
- ChimeraX

If ChimeraX works, visualization is enabled. If not, the app still runs with
visualization disabled.

## Step 5: Use it from the product

### Option A: Structure upload path

1. Open the frontend
2. Choose `Upload Structure (PDB/CIF)`
3. Upload a `.pdb` file
4. The backend runs the structure pipeline
5. If ChimeraX is available and the upload is a `.pdb`, the backend renders an
   image for the uploaded structure

### Option B: Direct visualization endpoint

You can also call the visualization endpoint directly with a known local PDB path:

```http
POST /api/visualize/protein
Content-Type: application/json

{
  "pdb_path": "C:\\Users\\sgoku\\Downloads\\Effectors\\Database\\<file>.pdb"
}
```

Expected response shape:

```json
{
  "available": true,
  "image": "/static/visualizations/<file>.png",
  "success": true,
  "cached": false
}
```

## Step 6: Open the rendered image

If the backend returns:

```text
/static/visualizations/example.png
```

Then open:

```text
http://localhost:8000/static/visualizations/example.png
```

## Important behavior notes

- CIF uploads currently skip ChimeraX visualization in the main structure path.
- Cached image identity is based on the PDB path string, not file contents.
- On Windows, the renderer avoids `--nogui` because ChimeraX needs OpenGL access
  to save images reliably.

## Most useful files to inspect

- `backend/config/chimerax.py`
- `backend/utils/chimerax_render.py`
- `backend/utils/validate_chimerax.py`
