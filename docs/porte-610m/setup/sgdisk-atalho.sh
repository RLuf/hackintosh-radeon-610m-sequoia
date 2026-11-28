#!/bin/bash
# O sgdisk 1.0.9 do Deepin 25 falha com a libpopt 1.19: perde o nome do disco e aborta com
# "Unable to open device '' for writing". Este atalho usa o sgdisk 1.0.10 do ambiente Ubuntu
# em /mnt/dados/fzwork/build-root (apt-get install gdisk dentro dele).
# Instalação: copiar para /mnt/dados/fzwork/bin/sgdisk, chmod +x, e pôr essa pasta na frente do PATH.
R=/mnt/dados/fzwork/build-root
for m in proc sys dev; do mountpoint -q $R/$m || mount --bind /$m $R/$m; done
exec chroot $R /usr/sbin/sgdisk "$@"
