#!/bin/bash
# Leva o USBMap-XHC0.kext de Roger Luft tambem para EFI/OCX (boot de experimento de video).
# O script de Roger Luft (~/fzdrv/usbmap/instala-usbmap-xhc0.sh) instala o mapa so em EFI/OC. Sem o mapa,
# o boot de experimento fica com o Bluetooth Realtek 0bda:c123 na XHC0 PRT2 e o bluetoothd/BlueTool
# reinicia em laco. Este script repete em EFI/OCX a mesma instalacao: mesmo kext, mesma entrada em
# Kernel > Add. Nao toca em EFI/OC, EFI/BOOT nem EFI/FZAUTO, e confere que EFI/OC nao mudou.
#
# Uso:
#   FZPW=... bash instala-usbmap-xhc0-ocx.sh          instala em EFI/OCX
#   FZPW=... bash instala-usbmap-xhc0-ocx.sh voltar   tira o mapa de EFI/OCX
# Teste sem EFI real: FZ_EFI_TESTE=/pasta/EFI FZ_BASE=/pasta bash instala-usbmap-xhc0-ocx.sh
set -u
FZ="${FZ_BASE:-$HOME/fzdrv}"
KEXT_SRC="$FZ/usbmap/USBMap-XHC0.kext"
EFIUUID=A664EFC6-4915-4FD7-9704-3FE79ADAED97
NOME=USBMap-XHC0.kext

if [ -n "${FZ_EFI_TESTE:-}" ]; then
  E="$FZ_EFI_TESTE"
  R=""
  monta() { :; }
  desmonta() { :; }
else
  : "${FZPW:?defina FZPW com a senha do sudo}"
  E=/Volumes/EFI/EFI
  R=sudo
  echo "$FZPW" | sudo -S -v 2>/dev/null || { echo "ERRO: sudo recusou a senha"; exit 1; }
  monta() { sudo diskutil mount "$EFIUUID" | tail -1; }
  desmonta() { sudo diskutil unmount /Volumes/EFI 2>&1 | tail -1; }
fi

lint() {
  python3 -I -c 'import plistlib,sys; plistlib.load(open(sys.argv[1],"rb"))' "$1" 2>/dev/null || return 1
  if command -v plutil >/dev/null 2>&1; then plutil -lint "$1" >/dev/null || return 1; fi
}
falha() { echo "ERRO: $*"; desmonta; exit 1; }

monta
[ -r "$E/OCX/config.plist" ] || falha "nao consegui ler $E/OCX/config.plist"
[ -r "$E/OC/config.plist" ] || falha "nao consegui ler $E/OC/config.plist"
OCSUM=$(shasum -a 256 "$E/OC/config.plist" | cut -c1-64)
TS=$(date +%Y%m%d-%H%M%S)

if [ "${1:-}" = "voltar" ]; then
  cp "$E/OCX/config.plist" "$FZ/ocx-config-antes-tirar-usbmap-$TS.plist" || falha "copia do config"
  TMP=$(mktemp /tmp/ocx-usbmap-XXXXXX)
  cp "$E/OCX/config.plist" "$TMP"
  python3 -I - "$TMP" "$NOME" <<'PY' || falha "edicao do config"
import plistlib, sys
p, nome = sys.argv[1], sys.argv[2]
c = plistlib.load(open(p, "rb"))
antes = len(c["Kernel"]["Add"])
c["Kernel"]["Add"] = [e for e in c["Kernel"]["Add"] if e.get("BundlePath") != nome]
print("  entradas removidas:", antes - len(c["Kernel"]["Add"]))
plistlib.dump(c, open(p, "wb"), sort_keys=False)
PY
  lint "$TMP" || falha "config gerado invalido"
  $R cp "$TMP" "$E/OCX/config.plist" || falha "gravacao do config"
  $R rm -rf "$E/OCX/Kexts/$NOME"
  rm -f "$TMP"
  lint "$E/OCX/config.plist" || falha "config na EFI invalido"
  desmonta
  echo "OK: EFI/OCX sem o mapa de USB. Copia do config anterior: $FZ/ocx-config-antes-tirar-usbmap-$TS.plist"
  exit 0
fi

[ -f "$KEXT_SRC/Contents/Info.plist" ] || falha "$KEXT_SRC/Contents/Info.plist ausente"
lint "$KEXT_SRC/Contents/Info.plist" || falha "Info.plist do mapa invalido"

echo "== 1. Estado de EFI/OC (so leitura)"
python3 -I - "$E/OC/config.plist" "$E/OCX/config.plist" "$NOME" <<'PY' || falha "leitura dos configs"
import plistlib, sys
oc, ocx, nome = plistlib.load(open(sys.argv[1], "rb")), plistlib.load(open(sys.argv[2], "rb")), sys.argv[3]
def modelo(c): return c["PlatformInfo"]["Generic"].get("SystemProductName")
def mapa(c): return [bool(e.get("Enabled")) for e in c["Kernel"]["Add"] if e.get("BundlePath") == nome]
print("  modelo em OC:", modelo(oc), "| em OCX:", modelo(ocx))
print("  mapa em OC > Kernel > Add:", mapa(oc) or "ausente", "| em OCX:", mapa(ocx) or "ausente")
assert modelo(oc) == modelo(ocx), "OC e OCX usam modelos diferentes: o mapa casa por board-id"
PY
[ -d "$E/OC/Kexts/$NOME" ] && echo "  kext em EFI/OC/Kexts: presente" || echo "  kext em EFI/OC/Kexts: AUSENTE"

echo "== 2. Copia de EFI/OCX"
BK="$FZ/ocx-inteira-antes-usbmap-$TS"
cp -R "$E/OCX" "$BK" || falha "copia de EFI/OCX"
diff -rq "$E/OCX" "$BK" >/dev/null || falha "a copia em $BK difere de EFI/OCX. Nada foi alterado."
echo "  ok: $BK"

restaura() {
  echo "RESTAURANDO EFI/OCX a partir de $BK"
  $R cp "$BK/config.plist" "$E/OCX/config.plist"
  [ -d "$BK/Kexts/$NOME" ] || $R rm -rf "$E/OCX/Kexts/$NOME"
  falha "$*"
}

echo "== 3. Instalando em EFI/OCX"
TMP=$(mktemp /tmp/ocx-usbmap-XXXXXX)
cp "$E/OCX/config.plist" "$TMP" || falha "copia do config"
python3 -I - "$TMP" "$NOME" <<'PY' || falha "edicao do config"
import plistlib, sys
p, nome = sys.argv[1], sys.argv[2]
c = plistlib.load(open(p, "rb"))
kadd = c["Kernel"]["Add"]
entry = {
    "Arch": "Any",
    "BundlePath": nome,
    "Comment": "Desabilita XHC0 PRT2 (BT Realtek 0bda:c123) sem tocar no XHC1/hub USB externo",
    "Enabled": True,
    "ExecutablePath": "",
    "MaxKernel": "",
    "MinKernel": "",
    "PlistPath": "Contents/Info.plist",
}
idx = next((i for i, e in enumerate(kadd) if e.get("BundlePath") == nome), None)
if idx is None:
    kadd.append(entry)
    print("  entrada adicionada em Kernel > Add")
else:
    kadd[idx] = entry
    print("  entrada atualizada em Kernel > Add")
plistlib.dump(c, open(p, "wb"), sort_keys=False)
PY
lint "$TMP" || falha "config gerado invalido"
$R rm -rf "$E/OCX/Kexts/$NOME"
$R cp -R "$KEXT_SRC" "$E/OCX/Kexts/$NOME" || restaura "copia do kext"
$R find "$E/OCX/Kexts/$NOME" -name '._*' -delete
$R cp "$TMP" "$E/OCX/config.plist" || restaura "gravacao do config"
rm -f "$TMP"

echo "== 4. Conferencia na EFI"
lint "$E/OCX/config.plist" || restaura "config na EFI invalido"
lint "$E/OCX/Kexts/$NOME/Contents/Info.plist" || restaura "Info.plist do mapa na EFI invalido"
python3 -I - "$BK/config.plist" "$E/OCX/config.plist" "$E/OCX/Kexts/$NOME/Contents/Info.plist" "$NOME" <<'PY' || restaura "conferencia"
import plistlib, sys
antes, depois = plistlib.load(open(sys.argv[1], "rb")), plistlib.load(open(sys.argv[2], "rb"))
kp, nome = plistlib.load(open(sys.argv[3], "rb")), sys.argv[4]
semmapa = lambda c: [e for e in c["Kernel"]["Add"] if e.get("BundlePath") != nome]
assert semmapa(antes) == semmapa(depois), "outras entradas de Kernel > Add mudaram"
a2, d2 = dict(antes), dict(depois)
ka, kd = dict(a2.pop("Kernel")), dict(d2.pop("Kernel"))
ka.pop("Add"); kd.pop("Add")
assert a2 == d2 and ka == kd, "algo fora de Kernel > Add mudou"
m = [e for e in depois["Kernel"]["Add"] if e.get("BundlePath") == nome]
assert len(m) == 1 and m[0]["Enabled"] is True and m[0]["ExecutablePath"] == "" and m[0]["PlistPath"] == "Contents/Info.plist", m
args = depois["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"].get("boot-args", "")
pers = kp["IOKitPersonalities"]
assert list(pers.keys()) == ["iMacPro1,1-XHC0"], list(pers.keys())
p0 = pers["iMacPro1,1-XHC0"]
assert p0["IONameMatch"] == "XHC0" and p0["board-id"] == "Mac-7BA5B2D9E42DDD94"
ports = sorted(p0["IOProviderMergeProperties"]["ports"].keys())
assert ports == ["PRT1", "PRT3"], ports
print("  ok: so a entrada do mapa mudou | portas:", ports)
print("  argumentos de EFI/OCX:", args)
print("  Kernel > Add de EFI/OCX:", ", ".join(("" if e.get("Enabled") else "(desligado) ") + e.get("BundlePath", "?") for e in depois["Kernel"]["Add"]))
PY
[ "$(shasum -a 256 "$E/OC/config.plist" | cut -c1-64)" = "$OCSUM" ] || restaura "EFI/OC/config.plist mudou"
echo "  ok: EFI/OC/config.plist nao mudou"
desmonta
echo "OK: mapa de USB instalado em EFI/OCX. Para tirar: FZPW=... bash $0 voltar"
