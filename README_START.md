# Quick Start Guide

## Starting the Application

### Option 1: Windows Batch File (Easiest)
Double-click `start_app.bat` or run from command prompt:
```cmd
start_app.bat
```

### Option 2: PowerShell Script
Right-click `start_app.ps1` → "Run with PowerShell" or run:
```powershell
.\start_app.ps1
```

### Option 3: Manual Start
**Terminal 1 - Backend:**
```cmd
cd backend
python main.py
```

**Terminal 2 - Frontend:**
```cmd
cd frontend
npm run dev
```

## Access the Application

- **Frontend UI:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **Status Endpoint:** http://localhost:8000/status

## Stopping the Servers

Close the terminal windows where the servers are running, or press `Ctrl+C` in each window.

## Features

- ✅ Upload Structure (PDB/CIF) - TM-align comparison
- ✅ Paste Single Sequence - BLAST search + structure matching
- ✅ Upload FASTA File - Process multiple sequences

All tools are automatically validated at startup. No manual configuration needed!

