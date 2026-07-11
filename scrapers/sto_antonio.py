"""
Scraper para www.lojasantoantonio.com.br (plataforma VTEX IO).

Preço Clube da Meire:
  Obtido via Selenium (Chromium headless) — a página usa React e o preço
  da Meire não está no HTML inicial, só depois da renderização JS.
  Elemento: .lojasantoantonio-shelf-custom-0-x-product-promotion--price-meire-selling--product

Preço regular e disponibilidade: VTEX APIs
  1. Catalog API:          /api/catalog_system/pub/products/search/?fq=linkText:{slug}
  2. Intelligent Search:   /_v/api/intelligent-search/product_search/?query={q}
"""
import os
import re
import shutil
import requests
from .base import ScrapeResult, HEADERS_PADRAO

BASE = "https://www.lojasantoantonio.com.br"
_CLASSE_MEIRE_CSS = (
    "lojasantoantonio-shelf-custom-0-x-product-promotion--price-meire-selling--product"
)

_session = requests.Session()
_session.headers.update({**HEADERS_PADRAO, "Accept": "application/json"})

# Browser Selenium compartilhado — inicializado na primeira chamada,
# fechado via fechar_browser() ao final da coleta.
_driver = None

# Caminhos possíveis para o binário do Chromium (snap e apt)
_CHROME_BINARIES = [
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]

# Caminhos possíveis para o ChromeDriver
_CHROMEDRIVER_PATHS = [
    "/usr/lib/chromium-browser/chromedriver",
    "/snap/chromium/current/usr/lib/chromium-browser/chromedriver",
    "/usr/bin/chromedriver",
]


# ---------------------------------------------------------------------------
# Selenium
# ---------------------------------------------------------------------------

def _init_browser():
    global _driver
    if _driver is None:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,800")
        options.add_argument("--disable-extensions")

        # Localiza binário do Chromium
        chrome_bin = None
        for path in _CHROME_BINARIES:
            if os.path.exists(path):
                chrome_bin = path
                break
        if chrome_bin is None:
            chrome_bin = shutil.which("chromium-browser") or shutil.which("chromium")
        if chrome_bin:
            options.binary_location = chrome_bin

        # Localiza ChromeDriver — prioriza versão do snap
        driver_path = (
            shutil.which("chromium.chromedriver")
            or shutil.which("chromium-chromedriver")
        )
        if driver_path is None:
            for path in _CHROMEDRIVER_PATHS:
                if os.path.exists(path):
                    driver_path = path
                    break
        if driver_path is None:
            driver_path = shutil.which("chromedriver")

        service = Service(driver_path) if driver_path else Service()
        _driver = webdriver.Chrome(service=service, options=options)
    return _driver


def fechar_browser():
    """Fecha o browser Selenium. Chamar após o loop da Sto. Antônio."""
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None


def _preco_meire_selenium(url: str) -> float | None:
    """
    Abre a página com Selenium (Chromium headless) e busca o preço do
    Clube da Meire. Retorna None se o elemento não existir.
    """
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver = _init_browser()
        driver.get(url)

        wait = WebDriverWait(driver, 10)
        el = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, f".{_CLASSE_MEIRE_CSS}")
            )
        )
        return _extrair_preco_br(el.text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extrair_preco_br(texto: str) -> float | None:
    """Converte texto em formato BR (R$ 1.290,50) para float."""
    nums = re.sub(r"[^\d,]", "", texto)
    if not nums:
        return None
    try:
        return float(nums.replace(",", "."))
    except ValueError:
        return None


def _link_text_da_url(url: str) -> str:
    partes = url.rstrip("/").split("/")
    return partes[-1] if partes[-1] != "p" else partes[-2]


def _slug_da_url(url: str) -> str:
    slug    = _link_text_da_url(url)
    palavras = slug.replace("-", " ").split()
    return " ".join(palavras[:6])


def _preco_do_item_catalog(produto: dict) -> tuple[float | None, bool]:
    try:
        oferta     = produto["items"][0]["sellers"][0]["commertialOffer"]
        price      = oferta.get("Price", 0)
        preco      = float(price) if price else None
        disponivel = int(oferta.get("AvailableQuantity", 0)) > 0
        return preco if preco else None, disponivel
    except (KeyError, IndexError, TypeError, ValueError):
        return None, False


def _preco_do_item(produto: dict) -> tuple[float | None, bool]:
    try:
        oferta     = produto["items"][0]["sellers"][0]["commertialOffer"]
        price      = oferta.get("Price", 0)
        preco      = float(price) if price else None
        disponivel = int(oferta.get("AvailableQuantity", 0)) > 0
        return preco if preco else None, disponivel
    except (KeyError, IndexError, TypeError, ValueError):
        return None, False


# ---------------------------------------------------------------------------
# API VTEX
# ---------------------------------------------------------------------------

def _get_preco_api(url: str, ean: str | None, descricao: str | None) -> ScrapeResult:
    """
    Obtém preço regular e disponibilidade via VTEX APIs.
    Tenta Catalog API → Intelligent Search por EAN → por slug → por descrição.
    """
    # 1. Catalog API por linkText
    resultado = _get_preco_catalog(url)
    if resultado.erro is None:
        return resultado

    # 2. Intelligent Search por EAN
    if ean:
        resultado = _get_preco_search(url, ean, ean_esperado=ean)
        if resultado.erro is None:
            return resultado

    # 3. Intelligent Search por slug
    slug      = _slug_da_url(url)
    resultado = _get_preco_search(url, slug, ean_esperado=None)
    if resultado.erro is None:
        return resultado

    # 4. Intelligent Search pela descrição
    if descricao:
        resultado = _get_preco_search(url, descricao, ean_esperado=None)

    return resultado


def _get_preco_catalog(url: str) -> ScrapeResult:
    link_text_original   = _link_text_da_url(url)
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


def _get_preco_search(url: str, query: str, ean_esperado: str | None = None) -> ScrapeResult:
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def get_preco(url: str, ean: str | None = None, descricao: str | None = None) -> ScrapeResult:
    """
    Obtém o preço da Loja Santo Antônio.

    1. Selenium (Chromium headless) → busca preço Clube da Meire no HTML renderizado.
    2. API VTEX → preço regular + disponibilidade (usado como fallback
                  ou quando não há preço Meire).
    """
    url = url.strip()

    preco_meire   = _preco_meire_selenium(url)
    resultado_api = _get_preco_api(url, ean, descricao)

    if preco_meire is not None:
        return ScrapeResult(
            preco=preco_meire,
            disponivel=resultado_api.disponivel,
            url=url,
        )

    return resultado_api


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def buscar_por_ean(ean: str) -> list[dict]:
    try:
        resp = _session.get(
            f"{BASE}/_v/api/intelligent-search/product_search/",
            params={"query": ean, "count": 5, "hideUnavailableItems": "false"},
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
