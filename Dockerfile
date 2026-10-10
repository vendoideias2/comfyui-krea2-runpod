# Imagem COM modelos assados — dispensa Pod e Network Volume.
# Derivatives de runpod/worker-comfyui: os modelos vao em /comfyui/models (NÃO /workspace).
# Os 4 arquivos baixam em PARALELO: ~19,5 GB é o gargalo do build.
FROM runpod/worker-comfyui:latest

ENV HF_HUB_ENABLE_HF_TRANSFER=1 \
    COMFY_POLLING_INTERVAL_MS=500 \
    COMFY_POLLING_MAX_RETRIES=1200 \
    B=https://huggingface.co/Comfy-Org/Krea-2/resolve/main \
    L=https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main

USER root

# O worker-comfyui instala o ComfyUI em /comfyui. Os modelos vao ali.
RUN mkdir -p /comfyui/models/diffusion_models \
             /comfyui/models/text_encoders \
             /comfyui/models/vae \
             /comfyui/models/loras \
             /comfyui/models/input \
             /comfyui/models/output

# ---- 4 downloads simultaneos (19,5 GB) ----
RUN set -eux; \
    wget -q -c -O /comfyui/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
         $B/diffusion_models/krea2_turbo_fp8_scaled.safetensors & \
    wget -q -c -O /comfyui/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
         $B/text_encoders/qwen3vl_4b_fp8_scaled.safetensors & \
    wget -q -c -O /comfyui/models/vae/qwen_image_vae.safetensors \
         $B/vae/qwen_image_vae.safetensors & \
    wget -q -c -O /comfyui/models/loras/krea2_identity_edit_v1_2_r128.safetensors \
         $L/krea2_identity_edit_v1_2_r128.safetensors & \
    wait; \
    du -sh /comfyui/models/*/; \
    test -s /comfyui/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors; \
    test -s /comfyui/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors; \
    test -s /comfyui/models/vae/qwen_image_vae.safetensors; \
    test -s /comfyui/models/loras/krea2_identity_edit_v1_2_r128.safetensors

# O RunPod GitHub integration exige src/handler.py e src/start.sh.
# A imagem base ja traz /handler.py e CMD /start.sh — aqui a gente reforca
# com os arquivos do repo, identicos aos upstream.
COPY requirements.txt ./
COPY src/handler.py src/start.sh src/network_volume.py /

HEALTHCHECK --interval=60s --timeout=25s --start-period=90s --retries=5 \
  CMD test -s /comfyui/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
   && test -s /comfyui/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
   && test -s /comfyui/models/vae/qwen_image_vae.safetensors \
   && test -s /comfyui/models/loras/krea2_identity_edit_v1_2_r128.safetensors \
   && echo "krea2 pronto" || exit 1