import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from sources.models import StreamLink
from stremio import MANIFEST, Extrator, criar_handler, para_stremio


class ExtratorFake(Extrator):
    """Sem rede: devolve links programados e conta quantas extrações reais houve."""

    def __init__(self, links: dict[str, list[StreamLink]]) -> None:
        super().__init__()
        self.programados = links
        self.chamadas: list[str] = []

    def extrair(self, tipo: str, identificador: str) -> list[StreamLink]:
        self.chamadas.append(f"{tipo}/{identificador}")
        return self.programados.get(f"{tipo}/{identificador}", [])


LINK = StreamLink(url="https://cdn.exemplo.invalid/a.m3u8", resolution="auto", label="WatchPlay")


class ServidorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.extrator = ExtratorFake({"movie/tt0133093": [LINK], "series/tt0096697:1:1": [LINK]})
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), criar_handler(self.extrator))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def tearDown(self) -> None:
        self.servidor.shutdown()
        self.servidor.server_close()

    def _json(self, caminho: str) -> dict[str, object]:
        with urlopen(self.base + caminho, timeout=5) as resposta:
            return json.loads(resposta.read())

    def test_manifest(self) -> None:
        self.assertEqual(self._json("/manifest.json"), MANIFEST)

    def test_filme(self) -> None:
        corpo = self._json("/stream/movie/tt0133093.json")
        self.assertEqual(corpo, {"streams": [para_stremio(LINK)]})

    def test_episodio_com_dois_pontos_codificados(self) -> None:
        corpo = self._json("/stream/series/tt0096697%3A1%3A1.json")
        self.assertEqual(corpo, {"streams": [para_stremio(LINK)]})

    def test_sem_video_devolve_lista_vazia(self) -> None:
        self.assertEqual(self._json("/stream/movie/tt9999999.json"), {"streams": []})

    def test_id_invalido_devolve_lista_vazia(self) -> None:
        self.assertEqual(self._json("/stream/series/tt0096697.json"), {"streams": []})

    def test_repetir_pedido_usa_cache(self) -> None:
        _ = self._json("/stream/movie/tt0133093.json")
        _ = self._json("/stream/movie/tt0133093.json")
        self.assertEqual(self.extrator.chamadas, ["movie/tt0133093"])

    def test_rota_desconhecida_404(self) -> None:
        with self.assertRaises(HTTPError) as erro:
            _ = self._json("/nada")
        self.assertEqual(erro.exception.code, 404)


class FormatoStremioTest(unittest.TestCase):
    def test_stream_tem_url_e_nome(self) -> None:
        stream = para_stremio(LINK)
        self.assertEqual(stream["url"], LINK.url)
        self.assertEqual(stream["name"], "WatchPlay")


if __name__ == "__main__":
    _ = unittest.main()
