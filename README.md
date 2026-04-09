## Structure-based Effector Discovery Pipeline

Research web application for structure-based effector discovery. The product
accepts protein structures, single sequences, and multi-FASTA inputs, then runs
sequence search and structure comparison against local effector databases.

This repository now contains two execution surfaces:

- the original synchronous research demo
- a new hosted-product scaffold with persistent jobs, staged uploads, a worker,
  result summaries, and email-ready completion flow

---

## 1. What the product does

The core product flow is:

1. user submits a structure, sequence, or FASTA file
2. backend runs BLAST and/or TM-align against the local effector databases
3. backend returns a classification summary and supporting match data
4. optional ChimeraX rendering produces a protein image
5. results are shown in the UI and can be prepared for email delivery

Supported inputs:

- `.pdb` or `.cif` structure uploads
- single protein sequences
- multi-FASTA uploads

Core tools:

- BLAST+ (`blastp`, `makeblastdb`)
- TM-align
- optional ChimeraX for structure rendering

Core data:

- `Database/` for local PDB structures
- `effector_sequences.fasta` for the local sequence database

---

## 2. Repository modes

### 2.1 Research demo

The original demo path is:

- frontend: [`frontend/app/page.tsx`](frontend/app/page.tsx)
- backend: [`backend/main.py`](backend/main.py)

This mode processes requests synchronously and is the current biology engine of
record.

### 2.2 Hosted product scaffold

The hosted path is:

- backend scaffold: [`backend/hosted_api/README.md`](backend/hosted_api/README.md)
- entrypoint: [`backend/hosted_api/main.py`](backend/hosted_api/main.py)
- worker: [`backend/hosted_api/worker.py`](backend/hosted_api/worker.py)
- hosted frontend page: [`frontend/app/hosted/page.tsx`](frontend/app/hosted/page.tsx)

This mode adds:

- persistent jobs
- staged uploads
- background worker execution
- result retrieval endpoints
- email preview or SMTP delivery
- execution-mode seam for future HPC routing

---

## 3. Product pipeline

### 3.1 Structure upload

- frontend submits a `.pdb` or `.cif`
- backend checks for exact filename match in `Database/`
- if needed, backend runs TM-align across the local structure DB
- backend returns best match, TM-score, RMSD, and optional top matches
- if ChimeraX is available and the input is a `.pdb`, a visualization image is generated

Primary endpoint:

- `POST /api/process/structure`

### 3.2 Single sequence

- frontend submits one protein sequence
- backend normalizes the sequence
- backend runs BLASTP against `effector_sequences.fasta`
- backend maps the hit to a local structure when possible
- backend runs TM-align if structure comparison is available
- if the sequence is novel or structure is missing, the backend returns a queued
  structure-prediction status placeholder

Primary endpoint:

- `POST /api/process/sequence`

### 3.3 Multi-FASTA

- frontend uploads a FASTA file
- backend parses each sequence
- each sequence goes through the same BLAST plus structure comparison path
- backend returns a per-sequence result list

Primary endpoint:

- `POST /api/process/fasta`

### 3.4 Visualization

- backend can render a protein PNG from a PDB file using ChimeraX
- rendered images are cached in `static/visualizations/`
- frontend can also download matched PDB files directly

Primary endpoints:

- `POST /api/visualize/protein`
- `GET /api/download/pdb?structure_id=<id>`

---

## 4. Hosted async flow

The hosted-product flow is:

1. client creates a job
2. API stores the input and writes a persistent job record
3. worker polls for queued jobs
4. worker runs the current backend engine through the hosted adapter
5. API stores a condensed result summary and full result artifact
6. email is sent through SMTP or written to a preview file
7. frontend polls job status and fetches final results

Important constraint:

- this repository currently supports `local` execution mode for hosted jobs
- `hpc` mode is reserved for future MedicineBow submission wiring

Hosted API endpoints:

- `POST /jobs`
- `POST /jobs/upload`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/results/{job_id}`
- `GET /jobs/mode`

---

## 5. Quick start for the original demo

### 5.1 Requirements

- Python 3.10+
- Node.js 18+

### 5.2 Install

```powershell
cd backend
py -3 -m pip install -r requirements.txt

cd ..\frontend
npm install
```

### 5.3 Run

From the repo root:

```powershell
.\start_app.ps1
```

Then open:

- frontend: `http://localhost:3000`
- backend docs: `http://localhost:8000/docs`

---

## 6. Quick start for the hosted scaffold

### 6.1 Install backend dependencies

```powershell
cd backend
py -3 -m pip install -r requirements-hosted.txt
```

### 6.2 Run the hosted API

```powershell
cd backend
py -3 -m uvicorn hosted_api.main:app --reload
```

### 6.3 Run the hosted worker

Open a second terminal:

```powershell
cd backend
py -3 -m hosted_api.worker
```

### 6.4 Run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Then open:

- demo UI: `http://localhost:3000`
- hosted async UI: `http://localhost:3000/hosted`

---

## 7. ChimeraX

ChimeraX is optional and only affects structure visualization.

Key files:

- [`backend/config/chimerax.py`](backend/config/chimerax.py)
- [`backend/utils/chimerax_render.py`](backend/utils/chimerax_render.py)
- [`backend/utils/validate_chimerax.py`](backend/utils/validate_chimerax.py)
- [`docs/CHIMERAX_USAGE.md`](docs/CHIMERAX_USAGE.md)

Minimal validation:

```powershell
Test-Path "C:\Program Files\ChimeraX 1.11\bin\chimerax.exe"
py -3 backend\utils\validate_chimerax.py
```

If ChimeraX is available, uploaded PDB structures can produce cached images under
`static/visualizations/`.

---

## 8. Key project files

```text
backend/
  main.py                    # current synchronous biology engine
  requirements.txt           # demo/backend deps
  requirements-hosted.txt    # hosted scaffold deps
  hosted_api/
    main.py                  # hosted API entrypoint
    worker.py                # DB-polling worker
    routes/jobs.py           # hosted job routes
    services/                # adapter, email, execution, runner
frontend/
  app/
    page.tsx                 # original synchronous demo UI
    hosted/page.tsx          # hosted async UI
Database/                    # local PDB structures
effector_sequences.fasta     # local sequence database
static/visualizations/       # ChimeraX image cache
docs/
  DISPATCHER_PRODUCT_PLAN.md
  CHIMERAX_USAGE.md
```

---

## 9. Current status

Implemented:

- real BLAST and TM-align integration in the original backend
- structure, sequence, and FASTA flows in the original frontend
- optional ChimeraX rendering
- hosted async API scaffold with persistent jobs
- local worker process for queued jobs
- staged uploads and result retrieval
- email preview fallback and SMTP-ready configuration

Pending:

- extract shared pipeline services out of `backend/main.py`
- connect hosted execution mode to MedicineBow for heavy jobs
- replace polling worker with a more production-grade queue if needed
- harden auth, abuse control, and deployment for a public internet-facing service

---

## 10. Notes

This is still research infrastructure, not a finished production SaaS. The hosted
scaffold is the correct next architecture for a public-facing version, but the
real heavy-compute path should move to HPC submission rather than running large
jobs directly on the public server.
