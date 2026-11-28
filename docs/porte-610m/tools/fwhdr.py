#!/usr/bin/env python3
"""fwhdr.py FILE...: common amdgpu firmware header (amdgpu_ucode.h common_firmware_header)."""
import struct, sys, hashlib
for f in sys.argv[1:]:
    b = open(f, 'rb').read()
    size, hsz, hmaj, hmin, ipmaj, ipmin, ver, usz, uoff, crc = struct.unpack_from('<IIHHHHIIII', b, 0)
    print('%-26s size %#7x hdr v%d.%d ip %d.%d ucode_ver %#010x ucode_size %#7x off %#x sha256 %s' % (
        f.split('/')[-1], size, hmaj, hmin, ipmaj, ipmin, ver, usz, uoff, hashlib.sha256(b).hexdigest()[:12]))
