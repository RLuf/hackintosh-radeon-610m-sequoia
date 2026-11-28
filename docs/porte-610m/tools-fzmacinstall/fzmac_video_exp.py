#!/usr/bin/env python3
"""fzmac_video_exp.py: experimento de vídeo numa segunda instância do OpenCore, com volta automática.

Para que serve: testar uma configuração de vídeo arriscada (por exemplo, apresentar uma GPU sem driver como se
fosse um modelo que a Apple suporta) sem tocar na configuração que já funciona.

Como funciona:
  - A EFI que funciona fica em EFI/OC e não muda (só ganha uma entrada no menu).
  - "make" cria EFI/OCX: cópia de EFI/OC com as propriedades do experimento no config.plist.
  - "arm" grava o roteiro da entrada de menu "EXPERIMENTO de video". Ao ser escolhida, ela cria uma opção de boot
    do firmware apontando para EFI\\OCX\\OpenCore.efi, marca essa opção em BootNext (vale para UM boot) e reinicia.
  - Se o experimento travar, cair ou der tela preta: desligar e ligar. O firmware já apagou o BootNext e o boot
    volta sozinho para EFI/OC.
  - "remove" apaga EFI/OCX e a entrada de menu.

Subcomandos:
  make   --efi DIR --gpu-path CAMINHO --device-id HEX [--model TEXTO] [--rom ARQ] [--weg PASTA.kext]
         [--boot-arg ARG ...] [--drop-arg ARG ...]
  arm    --efi DIR (--disk DISCO_OU_IMAGEM --part N | --part-guid GUID --part-start LBA --part-size LBAS)
  remove --efi DIR

DIR é a pasta que contém EFI/OC (a partição EFI montada, ou a pasta gerada pelo fzmac_hw.py build).
Só biblioteca padrão; Python 3.7+. Não grava em disco nenhum além dos arquivos dentro de DIR.
Autor: Roger Luft (com o Fabio)  |  Licença: GPLv2
"""
import argparse
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import uuid

EFI_GLOBAL = "8BE4DF61-93CA-11D2-AA0D-00E098032B8C"
APPLE_BOOT = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
BOOT_NUM = 0x0F2A          # número fixo da opção de boot do experimento (Boot0F2A)
MARKER = ".fzexp"
TOOL_DIR = "fzexp"
TOOL_NAME = "EXPERIMENTO de video (um boot; se falhar, desligue e ligue)"
INSTANCE = "FZEXP"


def load_plist(path):
    with open(path, "rb") as handle:
        return plistlib.load(handle)


def save_plist(data, path):
    with open(path, "wb") as handle:
        plistlib.dump(data, handle)


def paths(root):
    oc = os.path.join(root, "EFI", "OC")
    if not os.path.isfile(os.path.join(oc, "config.plist")) or not os.path.isfile(os.path.join(oc, "OpenCore.efi")):
        raise SystemExit("%s não tem EFI/OC/config.plist e EFI/OC/OpenCore.efi." % root)
    return oc, os.path.join(root, "EFI", "OCX")


def remove(root):
    oc, ocx = paths(root)
    if os.path.isdir(ocx):
        if not os.path.exists(os.path.join(ocx, MARKER)):
            raise SystemExit("%s existe e não foi criada por esta ferramenta; não apago." % ocx)
        shutil.rmtree(ocx)
    shutil.rmtree(os.path.join(oc, "Tools", TOOL_DIR), ignore_errors=True)
    cfg = load_plist(os.path.join(oc, "config.plist"))
    cfg["Misc"]["Tools"] = [t for t in cfg["Misc"]["Tools"] if not t.get("Path", "").startswith(TOOL_DIR + "/")]
    save_plist(cfg, os.path.join(oc, "config.plist"))
    print("  Experimento removido: EFI/OCX apagada e entrada de menu retirada.")


def nsh(lines):
    return "\r\n".join(lines) + "\r\n"


def unarmed_script():
    return nsh(["@echo -off",
                'echo "fzmacinstall: o experimento ainda nao foi armado para este disco."',
                'echo "No Linux, rode: fzmac_video_exp.py arm --efi PASTA --disk DISCO --part 1"',
                "pause", "exit"])


def make(root, args):
    oc, ocx = paths(root)
    if not re.match(r"^PciRoot\(0x[0-9A-Fa-f]+\)(/Pci\(0x[0-9A-Fa-f]+,0x[0-9A-Fa-f]+\))+$", args.gpu_path):
        raise SystemExit("--gpu-path deve ter a forma PciRoot(0x1)/Pci(0x8,0x1)/Pci(0x0,0x0).")
    if not re.match(r"^[0-9A-Fa-f]{4}$", args.device_id):
        raise SystemExit("--device-id deve ter 4 dígitos hexadecimais, ex.: 73ff.")
    remove(root)
    shutil.copytree(oc, ocx)
    open(os.path.join(ocx, MARKER), "w").close()
    cfg = load_plist(os.path.join(ocx, "config.plist"))
    cfg["Misc"]["Boot"]["InstanceIdentifier"] = INSTANCE
    props = dict(cfg["DeviceProperties"]["Add"].get(args.gpu_path, {}))
    props["device-id"] = struct.pack("<I", int(args.device_id, 16))   # 73ff -> FF 73 00 00
    if args.model:
        props["model"] = args.model
    if args.rom:
        with open(args.rom, "rb") as handle:
            props["ATY,bin_image"] = handle.read()
    cfg["DeviceProperties"]["Add"][args.gpu_path] = props
    if args.weg:
        info_path = os.path.join(args.weg, "Contents", "Info.plist")
        if not os.path.isfile(info_path):
            raise SystemExit("--weg deve apontar para a pasta WhateverGreen.kext.")
        name = os.path.basename(os.path.normpath(args.weg))
        dest = os.path.join(ocx, "Kexts", name)
        if not os.path.isdir(dest):
            shutil.copytree(args.weg, dest)
        entries = cfg["Kernel"]["Add"]
        if not any(e["BundlePath"] == name for e in entries):
            executable = load_plist(info_path).get("CFBundleExecutable", "")
            entry = {"Arch": "Any", "BundlePath": name, "Comment": "fzmacinstall: experimento", "Enabled": True,
                     "ExecutablePath": "Contents/MacOS/" + executable if executable else "",
                     "MaxKernel": "", "MinKernel": "", "PlistPath": "Contents/Info.plist"}
            after = next((i for i, e in enumerate(entries) if e["BundlePath"] == "Lilu.kext"), -1)
            if after < 0:
                raise SystemExit("o config não tem Lilu.kext; o WhateverGreen depende dele.")
            entries.insert(after + 1, entry)
    nvram = cfg["NVRAM"]["Add"][APPLE_BOOT]
    current = [a for a in nvram.get("boot-args", "").split() if a not in args.drop_arg]
    nvram["boot-args"] = " ".join(current + [a for a in args.boot_arg if a not in current])
    cfg["Misc"]["Tools"] = [t for t in cfg["Misc"]["Tools"] if not t.get("Path", "").startswith(TOOL_DIR + "/")]
    save_plist(cfg, os.path.join(ocx, "config.plist"))

    # Entrada de menu na instância normal: shell UEFI próprio, com o roteiro startup.nsh ao lado
    tool_dir = os.path.join(oc, "Tools", TOOL_DIR)
    os.makedirs(tool_dir)
    shell = os.path.join(oc, "Tools", "OpenShell.efi")
    if not os.path.isfile(shell):
        raise SystemExit("EFI/OC/Tools/OpenShell.efi não existe; a entrada de menu precisa dele.")
    shutil.copy(shell, tool_dir)
    with open(os.path.join(tool_dir, "startup.nsh"), "w", newline="") as handle:
        handle.write(unarmed_script())
    main = load_plist(os.path.join(oc, "config.plist"))
    main["Misc"]["Tools"].insert(0, {
        "Arguments": "fz -nointerrupt -noversion", "Auxiliary": False, "Comment": "fzmacinstall: experimento de video",
        "Enabled": True, "Flavour": "Auto", "FullNvramAccess": True, "Name": TOOL_NAME,
        "Path": TOOL_DIR + "/OpenShell.efi", "RealPath": True, "TextMode": False})
    save_plist(main, os.path.join(oc, "config.plist"))
    print("  EFI/OCX criada (instância %s)." % INSTANCE)
    print("  %s: device-id=%s%s%s" % (args.gpu_path, props["device-id"].hex().upper(),
                                      ", model=" + args.model if args.model else "",
                                      ", ATY,bin_image=%d bytes" % len(props["ATY,bin_image"]) if args.rom else ""))
    print("  boot-args do experimento: %s" % nvram["boot-args"])
    print("  Falta armar: fzmac_video_exp.py arm --efi %s --disk DISCO --part 1" % root)


def part_info(disk, number):
    """GUID, primeiro setor e tamanho da partição, lidos com sgdisk -i (só leitura)."""
    result = subprocess.run(["sgdisk", "-i", str(number), disk], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = result.stdout.decode(errors="replace")
    guid = re.search(r"Partition unique GUID: (\S+)", text)
    first = re.search(r"First sector: (\d+)", text)
    last = re.search(r"Last sector: (\d+)", text)
    if result.returncode != 0 or not (guid and first and last):
        raise SystemExit("não consegui ler a partição %s de %s:\n%s" % (number, disk, text))
    return guid.group(1), int(first.group(1)), int(last.group(1)) - int(first.group(1)) + 1


def load_option(description, number, guid, start, size, path):
    """EFI_LOAD_OPTION com caminho curto HD(...)/arquivo (UEFI 2.x, seções 3.1.3 e 10.3.5.1)."""
    hd = struct.pack("<BBHIQQ", 4, 1, 42, number, start, size) + uuid.UUID(guid).bytes_le + bytes([2, 2])
    name = path.encode("utf-16-le") + b"\0\0"
    file_node = struct.pack("<BBH", 4, 4, 4 + len(name)) + name
    device_path = hd + file_node + bytes([0x7F, 0xFF, 4, 0])
    return struct.pack("<IH", 1, len(device_path)) + description.encode("utf-16-le") + b"\0\0" + device_path


def arm(root, args):
    oc, ocx = paths(root)
    tool_dir = os.path.join(oc, "Tools", TOOL_DIR)
    if not os.path.isdir(ocx) or not os.path.isdir(tool_dir):
        raise SystemExit("rode o subcomando make antes.")
    if args.disk:
        guid, start, size = part_info(args.disk, args.part)
    elif args.part_guid and args.part_start is not None and args.part_size is not None:
        guid, start, size = args.part_guid, args.part_start, args.part_size
    else:
        raise SystemExit("informe --disk e --part, ou --part-guid, --part-start e --part-size.")
    option = load_option("fzmac experimento de video", args.part, guid, start, size, "\\EFI\\OCX\\OpenCore.efi")
    script = nsh([
        "@echo -off",
        'echo "fzmacinstall: EXPERIMENTO de video."',
        'echo "O proximo boot usa a pasta EFI\\OCX, so uma vez."',
        'echo "Se a tela ficar preta, travar ou cair: segure o botao de energia, ligue de novo."',
        'echo "O boot seguinte volta sozinho para a configuracao normal."',
        "setvar Boot%04X -guid %s -bs -rt -nv =H%s" % (BOOT_NUM, EFI_GLOBAL, option.hex().upper()),
        "if %lasterror% ne 0 then",
        '  echo "ERRO ao gravar a opcao de boot. Nada foi mudado. Use a configuracao normal."',
        "  pause", "  exit", "endif",
        "setvar BootNext -guid %s -bs -rt -nv =H%s" % (EFI_GLOBAL, struct.pack("<H", BOOT_NUM).hex().upper()),
        "if %lasterror% ne 0 then",
        '  echo "ERRO ao gravar BootNext. Nada foi mudado. Use a configuracao normal."',
        "  pause", "  exit", "endif",
        'echo "Pronto. Reiniciando em 30 segundos..."',
        "stall 30000000", "reset"])
    with open(os.path.join(tool_dir, "startup.nsh"), "w", newline="") as handle:
        handle.write(script)
    print("  Experimento armado para a partição %d (GUID %s, início %d, %d setores)." % (args.part, guid, start, size))
    print("  No menu do OpenCore, escolha: %s" % TOOL_NAME)


def main():
    parser = argparse.ArgumentParser(description="Experimento de vídeo em instância separada do OpenCore")
    sub = parser.add_subparsers(dest="cmd")
    m = sub.add_parser("make")
    m.add_argument("--efi", required=True)
    m.add_argument("--gpu-path", required=True, help="caminho da GPU, ex.: PciRoot(0x1)/Pci(0x8,0x1)/Pci(0x0,0x0)")
    m.add_argument("--device-id", required=True, help="device-id a apresentar, 4 dígitos hex, ex.: 73ff")
    m.add_argument("--model", default="", help="nome a mostrar no sistema")
    m.add_argument("--rom", default="", help="arquivo de BIOS de vídeo para ATY,bin_image")
    m.add_argument("--weg", default="", help="pasta WhateverGreen.kext a incluir só no experimento")
    m.add_argument("--boot-arg", action="append", default=[], help="argumento extra só do experimento (repetível)")
    m.add_argument("--drop-arg", action="append", default=[], help="argumento a retirar no experimento (repetível)")
    a = sub.add_parser("arm")
    a.add_argument("--efi", required=True)
    a.add_argument("--disk", default="", help="disco ou imagem onde a EFI está gravada (lido com sgdisk -i)")
    a.add_argument("--part", type=int, default=1, help="número da partição EFI")
    a.add_argument("--part-guid", default="")
    a.add_argument("--part-start", type=int)
    a.add_argument("--part-size", type=int)
    r = sub.add_parser("remove")
    r.add_argument("--efi", required=True)
    args = parser.parse_args()
    if args.cmd == "make":
        make(args.efi, args)
    elif args.cmd == "arm":
        arm(args.efi, args)
    elif args.cmd == "remove":
        remove(args.efi)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
