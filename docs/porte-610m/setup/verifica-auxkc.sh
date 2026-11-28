#!/bin/bash
# Confere se o AuxiliaryKernelExtensions.kc do sistema está íntegro. Só leitura no arquivo do sistema:
# a cópia nova é gerada em /tmp e comparada. Saída curta, para caber na leitura pela ponte.
F=/Library/KernelCollections/AuxiliaryKernelExtensions.kc
N=/tmp/aux-novo.kc
echo "== arquivo do sistema"
stat -f '%Sm | %z bytes' "$F"
shasum -a 256 "$F" | cut -c1-64
echo "== o sistema consegue ler a colecao?"
kmutil inspect -A "$F" 2>&1 | grep -i -E 'highpoint|error|invalid|fail' | head -6 | cut -c1-170
echo "== colecao nova gerada a partir de /Library/Extensions"
rm -f "$N"
kmutil create -n aux -a x86_64 -A "$N" -r /Library/Extensions \
  -B /System/Library/KernelCollections/BootKernelExtensions.kc \
  -S /System/Library/KernelCollections/SystemKernelExtensions.kc 2>&1 | tail -3 | cut -c1-200
if [ -f "$N" ]; then
  stat -f '%z bytes' "$N"
  shasum -a 256 "$N" | cut -c1-64
  cmp -l "$F" "$N" 2>/dev/null | wc -l | awk '{print "bytes diferentes: " $1}'
  cmp -l "$F" "$N" 2>/dev/null | head -1 | awk '{printf "primeira diferenca na posicao %d\n", $1}'
  cmp -l "$F" "$N" 2>/dev/null | tail -1 | awk '{printf "ultima diferenca na posicao %d\n", $1}'
fi
echo "== esta colecao esta carregada agora?"
kmutil showloaded 2>/dev/null | grep -i -c highpoint
echo "== o que o sistema registrou sobre ela"
log show --last 16h --style compact --predicate 'process == "kernelmanagerd"' 2>/dev/null | grep -i -E 'aux' | tail -4 | cut -c1-190
