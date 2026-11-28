#!/usr/bin/env python3
"""Read-only: display paths, eDP info and ext display connection info from an ATOM ROM."""
import struct, sys, json
img = open(sys.argv[1], 'rb').read()
tabs = json.load(open(sys.argv[2]))
CONN = {0x05: 'DP', 0x0c: 'HDMI-A', 0x13: 'DisplayPort', 0x14: 'eDP', 0x0e: 'LVDS', 0x18: 'USB-C', 0x0d: 'HDMI-B', 0x01:'DVI-I', 0x03:'DVI-D'}
ENC = {0x20: 'UNIPHY(A/B)', 0x21: 'UNIPHY1(C/D)', 0x25: 'UNIPHY2(E/F)', 0x26:'UNIPHY3(G)'}
def objid(v):
    return 'type %d enum %d id %#x' % ((v >> 12) & 7, (v >> 8) & 7, v & 0xff)
o, size, f, c = tabs['displayobjectinfo']
supp, npath = struct.unpack_from('<HB', img, o + 4)
print('displayobjectinfo v%d.%d: supported devices %#x, %d paths' % (f, c, supp, npath))
for i in range(npath):
    p = o + 8 + 16 * i
    did, rec, enc, ext, encrec, extrec, tag, prio = struct.unpack_from('<HHHHHHHB', img, p)
    print(' path %d: connector %#06x (%s, %s) encoder %#06x (%s, %s) ext %#06x tag %#x prio %d' % (
        i, did, objid(did), CONN.get(did & 0xff, '?'), enc, objid(enc), ENC.get(enc & 0xff, '?'), ext, tag, prio))
    for label, ro in (('conn', rec), ('enc', encrec)):
        q = o + ro
        if not ro:
            continue
        n = 0
        while n < 12:
            t, l = img[q], img[q + 1]
            if t == 0xff or l == 0:
                break
            print('    %s record type %d len %d: %s' % (label, t, l, img[q + 2:q + l].hex()))
            q += l; n += 1
o, size, f, c = tabs['integratedsysteminfo']
vm, gcap, syscfg, cpucap, ssp, sst, dpphy, memtype, umach = struct.unpack_from('<IIIIHHHBB', img, o + 4)
print('integratedsysteminfo v%d.%d: vbios_misc %#x gpucapinfo %#x system_config %#x cpucapinfo %#x dpphy_override %#x memorytype %#x umachannelnumber %d' % (f, c, vm, gcap, syscfg, cpucap, dpphy, memtype, umach))
e = o + 4 + 16 + 6 + 6
for k in range(2):
    pwm, ssp, ssr, r1, r2, d1, d2, d3, bpc, bl = struct.unpack_from('<HHHHIBBBBB', img, e + 20 * k)
    print(' edp%d_info: backlight_pwm_hz %d ss %d/%d pwr_on_off_delay %d vary_bl_to_blon %d bloff_to_vary_bloff %d panel_bpc %d bootup_bl_level %d' % (k + 1, pwm, ssp, ssr, d1, d2, d3, bpc, bl))
x = e + 40 + 32
hs, hf, hc = struct.unpack_from('<HBB', img, x)
print(' extdispconninfo header size %#x rev %d.%d' % (hs, hf, hc))
for k in range(7):
    p = x + 4 + 16 + 16 * k
    tag, acpi, conn, aux, hpd, extenc, chmap, pninv, caps, rsv = struct.unpack_from('<HHHBBHBBHH', img, p)
    if tag or conn:
        print('  ext path %d: tag %#x acpi %#x connector %#06x (%s %s) auxddc %d hpd %d ext_enc %#x chmap %#x pninv %#x caps %#x%s' % (
            k, tag, acpi, conn, objid(conn), CONN.get(conn & 0xff, '?'), aux, hpd, extenc, chmap, pninv, caps, ' DP_FIXED_VS_EN' if caps & 2 else ''))
t = x + 4 + 16 + 16 * 7
print('  checksum %#x stereopin %d remotedisplayconfig %d edptolvdsrxid %d fixdpvoltageswing %#x' % tuple(img[t:t + 5]))
o, size, f, c = tabs['firmwareinfo']
rev, sclk, mclk, cap, parser, scratch = struct.unpack_from('<IIIIII', img, o + 4)
print('firmwareinfo v%d.%d: fw rev %#x bootup sclk %d0 kHz mclk %d0 kHz capability %#x scratch reg %#x' % (f, c, rev, sclk, mclk, cap, scratch))
mch, mcl = struct.unpack_from('<II', img, o + 4 + 24 + 8 + 4)
print('  mc_baseaddr %#x_%08x' % (mch, mcl))
for name in ('lcd_info', 'smu_info', 'gfx_info', 'dce_info', 'vram_usagebyfirmware'):
    o, size, f, c = tabs[name]
    print('%s v%d.%d @%#x: %s' % (name, f, c, o, img[o + 4:o + min(size, 0x60)].hex()))
