#!/usr/bin/env python3
"""Teste em espaço de usuário do ipdisc.cpp (marco M1 do porte 610M) e decodificador da tabela de IPs.

Recorta do ipdisc.cpp real as constantes, os auxiliares com checagem de limites, mmCopy() (a
leitura por MM_INDEX/MM_DATA) e parse(), compila esse trecho com ASan + UBSan e roda:
  1. mmCopy() sobre um banco de registros falso que emula MM_INDEX / MM_INDEX_HI / MM_DATA e anota
     cada escrita: só os registros 0 e 6 podem ser escritos, os dois têm de voltar ao valor
     inicial, e o número de leituras de MM_DATA tem de ser o esperado (parada antecipada);
  2. tabelas sintéticas válidas (bases de 32 e de 64 bits) com a saída esperada linha a linha;
  3. tabelas corrompidas de propósito (assinatura, checksum, tamanhos, offsets, contagens);
  4. mutações aleatórias, com e sem os checksums recalculados.
Qualquer acesso fora da cópia de 10 KB derruba o teste (ASan).

Uso:
  ipdisc_parse_test.py CAMINHO/src/RembrandtGfx/ipdisc.cpp [iteracoes]
  ipdisc_parse_test.py CAMINHO/src/RembrandtGfx/ipdisc.cpp --decode ARQUIVO.bin
      decodifica um binário de descoberta real (por exemplo o debugfs amdgpu_discovery do Linux)
      com o mesmo parse() do kext e imprime as linhas "probe:" que o kext imprimiria;
  ipdisc_parse_test.py CAMINHO/src/RembrandtGfx/ipdisc.cpp --write-sample ARQUIVO.bin
      grava a tabela sintética válida usada nos testes.
"""
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile

HARNESS = r'''
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

using IOOptionBits = uint32_t;
enum : uint32_t { kIOMapAnywhere = 1, kIOMapInhibitCache = 2, kIOMapReadOnly = 4 };
static std::vector<std::string> gLog;
static void logf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void logf(const char *fmt, ...) {
	char line[1024];
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(line, sizeof(line), fmt, ap);
	va_end(ap);
	gLog.push_back(line);
}
#define LOG(fmt, ...) logf(fmt, ##__VA_ARGS__)

namespace {
#include "slice.inc"
}

// Fake page 0 of the register BAR: MM_INDEX (0), MM_DATA (1), MM_INDEX_HI (6) over a fake VRAM.
struct FakeRegs {
	uint32_t idx = 0x00012345, hi = 0x7, dataReads = 0;
	uint64_t base = 0;  // VRAM offset of vram[0]
	std::vector<uint8_t> vram;
	std::vector<std::pair<uint32_t, uint32_t>> writes;
	bool bad = false;   // an access the real code must never make
	struct Ref {
		FakeRegs &f;
		uint32_t reg;
		operator uint32_t() const { return f.read(reg); }
		Ref &operator=(uint32_t v) { f.write(reg, v); return *this; }
	};
	Ref operator[](uint32_t reg) { return {*this, reg}; }
	uint32_t read(uint32_t reg) {
		if (reg == 0)
			return idx;
		if (reg == 6)
			return hi;
		if (reg != 1 || !(idx & 0x80000000u)) {
			bad = true;
			return 0;
		}
		dataReads++;
		uint64_t p = (static_cast<uint64_t>(hi) << 31) | (idx & 0x7FFFFFFFu);
		if (p < base || p + 4 > base + vram.size())
			return 0xFFFFFFFFu;
		uint32_t v;
		memcpy(&v, vram.data() + (p - base), 4);
		return v;
	}
	void write(uint32_t reg, uint32_t v) {
		writes.push_back({reg, v});
		if (reg == 0)
			idx = v;
		else if (reg == 6)
			hi = v;
		else
			bad = true;
	}
};

struct Ip { uint16_t hw; uint8_t inst, major, minor, rev; std::vector<uint64_t> bases; };

static void w16(std::vector<uint8_t> &b, size_t o, uint32_t v) { b[o] = v & 0xFF; b[o + 1] = (v >> 8) & 0xFF; }
static void w32(std::vector<uint8_t> &b, size_t o, uint32_t v) { w16(b, o, v & 0xFFFF); w16(b, o + 2, v >> 16); }
static uint32_t r16(const uint8_t *b, size_t o) { return b[o] | b[o + 1] << 8; }

// Recompute the checksums the way the firmware fills them, when the fields that locate them are sane.
static void fixBin(uint8_t *b) {
	uint32_t size = r16(b, 10), s = 0;
	if (size >= 10 && size <= BinSize) {
		for (uint32_t i = 10; i < size; i++)
			s += b[i];
		b[8] = s & 0xFF, b[9] = (s >> 8) & 0xFF;
	}
}
static void fixSums(uint8_t *b) {
	uint32_t tOff = r16(b, 12);
	if (tOff && tOff + 80 <= BinSize) {
		uint32_t tSize = r16(b, tOff + 6), s = 0;
		if (tOff + tSize <= BinSize) {
			for (uint32_t i = 0; i < tSize; i++)
				s += b[tOff + i];
			b[14] = s & 0xFF, b[15] = (s >> 8) & 0xFF;
		}
	}
	fixBin(b);
}

// Same shape as the binary measured on the 82X5: 60-byte header, ip table at +60, version 1.1.
constexpr uint32_t T = 60, D = T + 80;
static std::vector<uint8_t> build(const std::vector<Ip> &ips, bool b64, uint32_t version) {
	std::vector<uint8_t> b(BinSize, 0);
	uint32_t o = D + 4;
	for (auto &ip : ips) {
		w16(b, o, ip.hw);
		b[o + 2] = ip.inst, b[o + 3] = static_cast<uint8_t>(ip.bases.size());
		b[o + 4] = ip.major, b[o + 5] = ip.minor, b[o + 6] = ip.rev;
		o += 8;
		for (auto base : ip.bases) {
			w32(b, o, static_cast<uint32_t>(base));
			if (b64)
				w32(b, o + 4, static_cast<uint32_t>(base >> 32));
			o += b64 ? 8 : 4;
		}
	}
	w32(b, 0, 0x28211407);
	w16(b, 4, 1), w16(b, 6, 1);
	w16(b, 10, o);                       // binary_size
	w16(b, 12, T), w16(b, 16, o - T);
	w32(b, T, 0x53445049);
	w16(b, T + 4, version), w16(b, T + 6, o - T);
	w16(b, T + 12, 1);                   // num_dies
	w16(b, T + 14, 0), w16(b, T + 16, D);
	b[T + 78] = b64;
	w16(b, D, 0), w16(b, D + 2, static_cast<uint32_t>(ips.size()));
	fixSums(b.data());
	return b;
}

static int failures;
static void check(const char *name, bool ok, const char *detail = "") {
	printf("%-56s %s  %s\n", name, ok ? "ok  " : "FAIL", detail);
	failures += !ok;
}
static const std::string &run(const std::vector<uint8_t> &b, uint32_t len = BinSize) {
	memcpy(gBin, b.data(), BinSize);
	gLen = len;
	gLog.clear();
	parse(0x7fff0000ULL);
	static const std::string none;
	return gLog.empty() ? none : gLog.back();
}
static void expectLast(const char *name, const std::vector<uint8_t> &b, const char *prefix, uint32_t len = BinSize) {
	const std::string &last = run(b, len);
	bool ok = !last.compare(0, strlen(prefix), prefix);
	unsigned fails = 0;
	for (auto &l : gLog)
		fails += !l.compare(0, 11, "probe: FAIL");
	if (!strncmp(prefix, "probe: FAIL", 11))
		ok = ok && fails == 1;          // exactly one FAIL line, and it is the last one
	else
		ok = ok && fails == 0;
	check(name, ok, last.c_str());
}

// Run mmCopy over a fake register page whose VRAM holds `bin` at offset pos; check the invariants.
static bool mmCase(const std::vector<uint8_t> &bin, uint64_t pos, uint32_t wantLen, unsigned wantHiWrites) {
	FakeRegs f;
	f.base = pos, f.vram = bin;
	memset(gBin, 0xA5, BinSize), gLen = 0xDEAD;
	uint32_t idx = 0, hi = 0;
	mmCopy(f, pos, idx, hi);
	bool ok = !f.bad && idx == 0x00012345 && hi == 0x7 && f.idx == 0x00012345 && f.hi == 0x7;  // saved and restored
	ok = ok && gLen == wantLen && f.dataReads == wantLen / 4 && !memcmp(gBin, bin.data(), gLen);
	for (uint32_t i = gLen; ok && i < BinSize; i++)
		ok = gBin[i] == 0;
	unsigned hiWrites = 0;
	for (auto &w : f.writes) {
		ok = ok && (w.first == 0 || w.first == 6);  // nothing but MM_INDEX and MM_INDEX_HI is ever written
		hiWrites += w.first == 6;
	}
	size_t n = f.writes.size();
	ok = ok && n == wantLen / 4 + hiWrites + 1 && hiWrites == wantHiWrites;
	ok = ok && f.writes[n - 2] == std::make_pair(0u, 0x00012345u) && f.writes[n - 1] == std::make_pair(6u, 0x7u);
	return ok;
}

int main(int argc, char **argv) {
	const std::vector<Ip> ips {
		{11, 0, 10, 3, 7, {0x00001260, 0x0000A000, 0x0001C000, 0x02402C00}},
		{271, 0, 3, 1, 6, {0x00000012, 0x000000C0, 0x000034C0, 0x00009000, 0x02403C00}},
		{255, 0, 13, 0, 8, {0x00016000, 0x00DC0000}},
		{1, 0, 13, 0, 8, {0x00016000}},
		{42, 0, 5, 2, 7, {0x00001260, 0x0000A000}},
		{40, 0, 5, 0, 3, {0x000010A0, 0x0240A000}},
		{108, 0, 7, 5, 1, {}},
	};
	auto good = build(ips, false, 3);
	if (argc == 3 && !strcmp(argv[1], "--write-sample")) {
		FILE *f = fopen(argv[2], "wb");
		if (!f || fwrite(good.data(), 1, BinSize, f) != BinSize)
			return 2;
		fclose(f);
		return 0;
	}
	if (argc == 3 && !strcmp(argv[1], "--decode")) {
		std::vector<uint8_t> b(BinSize, 0);
		FILE *f = fopen(argv[2], "rb");
		if (!f)
			return 2;
		uint32_t n = static_cast<uint32_t>(fread(b.data(), 1, BinSize, f));
		fclose(f);
		const std::string &last = run(b, n);
		for (auto &l : gLog)
			printf("%s\n", l.c_str());
		return last.compare(0, 9, "probe: OK") != 0;
	}
	const uint32_t goodLen = (r16(good.data(), 10) + 3) & ~3u;

	// 1. mmCopy: only MM_INDEX / MM_INDEX_HI written, both restored, bounded number of MM_DATA reads
	check("mmCopy: table at 2048 MB - 64 KB, stops at binary_size", mmCase(good, 0x7fff0000ULL, goodLen, 2));
	expectLast("  ... and what it copied parses", std::vector<uint8_t>(gBin, gBin + BinSize), "probe: OK 1 dies, 7 ips listed", gLen);
	check("mmCopy: MM_INDEX_HI changes inside the table", mmCase(good, 0x80000000ULL - 16, goodLen, 3));
	auto m = good;
	m[0] ^= 1;
	check("mmCopy: wrong signature, 1 word read", mmCase(m, 0x7fff0000ULL, 4, 2));
	expectLast("  ... parse reports it", std::vector<uint8_t>(gBin, gBin + BinSize), "probe: FAIL no binary signature", gLen);
	check("mmCopy: region reads ffffffff, 1 word read", mmCase(std::vector<uint8_t>(BinSize, 0xFF), 0x7fff0000ULL, 4, 2));
	m = good, w16(m, 10, 0xFFFF);
	check("mmCopy: binary_size 65535, 3 words read", mmCase(m, 0x7fff0000ULL, 12, 2));
	expectLast("  ... parse reports it", std::vector<uint8_t>(gBin, gBin + BinSize), "probe: FAIL binary size", gLen);
	m = good, w16(m, 10, 19);
	check("mmCopy: binary_size 19, 3 words read", mmCase(m, 0x7fff0000ULL, 12, 2));
	m = good, w16(m, 10, 21);
	check("mmCopy: binary_size 21, 6 words read", mmCase(m, 0x7fff0000ULL, 24, 2));
	m = good, w16(m, 10, BinSize);
	check("mmCopy: binary_size 10240, 2560 words read, no more", mmCase(m, 0x7fff0000ULL, BinSize, 2));
	m = good, w16(m, 10, BinSize + 1);
	check("mmCopy: binary_size 10241, 3 words read", mmCase(m, 0x7fff0000ULL, 12, 2));

	// 2. valid tables: exact lines
	run(good);
	const char *want[] {
		"probe: ip die0 11/0 hw_id=11 v=10.3.7 bases=0x00001260 0x0000A000 0x0001C000 0x02402C00",
		"probe: ip die0 271/0 hw_id=271 v=3.1.6 bases=0x00000012 0x000000C0 0x000034C0 0x00009000 0x02403C00",
		"probe: ip die0 255/0 hw_id=255 v=13.0.8 bases=0x00016000 0x00DC0000",
		"probe: ip die0 1/0 hw_id=1 v=13.0.8 bases=0x00016000",
		"probe: ip die0 42/0 hw_id=42 v=5.2.7 bases=0x00001260 0x0000A000",
		"probe: ip die0 40/0 hw_id=40 v=5.0.3 bases=0x000010A0 0x0240A000",
		"probe: ip die0 108/0 hw_id=108 v=7.5.1 bases=",
		"probe: OK 1 dies, 7 ips listed",
	};
	bool exact = gLog.size() == 2 + sizeof(want) / sizeof(*want);
	for (size_t i = 0; exact && i < sizeof(want) / sizeof(*want); i++)
		exact = gLog[2 + i] == want[i];
	check("valid 32-bit table, exact lines", exact);
#ifdef HAVE_IPREC
	// what the stage 3 preflight reads back (M3 and later): the recorded IP list
	check("recorded: 7 ips, GC 10.3.7 at 0x1260 / 0xA000",
	      gIpCount == 7 && gIps[0].hw == 11 && gIps[0].inst == 0 && gIps[0].major == 10 && gIps[0].minor == 3 && gIps[0].rev == 7 &&
	      gIps[0].bases == 4 && gIps[0].base[0] == 0x1260 && gIps[0].base[1] == 0xA000);
	check("recorded: an IP with no base address", gIps[6].hw == 108 && gIps[6].bases == 0 && gIps[6].base[0] == 0);
#endif
	if (!exact)
		for (auto &l : gLog)
			printf("    got: %s\n", l.c_str());
	auto good64 = build({{11, 0, 10, 3, 7, {0xFFFFFFFF00001260ULL, 0x12345678C000A000ULL}}}, true, 4);
	run(good64);
	check("valid 64-bit table, low 32 bits & 0x3FFFFFFF",
	      gLog.size() == 4 && gLog[2] == "probe: ip die0 11/0 hw_id=11 v=10.3.7 bases=0x00001260 0x0000A000");
	std::vector<Ip> many {{11, 0, 1, 2, 3, {}}};
	for (unsigned i = 0; i < 40; i++)
		many[0].bases.push_back(0x1000 + i);
	run(build(many, false, 3));
	check("40 bases: 16 printed, then ' ...'",
	      gLog.size() == 4 && gLog[2].size() > 14 && !gLog[2].compare(gLog[2].size() - 14, 14, "0x0000100F ..."));

	// 3. deliberate corruption: one FAIL line, nothing after it
	m = good, m[0] ^= 1;
	expectLast("binary signature wrong", m, "probe: FAIL no binary signature");
#ifdef HAVE_IPREC
	check("a table that fails leaves no recorded IPs", gIpCount == 0);
#endif
	expectLast("nothing read (0 bytes)", good, "probe: FAIL no binary signature", 0);
	m = good, m[0x30] ^= 0x10;
	expectLast("binary checksum wrong", m, "probe: FAIL binary size");
	m = good, w16(m, 10, 0xFFFF);
	expectLast("binary_size 65535", m, "probe: FAIL binary size");
	m = good, w16(m, 10, 19), fixSums(m.data());
	expectLast("binary_size 19", m, "probe: FAIL binary size");
	expectLast("fewer bytes read than binary_size", good, "probe: FAIL binary size", goodLen - 4);
	m = good, w16(m, 12, 0), fixSums(m.data());
	expectLast("ip table offset 0", m, "probe: FAIL ip table at");
	m = good, w16(m, 12, BinSize - 10), fixSums(m.data());
	expectLast("ip table offset at the end of the window", m, "probe: FAIL ip table at");
	m = good, w16(m, 12, 0xFFFF), fixSums(m.data());
	expectLast("ip table offset 65535", m, "probe: FAIL ip table at");
	m = good, m[T] ^= 1, fixSums(m.data());
	expectLast("ip table signature wrong", m, "probe: FAIL ip table at");
	m = good, w16(m, T + 6, 0xFFFF), fixSums(m.data());
	expectLast("ip table size 65535", m, "probe: FAIL ip table size");
	m = good, w16(m, T + 6, 79), fixSums(m.data());
	expectLast("ip table size 79", m, "probe: FAIL ip table size");
	m = good, m[T + 20] ^= 1, fixBin(m.data());
	expectLast("ip table checksum wrong (binary checksum right)", m, "probe: FAIL ip table size");
	m = good, w16(m, T + 12, 17), fixSums(m.data());
	expectLast("num_dies 17", m, "probe: FAIL ip table size");
	m = good, w16(m, T + 16, BinSize - 2), fixSums(m.data());
	expectLast("die header at the end of the window", m, "probe: FAIL die 0 header");
	m = good, w16(m, T + 16, 0xFFFF), fixSums(m.data());
	expectLast("die offset 65535", m, "probe: FAIL die 0 header");
	m = good, w16(m, T + 16, goodLen), fixSums(m.data());
	expectLast("die header just past the bytes read", m, "probe: FAIL die 0 header", goodLen);
	m = good, w16(m, D + 2, 0xFFFF), fixSums(m.data());
	expectLast("num_ips 65535", m, "probe: FAIL die 0 header");
	m = good, w16(m, T + 16, BinSize - 20), w16(m, BinSize - 18, 100), fixSums(m.data());
	expectLast("ips run past the end of the window", m, "probe: FAIL die 0 ip");
	m = good, w16(m, T + 16, BinSize - 600);
	memcpy(m.data() + BinSize - 600, good.data() + D, 12), m[BinSize - 600 + 4 + 3] = 255, fixSums(m.data());
	expectLast("255 bases run past the end of the window", m, "probe: FAIL die 0 ip");
	expectLast("valid table still passes", good, "probe: OK 1 dies, 7 ips listed");
	expectLast("valid table, only binary_size bytes read", good, "probe: OK 1 dies, 7 ips listed", goodLen);

	// 4. random mutations; ASan/UBSan abort on any out-of-bounds access
	unsigned long iters = argc > 1 ? strtoul(argv[1], nullptr, 0) : 300000, okRuns = 0, failRuns = 0, bad = 0;
	uint64_t rng = 0x9E3779B97F4A7C15ULL;
	auto next = [&] { rng ^= rng << 13, rng ^= rng >> 7, rng ^= rng << 17; return rng; };
	for (unsigned long it = 0; it < iters; it++) {
		m = (next() & 1) ? good : good64;
		unsigned kind = next() % 4, n = 1 + next() % 8;
		for (unsigned k = 0; k < n; k++) {
			size_t at = kind == 0 ? next() % 64 : kind == 1 ? T + next() % 96 : kind == 2 ? next() % 0x200 : next() % BinSize;
			m[at] = static_cast<uint8_t>(next());
		}
		if (kind == 3 && next() % 8 == 0)
			for (auto &x : m)
				x = static_cast<uint8_t>(next());
		if (next() % 4)
			w32(m, 0, 0x28211407), fixSums(m.data());
		// half of the runs go through mmCopy first (bytes read bounded by the binary's size field)
		uint32_t len = BinSize;
		if (next() & 1) {
			FakeRegs f;
			f.base = 0x7fff0000ULL, f.vram = m;
			uint32_t idx = 0, hi = 0;
			mmCopy(f, f.base, idx, hi);
			bad += f.bad || f.idx != 0x00012345 || f.hi != 0x7 || gLen > BinSize || f.dataReads != gLen / 4;
			for (auto &w : f.writes)
				bad += w.first != 0 && w.first != 6;
			len = gLen;
			m.assign(gBin, gBin + BinSize);
		}
		const std::string &last = run(m, len);
		bool isOk = !last.compare(0, 9, "probe: OK"), isFail = !last.compare(0, 11, "probe: FAIL");
		unsigned fails = 0;
		for (auto &l : gLog)
			fails += !l.compare(0, 11, "probe: FAIL");
		okRuns += isOk, failRuns += isFail;
		bad += !(isOk ^ isFail) || fails != isFail || gLog.size() > 2 + 16 * (1 + 256);
#ifdef HAVE_IPREC
		bad += isFail ? gIpCount != 0 : gIpCount > MaxRecs;
#endif
	}
	printf("fuzz: %lu runs, %lu ended OK, %lu ended FAIL, %lu inconsistent\n", iters, okRuns, failRuns, bad);
	failures += bad != 0;
	printf(failures ? "RESULT: %d FAILED\n" : "RESULT: all passed\n", failures);
	return failures != 0;
}
'''


def cut(code, start, end):
    a = code.index(start)
    return code[a:code.index(end, a)]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    code = pathlib.Path(sys.argv[1]).read_text()
    # constantes, gBin/gLen, inBin/le16/le32/byteSum, mmCopy() e parse(): tudo o que não depende do IOKit
    piece = cut(code, 'constexpr uint32_t RegMemSize', 'uint32_t dataU32(')
    # uint64_t é 'unsigned long long' na compilação do kernel (alvo macOS) e 'unsigned long' no Linux
    piece = piece.replace('void parse(uint64_t pos)', 'void parse(unsigned long long pos)')
    assert 'unsigned long long pos' in piece and 'void mmCopy(' in piece
    with tempfile.TemporaryDirectory(prefix='ipdisc-parse-test-') as directory:
        build = pathlib.Path(directory)
        (build / 'slice.inc').write_text(piece)
        (build / 'harness.cpp').write_text(HARNESS)
        # a árvore do M3 em diante guarda a lista de IPs para a checagem prévia do estágio 3
        flags = (['-DHAVE_IPREC'] if 'gIpCount' in piece else []) + [
                 '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-const-variable',
                 '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I' + str(build),
                 str(build / 'harness.cpp'), '-o', str(build / 'ipdisc-parse-test')]
        # clang++ primeiro; g++ se o clang não tiver as bibliotecas dos sanitizadores (compiler-rt) instaladas
        candidates = [os.environ['CXX']] if os.environ.get('CXX') else ['clang++', 'g++']
        for candidate in candidates:
            result = subprocess.run(shlex.split(candidate) + flags, capture_output=True, text=True)
            if result.returncode == 0:
                print('compilador: ' + candidate + ' (ASan + UBSan)', file=sys.stderr, flush=True)
                break
            print(candidate + ': falhou\n' + result.stderr.strip()[-1500:], file=sys.stderr)
        else:
            sys.exit('nenhum compilador conseguiu gerar o teste com sanitizadores')
        sys.exit(subprocess.run([str(build / 'ipdisc-parse-test')] + sys.argv[2:]).returncode)


if __name__ == '__main__':
    main()
