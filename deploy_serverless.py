#!/usr/bin/env python3
"""
deploy_serverless.py — cria template + endpoint Serverless no RunPod.

Uso:
    export RUNPOD_API_KEY=rpa_xxx
    export RUNPOD_CONTAINER_IMAGE=<user>/runpod-comfyui-krea2:latest
    python3 deploy_serverless.py            # mostra o plano, não executa
    python3 deploy_serverless.py --go       # executa

Idempotente: se já existir template/endpoint com o mesmo nome, reaproveita.
"""

import json
import os
import sys

import requests

API = "https://api.runpod.ai/graphql"
TEMPLATE_NAME = "comfyui-krea2"
ENDPOINT_NAME = "flordeseda-krea2"

GRAPHQL_LIST_TEMPLATES = """
query { pubGetTemplateList(input: {}) { templates { id name imageId containerDisk } } }
"""

GRAPHQL_LIST_ENDPOINTS = """
query { mine { serverlessEndpoints { id name gpuTypes workersMax } } }
"""


def gql(api_key, query, variables=None):
    r = requests.post(
        API,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def main():
    api_key = os.environ.get("RUNPOD_API_KEY")
    image = os.environ.get("RUNPOD_CONTAINER_IMAGE")

    print("=" * 68)
    print("RunPod Serverless — ComfyUI + Krea 2")
    print("=" * 68)
    print(f"API key      : {'OK' if api_key else 'FALTANDO'}")
    print(f"Container    : {image or 'FALTANDO (exporte RUNPOD_CONTAINER_IMAGE)'}")
    print()

    if not api_key:
        sys.exit("ERRO: export RUNPOD_API_KEY antes.")
    if not image:
        sys.exit(
            "ERRO: export RUNPOD_CONTAINER_IMAGE=<user>/runpod-comfyui-krea2:latest\n"
            "      O build precisa de Docker local:\n"
            "        docker build -f Dockerfile.krea2 -t <user>/runpod-comfyui-krea2:latest .\n"
            "        docker push <user>/runpod-comfyui-krea2:latest"
        )

    print("Imagem precisa estar no Docker Hub ANTES de rodar isto.")
    print(f"Confirme: docker manifest inspect {image}")
    print()

    data = gql(api_key, GRAPHQL_LIST_TEMPLATES)
    templates = (data.get("pubGetTemplateList") or {}).get("templates") or []
    found = next((t for t in templates if t.get("name") == TEMPLATE_NAME), None)

    if found:
        print(f"Template '{TEMPLATE_NAME}' ja existe: {found['id']}")
        template_id = found["id"]
    else:
        print(f"Template '{TEMPLATE_NAME}' nao existe — sera criado no console:")
        print(f"  1. https://runpod.io/console/serverless/user/templates -> New Template")
        print(f"  2. Template Name  : {TEMPLATE_NAME}")
        print(f"  3. Template Type  : serverless")
        print(f"  4. Container Image: {image}")
        print(f"  5. Container Disk : 60 GB  (imagem ja tem ~21 GB de modelos)")
        print(f"  6. Expose HTTP    : 8000/http   (a porta do worker)")
        template_id = None

    print()
    data = gql(api_key, GRAPHQL_LIST_ENDPOINTS)
    eps = (data.get("mine") or {}).get("serverlessEndpoints") or []
    hit = next((e for e in eps if e.get("name") == ENDPOINT_NAME), None)
    if hit:
        print(f"Endpoint '{ENDPOINT_NAME}' ja existe: {hit['id']}")
    else:
        print(f"Criar endpoint no console com:")
        print(f"  - Select Template   : {TEMPLATE_NAME}")
        print(f"  - GPU               : RTX 4090 24GB  (ou L40S)")
        print(f"  - Active Workers    : 0      <- escala a zero, nao cobra ocioso")
        print(f"  - Max Workers       : 1")
        print(f"  - GPUs per Worker   : 1")
        print(f"  - Idle Timeout      : 30 s")
        print(f"  - FlashBoot         : ENABLED")
        print(f"  - Execution Timeout : 600 s")

    print()
    print("PRONTO. Copie o Endpoint ID e mande pra mim que eu monto o cliente de teste.")
    return 0


if __name__ == "__main__":
    sys.exit(main())