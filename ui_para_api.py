#!/usr/bin/env python3
"""
Converte o workflow UI do ComfyUI para o formato API (o unico que o
handler do worker-comfyui aceita em job["input"]["workflow"]).

O ponto critico: mapear widgets_values para os nomes de input. So da para
fazer isso com precisao usando a definicao real dos nos, que vem do
endpoint /object_info do ComfyUI. Sem ele, adivinhamos.

Uso:
    python3 ui_para_api.py <endpoint_id>
    python3 ui_para_api.py 4rfl1chnndpxne workflows/KREA2_TRYON_FLOR_DE_SEDA.json saida.json
"""
import base64
import json
import os
import sys
import urllib.request

LINK_TYPES = {
    "MODEL", "CLIP", "VAE", "CONDITIONING", "LATENT", "IMAGE", "MASK",
    "CLIP_VISION", "CLIP_VISION_OUTPUT", "CONTROL_NET", "AUDIO", "UPSCALE_MODEL",
}


def pega_endpoint(eid):
    chave = os.environ.get("RUNPOD_API_KEY", "")
    if not chave:
        for linha in open(os.path.join(os.path.dirname(__file__), ".env"), encoding="utf-8"):
            if linha.strip().startswith("RUNPOD_API_KEY"):
                chave = linha.split("=", 1)[1].strip().strip('"')
    req = urllib.request.Request(
        f"https://api.runpod.ai/v2/{eid}/health",
        headers={"Authorization": f"Bearer {chave}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def pega_object_info(eid, chave):
    """Definicao real dos nos. Retorna {} se o worker nao responder."""
    req = urllib.request.Request(
        f"https://api.runpod.ai/v2/{eid}/object_info",
        headers={"Authorization": f"Bearer {chave}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status != 200:
                return {}
            return json.load(r)
    except Exception as e:
        print(f"  [aviso] /object_info falhou: {e}")
        return {}


def mapeia_widgets(node, info_no):
    """
    widgets_values -> {nome_input: valor}

    Estrategia: os inputs do tipo NAO-link (widget) aparecem no node["inputs"]
    na mesma ordem dos widgets_values. A definicao do /object_info da a ordem
    autoritativa. Sem /object_info, cai no order do proprio node exportado.
    """
    wv = list(node.get("widgets_values") or [])
    if not wv:
        return {}

    # ordem autoritativa vinda do ComfyUI
    if info_no:
        ordem = []
        for chave_in, spec in info_no.get("input", {}).items():
            req = spec.get("required", False)
            if req or (not req and chave_in in info_no.get("optional", {})):
                if spec.get("type") not in LINK_TYPES:
                    ordem.append(chave_in)
    else:
        ordem = [
            i["name"] for i in node.get("inputs", [])
            if i.get("link") is None and i.get("type") not in LINK_TYPES
        ]

    out, rest = {}, list(wv)
    for nome in ordem:
        if not rest:
            break
        out[nome] = rest.pop(0)

    # sobra de widgets (o export do CivitAI as vezes traz a mais) -> log
    if rest:
        print(f"    [aviso] node {node['id']} ({node['type']}): "
              f"{len(rest)} widget(s) sem input correspondente: {rest}")
    return out


def converte(ui, object_info=None):
    links = {l[0]: (l[1], l[2]) for l in ui.get("links", [])}
    api = {}

    for node in ui["nodes"]:
        tipo = node["type"]
        if tipo.startswith("Note") or tipo in ("Reroute", "PrimitiveNode"):
            continue

        info_no = (object_info or {}).get(tipo)
        entradas = {}

        # 1) inputs linkados
        for inp in node.get("inputs", []):
            lid = inp.get("link")
            if lid is None:
                continue
            if lid in links:
                origem, slot = links[lid]
                entradas[inp["name"]] = [str(origem), slot]

        # 2) widgets
        for k, v in mapeia_widgets(node, info_no).items():
            entradas[k] = v

        api[str(node["id"])] = {"class_type": tipo, "inputs": entradas}

    return api


def confere(api, ui):
    """Checagem de sanidade contra o grafo original."""
    links = {l[0]: (l[1], l[2]) for l in ui.get("links", [])}
    esperado = sum(1 for l in links.values())
    got_links = 0
    for no in api.values():
        for v in no["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0].isdigit():
                got_links += 1

    print(f"\n  nos: {len(api)}  (UI tem {len([n for n in ui['nodes'] if not n['type'].startswith('Note')])})")
    print(f"  conexoes: {got_links}  (UI tem {esperado})")

    orfaos = [k for k, v in api.items()
              if not any(isinstance(x, list) and len(x) == 2 and x[0].isdigit()
                         for v2 in v["inputs"].values() for x in [v2])]
    if orfaos:
        print(f"  [aviso] nos sem entrada linkada: {orfaos}")


def main():
    eid = sys.argv[1] if len(sys.argv) > 1 else None
    if not eid:
        print(__doc__)
        sys.exit(1)

    base = os.path.dirname(os.path.abspath(__file__))
    entrada = sys.argv[2] if len(sys.argv) > 2 else os.path.join(base, "workflows", "KREA2_TRYON_FLOR_DE_SEDA.json")
    saida = sys.argv[3] if len(sys.argv) > 3 else os.path.join(base, "workflows", "KREA2_TRYON_FLOR_DE_SEDA.api.json")

    chave = os.environ.get("RUNPOD_API_KEY", "")
    if not chave:
        for linha in open(os.path.join(base, ".env"), encoding="utf-8"):
            if linha.strip().startswith("RUNPOD_API_KEY"):
                chave = linha.split("=", 1)[1].strip().strip('"')

    print(f"endpoint: {eid}")
    print("lendo /health ...")
    print(" ", json.dumps(pega_endpoint(eid)))

    print("\nlendo /object_info (definicao real dos nos) ...")
    oi = pega_object_info(eid, chave)
    if oi:
        print(f"  {len(oi)} tipos de no disponiveis")
        for alvo in ("Krea2EditModelPatch", "Krea2EditGroundedEncode"):
            print(f"  {alvo}: {'PRESENTE' if alvo in oi else '*** AUSENTE ***'}")
    else:
        print("  indisponivel (worker subindo?) — usando ordem do export UI")

    ui = json.load(open(entrada, encoding="utf-8"))
    print(f"\nconvertendo {os.path.basename(entrada)} ...")
    api = converte(ui, oi)
    confere(api, ui)

    with open(saida, "w", encoding="utf-8") as f:
        json.dump(api, f, indent=2, ensure_ascii=False)
    print(f"\ngravado: {saida}")


if __name__ == "__main__":
    main()
