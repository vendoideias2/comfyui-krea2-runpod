# handler_simples.py - Handler minimo, ZERO dependencias
# Nao usa PIL, numpy, torch, requests. Funciona em qualquer imagem Python.
# Prova que container + handler + endpoint estao OK antes do Krea 2.
import base64, struct, zlib


def _png(width, height, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def handler(event):
    inp = (event or {}).get("input") or {}
    b64_img = base64.b64encode(_png(256, 256, (220, 20, 60))).decode()
    return {
        "status": "COMPLETED",
        "result": b64_img,
        "echo": {k: (v if isinstance(v, (str, int, float)) else type(v).__name__)
                 for k, v in inp.items()},
        "note": "handler minimo OK. Proximo: handler Krea 2 real.",
    }


if __name__ == "__main__":
    r = handler({"input": {"test": "hello"}})
    print("status:", r["status"], "| base64:", len(r["result"]), "chars")
    open("test_output.png", "wb").write(base64.b64decode(r["result"]))
    print("test_output.png gravado")
