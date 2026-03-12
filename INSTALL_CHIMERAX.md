# Installing ChimeraX for Protein Visualization

## Quick Installation Guide

### Step 1: Download ChimeraX
1. Go to: **https://www.cgl.ucsf.edu/chimerax/download.html**
2. Click "Download" for Windows
3. Download the installer (usually `ChimeraX-1.x-win64.exe`)

### Step 2: Install ChimeraX
1. Run the downloaded installer
2. Follow the installation wizard
3. **Important:** Install to the default location: `C:\Program Files\ChimeraX\`
4. Complete the installation

### Step 3: Verify Installation
Open a new PowerShell or Command Prompt and run:
```powershell
chimerax --version
```

If you see a version number, ChimeraX is installed correctly!

### Step 4: Restart Backend
1. Close the backend PowerShell window
2. Restart the backend server
3. The backend will automatically detect ChimeraX

## Alternative: Manual Path Configuration

If ChimeraX is installed in a non-standard location, you can:

1. **Add to PATH:**
   - Find where ChimeraX is installed (usually `C:\Program Files\ChimeraX\bin\`)
   - Add that directory to your system PATH environment variable
   - Restart the backend

2. **Or modify the code:**
   - Edit `backend/utils/chimerax_render.py`
   - Add your ChimeraX path to the `common_paths` list in `get_chimerax_command()`

## Testing Visualization

After installing ChimeraX and restarting the backend:

1. Upload a PDB structure file
2. Wait for processing to complete
3. Click the "+" button to expand results
4. You should see the "Protein Structure Visualization" section with the rendered image

## Troubleshooting

### "ChimeraX not found" after installation
- Make sure you restarted the backend after installing
- Verify ChimeraX is in PATH: `chimerax --version` in terminal
- Check if it's in a standard location (see Step 1 of verification)

### Visualization still not appearing
- Check backend logs for ChimeraX errors
- Verify the PDB file is valid
- Make sure the backend has write permissions to `static/visualizations/` directory

### Slow rendering
- First-time rendering can take 30-120 seconds
- Subsequent renders of the same file are cached and instant

## Notes

- ChimeraX is only needed for visualization - the rest of the app (BLAST, TM-align) works without it
- Visualization failures don't break the app - you'll just see a message instead of the image
- Images are cached, so repeated uploads of the same structure are fast

