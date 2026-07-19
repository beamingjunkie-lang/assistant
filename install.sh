#!/usr/bin/env bash
# Install the complete assistant in an isolated Python environment.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${AI_ASSISTANT_VENV:-$REPO_DIR/.venv}"
BIN_DIR="${HOME}/.local/bin"
COMMAND_PATH="${BIN_DIR}/ai-assistant"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required. Install it with your system package manager.\n' >&2
  exit 1
fi

if ! python3 -m venv "$VENV_DIR"; then
  printf 'Could not create a virtual environment.\n' >&2
  printf 'On Debian, Kali, or Ubuntu install the venv support first:\n' >&2
  printf '  sudo apt install python3-venv\n' >&2
  exit 1
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install --upgrade "$REPO_DIR[full]"

mkdir -p "$BIN_DIR"
if [[ -e "$COMMAND_PATH" && ! -L "$COMMAND_PATH" ]]; then
  printf 'Refusing to replace existing file: %s\n' "$COMMAND_PATH" >&2
  printf 'Run %s/bin/ai-assistant directly, or remove that file yourself.\n' "$VENV_DIR" >&2
  exit 1
fi
ln -sfn "$VENV_DIR/bin/ai-assistant" "$COMMAND_PATH"

printf '\nInstalled the complete assistant.\n'
printf 'Start it with: %s\n' "$COMMAND_PATH"
if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
  printf '\nAdd this directory to PATH, then open a new terminal:\n'
  printf '  echo %q >> ~/.bashrc\n' "export PATH=\"$BIN_DIR:\$PATH\""
fi
