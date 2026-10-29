"""Gera o executável Linux e o coloca nesta pasta: UniSpace + pasta _internal (bibliotecas).

Uso (no Linux; o PyInstaller não gera executável para outro sistema):
      .venv/bin/python build_linux.py            gera o executável
      .venv/bin/python build_linux.py --tar      gera o executável e o UniSpace-linux.tar.gz para envio
      .venv/bin/python build_linux.py --tar-only só cria o UniSpace-linux.tar.gz com o executável atual

Etapas: confere se o app está fechado, roda o PyInstaller (UniSpace.spec) numa pasta temporária, substitui o
UniSpace e a pasta _internal desta pasta, apaga os arquivos temporários e executa o autodiagnóstico.
Os dados do usuário (~/.local/share/UniSpace) não são tocados.
Para o executável funcionar em mais distribuições, gere na distribuição mais antiga que quiser atender (glibc).
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXE = ROOT / "UniSpace"
INTERNAL = ROOT / "_internal"
WORK = ROOT / "build"
STAGE = WORK / "_dist"
TAR = ROOT / "UniSpace-linux.tar.gz"
PACKAGING = ROOT / "packaging"

LEIA_ME = """UniSpace - Seu espaço na Unilavras (Linux)
==========================================

Reúne em um só lugar as atividades e prazos da Sala de Aula Virtual Unilavras (em um quadro de atividades),
notas e AVIN, encontros virtuais, os eventos da Unilavras e a sua agenda pessoal. Funciona no seu computador:
seus dados e sua senha ficam somente nele.

COMO USAR
1. Extraia o arquivo:  tar -xzf UniSpace-linux.tar.gz
2. Instale (cria o atalho no menu de aplicativos, sem precisar de sudo):
       cd UniSpace && ./instalar.sh
   Ou rode direto, sem instalar:  ./UniSpace
3. Na tela inicial, informe seu usuário e senha do portal do aluno e clique em
   "Conectar e buscar atividades".
Para desinstalar:  ~/.local/opt/UniSpace/instalar.sh --remover   (seus dados são mantidos)

REQUISITOS
- Uma distribuição Linux recente de 64 bits (Ubuntu 22.04+, Debian 12+, Fedora 38+ ou equivalente), com
  ambiente gráfico X11 ou Wayland.
- Um navegador: o aplicativo usa, nesta ordem, o primeiro que encontrar entre Google Chrome (recomendado),
  Chromium, Mozilla Firefox e Microsoft Edge.
- Um chaveiro do sistema para guardar a senha: GNOME Keyring (já vem no GNOME, Ubuntu, Fedora e Mint) ou
  KWallet (KDE). Em outros ambientes, instale o pacote gnome-keyring.
- Se a janela não abrir e aparecer um erro sobre "xcb", instale a biblioteca que falta:
       Ubuntu/Debian: sudo apt install libxcb-cursor0
       Fedora:        sudo dnf install xcb-util-cursor

AVISOS
- Mantenha o UniSpace sempre junto da pasta "_internal" (ela contém as bibliotecas do programa).
- Sua senha fica no chaveiro do sistema, nunca em arquivos. O aplicativo apenas lê o portal: nada é enviado
  ou alterado lá.
- Toda semana, na primeira vez que você abrir o app a partir de segunda-feira, ele atualiza tudo sozinho.
"""


def app_running() -> bool:
    out = subprocess.run(["pgrep", "-x", "UniSpace"], capture_output=True, text=True)
    return out.returncode == 0


def _add(tar: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mode = len(data), mode
    tar.addfile(info, io.BytesIO(data))


def make_tar() -> Path:
    """UniSpace-linux.tar.gz com a pasta UniSpace/ (executável, _internal, instalador, LEIA-ME.txt)."""
    if not (EXE.exists() and INTERNAL.exists()):
        raise SystemExit("Executável não encontrado. Rode primeiro: build_linux.py")
    tmp = TAR.with_suffix(".gz.tmp")
    with tarfile.open(tmp, "w:gz", compresslevel=9) as t:
        t.add(EXE, "UniSpace/UniSpace")
        t.add(INTERNAL, "UniSpace/_internal")
        _add(t, "UniSpace/instalar.sh", (PACKAGING / "instalar.sh").read_bytes(), 0o755)
        _add(t, "UniSpace/unispace.desktop.in", (PACKAGING / "unispace.desktop.in").read_bytes(), 0o644)
        _add(t, "UniSpace/LEIA-ME.txt", LEIA_ME.encode("utf-8"), 0o644)
    with tarfile.open(tmp) as t:                         # confere a integridade antes de substituir
        names = t.getnames()
        if "UniSpace/UniSpace" not in names:
            raise SystemExit("Pacote incompleto.")
    tmp.replace(TAR)
    print(f"Pacote para envio: {TAR}  ({TAR.stat().st_size / 1_048_576:.0f} MB)")
    return TAR


def main() -> int:
    if not sys.platform.startswith("linux"):
        print("Rode este script no Linux: o PyInstaller só gera executável para o sistema em que está rodando.")
        return 1
    if "--tar-only" in sys.argv:
        make_tar()
        return 0
    if app_running():
        print("Feche o UniSpace antes de gerar o executável (o arquivo atual está em uso).")
        return 1
    print("Gerando o executável…")
    r = subprocess.run([sys.executable, "-m", "PyInstaller", str(ROOT / "UniSpace.spec"), "--noconfirm",
                        "--distpath", str(STAGE), "--workpath", str(WORK / "_work")], cwd=ROOT)
    built = STAGE / "UniSpace"
    if r.returncode != 0 or not (built / "UniSpace").exists():
        print("Falha ao gerar o executável.")
        return 1

    # substitui a versão anterior
    if EXE.exists():
        EXE.unlink()
    if INTERNAL.exists():
        shutil.rmtree(INTERNAL)
    shutil.move(str(built / "UniSpace"), EXE)
    shutil.move(str(built / "_internal"), INTERNAL)
    shutil.rmtree(WORK, ignore_errors=True)

    print("Conferindo o executável (navegador + portal)…")
    d = subprocess.run([str(EXE), "--diagnostico"])
    if d.returncode != 0:
        print(f"O executável foi gerado, mas o autodiagnóstico falhou (código {d.returncode}).")
        return d.returncode
    size = sum(f.stat().st_size for f in INTERNAL.rglob("*") if f.is_file()) + EXE.stat().st_size
    print(f"Pronto: {EXE}  (+ pasta _internal, {size / 1_048_576:.0f} MB no total)")
    if "--tar" in sys.argv:
        make_tar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
