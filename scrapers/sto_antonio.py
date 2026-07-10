"""
Scraper para www.lojasantoantonio.com.br (plataforma VTEX).
Usa a API REST do VTEX — sem scraping de HTML.

Endpoints usados:
  - Preço por slug:  /api/catalog_system/pub/products/search/{slug}
  - Busca por query: /_v/api/intelligent-search/product_search/?query={q}&count={n}
"""
import requests
from .base import ScrapeResult, HEADERS_PADRAO

BASE = "https://www.lojasantoantonio.com.br"
_session = requests.Session()
_session.headers.update({**HEADERS_PADRAO, "Accept": "application/json"})


def _slug_da_url(url: str) -> str:
    """
    Extrai o slug do produto de uma URL VTEX e converte para query legível.
    Ex: '.../acucar-impalpavel-1kg-82/p' → 'acucar impalpavel 1kg 82'
    O Intelligent Search não aceita slugs com hífens — precisa de espaços.
    """
    partes = url.rstrip("/").split("/")
    slug = partes[-1] if partes[-1] != "p" else partes[-2]
    # Limita a 6 palavras: slugs Callebaut/Sicao têm códigos internos no final
    # que confundem o Intelligent Search (ex: "dcp-10n2101-k10-callebaut")
    palavras = slug.replace("-", " ").split()
    return " ".join(palavras[:6])


def _preco_do_item(produto: dict) -> tuple[float | None, bool]:
    """Extrai preço e disponibilidade do dict de produto VTEX.

    Usa spotPrice (preço do Clube da Meire) quando disponível,
    com fallback para Price (preço normal sem clube).
    """
    try:
        oferta = produto["items"][0]["sellers"][0]["commertialOffer"]
        spot  = oferta.get("spotPrice")
        price = oferta.get("Price", 0)
        preco = float(spot if spot and float(spot) > 0 else price)
        disponivel = int(oferta.get("AvailableQuantity", 0)) > 0
        return preco if preco > 0 else None, disponivel
    except (KeyError, IndexError, TypeError, ValueError):
        return None, False


def get_preco(url: str, ean: str | None = None) -> ScrapeResult:
    """
    Obtém o preço via VTEX Intelligent Search.
    1ª tentativa: busca por EAN (match exato).
    Fallback: busca pelo slug da URL (cobre EANs Callebaut/Sicao não indexados por EAN).
    """
    url = url.strip()

    if ean:
        resultado = _get_preco_search(url, ean, ean_esperado=ean)
        if resultado.erro != "não encontrado":
            return resultado
        # EAN não encontrado — tenta pelo slug
        slug = _slug_da_url(url)
        return _get_preco_search(url, slug, ean_esperado=None)

    slug = _slug_da_url(url)
    return _get_preco_search(url, slug, ean_esperado=None)


def _get_preco_search(url: str, query: str, ean_esperado: str | None = None) -> ScrapeResult:
    """Busca via VTEX Intelligent Search e extrai preço do produto."""
    try:
        resp = _session.get(
            f"{BASE}/_v/api/intelligent-search/product_search/",
            params={"query": query, "count": 5},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        produtos = data.get("products", [])

        if not produtos:
            return ScrapeResult(preco=None, disponivel=False, url=url, erro="não encontrado")

        # Se temos EAN, procura o produto que bate exatamente
        produto_alvo = None
        if ean_esperado:
            for prod in produtos:
                for item in prod.get("items", []):
                    if item.get("ean") == ean_esperado:
                        produto_alvo = prod
                        break
                if produto_alvo:
                    break

        if produto_alvo is None:
            produto_alvo = produtos[0]

        preco, disponivel = _preco_do_item(produto_alvo)
        if preco is None:
            return ScrapeResult(
                preco=None, disponivel=disponivel, url=url,
                erro="preço zero ou ausente na API",
            )
        return ScrapeResult(preco=preco, disponivel=disponivel, url=url)

    except requests.HTTPError as e:
        return ScrapeResult(
            preco=None, disponivel=False, url=url,
            erro=f"HTTP {e.response.status_code}",
        )
    except Exception as e:
        return ScrapeResult(preco=None, disponivel=False, url=url, erro=str(e))


def buscar_por_ean(ean: str) -> list[dict]:
    """
    Busca um produto pelo EAN via Intelligent Search.
    Retorna lista de {'nome', 'url', 'ean', 'preco'} com match exato por EAN.
    Usado pelo módulo de discovery.
    """
    try:
        resp = _session.get(
            f"{BASE}/_v/api/intelligent-search/product_search/",
            params={"query": ean, "count": 5},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        produtos = data.get("products", [])

        resultados = []
        for prod in produtos:
            for item in prod.get("items", []):
                if item.get("ean") == ean:
                    preco, disponivel = _preco_do_item(prod)
                    link_text = prod.get("linkText", "")
                    resultados.append({
                        "nome":       prod.get("productName"),
                        "url":        f"{BASE}/{link_text}/p",
                        "ean":        ean,
                        "preco":      preco,
                        "disponivel": disponivel,
                    })
                    break

        return resultados
    except Exception:
        return []
