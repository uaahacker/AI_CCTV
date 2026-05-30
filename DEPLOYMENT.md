# Deployment Guide — AWS EC2 (Ubuntu 24.04)

End-to-end walkthrough to put **AI CCTV Analytics** on a single EC2 instance
with Docker, TLS, backups, and safe security-group rules.

> Replace every placeholder (`cctv.example.com`, `YOUR_IP/32`, etc.) with your
> real values **before** running the commands.

## 1. EC2 + security group

| Item | Recommendation |
|---|---|
| Instance type | `t3.medium` (≤ 10 cameras) → `t3.large` (≤ 30) |
| OS | Ubuntu Server 24.04 LTS (HVM, x86_64) |
| Storage | 40 GB gp3 minimum |
| Key pair | Generate fresh, save the `.pem` locally — never commit it |

**Security group (inbound):**

| Port | Protocol | Source | Why |
|---|---|---|---|
| `22` | TCP | `YOUR_IP/32` (your office / VPN only) | SSH |
| `80` | TCP | `0.0.0.0/0` | HTTP → redirected to HTTPS |
| `443` | TCP | `0.0.0.0/0` | HTTPS (public app) |

**Never** expose `5432` (Postgres), `6379` (Redis), `8000` (Django), `11434`
(Ollama) to `0.0.0.0/0`. They stay inside the Docker network.

## 2. Ubuntu setup

SSH in as `ubuntu`, then:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg ufw fail2ban git make python3-pip

# Docker engine + compose plugin
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker

# Host-level firewall (defence in depth alongside the SG)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo systemctl enable --now fail2ban
```

## 3. Clone & configure

```bash
cd ~
git clone https://github.com/<you>/AI_CCTV.git
cd AI_CCTV
cp .env.example .env

# Generate real secrets
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
python3 -c "from cryptography.fernet import Fernet; print('FIELD_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
```

Paste the three values into `.env`, then update:

- `DATABASE_URL=postgres://cctv:<the-password-you-just-generated>@db:5432/cctv`
- `ALLOWED_HOSTS=cctv.example.com,localhost,127.0.0.1,backend`
- `CORS_ALLOWED_ORIGINS=https://cctv.example.com`
- `DEBUG=False`
- (Optional) configure SMTP for real email alerts.

## 4. First deploy

```bash
docker compose up -d --build
# wait ~30s for migrations + collectstatic to run
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py check --deploy
```

Smoke test:

```bash
curl -fsS http://localhost/api/schema/ | head
```

Visit `http://<ec2-public-ip>/` — you should see the React dashboard.

## 5. DNS + TLS (Let's Encrypt)

1. In your DNS provider, add `cctv.example.com → A → <EC2 public IP>`.
2. Wait for DNS to propagate (`dig cctv.example.com`).
3. Issue the cert:

```bash
docker compose down
sudo apt install -y certbot
sudo certbot certonly --standalone -d cctv.example.com \
    --agree-tos -m you@example.com --non-interactive

# Copy certs into the path the compose nginx expects
sudo mkdir -p infra/nginx/certs
sudo cp /etc/letsencrypt/live/cctv.example.com/fullchain.pem infra/nginx/certs/
sudo cp /etc/letsencrypt/live/cctv.example.com/privkey.pem  infra/nginx/certs/
sudo chown -R $USER:$USER infra/nginx/certs

# Bring the stack up with the TLS reverse-proxy
docker compose --profile production up -d
```

Set up auto-renewal:

```cron
# sudo crontab -e
0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/cctv.example.com/fullchain.pem /home/ubuntu/AI_CCTV/infra/nginx/certs/ && cp /etc/letsencrypt/live/cctv.example.com/privkey.pem /home/ubuntu/AI_CCTV/infra/nginx/certs/ && cd /home/ubuntu/AI_CCTV && docker compose --profile production restart nginx
```

## 6. Day-2 operations

```bash
# Update to latest main
cd ~/AI_CCTV
git pull
docker compose up -d --build
docker compose exec backend python manage.py migrate --noinput

# Tail logs
docker compose logs -f backend celery_worker celery_beat cv_worker

# Restart a single service
docker compose restart backend

# Backup database
mkdir -p ~/backups
docker compose exec -T db pg_dump -U cctv cctv | gzip > ~/backups/cctv-$(date +%F).sql.gz

# Restore
gunzip -c ~/backups/cctv-2026-05-01.sql.gz | docker compose exec -T db psql -U cctv cctv
```

Automate backups:

```cron
# crontab -e
0 3 * * * cd /home/ubuntu/AI_CCTV && docker compose exec -T db pg_dump -U cctv cctv | gzip > /home/ubuntu/backups/cctv-$(date +\%F).sql.gz && find /home/ubuntu/backups -mtime +14 -delete
```

Ship the backup folder to S3 with `aws s3 sync ~/backups s3://your-bucket/cctv/`
(using an IAM role attached to the instance — never long-lived access keys).

## 7. Optional: local Ollama for AI summaries

If you want LLM features without paying an external API:

```bash
docker compose --profile local-ai up -d ollama
docker compose exec ollama ollama pull llama3.1:8b
```

In the dashboard → **Settings → AI Settings**, set:

- Provider type: **Local Ollama**
- Base URL: `http://ollama:11434/v1`
- Model name: `llama3.1:8b`
- API key: _leave blank_

The compose file binds Ollama to `127.0.0.1:11434` on the host — it is
**not reachable from the public internet**.

## 8. Troubleshooting

| Symptom | Command | Fix |
|---|---|---|
| Backend won't start | `docker compose logs backend` | Most often `FIELD_ENCRYPTION_KEY` empty in `.env` |
| `entrypoint.sh: not found` | `file backend/entrypoint.sh` | CRLF line endings — `git add --renormalize . && git commit` |
| `502 Bad Gateway` from nginx | `docker compose ps`, `docker compose logs nginx` | Backend not healthy yet, or TLS cert path wrong |
| Cameras stuck "unknown" | `docker compose logs cv_worker` | RTSP URL wrong / firewall blocking / camera offline |
| Celery tasks never run | `docker compose logs celery_worker` | Redis unreachable, check `REDIS_URL` |
| AI summary always says "AI is disabled" | Settings → AI → reconfigure | `is_active=False` or wrong base URL |
| Migrations need to run | `docker compose exec backend python manage.py migrate` | After `git pull` that includes new model changes |

## 9. Updating after `git pull`

```bash
git pull
docker compose build
docker compose up -d
docker compose exec backend python manage.py migrate --noinput
docker compose exec backend python manage.py collectstatic --noinput
```

## 10. Rolling back

```bash
git checkout <previous-good-sha>
docker compose build
docker compose up -d
# If a bad migration shipped, restore the most recent pg_dump BEFORE running migrate.
```

## 11. Scaling beyond a single VPS

- Move Postgres to RDS, Redis to ElastiCache. Update `DATABASE_URL` / `REDIS_URL`.
- Run multiple `backend` replicas behind nginx. Keep `celery_beat` as a
  singleton.
- Move `cv_worker` to a dedicated GPU instance (swap base image to
  `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`, run with `--gpus all`).
- Add Loki/CloudWatch for centralised logging. Add Prometheus + Grafana for
  metrics.

## 12. Pre-flight before going live

Walk through every item in [SECURITY.md](SECURITY.md), then:

```bash
docker compose exec backend python manage.py check --deploy
docker compose exec backend pip list --outdated
docker compose exec backend python manage.py test -v 2
```
