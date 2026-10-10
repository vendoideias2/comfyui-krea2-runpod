#!/usr/bin/env bash
# Baixa a Tríade Base do Krea 2 no Network Volume.
# Roda UMA vez, dentro de um Pod com o volume montado.
set -euo pipefail
M=/workspace/models
B=https://huggingface.co/Comfy-Org/Krea-2/resolve/main
mkdir -p $M/diffusion_models $M/text_encoders $M/vae $M/loras $M/input $M/output

get () {  # url destino
  [ -s "$2" ] && { echo "OK  $(basename "$2")"; return; }
  echo "GET $(basename "$2")"; wget -q --show-progress -c -O "$2" "$1"
}
get $B/diffusion_models/krea2_turbo_fp8_scaled.safetensors $M/diffusion_models/krea2_turbo_fp8_scaled.safetensors
get $B/text_encoders/qwen3vl_4b_fp8_scaled.safetensors   $M/text_encoders/qwen3vl_4b_fp8_scaled.safetensors
get $B/vae/qwen_image_vae.safetensors                     $M/vae/qwen_image_vae.safetensors

# LoRA de EDICAO — OBRIGATORIO. Sem ele a saida sai em mosaico/blocos.
# Krea 2 Identity Edit v1.2 (variante r128). Sem ele nao ha try-on.
mkdir -p $M/loras
get https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main/krea2_identity_edit_v1_2_r128.safetensors \
    $M/loras/krea2_identity_edit_v1_2_r128.safetensors

echo; echo "=== CONTEUDO DO VOLUME ==="
du -sh $M/diffusion_models/* $M/text_encoders/* $M/vae/* 2>/dev/null
df -h /workspace | tail -1
