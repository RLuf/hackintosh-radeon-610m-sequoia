#!/bin/bash
# Compila o RembrandtGfx portado para a Radeon 610M no próprio macOS, com as ferramentas de linha
# de comando da Apple (clang e ld). Não precisa do ambiente Ubuntu do Deepin.
# Uso: bash build-mac.sh PASTA_DOS_PATCHES
# Saída: ~/fzdrv/out/RembrandtGfx.kext e ~/fzdrv/out/RembrandtGfx.sha256
# O kext sai da árvore com todos os patches. O estágio é escolhido no boot com rmbstage=1, 2 ou 3.
set -eu
P=$(cd "$1" && pwd)
W=~/fzdrv/src
mkdir -p "$W" ~/fzdrv/out
cd "$W"
[ -d rembrandt ] || git clone -q https://github.com/caoshiyuan0211-blip/winmax2-2022-6800u-hackintosh rembrandt
[ -d MacKernelSDK ] || git clone -q https://github.com/acidanthera/MacKernelSDK MacKernelSDK
[ -d Lilu-1.7.2 ] || git clone -q --depth 1 --branch 1.7.2 https://github.com/acidanthera/Lilu Lilu-1.7.2
(cd MacKernelSDK && git checkout -q 3f75008)
rm -rf mendocino
git clone -q rembrandt mendocino
cd mendocino
git checkout -q -B porte 87a01b5
ln -s "$W/MacKernelSDK" src/MacKernelSDK
ln -s "$W/Lilu-1.7.2" src/Lilu-1.7.2
for p in "$P"/[0-9][0-9][0-9][0-9]-*.patch; do
  git -c user.name=fzmac -c user.email=noreply@example.invalid am -q "$p"
done
echo "== árvore"; git log --oneline | head -5
# Firmware da AMD: não vem no repositório. Baixa do linux-firmware só os arquivos que o conjunto pede.
mkdir -p "$W/fw-host"
for b in $(python3 scripts/fw-extract.py --set mendocino --list); do
  [ -s "$W/fw-host/$b" ] || curl -fsSL -o "$W/fw-host/$b" \
    "https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/amdgpu/$b"
done
echo "== firmware"; ls "$W/fw-host" | tr '\n' ' '; echo
make -C src/RembrandtGfx clean >/dev/null 2>&1 || true
if ! make -C src/RembrandtGfx LD=ld FWSRC="$W/fw-host" > "$W/build.log" 2>&1; then
  echo "FALHOU a compilação"; tail -30 "$W/build.log"; exit 1
fi
file src/RembrandtGfx/RembrandtGfx | cut -c1-100
rm -rf ~/fzdrv/out/RembrandtGfx.kext
cp -R src/RembrandtGfx/RembrandtGfx.kext ~/fzdrv/out/
shasum -a 256 ~/fzdrv/out/RembrandtGfx.kext/Contents/MacOS/RembrandtGfx | cut -c1-64 | tee ~/fzdrv/out/RembrandtGfx.sha256
echo "== pronto: ~/fzdrv/out/RembrandtGfx.kext"
