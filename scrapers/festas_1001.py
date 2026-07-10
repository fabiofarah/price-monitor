"""
Scraper para 1001festas.com.br (plataforma Regex Solutions).
URL no formato: https://1001festas.com.br/p/d/{codigo_regex}/{slug}/p

O preço não está no HTML visível — está em um bloco JSON-LD (schema.org Product)
embutido na página:
  <script type="application/ld+json">{"offers":{"price":"11.99", ...}}</script>

Disponibilidade via offers.availability:
  "https://schema.org/InStock"    → disponível
  "https://schema.org/OutOfStock" → indisponível

ATENÇÃO: o formato antigo /p/d/{codigo}/a/p foi descontinuado e retorna a
homepage em vez do produto. Use _corrigir_url() para migrar URLs antigas.
"""
import json
import re
import unicodedata
import requests
from .base import ScrapeResult, HEADERS_PADRAO

_session = requests.Session()
_session.headers.update(HEADERS_PADRAO)

_RE_JSONLD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)
# Detecta o formato antigo: .../p/d/{codigo}/a/p
_RE_URL_ANTIGA = re.compile(r"(https://1001festas\.com\.br/p/d/\d+)/a/p$")


def _gerar_slug(texto: str) -> str:
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", "", texto)
    texto = re.sub(r"\s+", "-", texto.strip())
    return re.sub(r"-+", "-", texto)


def corrigir_url(url: str, descricao: str) -> str:
    """Converte URL antiga (/a/p) para o novo formato (/{slug}/p)."""
    m = _RE_URL_ANTIGA.match(url.strip())
    if m:
        return f"{m.group(1)}/{_gerar_slug(descricao)}/p"
    return url


def _extrair_jsonld(html: str) -> dict | None:
    """Retorna o primeiro bloco JSON-LD do tipo Product, com ou sem offers."""
    for m in _RE_JSONLD.finditer(html):
        try:
            data = json.loads(m.group(1))
            if data.get("@type") == "Product":
                return data
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def get_preco(url: str) -> ScrapeResult:
    url = url.strip()
    try:
        resp = _session.get(url, timeout=20)
        resp.raise_for_status()

        dados = _extrair_jsonld(resp.text)
        if dados is None:
            return ScrapeResult(
                preco=None, disponivel=False, url=url,
                erro="JSON-LD não encontrado",
            )

        # Plataforma Regex retorna "undefined" quando o codigo_regex não existe no catálogo
        if dados.get("sku") == "undefined" or dados.get("name") == "undefined":
            return ScrapeResult(
                preco=None, disponivel=False, url=url,
                erro="produto não encontrado no catálogo (codigo_regex inválido)",
            )

        oferta = dados["offers"]
        preco_str = oferta.get("price", "")
        try:
            preco = float(preco_str) if preco_str else None
        except ValueError:
            preco = None

        disponivel = "OutOfStock" not in oferta.get("availability", "InStock")

        if preco is None or preco == 0:
            return ScrapeResult(
                preco=None, disponivel=disponivel, url=url,
                erro="preço não encontrado no JSON-LD",
            )

        return ScrapeResult(preco=preco, disponivel=disponivel, url=url)

    except requests.HTTPError as e:
        return ScrapeResult(
            preco=None, disponivel=False, url=url,
            erro=f"HTTP {e.response.status_code}",
        )
    except Exception as e:
        return ScrapeResult(preco=None, disponivel=False, url=url, erro=str(e))
