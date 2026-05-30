<#
.SYNOPSIS
    AI CCTV Analytics — one-line installer for Windows hosts with Docker Desktop.

.DESCRIPTION
    iwr -useb https://raw.githubusercontent.com/uaahacker/AI_CCTV/main/install.ps1 | iex

    1. Verifies Docker Desktop is installed and running.
    2. Clones (or updates) the repo to $InstallDir (default $env:USERPROFILE\AI_CCTV).
    3. Runs an interactive wizard: public host, admin email/password, optional AI key, optional SMTP.
    4. Auto-generates SECRET_KEY, FIELD_ENCRYPTION_KEY, POSTGRES_PASSWORD.
    5. Writes .env, runs `docker compose up -d`, applies migrations, creates the superuser.

.PARAMETER InstallDir
    Where to clone the repo. Default: $env:USERPROFILE\AI_CCTV

.PARAMETER Reconfigure
    Overwrite an existing .env and re-run the wizard.

.PARAMETER NonInteractive
    Skip the wizard. Required env vars: PUBLIC_HOST, ADMIN_EMAIL. Auto-generates admin password if missing.

.NOTES
    Copyright (c) 2026 Ubaid Ullah <ubaidawan244@gmail.com> — MIT License.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'AI_CCTV'),
    [string]$RepoUrl    = 'https://github.com/uaahacker/AI_CCTV.git',
    [string]$Branch     = 'main',
    [switch]$Reconfigure,
    [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'

function Say  ($m) { Write-Host "==> $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "!!  $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "xx  $m" -ForegroundColor Red; exit 1 }
function Hr   ()   { Write-Host ('-' * 60) -ForegroundColor DarkGray }

function Ensure-Command ($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { Die "$name not found. $hint" }
}

function Ensure-Docker {
    Ensure-Command docker 'Install Docker Desktop from https://www.docker.com/products/docker-desktop and start it.'
    try { docker info | Out-Null } catch { Die 'Docker daemon not running. Open Docker Desktop and wait until the whale icon is steady.' }
    try { docker compose version | Out-Null } catch { Die "'docker compose' subcommand missing. Update Docker Desktop." }
    Say "Docker is ready: $((docker --version) -replace 'Docker version ','')"
}

function Clone-Or-Update {
    Ensure-Command git 'Install Git from https://git-scm.com/download/win and re-run.'
    if (Test-Path (Join-Path $InstallDir '.git')) {
        Say "Updating existing checkout in $InstallDir"
        git -C $InstallDir fetch --all --quiet
        git -C $InstallDir checkout $Branch --quiet
        git -C $InstallDir pull --ff-only --quiet
    } else {
        Say "Cloning $RepoUrl into $InstallDir"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $InstallDir) | Out-Null
        git clone --branch $Branch --depth 1 $RepoUrl $InstallDir
    }
}

function New-Secret([int]$Bytes = 48) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buf = New-Object byte[] $Bytes
    $rng.GetBytes($buf)
    return [Convert]::ToBase64String($buf).TrimEnd('=').Replace('+','-').Replace('/','_')
}
function New-FernetKey {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buf = New-Object byte[] 32
    $rng.GetBytes($buf)
    return [Convert]::ToBase64String($buf).Replace('+','-').Replace('/','_')
}

function Ask([string]$Message, [string]$Default = '', [switch]$Secret) {
    if ($NonInteractive) { return $Default }
    if ($Default) { $prompt = "$Message [$Default]" } else { $prompt = $Message }
    if ($Secret) {
        $ss = Read-Host -Prompt $prompt -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
        try { $val = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
        finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    } else {
        $val = Read-Host -Prompt $prompt
    }
    if ([string]::IsNullOrEmpty($val) -and $Default) { return $Default }
    return $val
}
function AskYn([string]$Message, [bool]$Default = $false) {
    if ($NonInteractive) { return $Default }
    $suffix = if ($Default) { '(Y/n)' } else { '(y/N)' }
    $r = Read-Host "$Message $suffix"
    if ([string]::IsNullOrEmpty($r)) { return $Default }
    return $r -match '^(y|Y|yes)$'
}

function Run-Wizard {
    Hr
    Write-Host 'First-time setup wizard' -ForegroundColor Cyan
    Write-Host '  Press Enter to accept defaults shown in [brackets].'
    Hr

    $detected = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                 Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
                 Select-Object -First 1 -ExpandProperty IPAddress)
    if (-not $detected) { $detected = 'localhost' }

    $global:PUBLIC_HOST      = if ($env:PUBLIC_HOST)      { $env:PUBLIC_HOST }      else { Ask 'Public hostname or IP (no scheme)' $detected }
    $global:ENABLE_TLS       = AskYn 'Enable HTTPS (you provide certs in infra/nginx/certs/)?' $false
    $global:ADMIN_EMAIL      = if ($env:ADMIN_EMAIL)      { $env:ADMIN_EMAIL }      else { Ask 'Admin email (becomes Django superuser)' "admin@$global:PUBLIC_HOST" }
    $global:ADMIN_PASSWORD   = if ($env:ADMIN_PASSWORD)   { $env:ADMIN_PASSWORD }   else { Ask 'Admin password (blank = auto-generate)' '' -Secret }
    if ([string]::IsNullOrEmpty($global:ADMIN_PASSWORD)) {
        $global:ADMIN_PASSWORD = New-Secret 18
        Warn "Generated random admin password: $global:ADMIN_PASSWORD  (save it now)"
    }

    $global:AI_PROVIDER = ''; $global:AI_API_KEY = ''; $global:AI_MODEL = ''
    if (AskYn 'Configure an AI provider now?' $false) {
        Write-Host '  1) OpenRouter   2) OpenAI   3) Local Ollama   4) Self-hosted (OpenAI-compat)'
        $choice = Ask 'Choose 1-4' '1'
        switch ($choice) {
            '1' { $global:AI_PROVIDER='openrouter'; $global:AI_MODEL='meta-llama/llama-3.1-8b-instruct' }
            '2' { $global:AI_PROVIDER='openai';     $global:AI_MODEL='gpt-4o-mini' }
            '3' { $global:AI_PROVIDER='ollama';     $global:AI_MODEL='llama3.1:8b' }
            '4' { $global:AI_PROVIDER='custom';     $global:AI_MODEL='' }
        }
        if ($global:AI_PROVIDER -ne 'ollama') {
            $global:AI_API_KEY = Ask "API key for $global:AI_PROVIDER" '' -Secret
        }
    }

    $global:SMTP_HOST=''; $global:SMTP_USER=''; $global:SMTP_PASS=''; $global:SMTP_FROM=''
    if (AskYn 'Configure SMTP for email alerts now?' $false) {
        $global:SMTP_HOST = Ask 'SMTP host' 'smtp.gmail.com'
        $global:SMTP_USER = Ask 'SMTP username' $global:ADMIN_EMAIL
        $global:SMTP_PASS = Ask 'SMTP password / app password' '' -Secret
        $global:SMTP_FROM = Ask 'From: address' $global:ADMIN_EMAIL
    }
}

function Write-Env {
    $envFile = Join-Path $InstallDir '.env'
    if ((Test-Path $envFile) -and (-not $Reconfigure)) {
        Warn "Existing .env found — keeping it. Re-run with -Reconfigure to overwrite."
        return
    }
    Say "Writing $envFile"

    $secretKey  = New-Secret 64
    $fernetKey  = New-FernetKey
    $dbPassword = New-Secret 24
    $origin     = if ($global:ENABLE_TLS) { "https://$global:PUBLIC_HOST" } else { "http://$global:PUBLIC_HOST" }
    $emailBackend = if ($global:SMTP_HOST) { 'django.core.mail.backends.smtp.EmailBackend' } else { 'django.core.mail.backends.console.EmailBackend' }
    $defaultFrom  = if ($global:SMTP_FROM) { $global:SMTP_FROM } else { "no-reply@$global:PUBLIC_HOST" }

    @"
# Auto-generated by install.ps1 on $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ' -AsUTC)
# Do not commit this file.

DEBUG=False
SECRET_KEY=$secretKey
FIELD_ENCRYPTION_KEY=$fernetKey
ALLOWED_HOSTS=$global:PUBLIC_HOST,localhost,127.0.0.1,backend
CSRF_TRUSTED_ORIGINS=$origin
CORS_ALLOWED_ORIGINS=$origin
FRONTEND_BASE_URL=$origin

POSTGRES_DB=cctv
POSTGRES_USER=cctv
POSTGRES_PASSWORD=$dbPassword
DATABASE_URL=postgres://cctv:$dbPassword@db:5432/cctv

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

PRIVACY_BLUR_FACES=True
PRIVACY_FACIAL_RECOGNITION_ENABLED=False
CONSENT_TERMS_VERSION=1.0

EMAIL_BACKEND=$emailBackend
EMAIL_HOST=$global:SMTP_HOST
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=$global:SMTP_USER
EMAIL_HOST_PASSWORD=$global:SMTP_PASS
DEFAULT_FROM_EMAIL=$defaultFrom

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM=

AI_PROVIDER=$global:AI_PROVIDER
AI_API_KEY=$global:AI_API_KEY
AI_MODEL=$global:AI_MODEL

DETECTOR=yolo
FRAME_INTERVAL_SECONDS=2
"@ | Set-Content -Encoding ASCII $envFile
}

function Start-Stack {
    Push-Location $InstallDir
    try {
        Say 'Building Docker images (first run may take a few minutes)…'
        if ($global:ENABLE_TLS) { docker compose --profile production build } else { docker compose build }
        Say 'Starting services…'
        if ($global:ENABLE_TLS) { docker compose --profile production up -d } else { docker compose up -d }
    } finally { Pop-Location }
}

function Wait-Backend {
    Say 'Waiting for backend to become healthy…'
    Push-Location $InstallDir
    try {
        for ($i = 0; $i -lt 60; $i++) {
            try {
                docker compose exec -T backend python -c "import django;print(django.get_version())" | Out-Null
                return
            } catch { Start-Sleep -Seconds 2 }
        }
        Die "Backend did not start within ~2 minutes — run 'docker compose logs backend'."
    } finally { Pop-Location }
}

function Apply-Migrations-And-Admin {
    Push-Location $InstallDir
    try {
        Say 'Generating app migrations…'
        docker compose exec -T backend python manage.py makemigrations --noinput accounts organizations cameras analytics alerts audit ai compliance
        Say 'Applying database migrations…'
        docker compose exec -T backend python manage.py migrate --noinput
        Say "Creating / updating admin user $global:ADMIN_EMAIL…"
        $py = @'
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
'@
        $py | docker compose exec -T `
            -e "DJANGO_SUPERUSER_EMAIL=$global:ADMIN_EMAIL" `
            -e "DJANGO_SUPERUSER_PASSWORD=$global:ADMIN_PASSWORD" `
            backend python manage.py shell
    } finally { Pop-Location }
}

function Print-Done {
    $origin = if ($global:ENABLE_TLS) { "https://$global:PUBLIC_HOST" } else { "http://$global:PUBLIC_HOST" }
    Hr
    Write-Host 'Installation complete!' -ForegroundColor Green
    Write-Host ''
    Write-Host "  Dashboard:      $origin"
    Write-Host "  Admin email:    $global:ADMIN_EMAIL"
    Write-Host "  Admin password: $global:ADMIN_PASSWORD"
    Write-Host "  API docs:       $origin/api/docs/"
    Write-Host "  Install dir:    $InstallDir"
    Write-Host ''
    Write-Host 'Useful commands:'
    Write-Host "  cd $InstallDir; docker compose ps"
    Write-Host "  cd $InstallDir; docker compose logs -f backend cv_worker celery_worker"
    Write-Host "  cd $InstallDir; docker compose down"
    Write-Host "  cd $InstallDir; docker compose pull; docker compose up -d   # update"
    Hr
    Warn 'Save the admin password above. It is NOT stored anywhere recoverable.'
}

# --- main ---
Write-Host ''
Write-Host '   AI CCTV Analytics — installer' -ForegroundColor Cyan
Write-Host ''
Ensure-Docker
Clone-Or-Update
Run-Wizard
Write-Env
Start-Stack
Wait-Backend
Apply-Migrations-And-Admin
Print-Done
