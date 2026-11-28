#!/usr/bin/env python3
"""regoff.py HEADER NAME... : print '#define' line numbers, offsets and BASE_IDX for register names."""
import re, sys
defs = {}
for n, l in enumerate(open(sys.argv[1], errors='replace'), 1):
    m = re.match(r'#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)', l)
    if m:
        defs[m.group(1)] = (int(m.group(2), 0), n)
for name in sys.argv[2:]:
    v = defs.get(name); b = defs.get(name + '_BASE_IDX')
    print('%-40s %s base_idx %s (line %s)' % (name, hex(v[0]) if v else None, b[0] if b else None, v[1] if v else None))
