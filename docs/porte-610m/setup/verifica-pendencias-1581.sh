#!/bin/bash
# Fecha as verificações que ficaram em aberto em 22/11/2026. Só leitura: nada é carregado nem alterado.
# Saída curta de propósito, para caber na leitura pela ponte.
K=/Volumes/CATREC/fzmac/porte-610m/kext-5patches/RembrandtGfx.kext
P='process == "WallpaperAgent"'
L='process == "loginwindow"'
echo "== papel: linhas com metal/mtl nas ultimas 12h"
log show --last 12h --style compact --predicate "$P" 2>/dev/null | grep -i -c -E 'metal|mtl'
log show --last 12h --style compact --predicate "$P" 2>/dev/null | grep -i -E 'metal|mtl' | tail -2 | cut -c1-180
echo "== papel: escolha gravada"
I="$HOME/Library/Application Support/com.apple.wallpaper/Store/Index.plist"
plutil -p "$I" 2>&1 | grep -i -E 'Provider|aerial|relative' | sort | uniq -c | head -6 | cut -c1-160
echo "== desbloqueio"
log show --last 12h --style compact --predicate "$L" 2>/dev/null | grep -i -E 'unlock|hang|timed out|timeout' | tail -5 | cut -c1-180
echo "== plano B: o sistema aceitaria o nosso kext pelo mecanismo proprio?"
codesign -dv "$K" 2>&1 | head -2 | cut -c1-160
kextutil -n -t "$K" 2>&1 | tail -6 | cut -c1-200
echo "== git no sistema novo"
git --version 2>&1 | head -1
