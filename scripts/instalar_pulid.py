#!/usr/bin/env python3
"""
Instala o custom node do PuLID-Flux, que define os nos usados pelo
gerador de ancoras:

    PulidFluxModelLoader
    PulidFluxEvaClipLoader
    PulidFluxInsightFaceLoader
    ApplyPulidFlux

O repo oficial no GitHub (cubiq/ComfyUI-PuLID-Flux) foi removido e devolve
404. O mirror vivo esta no HuggingFace:

    https://huggingface.co/snailmana99/comfyui-pulid-flux

CUIDADO: o zip foi empacotado no Windows e os caminhos usam barra
invertida ("eva_clip\\model.py"). O zipfile do Python cria arquivos com o
backslash LITERAL no nome, e o ComfyUI nao acha nenhum modulo. Por isso
aqui os nomes sao normalizados para barra normal antes de gravar.

Nao usa git nem unzip, igual ao instalar_krea2edit.py: a imagem base nao
garante os dois. So stdlib.
"""
import io
import os
import shutil
import urllib.request
import zipfile

URL = "https://huggingface.co/snailmana99/comfyui-pulid-flux/resolve/main/ComfyUI-PuLID-Flux.zip"
DESTINO = "/comfyui/custom_nodes/ComfyUI-PuLID-Flux"

# Nomes que o gerador de ancoras usa no workflow. Se algum faltar, a
# imagem sobe mas o job falha com "Node 'X' not found".
NOS_ESPERADOS = (
    "PulidFluxModelLoader",
    "PulidFluxEvaClipLoader",
    "PulidFluxInsightFaceLoader",
    "ApplyPulidFlux",
)


def extrair_normalizando(dados: bytes, destino: str) -> None:
    """
    Extrai o zip convertendo barra invertida em barra normal.

    Sem isso os diretorios ficam com o nome literal 'eva_clip\\' e o
    import falha.
    """
    zf = zipfile.ZipFile(io.BytesIO(dados))
    for info in zf.infolist():
        nome = info.filename.replace("\\", "/")
        if nome.startswith("/") or ".." in nome.split("/"):
            raise SystemExit(f"caminho perigoso no zip: {info.filename!r}")

        alvo = os.path.join(destino, nome)
        if info.is_dir():
            os.makedirs(alvo, exist_ok=True)
            continue

        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        origem = zf.open(info)
        with origem, open(alvo, "wb") as saida:
            shutil.copyfileobj(origem, saida)


def main():
    if os.path.isfile(os.path.join(DESTINO, "__init__.py")):
        print(f"ja instalado em {DESTINO}, pulando")
        return

    os.makedirs("/comfyui/custom_nodes", exist_ok=True)
    tmp = "/tmp/_pulid"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    print(f"baixando {URL}")
    dados = urllib.request.urlopen(URL, timeout=180).read()
    print(f"  {len(dados) / 1e6:.1f} MB")

    shutil.rmtree(DESTINO, ignore_errors=True)
    os.makedirs(DESTINO, exist_ok=True)
    extrair_normalizando(dados, DESTINO)
    shutil.rmtree(tmp, ignore_errors=True)

    init = os.path.join(DESTINO, "__init__.py")
    if not os.path.isfile(init):
        raise SystemExit(f"FALHOU: {init} nao existe")
    fonte = open(init, encoding="utf-8").read()

    # Confere que os nos estao registrados. O no do pulidflux costuma estar
    # em pulidflux.py, com o __init__.py so reexportando.
    registro = fonte
    for candidato in ("pulidflux.py", "pulid_flux.py"):
        caminho = os.path.join(DESTINO, candidato)
        if os.path.isfile(caminho):
            registro += open(caminho, encoding="utf-8").read()

    faltando = [no for no in NOS_ESPERADOS if f'"{no}"' not in registro]
    if faltando:
        raise SystemExit(f"FALHOU: nos nao registrados: {faltando}")

    for no in NOS_ESPERADOS:
        print(f"  ok: {no}")

    # Sanidade: o diretorio eva_clip precisa existir de verdade, com
    # separadores normais, senao o import do node quebra em runtime.
    eva = os.path.join(DESTINO, "eva_clip")
    if not os.path.isdir(eva):
        raise SystemExit(f"FALHOU: {eva} nao existe (barras invertidas?)")
    print(f"  ok: eva_clip ({len(os.listdir(eva))} arquivos)")

    print(f"instalado em {DESTINO}")


if __name__ == "__main__":
    main()
