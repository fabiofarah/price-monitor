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

_CLASSE_MEIRE   = "lojasantoantonio-shelf-custom-0-x-product-promotion--price-meire-selling--product"
_CLASSE_PRECO   = "vtex-price-1-x-sellingPriceValue"
_CLASSE_ESTOQUE = "vtex-store-components-3-x-skuSelectorItem--selected"


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


def _extrair_preco_br(texto: str) -> float | None:
    """Converte texto em formato BR (R$ 1.290,50) para float."""
    nums = re.sub(r"[^\d,]", "", texto)   # mantém só dígitos e vírgula
    if not nums:
        return None
    try:
        return float(nums.replace(",", "."))
    except ValueError:
        return None


def _precos_do_html(url: str) -> tuple[float | None, float | None]:
    """
    Busca preços diretamente no HTML da página do produto VTEX.
    Retorna (preco_meire, preco_regular).
    preco_meire  → elemento Clube da Meire (pode ser None se produto não tem clube)
    preco_regular → preço de venda padrão (vtex-price sellingPriceValue)
    """
    try:
        resp = _session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        el_meire = soup.find(class_=_CLASSE_MEIRE)
        preco_meire = _extrair_preco_br(el_meire.get_text()) if el_meire else None

        el_preco = soup.find(class_=_CLASSE_PRECO)
        preco_regular = _extrair_preco_br(el_preco.get_text()) if el_preco else None

        return preco_meire, preco_regular

    except Exception:
        return None, None


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

    Estratégia:
    1. Busca preço Clube da Meire e preço regular direto no HTML da página.
    2. Se o HTML retornar algum preço, usa ele (Meire tem prioridade).
    3. Se o HTML não retornar nada, cai para a VTEX Intelligent Search API.
    """
    url = url.strip()

    # Passo 1: tenta extrair preços do HTML da página do produto
    preco_meire, preco_regular = _precos_do_html(url)

    if preco_meire is not None or preco_regular is not None:
        preco_final = preco_meire if preco_meire is not None else preco_regular
        # Disponibilidade via API (busca rápida para confirmar estoque)
        disponivel = _disponibilidade_api(url, ean)
        return ScrapeResult(preco=preco_final, disponivel=disponivel, url=url)

    # Passo 2: fallback — VTEX Intelligent Search API
    if ean:
        resultado_api = _get_preco_search(url, ean, ean_esperado=ean)
        if resultado_api.erro == "não encontrado":
            slug = _slug_da_url(url)
            resultado_api = _get_preco_search(url, slug, ean_esperado=None)
    else:
        slug = _slug_da_url(url)
        resultado_api = _get_preco_search(url, slug, ean_esperado=None)

    return resultado_api


def _disponibilidade_api(url: str, ean: str | None) -> bool:
    """Consulta a API apenas para verificar disponibilidade em estoque."""
    try:
        query = ean if ean else _slug_da_url(url)
        resp = _session.get(
            f"{BASE}/_v/api/intelligent-search/product_search/",
            params={"query": query, "count": 3},
            timeout=10,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        produtos = resp.json().get("products", [])
        if not produtos:
            return True  # assume disponível se não encontrar na API
        _, disponivel = _preco_do_item(produtos[0])
        return disponivel
    except Exception:
        return True  # assume disponível em caso de erro


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
