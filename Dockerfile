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
FROM runpod/worker-comfyui:5.10.0-base

ENV COMFY_POLLING_INTERVAL_MS=500 \
    COMFY_POLLING_MAX_RETRIES=1200

COPY --from=models /models /comfyui/models

RUN mkdir -p /comfyui/models/input /comfyui/models/output

# O RunPod GitHub integration exige src/handler.py e src/start.sh.
COPY requirements.txt ./
COPY src/handler.py src/start.sh src/network_volume.py /

HEALTHCHECK --interval=60s --timeout=25s --start-period=90s --retries=5 \
  CMD test -s /comfyui/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
   && test -s /comfyui/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
   && test -s /comfyui/models/vae/qwen_image_vae.safetensors \
   && test -s /comfyui/models/loras/krea2_identity_edit_v1_2_r128.safetensors \
   && echo "krea2 pronto" || exit 1