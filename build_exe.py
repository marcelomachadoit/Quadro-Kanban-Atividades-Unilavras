"""Gera o executável e o coloca na raiz do projeto: UniSpace.exe + pasta _internal (bibliotecas).

Uso:  .\\.venv\\Scripts\\python.exe build_exe.py            gera o executável
      .\\.venv\\Scripts\\python.exe build_exe.py --zip      gera o executável e o UniSpace.zip para envio
      .\\.venv\\Scripts\\python.exe build_exe.py --zip-only só cria o UniSpace.zip com o executável atual

Etapas: confere se o app está fechado, roda o PyInstaller (UniSpace.spec) numa pasta temporária, substitui o
UniSpace.exe e a pasta _internal da raiz, apaga os arquivos temporários e executa o autodiagnóstico do .exe.
Os dados do usuário (%LOCALAPPDATA%\\UniSpace) não são tocados.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXE = ROOT / "UniSpace.exe"
INTERNAL = ROOT / "_internal"
WORK = ROOT / "build"
STAGE = WORK / "_dist"
ZIP = ROOT / "UniSpace.zip"

LEIA_ME = """UniSpace - Seu espaço na Unilavras
=================================

Reúne em um só lugar as atividades e prazos da Sala de Aula Virtual Unilavras (em um quadro de atividades),
notas e AVIN, encontros virtuais, os eventos da Unilavras e a sua agenda pessoal. Funciona no seu computador:
seus dados e sua senha ficam somente nele.

COMO USAR
1. Extraia este arquivo .zip (clique com o botão direito > "Extrair tudo...").
   Não abra o programa de dentro do .zip.
2. Abra a pasta "UniSpace" e dê dois cliques em UniSpace.exe.
3. Na tela inicial, informe seu usuário e senha do portal do aluno e clique em
   "Conectar e buscar atividades".

REQUISITOS
- Windows 10 ou 11.
- Um navegador: o aplicativo usa, nesta ordem, o primeiro que encontrar entre Google Chrome, Mozilla Firefox e
  Microsoft Edge (o Edge ja vem com o Windows) para ler o portal em segundo plano.

AVISOS
- Na primeira abertura, o Windows pode mostrar "O Windows protegeu o computador", porque o programa não tem
  assinatura digital. Clique em "Mais informações" e depois em "Executar assim mesmo".
- Mantenha o UniSpace.exe sempre junto da pasta "_internal" (ela contém as bibliotecas do programa).
- Sua senha fica guardada no Gerenciador de Credenciais do Windows, nunca em arquivos. O aplicativo apenas lê o
  portal: nada é enviado ou alterado lá.
- Toda semana, na primeira vez que você abrir o app a partir de segunda-feira, ele atualiza tudo sozinho.
- Quem já usava o UniKanban (nome antigo) não perde nada: dados e conta são levados para o UniSpace na
  primeira abertura.
"""


def app_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UniSpace.exe", "/NH"], capture_output=True, text=True)
    return "UniSpace.exe" in out.stdout


def make_zip() -> Path:
    """UniSpace.zip com a pasta UniSpace/ (UniSpace.exe + _internal + LEIA-ME.txt), pronto para envio."""
    if not (EXE.exists() and INTERNAL.exists()):
        raise SystemExit("Executável não encontrado. Rode primeiro: build_exe.py")
    tmp = ZIP.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(EXE, "UniSpace/UniSpace.exe")
        for f in sorted(INTERNAL.rglob("*")):
            if f.is_file():
                z.write(f, "UniSpace/_internal/" + f.relative_to(INTERNAL).as_posix())
        z.writestr("UniSpace/LEIA-ME.txt", LEIA_ME.replace("\n", "\r\n"))
    with zipfile.ZipFile(tmp) as z:                      # confere a integridade antes de substituir
        bad = z.testzip()
        if bad:
            raise SystemExit(f"Zip corrompido ({bad}).")
    tmp.replace(ZIP)
    print(f"Pacote para envio: {ZIP}  ({ZIP.stat().st_size / 1_048_576:.0f} MB)")
    return ZIP


def main() -> int:
    if "--zip-only" in sys.argv:
        make_zip()
        return 0
    if app_running():
        print("Feche o UniSpace antes de gerar o executável (o arquivo atual está em uso).")
        return 1
    print("Gerando o executável…")
    r = subprocess.run([sys.executable, "-m", "PyInstaller", str(ROOT / "UniSpace.spec"), "--noconfirm",
                        "--distpath", str(STAGE), "--workpath", str(WORK / "_work")], cwd=ROOT)
    built = STAGE / "UniSpace"
    if r.returncode != 0 or not (built / "UniSpace.exe").exists():
        print("Falha ao gerar o executável.")
        return 1

    # substitui a versão anterior na raiz
    if EXE.exists():
        EXE.unlink()
    if INTERNAL.exists():
        shutil.rmtree(INTERNAL)
    shutil.move(str(built / "UniSpace.exe"), EXE)
    shutil.move(str(built / "_internal"), INTERNAL)
    shutil.rmtree(WORK, ignore_errors=True)
    for legacy in (ROOT / "UniKanban.exe", ROOT / "UniKanban.zip"):   # executável com o nome antigo
        legacy.unlink(missing_ok=True)
    old_dist = ROOT / "dist"                      # local antigo do executável
    if old_dist.exists():
        shutil.rmtree(old_dist, ignore_errors=True)

    print("Conferindo o executável (navegador + portal)…")
    d = subprocess.run([str(EXE), "--diagnostico"])
    if d.returncode != 0:
        print(f"O executável foi gerado, mas o autodiagnóstico falhou (código {d.returncode}).")
        return d.returncode
    size = sum(f.stat().st_size for f in INTERNAL.rglob("*") if f.is_file()) + EXE.stat().st_size
    print(f"Pronto: {EXE}  (+ pasta _internal, {size / 1_048_576:.0f} MB no total)")
    if "--zip" in sys.argv:
        make_zip()
    return 0


if __name__ == "__main__":
    sys.exit(main())
