#!/bin/bash
# Um ciclo sem mãos do experimento de vídeo da 610M:
#   confere a EFI -> arma UM boot pela EFI/OCX -> reinicia -> o serviço de captura guarda o log e volta ao boot normal.
# Não grava nada em EFI/OC nem em EFI/OCX. O boot de experimento vale para um boot só.
# Uso: FZPW=<senha do sudo> bash fz-ciclo.sh [segundos de espera, padrão 180] [--reiniciar|--sem-reiniciar] [--sem-captura]
set -u
: "${FZPW:?defina FZPW com a senha do sudo}"
FZ=/Users/rluft/fzdrv
A=$FZ/auto
ESPERA=${1:-180}
REINICIAR=1; [ "${2:-}" = "--sem-reiniciar" ] && REINICIAR=0
OCG=4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102
EFIUUID=A664EFC6-4915-4FD7-9704-3FE79ADAED97
s() { echo "$FZPW" | sudo -S "$@" 2>&1 | sed 's/^Password://'; }
desarma() { s nvram -d "$OCG:OCBtNext" >/dev/null; rm -f "$A/captura.armada" "$A/retomar.armada"; }

echo "== 1. conferência da EFI"
s diskutil mount "$EFIUUID" | tail -1
MP=$(diskutil info "$EFIUUID" | sed -n 's/^ *Mount Point: *//p')
[ "$MP" = /Volumes/EFI ] || { echo "ABORTADO: a EFI $EFIUUID montou em '$MP', não em /Volumes/EFI (outra EFI com o mesmo nome?)"; [ -n "$MP" ] && s diskutil unmount "$EFIUUID" | tail -1; exit 1; }
python3 -I - /Volumes/EFI/EFI "$A" <<'PY'
import hashlib, plistlib, sys, os
efi, a = sys.argv[1], sys.argv[2]
ok = True
def falha(m):
    global ok; ok = False; print('  FALHA:', m)
def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
esperado = {
    'FZAUTO/OpenShell.efi': '6ea28271b19d610e77fe9f7717479a4daff1d26ffdd33cfbc8995a3a9c3bca58',
    'FZAUTO/OpenControl.efi': 'eef3c7a091fd1f635e6c736835ea97f87ec51470815f1842f188af3ecc3d45d7',
    'FZAUTO/startup.nsh': hashlib.sha256(open(os.path.join(a, 'fzauto-startup.nsh'), 'rb').read().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')).hexdigest(),
}
for rel, h in esperado.items():
    p = os.path.join(efi, rel)
    if not os.path.isfile(p): falha(rel + ' ausente')
    elif sha(p) != h: falha(rel + ' com hash diferente')
    else: print('  ok', rel)
GPU = 'PciRoot(0x1)/Pci(0x8,0x1)/Pci(0x0,0x0)'
def le(nome):
    c = plistlib.load(open(os.path.join(efi, nome, 'config.plist'), 'rb'))
    args = c['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82'].get('boot-args', '').split()
    gpu = c['DeviceProperties']['Add'].get(GPU, {})
    kexts = [e['BundlePath'] for e in c['Kernel']['Add'] if e.get('Enabled')]
    return args, gpu, kexts
def limpa(nome):
    args, gpu, kexts = le(nome)
    if any('rmb' in x for x in args): falha('EFI/' + nome + ' tem argumento rmb: ' + ' '.join(args))
    if 'device-id' in gpu or 'ATY,bin_image' in gpu: falha('EFI/' + nome + ' tem identidade falsa na GPU')
    if 'RembrandtGfx.kext' in kexts: falha('EFI/' + nome + ' tem o RembrandtGfx')
    if ok: print('  ok EFI/' + nome + ' limpa')
def comdriver(nome):
    args, gpu, kexts = le(nome)
    est = [x for x in args if x.startswith('rmbstage')]
    print('  EFI/' + nome + ':', ' '.join(est) or 'sem rmbstage', '| device-id', gpu.get('device-id', b'').hex() or 'ausente', '| ROM', len(gpu.get('ATY,bin_image', b'')), 'bytes')
    if '-rmbnoprobe' in args: falha('EFI/' + nome + ' tem -rmbnoprobe')
    if 'RembrandtGfx.kext' not in kexts: falha('EFI/' + nome + ' sem o RembrandtGfx')
    tem_id = 'device-id' in gpu
    if tem_id and est not in (['rmbstage=2'], ['rmbstage=3']): falha('identidade falsa sem rmbstage=2 ou 3 exato')
    if not tem_id and est not in ([], ['rmbstage=1']): falha('rmbstage acima de 1 sem identidade falsa')
# Desde 26/11 23:53 (pedido de Roger Luft) o driver e o boot padrao: EFI/OC tem o driver e o boot normal
# antigo esta em EFI/OC-NORMAL. Nesse modo a OC passa pelas travas da OCX e a OC-NORMAL tem de estar limpa.
if os.path.isdir(os.path.join(efi, 'OC-NORMAL')):
    print('  modo driver permanente (EFI/OC-NORMAL existe)')
    comdriver('OC'); limpa('OC-NORMAL')
else:
    limpa('OC')
comdriver('OCX')
sys.exit(0 if ok else 1)
PY
RC=$?
s diskutil unmount /Volumes/EFI | tail -1
[ $RC -eq 0 ] || { echo "ABORTADO: a EFI não está no estado esperado. Nada foi armado."; exit 1; }

echo "== 2. serviços"
CAPTURA=0
if [ -f /Library/LaunchDaemons/com.fz.expcaptura.plist ] && [ -x /usr/local/fz/fz-exp-captura.sh ]; then
  cmp -s "$A/fz-exp-captura.sh" /usr/local/fz/fz-exp-captura.sh || { echo "ABORTADO: o roteiro de captura instalado difere do de $A."; exit 1; }
  CAPTURA=1; echo "  ok captura instalada: o experimento guarda o log e volta sozinho ao boot normal"
else
  echo "  AVISO: serviço de captura NÃO instalado (só Roger Luft instala). O boot de experimento vai ficar ligado, sem tela,"
  echo "         até alguém reiniciar por SSH (ssh rluft@<ip> e sudo shutdown -r now) ou pelo botão de energia."
  [ "${3:-}" = "--sem-captura" ] || { echo "ABORTADO: para seguir assim mesmo, passe --sem-captura como terceiro argumento."; exit 1; }
fi

echo "== 3. opção de boot de uso único"
ESPERADO=$(python3 -I - <<'PY'
import struct
def ucs2(s): return s.encode('utf-16le') + b'\x00\x00'
hd = bytes.fromhex('04012A00' '01000000' '0008000000000000' '0060090000000000' 'C6EF64A61549D74F97043FE79ADAED97' '0202')
p = ucs2('\\EFI\\FZAUTO\\OpenShell.efi')
dp = hd + bytes([4, 4]) + struct.pack('<H', 4 + len(p)) + p + bytes.fromhex('7FFF0400')
print((struct.pack('<IH', 1, len(dp)) + ucs2('fzauto experimento de video') + dp).hex())
PY
)
ENC=$(echo "$ESPERADO" | sed 's/../%&/g')
[ $CAPTURA -eq 1 ] && echo "$ESPERA" > "$A/captura.armada"
[ -f "$HOME/Library/LaunchAgents/com.fz.retomar.plist" ] && : > "$A/retomar.armada"
s nvram "$OCG:OCBt0F2B=$ENC"
s nvram "$OCG:OCBtNext=%2b%0f"

echo "== 4. leitura do que foi gravado"
LIDO_OPT=$(nvram "$OCG:OCBt0F2B" 2>/dev/null | cut -f2-)
LIDO_NEXT=$(nvram "$OCG:OCBtNext" 2>/dev/null | cut -f2-)
python3 -I - "$ESPERADO" "$LIDO_OPT" "$LIDO_NEXT" <<'PY'
import sys
def dec(s):
    out = bytearray(); i = 0
    while i < len(s):
        if s[i] == '%': out.append(int(s[i+1:i+3], 16)); i += 3
        else: out.append(ord(s[i])); i += 1
    return bytes(out)
a = dec(sys.argv[2]) == bytes.fromhex(sys.argv[1])
b = dec(sys.argv[3]) == b'\x2b\x0f'
print('  OCBt0F2B confere:', a, '| OCBtNext = 0F2B:', b)
sys.exit(0 if a and b else 1)
PY
if [ $? -ne 0 ]; then desarma; echo "ABORTADO: a leitura não bate com o que foi gravado. Desarmado."; exit 1; fi

if [ $REINICIAR -eq 0 ]; then echo "Armado, sem reiniciar. Para desarmar: sudo nvram -d $OCG:OCBtNext"; exit 0; fi
echo "== 5. reiniciando em 10 segundos. Sequência esperada: menu do OpenCore (10 s) -> shell fzauto -> reinício -> menu da EFI/OCX (10 s) -> seq1581 no experimento -> captura -> reinício -> boot normal."
sleep 10
s shutdown -r now
