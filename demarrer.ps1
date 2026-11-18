<#
.SYNOPSIS
  Lance SmartCampus AI en local avec Docker (base, Ollama, backend, scheduler, frontend).

.EXAMPLE
  .\demarrer.ps1                    # LLM réel si le modèle de .env est installé, sinon LLM simulé
  .\demarrer.ps1 -Modele gemma2:2b  # LLM réel avec ce modèle (téléchargé si absent)
  .\demarrer.ps1 -Fake              # LLM simulé : réponses instantanées, idéal pour montrer l'interface
  .\demarrer.ps1 -Gpu               # active le GPU NVIDIA pour Ollama (docker-compose.gpu.yml)
  .\demarrer.ps1 -Synchro           # relance la synchronisation du catalogue depuis les sites officiels
  .\demarrer.ps1 -Arreter           # arrête tous les services (les données sont conservées)
#>
param(
    [string]$Modele = "",
    [switch]$Fake,
    [switch]$Gpu,
    [switch]$Synchro,
    [switch]$Arreter
)

# "Continue" : sous PowerShell 5.1, un simple avertissement de docker sur stderr deviendrait sinon une erreur
# bloquante. Les échecs sont contrôlés explicitement ($LASTEXITCODE, throw).
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step([string]$text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok([string]$text) { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn([string]$text) { Write-Host "    $text" -ForegroundColor Yellow }

$composeFiles = @("-f", "docker-compose.yml")
if ($Gpu) { $composeFiles += @("-f", "docker-compose.gpu.yml") }

function Invoke-Compose {
    & docker compose @composeFiles @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($args -join ' ') a échoué" }
}

# ------------------------------------------------------------------ .env (fichier local, jamais commité)
function Get-EnvValue([string]$key) {
    $line = Get-Content ".env" | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
    if ($line) { return $line.Substring($key.Length + 1).Trim() }
    return ""
}

function Set-EnvValue([string]$key, [string]$value) {
    $lines = [System.Collections.Generic.List[string]](Get-Content ".env")
    $index = $lines.FindIndex([Predicate[string]] { param($l) $l -match "^$key=" })
    if ($index -ge 0) { $lines[$index] = "$key=$value" } else { $lines.Add("$key=$value") }
    # UTF-8 sans BOM : lisible par docker compose et par pydantic-settings
    [System.IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), $lines, (New-Object System.Text.UTF8Encoding $false))
}

# ------------------------------------------------------------------ arrêt
if ($Arreter) {
    Write-Step "Arrêt des services"
    Invoke-Compose stop
    Write-Ok "Services arrêtés. Données conservées (volumes Docker). Relancer : .\demarrer.ps1"
    exit 0
}

# ------------------------------------------------------------------ 1. Docker
Write-Step "Vérification de Docker"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $desktop)) { throw "Docker Desktop est introuvable : installez-le puis relancez ce script." }
    Write-Warn "Docker n'est pas démarré : lancement de Docker Desktop (1 à 2 minutes)..."
    Start-Process $desktop
    $deadline = (Get-Date).AddMinutes(4)
    do {
        Start-Sleep -Seconds 5
        docker info *> $null
    } while ($LASTEXITCODE -ne 0 -and (Get-Date) -lt $deadline)
    if ($LASTEXITCODE -ne 0) { throw "Docker ne répond pas après 4 minutes." }
}
Write-Ok "Docker est prêt."

# ------------------------------------------------------------------ 2. .env
Write-Step "Configuration (.env)"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    Set-EnvValue "JWT_SECRET" ([Convert]::ToBase64String($bytes))
    Write-Ok ".env créé depuis .env.example (JWT_SECRET aléatoire)."
} else {
    Write-Ok ".env existant conservé."
}

# ------------------------------------------------------------------ 3. services
Write-Step "Construction et démarrage des services (la 1re fois : 5 à 10 minutes)"
Invoke-Compose up -d --build db ollama
Write-Ok "Base de données et Ollama démarrés."

# ------------------------------------------------------------------ 4. choix du LLM
Write-Step "Choix du modèle de langage"
function Test-ModelInstalled([string]$name) {
    $list = & docker compose @composeFiles exec -T ollama ollama list 2>$null
    $tag = if ($name.Contains(":")) { $name } else { "$name`:latest" }
    return [bool]($list | Where-Object { $_ -match "^$([regex]::Escape($tag))\s" })
}

# attendre qu'Ollama réponde
$deadline = (Get-Date).AddMinutes(2)
do {
    Start-Sleep -Seconds 2
    & docker compose @composeFiles exec -T ollama ollama list *> $null
} while ($LASTEXITCODE -ne 0 -and (Get-Date) -lt $deadline)

if ($Fake) {
    Set-EnvValue "LLM_PROVIDER" "fake"
    Write-Ok "LLM simulé (-Fake) : réponses instantanées « [fake-llm] ... »."
} else {
    $target = if ($Modele) { $Modele } else { Get-EnvValue "LLM_MODEL" }
    if (-not (Test-ModelInstalled $target) -and $Modele) {
        Write-Warn "Téléchargement du modèle $target (peut prendre plusieurs minutes)..."
        & docker compose @composeFiles exec -T ollama ollama pull $target
    }
    if (Test-ModelInstalled $target) {
        Set-EnvValue "LLM_PROVIDER" "openai"
        Set-EnvValue "LLM_MODEL" $target
        Set-EnvValue "LLM_TIMEOUT_S" "600"  # sur CPU, une réponse peut prendre plusieurs minutes
        Write-Ok "LLM réel : $target (via Ollama). Sur CPU : quelques secondes avec un modèle 3B, plusieurs minutes avec un 7B ou plus."
    } else {
        Set-EnvValue "LLM_PROVIDER" "fake"
        Write-Warn "Modèle '$target' non installé : LLM simulé utilisé pour cette démo."
        Write-Warn "Pour un vrai modèle : .\demarrer.ps1 -Modele qwen2.5:3b"
    }
}

Invoke-Compose up -d --build --force-recreate backend scheduler frontend
Write-Ok "Backend, scheduler et frontend démarrés."

# ------------------------------------------------------------------ 5. attente du backend
Write-Step "Attente du backend (migrations + seed au démarrage)"
$deadline = (Get-Date).AddMinutes(3)
$ready = $false
do {
    Start-Sleep -Seconds 3
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 3 -ErrorAction Stop
        $ready = $health.status -eq "ok"
    } catch { $ready = $false }
} while (-not $ready -and (Get-Date) -lt $deadline)
if (-not $ready) {
    Write-Warn "Le backend ne répond pas encore. Logs : docker compose logs backend"
    exit 1
}
Write-Ok "Backend prêt."

# ------------------------------------------------------------------ 6. catalogue
function Get-ProgramCount {
    # PowerShell 5.1 renvoie un tableau JSON comme UN objet : on le déroule dans le pipeline avant de compter
    $result = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/programs" -TimeoutSec 10 -ErrorAction Stop
    return ($result | ForEach-Object { $_ } | Measure-Object).Count
}
$count = Get-ProgramCount
if ($Synchro -or $count -eq 0) {
    Write-Step "Synchronisation du catalogue depuis les sites officiels (1 requête/s, ~10 minutes)"
    Invoke-Compose exec -T backend python -m scripts.sync_sites
    $count = Get-ProgramCount
}
Write-Ok "$count formations dans le catalogue."

# ------------------------------------------------------------------ 7. prêt
$deadline = (Get-Date).AddMinutes(2)
do {
    Start-Sleep -Seconds 2
    try { $front = (Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop).StatusCode } catch { $front = 0 }
} while ($front -ne 200 -and (Get-Date) -lt $deadline)

$adminEmail = Get-EnvValue "ADMIN_EMAIL"
$adminPassword = Get-EnvValue "ADMIN_PASSWORD"
Write-Host ""
Write-Host "SmartCampus AI est lancé" -ForegroundColor Green
Write-Host "  Application (chat)  : http://localhost:3000"
Write-Host "  API (Swagger)       : http://localhost:8000/docs   (Authorize : $adminEmail / $adminPassword)"
Write-Host "  LLM                 : $(Get-EnvValue 'LLM_PROVIDER') $(if ((Get-EnvValue 'LLM_PROVIDER') -ne 'fake') { Get-EnvValue 'LLM_MODEL' })"
Write-Host "  Arrêter             : .\demarrer.ps1 -Arreter"
Write-Host "  Logs                : docker compose logs -f backend"
Start-Process "http://localhost:3000"
