# Créditos, origens e licenças

Este projeto é um trabalho derivado e o diz com todas as letras. Conferência feita em 26/11/2026, comparando cada linha de código que a série acrescenta (1.380 linhas de 38 caracteres ou mais, nos 47 patches de código; o 48º só traz o aviso de terceiros) com os códigos de terceiros consultados.

## Base: RembrandtGfx (GPL-2.0)

- Origem: [caoshiyuan0211-blip/winmax2-2022-6800u-hackintosh](https://github.com/caoshiyuan0211-blip/winmax2-2022-6800u-hackintosh), commit `87a01b51c4a16123f88a50cfe9c4f85990b7c2cc` (15/11/2026).
- É o driver da Radeon 680M sobre o qual toda a série de patches é aplicada. O porte para a 610M é obra derivada e segue a mesma licença, **GPL-2.0** (arquivo `LICENSE`).
- Os patches movem e alteram código do upstream; por isso 46 linhas da série são idênticas às de outro derivado do mesmo upstream (`wzh4869/Radeon-680M-Hackintosh`). Todas as 46 já existem no upstream `87a01b5`: não houve cópia desse outro projeto.

## Radeonized (MIT)

- Origem: [FranciumOS-org/Radeonized](https://github.com/FranciumOS-org/Radeonized), commit `a5399fe1f3f0338dce3996c6638e78822c5d942c` (22/11/2026). Driver para a Radeon 680M/660M; não suporta a 610M.
- Linhas idênticas: 1 (uma chamada padrão da API do Lilu). Não há cópia literal, mas há **lógica portada e achados usados**, com conhecimento de causa:
  - `buildV2` (patch 0045): reescrita, no estilo deste projeto, do conversor `rb_otg_to_v2` (`src/common/rb_otg.h`), com as mesmas checagens. Diferença: os totais usam registrador + 1, como o Linux programa.
  - Resposta do AGDC `0x921` (patch 0045): layout de `rb_agdc_link_config` (`src/common/rb_agdc.h`), conferido também na desmontagem do binário da Apple.
  - Resposta do AGDC `0x711`, tipo scaler (patch 0042): a entrada "sem escalar" e a constatação de que só esse tipo é obrigatório.
  - Leitura do endereço do quadro em `flip+0x08` a cada tique (patch 0044): a ideia do `hubpPoll`.
  - Superfícies lineares por `getPreferredSwizzleMode2` (patch 0047): o Radeonized roteia a mesma função para forçar linear em todas as superfícies; aqui só nas de tela.
- Aviso exigido pela licença MIT, reproduzido na íntegra:

```
MIT License

Copyright (c) 2026 RembrandtGPU contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Referências de como a placa deve ser programada (sem cópia de código)

- **Linux `amdgpu`** (v6.12; GPL-2.0 e MIT conforme cada arquivo): offsets e campos dos registradores (`dcn_3_1_6_offset.h`, `dcn_3_1_6_sh_mask.h`), sequências documentadas (`hubp3_program_tiling`, programação do OPTC, PSP, GFX). Linhas idênticas: 0.
- **Mesa** (MIT): `addrinterface.h` do AddrLib (ordem dos bits de `ADDR2_SURFACE_FLAGS`) e os valores do `radeonsi` para a Mendocino (`GE_PC_ALLOC`). Só leitura.
- **IOGraphics-599** (Apple, APSL 2.0): código-fonte público lido para a ordem das chamadas de `IOFramebuffer::open` e o comportamento do `IOBootNDRV`. Linhas idênticas: 0.

## Ferramentas

- [Lilu](https://github.com/acidanthera/Lilu) e [OpenCore](https://github.com/acidanthera/OpenCorePkg) (acidanthera, BSD-3-Clause). O kext é compilado contra o Lilu; nenhum dos dois é redistribuído aqui.

## Apple

- Nenhum código nem binário da Apple é distribuído. O kext corrige, em tempo de execução, os drivers que já estão no macOS do usuário. O que se sabe desses drivers veio de desmontagem para fins de interoperabilidade com hardware que a Apple não suporta.

## Situação das pendências de licença (26/11/2026, 23:55)

1. **Feito.** O aviso do Radeonized (copyright e permissão, na íntegra) está no código-fonte, junto de `buildV2` em `display.cpp` (patch 0048, só comentário).
2. **Feito.** O binário compilado `src/RembrandtGfx/RembrandtGfx`, que tinha entrado por engano no patch 0043, saiu da série. A série tem 48 arquivos, nenhum binário, e foi conferida: aplica com `git am` sobre o upstream `87a01b5` e compila (387 símbolos indefinidos, como antes). O código é idêntico ao do kext 0041 testado; a única diferença na árvore é a ausência do binário e o comentário.
3. Continua valendo: não publicar a BIOS de vídeo da máquina nem firmware da AMD no repositório (hoje não há nenhum dos dois).
4. **Antes de tornar este repositório público:** o histórico do git ainda guarda a versão antiga do patch 0043, com o binário dentro (commits até `125bae0` e a tag `checkpoint-tela-0041`). Publicar exige reescrever esse histórico ou começar um repositório novo a partir do estado limpo.

## Método

Cada correção foi conferida na fonte (desmontagem, Linux, Mesa), revisada por um segundo agente e confrontada no Modo IA do Google antes de cada reinício. Trabalho de Roger Luft, autor do projeto, com o Claude, da Anthropic.

## Firmware da AMD

Versões antigas do histórico deste repositório trazem um kext compilado por engano, que embute firmware
da AMD para a 610M (`gc_10_3_7_*`, `sdma_5_2_7`, `psp_13_0_8_toc`, `dcn_3_1_6_dmcub`, do `linux-firmware`).
Esse firmware é da AMD e é redistribuído só em forma binária, sob a licença em [`LICENSE.amdgpu`](LICENSE.amdgpu)
(cópia de `LICENSES/LICENSE.amdgpu` do `linux-firmware`).
