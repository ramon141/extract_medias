"""CLI de extração de mídia (myembed/playerflix).

Exemplos:
    # o iframe que o usuário passar, direto:
    python main.py '<iframe src="https://myembed.biz/filme/tt22084616" ...></iframe>'

    # ou por URL / ID
    python main.py https://myembed.biz/filme/tt22084616
    python main.py https://myembed.biz/serie/30984/1/1
    python main.py tt22084616
    python main.py 30984 --serie --temporada 1 --episodio 1     # episódio
    python main.py 30984 --serie                                # catálogo

    --sem-verificar desliga o teste de HTTP dos links achados
    --json          saída como JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from enum import Enum

from sources.embed_urls import forcar_serie, parse_embed_url
from sources.errors import SourceError
from sources.models import Media, MediaKind
from sources.myembed import MyEmbedSource
from sources.registry import SourceRegistry
from sources.resolver import PlaywrightServerResolver


def build_argumentos() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Extrai mídia de iframes myembed.biz / playerflix.ink",
    )
    parser.add_argument("alvo", help="iframe/URL/ID (tt22084616 ou 30984)")
    parser.add_argument("--serie", action="store_true", help="tratar ID numérico como série (TMDB)")
    parser.add_argument("--temporada", type=int, help="temporada (séries)")
    parser.add_argument("--episodio", type=int, help="episódio (séries)")
    parser.add_argument("--sem-verificar", action="store_true", help="não testar os links com HTTP")
    parser.add_argument("--json", action="store_true", help="imprimir JSON")
    return parser


def extrair(args: argparse.Namespace) -> Media:
    alvo = parse_embed_url(args.alvo)
    if args.serie and alvo.kind is None:
        alvo = forcar_serie(alvo)

    resolver = PlaywrightServerResolver(verify=not args.sem_verificar)
    myembed = MyEmbedSource(resolver=resolver)
    registry = SourceRegistry()
    registry.register(myembed)

    if alvo.kind is MediaKind.SERIES or args.serie:
        temporada = args.temporada if args.temporada is not None else alvo.season
        episodio = args.episodio if args.episodio is not None else alvo.episode
        if (temporada is None) != (episodio is None):
            raise SourceError("--temporada e --episodio precisam vir juntos")
        return registry.extract_serie(
            "myembed",
            alvo.external_id,
            season=temporada,
            episode=episodio,
        )
    if args.temporada or args.episodio:
        raise SourceError("--temporada/--episodio só valem para séries")
    return registry.extract("myembed", alvo.external_id)


def to_json(media: Media) -> str:
    def converter(obj: object) -> str:
        if isinstance(obj, Enum):
            return str(obj.value)
        raise TypeError(f"não serializável: {type(obj)}")

    return json.dumps(asdict(media), default=converter, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    args = build_argumentos().parse_args(argv)
    try:
        media = extrair(args)
    except SourceError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 2
    except Exception as erro:  # noqa: BLE001
        print(f"Erro inesperado: {type(erro).__name__}: {erro}", file=sys.stderr)
        return 1

    if args.json:
        print(to_json(media))
        return 0

    episode_links = media.seasons[0].episodes[0].links if media.seasons else media.links
    print(f"Título: {media.title or '?'} [{media.kind.value}]")
    print(f"ID: {media.external_id}")
    if media.poster:
        print(f"Poster: {media.poster}")
    print(f"Links: {len(episode_links)}")
    for link in episode_links:
        rotulo = f" [{link.label}]" if link.label else ""
        print(f"  - ({link.resolution or '?'}{rotulo}) {link.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
