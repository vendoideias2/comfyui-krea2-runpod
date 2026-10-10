# Imagem COM modelos assados — dispensa Pod e Network Volume.
# Downloads em PARALELO: sao ~21 GB, o gargalo do build e o download.
# Se o build estourar o teto de 30 min do RunPod, caia no plano B (volume + 1 Pod).
FROM runpod/worker-comfyui:latest

ENV HF_HUB_ENABLE_HF_TRANSFER=1 \
    COMFY_POLLING_INTERVAL_MS=500 \
    COMFY_POLLING_MAX_RETRIES=1200 \
    B=https://huggingface.co/Comfy-Org/Krea-2/resolve/main \
    L=https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main

USER root

RUN mkdir -p /workspace/models/diffusion_models \
             /workspace/models/text_encoders \
             /workspace/models/vae \
             /workspace/models/loras \
             /workspace/models/input \
             /workspace/models/output

# ---- 4 downloads simultaneos ----
RUN set -eux; \
    wget -q -c -O /workspace/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
         $B/diffusion_models/krea2_turbo_fp8_scaled.safetensors & \
    wget -q -c -O /workspace/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
         $B/text_encoders/qwen3vl_4b_fp8_scaled.safetensors & \
    wget -q -c -O /workspace/models/vae/qwen_image_vae.safetensors \
         $B/vae/qwen_image_vae.safetensors & \
    wget -q -c -O /workspace/models/loras/krea2_identity_edit_v1_2_r128.safetensors \
         $L/krea2_identity_edit_v1_2_r128.safetensors & \
    wait; \
    du -sh /workspace/models/*/; \
    test -s /workspace/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors; \
    test -s /workspace/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors; \
    test -s /workspace/models/vae/qwen_image_vae.safetensors; \
    test -s /workspace/models/loras/krea2_identity_edit_v1_2_r128.safetensors

# Confere que os 4 arquivos estao la. Sem isso o worker morre em silencio.
HEALTHCHECK --interval=60s --timeout=25s --start-period=90s --retries=5 \
  CMD test -s /workspace/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
   && test -s /workspace/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
   && test -s /workspace/models/vae/qwen_image_vae.safetensors \
   && test -s /workspace/models/loras/krea2_identity_edit_v1_2_r128.safetensors \
   && echo "krea2 pronto" || exit 1