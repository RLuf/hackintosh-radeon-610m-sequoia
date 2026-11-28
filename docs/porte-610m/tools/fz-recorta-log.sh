#!/bin/bash
# Recorta o ÚLTIMO boot do log cumulativo do RembrandtGfx, guarda em ~/fzdrv com estágio, patch
# e sha do kext no nome, e mostra as linhas que decidem o estágio 3. Somente leitura do sistema.
# Uso: bash fz-recorta-log.sh [arquivo de log, padrão /private/var/log/rmb-msgbuf.log]
# Depende de: grep, tail, cut, awk, shasum (todos do macOS). Roda no bash 3.2.
set -euo pipefail

SRC=${1:-/private/var/log/rmb-msgbuf.log}
FZ="$HOME/fzdrv"
[ -r "$SRC" ] || { echo "não consigo ler $SRC" >&2; exit 1; }

# O log é cumulativo. Um boot novo começa onde o relógio do kernel volta para trás (o carimbo
# "[  ss.ffffff]:" cai mais de 20 s). Não usar "Boot args:": essa linha se repete no meio do boot
# e cortava fora o começo do estágio 3 (visto no boot de 24/11 18:26).
INICIO=$(LC_ALL=C /usr/bin/awk '
  match($0, /^\[ *[0-9]+\.[0-9]+\]:/) {
    t = substr($0, 2, RLENGTH - 3) + 0
    if (visto && t + 20 < anterior) inicio = NR
    anterior = t; visto = 1
  }
  END { print (inicio ? inicio : 1) }' "$SRC" || true)
INICIO=${INICIO:-1}

TMP=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/fzrecorta.XXXXXX")
trap 'rm -rf -- "$TMP"' EXIT
/usr/bin/tail -n "+$INICIO" -- "$SRC" > "$TMP/boot.log"

ESTAGIO=$(/usr/bin/grep -a -o -E 'rmbstage=[0-9]+' "$TMP/boot.log" | /usr/bin/head -1 | /usr/bin/cut -d= -f2 || true)
PATCH=$(/usr/bin/grep -a -o -E 'kext patch [0-9]+' "$TMP/boot.log" | /usr/bin/head -1 | /usr/bin/awk '{print $3}' || true)
# O sha de ~/fzdrv/out só vale para o boot se o log trouxer a linha "kext patch" (patch 0016 em
# diante). Sem ela, o kext que rodou é anterior e não se identifica: não pôr um sha que engana.
SHA=""
[ -n "$PATCH" ] && SHA=$(/usr/bin/cut -c1-8 "$FZ/out/RembrandtGfx.sha256" 2>/dev/null || true)
DATA=$(/bin/date +%Y%m%d-%H%M%S)
DEST="$FZ/rmb-boot-$DATA-estagio${ESTAGIO:-x}-patch${PATCH:-sem}-kext${SHA:-x}.log"

# Grava em arquivo temporário e move, para nunca deixar um recorte pela metade.
cp -- "$TMP/boot.log" "$DEST.tmp"
mv -- "$DEST.tmp" "$DEST"
chmod 600 "$DEST"

echo "recorte: $DEST"
echo "linhas do boot: $(/usr/bin/wc -l < "$DEST" | /usr/bin/tr -d ' ') (a partir da linha $INICIO de $SRC)"
echo "sha256 do kext compilado: $(cat "$FZ/out/RembrandtGfx.sha256" 2>/dev/null || echo desconhecido)"
echo
echo "== linhas que decidem"
/usr/bin/grep -a -E 'RembrandtGfx: (stage 3: (kext patch|[0-9] of|preflight passed|ttl_hw_init BLOCKED)|s3 |psp: |gc: 610M|golden: after gc_golden|gc_check_ucode_loaded: (exit|late wait|autoload complete|Mendocino)|psp-km: |fw: SETUP_TMR|<< ttl_hw_init|<< psp_hw_init|<< ttl_initialize|failed to route)' "$DEST" \
  | /usr/bin/sed -E 's/^.*RembrandtGfx: //' | /usr/bin/cut -c1-420 || true

# Em qual comando do PSP o chip deixa de estar livre: primeira linha psp-km com CP_STAT diferente de 0.
echo
echo "== primeiro comando do PSP com o processador de comandos ocupado"
/usr/bin/grep -a -o -E 'psp-km: .*CP_STAT=[0-9a-f]+ GRBM=[0-9a-f]+' "$DEST" \
  | /usr/bin/awk '!/CP_STAT=0 / { print "  " $0; achou = 1; exit } END { if (!achou) print "  nenhum: CP_STAT=0 em todos os comandos" }' || true
MAPA="$FZ/mapa-codigos-hwlibs-15.8.1.md"

# Tradução pelo mapa de códigos: cada espera longa (callback +X) e cada índice de evento do GC/GVM
# vira o nome da função da Apple. Sem o mapa, esta parte é pulada com aviso.
traduz() {  # traduz TEXTO-FIXO [máximo de linhas]
  /usr/bin/grep -a -F -- "$1" "$MAPA" | /usr/bin/head -"${2:-2}" | /usr/bin/cut -c1-210 | /usr/bin/sed 's/^/      mapa: /' || true
}
echo
echo "== esperas longas, com o nome da função (pelo mapa)"
if [ -r "$MAPA" ]; then
  /usr/bin/grep -a -o -E 's3 wait: callback \+[0-9a-f]+ caller \+[0-9a-f]+ timeout [0-9]+ ms took [0-9]+ ms ret [0-9a-f]+' "$DEST" \
    | /usr/bin/awk '!visto[$0]++' | while IFS= read -r linha; do
        echo "  $linha"
        cb=$(echo "$linha" | /usr/bin/awk '{print $4}' | /usr/bin/tr -d '+')
        traduz "| +0x$cb |" 2
      done || true
  echo
  echo "== índices de evento gravados (pelo mapa)"
  /usr/bin/grep -a -o -E 's3 (gc|gvm) amdlog: index 0x[0-9a-f]+' "$DEST" | /usr/bin/awk '!visto[$0]++' | while IFS= read -r linha; do
        echo "  $linha"
        ip=$(echo "$linha" | /usr/bin/awk '{print $2}'); idx=$(echo "$linha" | /usr/bin/awk '{print $5}')
        # a mesma numeração existe em mais de uma tabela: mostra só as linhas com função da família certa
        /usr/bin/grep -a -F -- "| $idx | 0x" "$MAPA" | /usr/bin/grep -a -F -- "\`_${ip}_" | /usr/bin/head -2 | /usr/bin/cut -c1-210 | /usr/bin/sed 's/^/      mapa: /' || true
      done || true
else
  echo "  (mapa não encontrado em $MAPA; rode sem tradução)"
fi

echo
echo "== todas as mensagens do driver da Apple neste boot (distintas, sem tempo nem ponteiro)"
/usr/bin/grep -a -o -E '(AMD Error|AMD TTL [A-Z]+|AMD TTL COS: ASSERT [A-Z]+):.*' "$DEST" \
  | /usr/bin/sed -E 's/<ptr>//g; s/\{?[0-9]{9,}:/T:/g; s/[[:space:]]+$//' | /usr/bin/cut -c1-170 \
  | /usr/bin/sort | /usr/bin/uniq -c | /usr/bin/sort -rn | /usr/bin/head -60 || true

echo
echo "== erros do driver da Apple neste boot"
# O prefixo varia ("AMD Error:" ou "AMD TTL AMDLOG:"), por isso casa a partir do "[n:n:n]".
/usr/bin/grep -a -o -E '(\[[0-9]+:[0-9]+:[0-9]+\] (Error [A-Za-z_]+: event_id=0x[0-9a-f]+ event_info:type=[0-9]+ hw_id=[0-9]+ event_specific_tag=0x[0-9a-f]+|TTL Event[^}]{0,150})|ASSERT REASON: +.*|RSMU Timeout Events Recorded: [0-9]+|SlaveError=0x[0-9a-f]+|RESTORE MISMATCH.*|panic\(.*)' "$DEST" \
  | /usr/bin/cut -c1-200 | /usr/bin/awk '!visto[$0]++' > "$TMP/erros.txt" || true
cat "$TMP/erros.txt"

if [ -r "$MAPA" ]; then
  echo
  echo "== o que cada código quer dizer (pelo mapa)"
  /usr/bin/grep -a -o -E 'event_id=0x[0-9a-f]+' "$TMP/erros.txt" | /usr/bin/cut -d= -f2 | /usr/bin/awk '!visto[$0]++' | while IFS= read -r id; do
    echo "  $id"
    traduz "| $id |" 3
    traduz "| **$id** |" 3
  done || true
fi
