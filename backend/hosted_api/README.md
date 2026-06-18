# Hosted API Scaffold

This package is the next-step public hosting scaffold for the effector product.
It does not replace `backend/main.py`. It adds the production-oriented shape:

- persistent job records
- per-job access tokens for public status/result access
- async-friendly result contract
- explicit pipeline adapter seam wired to the current backend engine
- separate status and summary endpoints
- worker leases, heartbeats, and stale-job recovery
- optional SSH/Slurm-backed HPC submission mode

## Why this exists

The current demo backend processes requests synchronously. That works for local
research use, but a public product needs:

- immediate job creation
- persistent status tracking
- result summaries for UI and email
- a future worker or HPC execution mode

## Start locally

From `backend/`:

```powershell
py -3 -m pip install -r requirements-hosted.txt
py -3 -m uvicorn hosted_api.main:app --reload
```

Environment settings example:

- `hosted_api/.env.example`

Run the worker in a second terminal:

```powershell
cd backend
py -3 -m hosted_api.worker
```

## API shape

- `POST /jobs`
- `POST /jobs/upload`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/results/{job_id}`
- `GET /jobs/mode`
- `GET /health`
- `POST /jobs/{job_id}/run`

`POST /jobs/{job_id}/run` is an explicit local demo trigger for now. In the real
hosted product this should be called by a worker, not by a browser.

## What is real today

- Sequence jobs can be routed into the existing biology engine in `backend/main.py`
- Structure and FASTA uploads can be staged through the hosted API and executed
  through the same adapter contract
- Email delivery uses SMTP if configured, otherwise writes a local preview file
- Worker polling and execution mode are configured through `.env.example`
- Upload size, sequence length, retry count, rate limiting, and admin-key protection are configurable

## HPC execution mode (SSH + Slurm)

Set `EFFECTOR_EXECUTION_MODE=hpc` on the machine running the hosted API + worker
(the “API host”). In this mode:

- the API host stages uploads to local disk as usual
- the worker copies staged inputs to the cluster over `scp`
- the worker submits an `sbatch` job over `ssh`
- the worker periodically refreshes job status via `sacct`/`squeue`
- when finished, the worker copies `result.json` back to `backend/hosted_api/data/results/`

### 1) Prepare SSH access from the API host

Ensure `ssh <EFFECTOR_HPC_REMOTE_HOST>` works non-interactively (keys, not
password prompts). The value is an SSH host alias, typically configured in
`~/.ssh/config` on the API host.

### 2) Clone the repo on the cluster

On the cluster (or shared filesystem), clone this repo to the path configured as:

- `EFFECTOR_HPC_REMOTE_EFFECTORS_ROOT`

This path must contain `backend/hosted_api/remote_runner.py` because Slurm jobs
run that entrypoint inside the repo clone.

### 3) Configure remote writable directories

These must exist or be creatable by your cluster user:

- `EFFECTOR_HPC_REMOTE_RUNS_ROOT`
- `EFFECTOR_HPC_REMOTE_RESULTS_ROOT`
- `EFFECTOR_HPC_REMOTE_LOGS_ROOT`

### 4) Configure Slurm + modules/env

Set:

- `EFFECTOR_HPC_SLURM_ACCOUNT` (required on many clusters)
- optional `EFFECTOR_HPC_SLURM_PARTITION`, `*_TIME`, `*_MEM`, `*_CPUS`, `*_GPUS`

If your cluster needs module loads or conda activation, put it in:

- `EFFECTOR_HPC_JOB_PROLOGUE`

### 5) Validate connectivity

With `EFFECTOR_ADMIN_API_KEY` set, call:

- `GET /jobs/hpc/diagnostics`

This checks SSH connectivity, Slurm tool availability, the repo path, and
optional AlphaFold binary visibility under the configured prologue.
