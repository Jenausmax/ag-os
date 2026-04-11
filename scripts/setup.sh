#!/usr/bin/env bash
# AG-OS installer for Linux / macOS / WSL2
# Интерактивный установщик: выбор между native host и docker-режимом.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="/data/ag-os"

color() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
info()  { echo "$(color '1;36' '[info]') $*"; }
ok()    { echo "$(color '1;32' '[ ok ]') $*"; }
warn()  { echo "$(color '1;33' '[warn]') $*"; }
err()   { echo "$(color '1;31' '[err ]') $*" >&2; }

detect_os() {
    local uname_s
    uname_s="$(uname -s)"
    case "$uname_s" in
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        Darwin*) echo "macos" ;;
        *) echo "unknown" ;;
    esac
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        err "Требуется команда: $1"
        return 1
    fi
}

ensure_data_dirs() {
    local dirs=("$DATA_ROOT/workspaces" "$DATA_ROOT/shared" "$DATA_ROOT/db")
    local need_sudo=0
    for d in "${dirs[@]}"; do
        if [ ! -d "$d" ] && ! mkdir -p "$d" 2>/dev/null; then
            need_sudo=1
            break
        fi
    done
    if [ "$need_sudo" -eq 1 ]; then
        info "Создаю $DATA_ROOT/* через sudo..."
        sudo mkdir -p "${dirs[@]}"
        sudo chown -R "$USER":"$(id -gn)" "$DATA_ROOT"
    fi
    touch "$DATA_ROOT/db/ag-os.db"
    ok "Директории данных готовы: $DATA_ROOT"
}

install_native() {
    info "Режим: native host"
    local os="$1"

    if [ "$os" = "macos" ]; then
        require_cmd brew || { err "Установи Homebrew: https://brew.sh"; exit 1; }
        brew list tmux >/dev/null 2>&1 || brew install tmux
        brew list python@3.11 >/dev/null 2>&1 || brew install python@3.11
    else
        require_cmd apt-get || { err "Поддерживается только apt-based дистрибутив"; exit 1; }
        info "Ставлю tmux и python3.11 через apt..."
        sudo apt-get update
        sudo apt-get install -y tmux python3.11 python3.11-venv python3-pip
    fi

    require_cmd claude || warn "Claude Code CLI не найден. Установи: npm install -g @anthropic-ai/claude-code"

    ensure_data_dirs

    info "Создаю venv в $PROJECT_ROOT/.venv"
    python3.11 -m venv "$PROJECT_ROOT/.venv"
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$PROJECT_ROOT/requirements.txt"

    ok "Native-установка завершена"
    cat <<EOF

Дальше:
  1. Заполни config.yaml (telegram.token, allowed_users, guard.haiku_api_key)
  2. Залогинься в Claude Code:  claude login
  3. Запусти:
       source .venv/bin/activate
       python main.py bot   --config config.yaml
       python main.py tui   --config config.yaml
       python main.py all   --config config.yaml
EOF
}

install_docker() {
    info "Режим: docker"
    require_cmd docker || { err "Установи Docker: https://docs.docker.com/engine/install/"; exit 1; }
    if ! docker compose version >/dev/null 2>&1; then
        err "Требуется Docker Compose v2 ('docker compose')"
        exit 1
    fi

    ensure_data_dirs

    info "Собираю образ агентов (Dockerfile.agent → ag-os-full:latest)..."
    docker build -f "$PROJECT_ROOT/Dockerfile.agent" -t ag-os-full:latest "$PROJECT_ROOT"

    info "Собираю образ приложения (Dockerfile.app → ag-os:latest)..."
    (cd "$PROJECT_ROOT" && docker compose build)

    ok "Docker-установка завершена"
    cat <<EOF

Дальше:
  1. Заполни config.yaml (telegram.token, allowed_users, guard.haiku_api_key)
  2. Залогинься в Claude Code (один раз, интерактивно):
       docker compose run --rm ag-os claude login
  3. Запусти:
       docker compose up -d ag-os                              # бот в фоне
       docker compose run --rm ag-os python main.py tui ...    # TUI
       docker compose logs -f ag-os                            # логи
EOF
}

main() {
    local os
    os="$(detect_os)"
    info "Обнаружена ОС: $os"

    case "$os" in
        linux|wsl|macos) ;;
        *) err "Неподдерживаемая ОС. Используй Linux, macOS или WSL2."; exit 1 ;;
    esac

    echo
    echo "Выбери режим установки:"
    echo "  1) native  — установка на текущую машину (tmux + python venv)"
    echo "  2) docker  — всё в контейнере (AG-OS + sub-агенты через socket mount)"
    echo
    read -rp "Режим [1/2]: " mode

    case "$mode" in
        1) install_native "$os" ;;
        2) install_docker ;;
        *) err "Неверный выбор"; exit 1 ;;
    esac
}

main "$@"
