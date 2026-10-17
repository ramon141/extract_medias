import unittest
from dataclasses import dataclass, field

from sources.errors import SourceError
from sources.playerflix import PlayerFlixClient


@dataclass
class RespostaFake:
    body: dict[str, object]

    def json(self) -> object:
        return self.body

    def raise_for_status(self) -> None:
        return None


RESPOSTA_FILME: dict[str, object] = {
    "status": True,
    "data": {
        "id": 46202,
        "title": {"pt": "Homem-Aranha: Um Novo Dia", "en": "Spider-Man: Brand New Day"},
        "bgImage": "https://media.themoviedb.org/t/p/w1920_and_h1080_bestv2/x.jpg",
        "release_date": "2026-07-29",
        "seasons": None,
        "season_count": None,
        "options": [
            {
                "embed": "https://v1.watchplay.shop/movie/tt22084616",
                "lang": "pt-br",
                "label": "WatchPlay",
                "budget": "success",
                "id": "watchplay",
            },
            {
                "embed": "https://embedplayer2.xyz/video/ff4d3dab210c762071b8f711584298cc",
                "lang": "pt-br",
                "label": "VIP Player",
                "budget": "danger",
                "id": "embedplayer",
            },
            {
                "embed": "https://superflixapi.quest/filme/tt22084616?repetido=1",
                "lang": "en-us",
                "label": "Premium",
                "budget": "success",
                "id": "superflixapi",
            },
        ],
    },
}

RESPOSTA_SERIE: dict[str, object] = {
    "status": True,
    "data": {
        "id": 14260,
        "title": {"pt": "Bleach", "en": "Bleach"},
        "bgImage": "https://media.themoviedb.org/o0NsbcIvsllg6CJX0FBFY8wWbsn.jpg",
        "release_date": "2004-10-05",
        "seasons": [
            {
                "id": 950,
                "season_number": 0,
                "release_date": "2004-12-18",
                "episodes": [
                    {
                        "id": 15602,
                        "episode_number": 1,
                        "release_date": "2004-12-18",
                        "images": {"poster": "/a.jpg"},
                    },
                    {
                        "id": 15603,
                        "episode_number": 2,
                        "release_date": "2005-12-06",
                        "images": {"poster": None},
                    },
                ],
            }
        ],
        "season_count": 1,
        "options": [],
    },
}


@dataclass
class SessaoFake:
    body: dict[str, object] = field(default_factory=dict[str, object])
    chamadas: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    headers_enviados: dict[str, str] = field(default_factory=dict[str, str])

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> RespostaFake:
        self.headers_enviados = headers or {}
        self.chamadas.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return RespostaFake(self.body)


class ClientMovieTest(unittest.TestCase):
    def test_filme_mapeia_titulo_e_options(self) -> None:
        sessao = SessaoFake(body=RESPOSTA_FILME)
        client = PlayerFlixClient(session=sessao)
        info, options = client.filme("tt22084616")

        self.assertEqual(info.title, "Homem-Aranha: Um Novo Dia")
        self.assertEqual(info.title_en, "Spider-Man: Brand New Day")
        self.assertEqual(info.release_date, "2026-07-29")
        self.assertEqual(len(options), 3)
        self.assertEqual(options[0].id, "watchplay")
        self.assertFalse(next(o for o in options if o.id == "embedplayer").healthy)

        chamada = sessao.chamadas[0]
        self.assertEqual(chamada["params"], {
            "type": "movie",
            "id": "tt22084616",
            "season": "null",
            "episode": "null",
        })
        self.assertEqual(sessao.headers_enviados.get("X-Requested-With"), "XMLHttpRequest")

    def test_options_saudaveis_e_pt_br_primeiro(self) -> None:
        sessao = SessaoFake(body=RESPOSTA_FILME)
        client = PlayerFlixClient(session=sessao)
        _, options = client.filme("tt22084616")

        self.assertEqual(
            [o.id for o in options],
            ["watchplay", "superflixapi", "embedplayer"],
        )


class ClientSerieTest(unittest.TestCase):
    def test_catalogo_mapeia_temporadas(self) -> None:
        sessao = SessaoFake(body=RESPOSTA_SERIE)
        client = PlayerFlixClient(session=sessao)
        info, temporadas = client.catalogo("30984")

        self.assertEqual(info.title, "Bleach")
        self.assertEqual(list(temporadas), [0])
        episodios = temporadas[0].episodes
        self.assertEqual(episodios[0].number, 1)
        self.assertTrue(episodios[0].poster.startswith("https://"))
        self.assertEqual(episodios[1].number, 2)

        chamada = sessao.chamadas[0]
        self.assertEqual(chamada["params"], {
            "type": "tv",
            "id": "30984",
            "season": "null",
            "episode": "null",
        })

    def test_temporada_episodio_passa_parametros(self) -> None:
        sessao = SessaoFake(body=RESPOSTA_FILME)
        client = PlayerFlixClient(session=sessao)
        client.temporada_episodio("30984", 1, 1)
        self.assertEqual(sessao.chamadas[0]["params"], {
            "type": "tv",
            "id": "30984",
            "season": "1",
            "episode": "1",
        })


class ClientErrosTest(unittest.TestCase):
    def test_status_false_levanta_erro(self) -> None:
        sessao = SessaoFake(body={"status": False, "message": "Requisição inválida (não é AJAX)."})
        client = PlayerFlixClient(session=sessao)
        with self.assertRaises(SourceError):
            client.filme("30984")


if __name__ == "__main__":
    _ = unittest.main()
