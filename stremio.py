"""Addon do Stremio: serve os links do extrator em /stream/<tipo>/<id>.json.

    python stremio.py                 # http://127.0.0.1:7100/manifest.json
    python stremio.py --porta 8000
    ADDON_TOKEN=segredo python stremio.py   # addon só responde em /segredo/manifest.json

No Stremio: Addons → "Add addon" → cole a URL do manifest.json.
O id vem do Stremio no formato IMDb: filme "tt0133093", episódio "tt0096697:1:1".
"""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import requests

from sources.models import StreamLink
from sources.myembed import MyEmbedSource
from sources.playerflix import _dict  # pyright: ignore[reportPrivateUsage]
from sources.resolver import USER_AGENT

logger = logging.getLogger("stremio")

MANIFEST: dict[str, object] = {
    "id": "local.extract-medias",
    "version": "1.0.0",
    "name": "Extract Medias",
    "description": "Links de vídeo extraídos pelo projeto extract_medias.",
    "resources": ["stream", "meta"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
    "catalogs": [],
}

CACHE_TTL = 120.0  # links expiram em minutos; só evita repetir a extração do mesmo pedido

_ROTA_STREAM = re.compile(r"^/stream/(movie|series)/([^/]+)\.json$")
_ROTA_META = re.compile(r"^/meta/(movie|series)/(tt\d+)\.json$")
_ID_FILME = re.compile(r"^tt\d+$")
_ID_EPISODIO = re.compile(r"^(tt\d+):(\d+):(\d+)$")


_CINEMETA = "https://v3-cinemeta.strem.io/meta/series/{imdb}.json"


def tmdb_da_serie(imdb: str, timeout: float = 8.0) -> str | None:
    """Código TMDB da série (o catálogo só lista os servidores bons por ele); None se não achar."""
    try:
        resposta = requests.get(_CINEMETA.format(imdb=imdb), timeout=timeout)
        resposta.raise_for_status()
        meta = _dict(_dict(resposta.json()).get("meta"))
    except (requests.RequestException, ValueError):
        return None
    codigo = meta.get("moviedb_id")
    return str(codigo) if isinstance(codigo, int) and codigo > 0 else None


# TMDB Addon (idioma pt-BR, sem catálogos): o catálogo padrão do Stremio só tem inglês
_META_PTBR = os.environ.get(
    "META_PTBR_URL", "https://tmdb.elfhosted.com/N4IgNghgdg5grhGBTEAuEAHALgWgEIBKIANCAMYRYRgD2MAzmgNoC6AvkA"
).rstrip("/")
_META_TTL = 6 * 3600.0
_meta_cache: dict[str, tuple[float, dict[str, object]]] = {}


def meta_ptbr(tipo: str, identificador: str, timeout: float = 15.0) -> dict[str, object] | None:
    """Informações do título em português; None se o serviço falhar (o Stremio usa o próximo addon)."""
    chave = f"{tipo}/{identificador}"
    guardado = _meta_cache.get(chave)
    if guardado and time.monotonic() - guardado[0] < _META_TTL:
        return guardado[1]
    try:
        resposta = requests.get(f"{_META_PTBR}/meta/{chave}.json", timeout=timeout)
        resposta.raise_for_status()
        corpo = _dict(resposta.json())
    except (requests.RequestException, ValueError):
        return None
    if not _dict(corpo.get("meta")).get("name"):
        return None
    _meta_cache[chave] = (time.monotonic(), corpo)
    return corpo


class Extrator:
    """Extrai os links de um id do Stremio; pedidos diferentes andam em paralelo.

    Pedidos iguais ao mesmo tempo (o Stremio repete) esperam uma única extração.
    """

    def __init__(self, fonte: MyEmbedSource | None = None) -> None:
        self.fonte = fonte or MyEmbedSource()
        self._trava = threading.Lock()  # só protege os dicionários abaixo, nunca a extração
        self._cache: dict[str, tuple[float, list[StreamLink]]] = {}
        self._em_andamento: dict[str, Future[list[StreamLink]]] = {}
        self._tmdb: dict[str, str] = {}

    def links(self, tipo: str, identificador: str) -> list[StreamLink]:
        chave = f"{tipo}/{identificador}"
        with self._trava:
            guardado = self._cache.get(chave)
            if guardado and time.monotonic() - guardado[0] < CACHE_TTL:
                return guardado[1]
            espera = self._em_andamento.get(chave)
            dono = espera is None
            if espera is None:
                espera = self._em_andamento[chave] = Future()
        if not dono:
            return espera.result()
        try:
            encontrados = self.extrair(tipo, identificador)
            if encontrados:  # falha não fica em cache
                with self._trava:
                    self._cache[chave] = (time.monotonic(), encontrados)
            espera.set_result(encontrados)
            return encontrados
        except BaseException as erro:
            espera.set_exception(erro)
            raise
        finally:
            with self._trava:
                del self._em_andamento[chave]

    def _buscar_tmdb(self, imdb: str) -> str:
        codigo = tmdb_da_serie(imdb)
        if codigo:
            self._tmdb[imdb] = codigo
        return codigo or imdb  # sem TMDB, segue pelo IMDb (WatchPlay/VidSrc aceitam)

    def fechar(self) -> None:
        self.fonte.resolver.fechar()

    def extrair(self, tipo: str, identificador: str) -> list[StreamLink]:
        if tipo == "movie":
            if not _ID_FILME.match(identificador):
                return []
            return self.fonte.fetch(identificador).links
        episodio = _ID_EPISODIO.match(identificador)
        if not episodio:
            return []
        imdb = episodio.group(1)
        media = self.fonte.fetch_serie(
            self._tmdb.get(imdb) or self._buscar_tmdb(imdb), season=int(episodio.group(2)), episode=int(episodio.group(3))
        )
        return media.seasons[0].episodes[0].links


def para_stremio(link: StreamLink) -> dict[str, object]:
    return {
        "url": link.url,
        "name": link.label or "Extract Medias",
        "title": f"{link.label} · {link.resolution}" if link.label else link.resolution,
        # o Google (Blogger) só serve o vídeo para o mesmo User-Agent que o achou
        "behaviorHints": {
            "notWebReady": True,
            "proxyHeaders": {"request": {"User-Agent": USER_AGENT}},
        },
    }


def resposta_stream(extrator: Extrator, tipo: str, identificador: str) -> dict[str, object]:
    try:
        links = extrator.links(tipo, identificador)
    except Exception as erro:  # noqa: BLE001 - o Stremio só precisa de uma lista (vazia)
        logger.warning("falha em %s/%s: %s: %s", tipo, identificador, type(erro).__name__, erro)
        links = []
    return {"streams": [para_stremio(link) for link in links]}


def sem_token(caminho: str, token: str) -> str | None:
    """Tira o trecho secreto do início do caminho; None se faltar ou estiver errado.

    Sem token configurado, o caminho passa como está. /health fica sempre aberto
    (a checagem de saúde do Docker/Coolify não conhece o segredo) e não expõe nada.
    """
    if not token or caminho == "/health":
        return caminho
    primeiro, _, resto = caminho.removeprefix("/").partition("/")
    if not hmac.compare_digest(primeiro.encode(), token.encode()):
        return None
    return "/" + resto


def criar_handler(extrator: Extrator, token: str = "") -> type[BaseHTTPRequestHandler]:
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
            bruto = unquote(urlparse(self.path).path)
            caminho = sem_token(bruto, token)
            try:
                if caminho == "/health":
                    self._enviar(200, {"ok": True})
                    return
                if caminho is None:  # mesmo 404 de qualquer rota inexistente: não revela que há segredo
                    self._enviar(404, {"erro": "não encontrado"})
                    return
                if caminho == "/manifest.json":
                    self._enviar(200, MANIFEST)
                    return
                rota = _ROTA_STREAM.match(caminho)
                if rota:
                    self._enviar(200, resposta_stream(extrator, rota.group(1), rota.group(2)))
                    return
                rota_meta = _ROTA_META.match(caminho)
                if rota_meta:
                    meta = meta_ptbr(rota_meta.group(1), rota_meta.group(2))
                    self._enviar(200 if meta else 404, meta or {"erro": "não encontrado"})
                    return
                self._enviar(404, {"erro": "não encontrado"})
            except (BrokenPipeError, ConnectionResetError):
                logger.info("Stremio desistiu de esperar")

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
    token = os.environ.get("ADDON_TOKEN", "").strip().strip("/")
    extrator = Extrator()
    servidor = ThreadingHTTPServer((host, porta), criar_handler(extrator, token))
    prefixo = f"/{token}" if token else ""
    print(f"Addon no ar: http://{host}:{porta}{prefixo}/manifest.json")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
        extrator.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
