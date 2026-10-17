# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Extrai links de vídeo (m3u8/mp4/mpd) de iframes `myembed.biz` / `playerflix.ink`. Dois pontos de entrada: CLI (`main.py`) e addon do Stremio (`stremio.py`, servidor HTTP em `/stream/<tipo>/<id>.json`). Código, mensagens e docstrings em português.

## Comandos

Python >=3.13, venv em `.venv`. Dependências no `pyproject.toml` (única fonte das versões; o Dockerfile lê dele).

```bash
.venv/bin/python -m unittest discover -s tests -t .       # todos os testes (unittest, não pytest)
.venv/bin/python -m unittest tests.test_myembed           # um módulo
.venv/bin/python -m unittest tests.test_myembed.NomeClasse.test_x   # um teste
.venv/bin/pyright                                         # type check (strict, ver abaixo)

.venv/bin/python main.py tt22084616                       # filme (aceita iframe/URL/ID)
.venv/bin/python main.py 30984 --serie --temporada 1 --episodio 1   # episódio (ID TMDB)
.venv/bin/python main.py 30984 --serie                    # catálogo da série
.venv/bin/python stremio.py --porta 7000                  # addon Stremio
docker compose up --build                                 # addon em container (127.0.0.1:7000)
```

Flags do CLI: `--sem-verificar` (não testa links via HTTP), `--json`.

## Arquitetura

Fluxo: `parse_embed_url` → `Source` (via `SourceRegistry`) → `PlayerFlixClient` (API Ajax do playerflix: metadados + lista de servers) → `PlaywrightServerResolver` (servers → URLs de mídia reais) → `Media`/`StreamLink`.

- `sources/base.py` / `registry.py`: contrato `Source` (`fetch` filme, `fetch_serie` série) e registro por nome. `factories.default_registry()` monta o padrão; `main.py` monta o seu próprio.
- `sources/embed_urls.py`: interpreta iframe/URL/ID. IMDb `tt…` = filme; **série usa ID TMDB** (numérico) — URLs de série também aceitam IMDb `tt…`.
- `sources/myembed.py`: `MyEmbedSource`, única fonte. Acrescenta o server extra vidsrc depois dos do playerflix e ignora servers que o playerflix marca como não saudáveis.
- `sources/resolver.py`: coração da extração. Tenta primeiro `sources/direct.py` (só HTTP, ex.: WatchPlay); se o player não permitir, abre Chromium via Playwright, escuta a rede e captura requisições de vídeo (regex `_STREAM_RE`), clicando em seletores de play comuns se preciso. Verifica cada link por HTTP salvo `verify=False`.
- `sources/captcha.py`: cliente CapMonster Cloud (REST) para o Cloudflare Turnstile do server Premium; o token é injetado na página pelo resolver. Chave em `CAPMONSTER_CLIENT_KEY` (ou `CAPMONSTER_API_KEY`).
- `sources/config.py`: lê `.env` da raiz; variável já presente no ambiente vence o `.env`.
- `sources/models.py`: dataclasses `Media` → `Season` → `Episode` → `StreamLink`. Filme usa `Media.links`; série com s/e usa `seasons[0].episodes[0].links`; catálogo vem sem links.
- `stremio.py`: `Extrator` serializa pedidos com lock (navegador não é paralelo) e guarda cache de 120 s só para extrações com sucesso. Ids do Stremio: `tt123` (filme) e `tt123:T:E` (episódio).
- `errors.SourceError`: erro esperado de negócio; o CLI sai com código 2 (1 para erro inesperado).

`extractor/` e `media/` são código legado anterior (Selenium, imports quebrados, ex.: `from constants import *`); não fazem parte do fluxo atual, não estão no Dockerfile e os testes não os cobrem.

## Convenções

- Pyright em modo `strict` com `reportUnknown*` como erro: proibido `Any`/`unknown`; dados JSON externos são tipados via helpers (`_dict`, `_str`, `_int` em `playerflix.py`) e `Protocol` (`SessaoProtocol`) para injetar sessões/clientes falsos nos testes.
- Testes usam fakes injetados (cliente, resolver, sessão) — sem rede nem navegador real.
- Imports de tipos do Playwright ficam sob `TYPE_CHECKING` em `resolver.py`.
