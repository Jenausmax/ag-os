# AG-OS installer for Windows
# Проверяет WSL2 и Docker Desktop, маршрутизирует установку.

$ErrorActionPreference = "Stop"

function Write-Info($msg)  { Write-Host "[info] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[ ok ] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "[warn] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "[err ] $msg" -ForegroundColor Red }

function Test-Command($name) {
    $null = Get-Command $name -ErrorAction SilentlyContinue
    return $?
}

function Test-Wsl2 {
    if (-not (Test-Command "wsl")) { return $false }
    try {
        $output = wsl --status 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Test-DockerDesktop {
    if (-not (Test-Command "docker")) { return $false }
    try {
        docker info *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

Write-Info "AG-OS Windows installer"
Write-Host ""
Write-Info "На Windows AG-OS не запускается нативно (требуется tmux)."
Write-Info "Варианты: WSL2 (нативный Linux внутри Windows) или Docker Desktop."
Write-Host ""

$hasWsl = Test-Wsl2
$hasDocker = Test-DockerDesktop

if ($hasWsl)    { Write-Ok "WSL2 обнаружен" }    else { Write-Warn "WSL2 не обнаружен" }
if ($hasDocker) { Write-Ok "Docker Desktop обнаружен" } else { Write-Warn "Docker Desktop не обнаружен" }
Write-Host ""

if (-not $hasWsl -and -not $hasDocker) {
    Write-Err "Нет ни WSL2, ни Docker Desktop. Установи один из них:"
    Write-Host "  WSL2:           wsl --install"
    Write-Host "  Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
}

Write-Host "Выбери режим установки:"
$options = @()
if ($hasWsl)    { $options += "1"; Write-Host "  1) WSL2   — запустить scripts/setup.sh внутри WSL (native или docker внутри WSL)" }
if ($hasDocker) { $options += "2"; Write-Host "  2) docker — docker compose прямо на Windows (Docker Desktop)" }
Write-Host ""
$mode = Read-Host "Режим"

switch ($mode) {
    "1" {
        if (-not $hasWsl) { Write-Err "WSL2 недоступен"; exit 1 }
        $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
        $wslPath = wsl wslpath -u ($projectRoot -replace '\\', '/')
        Write-Info "Передаю управление WSL..."
        wsl bash -c "cd $wslPath && bash scripts/setup.sh"
    }
    "2" {
        if (-not $hasDocker) { Write-Err "Docker Desktop недоступен"; exit 1 }
        $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
        Push-Location $projectRoot
        try {
            Write-Info "Собираю образ агентов..."
            docker build -f Dockerfile.agent -t ag-os-full:latest .
            Write-Info "Собираю образ приложения..."
            docker compose build
            Write-Ok "Готово."
            Write-Host ""
            Write-Host "Дальше:"
            Write-Host "  1. Заполни config.yaml"
            Write-Host "  2. docker compose run --rm ag-os claude login"
            Write-Host "  3. docker compose up -d ag-os"
            Write-Warn "На Windows пути /data/ag-os/* в compose не сработают напрямую —"
            Write-Warn "отредактируй docker-compose.yml под свои хостовые пути, либо используй WSL2."
        } finally {
            Pop-Location
        }
    }
    default { Write-Err "Неверный выбор"; exit 1 }
}
