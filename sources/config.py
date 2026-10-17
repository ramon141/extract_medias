"""Credenciais acedidas via variáveis de ambiente (carregadas do .env do projeto).

O .env é simples: linhas ``CHAVE=valor``. Já existente no ambiente vence o
.env (o .env só preenche o que não foi definido).
"""

import os
from pathlib import Path


def diretorio_projeto() -> Path:
    """Raiz do projeto (pasta acima de sources/)."""
    return Path(__file__).resolve().parent.parent


def carregar_env(caminho: Path | None = None) -> dict[str, str]:
    """Lê o .env e só define variáveis que ainda não existem no ambiente."""
    caminho = caminho or diretorio_projeto() / ".env"
    carregadas: dict[str, str] = {}
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError:
        return carregadas
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip().strip("'\"")
        if not chave:
            continue
        if chave not in os.environ:
            os.environ[chave] = valor
        carregadas[chave] = os.environ[chave]
    return carregadas


def variavel(nome: str, padrao: str = "") -> str:
    return os.environ.get(nome, padrao)
