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

BUG QUE ESTA VERSAO CORRIGE
    A versao anterior validava os nos por TEXTO: procurava a string
    '"PulidFluxModelLoader"' dentro do fonte. Isso passa mesmo quando o
    import estoura em runtime -- e o import estourava.

    pulidflux.py faz, no topo do modulo e sem protecao:

        from insightface.app import FaceAnalysis
        from facexlib.parsing import init_parsing_model
        from facexlib.utils.face_restoration_helper import FaceRestoreHelper

    insightface e facexlib nao vem no runpod/worker-comfyui. O ImportError
    derruba o modulo inteiro e o ComfyUI descarta o pacote, entao os quatro
    nos somem do object_info. O job morre com

        invalid prompt: {'type': 'missing_node_type',
        'message': "Node 'PulidFluxModelLoader' not found"}

    Note que apex e xformers JA sao try/except no proprio fonte (caem para
    LayerNorm), entao nao sao a causa. So insightface/facexlib.

    A correcao tem duas partes: instalar as dependencias e, em seguida,
    testar o import de verdade dentro da imagem -- que e o unico teste que
    pega este tipo de falha.
"""
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

URL = "https://huggingface.co/snailmana99/comfyui-pulid-flux/resolve/main/ComfyUI-PuLID-Flux.zip"
DESTINO = "/comfyui/custom_nodes/ComfyUI-PuLID-Flux"

# insightface so publica SDIST (0.7.3.tar.gz) e compila uma extensao
# Cython. Sem compilador na imagem o build morre em ~67s com:
#     error: [Errno 2] No such file or directory: 'x86_64-linux-gnu-g++'
# O Dockerfile instala g++ antes de rodar este script.
#
# onnxruntime NAO e pinado de proposito: a imagem worker-comfyui ja traz
# uma versao e fixar 1.19.2 forçaria reinstalacao, podendo conflito com a
# build GPU. O proprio insightface declara a dependencia, entao o pip
# resolve. gfpgan tambem foi removido: facexlib so precisa de
# basicsr/filterpy, que constroem sem compilador.
DEPENDENCIAS = (
    "insightface==0.7.3",
    "facexlib==0.3.0",
)

# Nomes que o gerador de ancoras usa no workflow. Se algum faltar, a
# imagem sobe mas o job falha com "Node 'X' not found".
NOS_ESPERADOS = (
    "PulidFluxModelLoader",
    "PulidFluxEvaClipLoader",
    "PulidFluxInsightFaceLoader",
    "ApplyPulidFlux",
)


def instalar_dependencias():
    """
    Instala insightface/facexlib. Falha ruidosa se nao conseguir: mais
    seguro o build quebrar aqui do que subir imagem sem os nos.
    """
    print("instalando dependencias do PuLID (pode demorar alguns minutos)")
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", *DEPENDENCIAS]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            "FALHOU: pip install das dependencias do PuLID\n"
            f"comando: {' '.join(cmd)}\n"
            f"saida:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
    print("  ok: dependencias instaladas")


def testar_import_real(destino: str):
    """
    Importa o pacote de verdade e confere se os nos entram no mapa.

    Este e o teste que pega a falha do insightface: a checagem por texto
    passaria, mas o import levanta ImportError.
    """
    # O diretorio tem hifen ("ComfyUI-PuLID-Flux"), que nao serve como
    # identificador de modulo. Por isso o import e feito pelo caminho do
    # arquivo, usando o mesmo mecanismo que o ComfyUI usa ao carregar
    # custom_nodes.
    teste = (
        "import importlib.util, sys\n"
        f"caminho = {os.path.join(destino, '__init__.py')!r}\n"
        "spec = importlib.util.spec_from_file_location('pulid_flux_probe', caminho,\n"
        "                                               submodule_search_locations=[%r])\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules['pulid_flux_probe'] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "mapa = getattr(mod, 'NODE_CLASS_MAPPINGS', {}) or {}\n"
        "faltando = [n for n in %r if n not in mapa]\n"
        "print('NOS:', sorted(mapa))\n"
        "if faltando:\n"
        "    print('FALTANDO:', faltando)\n"
        "    sys.exit(3)\n"
        "print('IMPORT_OK')\n" % (destino, NOS_ESPERADOS)
    )
    proc = subprocess.run([sys.executable, "-c", teste],
                          capture_output=True, text=True, cwd="/comfyui")
    saida = (proc.stdout or "") + (proc.stderr or "")
    print(saida.strip()[-1500:])
    if proc.returncode != 0 or "IMPORT_OK" not in saida:
        raise SystemExit(
            "FALHOU: o pacote do PuLID instala mas nao importa.\n"
            "Este e o bug que derrubava os 4 nos em runtime.\n"
            f"saida:\n{saida[-2500:]}"
        )
    print("  ok: import real funciona, os 4 nos entram no mapa")


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

    falta = [no for no in NOS_ESPERADOS if f'"{no}"' not in registro]
    if falta:
        raise SystemExit(f"FALHOU: nos nao registrados: {falta}")

    for no in NOS_ESPERADOS:
        print(f"  ok: {no}")

    # Sanidade: o diretorio eva_clip precisa existir de verdade, com
    # separadores normais, senao o import do node quebra em runtime.
    eva = os.path.join(DESTINO, "eva_clip")
    if not os.path.isdir(eva):
        raise SystemExit(f"FALHOU: {eva} nao existe (barras invertidas?)")
    print(f"  ok: eva_clip ({len(os.listdir(eva))} arquivos)")

    # As dependencias vao DEPOIS da extracao e ANTES do teste de import.
    instalar_dependencias()

    # O teste que realmente importa: arquivo no disco nao prova que o
    # modulo carrega. Foi exatamente essa a falha que derrubou os nos.
    testar_import_real(DESTINO)

    print(f"instalado em {DESTINO}")


if __name__ == "__main__":
    main()
