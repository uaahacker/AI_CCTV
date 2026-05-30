#!/usr/bin/env bash
# AI CCTV Analytics — one-line installer
#
#   curl -fsSL https://raw.githubusercontent.com/UbaidUllah/AI_CCTV/main/install.sh | bash
#
# What it does:
#   1. Checks/installs Docker + Docker Compose plugin (Debian/Ubuntu, RHEL/Fedora,
#      or via the official get.docker.com convenience script).
#   2. Clones (or updates) the repository to $INSTALL_DIR (default /opt/ai-cctv).
#   3. Runs an interactive first-time wizard that asks for:
#        - public host / domain (or IP)
#        - admin email + password (becomes Django superuser)
#        - optional AI provider + API key
#        - optional SMTP credentials
#      and auto-generates SECRET_KEY, FIELD_ENCRYPTION_KEY, POSTGRES_PASSWORD.
#   4. Writes .env, builds + starts the stack with `docker compose up -d`.
#   5. Runs migrations and creates the Django superuser non-interactively.
#   6. Prints the URL to open in your browser.
#
# Environment variables (skip the wizard, useful for CI / automation):
#   INSTALL_DIR=/opt/ai-cctv
#   REPO_URL=https://github.com/UbaidUllah/AI_CCTV.git
#   REPO_BRANCH=main
#   NONINTERACTIVE=1
#   PUBLIC_HOST=cctv.example.com
#   ADMIN_EMAIL=admin@example.com
#   ADMIN_PASSWORD=...           # if unset and NONINTERACTIVE=1, a random one is generated
#   ENABLE_TLS=0                 # 1 = start the production nginx profile
#
# Re-running this script is safe: it will update the repo and re-apply migrations
# without overwriting an existing .env (use --reconfigure to force the wizard).
#
# Copyright (c) 2026 Ubaid Ullah <ubaidawan244@gmail.com> — MIT License.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/ai-cctv}"
REPO_URL="${REPO_URL:-https://github.com/UbaidUllah/AI_CCTV.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
NONINTERACTIVE="${NONINTERACTIVE:-0}"
RECONFIGURE=0

for arg in "$@"; do
  case "$arg" in
    --reconfigure) RECONFIGURE=1 ;;
    --noninteractive) NONINTERACTIVE=1 ;;
    --dir=*) INSTALL_DIR="${arg#*=}" ;;
    --branch=*) REPO_BRANCH="${arg#*=}" ;;
    --repo=*) REPO_URL="${arg#*=}" ;;
    -h|--help)
      sed -n '2,40p' "$0" 2>/dev/null || true
      exit 0 ;;
  esac
done

# ---------- pretty output ----------
if [ -t 1 ]; then
  C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_RESET=$'\033[0m'
else
  C_BOLD=""; C_DIM=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_RESET=""
fi
say()  { printf '%s==>%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s!! %s%s\n'  "$C_YELLOW" "$*" "$C_RESET"; }
die()  { printf '%sxx %s%s\n'  "$C_RED" "$*" "$C_RESET" >&2; exit 1; }
hr()   { printf '%s%s%s\n' "$C_DIM" "----------------------------------------" "$C_RESET"; }

banner() {
cat <<'EOF'

   _____ ____   _________________   __
  /  _  \   |  \\_   ___ \_   ___\ /  |_ __  __
 /  /_\  \  |  //    \  \//    \  \\   __\  \/ /
/    |    \    /\     \___\     \___|  |  \   /
\____|__  /____/  \______  /\______  /__|   \_/
        \/                \/        \/
   AI CCTV Analytics — installer
EOF
}

# ---------- root / sudo handling ----------
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    die "This script needs root privileges. Re-run as root or install sudo."
  fi
else
  SUDO=""
fi

# ---------- Docker install ----------
ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    say "Docker $(docker --version | awk '{print $3}' | tr -d ,) already installed."
    return
  fi
  say "Installing Docker (this may take a minute)…"
  if ! curl -fsSL https://get.docker.com -o /tmp/get-docker.sh; then
    die "Could not download get.docker.com. Install Docker manually and re-run."
  fi
  $SUDO sh /tmp/get-docker.sh
  if ! docker compose version >/dev/null 2>&1; then
    warn "Docker Compose plugin not detected; trying apt fallback…"
    if command -v apt-get >/dev/null 2>&1; then
      $SUDO apt-get update -y
      $SUDO apt-get install -y docker-compose-plugin
    fi
  fi
  if [ -n "$SUDO" ] && id -nG "$USER" | grep -qv docker; then
    $SUDO usermod -aG docker "$USER" || true
    warn "Added $USER to the 'docker' group — you may need to log out and back in."
  fi
}

# ---------- git + clone ----------
ensure_git() {
  if command -v git >/dev/null 2>&1; then return; fi
  say "Installing git…"
  if command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -y && $SUDO apt-get install -y git
  elif command -v dnf >/dev/null 2>&1; then $SUDO dnf install -y git
  elif command -v yum >/dev/null 2>&1; then $SUDO yum install -y git
  elif command -v apk >/dev/null 2>&1; then $SUDO apk add --no-cache git
  else die "Please install git manually and re-run."; fi
}

clone_or_update() {
  $SUDO mkdir -p "$(dirname "$INSTALL_DIR")"
  if [ -d "$INSTALL_DIR/.git" ]; then
    say "Updating existing checkout in $INSTALL_DIR…"
    $SUDO git -C "$INSTALL_DIR" fetch --all --quiet
    $SUDO git -C "$INSTALL_DIR" checkout "$REPO_BRANCH" --quiet
    $SUDO git -C "$INSTALL_DIR" pull --ff-only --quiet
  else
    say "Cloning $REPO_URL → $INSTALL_DIR"
    $SUDO git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
  $SUDO chown -R "$USER":"$(id -gn)" "$INSTALL_DIR" 2>/dev/null || true
}

# ---------- secret generation ----------
gen_secret_urlsafe() {
  # 64-char URL-safe secret
  python3 -c "import secrets;print(secrets.token_urlsafe(64))" 2>/dev/null \
    || openssl rand -base64 64 | tr -d '\n=+/' | cut -c1-64
}
gen_fernet_key() {
  python3 - <<'PY' 2>/dev/null
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except ModuleNotFoundError:
    import base64, secrets
    print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
}
gen_password() {
  python3 -c "import secrets;print(secrets.token_urlsafe(24))" 2>/dev/null \
    || openssl rand -base64 24 | tr -d '\n=+/' | cut -c1-24
}

# ---------- wizard ----------
prompt() {
  local var="$1" message="$2" default="${3:-}" secret="${4:-0}" answer=""
  if [ "$NONINTERACTIVE" = "1" ]; then
    eval "$var=\"${!var:-$default}\""
    return
  fi
  if [ -n "$default" ]; then
    printf '%s%s%s [%s]: ' "$C_BOLD" "$message" "$C_RESET" "$default"
  else
    printf '%s%s%s: ' "$C_BOLD" "$message" "$C_RESET"
  fi
  if [ "$secret" = "1" ]; then
    stty -echo 2>/dev/null || true
    IFS= read -r answer
    stty echo 2>/dev/null || true
    echo
  else
    IFS= read -r answer
  fi
  if [ -z "$answer" ] && [ -n "$default" ]; then answer="$default"; fi
  eval "$var=\"\$answer\""
}

run_wizard() {
  hr
  echo "${C_BOLD}First-time setup wizard${C_RESET}"
  echo "  Press Enter to accept defaults shown in [brackets]."
  hr

  local detected_ip
  detected_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -z "$detected_ip" ] && detected_ip="localhost"

  PUBLIC_HOST="${PUBLIC_HOST:-}"
  prompt PUBLIC_HOST "Public hostname or IP (no scheme)" "$detected_ip"

  ENABLE_TLS="${ENABLE_TLS:-0}"
  if [ "$NONINTERACTIVE" != "1" ]; then
    printf '%sEnable HTTPS (nginx + your own certs)? (y/N): %s' "$C_BOLD" "$C_RESET"
    IFS= read -r _yn; case "$_yn" in y|Y|yes) ENABLE_TLS=1 ;; *) ENABLE_TLS=0 ;; esac
  fi

  ADMIN_EMAIL="${ADMIN_EMAIL:-}"
  prompt ADMIN_EMAIL "Admin email (will be your Django superuser)" "admin@${PUBLIC_HOST}"

  ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
  if [ -z "$ADMIN_PASSWORD" ]; then
    if [ "$NONINTERACTIVE" = "1" ]; then
      ADMIN_PASSWORD="$(gen_password)"
      warn "Generated random admin password: $ADMIN_PASSWORD  (save it now)"
    else
      prompt ADMIN_PASSWORD "Admin password (leave blank to auto-generate)" "" 1
      if [ -z "$ADMIN_PASSWORD" ]; then
        ADMIN_PASSWORD="$(gen_password)"
        warn "Generated random admin password: $ADMIN_PASSWORD  (save it now)"
      fi
    fi
  fi

  AI_PROVIDER=""
  AI_API_KEY=""
  AI_MODEL=""
  if [ "$NONINTERACTIVE" != "1" ]; then
    printf '%sConfigure an AI provider now? (y/N): %s' "$C_BOLD" "$C_RESET"
    IFS= read -r _yn
    if [ "$_yn" = "y" ] || [ "$_yn" = "Y" ]; then
      echo "  1) OpenRouter   2) OpenAI   3) Local Ollama   4) Self-hosted (OpenAI-compat)"
      prompt _ai "Choose 1-4" "1"
      case "$_ai" in
        1) AI_PROVIDER=openrouter; AI_MODEL="meta-llama/llama-3.1-8b-instruct";;
        2) AI_PROVIDER=openai;     AI_MODEL="gpt-4o-mini";;
        3) AI_PROVIDER=ollama;     AI_MODEL="llama3.1:8b";;
        4) AI_PROVIDER=custom;     AI_MODEL="";;
      esac
      if [ "$AI_PROVIDER" != "ollama" ]; then
        prompt AI_API_KEY "API key for ${AI_PROVIDER}" "" 1
      fi
    fi
  fi

  SMTP_HOST=""; SMTP_USER=""; SMTP_PASS=""; SMTP_FROM=""
  if [ "$NONINTERACTIVE" != "1" ]; then
    printf '%sConfigure SMTP for email alerts now? (y/N): %s' "$C_BOLD" "$C_RESET"
    IFS= read -r _yn
    if [ "$_yn" = "y" ] || [ "$_yn" = "Y" ]; then
      prompt SMTP_HOST "SMTP host" "smtp.gmail.com"
      prompt SMTP_USER "SMTP username" "$ADMIN_EMAIL"
      prompt SMTP_PASS "SMTP password / app password" "" 1
      prompt SMTP_FROM "From: address" "$ADMIN_EMAIL"
    fi
  fi
}

write_env() {
  local env_file="$INSTALL_DIR/.env"
  if [ -f "$env_file" ] && [ "$RECONFIGURE" != "1" ]; then
    warn "Existing .env found — keeping it. Pass --reconfigure to overwrite."
    return
  fi

  local SECRET_KEY FIELD_ENCRYPTION_KEY POSTGRES_PASSWORD
  SECRET_KEY="$(gen_secret_urlsafe)"
  FIELD_ENCRYPTION_KEY="$(gen_fernet_key)"
  POSTGRES_PASSWORD="$(gen_password)"

  local origin="http://${PUBLIC_HOST}"
  [ "$ENABLE_TLS" = "1" ] && origin="https://${PUBLIC_HOST}"

  say "Writing $env_file"
  cat > "$env_file" <<EOF
# Auto-generated by install.sh on $(date -u +%FT%TZ)
# Do not commit this file. Re-run install.sh --reconfigure to regenerate.

DEBUG=False
SECRET_KEY=${SECRET_KEY}
FIELD_ENCRYPTION_KEY=${FIELD_ENCRYPTION_KEY}
ALLOWED_HOSTS=${PUBLIC_HOST},localhost,127.0.0.1,backend
CSRF_TRUSTED_ORIGINS=${origin}
CORS_ALLOWED_ORIGINS=${origin}
FRONTEND_BASE_URL=${origin}

POSTGRES_DB=cctv
POSTGRES_USER=cctv
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATABASE_URL=postgres://cctv:${POSTGRES_PASSWORD}@db:5432/cctv

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Privacy & compliance
PRIVACY_BLUR_FACES=True
PRIVACY_FACIAL_RECOGNITION_ENABLED=False
CONSENT_TERMS_VERSION=1.0

# Email
EMAIL_BACKEND=$( [ -n "$SMTP_HOST" ] && echo "django.core.mail.backends.smtp.EmailBackend" || echo "django.core.mail.backends.console.EmailBackend" )
EMAIL_HOST=${SMTP_HOST}
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=${SMTP_USER}
EMAIL_HOST_PASSWORD=${SMTP_PASS}
DEFAULT_FROM_EMAIL=${SMTP_FROM:-no-reply@${PUBLIC_HOST}}

# SMS (Twilio) — fill these in to enable SMS channel
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM=

# AI provider (optional — can also be set per-org from the UI)
AI_PROVIDER=${AI_PROVIDER}
AI_API_KEY=${AI_API_KEY}
AI_MODEL=${AI_MODEL}

# CV worker
DETECTOR=dummy
FRAME_INTERVAL_SECONDS=2
EOF
  chmod 600 "$env_file"
}

# ---------- bring up the stack ----------
start_stack() {
  cd "$INSTALL_DIR"
  say "Building Docker images (first run can take a few minutes)…"
  if [ "$ENABLE_TLS" = "1" ]; then
    docker compose --profile production build
  else
    docker compose build
  fi
  say "Starting services…"
  if [ "$ENABLE_TLS" = "1" ]; then
    docker compose --profile production up -d
  else
    docker compose up -d
  fi
}

wait_for_backend() {
  say "Waiting for backend to become healthy…"
  for i in $(seq 1 60); do
    if docker compose exec -T backend python -c "import django;print(django.get_version())" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  die "Backend did not start within ~2 minutes — check 'docker compose logs backend'."
}

run_migrations_and_superuser() {
  cd "$INSTALL_DIR"
  say "Applying database migrations…"
  docker compose exec -T backend python manage.py migrate --noinput
  say "Creating / updating admin user ${ADMIN_EMAIL}…"
  docker compose exec -T \
    -e DJANGO_SUPERUSER_EMAIL="$ADMIN_EMAIL" \
    -e DJANGO_SUPERUSER_PASSWORD="$ADMIN_PASSWORD" \
    backend python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model
User = get_user_model()
email = os.environ["DJANGO_SUPERUSER_EMAIL"]
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]
user, created = User.objects.get_or_create(email=email)
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.set_password(password)
user.save()
print(("Created" if created else "Updated"), "superuser:", email)
PY
}

print_done() {
  local origin="http://${PUBLIC_HOST}"
  [ "$ENABLE_TLS" = "1" ] && origin="https://${PUBLIC_HOST}"
  hr
  printf '%sInstallation complete!%s\n\n' "$C_GREEN$C_BOLD" "$C_RESET"
  printf '  Dashboard:     %s\n' "$origin"
  printf '  Admin email:   %s\n' "$ADMIN_EMAIL"
  printf '  Admin password: %s\n' "${ADMIN_PASSWORD:-<the one you typed>}"
  printf '  API docs:      %s/api/docs/\n' "$origin"
  printf '  Install dir:   %s\n' "$INSTALL_DIR"
  echo
  echo "Useful commands:"
  echo "  cd $INSTALL_DIR && docker compose ps"
  echo "  cd $INSTALL_DIR && docker compose logs -f backend cv_worker celery_worker"
  echo "  cd $INSTALL_DIR && docker compose down            # stop"
  echo "  cd $INSTALL_DIR && docker compose pull && docker compose up -d   # update"
  hr
  warn "Save the admin password above. It is NOT stored anywhere recoverable."
  if [ "$ENABLE_TLS" = "1" ]; then
    warn "TLS profile is enabled — drop your fullchain.pem + privkey.pem in $INSTALL_DIR/infra/nginx/certs/ and run 'docker compose --profile production restart nginx'."
  fi
}

main() {
  banner
  ensure_git
  ensure_docker
  clone_or_update
  run_wizard
  write_env
  start_stack
  wait_for_backend
  run_migrations_and_superuser
  print_done
}

main "$@"
