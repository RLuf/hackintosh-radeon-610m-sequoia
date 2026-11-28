#!/usr/bin/env python3
"""Read-only dump of an ACPI VFCT table: images, PCIR, ATOM master data table."""
import struct, sys
NAMES = """utilitypipeline multimedia_info smc_dpm_info sw_datatable3 firmwareinfo sw_datatable5 lcd_info sw_datatable7
smu_info sw_datatable9 sw_datatable10 vram_usagebyfirmware gpio_pin_lut sw_datatable13 gfx_info powerplayinfo
sw_datatable16 sw_datatable17 sw_datatable18 sw_datatable19 sw_datatable20 sw_datatable21 displayobjectinfo
indirectioaccess umc_info sw_datatable25 sw_datatable26 dce_info vram_info sw_datatable29 integratedsysteminfo
asic_profiling_info voltageobject_info sw_datatable33 sw_datatable34""".split()
data = open(sys.argv[1], 'rb').read()
sig, length = struct.unpack_from('<4sI', data, 0)
print('sig', sig, 'len', length, 'file', len(data))
vbios_off, = struct.unpack_from('<I', data, 36 + 16)
off = vbios_off
imgs = []
while off + 28 <= length:
    bus, dev, fn, ven, did, ssv, ssid, rev, ilen = struct.unpack_from('<IIIHHHHII', data, off)
    print('image @%#x: %02x:%02x.%x %04x:%04x subsys %04x:%04x rev %#x len %d' % (off, bus, dev, fn, ven, did, ssv, ssid, rev, ilen))
    img = data[off + 28: off + 28 + ilen]
    imgs.append(img)
    off += 28 + ilen
img = imgs[0]
if len(sys.argv) > 2:
    open(sys.argv[2], 'wb').write(img)
print('rom sig %s, size byte %d (*512=%d), sum(all)&ff=%#x sum(legacy)&ff=%#x' % (img[:2].hex(), img[2], img[2] * 512, sum(img) & 0xff, sum(img[:img[2] * 512]) & 0xff))
pcir, = struct.unpack_from('<H', img, 0x18)
print('PCIR @%#x %s vendor %04x device %04x, len %d rev %d class %s, image len %d*512, code rev %#x, type %d, indicator %#x' % (
    (pcir, img[pcir:pcir + 4]) + struct.unpack_from('<HH', img, pcir + 4) + (struct.unpack_from('<H', img, pcir + 10)[0], img[pcir + 12], img[pcir + 13:pcir + 16].hex(),
    struct.unpack_from('<H', img, pcir + 0x10)[0], struct.unpack_from('<H', img, pcir + 0x12)[0], img[pcir + 0x14], img[pcir + 0x15])))
romhdr, = struct.unpack_from('<H', img, 0x48)
print('ATOM rom header @%#x: %s rev %d.%d sig %s' % (romhdr, img[romhdr:romhdr + 4].hex(), img[romhdr + 2], img[romhdr + 3], img[romhdr + 4:romhdr + 8]))
# atom_rom_header_v2_2
(bios_seg, protmode, cfgname, crc, vbbootmsg, int10, pcibus, iobase, ssvid, ssid, pciinfo, mct, mdt) = struct.unpack_from('<HHHHHHHHHHHHH', img, romhdr + 8)
print('  subsys %04x:%04x master cmd tbl @%#x master data tbl @%#x pci_info @%#x' % (ssvid, ssid, mct, mdt, pciinfo))
# strings
i = img.find(b'102-')
if i >= 0:
    print('  part string:', img[i:i + 40].split(b'\0')[0])
for needle in (b'MENDOCINO', b'AMD ATOMBIOS', b'ATOMBIOSBK-AMD VER'):
    j = img.find(needle)
    if j >= 0:
        print('  str @%#x: %r' % (j, img[j:j + 60].split(b'\0')[0]))
size, frev, crev = struct.unpack_from('<HBB', img, mdt)
print('master data table: size %#x rev %d.%d -> %d slots' % (size, frev, crev, (size - 4) // 2))
tabs = {}
for k in range((size - 4) // 2):
    o, = struct.unpack_from('<H', img, mdt + 4 + 2 * k)
    name = NAMES[k] if k < len(NAMES) else 'slot%d' % k
    if o:
        s, f, c = struct.unpack_from('<HBB', img, o)
        tabs[name] = (o, s, f, c)
        print('  [%2d] +%#04x %-22s @%#06x size %#06x rev %d.%d' % (k, 4 + 2 * k, name, o, s, f, c))
    else:
        print('  [%2d] +%#04x %-22s ABSENT' % (k, 4 + 2 * k, name))
# master command table: list which command tables exist
size, frev, crev = struct.unpack_from('<HBB', img, mct)
present = [k for k in range((size - 4) // 2) if struct.unpack_from('<H', img, mct + 4 + 2 * k)[0]]
print('master cmd table: size %#x rev %d.%d, present indices:' % (size, frev, crev), present)
import json
json.dump({k: v for k, v in tabs.items()}, open(sys.argv[3], 'w')) if len(sys.argv) > 3 else None
