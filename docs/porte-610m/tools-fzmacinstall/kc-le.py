#!/usr/bin/env python3
# kc-le.py: le um kext de dentro de um Kernel Collection (MH_FILESET) do macOS.
# So leitura. Nao extrai nem altera nada do sistema; os temporarios ficam em pasta propria e somem.
#
# Uso:
#   kc-le.py [--kc ARQ] [--kext NOME] syms REGEX            lista simbolos (endereco, nome)
#   kc-le.py ... dis SIMBOLO [--calls] [--max BYTES]        desmonta a funcao; --calls mostra so o esqueleto
#   kc-le.py ... imm HEX                                    acha um imediato de 32 bits e diz em que funcao esta
#   kc-le.py ... around SIMBOLO HEX [N]                     N instrucoes em volta do imediato dentro da funcao
#   kc-le.py ... kexts REGEX                                lista os kexts do KC
#   kc-le.py ... vers [SIMBOLO]                             quem chama get_hw_revision e que versoes compara
#   kc-le.py ... tabs [SIMBOLO] [TAM_LINHA]                 tabelas de versao lidas por um seletor (padrao
#                                                           _gvm_get_ip_function, linhas de 0x28 bytes)
#
# Padrao: --kc /System/Library/KernelCollections/SystemKernelExtensions.kc --kext AMDRadeonX6000HWLibs
# Precisa de clang e objdump (ferramentas de linha de comando da Apple) para os modos dis e around.
import bisect
import mmap
import os
import re
import struct
import subprocess
import sys
import tempfile

LC_SYMTAB = 0x2
LC_SEGMENT_64 = 0x19
LC_FILESET_ENTRY = 0x80000035
KC_PADRAO = '/System/Library/KernelCollections/SystemKernelExtensions.kc'


def load_commands(buf, off):
    magic, _, _, _, ncmds = struct.unpack_from('<IiiII', buf, off)
    if magic != 0xfeedfacf:
        raise SystemExit('nao e Mach-O de 64 bits em 0x%x' % off)
    p = off + 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', buf, p)
        yield cmd, p
        p += size


def cstr(buf, off, limit=512):
    end = buf.find(b'\0', off, off + limit)
    if end < 0:
        end = off + limit
    return buf[off:end].decode('latin-1')


def fileset(buf):
    out = []
    for cmd, p in load_commands(buf, 0):
        if cmd == LC_FILESET_ENTRY:
            vmaddr, fileoff = struct.unpack_from('<QQ', buf, p + 8)
            name = cstr(buf, p + struct.unpack_from('<I', buf, p + 24)[0])
            out.append((name, vmaddr, fileoff))
    return out


class Kext:
    def __init__(self, buf, want):
        self.buf = buf
        entries = fileset(buf)
        hit = [e for e in entries if e[0] == want or e[0].endswith('.' + want)]
        if len(hit) != 1:
            raise SystemExit('kext "%s": %d entradas no KC' % (want, len(hit)))
        self.name, self.vmaddr, self.off = hit[0]
        self.segs = []
        self.syms = {}
        names = {}
        for cmd, p in load_commands(buf, self.off):
            if cmd == LC_SEGMENT_64:
                segname = buf[p + 8:p + 24].split(b'\0')[0].decode('latin-1')
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', buf, p + 24)
                self.segs.append((segname, vmaddr, vmsize, fileoff, filesize))
            elif cmd == LC_SYMTAB:
                symoff, nsyms, stroff, _ = struct.unpack_from('<IIII', buf, p + 8)
                for i in range(nsyms):
                    strx, ntype, _, _, value = struct.unpack_from('<IBBHQ', buf, symoff + 16 * i)
                    if ntype & 0xe0 or (ntype & 0x0e) != 0x0e or not value:
                        continue
                    name = cstr(buf, stroff + strx)
                    self.syms[name] = value
                    names.setdefault(value, name)
        self.by_addr = names
        self.addrs = sorted(names)

    def vm2off(self, addr):
        for name, vmaddr, _, fileoff, filesize in self.segs:
            if vmaddr <= addr < vmaddr + filesize:
                return fileoff + addr - vmaddr
        return None

    def enclosing(self, addr):
        i = bisect.bisect_right(self.addrs, addr) - 1
        if i < 0:
            return None, 0
        base = self.addrs[i]
        return self.by_addr[base], addr - base

    def label(self, addr):
        name, off = self.enclosing(addr)
        if name is None or off > 0x4000:
            return '0x%x' % addr
        return name if off == 0 else '%s+0x%x' % (name, off)

    def text_at(self, addr):
        off = self.vm2off(addr)
        if off is None:
            return None
        raw = self.buf[off:off + 110]
        end = raw.find(b'\0')
        if end < 4:
            return None
        raw = raw[:end]
        if all(32 <= b < 127 or b in (9, 10) for b in raw):
            return raw.decode('latin-1').replace('\n', '\\n')
        return None

    def code(self, symbol, limit):
        if symbol.startswith('0x'):
            symbol = self.enclosing(int(symbol, 16))[0]
        if symbol not in self.syms:
            raise SystemExit('simbolo nao encontrado: %s' % symbol)
        base = self.syms[symbol]
        i = bisect.bisect_right(self.addrs, base)
        end = self.addrs[i] if i < len(self.addrs) else base + limit
        size = min(end - base, limit)
        off = self.vm2off(base)
        return base, bytes(self.buf[off:off + size]), end - base


def objdump(code):
    with tempfile.TemporaryDirectory() as d:
        s, o = os.path.join(d, 'f.s'), os.path.join(d, 'f.o')
        with open(s, 'w') as f:
            f.write('.text\n.globl _f\n_f:\n')
            for i in range(0, len(code), 16):
                f.write('.byte ' + ','.join('0x%02x' % b for b in code[i:i + 16]) + '\n')
        subprocess.check_call(['clang', '-c', '-target', 'x86_64-apple-macos11', s, '-o', o])
        out = subprocess.check_output(['objdump', '-d', '--no-show-raw-insn', o]).decode('latin-1')
    insns = []
    for line in out.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+(\S.*)$', line)
        if m:
            text = re.sub(r'\s*#.*$', '', m.group(2))
            insns.append((int(m.group(1), 16), re.sub(r'\s+', ' ', text).strip()))
    return insns


def disasm(k, symbol, limit):
    base, code, real = k.code(symbol, limit)
    insns = objdump(code)
    out = []
    for i, (rel, text) in enumerate(insns):
        nxt = insns[i + 1][0] if i + 1 < len(insns) else len(code)
        note = ''
        m = re.match(r'^(call\w*|j\w+)\s+0x([0-9a-f]+)', text)
        if m:
            target = int(m.group(2), 16)
            if target < len(code):
                text = '%s +0x%x' % (m.group(1), target)
            else:
                text = '%s %s' % (m.group(1), k.label((base + target) & 0xffffffffffffffff))
        m = re.search(r'(-?0x[0-9a-f]+|-?\d+)\(%rip\)', text)
        if m:
            disp = int(m.group(1), 16) if 'x' in m.group(1) else int(m.group(1))
            target = (base + nxt + disp) & 0xffffffffffffffff
            s = k.text_at(target)
            note = '  ; "%s"' % s if s else '  ; ' + k.label(target)
        out.append((rel, text + note))
    return base, real, len(code), out


def main(argv):
    kc, kext = KC_PADRAO, 'AMDRadeonX6000HWLibs'
    args = []
    opts = {'--calls': False, '--max': '6000'}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--kc':
            kc = argv[i + 1]; i += 2
        elif a == '--kext':
            kext = argv[i + 1]; i += 2
        elif a == '--max':
            opts['--max'] = argv[i + 1]; i += 2
        elif a == '--calls':
            opts['--calls'] = True; i += 1
        else:
            args.append(a); i += 1
    if not args:
        raise SystemExit(__doc__ or 'uso: kc-le.py syms|dis|imm|around|kexts ...')
    with open(kc, 'rb') as f:
        buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    mode = args[0]
    if mode == 'kexts':
        rx = re.compile(args[1] if len(args) > 1 else '.')
        for name, vmaddr, off in fileset(buf):
            if rx.search(name):
                print('%10x %10x %s' % (vmaddr, off, name))
        return
    k = Kext(buf, kext)
    if mode == 'syms':
        rx = re.compile(args[1])
        for name in sorted(k.syms, key=k.syms.get):
            if rx.search(name):
                print('%10x %s' % (k.syms[name], name))
    elif mode == 'imm':
        pat = struct.pack('<I', int(args[1], 16))
        n = 0
        for name, vmaddr, _, fileoff, filesize in k.segs:
            if name == '__LINKEDIT':
                continue
            p = buf.find(pat, fileoff, fileoff + filesize)
            while p >= 0 and n < 60:
                print('%10x %s (%s)' % (vmaddr + p - fileoff, k.label(vmaddr + p - fileoff), name))
                n += 1
                p = buf.find(pat, p + 1, fileoff + filesize)
        print('ocorrencias: %d' % n)
    elif mode == 'vers':
        # Toda funcao que chama o empacotador de versao (get_hw_revision) e as versoes que ela compara.
        target = k.syms[args[1] if len(args) > 1 else '_get_hw_revision']
        callers = {}
        for name, vmaddr, _, fileoff, filesize in k.segs:
            if not (vmaddr <= target < vmaddr + filesize):
                continue
            end = fileoff + filesize - 5
            p = buf.find(b'\xe8', fileoff, end)
            while p >= 0:
                here = vmaddr + p - fileoff
                if here + 5 + struct.unpack_from('<i', buf, p + 1)[0] == target:
                    callers.setdefault(k.enclosing(here)[0], []).append(here)
                p = buf.find(b'\xe8', p + 1, end)

        def ver(v):
            return '%d.%d.%d' % (v >> 16, (v >> 8) & 0xff, v & 0xff)
        for fn in sorted(callers, key=k.syms.get):
            base, real, got, lines = disasm(k, fn, 6000)
            out = []
            for n, (_, text) in enumerate(lines):
                m = re.match(r'^cmpl \$0x([0-9a-f]+), %e', text)
                if m and 0x10000 <= int(m.group(1), 16) <= 0xffffff:
                    nxt = lines[n + 1][1].split(' ')[0] if n + 1 < len(lines) else ''
                    out.append(ver(int(m.group(1), 16)) + ('' if nxt in ('je', 'jne') else '(' + nxt + ')'))
                m = re.match(r'^addl \$0x(ff[0-9a-f]{6}), %e', text)
                if m:
                    out.append('faixa-de:' + ver((-int(m.group(1), 16)) & 0xffffffff))
                m = re.match(r'^(leal|subl) -0x([0-9a-f]+)\(%r', text)
                if m and 0x10000 <= int(m.group(2), 16) <= 0xffffff:
                    out.append('faixa-de:' + ver(int(m.group(2), 16)))
                m = re.match(r'^cmpl \$0x([0-9a-f]+), %e', text)
                if m and int(m.group(1), 16) < 0x40 and out and out[-1].startswith('faixa-de'):
                    out.append('ate+%d' % int(m.group(1), 16))
                m = re.match(r'^movl \$0x([0-9a-f]+), %e', text)
                if m and n + 1 < len(lines) and lines[n + 1][1].startswith('bt'):
                    out.append('mascara:%x' % int(m.group(1), 16))
            print('%s [%dx]: %s' % (fn, len(callers[fn]), ' '.join(out)))
    elif mode == 'tabs':
        # Tabelas de versao lidas por um seletor do tipo f(maj, min, rev, qual, tabela, n), como
        # _gvm_get_ip_function: linhas de 0x28 bytes com maj, min, rev (16 bits cada) e quatro ponteiros.
        sel = args[1] if len(args) > 1 else '_gvm_get_ip_function'
        row = int(args[2], 0) if len(args) > 2 else 0x28
        target = k.syms[sel]
        sites = {}
        for name, vmaddr, _, fileoff, filesize in k.segs:
            if not (vmaddr <= target < vmaddr + filesize):
                continue
            end = fileoff + filesize - 5
            p = buf.find(b'\xe8', fileoff, end)
            while p >= 0:
                here = vmaddr + p - fileoff
                if here + 5 + struct.unpack_from('<i', buf, p + 1)[0] == target:
                    sites.setdefault(k.enclosing(here)[0], []).append(here)
                p = buf.find(b'\xe8', p + 1, end)

        def ptr(raw):
            if raw == 0:
                return 'NULO'
            for cand in (raw, raw & 0xffffffffffff, raw & 0x3fffffff):
                name, off = k.enclosing(cand)
                if name is not None and off == 0:
                    return name
            return 'ptr:%x' % raw

        shown = {}
        for fn in sorted(sites, key=k.syms.get):
            base, real, got, lines = disasm(k, fn, 6000)
            for n, (rel, text) in enumerate(lines):
                if base + rel not in sites[fn]:
                    continue
                tab = count = which = None
                for j in range(n - 1, max(-1, n - 24), -1):
                    t = lines[j][1]
                    m = re.match(r'^leaq (-?0x[0-9a-f]+|-?\d+)\(%rip\), %r8\b', t)
                    if m and tab is None:
                        disp = int(m.group(1), 16) if 'x' in m.group(1) else int(m.group(1))
                        tab = (base + lines[j + 1][0] + disp) & 0xffffffffffffffff
                    m = re.match(r'^movl \$(0x[0-9a-f]+|\d+), %r9d\b', t)
                    if m and count is None:
                        count = int(m.group(1), 0)
                    m = re.match(r'^movl \$(0x[0-9a-f]+|\d+), %ecx\b', t)
                    if m and which is None:
                        which = int(m.group(1), 0)
                    if t.startswith('xorl %ecx, %ecx') and which is None:
                        which = 0
                print('%s+0x%x: tabela %s, linhas %s, funcao #%s' % (
                    fn, rel, '0x%x' % tab if tab is not None else '?', count if count is not None else '?',
                    which if which is not None else '?'))
                if tab is None:
                    continue
                if tab in shown:
                    print('   (mesma tabela de %s)' % shown[tab])
                    continue
                shown[tab] = fn
                for i in range(count if count is not None else 16):
                    off = k.vm2off(tab + i * row)
                    if off is None:
                        print('   linha %d fora do kext' % i)
                        break
                    maj, mnr, rev = struct.unpack_from('<HHH', buf, off)
                    ptrs = struct.unpack_from('<%dQ' % ((row - 8) // 8), buf, off + 8)
                    if count is None and not (maj or mnr or rev or any(ptrs)):
                        break
                    print('   %d.%d.%d  %s' % (maj, mnr, rev, '  '.join(ptr(x) for x in ptrs)))
    elif mode in ('dis', 'around'):
        base, real, got, lines = disasm(k, args[1], int(opts['--max'], 0))
        print('%s em 0x%x, %d bytes (lidos %d)' % (k.label(base), base, real, got))
        if mode == 'around':
            needle = '$0x%x' % int(args[2], 16)
            span = int(args[3]) if len(args) > 3 else 12
            keep = set()
            for n, (_, text) in enumerate(lines):
                if needle in text:
                    keep.update(range(max(0, n - span), min(len(lines), n + span + 1)))
            last = None
            for n in sorted(keep):
                if last is not None and n != last + 1:
                    print('   ...')
                print('%6x: %s' % lines[n])
                last = n
        else:
            for rel, text in lines:
                if opts['--calls'] and not re.search(r'^call|^ret|; "|\$0x[0-9a-f]{6,}|^j\w+ [^+]', text):
                    continue
                print('%6x: %s' % (rel, text))
    else:
        raise SystemExit('modo desconhecido: ' + mode)


if __name__ == '__main__':
    main(sys.argv[1:])
