# ComfyUI + Krea 2 no RunPod Serverless

Try-on de roupa (foto da peça + foto do modelo) em API, com **nós 100% nativos do ComfyUI** —
zero custom nodes. O nó responsável é o `TextEncodeKrea2`, nativo do ComfyUI.

# 🎯 TRY-ON DO FLOR DE SEDA — `KREA2_TRYON_FLOR_DE_SEDA.json`

**16 nós, 100% nativos do ComfyUI. Zero custom nodes. Zero pacote.**

```
UNETLoader (krea2_turbo_fp8_scaled)
  └─ LoraLoaderModelOnly  krea2_identity_edit_v1_2_r128  @ 1.0
       └─ Krea2EditModelPatch  [ref_boost 4.0 | ref_boost_a 1.0 | fit]
            ├─ ← VAEEncode (MODELO)     ← imagem original
            ├─ ← VAEEncode (PECA_SEDA)  ← imagem original
            └─ → model → KSampler → VAEDecode → SaveImage

CLIPLoader (qwen3vl_4b_fp8_scaled, type=krea2)
  ├─ Krea2EditGroundedEncode  (instrução)  ← as 2 imagens
  └─ Krea2EditGroundedEncode  ("")         ← negative

VAEEncode (MODELO) → KSampler.latent_image
KSampler [10 steps | CFG 1.0 | euler/simple | denoise 1.0]
```

| Nó | Papel |
|---|---|
| `Krea2EditModelPatch` | injeta o patch de edição no MODEL + os 2 latentes de referência |
| `Krea2EditGroundedEncode` | codifica a instrução **junto com as 2 imagens** (grounded) |

## 🚨 O LoRA de edição é obrigatório

`krea2_identity_edit_v1_2_r128.safetensors` — sem ele a saída sai **em mosaico/blocos**
(o modelo base lê os tokens de referência como conteúdo e quebra a imagem).
Não é bug de prompt. O `scripts/download_models.sh` já baixa.

## Ajustes

| Onde | O quê |
|---|---|
| `LoadImage` 4 | **MODELO.jpg** — a pessoa. Vira o `latent_image` do KSampler. |
| `LoadImage` 5 | **PECA_SEDA.jpg** — a peça. Vai como referência. |
| `Krea2EditModelPatch[0]` | `ref_boost` = 4.0. **Sobe se a peça não persistir.** |
| `KSampler` | 10 passos, CFG 1.0, euler/simple. Não mexa no CFG. |

Se a peça não aparecer: sobe `ref_boost` para 6. Se a pessoa mudar: desce para 3.

---

## Arquitetura

Modelos num **Network Volume** (build da imagem leva ~2 min, sem risco de estourar o
teto de 30 min do RunPod). A imagem é a oficial `runpod/worker-comfyui` sem nada dentro.

```
Network Volume (200 GB)          imagem slim
├── models/diffusion_models/      runpod/worker-comfyui:latest
├── models/text_encoders/  <--    + healthcheck que confere os 3 arquivos
└── models/vae/
```

---

## Passo 1 — Conectar o GitHub ao RunPod

RunPod console → *Account Settings* → **GitHub** → *Connect*. Autoriza `vendoideias2`.

## Passo 2 — Criar o Network Volume

RunPod console → **Storage → Network Volumes → Create**
- Name: `krea2-models`
- Size: **200 GB**
- Region: a mesma do endpoint

## Passo 3 — Baixar os modelos (uma vez)

1. Crie um **Pod** com GPU (qualquer, 16 GB+) e **anexe o volume `krea2-models`** montado em `/workspace`
2. Abra um shell (Connect → Start Web Terminal) e rode:

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/vendoideias2/comfyui-krea2-runpod/main/scripts/download_models.sh)"
```

3. Confirme que terminou (~21 GB, 20–30 min). Depois **pode destruir o Pod** — o volume fica.

## Passo 4 — Deploy do endpoint

Serverless → **+ New Endpoint** → **Import Git Repository**

| Campo | Valor |
|---|---|
| Repository | `vendoideias2/comfyui-krea2-runpod` |
| Branch | `main` |
| Context Path | `/` |
| Dockerfile Path | `Dockerfile` |
| Endpoint Type | **Queue** |
| GPU | RTX 4090 24 GB (ou L40S) |
| Active Workers | **0** ← escala a zero, não cobra ocioso |
| Max Workers | 1 |
| GPUs per Worker | 1 |
| Idle Timeout | 30 s |
| FlashBoot | **ENABLED** |
| Execution Timeout | 600 s |
| Network Volume | `krea2-models` montado em `/workspace` |

Clique **Deploy Endpoint**. Anote o **Endpoint ID**.

## Passo 5 — Testar

```bash
export RUNPOD_API_KEY=rpa_xxx
export RUNPOD_ENDPOINT_ID=xxxxxxxx

python3 testar_endpoint.py \
  workflows/Krea2_REF_IMAGE_TRYON.json \
  /caminho/da/PECA_DE_SEDA.jpg
```

Imprime `delayTime` (fila + cold start) separado de `executionTime` (geração) e salva
`out_0.png`. Custo de 1 imagem na 4090 ≈ US$ 0,003.

---

## O workflow

`workflows/Krea2_REF_IMAGE_TRYON.json` — 20 nós, todos core:

```
UNETLoader (krea2_turbo_fp8_scaled)
  └─ LoraLoaderModelOnly            ← opcional, deixar desconectado
       └─ ModelSamplingFlux
            ├─ BasicScheduler  (simple, 20 steps)
            └─ CFGOverride     (guidance 1, cfg 0)
                 └─ SamplerCustom   ← positive
CLIPLoader (qwen3vl_4b_fp8_scaled, type="krea2")
  └─ TextEncodeKrea2  ← image1 = a foto de referência (a peça)
EmptyLatentImage → SamplerCustom.latent_image
```

**A referência entra pelo `TextEncodeKrea2` (grounding semântico), não por latente.**
Ela orienta o resultado — não preserva a pessoa pixel a pixel. O prompt descreve o modelo.

### Prompt (nó `CLIPTextEncode`)

```
Full-body e-commerce fashion photograph of a model wearing a fluid silk dress,
the exact fabric and drape shown in the reference image. Natural relaxed standing
pose, soft diffused studio lighting, clean seamless background, sharp focus on
fabric texture, luxury boutique catalog style.
```

Ordem de caption: *framing → câmera → pose → expressão → cabelo → roupa → luz → ambiente.*

## Outros workflows

| Arquivo | Pra quê |
|---|---|
| `GERADOR_ANCORAS_FLOR_DE_SEDA.api.json` | 💎 Gerador de Âncoras T2I Krea 2 nativo (CFG 1.0, 8 steps, ConditioningZeroOut) |
| `F - 11 - P02 - Character Create_Krea-2-Turbo_T2I.json` | 👤 Template da comunidade para criação consistente de modelos |
| `KREA2_TRYON_FLOR_DE_SEDA.json` | 🎯 Try-on oficial Flor de Seda (vestir modelo com a peça) |
| `Krea2_REF_IMAGE_TRYON.json` | 👗 Try-on com imagem de referência |

---

## Custos

| | |
|---|---|
| Storage do volume (~21 GB) | ~US$ 2/mês |
| 1 imagem (≈10 s de geração) | ≈ US$ 0,003 |
| 5 tamanhos do Flor de Seda | ≈ US$ 0,015 |

Com `Active Workers = 0` não se paga GPU em ocioso.
