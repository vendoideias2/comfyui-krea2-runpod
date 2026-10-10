# Imagem SLIM — modelos ficam no Network Volume (build ~2 min, sem teto de 30 min)
FROM runpod/worker-comfyui:latest

ENV HF_HUB_ENABLE_HF_TRANSFER=1
ENV COMFY_POLLING_INTERVAL_MS=500
ENV COMFY_POLLING_MAX_RETRIES=1200

# Confere que o volume foi montado e tem os 3 arquivos do Krea 2
HEALTHCHECK --interval=60s --timeout=20s --start-period=120s --retries=5 \
  CMD test -f /workspace/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors \
   && test -f /workspace/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors \
   && test -f /workspace/models/vae/qwen_image_vae.safetensors || exit 1
