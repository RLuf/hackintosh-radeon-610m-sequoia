<div align="center">

# Hackintosh Radeon 610M — macOS Sequoia

**Aceleração Metal 3D e Composição de Tela pela GPU na AMD Radeon 610M (Mendocino) no macOS Sequoia 15.8.1**

[![macOS Sequoia 15.8.1](https://img.shields.io/badge/macOS-Sequoia%2015.8.1-000000?style=flat-square&logo=apple&logoColor=white)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![GPU AMD Radeon 610M](https://img.shields.io/badge/GPU-AMD%20Radeon%20610M%20(1002%3A1506)-ED1C24?style=flat-square&logo=amd&logoColor=white)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![Arquitetura RDNA 2 GC 10.3.7](https://img.shields.io/badge/Arq-RDNA%202%20%C2%B7%20GC%2010.3.7%20%C2%B7%202%20CUs-ED1C24?style=flat-square)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![Aceleração Metal 3D + WindowServer](https://img.shields.io/badge/Accel-Metal%203D%20%2B%20WindowServer-2ea043?style=flat-square)](https://github.com/RLuf/hackintosh-radeon-610m-sequoia)
[![Licença GPL-2.0](https://img.shields.io/badge/Licen%C3%A7a-GPL--2.0-0969da?style=flat-square)](LICENSE)

🌐 [English](README.md) · **Português (Brasil)**

<!-- Coloque o print ou GIF principal aqui antes do anúncio, ex.: ![macOS Sequoia na Radeon 610M](docs/screenshot.png) -->

</div>

---

## Visão Geral

Em **26/11/2026**, a **renderização Metal 3D** e a **composição de tela pelo WindowServer na GPU** rodaram em bare metal pela primeira vez na **AMD Radeon 610M (`1002:1506`)** em um **Lenovo IdeaPad 1 82X5 (Ryzen 5 7520U)** com **macOS Sequoia 15.8.1**.

Por padrão, o macOS não traz nenhum suporte à família Mendocino (`GC 10.3.7`): o comando `ioreg -c IOAccelerator` sobe vazio, nenhum kext da Apple lista o device-id `0x1506`, e os projetos da comunidade para APUs AMD — como o NootedRed (Vega) e o Radeonized para a 680M ([`src/common/rb_gpuname.h:57`](https://github.com/FranciumOS-org/Radeonized/blob/a5399fe1f3f0338dce3996c6638e78822c5d942c/src/common/rb_gpuname.h#L57-L58)) — não suportam a 610M.

Este projeto aplica uma **série de 48 patches** sobre o **RembrandtGfx** (plugin do [Lilu](https://github.com/acidanthera/Lilu)) para adaptar a pilha **Navi 23** da Apple (`AMDRadeonX6000`, `AMDRadeonX6000Framebuffer`, `AMDRadeonX6000HWLibs` e o driver Metal em espaço de usuário) em tempo de execução ao silício bem menor da Mendocino — mapeando cada diferença boot a boot, cruzando medições reais da placa com o `amdgpu` do Linux, o Mesa e a desmontagem dos binários da Apple.

### Destaques Medidos

| Métrica | Resultado Medido |
|---|---|
| **3D e Computação** | **`324,2 GFLOPS`** (shader de computação FP32 no `metal-bench`), fundos animados 3D *Sequoia* e *Macintosh*, OpenGL 3D |
| **Clocks da GPU** | **`400–533 MHz`** ocioso → **`1900 MHz`** de pico sob carga (`GFXCLK` via SMU `13.0.8`) |
| **Eficiência do Compositor** | Uso de CPU do `WindowServer` caiu de **~49%** (renderização por software) para **~3%** (composição por Metal na GPU), **`0`** erros de GPU e **`0`** kernel panics |
| **Latência de Interrupção** | **`~1,8 ms`** por ida e volta de comando Metal (anel `IH` / `MSI`) |

---

## Perfil do Hardware e Silício

| Componente | Especificação |
|---|---|
| **Máquina** | Lenovo IdeaPad 1 (`82X5`), AMD Ryzen 5 7520U (Mendocino) |
| **PCI ID e Alvo de Spoof** | `1002:1506` → apresentado como `1002:73ff` (Navi 23 / AMD Radeon RX 6600) |
| **Núcleo Gráfico** | **GC 10.3.7** — `1 SE`, `1 SA`, `1 RB`, **`2 Compute Units`** (`TTL: SE=1, SA/SE=1, numActiveRB=1, numActiveCU=2`) |
| **Motor de Tela** | **DCN 3.1.6** — painel interno eDP BOE `NT156WHM-N44` (`1366×768 @ 60 Hz`) |
| **Firmware** | **PSP e SMU 13.0.8** |
| **Memória de Vídeo** | `2048 MB` reservados da RAM do sistema (UMA) |

---

## Recursos e Marcos Alcançados

> **Sobre a numeração:** Os rótulos gravados pelo kext no log (`kext patch 00NN`) coincidem com os nomes dos arquivos até `0028`, e passam a divergir a partir do `0028b` ao longo dos **48 arquivos de patch** (`0001`–`0048`, chegando ao rótulo `0041`). A tabela completa está no [`CHANGELOG.md`](CHANGELOG.md).

| Recurso | Estado | Rótulo do Kext |
|---|---|---|
| Firmware da GPU (`PSP`, `RLC`, `TMR`) e tradução de endereços (`GART`, `UTCL2`) | ✅ | `0020–0022` |
| Acelerador da Apple ligado (`powerUpHW`, motores `GFX` e `SDMA`) | ✅ | `0024` |
| Interrupções MSI e anel IH (~1,8 ms no Metal, subida automática no boot) | ✅ | `0025–0026` |
| Painel interno eDP herdando o modo do UEFI GOP (`1366×768 @ 60 Hz`) | ✅ | `0027–0028e` |
| Aceleração OpenGL 3D (Xadrez do macOS) | ✅ | `0034` |
| **Desenho 3D por Metal** (fundos animados *Macintosh* e *Sequoia*, shaders 3D/compute) | ✅ | **`0035`** |
| **Escalonamento Dinâmico de Clock via SMU** (`GFXCLK` chegando a **1900 MHz** sob carga) | ✅ | `0036` |
| **Painel Interno Composto pela GPU** (`AGDC`, temporização do `OTG0`, flip linear no `HUBP0`; `WindowServer` em ~3% de CPU) | ✅ | **`0037–0041`** |

---

## Mergulho Técnico

### 1. Como a Trava do Metal 3D nas 2 CUs Foi Resolvida (`0033` → `0035`)

O fundo animado travava a GPU sempre do mesmo jeito: o processador de comandos terminava a lista (IB) e ficava esperando o fim do desenho para sempre. Três medições isolaram a causa exata:

1. **`0033`**: Confirmou que os shaders na memória estavam íntegros e descartou problemas no caminho `HDP` (CPU até a VRAM).
2. **`0034`**: Mediu o estado da GPU no instante da trava — **zero ondas vivas**. O bloco lançador de ondas (`SPI`) nem chegava a iniciar.
3. **Metal da Apple contra o Mesa**: O driver Metal em espaço de usuário da Apple (`amdMtl_GFX10_InitStaticHwRegs`) liga a *oversubscription* do cache de parâmetros (`GE_PC_ALLOC = 0x3ff`) sem verificar `late_alloc`. Com apenas **2 CUs**, isso trava o lançamento de ondas; o Mesa (`radeonsi`) grava `0x7e` nessa placa.

O patch **`0035`** troca **18 bytes** de `amdMtl_GFX10_InitStaticHwRegs` no cache compartilhado `dyld` em tempo de carga para gravar `0x7e`, devolvendo imediatamente a animação 3D.

*(Nota técnica: `0x7e` desliga a oversubscription e também reduz o número de linhas do cache; o teste anterior no `0031`, com 256 linhas e a oversubscription ainda ligada via `0x1ff`, continuou travando — apontando diretamente para a oversubscription.)*

### 2. Composição de Tela na GPU Sem o DAL da Apple (`0037` → `0041`)

Tirar o `WindowServer` da composição por software (~49% de CPU) exigiu conectar o Apple Graphics Device Control (`AGDC`) e o scanout físico diretamente ao bloco `DCN 3.1.6` da Mendocino:

```text
createAgdc (-rmbagdc)
 └─ capacidade de scaler 0x711
     └─ getLinkConfig 0x921 (IODetailedTimingInformationV2 montada do OTG0: 1366×768, total 1592×798, 60 Hz, 76.224.960 Hz)
         └─ transações 'amtr' e leitura contínua de flip+0x08 (-rmbgopflip)
             └─ scanout físico no HUBP0 (0x3aca / 0x3acb)
```

Com superfícies em `64KB_R_X`, o painel repetia linhas porque o UEFI GOP havia deixado a configuração de requisição/swath/DET ajustada para modo linear. O patch `0047` (rótulo **`0041`**, `-rmbgoplinear`) força superfícies de tela (`ADDR2_SURFACE_FLAGS` bit `5`, `display`, conferido no `addrinterface.h` do Mesa) a saírem lineares em `getPreferredSwizzleMode2`, entregando composição Metal limpa no painel interno.

---

## Arquitetura e Configuração de Boot

```text
OpenCore (EFI/OC)
 ├─ DeviceProperties (GPU)
 │   ├─ device-id: 0x73ff (Navi 23)
 │   ├─ model: "AMD Radeon RX 6600"
 │   └─ ATY,bin_image: VBIOS nativa da Mendocino (102-MENDOCINO-006, 46.592 bytes)
 │                     com o device-id do cabeçalho PCIR trocado para 73ff
 ├─ boot-args: rmbstage=3 -rmbfbstubs -rmbirqauto -rmbgopfb -rmbpcalloc7e -rmbagdc -rmbgopflip -rmbgoplinear
 └─ Lilu + RembrandtGfx (48 patches sobre o upstream 87a01b5)
     ├─ estágio 3: firmware, memória e núcleo gráfico inicializados como no amdgpu do Linux
     ├─ 4a: framebuffers registrados e acelerador da Apple habilitado
     ├─ gopfb: painel interno herda o modo do UEFI GOP sem o DAL da Apple, ligado via AGDC + flip linear no HUBP0
     └─ umdpatch: correções em tempo de carga no driver Metal (cache dyld)
```

> [!WARNING]
> **Modificações experimentais de GPU em nível de kernel.** Este driver altera carregamento de firmware, tradução de memória e o comportamento do driver Metal em tempo de execução. Embora já rode na configuração principal (`EFI/OC`), mantenha sempre uma entrada alternativa do OpenCore intacta (`EFI/OC-NORMAL` ou backup em pendrive) ao testar ou atualizar patches.

---

## Mapa do Repositório

| Caminho | Conteúdo |
|---|---|
| [`docs/porte-610m/patches/`](docs/porte-610m/patches/) | Os 48 patches da série, aplicáveis com `git am` sobre o upstream `87a01b5` |
| [`docs/porte-610m/setup/build-mac.sh`](docs/porte-610m/setup/build-mac.sh) | Compila o kext nativamente no macOS 15.8.1 |
| [`CHANGELOG.md`](CHANGELOG.md) | Histórico detalhado patch a patch e correspondência de rótulos do kext |
| [`CREDITOS.md`](CREDITOS.md) | Auditoria completa de origens, atribuições e licenças |

---

## Créditos, Licenças e Repositórios Relacionados

- **RembrandtGfx** (driver base da Radeon 680M): [caoshiyuan0211-blip/winmax2-2022-6800u-hackintosh](https://github.com/caoshiyuan0211-blip/winmax2-2022-6800u-hackintosh) ([GPL-2.0](LICENSE)).
- **Radeonized** (driver da 680M): [FranciumOS-org/Radeonized](https://github.com/FranciumOS-org/Radeonized) (MIT) — lógica portada e achados usados na etapa da tela (temporização do `OTG0`, respostas do `AGDC`, leitura do quadro, superfícies lineares).
- **Lilu** e **OpenCore**: [acidanthera/Lilu](https://github.com/acidanthera/Lilu) e [acidanthera/OpenCorePkg](https://github.com/acidanthera/OpenCorePkg) (BSD-3-Clause).
- **Linux `amdgpu` e Mesa**: Referência de programação de hardware para Mendocino (`GC 10.3.7`, `DCN 3.1.6`, `GE_PC_ALLOC`, `ADDR2_SURFACE_FLAGS`).
- **Autores do porte 610M**: **RLuf** e **opus-fable**. Origens e avisos exigidos na íntegra: [`CREDITOS.md`](CREDITOS.md).

### Repositórios Relacionados

- `tools/fzmacinstall` (submódulo): Instalador que prepara o disco externo com recovery da Apple e OpenCore sob medida usado para instalar o macOS nesta máquina.
- [`RLuf/fzmacscript`](https://github.com/RLuf/fzmacscript): Onde o porte começou (ramo `claude/loving-turing-h91cjh`), junto com os scripts de Mac OS X legado no Proxmox.
