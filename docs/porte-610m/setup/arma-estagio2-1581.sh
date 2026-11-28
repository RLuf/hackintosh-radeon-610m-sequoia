#!/bin/bash
# Arma o estágio 2 no experimento (EFI/OCX): identidade falsa 73ff, BIOS de vídeo aumentada e rmbstage=2.
# As três coisas entram juntas: identidade falsa com rmbstage=1 é a pior combinação (M2-NOTAS, seção 7).
# Guarda cópia do config.plist do experimento antes. A EFI/OC normal não é tocada.
# Uso: FZPW=... bash arma-estagio2-1581.sh          arma o estágio 2
#      FZPW=... bash arma-estagio2-1581.sh voltar   devolve o config.plist guardado (estágio 1)
set -u
: "${FZPW:?defina FZPW com a senha do sudo}"
EFIUUID=A664EFC6-4915-4FD7-9704-3FE79ADAED97
ROM=/Volumes/CATREC/fzmac/porte-610m/roms/610m-73ff-aug.rom
ROMSUM=d4080aa35f9fd4dfbc70a5e52d4498f8ff121d5ca8f7fac20d8008137c4fdb5c
GUARDA="$HOME/fzdrv/ocx-config-estagio1.plist"
echo "$FZPW" | sudo -S diskutil mount "$EFIUUID" 2>&1 | tail -1
CFG=/Volumes/EFI/EFI/OCX/config.plist
if [ "${1:-}" = "voltar" ]; then
  [ -f "$GUARDA" ] || { echo "sem copia guardada em $GUARDA"; sudo diskutil unmount /Volumes/EFI | tail -1; exit 1; }
  sudo cp "$GUARDA" "$CFG" && echo "config.plist do estagio 1 devolvido"
else
  S=$(shasum -a 256 "$ROM" 2>/dev/null | cut -c1-64)
  if [ "$S" != "$ROMSUM" ]; then
    echo "BIOS de video nao confere: $S"; sudo diskutil unmount /Volumes/EFI | tail -1; exit 1
  fi
  [ -f "$GUARDA" ] || cp "$CFG" "$GUARDA"
  cp "$CFG" "$HOME/fzdrv/ocx-config-antes-$(date +%Y%m%d-%H%M).plist"
  cp "$CFG" /tmp/ocx-config.plist
  python3 - "$ROM" <<'PY'
import plistlib, sys
p = '/tmp/ocx-config.plist'
c = plistlib.load(open(p, 'rb'))
d = c['DeviceProperties']['Add'].setdefault('PciRoot(0x1)/Pci(0x8,0x1)/Pci(0x0,0x0)', {})
d['device-id'] = bytes.fromhex('FF730000')
d['ATY,bin_image'] = open(sys.argv[1], 'rb').read()
d['CFG_NO_BOOT_PWDN'] = bytes.fromhex('0100000000000000')
d['CFG_USE_AGDC'] = bytes(8)
d['model'] = 'AMD Radeon RX 6600'
nv = c['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']
args = [a for a in nv['boot-args'].split() if not a.startswith('rmbstage=')]
args.append('rmbstage=2')
nv['boot-args'] = ' '.join(args)
plistlib.dump(c, open(p, 'wb'))
PY
  plutil -lint /tmp/ocx-config.plist && sudo cp /tmp/ocx-config.plist "$CFG"
fi
python3 - "$CFG" <<'PY'
import plistlib, sys
c = plistlib.load(open(sys.argv[1], 'rb'))
d = c['DeviceProperties']['Add'].get('PciRoot(0x1)/Pci(0x8,0x1)/Pci(0x0,0x0)', {})
print('device-id:', d.get('device-id', b'').hex() or 'ausente', '| BIOS de video:', len(d.get('ATY,bin_image', b'')), 'bytes | model:', d.get('model', 'ausente'))
print('boot-args:', c['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args'])
k = [e['BundlePath'] for e in c['Kernel']['Add'] if e.get('Enabled')]
print('kexts:', ' '.join(k))
PY
echo "kext do experimento: $(shasum -a 256 /Volumes/EFI/EFI/OCX/Kexts/RembrandtGfx.kext/Contents/MacOS/RembrandtGfx | cut -c1-64)"
sudo diskutil unmount /Volumes/EFI 2>&1 | tail -1
