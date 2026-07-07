#!/bin/bash
# Set up SSH keys from environment variables then start the hosted API

if [ -n "$HPC_SSH_KEY_B64" ]; then
    mkdir -p ~/.ssh
    echo "$HPC_SSH_KEY_B64" | base64 -d > ~/.ssh/medicinebow
    chmod 600 ~/.ssh/medicinebow
fi

if [ -n "$HPC_SSH_CERT_B64" ]; then
    echo "$HPC_SSH_CERT_B64" | base64 -d > ~/.ssh/medicinebow-cert.pub
    chmod 644 ~/.ssh/medicinebow-cert.pub
fi

cat > ~/.ssh/config << 'EOF'
Host medicinebow
    HostName medicinebow.arcc.uwyo.edu
    User gokulsrinathseetharam
    IdentityFile ~/.ssh/medicinebow
    CertificateFile ~/.ssh/medicinebow-cert.pub
    IdentitiesOnly yes
    PubkeyAuthentication yes
    PreferredAuthentications publickey
    StrictHostKeyChecking no
EOF
chmod 600 ~/.ssh/config

# Install openssh-client if ssh is not available
if ! command -v ssh &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq openssh-client
fi

echo "SSH setup complete"

# Start worker in background
python -m hosted_api.worker &

exec python -m uvicorn hosted_api.main:app --host 0.0.0.0 --port ${PORT:-8080}
