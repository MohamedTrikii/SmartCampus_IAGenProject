<#
.SYNOPSIS
  Arrête SmartCampus AI (base, Ollama, backend, scheduler, frontend). Les données sont conservées.

.EXAMPLE
  .\arreter.ps1              # arrête les services (redémarrage rapide avec .\demarrer.ps1)
  .\arreter.ps1 -Supprimer   # arrête et supprime les conteneurs (libère de la mémoire ; données conservées)
  .\arreter.ps1 -Docker      # arrête aussi Docker Desktop (libère toute la mémoire du PC)
#>
param(
    [switch]$Supprimer,
    [switch]$Docker
)

# "Continue" : sous PowerShell 5.1, un simple avertissement de docker sur stderr deviendrait sinon une erreur
# bloquante. Les échecs sont contrôlés explicitement ($LASTEXITCODE).
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step([string]$text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok([string]$text) { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn([string]$text) { Write-Host "    $text" -ForegroundColor Yellow }

$composeFiles = @("-f", "docker-compose.yml")
if (Test-Path "docker-compose.gpu.yml") { $composeFiles += @("-f", "docker-compose.gpu.yml") }

# ------------------------------------------------------------------ 1. Docker démarré ?
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Ok "Docker n'est pas démarré : SmartCampus AI est déjà arrêté."
    exit 0
}

# ------------------------------------------------------------------ 2. arrêt des services
if ($Supprimer) {
    Write-Step "Arrêt et suppression des conteneurs (les données sont conservées)"
    & docker compose @composeFiles down
} else {
    Write-Step "Arrêt des services"
    & docker compose @composeFiles stop
}
if ($LASTEXITCODE -ne 0) {
    Write-Warn "docker compose a signalé une erreur. Vérifiez avec : docker compose ps"
    exit 1
}
Write-Ok "Services arrêtés : base de données, Ollama, backend, scheduler, frontend."
Write-Ok "Données conservées : comptes, conversations, catalogue et modèles téléchargés."

# ------------------------------------------------------------------ 3. Docker Desktop (option)
if ($Docker) {
    Write-Step "Arrêt de Docker Desktop"
    Get-Process "Docker Desktop" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    & wsl --shutdown 2>$null
    Write-Ok "Docker Desktop arrêté (mémoire libérée)."
}

Write-Host ""
Write-Host "SmartCampus AI est arrêté." -ForegroundColor Green
Write-Host "  Relancer : demarrer.bat"
