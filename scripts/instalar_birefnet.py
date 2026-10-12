#!/usr/bin/env python3
"""
Instala o custom node BiRefNet-ZHO e o peso do modelo.

   https://github.com/ZHO-ZHO-ZHO/ComfyUI-BiRefNet-ZHO
   pesos em https://huggingface.co/ViperYX/BiRefNet

POR QUE BiRefNet E NAO ComfyUI-RMBG

O RMBG e o mais popular (2176 estrelas), mas o requirements.txt dele puxa 15+
pacotes: segment-anything, groundingdino, hydra-core, decord, transformers,
diffusers. Este Dockerfile tem teto de 30 min de build e ja baixa 28,9 GB em
camadas cacheadas. Um pip install desses dozen e meio e a chance de o build
morrer por conflito de versao — e o custo e o de sempre: os 28,9 GB de cache
saem do caminho e o build inteiro recomeca.

O BiRefNet-ZHO pede UMA coisa: timm. E foi escolhido tambem pela qualidade
de borda, que e exatamente o ponto critico aqui: renda, franja e bordado sao
fina e e onde o recorte estraga a peca.

POR QUE .pth E NAO .safetensors

O loader faz torch.load(model_path), que le pickle. torch.load NAO abre
safetensors — para isso seria safetensors.torch.load_file. Os pesos do
ZhengPeng7/BiRefNet no HuggingFace so tem model.safetensors, entao aquele
caminho falha no primeiro job, dentro do container, onde o diagnostico e
pior. Daí usar o repo que o proprio README do node indica: ViperYX/BiRefNet,
que expoe os .pth.

O README pede os 6 modelos. Baixamos 1. Os outros 5 sao checkpoints de
variacoes (DIS, HR, dynamic, lite) e os backbones pvt_v2/swin usados pelo
codigo de treino. Para inferencia o load_state_dict sobrescreve o
backbone inteiro, entao um checkpoint completo basta.
"""
import io
import os
import shutil
import sys
import time
import urllib.request
import zipfile

REPO = "ZHO-ZHO-ZHO/ComfyUI-BiRefNet-ZHO"
BRANCH = "main"
DESTINO = "/comfyui/custom_nodes/ComfyUI-BiRefNet-ZHO"

HF = "https://huggingface.co/ViperYX/BiRefNet/resolve/main"
# ep480 = BiRefNet depaper, treinado em mistura (DIS5K, COD, HRSOD...).
# Preferido ao DIS_ep580 porque a foto da peca chega com fundos variados
# (espelho, parede, cabide) e um checkpoint generalista erra menos que um
# treinado so em DIS5K.
PESO = "BiRefNet-ep480.pth"
DIR_MODELOS = "/comfyui/models/BiRefNet"

# O loader so funciona se estes dois nomes existirem registrados. Conferir
# aqui e no build — antes do container subir — em vez de descobrir no
# primeiro job.
NOS_ESPERADOS = ("BiRefNet_ModelLoader_Zho", "BiRefNet_Zho")

TENTATIVAS = 3


def log(msg):
    print(f"[birefnet] {msg}", flush=True)


def baixa(url, destino, rotulo):
    """Baixa com retentativa e sem partir do zero.

    849 MB numa unica tacada e fragil: 502 de CDN e comum e o custo de
    recomecar seria o build inteiro. espelhar o -c do wget, que o resto do
    Dockerfile ja usa.
    """
    parcial = destino + ".part"
    for tentativa in range(1, TENTATIVAS + 1):
        inicio = time.time()
        try:
            restante = os.path.getsize(parcial) if os.path.exists(parcial) else 0
            req = urllib.request.Request(url)
            if restante:
                req.add_header("Range", f"bytes={restante}-")
            with urllib.request.urlopen(req, timeout=120) as r:
                total = int(r.headers.get("Content-Length") or 0) + restante
                lidos = restante
                modo = "ab" if restante else "wb"
                with open(parcial, modo) as f:
                    while True:
                        bloco = r.read(1 << 20)
                        if not bloco:
                            break
                        f.write(bloco)
                        lidos += len(bloco)
                    if total:
                        log(f"    {lidos/1e6:6.0f} / {total/1e6:.0f} MB  "
                            f"({lidos/1e6/max(time.time()-inicio,0.01):.0f} MB/s)")
            os.replace(parcial, destino)
            log(f"  ok: {rotulo} ({os.path.getsize(destino)/1e6:.0f} MB)")
            return
        except Exception as e:
            log(f"  tentativa {tentativa}/{TENTATIVAS} falhou: {type(e).__name__}: {e}")
            if tentativa == TENTATIVAS:
                raise SystemExit(f"FALHOU: {rotulo} — {e}")
            time.sleep(5)


def instala_node():
    init = os.path.join(DESTINO, "__init__.py")
    if os.path.isfile(init):
        log(f"node ja instalado em {DESTINO}, pulando")
        return
    os.makedirs("/comfyui/custom_nodes", exist_ok=True)
    tmp = "/tmp/_birefnet"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    url = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
    log(f"baixando {url}")
    dados = urllib.request.urlopen(url, timeout=180).read()
    log(f"  {len(dados)/1e6:.1f} MB")
    zipfile.ZipFile(io.BytesIO(dados)).extractall(tmp)

    internos = [d for d in os.listdir(tmp) if d != "__MACOSX"]
    if not internos:
        raise SystemExit("zip vazio")
    origem = os.path.join(tmp, internos[0])
    shutil.rmtree(DESTINO, ignore_errors=True)
    shutil.move(origem, DESTINO)
    shutil.rmtree(tmp, ignore_errors=True)

    if not os.path.isfile(init):
        raise SystemExit(f"FALHOU: {init} nao existe")
    fonte = open(init, encoding="utf-8").read()
    # O registro real vive em birefnet.py; o __init__ so faz merge. Ler os
    # dois, senao a checagem passa sem ter visto nada.
    registro = fonte + open(os.path.join(DESTINO, "birefnet.py"), encoding="utf-8").read()
    for no in NOS_ESPERADOS:
        if f'"{no}"' not in registro:
            raise SystemExit(f"FALHOU: {no} nao registrado")
        log(f"  ok: {no}")


def instala_timm():
    """timm e a unica dependencia e o node nao importa sem ela.

    Sem --break-system-packages o pip aborta numa imagem que ja tem torch
    instalado fora de venv, e o build morre aqui — no lugar certo, antes de
    qualquer job.
    """
    try:
        import timm  # noqa: F401
        log("timm ja presente, pulando")
        return
    except ImportError:
        pass
    log("instalando timm")
    rc = os.system("pip install --no-cache-dir --break-system-packages timm")
    if rc != 0:
        raise SystemExit(f"FALHOU: pip install timm saiu com {rc}")


def instala_peso():
    destino = os.path.join(DIR_MODELOS, PESO)
    if os.path.isfile(destino) and os.path.getsize(destino) > 500_000_000:
        log(f"peso ja em {destino}, pulando")
        return
    os.makedirs(DIR_MODELOS, exist_ok=True)
    baixa(f"{HF}/{PESO}", destino, PESO)


def main():
    if os.environ.get("BIREFNET_PULAR") == "1":
        log("BIREFNET_PULAR=1 — pulando tudo")
        return
    log("instalando BiRefNet-ZHO")
    instala_node()
    instala_timm()
    instala_peso()
    log("BiRefNet pronto")


if __name__ == "__main__":
    sys.exit(main())