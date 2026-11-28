#!/bin/bash
# Arma o teste do estágio 1 no experimento (EFI/OCX) com o kext de 5 patches que está no CATREC
# e dispara, em segundo plano, a instalação das ferramentas de linha de comando da Apple.
# A senha do sudo entra pela variável FZPW. Nada de senha neste arquivo.
# Uso: FZPW=... bash arma-estagio1-1581.sh
set -u
: "${FZPW:?defina FZPW com a senha do sudo}"
EFIUUID=A664EFC6-4915-4FD7-9704-3FE79ADAED97
ESPERA=4599e05abc50e423263eba3c040578f06bdad858f1e6dd8f22a6ec242462f2b4
APPLE=7C436110-AB2A-4BBB-A880-FE41995C9F82
echo "$FZPW" | sudo -S diskutil mount "$EFIUUID" 2>&1 | tail -1
E=/Volumes/EFI/EFI
ls "$E" 2>&1 | tr '\n' ' '; echo
K=$E/OCX/Kexts/RembrandtGfx.kext
N=/Volumes/CATREC/fzmac/porte-610m/kext-5patches/RembrandtGfx.kext
if [ -d "$K" ] && [ -d "$N" ]; then
  echo "antes:  $(shasum -a 256 "$K/Contents/MacOS/RembrandtGfx" | cut -c1-64)"
  B="$HOME/fzdrv/ocx-kext-antes-$(date +%Y%m%d-%H%M)"
  mkdir -p "$HOME/fzdrv"
  cp -R "$K" "$B" && echo "copia em $B"
  sudo rm -rf "$K" && sudo cp -R "$N" "$E/OCX/Kexts/" && sudo find "$K" -name "._*" -delete
  echo "depois: $(shasum -a 256 "$K/Contents/MacOS/RembrandtGfx" | cut -c1-64)"
  echo "espera: $ESPERA"
else
  echo "FALTA: OCX=$([ -d "$K" ] && echo ok || echo nao) CATREC=$([ -d "$N" ] && echo ok || echo nao)"
fi
echo "boot-args OCX: $(/usr/libexec/PlistBuddy -c "Print :NVRAM:Add:$APPLE:boot-args" "$E/OCX/config.plist" 2>&1)"
echo "boot-args OC:  $(/usr/libexec/PlistBuddy -c "Print :NVRAM:Add:$APPLE:boot-args" "$E/OC/config.plist" 2>&1)"
ls "$E/OC/Tools" 2>&1 | tr '\n' ' '; echo
sudo diskutil unmount /Volumes/EFI 2>&1 | tail -1
cat > "$HOME/fzdrv/instala-clt-1581.sh" <<'X'
#!/bin/bash
touch /tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress
L=$(softwareupdate -l 2>&1 | grep -E "Label: Command Line Tools" | sed 's/^.*Label: //' | sort -V | tail -1)
echo "rotulo: $L"
[ -n "$L" ] && echo "$FZPW" | sudo -S softwareupdate -i "$L" --verbose 2>&1 | tail -20
rm -f /tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress
xcode-select -p 2>&1
echo "FIM-CLT $(date)"
X
FZPW="$FZPW" nohup bash "$HOME/fzdrv/instala-clt-1581.sh" > "$HOME/fzdrv/instala-clt.log" 2>&1 &
echo "CLT em segundo plano, log em ~/fzdrv/instala-clt.log"
