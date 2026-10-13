#!/usr/bin/env python3
"""
O Dockerfile do worker vale 28,9 GB em cache.

As camadas de modelo sao deliberadamente as PRIMEIRAS, num stage `models`
separado, e o `COPY --from=models` so acontece no stage final. Isso existe
porque o BuildKit constroi stages em paralelo e o teto do RunPod e 30 min:
se os 28,9 GB e o resto do build fossem sequenciais, nenhum dos dois caberia.

O preco dessa arquitetura e um: qualquer instrucao nova colocada ANTES do
COPY invalida tudo e o build recomeca do zero. O cache nao avisa — ele
simplesmente deixa de bater, e a primeira pista e que o build demora meia
hora do nada.

Estes testes existem para essa regra nao depender de ninguem lembrar do
comentario no arquivo.

   python3 teste/testar_build.py
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = RAIZ / "Dockerfile"
INSTALADOR = RAIZ / "scripts" / "instalar_birefnet.py"


def linhas():
    return DOCKERFILE.read_text(encoding="utf-8").splitlines()


def linha_de(agulha, comentario_ok=False):
    for i, l in enumerate(linhas(), 1):
        if agulha in l and (not l.strip().startswith("#") or comentario_ok):
            return i
    raise AssertionError(f"nao achei {agulha!r} no Dockerfile")


def test_o_stage_de_modelos_vem_primeiro():
    """Sem o stage `models` separado, o build estoura o teto de 30 min."""
    assert linha_de("FROM alpine:3.20 AS models") < linha_de("FROM runpod/worker-comfyui"), (
        "o stage models precisa vir antes do stage final"
    )


def test_toda_camada_nova_fica_depois_do_copy_dos_modelos():
    """O invariante que custa 28,9 GB quando quebrado."""
    copy = linha_de("COPY --from=models")
    for camada in ("instalar_birefnet.py", "instalar_krea2edit.py", "instalar_pulid.py"):
        pos = linha_de(camada)
        assert pos > copy, (
            f"{camada} esta na linha {pos}, antes do COPY --from=models ({copy}). "
            "Isso invalida o cache dos 28,9 GB e o build inteiro recomeca. "
            "Mova a camada para depois do COPY."
        )


def test_o_peso_do_birefnet_entra_no_build_e_nao_no_primeiro_job():
    """Sem isso, o primeiro job paga 849 MB de download — que foi
    exatamente o que o rembg local fez com o container da aplicacao."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "BiRefNet-ep480.pth" in dockerfile, "o peso nao e conferido no build"
    assert "test -s /comfyui/models/BiRefNet/BiRefNet-ep480.pth" in dockerfile, (
        "o healthcheck nao garante que o peso chegou"
    )


def test_o_healthcheck_cobre_o_birefnet():
    """O worker so aceita trafego se o healthcheck passa. Sem as duas
    checagens, um build que perdeu o node sobe assim mesmo e falha no job."""
    bloco = linhas()
    inicio = next(i for i, l in enumerate(bloco) if l.startswith("HEALTHCHECK"))
    cmd = "\n".join(bloco[inicio:])
    assert "ComfyUI-BiRefNet-ZHO/__init__.py" in cmd, "node fora do healthcheck"
    assert "BiRefNet-ep480.pth" in cmd, "peso fora do healthcheck"


def test_o_build_tag_muda():
    """O BUILD_TAG e o unico jeito de ler, de fora, qual imagem esta no
    endpoint: o erro do ComfyUI devolve a lista de loras e o 'disponivel em'
    mostra o prefixo. Sem bump, um diagnostico points to imagem antiga."""
    assert "ARG BUILD_TAG=birefnet-v3" in DOCKERFILE.read_text(encoding="utf-8")


def test_o_instalador_declara_por_que_usa_pth_e_nao_safetensors():
    """torch.load nao abre safetensors. O HF do ZhengPeng7 so publica
    model.safetensors, entao seguir aquela URL passa o build e quebra no
    primeiro job. Este comentario e a defesa contra alguem 'simplificar' a
    URL depois."""
    fonte = INSTALADOR.read_text(encoding="utf-8")
    assert "torch.load" in fonte, "a razao do .pth sumiu do instalador"
    assert "ViperYX" in fonte, "o instalador parou de usar o repo de .pth"
    assert "safetensors" in fonte.lower()


def test_o_instalador_confere_os_nos_registrados():
    """Se o node mudar de nome, o build precisa quebrar. Descobrir no job
    custa um cold start de 36 GB mais uma peca perdida."""
    fonte = INSTALADOR.read_text(encoding="utf-8")
    for no in ("BiRefNet_ModelLoader_Zho", "BiRefNet_Zho"):
        assert no in fonte, f"o instalador nao confere o no {no}"


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except AssertionError as e:
                falhas += 1
                print(f"  FALHA {nome}: {e}")
    print(f"\n{falhas} falha(s)")
    sys.exit(1 if falhas else 0)