#!/usr/bin/env python3
"""fzmac_bootdiag.py - diagnóstico de boot do OpenCore para qualquer máquina.

Só usa a biblioteca padrão (Python 3.7+). Não grava em disco nenhum, exceto no
comando "ajustar" com --gravar, que edita UM config.plist e antes faz uma cópia.

Comandos:
  logs     lê os logs do OpenCore DEBUG (opencore-*.txt da partição EFI) e, se
           houver, os registros do macOS (system.log). Diz qual boot passou,
           qual travou, quanto tempo levou cada fase e se a trava acompanha o
           valor de "slide" (posição do kernel na memória, sorteada a cada boot).
  ajustar  muda num config.plist já gravado só o que afeta a entrega ao kernel:
           slide fixo, limite de slide (ProvideMaxSlide), ForceExitBootServices, outras
           opções de Booter/Quirks e a troca de um driver. Nunca toca em números de série.

Como o log do OpenCore termina em EXITBS:START (dali em diante o firmware está
desligado e não há onde gravar), o log sozinho NÃO diz se o boot travou depois.
Quem diz é o macOS: cada boot que chega ao sistema deixa uma linha BOOT_TIME em
/private/var/log/system.log. Boot do OpenCore sem BOOT_TIME logo depois = travou.
"""
import argparse
import calendar
import datetime
import glob
import gzip
import os
import plistlib
import re
import shutil
import sys

APPLE_GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
MATCH_WINDOW = 180   # segundos entre EXITBS:START e o BOOT_TIME do macOS para casar os dois
SLOW_PHASE = 30.0    # segundos a partir dos quais uma fase entra na lista de fases lentas


def stamp(text):
    minutes, millis = text.split(":")
    return int(minutes) + int(millis) / 1000.0


def epoch(text, fmt):
    return calendar.timegm(datetime.datetime.strptime(text, fmt).timetuple())


def read_text(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as handle:
        return handle.read().replace(b"\0", b"").decode("utf-8", "replace").replace("\r", "")


# ---------------------------------------------------------------- logs do OpenCore
def parse_oc_log(path):
    lines = []
    for raw in read_text(path).split("\n"):
        m = re.match(r"(\d+:\d+) (\d+:\d+) (.*)", raw)
        if m:
            lines.append((stamp(m.group(1)), stamp(m.group(2)), m.group(3)))
    log = {"file": os.path.basename(path), "lines": len(lines), "attempts": [], "valid_slides": "", "usb": "",
           "boot_time": "", "version": "", "quirks": ""}

    def first(pattern, group=1):
        for _, _, text in lines:
            m = re.search(pattern, text)
            if m:
                return m.group(group)
        return ""

    log["boot_time"] = first(r"Boot timestamp - (.*)")
    log["version"] = first(r"OpenCore (\S+) is loading")
    log["valid_slides"] = first(r"OCABC: (Valid slides - .*|All slides are usable.*)")
    log["quirks"] = (first(r"OCABC: (ALRBL.*)") + " " + first(r"OCABC: (FEXITBS.*)")).strip()
    for _, _, text in lines:
        if text.startswith("OCB: Adding fs") and "L:1" in text:
            log["usb"] = "/".join(re.findall(r"USB\([^)]*\)", text)) or "(não é USB)"
    current = None
    for index, (when, delta, text) in enumerate(lines):
        m = re.search(r"OCB: Should boot from \d+\. (.*?) \(", text)
        if m:
            current = {"entry": m.group(1), "t_choice": when, "phases": [], "failed": "", "slide": None,
                       "kernel": "", "digest": "", "exitbs": None, "exitbs_epoch": None, "last": "",
                       "ramdisk": False}
            log["attempts"].append(current)
            continue
        if current is None:
            continue
        if delta >= SLOW_PHASE:
            current["phases"].append((round(delta, 1), text[:80]))
        if text.startswith("OCB: Perform boot") and ".dmg" in text:
            current["ramdisk"] = True   # recovery: roda de uma imagem carregada na memória
        m = re.search(r"#MBA:OUT\] \((.*)\)", text)
        if m:
            s = re.search(r"slide=(\d+)", m.group(1))
            current["slide"] = int(s.group(1)) if s else None
            if "rootdmg" in m.group(1):
                current["ramdisk"] = True   # segunda etapa do instalador: também roda da memória
        m = re.search(r"Result of 64-bit XNU hook on (.*?) \((\w+)\) is", text)
        if m and not current["kernel"]:
            current["kernel"], current["digest"] = m.group(1).split("\\")[-1], m.group(2)
            current["kernel_read"] = round(delta, 1)
        m = re.search(r"EXITBS:START\] (\S+)", text)
        if m:
            current["exitbs"] = when
            try:
                current["exitbs_epoch"] = epoch(m.group(1), "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass
        if "Boot failed" in text or "StartImage failed" in text:
            current["failed"] = text[:60]
        if re.search(r"LD:LKC\] \} Err|#STOP", text):
            current["failed"] = current["failed"] or text[:60]
        current["last"] = text[:70]
    return log


def macos_boot_times(paths):
    boots, shutdowns = [], []
    for path in paths:
        for line in read_text(path).split("\n"):
            m = re.search(r"BOOT_TIME (\d+)", line)
            if m:
                boots.append(int(m.group(1)))
            m = re.search(r"SHUTDOWN_TIME: (\d+)", line)
            if m:
                shutdowns.append(int(m.group(1)))
    return sorted(set(boots)), sorted(set(shutdowns))


def classify(attempt, boots, have_macos, manual):
    """Devolve (resultado, motivo). Resultados: passou, travou, falhou, outro, desconhecido."""
    if attempt["key"] in manual:
        return manual[attempt["key"]], "informado na linha de comando"
    if attempt["failed"]:
        return "falhou", attempt["failed"]
    if attempt["exitbs"] is None:
        return "outro", "não é boot do macOS ou não chegou a EXITBS:START"
    if not have_macos:
        return "desconhecido", "sem registro do macOS para comparar"
    if attempt["ramdisk"]:
        return "desconhecido", "recovery/instalador roda da memória e não deixa registro no disco"
    start = attempt["exitbs_epoch"]
    if start is not None:
        for boot in boots:
            if 0 <= boot - start <= MATCH_WINDOW:
                return "passou", "kernel iniciou %d s depois (BOOT_TIME)" % (boot - start)
    return "travou", "nenhum BOOT_TIME do macOS até %d s depois" % MATCH_WINDOW


def cmd_logs(args):
    files = sorted(glob.glob(os.path.join(args.oc, "opencore-*.txt")))
    if not files:
        raise SystemExit("nenhum opencore-*.txt em %s (o log só existe com o OpenCore DEBUG)." % args.oc)
    boots, _ = macos_boot_times(args.macos_log)
    manual = {}
    for result, values in (("travou", args.travou), ("passou", args.passou)):
        for value in values:
            for key in value.split(","):
                manual[key.strip()] = result
    rows = []
    for path in files:
        log = parse_oc_log(path)
        for number, attempt in enumerate(log["attempts"], 1):
            attempt["key"] = log["file"][9:26]
            result, why = classify(attempt, boots, bool(args.macos_log), manual)
            rows.append((log, attempt, result, why))
    print("Boots registrados pelo OpenCore: %d em %d arquivos. Inícios do kernel registrados pelo macOS: %d."
          % (len(rows), len(files), len(boots)))
    print()
    print("%-18s %-16s %-6s %-11s %-9s %s" % ("log", "entrada", "slide", "resultado", "kernel(s)", "motivo"))
    for log, attempt, result, why in rows:
        print("%-18s %-16s %-6s %-11s %-9s %s" % (attempt["key"], attempt["entry"][:16],
              attempt["slide"] if attempt["slide"] is not None else "-", result,
              attempt.get("kernel_read", "-"), why))
    slow = [(a["key"], p) for _, a, _, _ in rows for p in a["phases"] if "FreeHotKeys" not in p[1]]
    if slow:
        print()
        print("Fases lentas antes da entrega ao kernel (não são trava; o boot seguiu):")
        for key, (seconds, text) in slow:
            print("  %s: %.0f s em \"%s\"" % (key, seconds, text))
        print("  Leitura lenta do kernel de dentro da imagem do recovery é esperada na primeira etapa.")
    valid = sorted({log["valid_slides"] for log, _, _, _ in rows if log["valid_slides"]})
    if valid:
        print()
        print("Faixa de slide que o OpenCore considera utilizável: %s" % "; ".join(valid))
    good = sorted(a["slide"] for _, a, r, _ in rows if r == "passou" and a["slide"] is not None)
    bad = sorted(a["slide"] for _, a, r, _ in rows if r in ("travou", "falhou") and a["slide"] is not None)
    print()
    if not bad:
        print("Nenhum boot classificado como travado ou falho. Nada a concluir sobre slide.")
        return
    print("slide dos boots que passaram: %s" % (good or "nenhum"))
    print("slide dos boots que travaram ou falharam: %s" % bad)
    if len(good) >= 3 and len(bad) >= 2 and max(good) < min(bad):
        print()
        print("HIPÓTESE (os dados separam os dois grupos sem mistura): o boot trava quando o slide passa de")
        print("algum valor entre %d e %d. Teste: um boot com slide=%d (deve travar) e três com slide=%d (devem passar)."
              % (max(good) + 1, min(bad), min(bad), max(good)))
        print("Se confirmar, limite o sorteio: %s ajustar --config CAMINHO/config.plist --max-slide %d --gravar"
              % (os.path.basename(sys.argv[0]), max(good)))
        print("Fonte: documentação do OpenCore, opção ProvideMaxSlide (\"random boot failures ... the randomized slide")
        print("falls into the unavailable range\").")
    elif len(good) >= 3 and len(bad) >= 2 and max(bad) < min(good):
        print()
        print("HIPÓTESE: o boot trava com slide baixo (até %d) e passa com slide alto (a partir de %d)." % (max(bad), min(good)))
        print("O OpenCore não tem opção de slide mínimo; teste fixar um valor bom: ajustar --slide %d." % min(good))
    else:
        print()
        print("Os valores de slide dos dois grupos se misturam ou há poucos boots: o slide não explica sozinho.")
        print("Junte mais boots (pelo menos 3 de cada tipo) antes de concluir.")


# ---------------------------------------------------------------- ajuste do config.plist
def cmd_ajustar(args):
    with open(args.config, "rb") as handle:
        cfg = plistlib.load(handle)
    changes = []
    quirks = cfg["Booter"]["Quirks"]
    nvram = cfg["NVRAM"]["Add"][APPLE_GUID]
    boot_args = nvram.get("boot-args", "")
    if args.max_slide is not None:
        if not 0 <= args.max_slide <= 254:
            raise SystemExit("--max-slide aceita de 0 (sem limite) a 254.")
        if args.max_slide and not quirks.get("ProvideCustomSlide"):
            raise SystemExit("ProvideMaxSlide só vale com ProvideCustomSlide ligado (regra do ocvalidate).")
        changes.append("Booter/Quirks/ProvideMaxSlide: %s -> %s" % (quirks.get("ProvideMaxSlide", 0), args.max_slide))
        quirks["ProvideMaxSlide"] = args.max_slide
    if args.slide is not None:
        words = [w for w in boot_args.split() if not w.startswith("slide=")]
        if args.slide != "off":
            if not args.slide.isdigit() or not 0 <= int(args.slide) <= 255:
                raise SystemExit("--slide aceita um número de 0 a 255, ou off para voltar ao sorteio.")
            words.append("slide=%d" % int(args.slide))
        new = " ".join(words)
        changes.append("boot-args: \"%s\" -> \"%s\"" % (boot_args, new))
        nvram["boot-args"] = new
    if args.force_exit_bs is not None:
        value = args.force_exit_bs == "on"
        changes.append("Booter/Quirks/ForceExitBootServices: %s -> %s" % (quirks.get("ForceExitBootServices", False), value))
        quirks["ForceExitBootServices"] = value
    for item in args.booter_quirk:
        name, _, value = item.partition("=")
        if name not in quirks or not isinstance(quirks[name], bool) or value not in ("on", "off"):
            raise SystemExit("--booter-quirk espera Nome=on ou Nome=off, com um nome que já exista em Booter/Quirks: %s" % item)
        changes.append("Booter/Quirks/%s: %s -> %s" % (name, quirks[name], value == "on"))
        quirks[name] = value == "on"
    for item in args.trocar_driver:
        old, _, new = item.partition("=")
        entries = [d for d in cfg["UEFI"]["Drivers"] if d.get("Path") == old]
        target = os.path.join(os.path.dirname(os.path.abspath(args.config)), "Drivers", new)
        if not entries or not new:
            raise SystemExit("--trocar-driver espera ANTIGO=NOVO e o ANTIGO tem de estar em UEFI/Drivers: %s" % item)
        if not os.path.isfile(target):
            raise SystemExit("copie antes o arquivo %s para %s" % (new, os.path.dirname(target)))
        for entry in entries:
            entry["Path"] = new
        changes.append("UEFI/Drivers: %s -> %s" % (old, new))
    if not changes:
        print("Estado atual de %s:" % args.config)
        print("  boot-args: %s" % boot_args)
        for key in ("ProvideCustomSlide", "ProvideMaxSlide", "ForceExitBootServices", "EnableSafeModeSlide"):
            print("  %s: %s" % (key, quirks.get(key)))
        return
    print("Mudanças em %s:" % args.config)
    for change in changes:
        print("  " + change)
    print("  (PlatformInfo e números de série não são tocados)")
    if not args.gravar:
        print("Nada foi gravado. Repita com --gravar para aplicar.")
        return
    backup = "%s.fz-antes-%s" % (args.config, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(args.config, backup)
    with open(args.config, "wb") as handle:
        plistlib.dump(cfg, handle)
    print("Gravado. Cópia do arquivo anterior: %s" % backup)
    print("Para desfazer: copie essa cópia de volta por cima do config.plist.")


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico de boot do OpenCore (fzmacinstall).")
    sub = parser.add_subparsers(dest="cmd")
    logs = sub.add_parser("logs", help="classifica os boots e procura relação com o slide")
    logs.add_argument("--oc", required=True, help="pasta com os opencore-*.txt (raiz da partição EFI)")
    logs.add_argument("--macos-log", action="append", default=[],
                      help="system.log do macOS (repetível; aceita .gz). No macOS: /private/var/log/system.log*")
    logs.add_argument("--travou", action="append", default=[], help="logs que você viu travar, ex.: 2026-11-12-190726")
    logs.add_argument("--passou", action="append", default=[], help="logs que você viu passar")
    adj = sub.add_parser("ajustar", help="ajusta slide/ProvideMaxSlide/ForceExitBootServices num config.plist")
    adj.add_argument("--config", required=True)
    adj.add_argument("--max-slide", dest="max_slide", type=int, help="0 a 254; 0 tira o limite")
    adj.add_argument("--slide", help="fixa slide=N nos boot-args; off volta ao sorteio")
    adj.add_argument("--force-exit-bs", dest="force_exit_bs", choices=["on", "off"])
    adj.add_argument("--booter-quirk", dest="booter_quirk", action="append", default=[],
                     help="liga ou desliga uma opção de Booter/Quirks, ex.: SetupVirtualMap=off (repetível)")
    adj.add_argument("--trocar-driver", dest="trocar_driver", action="append", default=[],
                     help="troca um driver em UEFI/Drivers, ex.: OpenHfsPlus.efi=HfsPlus.efi (o novo já copiado em Drivers)")
    adj.add_argument("--gravar", action="store_true", help="aplica (sem isto só mostra o que mudaria)")
    args = parser.parse_args()
    if args.cmd == "logs":
        cmd_logs(args)
    elif args.cmd == "ajustar":
        cmd_ajustar(args)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
