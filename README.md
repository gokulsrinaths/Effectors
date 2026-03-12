## Structure-based Effector Discovery Pipeline

Research-grade web application for **structure-based effector discovery**. This project combines sequence search (BLAST) and structure comparison (TM-align) against an curated effector database, with a modern web UI suitable for academic demos and cyberinfrastructure proposals.

---

## 1. Highlights

- **End-to-end pipeline**: sequence/structure in → effector classification out  
- **Modern stack**: FastAPI backend + Next.js (React) frontend  
- **Research-focused**: designed around BLAST+, TM-align and effector DBs  
- **Windows-friendly**: one-command launcher scripts for local demos  

---

## 2. Table of contents

1. [Highlights](#1-highlights)  
2. [Architecture](#3-architecture)  
3. [Quick start (Windows demo)](#4-quick-start-windows-demo)  
4. [Manual dev setup (any OS)](#5-manual-dev-setup-any-os)  
5. [System requirements (full pipeline)](#6-system-requirements-full-pipeline)  
6. [Core workflows](#7-core-workflows)  
7. [Project layout](#8-project-layout)  
8. [Status & roadmap](#9-status--roadmap)  
9. [Academic context](#10-academic-context)  

---

## 3. Architecture

- **Frontend**
  - Framework: **Next.js 14 + React 18**
  - Role: Single-page UI for uploading structures / sequences and visualizing results
  - Communication: JSON over HTTP to the FastAPI backend

- **Backend**
  - Framework: **FastAPI**
  - Role: Orchestrates BLAST+, TM-align, structure DB lookup, and optional visualization
  - External tools:
    - **BLAST+** (`blastp`, `makeblastdb`)
    - **TM-align** (via WSL on Windows)
    - Optional: **ChimeraX** for 3D renderings (if installed)

- **Data**
  - `Database/`: curated PDB structures for effectors
  - `effector_sequences.fasta`: effector sequence database
  - `static/visualizations/`: cached PNG renderings (if ChimeraX is available)

---

## 4. Quick start (Windows demo)

This is the **fastest way to see the app running** on a Windows laptop for a demo.

### 4.1 Prerequisites

- **Python 3.10+** (accessible as `python`)
- **Node.js 18+** (with `npm`)

### 4.2 One-time install

```bash
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

### 4.3 Launch both servers

From the project root:

- **PowerShell**

```powershell
.\start_app.ps1
```

- **Command Prompt (cmd.exe)**

```bat
start_app.bat
```

These scripts will:
- open a window for the **backend** (FastAPI)
- open a window for the **frontend** (Next.js)

Then open a browser and visit:

- **Frontend UI**: `http://localhost:3000`  
- **API docs**: `http://localhost:8000/docs`

---

## 5. Manual dev setup (any OS)

Use this when developing or running on macOS / Linux.

### 5.1 Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Backend runs at **`http://localhost:8000`**.

### 5.2 Frontend (Next.js)

```bash
cd frontend
npm install       # first time only
npm run dev
```

Frontend runs at **`http://localhost:3000`**.

### 5.3 Frontend → backend configuration

By default, the frontend targets `http://localhost:8000`.  
You can override this via an environment variable:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 6. System requirements (full pipeline)

The backend is designed to use **real bioinformatics tools**, not mocks. On startup it runs a comprehensive validation and **fails fast** with human-readable error messages if anything is missing.

To run the **full effector discovery pipeline**, you need:

- **BLAST+**
  - Executables: `blastp`, `makeblastdb`
  - Must be installed and visible on your system `PATH`

- **WSL + Ubuntu** (on Windows) *or* a Linux environment
  - Used as the execution environment for TM-align

- **TM-align**
  - Installed inside WSL/Linux
  - Invokable as `TMalign` (the backend calls `wsl TMalign ...` on Windows)

- **Local databases**
  - `Database/` directory with PDB structures
  - `effector_sequences.fasta` sequence FASTA in the project root

If any of these are missing, `backend/main.py` prints a **BACKEND STARTUP FAILED** block with:
- what is missing (e.g. BLAST+, WSL, TM-align, or the FASTA file), and  
- concrete installation steps to fix it.

You can always still run the **frontend UI** without these tools, but the backend API will not start until requirements are met.

---

## 7. Core workflows

### 7.1 Structure upload

- Endpoint: **`POST /api/process/structure`**
- Input: PDB/CIF file (multipart `file`)
- Behavior:
  - Runs TM-align against the internal structure DB
  - Classifies matches using TM-score:
    - TM-score ≥ 0.9 → *Already in database*
    - 0.6 ≤ TM-score < 0.9 → *Known structural family*
    - TM-score < 0.5 → *Novel structure*

### 7.2 Single-sequence upload

- Endpoint: **`POST /api/process/sequence`**
- Input: JSON body with `sequence` and optional `sequence_id`
- Behavior:
  - Runs BLASTP against the effector sequence DB
  - Maps top hit to a structure, then runs TM-align
  - If no good BLAST hit or structure missing:
    - Returns a “structure prediction queued” status (placeholder for AlphaFold/ColabFold integration in Phase 2)

### 7.3 Multi-FASTA upload

- Endpoint: **`POST /api/process/fasta`**
- Input: multi‑FASTA file (multipart `file`)
- Behavior:
  - Parses sequences and runs the same BLAST+TM-align pipeline per sequence
  - Returns per-sequence classifications and optional “AlphaFold queued” flags

### 7.4 Health & tooling status

- Endpoint: **`GET /status`**
- Reports:
  - Whether BLAST+ is available and indexed
  - Whether WSL and TM-align are reachable
  - Presence/size of the structure database

---

## 8. Project layout

```text
.
├── backend/
│   ├── main.py              # FastAPI application (BLAST + TM-align pipeline)
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Main UI
│   │   ├── page.module.css  # Styles
│   │   ├── layout.tsx       # Root layout
│   │   └── globals.css      # Global styles
│   ├── package.json         # Node dependencies
│   └── tsconfig.json        # TypeScript config
├── Database/                # PDB structures
├── effector_sequences.fasta # Effector sequence database
├── static/visualizations/   # Cached protein renderings (if ChimeraX available)
├── start_app.bat            # Windows launcher (cmd)
└── start_app.ps1            # Windows launcher (PowerShell)
```

---

## 9. Status & roadmap

- **NSF Phase 1**
  - Real BLAST+ + TM-align integration
  - Local effector structure and sequence databases
  - Web interface for structure/sequence upload and classification

- **Planned / Phase 2**
  - AlphaFold/ColabFold integration for unseen sequences
  - Deeper visualization workflows (e.g., richer 3D viewers)
  - Hardened deployment path for HPC and cloud environments

---

## 10. Academic context

This codebase is intended as **research infrastructure** rather than a product:

- Suitable for:
  - Demonstrating structure-based effector discovery in talks and proposals
  - Prototyping workflows for effector classification
  - Serving as a reference implementation for BLAST+ / TM-align orchestration
- Not intended for:
  - Clinical diagnostics
  - High-throughput production pipelines without additional validation and hardening

If you use this work in academic settings, please acknowledge the **Structure-based Effector Discovery Pipeline** project accordingly.

