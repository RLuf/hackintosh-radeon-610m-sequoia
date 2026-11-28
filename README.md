<div align="center">

# Hackintosh Radeon 610M — macOS Sequoia

**Metal 3D & GPU-Composited Display Acceleration on AMD Radeon 610M (Mendocino) under macOS Sequoia 15.8.1**

[![macOS Sequoia 15.8.1](https://img.shields.io/badge/macOS-Sequoia%2015.8.1-000000?style=flat-square&logo=apple&logoColor=white)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![GPU AMD Radeon 610M](https://img.shields.io/badge/GPU-AMD%20Radeon%20610M%20(1002%3A1506)-ED1C24?style=flat-square&logo=amd&logoColor=white)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![Architecture RDNA 2 GC 10.3.7](https://img.shields.io/badge/Arch-RDNA%202%20%C2%B7%20GC%2010.3.7%20%C2%B7%202%20CUs-ED1C24?style=flat-square)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![Acceleration Metal 3D + WindowServer](https://img.shields.io/badge/Accel-Metal%203D%20%2B%20WindowServer-2ea043?style=flat-square)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![License GPL-2.0](https://img.shields.io/badge/License-GPL--2.0-0969da?style=flat-square)](LICENSE)

🌐 **English** · [Português (Brasil)](README.pt-BR.md)

<!-- Drop hero screenshot / GIF here before launch, e.g. ![macOS Sequoia on Radeon 610M](docs/screenshot.png) -->

</div>

---

## Overview

On **November 26, 2026**, full **Metal 3D rendering** and **GPU-composited WindowServer display** ran bare-metal for the first time on the **AMD Radeon 610M (`1002:1506`)** inside a **Lenovo IdeaPad 1 82X5 (Ryzen 5 7520U)** running **macOS Sequoia 15.8.1**.

Out of the box, macOS ships zero support for AMD Mendocino (`GC 10.3.7`): `ioreg -c IOAccelerator` comes up empty, no Apple kext matches `0x1506`, and existing community AMD APU efforts — such as NootedRed (Vega) and Radeonized for the 680M ([`src/common/rb_gpuname.h:57`](https://github.com/FranciumOS-org/Radeonized/blob/a5399fe1f3f0338dce3996c6638e78822c5d942c/src/common/rb_gpuname.h#L57-L58)) — do not support the 610M.

This project applies a **48-patch series** on top of **RembrandtGfx** (a [Lilu](https://github.com/acidanthera/Lilu) kernel plugin) to adapt Apple's **Navi 23** graphics stack (`AMDRadeonX6000`, `AMDRadeonX6000Framebuffer`, `AMDRadeonX6000HWLibs`, and the user-space Metal driver) at runtime to Mendocino's much smaller silicon — discovered boot by boot by cross-checking live hardware measurements against Linux `amdgpu`, Mesa, and Apple binary disassembly.

### Measured Highlights

| Metric | Measured Result |
|---|---|
| **3D & Compute** | **`324.2 GFLOPS`** (`metal-bench` FP32 compute shader), animated 3D *Sequoia* & *Macintosh* wallpapers, OpenGL 3D |
| **GPU Clocks** | **`400–533 MHz`** idle → **`1900 MHz`** peak boost under load (`GFXCLK` via SMU `13.0.8`) |
| **Compositor Efficiency** | `WindowServer` CPU dropped from **~49%** (software rendering) to **~3%** (Metal hardware composition), **`0`** GPU errors, **`0`** kernel panics |
| **Interrupt Latency** | **`~1.8 ms`** Metal command round-trip (`IH` ring / `MSI`) |

---

## Hardware & Silicon Profile

| Component | Specification |
|---|---|
| **Host Machine** | Lenovo IdeaPad 1 (`82X5`), AMD Ryzen 5 7520U (Mendocino) |
| **PCI ID & Spoof Target** | `1002:1506` → spoofed as `1002:73ff` (Navi 23 / AMD Radeon RX 6600) |
| **Graphics Core** | **GC 10.3.7** — `1 SE`, `1 SA`, `1 RB`, **`2 Compute Units`** (`TTL: SE=1, SA/SE=1, numActiveRB=1, numActiveCU=2`) |
| **Display Engine** | **DCN 3.1.6** — internal eDP panel BOE `NT156WHM-N44` (`1366×768 @ 60 Hz`) |
| **Firmware** | **PSP & SMU 13.0.8** |
| **Video Memory** | `2048 MB` UMA reserved from system RAM |

---

## Capabilities & Milestone Matrix

> **Patch numbering note:** The kext log label (`kext patch 00NN`) matches the patch filenames up to `0028`, and diverges from `0028b` onward across the **48 patch files** (`0001`–`0048`, up to kext label `0041`). See [`CHANGELOG.md`](CHANGELOG.md) for the complete mapping.

| Capability | Status | Kext Label |
|---|---|---|
| GPU Firmware (`PSP`, `RLC`, `TMR`) & Virtual Memory (`GART`, `UTCL2`) | ✅ | `0020–0022` |
| Apple Hardware Accelerator (`powerUpHW`, `GFX` & `SDMA` engines) | ✅ | `0024` |
| MSI Interrupts & IH Ring (~1.8 ms Metal completion, automatic boot init) | ✅ | `0025–0026` |
| Internal eDP Panel via UEFI GOP Mode Inheritance (`1366×768 @ 60 Hz`) | ✅ | `0027–0028e` |
| OpenGL 3D Acceleration (macOS Chess) | ✅ | `0034` |
| **Metal 3D Rendering** (animated *Macintosh* & *Sequoia* wallpapers, 3D/compute shaders) | ✅ | **`0035`** |
| **SMU Dynamic Clock Boost** (`GFXCLK` scaling up to **1900 MHz** under load) | ✅ | `0036` |
| **GPU-Composited Internal Display** (`AGDC`, `OTG0` timings, `HUBP0` linear page-flip; `WindowServer` ~3% CPU) | ✅ | **`0037–0041`** |

---

## Technical Deep Dives

### 1. Solving the 2-CU Metal 3D Hang (`0033` → `0035`)

Animated 3D scenes originally locked up the GPU the exact same way every time: the command processor finished the IB and waited forever for draw completion. Three targeted measurements isolated the root cause:

1. **`0033`**: Confirmed shader binaries in memory were intact and ruled out CPU-to-VRAM `HDP` flush issues.
2. **`0034`**: Sampled live GPU state during the hang — **zero active waves** on the GPU. The `SPI` wave-launch block never even started.
3. **Apple Metal vs. Mesa**: Apple's user-space Metal driver (`amdMtl_GFX10_InitStaticHwRegs`) enables parameter-cache oversubscription (`GE_PC_ALLOC = 0x3ff`) without checking `late_alloc`. With only **2 CUs**, that deadlocks wave launch; Mesa (`radeonsi`) programs `0x7e` on Mendocino.

Patch **`0035`** rewrites **18 bytes** of `amdMtl_GFX10_InitStaticHwRegs` in the `dyld` shared cache at load time to emit `0x7e`, immediately bringing 3D rendering back to life.

*(Technical note: `0x7e` disables oversubscription and reduces cache lines; the earlier `0031` test with 256 lines and oversubscription still enabled via `0x1ff` continued to hang, pointing directly to oversubscription.)*

### 2. GPU-Composited Display Without Apple DAL (`0037` → `0041`)

Getting `WindowServer` off ~49% CPU software compositing required wiring the Apple Graphics Device Control (`AGDC`) and physical display scanout path directly to Mendocino's `DCN 3.1.6` hardware:

```text
createAgdc (-rmbagdc)
 └─ scaler capability 0x711
     └─ getLinkConfig 0x921 (IODetailedTimingInformationV2 built live from OTG0: 1366×768, total 1592×798, 60 Hz, 76,224,960 Hz)
         └─ 'amtr' transactions & flip+0x08 polling (-rmbgopflip)
             └─ HUBP0 (0x3aca / 0x3acb) physical scanout
```

With tiled `64KB_R_X` surfaces, the panel repeated scanlines because UEFI GOP had initialized request/swath/DET state for linear scanout. Patch `0047` (kext label **`0041`**, `-rmbgoplinear`) forces display surfaces (`ADDR2_SURFACE_FLAGS` bit `5`, `display`, verified against Mesa's `addrinterface.h`) to linear mode inside `getPreferredSwizzleMode2`, delivering clean, tear-free Metal composition on the internal panel.

---

## Architecture & Boot Configuration

```text
OpenCore (EFI/OC)
 ├─ DeviceProperties (GPU)
 │   ├─ device-id: 0x73ff (Navi 23)
 │   ├─ model: "AMD Radeon RX 6600"
 │   └─ ATY,bin_image: native Mendocino VBIOS (102-MENDOCINO-006, 46,592 bytes)
 │                     with PCIR header device-id patched to 73ff
 ├─ boot-args: rmbstage=3 -rmbfbstubs -rmbirqauto -rmbgopfb -rmbpcalloc7e -rmbagdc -rmbgopflip -rmbgoplinear
 └─ Lilu + RembrandtGfx (48 patches over upstream 87a01b5)
     ├─ stage 3: GPU firmware, memory & graphics core initialized per Linux amdgpu
     ├─ 4a: framebuffers registered & Apple hardware accelerator enabled
     ├─ gopfb: internal panel inherits UEFI GOP mode without Apple DAL, wired via AGDC + HUBP0 linear flip
     └─ umdpatch: runtime dyld shared-cache fixes for Apple's user-space Metal driver
```

> [!WARNING]
> **Experimental kernel-level GPU modifications.** This driver modifies GPU firmware loading, memory translation, and runtime Metal driver behavior. Although now capable of running as the main `EFI/OC` boot configuration, always keep a clean fallback OpenCore entry (`EFI/OC-NORMAL` or a bootable USB backup) ready when testing or updating patches.

---

## Repository Map

| Path | Contents |
|---|---|
| [`docs/porte-610m/patches/`](docs/porte-610m/patches/) | All 48 patches in the series, applicable via `git am` onto upstream `87a01b5` |
| [`docs/porte-610m/setup/build-mac.sh`](docs/porte-610m/setup/build-mac.sh) | Builds the kext natively on macOS 15.8.1 |
| [`CHANGELOG.md`](CHANGELOG.md) | Detailed patch-by-patch changelog and kext label mapping |
| [`CREDITOS.md`](CREDITOS.md) | Full origins, attributions, and license compliance audit |

---

## Credits, Licenses & Related Repositories

- **RembrandtGfx** (Radeon 680M base driver): [caoshiyuan0211-blip/winmax2-2022-6800u-hackintosh](https://github.com/caoshiyuan0211-blip/winmax2-2022-6800u-hackintosh) ([GPL-2.0](LICENSE)).
- **Radeonized** (680M driver): [FranciumOS-org/Radeonized](https://github.com/FranciumOS-org/Radeonized) (MIT) — ported logic and findings used in the display stage (`OTG0` timings, `AGDC` responses, framebuffer readback, linear surface handling).
- **Lilu** & **OpenCore**: [acidanthera/Lilu](https://github.com/acidanthera/Lilu) & [acidanthera/OpenCorePkg](https://github.com/acidanthera/OpenCorePkg) (BSD-3-Clause).
- **Linux `amdgpu` & Mesa**: Hardware programming reference for Mendocino (`GC 10.3.7`, `DCN 3.1.6`, `GE_PC_ALLOC`, `ADDR2_SURFACE_FLAGS`).
- **610M Port Authors**: **RLuf** & **opus-fable**. Full origins and license notices: [`CREDITOS.md`](CREDITOS.md).

### Related Repositories

- `tools/fzmacinstall` (submodule): Installer that prepares an external drive with Apple recovery and custom OpenCore used to install macOS on this machine.
- [`RLuf/fzmacscript`](https://github.com/RLuf/fzmacscript): Where the port originated (`claude/loving-turing-h91cjh` branch), alongside legacy Mac OS X Proxmox scripts.
