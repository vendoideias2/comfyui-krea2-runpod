#!/usr/bin/env python3
"""
Teste de geração de âncora via Krea 2 Txt2Img no RunPod Serverless.
Executa a geração da Mariana (~35 anos, Plus Size) ou Helena (~42 anos) usando
o novo workflow nativo Krea 2 Turbo sem nós de Flux/PuLID.
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


def chave_api():
    env_path = os.path.join(RAIZ, ".env")
    if os.path.exists(env_path):
        for linha in open(env_path, encoding="utf-8"):
            if linha.strip().startswith("RUNPOD_API_KEY"):
                return linha.split("=", 1)[1].strip().strip('"')
    return os.environ.get("RUNPOD_API_KEY", "")


K = chave_api()
BASE = f"https://api.runpod.ai/v2/{EID}"


def get(path, timeout=120):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {K}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


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
    print(f"💎 Teste Gerador Âncoras Krea 2 Txt2Img — Endpoint {EID}\n")

    wf_path = os.path.join(RAIZ, "workflows", "GERADOR_ANCORAS_FLOR_DE_SEDA.api.json")
    wf = json.load(open(wf_path, encoding="utf-8"))["prompt"]

    prompts_path = os.path.join(RAIZ, "workflows", "prompts_ancoras_krea2.json")
    if os.path.exists(prompts_path):
        cfg = json.load(open(prompts_path, encoding="utf-8"))
        mariana = cfg["modelos"]["mariana"]
        prompt_txt = mariana["prompt"]
        seed = mariana["seed"]
    else:
        prompt_txt = "RAW ultra-realistic photograph, full-body shot of Mariana, a 35-year-old Brazilian woman with smooth long honey-brown hair..."
        seed = 88005

    wf["10"]["inputs"]["text"] = prompt_txt
    wf["30"]["inputs"]["seed"] = seed

    payload = {"input": {"workflow": wf}}

    print("1) Verificando health do endpoint...")
    try:
        health = get("/health")
        print("  ", json.dumps(health))
    except Exception as e:
        print(f"   Erro ao consultar health: {e}")

    print("\n2) Enviando job para RunPod /run...")
    try:
        r = post_run(payload)
    except Exception as e:
        print(f"   Erro no envio: {e}")
        return

    jid = r.get("id")
    print(f"   Job ID: {jid} | Status: {r.get('status')}")

    print("\n3) Aguardando conclusão...")
    for i in range(120):
        time.sleep(8)
        try:
            s = get(f"/status/{jid}", timeout=60)
        except Exception as e:
            print(f"   [poll erro] {e}")
            continue

        st = s.get("status")
        print(f"   t+{i*8:>4}s | {st}")
        if st in ("COMPLETED", "FAILED", "CANCELLED"):
            if st == "COMPLETED":
                imgs = s.get("output", {}).get("images", [])
                if imgs:
                    out_path = os.path.join(AQUI, "teste_mariana_gerada.png")
                    with open(out_path, "wb") as f:
                        f.write(base64.b64decode(imgs[0]["data"]))
                    print(f"\n✅ Sucesso! Imagem salva em: {out_path}")
                else:
                    print("\n⚠️ Job concluído mas sem imagem em output:", s.get("output"))
            else:
                print(f"\n❌ Job finalizou com erro ({st}):", s.get("error"))
            return
    print("   Timeout de polling.")


if __name__ == "__main__":
    main()
