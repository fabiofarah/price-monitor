"""Tipos e utilitários compartilhados pelos scrapers."""
import re
from dataclasses import dataclass, field


@dataclass
class ScrapeResult:
    preco: float | None
    disponivel: bool
    url: str | None
    erro: str | None = None


_RE_PRECO = re.compile(r"R\$\s*([\d.]+,\d{2})")
_RE_POR_PRECO = re.compile(r"[Pp]or\s+R\$\s*([\d.]+,\d{2})")


def _to_float(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def parse_preco(texto: str) -> float | None:
    """Extrai o primeiro valor R$ encontrado no texto. Retorna None se não achar."""
    m = _RE_PRECO.search(texto)
    if not m:
        return None
    valor = _to_float(m.group(1))
    return valor if valor > 0 else None


def parse_preco_por(texto: str) -> float | None:
    """Extrai valor após 'Por R$' ou 'por R$' (preço final quando há desconto)."""
    m = _RE_POR_PRECO.search(texto)
    if not m:
        return parse_preco(texto)
    valor = _to_float(m.group(1))
    return valor if valor > 0 else None


HEADERS_PADRAO = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
