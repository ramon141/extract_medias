import unittest

from sources.embed_urls import forcar_serie, parse_embed_url
from sources.errors import SourceError
from sources.models import MediaKind


IFRAME_FILME = (
    '<iframe src="https://myembed.biz/filme/tt22084616" '
    'allow="autoplay;encrypted-media;picture-in-picture" allowfullscreen '
    'frameborder="0" scrolling="no" style="width:100%;border:0;height:70vh"></iframe>'
)


class ParseIframeTest(unittest.TestCase):
    def test_iframe_do_usuario(self) -> None:
        alvo = parse_embed_url(IFRAME_FILME)
        self.assertEqual(alvo.external_id, "tt22084616")
        self.assertEqual(alvo.kind, MediaKind.MOVIE)
        self.assertIsNone(alvo.season)
        self.assertIsNone(alvo.episode)

    def test_iframe_serie_com_temporada_episodio(self) -> None:
        html = '<iframe src="https://myembed.biz/serie/30984/2/7"></iframe>'
        alvo = parse_embed_url(html)
        self.assertEqual(alvo.external_id, "30984")
        self.assertEqual(alvo.kind, MediaKind.SERIES)
        self.assertEqual(alvo.season, 2)
        self.assertEqual(alvo.episode, 7)


class ParseUrlTest(unittest.TestCase):
    def test_url_filme(self) -> None:
        alvo = parse_embed_url("https://myembed.biz/filme/tt22084616")
        self.assertEqual(alvo.external_id, "tt22084616")
        self.assertEqual(alvo.kind, MediaKind.MOVIE)

    def test_url_serie_catalogo(self) -> None:
        alvo = parse_embed_url("https://myembed.biz/serie/30984")
        self.assertEqual(alvo.external_id, "30984")
        self.assertEqual(alvo.kind, MediaKind.SERIES)
        self.assertIsNone(alvo.season)

    def test_url_serie_episodio(self) -> None:
        alvo = parse_embed_url("https://myembed.biz/serie/30984/1/1")
        self.assertEqual(alvo.season, 1)
        self.assertEqual(alvo.episode, 1)

    def test_url_playerflix_direto(self) -> None:
        alvo = parse_embed_url("https://playerflix.ink/filme/tt22084616")
        self.assertEqual(alvo.external_id, "tt22084616")
        self.assertEqual(alvo.kind, MediaKind.MOVIE)

    def test_url_serie_com_temporada_sem_episodio(self) -> None:
        alvo = parse_embed_url("https://myembed.biz/serie/30984/3")
        self.assertEqual(alvo.season, 3)
        self.assertIsNone(alvo.episode)

    def test_dominio_desconhecido_levanta_erro(self) -> None:
        with self.assertRaises(SourceError):
            parse_embed_url("https://outro-player.com/filme/tt22084616")

    def test_caminho_desconhecido_levanta_erro(self) -> None:
        with self.assertRaises(SourceError):
            parse_embed_url("https://myembed.biz/anime/tt22084616")

    def test_filme_sem_imdb_levanta_erro(self) -> None:
        with self.assertRaises(SourceError):
            parse_embed_url("https://myembed.biz/filme/30984")


class ParseIdTest(unittest.TestCase):
    def test_imdb_cru_e_filme(self) -> None:
        alvo = parse_embed_url("tt22084616")
        self.assertEqual(alvo.kind, MediaKind.MOVIE)
        self.assertEqual(alvo.external_id, "tt22084616")

    def test_id_numerico_cru_sem_tipo(self) -> None:
        alvo = parse_embed_url("30984")
        self.assertIsNone(alvo.kind)
        self.assertEqual(forcar_serie(alvo).kind, MediaKind.SERIES)

    def test_id_aleatorio_levanta_erro(self) -> None:
        with self.assertRaises(SourceError):
            parse_embed_url("banana")


if __name__ == "__main__":
    _ = unittest.main()
