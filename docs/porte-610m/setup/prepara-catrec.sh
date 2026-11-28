#!/bin/bash
# Recompila o driver de vídeo com todos os patches e deixa no CATREC o que o sistema novo precisa:
# kext, patches, ferramentas e o pacote do Wi-Fi USB MediaTek (MT7601U, 148f:7601).
# O CATREC é a partição FAT do SSD, visível nos dois sistemas (15.8.3 e 15.8.1).
# Uso: bash setup/prepara-catrec.sh   (de dentro da pasta que tem patches, setup e tools-fzmacinstall)
set -euo pipefail
P=$(cd "$(dirname "$0")/.." && pwd)
C=/Volumes/CATREC/fzmac
[ -d "$C" ] || { echo "CATREC não está montado"; exit 1; }
bash "$P/setup/build-mac.sh" "$P/patches" 2>&1 | tail -8
D=$C/porte-610m
rm -rf "$D/kext-5patches" "$D/patches" "$D/setup" "$D/tools-fzmacinstall"
mkdir -p "$D/kext-5patches"
cp -R ~/fzdrv/out/RembrandtGfx.kext ~/fzdrv/out/RembrandtGfx.sha256 "$D/kext-5patches/"
cp -R "$P/patches" "$P/setup" "$P/tools-fzmacinstall" "$D/"
mkdir -p "$C/wifi"
cd "$C/wifi"
api=https://api.github.com/repos/chris1111/D-LinkUtility-Package/releases/tags/V11
for u in $(curl -fsSL "$api" | awk -F'"' '/browser_download_url/{print $4}'); do
  echo "baixando $u"
  curl -fsSLO "$u"
done
ls -la "$C/wifi" "$D/kext-5patches"
df -h /Volumes/CATREC | tail -1
