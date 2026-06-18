# Structure-based Effector Discovery Pipeline

Research infrastructure for structure-based effector discovery using BLAST,
TM-align, and AlphaFold/ColabFold. Accepts protein structures, sequences, and
multi-FASTA inputs and classifies them as known, structurally similar, or novel
effectors.

Jobs run on the **University of Wyoming Medicine Bow HPC cluster** (Slurm) via
SSH from your local machine. AlphaFold structure prediction runs on Medicine Bow
GPU nodes using ColabFold 1.5.5.

## Quick Start

### Requirements

- Python 3.10+ (3.12 recommended)
- Node.js 18+ (24.x supported via Turbopack)
- BLAST+ installed and on PATH
- WSL with Ubuntu (for TM-align on Windows) **or** native TM-align binary
- SSH access to Medicine Bow HPC (University of Wyoming ARCC)

### Run everything (one command)

```powershell
.\start_app.bat
```

or

```powershell
.\start_app.ps1
```

This starts all 4 processes:
- Demo backend on `http://localhost:8000`
- Hosted API on `http://localhost:8001`
- Worker process (polls for queued jobs)
- Frontend on `http://localhost:3000`

Then open **`http://localhost:3000`** — that's the production UI.

---

## Architecture

```
Browser (localhost:3000)
    ↓
Next.js Frontend (Turbopack)
    ↓
Hosted API (port 8001) — creates + tracks jobs
    ↓
Worker — picks up queued jobs every 5s
    ↓ SSH/SCP
Medicine Bow HPC (medicinebow.arcc.uwyo.edu)
    ↓ Slurm (teton partition — CPU, teton-gpu — AlphaFold)
Compute node:
    BLAST 2.16.0            — sequence search
    TMalign (~/bin)         — structure comparison
    ColabFold 1.5.5 (GPU)   — novel structure prediction
    ↓ SCP results back
Worker → DB → UI
```

### Execution modes

Set in `backend/hosted_api/.env`:

| Mode | What happens |
|------|-------------|
| `local` | Jobs run on your Windows machine (BLAST + TM-align via WSL) |
| `hpc` | Jobs submitted to Medicine Bow via SSH/Slurm (**default, recommended**) |

---

## UI

**`http://localhost:3000`** — main production UI with 3 tabs:

| Tab | What it does |
|-----|-------------|
| Paste Sequence | BLAST search → TM-align → classification |
| Upload Structure (PDB/CIF) | TM-align against 470 database structures |
| Upload FASTA | Batch processing — one result per sequence |

All tabs support optional email notification and AlphaFold prediction for novel
sequences.

**`http://localhost:3000/hosted`** — raw admin/debug view (job IDs, tokens, JSON).

---

## Repository Layout

```
backend/
  main.py                        # synchronous biology engine (BLAST + TM-align)
  requirements.txt               # demo backend deps
  requirements-hosted.txt        # hosted backend deps (includes sqlalchemy, dotenv)
  hosted_api/
    main.py                      # hosted FastAPI app
    worker.py                    # DB-polling worker (submits to HPC or runs locally)
    config.py                    # settings loaded from .env
    db.py                        # SQLAlchemy + SQLite setup
    models.py                    # HostedJob model
    schemas.py                   # Pydantic request/response schemas
    routes/jobs.py               # job CRUD + polling endpoints
    remote_runner.py             # entrypoint executed on Medicine Bow compute nodes
    services/
      pipeline_adapter.py        # bridges hosted jobs → backend/main.py pipeline
      hpc_submission.py          # SSH/SCP/Slurm job submission
      hpc_diagnostics.py         # remote host connectivity checks
      alphafold_runner.py        # ColabFold via Apptainer container
      job_runner.py              # local execution with heartbeat
      execution.py               # mode resolver (local vs hpc)
      rate_limit.py              # sliding-window rate limiter
    tests/
      test_hosted_api_unittest.py  # 5 contract tests
frontend/
  app/
    page.tsx                     # main production UI (all 3 input types)
    hosted/page.tsx              # admin/debug raw view
    api/                         # Next.js mock API routes (demo fallback)
  next.config.js                 # Turbopack config
Database/                        # 470 curated effector PDB structures
effector_sequences.fasta         # 464 effector sequences (BLAST database)
deploy/
  linux/                         # Linux server deployment templates
  AZURE_VERCEL_MEDICINEBOW.md    # cloud + HPC deployment guide
start_app.bat                    # Windows: start all 4 processes
start_app.ps1                    # PowerShell: start all 4 processes
```

---

## Configuration

Copy `backend/hosted_api/.env.example` → `backend/hosted_api/.env` and fill in:

```env
# Switch between local execution and HPC
EFFECTOR_EXECUTION_MODE=hpc

# Medicine Bow SSH host alias (must match ~/.ssh/config)
EFFECTOR_HPC_REMOTE_HOST=medicinebow

# Your UWyo paths
EFFECTOR_HPC_REMOTE_EFFECTORS_ROOT=/home/<netid>/projects/Effectors
EFFECTOR_HPC_REMOTE_RUNS_ROOT=/gscratch/<netid>/runs/effectors
EFFECTOR_HPC_REMOTE_RESULTS_ROOT=/gscratch/<netid>/results/effectors
EFFECTOR_HPC_REMOTE_LOGS_ROOT=/gscratch/<netid>/logs/effectors

# Slurm
EFFECTOR_HPC_SLURM_ACCOUNT=effectorfold
EFFECTOR_HPC_SLURM_PARTITION=teton
EFFECTOR_HPC_SLURM_PARTITION_GPU=teton-gpu

# Module load prologue on compute nodes
EFFECTOR_HPC_JOB_PROLOGUE=module load arcc/1.0 gcc/14.2.0 blast/2.16.0 python/3.12.0 colabfold/1.5.5 && export PATH=$HOME/bin:$PATH

# AlphaFold via Apptainer container
EFFECTOR_ALPHAFOLD_BIN=apptainer exec --nv --bind $CF_CACHE:/cache $CF_SIF colabfold_batch
EFFECTOR_ALPHAFOLD_ARGS=--num-recycle 1 --num-models 1 --msa-mode single_sequence

# Admin key for protected endpoints
EFFECTOR_ADMIN_API_KEY=<your-secret>
```

### SSH config (`~/.ssh/config`)

```
Host medicinebow
    HostName medicinebow.arcc.uwyo.edu
    User <your-netid>
    IdentityFile ~/.ssh/medicinebow
    CertificateFile ~/.ssh/medicinebow-cert.pub
    IdentitiesOnly yes
    BatchMode yes
```

### One-time Medicine Bow setup

```bash
# On Medicine Bow (via OnDemand shell):
mkdir -p ~/projects ~/bin /gscratch/<netid>/{runs,results,logs}/effectors

# Compile TM-align (not available as a module)
wget https://zhanggroup.org/TM-align/TMalign.cpp -O /tmp/TMalign.cpp
g++ -O3 -o ~/bin/TMalign /tmp/TMalign.cpp

# Clone the repo
git clone https://github.com/gokulsrinaths/Effectors ~/projects/Effectors

# Install Python deps
module load arcc/1.0 gcc/14.2.0 python/3.12.0
pip3 install --user fastapi pydantic sqlalchemy python-multipart uvicorn
```

---

## HPC Diagnostics

Verify Medicine Bow connectivity before submitting jobs:

```bash
curl -H "x-api-key: <ADMIN_KEY>" http://localhost:8001/jobs/hpc/diagnostics
```

All fields should show `ok`. Expected output:
```json
{
  "ok": true,
  "stdout": "host=mblog1\nuser=...\nsbatch=ok\nsacct=ok\nrepo_dir=ok\nremote_runner=ok\nalphafold_bin=ok\npython3=ok\nbash=ok"
}
```

---

## Status and Roadmap

### ✅ Completed and Working

| Feature | Details |
|---------|---------|
| BLAST sequence search | BLAST 2.16.0, local effector FASTA database (464 sequences) |
| TM-align structure comparison | 470 curated PDB structures, native binary on HPC |
| Structure upload (PDB/CIF) | TM-align against full database |
| Single sequence | BLAST → TM-align on best hit |
| FASTA batch processing | Per-sequence BLAST + TM-align |
| AlphaFold/ColabFold 1.5.5 | Novel sequences → GPU prediction on Medicine Bow |
| HPC submission via SSH/Slurm | teton (CPU) + teton-gpu (GPU) partitions |
| Async job queue + worker | SQLite-backed, polling every 5s, lease recovery |
| Job access tokens + rate limiting | Per-job tokens, 30 req/min rate limit |
| Admin API key protection | `/jobs` list, diagnostics, manual trigger |
| Unified production UI | 3 tabs, email field, AlphaFold checkbox, results table |
| Unit tests (5/5 passing) | Token gating, rate limit, upload validation, stale job recovery |
| Start scripts (Windows) | `start_app.bat` / `start_app.ps1` — starts all 4 processes |
| Linux deployment templates | systemd, nginx, install script in `deploy/linux/` |
| Email notifications | SMTP or preview-file fallback |

### ⏳ Pending / TODO

| Item | Priority | Notes |
|------|----------|-------|
| **Public hosting** | High | App runs locally only. Need a Linux VM with public IP to serve external users. Deploy guide at `deploy/AZURE_VERCEL_MEDICINEBOW.md`. Google Cloud / DigitalOcean free/cheap options work. |
| **Frontend on Vercel** | High | Set `NEXT_PUBLIC_API_URL` to hosted server, deploy `frontend/` on Vercel. Free tier works. |
| **SMTP email config** | Medium | Currently saves email previews to local files. Set `EFFECTOR_SMTP_HOST` etc. in `.env` to enable real delivery. |
| **Postgres + object storage** | Low | SQLite + local disk is fine for single-server use. Replace with Postgres + S3/Azure Blob for multi-node or high-throughput. |
| **Redis/queue worker** | Low | Polling worker is sufficient. Replace with Redis/RabbitMQ if job volume grows significantly. |
| **User authentication** | Low | No login system. Anyone with the URL can submit jobs. Add if needed for access control. |
| **Visualization (3D)** | Low | Currently returns a placeholder SVG. Wire up py3Dmol or ChimeraX for real 3D structure rendering. |

---

## API Reference

### Hosted API (`localhost:8001`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/jobs` | — | Create sequence job |
| POST | `/jobs/upload` | — | Create structure or FASTA job |
| GET | `/jobs/{id}` | job token | Poll job status |
| GET | `/jobs/results/{id}` | job token | Fetch completed results |
| GET | `/jobs/files/{id}/alphafold` | job token | Download AlphaFold PDB |
| GET | `/jobs` | admin key | List all jobs |
| GET | `/jobs/hpc/diagnostics` | admin key | Check Medicine Bow connectivity |
| GET | `/jobs/mode` | — | Current execution mode |
| GET | `/health` | — | Service health and config |

### Demo backend (`localhost:8000`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/process/structure` | Synchronous structure comparison |
| POST | `/api/process/sequence` | Synchronous sequence search |
| POST | `/api/process/fasta` | Synchronous batch FASTA |
| GET | `/api/download/pdb` | Download a structure from the database |
| GET | `/status` | Tool availability (BLAST, TM-align, WSL) |

---

## Notes

- This is research infrastructure, not a clinical or regulated product.
- The synchronous demo backend (`localhost:8000`) is useful for debugging biology
  logic locally without the job queue overhead.
- HPC mode requires your machine to be on and SSH-accessible to Medicine Bow when
  jobs are submitted. For 24/7 unattended operation, run the worker on a server.
