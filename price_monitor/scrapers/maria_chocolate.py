"""
Scraper para www.mariachocolate.com.br
Usa requests + BeautifulSoup. Preço está em texto simples: "Por R$ XX,XX".
"""
import time
import requests
from bs4 import BeautifulSoup
from .base import ScrapeResult, parse_preco_por, HEADERS_PADRAO

BASE_URL = "https://www.mariachocolate.com.br"
_session = requests.Session()
_session.headers.update(HEADERS_PADRAO)


def get_preco(url: str) -> ScrapeResult:
    url = url.strip()
    try:
        resp = _session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        texto = soup.get_text(" ", strip=True)
        preco = parse_preco_por(texto)

        if preco is None:
            # Produto pode estar fora de estoque ou sem preço exibido
            indisponivel = any(
                kw in texto.lower()
                for kw in ("indisponível", "fora de estoque", "esgotado")
            )
            return ScrapeResult(
                preco=None,
                disponivel=False,
                url=url,
                erro="preço não encontrado" + (" (indisponível)" if indisponivel else ""),
            )

        return ScrapeResult(preco=preco, disponivel=True, url=url)

    except requests.HTTPError as e:
        return ScrapeResult(
            preco=None, disponivel=False, url=url,
            erro=f"HTTP {e.response.status_code}",
        )
    except Exception as e:
        return ScrapeResult(preco=None, disponivel=False, url=url, erro=str(e))


def buscar_produtos(query: str, max_resultados: int = 5) -> list[dict]:
    """
    Busca produtos por texto. Retorna lista de {'nome', 'url', 'preco'}.
    Usado pelo módulo de discovery para encontrar produtos faltantes.
    """
    url = f"{BASE_URL}/busca/"
    try:
        resp = _session.get(url, params={"q": query}, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        resultados = []
        # Cada produto aparece como um card com link e texto de preço
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href.endswith("-p"):
                continue
            nome = a.get_text(" ", strip=True)
            if not nome or len(nome) < 5:
                continue
            url_prod = href if href.startswith("http") else BASE_URL + href
            resultados.append({"nome": nome, "url": url_prod, "preco": None})
            if len(resultados) >= max_resultados:
                break

        return resultados
    except Exception:
        return []
