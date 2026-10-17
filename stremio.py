"""Addon do Stremio: serve os links do extrator em /stream/<tipo>/<id>.json.

    python stremio.py                 # http://127.0.0.1:7100/manifest.json
    python stremio.py --porta 8000

No Stremio: Addons → "Add addon" → cole a URL do manifest.json.
O id vem do Stremio no formato IMDb: filme "tt0133093", episódio "tt0096697:1:1".
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from sources.models import StreamLink
from sources.myembed import MyEmbedSource

logger = logging.getLogger("stremio")

MANIFEST: dict[str, object] = {
    "id": "local.extract-medias",
    "version": "1.0.0",
    "name": "Extract Medias",
    "description": "Links de vídeo extraídos pelo projeto extract_medias.",
    "resources": ["stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
    "catalogs": [],
}

CACHE_TTL = 120.0  # links expiram em minutos; só evita repetir a extração do mesmo pedido

_ROTA_STREAM = re.compile(r"^/stream/(movie|series)/([^/]+)\.json$")
_ID_FILME = re.compile(r"^tt\d+$")
_ID_EPISODIO = re.compile(r"^(tt\d+):(\d+):(\d+)$")


class Extrator:
    """Extrai os links de um id do Stremio, um pedido por vez (o navegador não é paralelo)."""

    def __init__(self, fonte: MyEmbedSource | None = None) -> None:
        self.fonte = fonte or MyEmbedSource()
        self._trava = threading.Lock()
        self._cache: dict[str, tuple[float, list[StreamLink]]] = {}

    def links(self, tipo: str, identificador: str) -> list[StreamLink]:
        chave = f"{tipo}/{identificador}"
        with self._trava:
            guardado = self._cache.get(chave)
            if guardado and time.monotonic() - guardado[0] < CACHE_TTL:
                return guardado[1]
            encontrados = self.extrair(tipo, identificador)
            if encontrados:  # falha não fica em cache
                self._cache[chave] = (time.monotonic(), encontrados)
            return encontrados

    def extrair(self, tipo: str, identificador: str) -> list[StreamLink]:
        if tipo == "movie":
            if not _ID_FILME.match(identificador):
                return []
            return self.fonte.fetch(identificador).links
        episodio = _ID_EPISODIO.match(identificador)
        if not episodio:
            return []
        media = self.fonte.fetch_serie(
            episodio.group(1), season=int(episodio.group(2)), episode=int(episodio.group(3))
        )
        return media.seasons[0].episodes[0].links


def para_stremio(link: StreamLink) -> dict[str, object]:
    return {
        "url": link.url,
        "name": link.label or "Extract Medias",
        "title": f"{link.label} · {link.resolution}" if link.label else link.resolution,
        "behaviorHints": {"notWebReady": True},
    }


def resposta_stream(extrator: Extrator, tipo: str, identificador: str) -> dict[str, object]:
    try:
        links = extrator.links(tipo, identificador)
    except Exception as erro:  # noqa: BLE001 - o Stremio só precisa de uma lista (vazia)
        logger.warning("falha em %s/%s: %s: %s", tipo, identificador, type(erro).__name__, erro)
        links = []
    return {"streams": [para_stremio(link) for link in links]}


def criar_handler(extrator: Extrator) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _enviar(self, status: int, corpo: dict[str, object] | None) -> None:
            dados = json.dumps(corpo, ensure_ascii=False).encode() if corpo is not None else b""
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_OPTIONS(self) -> None:  # noqa: N802 - nome exigido pelo http.server
            self._enviar(204, None)

        def do_GET(self) -> None:  # noqa: N802
            caminho = unquote(urlparse(self.path).path)
            try:
                if caminho == "/manifest.json":
                    self._enviar(200, MANIFEST)
                    return
                rota = _ROTA_STREAM.match(caminho)
                if rota:
                    self._enviar(200, resposta_stream(extrator, rota.group(1), rota.group(2)))
                    return
                self._enviar(404, {"erro": "não encontrado"})
            except (BrokenPipeError, ConnectionResetError):
                logger.info("Stremio desistiu de esperar %s", caminho)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            logger.info("%s " + format, self.address_string(), *args)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python stremio.py", description="Addon do Stremio")
    _ = parser.add_argument("--porta", type=int, default=7100)
    _ = parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 só se quiser abrir para a rede")
    args = parser.parse_args(argv)
    porta: int = args.porta
    host: str = args.host

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    servidor = ThreadingHTTPServer((host, porta), criar_handler(Extrator()))
    print(f"Addon no ar: http://{host}:{porta}/manifest.json")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
