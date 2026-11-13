# deploy.ps1 — full deployment of Claude Anonymizer (Python + FastAPI + PostgreSQL)
# Run: right-click -> "Run with PowerShell" or:
# powershell -ExecutionPolicy Bypass -File deploy.ps1

$ErrorActionPreference = "Stop"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Claude Anonymizer - deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

# ---------- 1. Find psql.exe ----------
$PsqlPath = Get-Command psql -ErrorAction SilentlyContinue
if (-not $PsqlPath) {
    Write-Host " psql.exe not found in PATH." -ForegroundColor Yellow
    Write-Host " Enter full path to psql.exe" -ForegroundColor Yellow
    Write-Host " Example: C:\Program Files\PostgreSQL\16\bin\psql.exe" -ForegroundColor Yellow
    $PsqlPath = Read-Host "Path to psql.exe"
    if (-not (Test-Path $PsqlPath)) {
        Write-Host " File not found. Install PostgreSQL and add bin to PATH." -ForegroundColor Red
        exit 1
    }
}

$PgBinDir = Split-Path -Parent $PsqlPath
$env:PATH = "$PgBinDir;$env:PATH"
Write-Host " Found psql: $PsqlPath" -ForegroundColor Green

# ---------- 2. Check Python ----------
Write-Host "`nChecking Python..." -ForegroundColor Cyan
python --version | Out-Host
pip --version | Out-Host

# ---------- 3. Install Python dependencies ----------
Write-Host "`nInstalling Python dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host " Error installing dependencies" -ForegroundColor Red
    exit 1
}

# ---------- 4. Setup .env ----------
Write-Host "`nSetting up .env..." -ForegroundColor Cyan
$EnvFile = Join-Path $ProjectDir ".env"
$EnvContent = @"
CLAUDE_API_KEY=sk-ant-your-key-here
CLAUDE_MODEL=claude-3-haiku-20240307
DATABASE_URL=postgresql://postgres:2912@localhost:5432/claude_anonimizer
APP_SECRET=change-me-secret
LOG_LEVEL=INFO
"@
$EnvContent | Out-File -FilePath $EnvFile -Encoding utf8
Write-Host " .env updated (DATABASE_URL with password 2912)" -ForegroundColor Green

# ---------- 5. Create database and user ----------
Write-Host "`nCreating database and user..." -ForegroundColor Cyan
& $PsqlPath -U postgres -d postgres -c "CREATE DATABASE claude_anonimizer;"
if ($LASTEXITCODE -ne 0) {
    Write-Host " Database may already exist (ignoring)" -ForegroundColor Yellow
}

& $PsqlPath -U postgres -d postgres -c "CREATE USER app_user WITH PASSWORD '2912';"
if ($LASTEXITCODE -ne 0) {
    Write-Host " User may already exist (ignoring)" -ForegroundColor Yellow
}

& $PsqlPath -U postgres -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE claude_anonimizer TO app_user;"

# ---------- 6. Apply schema ----------
Write-Host "`nApplying database schema..." -ForegroundColor Cyan
$InitSql = Join-Path $ProjectDir "init_db.sql"
& $PsqlPath -U app_user -d claude_anonimizer -f $InitSql
if ($LASTEXITCODE -ne 0) {
    Write-Host " Trying as postgres user..." -ForegroundColor Yellow
    & $PsqlPath -U postgres -d claude_anonimizer -f $InitSql
}
Write-Host " Schema applied" -ForegroundColor Green

# ---------- 7. Startup instructions ----------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Deployment completed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " IMPORTANT: Open .env and set your real CLAUDE_API_KEY (Anthropic key)." -ForegroundColor Yellow
Write-Host ""
Write-Host " To start the server, run:" -ForegroundColor Cyan
Write-Host "   cd C:\Users\vlsta\projects\Pithon_anonimizer" -ForegroundColor White
Write-Host "   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor White
Write-Host ""
Write-Host " Then open in browser:" -ForegroundColor Cyan
Write-Host "   http://localhost:8000/ui" -ForegroundColor White
Write-Host ""
