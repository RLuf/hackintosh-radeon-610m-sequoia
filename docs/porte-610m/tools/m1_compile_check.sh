#!/bin/bash
# Compila cada objeto do RembrandtGfx com as flags exatas de src/RembrandtGfx/Makefile (KFLAGS/CXXFLAGS),
# sem ligar (a ligação exige o ld64 do cctools-port). Lê a lista de objetos da linha OBJS do Makefile.
# fw.o fica de fora: fw.s embute os pedaços de firmware de fw/, que não fazem parte do repositório.
#
# Uso: m1_compile_check.sh RAIZ_DO_REPO DIR_SAIDA ["flags extras só para ipdisc.cpp"]
# Dependências (variáveis): SDK=.../MacKernelSDK  LILU=.../Lilu-1.7.2/Lilu
set -u
if [ $# -lt 2 ]; then
  sed -n '2,8p' "$0"
  exit 2
fi
SRC="$1/src/RembrandtGfx"
OUT="$2"
EXTRA="${3:-}"
SDK="${SDK:?defina SDK=caminho/para/MacKernelSDK}"
LILU="${LILU:?defina LILU=caminho/para/Lilu-1.7.2/Lilu}"
KFLAGS="-target x86_64-apple-macos10.15 -mkernel -nostdinc -fno-builtin -fno-common -mno-red-zone -O2 -fno-asynchronous-unwind-tables -DKERNEL -DKERNEL_PRIVATE -DDRIVER_PRIVATE -DAPPLE -DNeXT -I$SDK/Headers -I$LILU"
CXXFLAGS="$KFLAGS -std=c++17 -fapple-kext -nostdlib -fno-rtti -fno-exceptions -fno-use-cxa-atexit -mllvm -disable-atexit-based-global-dtor-lowering -DPRODUCT_NAME=RembrandtGfx -DMODULE_VERSION=0.1.0 -Wno-deprecated-declarations"
mkdir -p "$OUT"
rm -f "$OUT"/*.o "$OUT"/*.err
rc=0
objs=$(sed -n 's/^OBJS *:= *//p' "$SRC/Makefile")
for o in $objs; do
  b=${o%.o}
  # shellcheck disable=SC2086  # as flags precisam ser separadas em palavras
  case $b in
    plugin_start) clang++ $CXXFLAGS -c "$LILU/Library/plugin_start.cpp" -o "$OUT/$o" 2>"$OUT/$b.err" ;;
    info)         clang $KFLAGS -c "$SRC/info.c" -o "$OUT/$o" 2>"$OUT/$b.err" ;;
    fw)           echo "PULADO fw.o (fw.s precisa dos firmwares divididos em fw/)"; continue ;;
    ipdisc)       clang++ $CXXFLAGS $EXTRA -c "$SRC/$b.cpp" -o "$OUT/$o" 2>"$OUT/$b.err" ;;
    *)            clang++ $CXXFLAGS -c "$SRC/$b.cpp" -o "$OUT/$o" 2>"$OUT/$b.err" ;;
  esac
  r=$?
  [ $r -ne 0 ] && rc=1
  printf '%-16s saida %d  avisos %s  erros %s\n' "$o" $r "$(grep -c 'warning:' "$OUT/$b.err")" "$(grep -c 'error:' "$OUT/$b.err")"
done
exit $rc
