#!/usr/bin/env python3
"""Reconstruction of the generator of RembrandtGfx phyvalid.hpp.

  phyvalid_gen.py DPCS_offset.h DCN_offset.h [--check phyvalid.hpp] [--skip REGEX]

bit (off - 0x2928) set = DCN seg2 offset `off` is a defined register in either header.
--skip drops register names matching REGEX (use '^DCIO_UNIPHY[05]_UNIPHY_MACRO_CNTL_RESERVED'
for DCN 3.1.6, whose header names the PHY holes)."""
import argparse, re
FIRST, WORDS = 0x2928, 36
ap = argparse.ArgumentParser()
ap.add_argument('dpcs'); ap.add_argument('dcn'); ap.add_argument('--check'); ap.add_argument('--skip')
a = ap.parse_args()

def seg2(path):
    off, idx = {}, {}
    for l in open(path, errors='replace'):
        m = re.match(r'#define\s+(mm|reg)(\w+)\s+(0x[0-9a-fA-F]+|\d+)\s*$', l)
        if not m:
            continue
        n, v = m.group(2), int(m.group(3), 0)
        if n.endswith('_BASE_IDX'):
            idx[n[:-9]] = v
        else:
            off[n] = v
    return {o for n, o in off.items() if idx.get(n) == 2 and not (a.skip and re.search(a.skip, n))}

w = [0] * WORDS
for o in seg2(a.dpcs) | seg2(a.dcn):
    i = o - FIRST
    if 0 <= i < WORDS * 32:
        w[i // 32] |= 1 << (i % 32)
print(', '.join('0x%08x' % x for x in w))
if a.check:
    ref = [int(x, 16) for x in re.findall(r'0x[0-9a-f]{8}', open(a.check).read())]
    print('matches upstream phyvalid.hpp:', ref == w, '(differing words: %s)' % [i for i in range(WORDS) if i < len(ref) and ref[i] != w[i]])
