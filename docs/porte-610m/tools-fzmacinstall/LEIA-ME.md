Cópias sem alteração de `fzmac_video_exp.py` e `fzmac_bootdiag.py` do repositório fzmacinstall, commit 752f0c7.
Estão aqui só para chegarem ao macOS da máquina de teste. A fonte continua sendo o fzmacinstall.

Diferença em relação ao fzmacinstall `752f0c7`, a pedido de Roger Luft em 24/11/2026: no `fzmac_video_exp.py` a pausa antes de reiniciar passou de 3 para 30 segundos (mensagem e `stall`). A mesma mudança precisa entrar no fzmacinstall para não se perder.
`kc-le.py` é desta pasta e não existe no fzmacinstall. Lê um kext de dentro do `SystemKernelExtensions.kc`: modos `syms`, `dis`, `imm`, `around`, `kexts`, `vers` e `tabs`. O `tabs` imprime as tabelas de versão que um seletor como `_gvm_get_ip_function` consulta.
