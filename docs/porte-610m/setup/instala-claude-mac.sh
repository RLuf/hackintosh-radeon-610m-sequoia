#!/bin/bash
# Instala o Claude Code (CLI) no macOS, para trabalhar direto na máquina, sem ponte.
# Usa o instalador oficial, que grava o binário em ~/.local/bin/claude.
# Uso: bash instala-claude-mac.sh
set -u
curl -fsSL https://claude.ai/install.sh | bash 2>&1 | tail -15
if ! grep -q '.local/bin' "$HOME/.zshrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
fi
ls -la "$HOME/.local/bin/claude" 2>&1
"$HOME/.local/bin/claude" --version 2>&1 | head -2
