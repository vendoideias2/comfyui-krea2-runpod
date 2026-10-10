#!/usr/bin/env python3
"""
testar_endpoint.py — bate no endpoint Serverless e mostra o custo real.

    export RUNPOD_API_KEY=rpa_xxx
    export RUNPOD_ENDPOINT_ID=xxxxxxxx
    python3 testar_endpoint.py/workflows/Krea2_REF_IMAGE_TRYON.json MODELO.jpg PECA_SEDA.jpg

Mede: delayTime (fila + cold start) vs executionTime (geração).
Separar os dois é o que diz se o cold start está te comendo o orçamento.
"""

import base64
import json
import os
import sys
import time

import requests

URL = "https://api.runpod.ai/v2/{eid}/runsync"


def b64(path, max_mb=8.0):
    raw = open(path, "rb").read()
    mb = len(raw) / 1_048_576
    if mb > max_mb:
        raise SystemExit(f"{path} tem {mb:.1f} MB. Limite do /runsync e 20 MB — reduz a imagem.")
    return f"data:image/jpeg;base64," + base64.b64encode(raw).decode()


def strip_ui(workflow):
    """Aceita UI format (nodes/links) ou API format (input.workflow)."""
    if "input" in workflow and "workflow" in workflow["input"]:
        return workflow["input"]["workflow"]
    # UI -> API: so os nós com class_type (ja vem pronto em JSON exportado API)
    if "nodes" in workflow:
        out = {}
        for n in workflow["nodes"]:
            if n.get("type") in ("Note", "Reroute", "PrimitiveNode"):
                continue
            ins, wv, wi = {}, list(n.get("widgets_values") or []), 0
            for inp in n.get("inputs") or []:
                nm = inp.get("name")
                if not nm or inp.get("link") is not None:
                    continue
                if wi < len(wv):
                    ins[nm] = wv[wi]; wi += 1
            out[str(n["id"])] = {"class_type": n["type"], "inputs": ins}
        return out
    raise SystemExit("Formato de workflow nao reconhecido.")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    wf_path = sys.argv[1]
    eid = os.environ.get("RUNPOD_ENDPOINT_ID")
    key = os.environ.get("RUNPOD_API_KEY")
    if not eid or not key:
        raise SystemExit("export RUNPOD_ENDPOINT_ID e RUNPOD_API_KEY")

    api = strip_ui(json.load(open(wf_path)))

    payload = {"input": {"workflow": api}}

    # substitui o no LoadImage pela foto da peca
    if len(sys.argv) > 2:
        peca = sys.argv[-1]
        for node in api.values():
            if node["class_type"] == "LoadImage":
                node["inputs"]["image"] = b64(peca)
                payload["input"]["images"] = [{"name": "peca.jpg", "image": b64(peca)}]
                print(f"LoadImage -> {peca}")
                break

    print(f"POST /runsync  ({len(json.dumps(payload)) / 1024:.0f} KB)")
    t0 = time.time()
    r = requests.post(
        URL.format(eid=eid),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=900,
    )
    wall = time.time() - t0

    print(f"HTTP {r.status_code} | wall {wall:.1f}s")
    try:
        data = r.json()
    except Exception:
        print(r.text[:600]); return 1

    if data.get("error"):
        print("ERRO:", json.dumps(data["error"])[:800]); return 1

    delay = data.get("delayTime")
    exec_ = data.get("executionTime")
    if delay is not None: print(f"  delayTime     (fila+cold) {delay/1000:6.1f}s")
    if exec_ is not None:  print(f"  executionTime (geracao)  {exec_/1000:6.1f}s")

    imgs = (data.get("output") or {}).get("images") or []
    print(f"  imagens: {len(imgs)}")
    for i, im in enumerate(imgs):
        if im.get("type") == "base64":
            raw = base64.b64decode(im["data"])
            name = f"out_{i}.png"
            open(name, "wb").write(raw)
            print(f"    -> {name} ({len(raw)/1024:.0f} KB)")
        else:
            print(f"    -> {im.get('data')}")

    print("\nCusto estimado (4090 @ US$0.00031/s):")
    if exec_ is not None:
        print(f"  geracao pura : US$ {exec_/1000*0.00031:.4f}")
    print("  cold start desconta do 'delayTime' e tb e cobrado apos virar Running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())