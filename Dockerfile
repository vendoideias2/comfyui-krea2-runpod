# Imagem COM modelos assados — dispensa Pod e Network Volume.
#
# TRUQUE PRINCIPAL: BuildKit constroi stages independentes EM PARALELO.
# O stage "models" (base alpine, ~7 MB) baixa os 19,5 GB do Krea 2 enquanto o
# BuildKit ja puxa os 14,7 GB do worker-comfyui. Sem isso os 34 GB seriam
# sequenciais e o build estouraria o teto de 30 min do RunPod.
#
# Derivatives de runpod/worker-comfyui: os modelos vao em /comfyui/models.
# ATENCAO: a imagem NAO tem tag "latest" — tags sao versionadas.
FROM alpine:3.20 AS models

ENV B=https://huggingface.co/Comfy-Org/Krea-2/resolve/main \
    L=https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main

RUN apk add --no-cache wget ca-certificates \
 && mkdir -p /models/diffusion_models \
             /models/text_encoders \
             /models/vae \
             /models/loras

# 4 downloads simultaneos (~19,5 GB)
RUN set -eux; \
    wget -q -c -O /models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
         $B/diffusion_models/krea2_turbo_fp8_scaled.safetensors & \
    wget -q -c -O /models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
         $B/text_encoders/qwen3vl_4b_fp8_scaled.safetensors & \
    wget -q -c -O /models/vae/qwen_image_vae.safetensors \
         $B/vae/qwen_image_vae.safetensors & \
    wget -q -c -O /models/loras/krea2_identity_edit_v1_2_r128.safetensors \
         $L/krea2_identity_edit_v1_2_r128.safetensors & \
    wait; \
    du -sh /models/*/; \
    test -s /models/diffusion_models/krea2_turbo_fp8_scaled.safetensors; \
    test -s /models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors; \
    test -s /models/vae/qwen_image_vae.safetensors; \
    test -s /models/loras/krea2_identity_edit_v1_2_r128.safetensors

# ------------------------------------------------------------------
# GERADOR DE ANCORAS — camada nova, downloads em paralelo (~9,4 GB)
#
# POR QUE: o try-on acima VESTE roupa. O Krea2EditModelPatch tem
# source_latent e target_latent apontando para a mesma imagem A, entao o
# workflow sempre devolve a pessoa da imagem A — nao existe parametro que
# troque a identidade. Foi por isso que a Mariana saia parecendo com a
# Helena mesmo com ref_boost alto.
#
# O gerador de ancoras e txt2img + PuLID: o rosto vem da referencia facial
# (trancado pelo PuLID) e o restante — corpo, cabelo, cenario — vem do
# prompt. E a unica via que produz uma modelo diferente das outras.
#
# IMPORTANTE: esta e uma CAMADA SEPARADA de proposito. Mexer no RUN acima
# invalidaria o cache e faria os 19,5 GB do try-on baixarem de novo. Como
# e uma instrucao nova, so estes 9,4 GB entram.
#
# O clip bf16 e novo: o gerador usa CLIPLoader type=qwen2vl com
# qwen3vl_4b_bf16, enquanto o try-on usa type=krea2 com o fp8_scaled.
# Sao arquivos diferentes — renomear nao resolve.
#
# NOTA: os LoRAs do CivitAI (fashion_pose, krea2_pro_realism) ficam de
# fora de proposito — este repositorio e PUBLICO e botar um token de API
# no Dockerfile vazaria a credencial. Sem eles a textura fica menos
# "lookbook", mas o gerador funciona.
# ------------------------------------------------------------------
ENV P=https://huggingface.co/guozinan/PuLID/resolve/main

RUN mkdir -p /models/pulid \
 && set -eux; \
    wget -q -c -O /models/text_encoders/qwen3vl_4b_bf16.safetensors \
         $B/text_encoders/qwen3vl_4b_bf16.safetensors & \
    wget -q -c -O /models/pulid/pulid_flux_v0.9.1.safetensors \
         $P/pulid_flux_v0.9.1.safetensors & \
    wait; \
    du -sh /models/*/; \
    test -s /models/text_encoders/qwen3vl_4b_bf16.safetensors; \
    test -s /models/pulid/pulid_flux_v0.9.1.safetensors

# ------------------------------------------------------------------
FROM runpod/worker-comfyui:5.10.0-base

ENV COMFY_POLLING_INTERVAL_MS=500 \
    COMFY_POLLING_MAX_RETRIES=1200

COPY --from=models /models /comfyui/models

RUN mkdir -p /comfyui/models/input /comfyui/models/output

# ---- custom node dos nos Krea2Edit* ----
# Krea2EditModelPatch e Krea2EditGroundedEncode NAO estao no ComfyUI core.
# Pack: https://github.com/lbouaraba/comfyui-krea2edit  (696 stars)
COPY scripts/instalar_krea2edit.py /tmp/instalar_krea2edit.py
RUN python3 /tmp/instalar_krea2edit.py && rm /tmp/instalar_krea2edit.py \
 && test -f /comfyui/custom_nodes/comfyui-krea2edit/__init__.py

# ---- modelo de analise facial (antelopev2) ----
# pulidflux.py carrega FaceAnalysis(name="antelopev2"), que BAIXA do
# GitHub no primeiro uso. Baixar no build em vez do job: se a URL cair,
# o build quebra aqui (barato) e nao no meio de um job de geracao.
#
# Origem: HuggingFace, nao o release do GitHub. O build de 13:26 morreu com
# "HTTP Error 502: Bad Gateway" na urlretrieve contra github.com -- o HF ja
# serviu os outros 19,5 GB deste build sem uma falha. Os 5 arquivos foram
# conferidos byte a byte contra o zip do GitHub (mesmo tamanho, download de
# 360.662.982 bytes).
#
# Sem zip e sem subpasta: figo711/antelopev2 expoe os .onnx na raiz, então
# cada arquivo vai direto para antelopev2/ -- o caminho que o insightface
# procura em <root>/models/antelopev2/.
#
# Download em paralelo (como o resto) + 3 tentativas por arquivo: 502 de
# CDN e intermitente e nao deve custar um build.
RUN set -eux; \
    HF=https://huggingface.co/figo711/antelopev2/resolve/main; \
    mkdir -p /comfyui/models/insightface/models/antelopev2; \
    cd /comfyui/models/insightface/models/antelopev2; \
    wget -q -c -O glintr100.onnx       $HF/glintr100.onnx & \
    wget -q -c -O 1k3d68.onnx          $HF/1k3d68.onnx & \
    wget -q -c -O scrfd_10g_bnkps.onnx $HF/scrfd_10g_bnkps.onnx & \
    wget -q -c -O 2d106det.onnx        $HF/2d106det.onnx & \
    wget -q -c -O genderage.onnx       $HF/genderage.onnx & \
    wait; \
    du -sh .; \
    test -s glintr100.onnx; \
    test -s 1k3d68.onnx; \
    test -s scrfd_10g_bnkps.onnx; \
    test -s 2d106det.onnx; \
    test -s genderage.onnx

# ---- custom node do PuLID (gerador de ancoras) ----
# Repositorio oficial no GitHub foi removido (404); o mirror esta no HF.
# O instalador tambem normaliza as barras invertidas do zip, senao o
# diretorio eva_clip/ fica com o nome literal e o import quebra.
COPY scripts/instalar_pulid.py /tmp/instalar_pulid.py
RUN python3 /tmp/instalar_pulid.py && rm /tmp/instalar_pulid.py \
 && test -f /comfyui/custom_nodes/ComfyUI-PuLID-Flux/__init__.py \
 && test -d /comfyui/custom_nodes/ComfyUI-PuLID-Flux/eva_clip

# ---- custom node do BiRefNet (recorte de fundo da PECA) ----
# POR QUE ESTA CAMADA ESTA AQUI E NAO ACIMA
# Este RUN fica DEPOIS do COPY --from=models de proposito. Qualquer linha
# acima dele invalidaria o cache e faria os 19,5 GB do try-on mais os 9,4 GB
# do gerador baixarem de novo — o build deixaria de ser um cache hit e
# passaria a ser o build completo de meia hora. Aqui so esta camada nova
# entra: 849 MB do peso mais o pip do timm.
#
# POR QUE BiRefNet
# O Krea2Edit monta a peca junto com o que estiver em volta na foto do
# grupo: espelho, cabide, moldura, parede. ate o dia 09/out isso era limpo
# localmente, com rembg, no container da aplicacao. A primeira inferencia do
# ONNX Runtime travava o pool de threads e matava a peca inteira.
#
# Limpar no worker tira o rembg do caminho local e devolve a decisao de
# imagem para um unico lugar. Alem disso, o recorte por segmentacao neural e
# melhor para renda, franja e bordado do que o que o modelo de edicao
# inventaria sozinho a partir do texto.
#
# Instalado por script e nao por git clone: a imagem base nao garante git,
# e o script ainda confere que os nos foram registrados. Detalhe do
#BiRefNet-ZHO estar em scripts/instalar_birefnet.py.
COPY scripts/instalar_birefnet.py /tmp/instalar_birefnet.py
RUN python3 /tmp/instalar_birefnet.py && rm /tmp/instalar_birefnet.py \
 && test -f /comfyui/custom_nodes/ComfyUI-BiRefNet-ZHO/__init__.py \
 && test -s /comfyui/models/BiRefNet/BiRefNet-ep480.pth

# O RunPod GitHub integration exige src/handler.py e src/start.sh.
# O requirements.txt NAO e instalado aqui: runpod, websocket-client e
# requests ja vem na imagem base, e instalar de novo arrisca conflito
# de versao. O handler original era copiado daqui.
COPY src/handler.py src/start.sh src/network_volume.py /

# ------------------------------------------------------------------
# MARCADOR DE BUILD
#
# MOTIVO: ja houve confusao sobre qual imagem estava no endpoint. O
# "disponivel em loras: ..." no erro de validacao do ComfyUI permite ler
# esta string de fora, sem console e sem deploy. Basta pedir um lora
# inexistente e ler a lista que o worker devolve.
#
# ATENCAO: esta camada vem DEPOIS do COPY --from=models de proposito.
# Qualquer alteracao nas linhas acima invalidaria o cache e faria os
# 19,5 GB do try-on baixarem de novo.
# ------------------------------------------------------------------
ARG BUILD_TAG=birefnet-v3
ENV FLOR_DE_SEDA_BUILD=$BUILD_TAG

RUN echo "$BUILD_TAG" > /comfyui/BUILD_TAG \
 && printf 'build=%s\nkrea2_turbo=ok\nqwen3vl_fp8=ok\nqwen3vl_bf16=ok\nqwen_image_vae=ok\nidentity_edit=ok\npulid_flux=ok\npulid_node=ok\nantelopev2=ok\nbirefnet_node=ok\nbirefnet_model=ok\n' \
      "$BUILD_TAG" > /comfyui/BUILD_INFO

# ------------------------------------------------------------------
# HEALTHCHECK
#
# NAO pode importar nada de Python aqui. 'import insightface' carrega
# onnxruntime + opencv + scipy + scikit-image + numpy: 10-30 s, e com
# --timeout estouraria, marcando o container unhealthy e fazendo o
# RunPod reiniciar em laco (sintoma: worker oscila entre initializing e
# throttled e o job fica IN_QUEUE para sempre).
#
# A verificacao pesada de import fica em instalar_pulid.py, no build: se
# o modulo nao carregar, o build QUEBRA -- que e o lugar certo para
# falhar, e nao no boot de todo worker.
#
# Aqui sao so checagens de arquivo (rapidas) mais o processo do ComfyUI.
# start-period generoso: a imagem tem 36 GB e o boot demora.
# ------------------------------------------------------------------
HEALTHCHECK --interval=60s --timeout=20s --start-period=300s --retries=3 \
  CMD test -s /comfyui/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
   && test -s /comfyui/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
   && test -s /comfyui/models/vae/qwen_image_vae.safetensors \
   && test -s /comfyui/models/loras/krea2_identity_edit_v1_2_r128.safetensors \
   && test -s /comfyui/models/text_encoders/qwen3vl_4b_bf16.safetensors \
   && test -s /comfyui/models/pulid/pulid_flux_v0.9.1.safetensors \
   && test -d /comfyui/custom_nodes/ComfyUI-PuLID-Flux/eva_clip \
   && test -s /comfyui/models/insightface/models/antelopev2/glintr100.onnx \
   && test -s /comfyui/custom_nodes/ComfyUI-BiRefNet-ZHO/__init__.py \
   && test -s /comfyui/models/BiRefNet/BiRefNet-ep480.pth \
   && test -s /comfyui/BUILD_TAG \
   && pgrep -f "comfyui/main.py" > /dev/null \
   && echo "pronto ($(cat /comfyui/BUILD_TAG))" || exit 1