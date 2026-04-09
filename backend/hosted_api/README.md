# Hosted API Scaffold

This package is the next-step public hosting scaffold for the effector product.
It does not replace `backend/main.py`. It adds the production-oriented shape:

- persistent job records
- async-friendly result contract
- explicit pipeline adapter seam wired to the current backend engine
- separate status and summary endpoints

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
- Upload size, sequence length, retry count, and optional admin-key protection are configurable
