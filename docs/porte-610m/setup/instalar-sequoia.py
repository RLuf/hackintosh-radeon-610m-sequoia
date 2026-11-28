#!/usr/bin/env python3
"""Conduz o fzmacinstall.sh para gravar o instalador do macOS Sequoia num disco externo, sem perguntas.

Cada resposta é ligada ao TEXTO da pergunta, não à ordem. Pergunta desconhecida: o roteiro para e nada é
confirmado. O disco só é confirmado se o número de série lido agora for o esperado.

Uso (como root, no Linux da máquina):
  FZ_WORKDIR=/pasta/com/espaco python3 instalar-sequoia.py /caminho/fzmacinstall.sh /dev/sdX SERIE [log]

No Deepin 25 o sgdisk do sistema (1.0.9 com libpopt 1.19) falha. Usar o atalho sgdisk-atalho.sh:
  sudo env PATH=/mnt/dados/fzwork/bin:/usr/sbin:/usr/bin:/sbin:/bin FZ_WORKDIR=... TMPDIR=... python3 instalar-sequoia.py ...
"""
import os, pty, re, select, subprocess, sys, time

script, disk, serial = sys.argv[1], sys.argv[2], sys.argv[3]
logpath = sys.argv[4] if len(sys.argv) > 4 else "/tmp/instalar-sequoia.log"
TIMEOUT_TOTAL, QUIET = 3600, 1.0

def disk_serial():
    return subprocess.run(["lsblk", "-dno", "SERIAL", disk], capture_output=True, text=True).stdout.strip()

if os.geteuid() != 0:
    sys.exit("rode como root")
if disk_serial() != serial:
    sys.exit("o disco %s nao tem a serie %s; nada foi feito" % (disk, serial))

def pick_disk(buf):
    for line in buf.splitlines():
        m = re.match(r"\s+(\d+)\s+(\S+)\s", line)
        if m and m.group(2) == disk and "livre" in line:
            return m.group(1)
    return None

def pick_version(buf):
    m = re.findall(r"^\s+(\d+)\)\s+.*Sequoia", buf, re.M)
    return m[-1] if m else None

def confirm(buf):
    if "(%s)" % disk in buf and disk_serial() == serial:
        return disk
    return None

# (trecho da pergunta, resposta ou funcao). A primeira que casar com a ultima linha vale.
RULES = [
    ("Digite o caminho exato", confirm),
    ("Disco de destino", pick_disk),
    ("Perfil", "1"),
    ("Rede", "1"),
    ("Esconder o NVMe/SSD interno", "s"),
    ("Teclado ABNT2", "s"),
    ("driver do trackpad I2C", "s"),
    ("OpenCore DEBUG", "s"),
    ("Versão", pick_version),
    ("revisão do plano ao Claude", "n"),
    ("Preparar esses ajustes", "s"),
    ("Fuso horário", ""),
    ("Nome da máquina", ""),
    ("chave PÚBLICA de SSH", ""),
    ("com.apple.recovery.boot já baixada", ""),
    ("Board-ID do recovery", ""),
    ("Partição EFI, OpenCore", ""),
    ("Partição CATREC, recovery", ""),
    ("Partição MACOS", ""),
    ("Menu", "1"),
    ("entrada fixa no firmware", "n"),
    ("Testar o boot deste destino", "n"),
    ("Opção", "1"),
]

pid, fd = pty.fork()
if pid == 0:
    os.chdir(os.path.dirname(os.path.abspath(script)))
    os.execvp("bash", ["bash", script])

log = open(logpath, "w", buffering=1)
strip = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
buf, since, start, last, status = "", "", time.time(), time.time(), None
answered = 0
while True:
    if time.time() - start > TIMEOUT_TOTAL:
        log.write("\n[roteiro] tempo esgotado\n"); os.kill(pid, 15); status = 3; break
    r, _, _ = select.select([fd], [], [], 0.3)
    if r:
        try:
            data = os.read(fd, 65536)
        except OSError:
            data = b""
        if not data:
            break
        text = strip.sub("", data.decode("utf-8", "replace")).replace("\r", "")
        log.write(text); buf += text; since += text; last = time.time()
        continue
    tail = since.rstrip(" ")
    if since.endswith(": ") and time.time() - last >= QUIET:
        question = tail.splitlines()[-1] if tail.splitlines() else ""
        for key, ans in RULES:
            if key in question:
                value = ans(since) if callable(ans) else ans
                if value is None:
                    log.write("\n[roteiro] nao consegui responder com seguranca a: %s\n" % question)
                    os.kill(pid, 15); status = 2
                else:
                    log.write("\n[roteiro] resposta a '%s': '%s'\n" % (key, value))
                    os.write(fd, (value + "\n").encode()); since = ""; answered += 1; last = time.time()
                break
        else:
            log.write("\n[roteiro] pergunta desconhecida, parei: %s\n" % question)
            os.kill(pid, 15); status = 2
        if status:
            break
try:
    _, st = os.waitpid(pid, 0)
    rc = os.waitstatus_to_exitcode(st)
except ChildProcessError:
    rc = -1
log.write("\n[roteiro] fim: respostas=%d codigo=%s parada=%s\n" % (answered, rc, status))
sys.exit(status or (0 if rc == 0 else 1))
