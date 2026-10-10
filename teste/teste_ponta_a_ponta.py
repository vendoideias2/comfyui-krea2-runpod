#!/usr/bin/env python3
"""
Teste ponta a ponta no endpoint RunPod.

Responde de uma vez:
  1. os nos Krea2 existem na imagem?
  2. o modelo assado carrega?
  3. o try-on gera imagem?

Envia as duas imagens em base64 (o handler do worker-comfyui aceita o
campo "images"), converte o workflow UI para API e chama /run.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

EID = sys.argv[1] if len(sys.argv) > 1 else "4rfl1chnndpxne"
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

sys.path.insert(0, RAIZ)
from ui_para_api import converte  # noqa: E402


def chave_api():
    for linha in open(os.path.join(RAIZ, ".env"), encoding="utf-8"):
        if linha.strip().startswith("RUNPOD_API_KEY"):
            return linha.split("=", 1)[1].strip().strip('"')
    return ""


K = chave_api()
BASE = f"https://api.runpod.ai/v2/{EID}"


def get(path, timeout=120):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {K}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def b64(nome):
    with open(os.path.join(AQUI, nome), "rb") as f:
        return base64.b64encode(f.read()).decode()


def post_run(payload, timeout=600):
    req = urllib.request.Request(
        f"{BASE}/run",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {K}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main():
    print(f"endpoint {EID}\n")

    print("1) health")
    print("  ", json.dumps(get("/health")))

    print("\n2) convertendo workflow")
    ui = json.load(open(os.path.join(RAIZ, "workflows", "KREA2_TRYON_FLOR_DE_SEDA.json"), encoding="utf-8"))
    api = converte(ui, None)  # sem object_info: usa a ordem do export UI
    print(f"   {len(api)} nos")
    for alvo in ("11", "12"):
        print(f"   no {alvo}: {api[alvo]['class_type']}")
        print(f"     inputs: {json.dumps(api[alvo]['inputs'], ensure_ascii=False)[:230]}")

    payload = {
        "input": {
            "workflow": api,
            "images": [
                {"name": "MODELO.png", "image": b64("MODELO.png")},
                {"name": "PECA_SEDA.png", "image": b64("PECA_SEDA.png")},
            ],
        }
    }

    print("\n3) enviando job (pode demorar: worker esta ocioso e vai subir)")
    try:
        r = post_run(payload)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode()[:900]
        print(f"   HTTP {e.code}: {corpo}")
        return
    except Exception as e:
        print(f"   erro: {e}")
        return

    jid = r.get("id")
    print(f"   job {jid}  status={r.get('status')}")

    print("\n4) aguardando")
    for i in range(150):
        time.sleep(8)
        try:
            s = get(f"/status/{jid}", timeout=60)
        except Exception as e:
            print(f"   [poll erro] {e}")
            continue
        st = s.get("status")
        print(f"   t+{i*8:>4}s  {st}")
        if st in ("COMPLETED", "FAILED", "CANCELLED"):
            print("\n=== RESULTADO ===")
            print(json.dumps(s, indent=2, ensure_ascii=False)[:3000])
            return
    print("   timeout no poll")


if __name__ == "__main__":
    main()