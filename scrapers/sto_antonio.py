"""
Scraper para www.lojasantoantonio.com.br (plataforma VTEX).

Preço do Clube da Meire: extraído do HTML da página do produto via elemento CSS
  'lojasantoantonio-shelf-custom-0-x-product-promotion--price-meire-selling--product'

Disponibilidade e preço de fallback: via VTEX Intelligent Search API
  /_v/api/intelligent-search/product_search/?query={q}&count={n}
"""
import re
import requests
from bs4 import BeautifulSoup
from .base import ScrapeResult, HEADERS_PADRAO

BASE = "https://www.lojasantoantonio.com.br"

_session = requests.Session()
_session.headers.update({**HEADERS_PADRAO, "Accept": "text/html,application/json"})

_CLASSE_MEIRE = (
    "lojasantoantonio-shelf-custom-0-x-product-promotion--price-meire-selling--product"
)


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


def _preco_meire_do_html(url: str) -> float | None:
    """
    Busca o preço do Clube da Meire diretamente no HTML da página do produto.
    Retorna None se o elemento não existir ou o produto não tiver preço clube.
    """
    try:
        resp = _session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        el = soup.find(class_=_CLASSE_MEIRE)
        if el is None:
            return None

        texto = el.get_text(strip=True)
        # Formato BR: "R$ 12,90" ou "R$1.290,50"
        # Remove tudo exceto dígitos e vírgula, depois converte
        nums = re.sub(r"[^\d,]", "", texto)
        if not nums:
            return None
        return float(nums.replace(",", "."))

    except Exception:
        return None


def _preco_do_item(produto: dict) -> tuple[float | None, bool]:
    """Extrai preço regular e disponibilidade do dict de produto VTEX (API)."""
    try:
        oferta = produto["items"][0]["sellers"][0]["commertialOffer"]
        price = oferta.get("Price", 0)
        preco = float(price) if price else None
        disponivel = int(oferta.get("AvailableQuantity", 0)) > 0
        return preco if preco else None, disponivel
    except (KeyError, IndexError, TypeError, ValueError):
        return None, False


def get_preco(url: str, ean: str | None = None) -> ScrapeResult:
    """
    Obtém o preço da Loja Santo Antônio.

    1. Tenta extrair o preço do Clube da Meire via HTML da página do produto.
    2. Consulta a API para disponibilidade (e preço de fallback se não houver clube).
    """
    url = url.strip()

    # Passo 1: preço Clube da Meire via HTML
    preco_meire = _preco_meire_do_html(url)

    # Passo 2: disponibilidade (e preço regular) via API
    if ean:
        resultado_api = _get_preco_search(url, ean, ean_esperado=ean)
        if resultado_api.erro == "não encontrado":
            slug = _slug_da_url(url)
            resultado_api = _get_preco_search(url, slug, ean_esperado=None)
    else:
        slug = _slug_da_url(url)
        resultado_api = _get_preco_search(url, slug, ean_esperado=None)

    # Passo 3: retorna preço Meire se disponível, senão usa preço da API
    if preco_meire is not None:
        return ScrapeResult(
            preco=preco_meire,
            disponivel=resultado_api.disponivel,
            url=url,
        )

    return resultado_api


def _get_preco_search(url: str, query: str, ean_esperado: str | None = None) -> ScrapeResult:
    """Busca via VTEX Intelligent Search e extrai preço do produto."""
    try:
        resp = _session.get(
            f"{BASE}/_v/api/intelligent-search/product_search/",
            params={"query": query, "count": 5},
            timeout=15,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        produtos = data.get("products", [])

        if not produtos:
            return ScrapeResult(preco=None, disponivel=False, url=url, erro="não encontrado")

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
            headers={"Accept": "application/json"},
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
