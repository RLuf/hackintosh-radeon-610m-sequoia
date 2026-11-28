#!/bin/bash
# Compila e liga os kexts dos marcos M1, M2 e M3 do porte da Radeon 610M e gera a BIOS de vídeo.
# Roda no Deepin 25 da máquina (host pop25), FORA do ambiente isolado. Usa ~/fzdrv/entrar.sh.
# Pré-requisitos, já montados em 19/11/2026: /mnt/dados/fzwork com build-root, src/rembrandt
# (com MacKernelSDK, Lilu 1.7.2 e build/cctools), src/fw-host e a cópia de docs/.
# Uso: bash /mnt/dados/fzwork/docs/porte-610m/setup/build-marcos.sh
set -eu
W=/mnt/dados/fzwork
P=$W/docs/porte-610m/patches
E=$(ls -d "$W"/evidencias/linux-amdgpu-* | tail -1)
for f in "$P"/0001-m1-probe-1002-1506.patch "$P"/0002-m2-identidade-e-vbios.patch "$P"/0003-m3-firmware-e-gc.patch "$E"/VFCT.bin; do
  [ -f "$f" ] || { echo "falta $f"; exit 1; }
done
rm -rf "$W/src/patches" && mkdir -p "$W/src/patches" "$W/out"
cp "$P"/000[123]-*.patch "$W/src/patches/"
cp "$E/VFCT.bin" "$W/src/VFCT.bin"

cat > "$W/src/build-marcos-in.sh" <<'INNER'
#!/bin/bash
# Parte que roda dentro do ambiente isolado (/work = /mnt/dados/fzwork/src).
set -eu
cd /work
rm -rf mendocino && git clone -q rembrandt mendocino && cd mendocino
ln -s /work/rembrandt/src/MacKernelSDK src/MacKernelSDK
ln -s /work/rembrandt/src/Lilu-1.7.2 src/Lilu-1.7.2
mkdir -p build && ln -s /work/rembrandt/build/cctools build/cctools
mkdir -p /work/out-kexts
n=0
for p in /work/patches/0001-*.patch /work/patches/0002-*.patch /work/patches/0003-*.patch; do
  n=$((n+1))
  git -c user.name=fzmac -c user.email=noreply@example.invalid am -q "$p"
  echo "== M$n: $(git log -1 --format='%h %s')"
  make -C src/RembrandtGfx clean >/dev/null 2>&1 || true
  # No M1 e no M2 o firmware embutido ainda é o conjunto original; o M3 troca para o da 610M (FWSET=mendocino).
  make -C src/RembrandtGfx FWSRC=/work/fw-host > "/work/m$n-build.log" 2>&1 || { echo "FALHOU M$n"; tail -15 "/work/m$n-build.log"; exit 1; }
  file src/RembrandtGfx/RembrandtGfx | cut -c1-90
  rm -rf "/work/out-kexts/RembrandtGfx-M$n.kext"
  cp -r src/RembrandtGfx/RembrandtGfx.kext "/work/out-kexts/RembrandtGfx-M$n.kext"
  sha256sum "/work/out-kexts/RembrandtGfx-M$n.kext/Contents/MacOS/RembrandtGfx" | cut -c1-64 | tee "/work/out-kexts/RembrandtGfx-M$n.sha256"
  llvm-nm -u src/RembrandtGfx/RembrandtGfx | sort -u > "/work/m$n-nm-u.txt"
done
echo "== BIOS de vídeo (scripts do M2 em diante)"
rm -rf /work/roms-tmp && mkdir -p /work/roms-tmp && cd /work/roms-tmp
python3 -I /work/mendocino/scripts/vfct-rom.py /work/VFCT.bin
python3 -I /work/mendocino/scripts/augment-rom.py roms/610m-73ff.rom roms/610m-73ff-aug.rom --vram-mb 2048
sha256sum roms/*.rom
INNER
chmod +x "$W/src/build-marcos-in.sh"
~/fzdrv/entrar.sh 'bash /work/build-marcos-in.sh'

for n in 1 2 3; do rm -rf "$W/out/RembrandtGfx-M$n.kext"; cp -r "$W/src/out-kexts/RembrandtGfx-M$n.kext" "$W/out/"; cp "$W/src/out-kexts/RembrandtGfx-M$n.sha256" "$W/out/"; done
rm -rf "$W/out/roms" && cp -r "$W/src/roms-tmp/roms" "$W/out/roms"
echo "== pronto em $W/out"; ls -la "$W/out" | awk '{print $5, $9}'
echo "Valores esperados da BIOS de vídeo (medidos na nuvem com a mesma VFCT):"
echo "  610m.rom          4886598af7cba02ace0ce54d7ecf973f9a323887e4ca4d7eb974fb1ee0171bec"
echo "  610m-73ff.rom     41fcfa0c489f5933be378fe8f8dda6971683ee6c0a4237748c3f31c3403fa5a3"
echo "  610m-73ff-aug.rom d4080aa35f9fd4dfbc70a5e52d4498f8ff121d5ca8f7fac20d8008137c4fdb5c"
