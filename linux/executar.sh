#!/bin/sh
# Abre o UniSpace pelo código-fonte. Na primeira vez, cria o ambiente Python (.venv) e instala as dependências;
# nas próximas, só abre o aplicativo. Uso:  ./executar.sh        (ou ./executar.sh --diagnostico)
set -eu

DIR=$(cd "$(dirname "$0")" && pwd)
VENV="$DIR/.venv"
PY="$VENV/bin/python"
STAMP="$VENV/.dependencias-ok"

if [ ! -x "$PY" ] || [ ! -f "$STAMP" ] || [ "$DIR/requirements.txt" -nt "$STAMP" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3 não encontrado. Instale o Python 3.12 ou superior e tente de novo."
        exit 1
    fi
    if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
        echo "O UniSpace precisa do Python 3.12 ou superior (encontrado: $(python3 --version 2>&1))."
        exit 1
    fi
    echo "Preparando o UniSpace pela primeira vez (pode levar alguns minutos)…"
    if [ ! -x "$PY" ]; then
        python3 -m venv "$VENV" || {
            echo "Não foi possível criar o ambiente Python. No Ubuntu/Debian, instale: sudo apt install python3-venv"
            exit 1
        }
    fi
    "$PY" -m pip install --quiet --upgrade pip
    # só o necessário para usar o app (pytest e pyinstaller ficam de fora)
    grep -viE '^(pytest|pyinstaller)==' "$DIR/requirements.txt" > "$VENV/requirements-app.txt"
    "$PY" -m pip install --quiet -r "$VENV/requirements-app.txt"
    touch "$STAMP"
fi

cd "$DIR"
exec "$PY" main.py "$@"
