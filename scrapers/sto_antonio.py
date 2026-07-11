"""
Scraper para www.lojasantoantonio.com.br (plataforma VTEX).

Estratégia de busca de preço (em ordem):
  1. VTEX Catalog API por linkText da URL — busca direta, mais confiável.
     Endpoint: /api/catalog_system/pub/products/search/?fq=linkText:{slug}
     Retorna spotPrice (Clube da Meire) com fallback para Price (regular).
  2. VTEX Intelligent Search por EAN — para produtos indexados por EAN.
  3. VTEX Intelligent Search por slug — último recurso.
"""
import re
import requests
from .base import ScrapeResult, HEADERS_PADRAO

BASE = "https://www.lojasantoantonio.com.br"

_session = requests.Session()
_session.headers.update({**HEADERS_PADRAO, "Accept": "application/json"})


def _link_text_da_url(url: str) -> str:
    """Extrai o linkText (slug) da URL do produto. Ex: '.../produto-x/p' → 'produto-x'"""
    partes = url.rstrip("/").split("/")
    return partes[-1] if partes[-1] != "p" else partes[-2]


def _slug_da_url(url: str) -> str:
    """
    Converte o slug da URL em query para o Intelligent Search.
    Limita a 6 palavras para evitar que códigos internos (Callebaut/Sicao)
    confundam a busca.
    """
    slug = _link_text_da_url(url)
    palavras = slug.replace("-", " ").split()
    return " ".join(palavras[:6])


def _preco_do_item_catalog(produto: dict) -> tuple[float | None, bool]:
    """
    Extrai preço e disponibilidade do dict retornado pela Catalog API.
    Usa spotPrice (Clube da Meire) com fallback para Price (regular).
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


def _preco_do_item(produto: dict) -> tuple[float | None, bool]:
    """
    Extrai preço e disponibilidade do dict retornado pela Intelligent Search API.
    Usa spotPrice (Clube da Meire) com fallback para Price (regular).
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


def _get_preco_catalog(url: str) -> ScrapeResult:
    """
    Busca produto via VTEX Catalog API pelo linkText da URL.
    Tenta primeiro com o linkText normalizado (dashes simples),
    depois com o linkText original caso não encontre.
    """
    link_text_original = _link_text_da_url(url)
    # VTEX armazena linkText com dashes simples; URLs podem ter múltiplos dashes
    link_text_normalizado = re.sub(r"-+", "-", link_text_original)

    candidatos = [link_text_normalizado]
    if link_text_original != link_text_normalizado:
        candidatos.append(link_text_original)

    for link_text in candidatos:
        try:
            resp = _session.get(
                f"{BASE}/api/catalog_system/pub/products/search/",
                params={"fq": f"linkText:{link_text}"},
                timeout=15,
            )
            resp.raise_for_status()
            produtos = resp.json()

            if not produtos:
                continue

            preco, disponivel = _preco_do_item_catalog(produtos[0])
            if preco is None:
                return ScrapeResult(preco=None, disponivel=disponivel, url=url,
                                    erro="preço zero ou ausente na Catalog API")
            return ScrapeResult(preco=preco, disponivel=disponivel, url=url)

        except requests.HTTPError as e:
            return ScrapeResult(preco=None, disponivel=False, url=url,
                                erro=f"HTTP {e.response.status_code}")
        except Exception as e:
            return ScrapeResult(preco=None, disponivel=False, url=url, erro=str(e))

    return ScrapeResult(preco=None, disponivel=False, url=url, erro="não encontrado")


def get_preco(url: str, ean: str | None = None, descricao: str | None = None) -> ScrapeResult:
    """
    Obtém o preço da Loja Santo Antônio.

    1. Catalog API pelo linkText da URL.
    2. Intelligent Search por EAN.
    3. Intelligent Search por slug da URL.
    4. Intelligent Search pela descrição do produto (fallback quando o slug
       usa termos internos que não batem com o nome real, ex: "gold" vs "Nobre").
    """
    url = url.strip()

    # Passo 1: Catalog API — busca direta pelo slug da URL
    resultado = _get_preco_catalog(url)
    if resultado.erro is None:
        return resultado

    # Passo 2: Intelligent Search por EAN
    if ean:
        resultado = _get_preco_search(url, ean, ean_esperado=ean)
        if resultado.erro is None:
            return resultado

    # Passo 3: Intelligent Search por slug da URL
    slug = _slug_da_url(url)
    resultado = _get_preco_search(url, slug, ean_esperado=None)
    if resultado.erro is None:
        return resultado

    # Passo 4: Intelligent Search pela descrição do produto
    if descricao:
        resultado = _get_preco_search(url, descricao, ean_esperado=None)

    return resultado


def _get_preco_search(url: str, query: str, ean_esperado: str | None = None) -> ScrapeResult:
    """Busca via VTEX Intelligent Search e extrai preço do produto."""
    try:
        resp = _session.get(
            f"{BASE}/_v/api/intelligent-search/product_search/",
            params={"query": query, "count": 5, "hideUnavailableItems": "false"},
            timeout=15,
        )
        resp.raise_for_status()
        produtos = resp.json().get("products", [])

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
            return ScrapeResult(preco=None, disponivel=disponivel, url=url,
                                erro="preço zero ou ausente na API")
        return ScrapeResult(preco=preco, disponivel=disponivel, url=url)

    except requests.HTTPError as e:
        return ScrapeResult(preco=None, disponivel=False, url=url,
                            erro=f"HTTP {e.response.status_code}")
    except Exception as e:
        return ScrapeResult(preco=None, disponivel=False, url=url, erro=str(e))


def buscar_por_ean(ean: str) -> list[dict]:
    """
    Busca um produto pelo EAN via Intelligent Search.
    Retorna lista de {'nome', 'url', 'ean', 'preco'} com match exato por EAN.
    """
    try:
        resp = _session.get(
            f"{BASE}/_v/api/intelligent-search/product_search/",
            params={"query": ean, "count": 5},
            timeout=15,
        )
        resp.raise_for_status()
        produtos = resp.json().get("products", [])

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
