#!/bin/bash
# Compila o driver com todos os patches do contexto e troca o kext do experimento (EFI/OCX) pelo novo.
# Também mostra a configuração do menu do OpenCore e as variáveis de boot que o macOS enxerga.
# A senha do sudo entra pela variável FZPW. Saída curta, para caber na leitura pela ponte.
# Uso: FZPW=... bash compila-e-arma-1581.sh
set -u
: "${FZPW:?defina FZPW com a senha do sudo}"
C="$HOME/fzdrv/contexto/fzmacscript/docs/porte-610m"
EFIUUID=A664EFC6-4915-4FD7-9704-3FE79ADAED97
G=8BE4DF61-93CA-11D2-AA0D-00E098032B8C
PB=/usr/libexec/PlistBuddy
echo "== compilacao"
bash "$C/setup/build-mac.sh" "$C/patches" 2>&1 | tail -4 | cut -c1-150
K="$HOME/fzdrv/out/RembrandtGfx.kext"
[ -d "$K" ] || { echo "sem kext compilado"; exit 1; }
H=$(shasum -a 256 "$K/Contents/MacOS/RembrandtGfx" | cut -c1-64)
echo "$FZPW" | sudo -S diskutil mount "$EFIUUID" 2>&1 | tail -1
E=/Volumes/EFI/EFI
X=$E/OCX/Kexts/RembrandtGfx.kext
B="$HOME/fzdrv/ocx-kext-antes-$(date +%Y%m%d-%H%M)"
echo "antes:     $(shasum -a 256 "$X/Contents/MacOS/RembrandtGfx" | cut -c1-64)"
cp -R "$X" "$B" && echo "copia do anterior em $B"
sudo rm -rf "$X" && sudo cp -R "$K" "$E/OCX/Kexts/" && sudo find "$X" -name "._*" -delete
echo "compilado: $H"
echo "na EFI:    $(shasum -a 256 "$X/Contents/MacOS/RembrandtGfx" | cut -c1-64)"
D=/Volumes/CATREC/fzmac/porte-610m/kext-6patches
rm -rf "$D" && mkdir -p "$D" && cp -R "$K" "$D/" && echo "$H" > "$D/RembrandtGfx.sha256"
echo "== menu do OpenCore"
for c in OC OCX; do
  f="$E/$c/config.plist"
  echo "$c: Timeout=$($PB -c 'Print :Misc:Boot:Timeout' "$f" 2>&1) ShowPicker=$($PB -c 'Print :Misc:Boot:ShowPicker' "$f" 2>&1) BootVarRouting=$($PB -c 'Print :UEFI:Quirks:RequestBootVarRouting' "$f" 2>&1) SetDefault=$($PB -c 'Print :Misc:Security:AllowSetDefault' "$f" 2>&1)"
done
sudo diskutil unmount /Volumes/EFI 2>&1 | tail -1
echo "== variaveis de boot vistas pelo macOS"
nvram "$G:BootCurrent" 2>&1 | cut -c1-90
nvram "$G:BootOrder" 2>&1 | cut -c1-120
nvram "$G:Boot0F2A" 2>&1 | cut -c1-90
nvram -p | grep -i -E 'efi-boot-device	|csr-active' | cut -c1-140
echo "== voz na tela de login"
log show --last 60m --style compact --predicate 'process == "loginwindow"' 2>/dev/null | grep -i -E 'voiceover|accessib' | head -4 | cut -c1-180
pgrep -lf 'VoiceOver|AssistiveControl' | cut -c1-90
