#!/bin/sh
# Instala o UniSpace para o usuário atual (sem sudo): copia a pasta para ~/.local/opt/UniSpace e cria o atalho
# no menu de aplicativos. Uso, dentro da pasta extraída:  ./instalar.sh        (ou ./instalar.sh --remover)
set -eu

SRC=$(cd "$(dirname "$0")" && pwd)
DEST="$HOME/.local/opt/UniSpace"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP="$APPS/unispace.desktop"

if [ "${1:-}" = "--remover" ]; then
    rm -f "$DESKTOP"
    rm -rf "$DEST"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true
    echo "UniSpace removido. Seus dados continuam em ${XDG_DATA_HOME:-$HOME/.local/share}/UniSpace."
    exit 0
fi

if [ "$SRC" != "$DEST" ]; then
    rm -rf "$DEST"
    mkdir -p "$DEST"
    cp -a "$SRC/." "$DEST/"
fi
chmod +x "$DEST/UniSpace"

mkdir -p "$APPS"
sed -e "s|@EXEC@|\"$DEST/UniSpace\"|" -e "s|@ICON@|$DEST/_internal/assets/icon.png|" \
    "$DEST/unispace.desktop.in" > "$DESKTOP"
chmod +x "$DESKTOP"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true

echo "UniSpace instalado em $DEST"
echo "Abra pelo menu de aplicativos (procure por UniSpace) ou rode: $DEST/UniSpace"
