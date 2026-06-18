# Deploy: Azure VM + Vercel + Medicine Bow (HPC)

This repo is designed to run as:

- Frontend: Vercel (Next.js in `frontend/`)
- Backend: Ubuntu VM (FastAPI + worker in `backend/hosted_api/`)
- Compute: Medicine Bow (Slurm) for HPC jobs, including AlphaFold/ColabFold

The backend VM submits jobs to Medicine Bow over SSH when `EFFECTOR_EXECUTION_MODE=hpc`.

## 1. Azure VM

Create an Ubuntu 22.04 or 24.04 VM.

Minimum starting size:

- B1s works for light API + worker traffic (not for heavy compute)

Networking:

- Allow inbound `22/tcp`, `80/tcp`, `443/tcp`

## 2. DNS

- `api.<your-domain>` -> Azure VM public IP (A record)
- `app.<your-domain>` -> Vercel (CNAME as instructed by Vercel)

## 3. Backend install (on the VM)

```bash
sudo mkdir -p /opt/effectors
sudo chown -R ubuntu:ubuntu /opt/effectors
cd /opt/effectors
git clone <your-repo-url> Effectors
cd /opt/effectors/Effectors
sudo bash deploy/linux/install_backend.sh
cp deploy/linux/env.backend.example deploy/linux/env.backend
```

Edit `deploy/linux/env.backend`:

- `EFFECTOR_PUBLIC_BASE_URL=https://api.<your-domain>`
- `EFFECTOR_CORS_ALLOWED_ORIGINS=https://app.<your-domain>`
- `EFFECTOR_ADMIN_API_KEY=<random-secret>`
- `EFFECTOR_EXECUTION_MODE=hpc`
- `EFFECTOR_HPC_REMOTE_HOST=medicinebow`
- `EFFECTOR_HPC_REMOTE_EFFECTORS_ROOT=/home/gokulsrinathseetharam/projects/Effectors` (path on Medicine Bow)
- `EFFECTOR_HPC_JOB_PROLOGUE=<module/conda activation for Medicine Bow>`
- `EFFECTOR_ALPHAFOLD_BIN=colabfold_batch` (or the correct binary on Medicine Bow)

## 4. Put Medicine Bow SSH credentials on the VM

The backend VM must be able to run `ssh medicinebow ...` without prompts.

Install the key and cert under the user that runs the systemd services (default is `ubuntu`).

```bash
mkdir -p /home/ubuntu/.ssh
chmod 700 /home/ubuntu/.ssh

# Copy these from your local machine:
# - medicinebow (private key)
# - medicinebow-cert.pub (certificate)

chmod 600 /home/ubuntu/.ssh/medicinebow
chmod 644 /home/ubuntu/.ssh/medicinebow-cert.pub

cat > /home/ubuntu/.ssh/config <<'EOF'
Host medicinebow
  HostName medicinebow.arcc.uwyo.edu
  User gokulsrinathseetharam
  IdentityFile ~/.ssh/medicinebow
  CertificateFile ~/.ssh/medicinebow-cert.pub
  IdentitiesOnly yes
  PubkeyAuthentication yes
  PreferredAuthentications publickey
EOF
chmod 600 /home/ubuntu/.ssh/config
```

Verify:

```bash
sudo -u ubuntu ssh -o BatchMode=yes medicinebow "hostname"
```

## 5. Clone the repo on Medicine Bow

On Medicine Bow (OnDemand Shell Access):

```bash
mkdir -p ~/projects
cd ~/projects
git clone <your-repo-url> Effectors
```

This path must match `EFFECTOR_HPC_REMOTE_EFFECTORS_ROOT`.

## 6. systemd + nginx + TLS (on the VM)

```bash
sudo cp deploy/linux/systemd/effectors-api.service /etc/systemd/system/
sudo cp deploy/linux/systemd/effectors-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable effectors-api effectors-worker
sudo systemctl restart effectors-api effectors-worker
```

Install nginx config:

```bash
sudo cp deploy/linux/nginx/effectors-api.conf /etc/nginx/sites-available/effectors-api
sudo ln -sf /etc/nginx/sites-available/effectors-api /etc/nginx/sites-enabled/effectors-api
sudo nginx -t
sudo systemctl reload nginx
```

Get HTTPS (Certbot):

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.<your-domain>
```

## 7. Verify the backend and HPC wiring

Public:

- `GET https://api.<your-domain>/health`

Admin-only diagnostics:

- `GET https://api.<your-domain>/jobs/hpc/diagnostics`
  - header: `x-api-key: <EFFECTOR_ADMIN_API_KEY>`

## 8. Vercel frontend

Deploy `frontend/` to Vercel and set env:

- `NEXT_PUBLIC_API_URL=https://api.<your-domain>`

