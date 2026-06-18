# Linux Backend Deployment

This directory contains the minimum files needed to deploy the hosted backend on
an Ubuntu VM.

## Assumptions

- Linux host: Ubuntu 22.04 or 24.04
- Repo clone location: `/opt/effectors/Effectors`
- Public API domain: `api.example.com`
- Hosted backend runs in `local` execution mode for now
- A separate frontend will talk to this backend over HTTPS

## Files

- `install_backend.sh`: one-time bootstrap script
- `env.backend.example`: environment file template
- `systemd/effectors-api.service`: systemd unit for the FastAPI process
- `systemd/effectors-worker.service`: systemd unit for the worker process
- `nginx/effectors-api.conf`: nginx reverse proxy template

## AlphaFold via HPC

The hosted scaffold can request GPU resources for Slurm jobs when the client
sets `run_alphafold=true` in the job request payload.

To make AlphaFold/ColabFold available on the cluster nodes, set:

- `EFFECTOR_HPC_JOB_PROLOGUE` in `deploy/linux/env.backend` to load modules or
  activate a conda env
- `EFFECTOR_ALPHAFOLD_BIN` and optional `EFFECTOR_ALPHAFOLD_ARGS` inside that
  prologue (for example, `colabfold_batch`)

## Recommended deployment order

1. Clone the repo on the Linux VM.
2. Copy `env.backend.example` to `env.backend`.
3. Run `install_backend.sh`.
4. Copy the systemd unit files into `/etc/systemd/system/`.
5. Copy the nginx config into `/etc/nginx/sites-available/`.
6. Enable systemd services.
7. Enable nginx and add HTTPS with certbot.

## Quick commands

```bash
cd /opt/effectors/Effectors
sudo bash deploy/linux/install_backend.sh
cp deploy/linux/env.backend.example deploy/linux/env.backend
sudo cp deploy/linux/systemd/effectors-api.service /etc/systemd/system/
sudo cp deploy/linux/systemd/effectors-worker.service /etc/systemd/system/
sudo cp deploy/linux/nginx/effectors-api.conf /etc/nginx/sites-available/effectors-api
sudo ln -sf /etc/nginx/sites-available/effectors-api /etc/nginx/sites-enabled/effectors-api
sudo systemctl daemon-reload
sudo systemctl enable effectors-api effectors-worker
sudo systemctl restart effectors-api effectors-worker
sudo nginx -t && sudo systemctl reload nginx
```

## Verify

```bash
systemctl status effectors-api --no-pager
systemctl status effectors-worker --no-pager
journalctl -u effectors-api -n 50 --no-pager
journalctl -u effectors-worker -n 50 --no-pager
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/jobs/mode
```
