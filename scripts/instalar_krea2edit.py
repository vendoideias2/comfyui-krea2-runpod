#!/usr/bin/env python3
"""
Instala o custom node que define Krea2EditModelPatch e Krea2EditGroundedEncode.

   https://github.com/lbouaraba/comfyui-krea2edit

Nao usa git nem unzip: a imagem base nao garante os dois. Faz o download
do zip do GitHub e extrai com a stdlib do Python, que sempre existe la.
"""
import io
import os
import shutil
import urllib.request
import zipfile

REPO = "lbouaraba/comfyui-krea2edit"
BRANCH = "main"
DESTINO = "/comfyui/custom_nodes/comfyui-krea2edit"
MARCADORES = ("__init__.py",)


def main():
    if os.path.isfile(os.path.join(DESTINO, MARCADORES[0])):
        print(f"ja instalado em {DESTINO}, pulando")
        return

    os.makedirs("/comfyui/custom_nodes", exist_ok=True)
    tmp = "/tmp/_krea2edit"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    url = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
    print(f"baixando {url}")
    dados = urllib.request.urlopen(url, timeout=180).read()
    print(f"  {len(dados)/1e6:.1f} MB")

    zipfile.ZipFile(io.BytesIO(dados)).extractall(tmp)

    internos = [d for d in os.listdir(tmp) if d != "__MACOSX"]
    if not internos:
        raise SystemExit("zip vazio")
    origem = os.path.join(tmp, internos[0])
    print(f"  conteudo: {sorted(os.listdir(origem))[:8]}")

    shutil.rmtree(DESTINO, ignore_errors=True)
    shutil.move(origem, DESTINO)
    shutil.rmtree(tmp, ignore_errors=True)

    # confere que os nos estao mesmo la
    init = os.path.join(DESTINO, "__init__.py")
    if not os.path.isfile(init):
        raise SystemExit(f"FALHOU: {init} nao existe")
    fonte = open(init, encoding="utf-8").read()
    for no in ("Krea2EditModelPatch", "Krea2EditGroundedEncode"):
        if f'"{no}"' not in fonte:
            raise SystemExit(f"FALHOU: {no} nao registrado")
        print(f"  ok: {no}")

    print(f"instalado em {DESTINO}")


if __name__ == "__main__":
    main()