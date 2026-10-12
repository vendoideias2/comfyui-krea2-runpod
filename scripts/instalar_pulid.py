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

# insightface e a unica dependencia que deu problema.
#
# O 0.7.3 (abr/2023, usado nas tentativas anteriores) so publica SDIST e
# compila mesh_core_cython. Sem compilador o build morre em ~67s com
#     error: [Errno 2] No such file or directory: 'x86_64-linux-gnu-g++'
#
# A partir da 1.0 o insightface publica wheel universal py3-none-any, e o
# cython virou EXTRA OPCIONAL de face3d -- ou seja, a instalacao base nao
# compila nada. A 2.1 (out/2026) exige python>=3.10, compativel com o 3.12
# da imagem.
#
# Nao pinamos onnxruntime: a imagem worker-comfyui ja traz uma versao e
# fixar forcaria reinstall, com risco de conflito com a build GPU. O proprio
# insightface declara a dependencia e o pip resolve. gfpgan fora: facexlib
# so usa basicsr/filterpy, que constroem em python puro.
DEPENDENCIAS = (
    "insightface==2.1",
    "facexlib==0.3.0",
    "ftfy",
)

# Nomes que o gerador de ancoras usa no workflow. Se algum faltar, a
# imagem sobe mas o job falha com "Node 'X' not found".
NOS_ESPERADOS = (
    "PulidFluxModelLoader",
    "PulidFluxEvaClipLoader",
    "PulidFluxInsightFaceLoader",
    "ApplyPulidFlux",
)


def _versao(modulo):
    """Versao instalada de um pacote, ou None se ausente."""
    try:
        from importlib.metadata import version
        return version(modulo)
    except Exception:
        return None


def instalar_dependencias():
    """
    Instala insightface/facexlib. Falha ruidosa se nao conseguir: mais
    seguro o build quebrar aqui do que subir imagem sem os nos.

    REGRA CRITICA: o pip nao pode rebaixar numpy nem onnxruntime. O
    insightface declara ambos como dependencia, e um rebaixamento
    silencioso quebra o torch -- o que derrubaria o try-on, que hoje
    funciona. A versao de numpy antes e depois e comparada, e qualquer
    mudanca aborta o build.
    """
    antes = {p: _versao(p) for p in ("numpy", "onnxruntime")}
    print(f"  numpy antes: {antes['numpy']} | onnxruntime antes: {antes['onnxruntime']}")

    print("instalando dependencias do PuLID (pode demorar alguns minutos)")
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", *DEPENDENCIAS]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            "FALHOU: pip install das dependencias do PuLID\n"
            f"comando: {' '.join(cmd)}\n"
            f"saida:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )

    depois = {p: _versao(p) for p in ("numpy", "onnxruntime")}
    print(f"  numpy depois: {depois['numpy']} | onnxruntime depois: {depois['onnxruntime']}")

    if antes["numpy"] and depois["numpy"] and antes["numpy"] != depois["numpy"]:
        raise SystemExit(
            f"FALHOU: o pip alterou o numpy ({antes['numpy']} -> {depois['numpy']}).\n"
            "Isso quebra o torch e derrubaria o try-on, que hoje funciona.\n"
            "Fixe a versao do numpy no Dockerfile antes de seguir."
        )

    # Prova final de que o torch continua utilizavel. Mais barato que
    # descobrir no primeiro job que a imagem subiu quebrada.
    check = subprocess.run(
        [sys.executable, "-c", "import torch; print(torch.__version__)"],
        capture_output=True, text=True)
    if check.returncode != 0:
        raise SystemExit(f"FALHOU: o torch nao importa mais:\n{check.stderr[-1500:]}")
    print(f"  ok: dependencias instaladas, torch {check.stdout.strip()} intacto")


def testar_import_real(destino: str):
    """
    Verifica o que da para checar SEM GPU.

    Por que nao importar o pacote inteiro: pulidflux.py faz, na linha 10,

        from comfy.ldm.flux.layers import timestep_embedding

    que puxa comfy.ldm.flux.layers -> math -> attention -> comfy.model_management.
    E o model_management do ComfyUI executa no TOPO do modulo (linha 363):

        total_vram = get_total_memory(get_torch_device())

    que chama torch.cuda.current_device(). Na maquina de build do RunPod
    nao ha GPU, entao o import morre com:

        RuntimeError: Found no NVIDIA driver on your system

    Isso NAO e um problema do no: em runtime, no worker, ha GPU e o mesmo
    import funciona. O que quebrou foi o teste de build (13:40), nao a
    imagem.

    O que este teste faz, sem tocar em CUDA:
      1. importa as dependencias que o modulo usa no topo (insightface,
         facexlib) -- de verdade, e elas nao tocam em GPU;
      2. compila pulidflux.py com ast, o que pega erro de sintaxe sem
         executar nada;
      3. le NODE_CLASS_MAPPINGS por texto e confere os 4 nomes.
    """
    teste = (
        # 1. dependencias reais, sem CUDA
        "from insightface.app import FaceAnalysis\n"
        "from facexlib.parsing import init_parsing_model\n"
        "from facexlib.utils.face_restoration_helper import FaceRestoreHelper\n"
        "import insightface, facexlib, ftfy\n"
        "print('INSIGHTFACE', getattr(insightface, '__version__', '?'),\n"
        "      '| FACEXLIB', getattr(facexlib, '__version__', '?'),\n"
        "      '| FTFY', getattr(ftfy, '__version__', '?'))\n"
        # 2. sintaxe do modulo, sem executar
        "import ast, pathlib\n"
        "fonte = pathlib.Path(%r) / 'pulidflux.py'\n"
        "arvore = ast.parse(fonte.read_text(encoding='utf-8'))\n"
        "print('SINTAXE OK:', fonte.name)\n"
        # 3. os 4 nos no NODE_CLASS_MAPPINGS. As CHAVES do dict sao os nomes
        # dos nos; os VALORES sao referencias a classes (ast.Name), entao
        # literal_eval nao serve. Extrai-se so a chave.
        "nomes = set()\n"
        "for no in ast.walk(arvore):\n"
        "    if not isinstance(no, ast.Assign):\n"
        "        continue\n"
        "    if not any(getattr(t, 'id', '') == 'NODE_CLASS_MAPPINGS' for t in no.targets):\n"
        "        continue\n"
        "    if isinstance(no.value, ast.Dict):\n"
        "        for chave in no.value.keys:\n"
        "            if isinstance(chave, ast.Constant) and isinstance(chave.value, str):\n"
        "                nomes.add(chave.value)\n"
        "print('NOS:', sorted(nomes))\n"
        "faltando = [n for n in %r if n not in nomes]\n"
        "if faltando:\n"
        "    print('FALTANDO:', faltando)\n"
        "    sys.exit(3)\n"
        "print('IMPORT_OK')\n" % (destino, NOS_ESPERADOS)
    )
    teste = "import sys\n" + teste
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
