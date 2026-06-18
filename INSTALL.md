# Installation Guide for Effector Discovery Pipeline

This guide will help you install BLAST+ and TMalign to enable full functionality of the pipeline.

## Prerequisites

- Python 3.8+ (already installed)
- Windows 10/11 (current system)
- Node.js **22 LTS** (recommended) or **20 LTS** (for the frontend)

## Step 1: Install BLAST+

### Option A: Download Windows Installer (Recommended)

1. **Download BLAST+**:
   - Visit: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/
   - Download: `ncbi-blast-*-win64.exe` (Windows installer)

2. **Install**:
   - Run the installer
   - Default installation path: `C:\Program Files\NCBI\blast-*\bin`
   - **Important**: Check "Add to PATH" during installation, or manually add to PATH

3. **Verify Installation**:
   ```powershell
   blastp -version
   ```
   Should show version information.

### Option B: Manual Installation

1. **Download**:
   - Visit: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/
   - Download: `ncbi-blast-*-win64.tar.gz`

2. **Extract**:
   - Extract to `C:\Program Files\NCBI\` or project `bin\` directory

3. **Add to PATH**:
   - Add `C:\Program Files\NCBI\blast-*\bin` to system PATH
   - Or copy `blastp.exe` and `makeblastdb.exe` to project `bin\` directory

## Step 2: Install TMalign

### Option A: Download Pre-compiled (if available)

1. **Download**:
   - Visit: https://zhanggroup.org/TM-align/
   - Download Windows executable if available

2. **Install**:
   - Extract `TMalign.exe` to project `bin\` directory
   - Or add to system PATH

### Option B: Compile from Source

1. **Download Source**:
   - Visit: https://zhanggroup.org/TM-align/
   - Download source code

2. **Compile**:
   ```bash
   # Requires C++ compiler (Visual Studio or MinGW)
   g++ -static -O3 -ffast-math -lm -o TMalign TMalign.cpp
   ```

3. **Copy**:
   - Copy `TMalign.exe` to project `bin\` directory

## Step 3: Create BLAST Database

After installing BLAST+, create the database index:

```powershell
cd C:\Users\sgoku\Downloads\Effectors
makeblastdb -in "Effector sequence.txt" -dbtype prot -out "Effector sequence" -title "Effector Sequences"
```

This will create database files:
- `Effector sequence.psq`
- `Effector sequence.phr`
- `Effector sequence.pin`

## Step 4: Verify Installation

Run the setup verification script:

```powershell
python setup_tools.py
```

Or test manually:

```powershell
# Test BLAST+
blastp -version
makeblastdb -version

# Test TMalign
TMalign

# Check database
dir "Effector sequence.*"
```

## Step 5: Restart Backend

After installation, restart the backend server:

```powershell
# Stop existing server (Ctrl+C in server window)
cd backend
python main.py
```

## Troubleshooting

### BLAST+ not found
- Verify PATH includes BLAST+ bin directory
- Or copy executables to project `bin\` directory
- Restart terminal/IDE after adding to PATH

### TMalign not found
- Copy `TMalign.exe` to project `bin\` directory
- Or add TMalign directory to PATH

### Database creation fails
- Ensure `Effector sequence.txt` exists
- Check BLAST+ is installed correctly
- Verify write permissions in project directory

### Still having issues?
- Check backend logs for detailed error messages
- Verify binaries are executable (not blocked by Windows)
- Try running binaries directly from command line

### Frontend `next dev` fails with `Error: spawn EPERM`
- This usually means your Node.js version can't `fork()` child processes on your Windows setup.
- Use Node.js **22 LTS** (recommended) or **20 LTS** (avoid Node.js 24+), then reinstall frontend deps:
  ```powershell
  cd frontend
  Remove-Item -Recurse -Force node_modules,package-lock.json
  npm install
  npm run dev
  ```

## Quick Test

After installation, test the API:

```powershell
python test_api.py
```

All endpoints should return real results instead of mock data.

