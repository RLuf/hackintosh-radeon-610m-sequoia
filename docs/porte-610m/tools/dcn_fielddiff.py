#!/usr/bin/env python3
"""dcn_fielddiff.py A_sh_mask.h B_sh_mask.h: fields (REG__FIELD_MASK) present in both with different masks,
plus counts of fields only in one side. Stand-in for the missing scripts/dcn-fielddiff.py."""
import re, sys
def load(p):
    d = {}
    for l in open(p, errors='replace'):
        m = re.match(r'#define\s+(\w+)_MASK\s+(0x[0-9a-fA-F]+)L?', l)
        if m: d[m.group(1)] = int(m.group(2), 16)
    return d
a, b = load(sys.argv[1]), load(sys.argv[2])
diff = sorted(n for n in a if n in b and a[n] != b[n])
print('fields: A %d, B %d, common %d, mask differs %d, A-only %d, B-only %d' % (len(a), len(b), len([n for n in a if n in b]), len(diff), len([n for n in a if n not in b]), len([n for n in b if n not in a])))
lim = int(sys.argv[3]) if len(sys.argv) > 3 else 40
for n in diff[:lim]:
    print('  %-70s %#010x -> %#010x' % (n, a[n], b[n]))
if len(sys.argv) > 4:
    regs = sorted({n.split('__')[0] for n in a if n not in b})
    print('  A-only fields belong to %d registers, e.g. %s' % (len(regs), regs[:12]))
