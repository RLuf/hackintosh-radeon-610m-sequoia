# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Unreleased]

### Tela com composição pela GPU (26/11/2026, 23:19)

O painel interno passa a mostrar o que o WindowServer compõe por Metal. A CPU do WindowServer caiu de ~49 % (composição por software) para ~3 %; 0 erros de GPU, nenhum pânico. A série tem 47 arquivos (`docs/porte-610m/patches/`). Rótulos do kext a partir de 0040:

| arquivo | rótulo do kext | o que faz |
|---|---|---|
| 0040 | 0036 | `-rmbsmuclkwatch`: GFXCLK/FCLK a cada 2 s (medido 1900 MHz sob carga) |
| 0041 | 0037 | `-rmbagdc`: cria o AGDC da AMD (`createAgdc`), o WindowServer sai do renderizador de software |
| 0042 | 0038 | `-rmbagdc`: responde a capacidade de scaler (AGDC `0x711` tipo `0x10`); `-rmbgopflip`: reaponta o HUBP0 a cada `'amtr'` |
| 0043 | 0038b | flip aceita só endereço MC dentro do FB (scanout físico) |
| 0044 | 0038c | relê `flip+8` a cada tique (o compositor alterna superfícies sem nova `'amtr'`) |
| 0045 | 0039 | responde `getLinkConfig` (AGDC `0x921`) com a temporização real do OTG0: some o "Invalid end point size" e o WindowServer passa a mandar quadros |
| 0046 | 0040 | programa `DCSURF_ADDR_CONFIG`/`TILING_CONFIG` do HUBP0 com o tiling do flip (`hubp3_program_tiling` do Linux) |
| 0047 | 0041 | `-rmbgoplinear`: superfícies de tela (`ADDR2_SURFACE_FLAGS` bit 5, `display`) saem lineares em `getPreferredSwizzleMode2`, e o HUBP0 lê com a configuração linear que o GOP deixou |

Boot-args do estado que funciona: `rmbstage=3 -rmbfbstubs -rmbirqauto -rmbgopfb -rmbpcalloc7e -rmbagdc -rmbgopflip -rmbgoplinear` (mais os de medição). Ponto de restauração: tag `checkpoint-tela-0041`.

Caminho da imagem, medido: `createAgdc` → scaler `0x711` → temporização `0x921` (`IODetailedTimingInformationV2` montada do OTG0: 1366x768, total 1592x798, 60 Hz, 76.224.960 Hz) → transações `'amtr'` → endereço da superfície em `flip+0x08` → HUBP0 (`0x3aca/0x3acb`). Com a superfície em 64KB_R_X o painel repetia linhas (o GOP deixou requisição/swath/DET para linear); com as superfícies de tela lineares, imagem certa.

Método: cada correção foi confrontada no Modo IA do Google antes do reinício (trava `auto/fz-trava-ia.sh`) e conferida na fonte/desmontagem. O Modo IA errou detalhes que a fonte corrigiu (ex.: disse que `display` era o bit 8; é o bit 5, `addrinterface.h` do Mesa).

#### Tempo de trabalho com Roger Luft presente

Medido pelos horários das mensagens de Roger Luft nos históricos locais (sete chats, de 22/11 22:33 a 26/11 23:37, horário de Brasília). Um período de presença termina quando passam mais de 30 minutos sem mensagem dele; o tempo em que o agente ficou parado ou trabalhando sozinho não conta.

| dia | horas |
|---|---|
| 22/11 | 1,9 |
| 24/11 | 5,4 |
| 25/11 | 3,6 |
| 26/11 | 10,9 |
| **total** | **21,7** |

Com o critério mais estrito (pausa de 15 minutos encerra o período) o total é 17,5 h. Fora da conta, por não estarem neste disco: os chats da nuvem (linha de 23/11) e os anteriores a 22/11 (instalação do macOS).

**Tempo efetivo registrado por Roger Luft: 23 horas** (Roger Luft esteve presente o tempo todo; as medições acima são estimativas pelos horários das mensagens).

#### Créditos

Origens, licenças e o que foi portado de cada projeto: [`CREDITOS.md`](CREDITOS.md).

Limpeza de 26/11 23:55: a série passou a 48 arquivos. O 0048 só acrescenta, em comentário, o aviso de terceiros do Radeonized junto do código portado; o binário compilado que tinha entrado por engano no 0043 foi retirado. Nenhuma mudança de código: o kext testado continua sendo o de rótulo 0041 (`275f8a66…`).


### Metal 3D funcionando (26/11/2026)

A série de patches do RembrandtGfx para a Radeon 610M chegou a 39 arquivos. Com eles o macOS 15.8.1 sobe a GPU, liga o acelerador da Apple, usa interrupções, mostra o painel interno com o WindowServer e **desenha 3D por Metal**. Os arquivos em `docs/porte-610m/patches/` são numerados de 0001 a 0039. O rótulo que o kext mostra no log (`kext patch 00NN`) é igual ao número do arquivo até 0028; daí em diante é este:

| arquivo | rótulo do kext |
|---|---|
| 0029, 0030, 0031, 0032 | 0028b, 0028c, 0028d, 0028e |
| 0033, 0034, 0035, 0036 | 0029, 0030, 0031, 0032 |
| 0037, 0038, 0039 | 0033, 0034, 0035 |

#