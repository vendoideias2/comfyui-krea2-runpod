# PLANO A — Build da imagem com modelos, via GitHub do RunPod

Endpoint alvo: `3ohh2rihn2hxjh` (esse vai ser **substituído** por um novo).
Repo: `vendoideias2/comfyui-krea2-runpod` · branch `main` · commit `eb37345`

---

## PASSO 0 — Conectar o GitHub ao RunPod (2 min)

1. RunPod → canto superior direito → **Account Settings** (ou clique no avatar)
2. Procura a seção **GitHub** (pode estar em *Connections* ou *Integrations*)
3. Clique **Connect** → authorize a conta `vendoideias2`
4. Confirma que volta pro RunPod e mostra a conta conectada

**Se não achar a seção GitHub:** não bloqueia. O passo 1 abaixo te diz o plano B.

---

## PASSO 1 — Criar o endpoint NOVO do repo (5 min)

> ⚠️ **Não edite o endpoint antigo.** Cria um novo. O antigo está preso numa imagem slim
> que nunca vai funcionar (worker `unhealthy`, 2 jobs presos na fila).

1. RunPod → **Serverless** (menu lateral) → **+ New Endpoint**
2. Rola até a parte de baixo → clica em **"Start from GitHub Repo"** ou
   **"Import Git Repository"**
3. Preenche:

| Campo | Valor |
|---|---|
| Repository | `vendoideias2/comfyui-krea2-runpod` |
| Branch | `main` |
| Context Path | `/` |
| Dockerfile Path | `Dockerfile` |
| Endpoint Name | `flordeseda-krea2` |
| Endpoint Type | **Queue** ← obrigatório (o Worker só existe em Queue) |

---

## PASSO 2 — Configuração de GPU (2 min)

| Campo | Valor | Por quê |
|---|---|---|
| GPU Type | **RTX 4090 24 GB** (ou L40S) | cabe o fp8 + encoder |
| **Active Workers** | **0** | escala a zero, **não cobra ocioso** |
| **Max Workers** | **1** | ⚠️ **tem que ser ≥ 1** — se for 0 o endpoint pausa |
| GPUs per Worker | 1 | |
| Execution Timeout | 600 s | |
| Idle Timeout | 30 s | |
| **FlashBoot** | **ENABLED** | revival <200 ms |
| Container Disk | **60 GB** | a imagem já tem 19,5 GB |
| **Network Volume** | **NENHUM** | ← não anexa volume nenhum, é o que matou o anterior |

---

## PASSO 3 — Deploy (1 clique)

Clica **Deploy Endpoint**. Tu é levado pra página do endpoint.

Vai aparecer a aba **Builds**. Estados possíveis:

| Estado | O que significa | Quanto demora |
|---|---|---|
| `Building` | baixando os 19,5 GB | **15–30 min** |
| `Ready` / `Active` | deu certo | |
| `Failed` | estourou o teto de 30 min | vai pro PASSO 5 |

**Não navega pra fora da página.** O build roda sozinho.

---

## PASSO 4 — Verificar que subiu (2 min)

Assim que o build virar `Ready`, me manda o **Endpoint ID novo**.

Eu rodo:

```bash
curl -H "Authorization: Bearer $RUNPOD_API_KEY" \
  https://api.runpod.ai/v2/<ID_NOVO>/health
```

O esperado é:

```json
{"jobs":{"inQueue":0,...},
 "workers":{"ready":0,"unhealthy":0,"idle":0,"initializing":0,"running":0,...}}
```

Com **`unhealthy: 0`**. Se continuar `unhealthy: 1`, a imagem subiu errada.

---

## PASSO 5 — Se o build falhar

O motivo quase sempre é o **teto de 30 min do `docker build`** (19,5 GB é muito).

Nessa hora, plano B — 1 Pod pra popular o volume:

1. Cria um Network Volume: **Storage → Network Volumes → Create**, `krea2-models`, 200 GB
2. Cria 1 Pod com esse volume montado em `/workspace`
3. Connect → Web Terminal → roda:

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/vendoideias2/comfyui-krea2-runpod/main/scripts/download_models.sh)"
```

4. ~25 min. Depois **destrói o Pod** (o volume fica)
5. Cria o endpoint apontando pro volume montado em `/workspace`

Esse caminho não tem risco de build. Custo: ~US$ 2/mês de storage, zero GPU parado.

---

## PASSO 6 — Limpança

Depois que o endpoint novo funcionar:

- **Deleta o endpoint antigo** `3ohh2rihn2hxjh` (ele tem 2 jobs presos na fila segurando
  worker `unhealthy`)
- Confirma que `workers: unhealthy: 0` no endpoint novo

---

## Referência rápida

| | |
|---|---|
| Repo | `https://github.com/vendoideias2/comfyui-krea2-runpod` |
| Commit | `eb37345` |
| Workflow | `workflows/KREA2_TRYON_FLOR_DE_SEDA.json` |
| Modelos | 19,5 GB baked na imagem |
| Custo ocioso | US$ 0 (Active Workers = 0) |
| Custo por imagem | ~US$ 0,003 (10 s de geração na 4090) |