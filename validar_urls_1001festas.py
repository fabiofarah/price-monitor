"""
Testa todas as URLs da 1001 Festas no banco e grava o resultado em CSV.
Execute via: validar_urls_1001festas.bat
"""
import json, re, sqlite3, time, csv
from datetime import datetime
from pathlib import Path

import requests

DB = Path(__file__).parent / "precos.db"
SAIDA = Path(__file__).parent / f"validacao_urls_1001festas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
RE_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL)

session = requests.Session()
session.headers.update(HEADERS)

def checar(url):
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return "erro_http", None, f"HTTP {r.status_code}"
        for m in RE_JSONLD.finditer(r.text):
            try:
                d = json.loads(m.group(1))
                if d.get("@type") != "Product":
                    continue
                if d.get("sku") == "undefined" or d.get("name") == "undefined":
                    return "produto_nao_encontrado", None, "sku=undefined"
                oferta = d.get("offers", {})
                avail = oferta.get("availability", "")
                disponivel = "OutOfStock" not in avail
                preco_str = oferta.get("price", "")
                preco = float(preco_str) if preco_str else None
                if not disponivel:
                    return "indisponivel", preco, "OutOfStock"
                if not preco:
                    return "sem_preco", None, "price ausente no JSON-LD"
                return "ok", preco, ""
            except Exception:
                continue
        return "sem_jsonld", None, "JSON-LD não encontrado (possível URL errada)"
    except Exception as e:
        return "erro", None, str(e)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
produtos = conn.execute("SELECT sku, ean, descricao, url_1001 FROM produtos ORDER BY descricao").fetchall()
conn.close()

total = len(produtos)
contagem = {"ok": 0, "indisponivel": 0, "produto_nao_encontrado": 0, "sem_jsonld": 0, "sem_preco": 0, "erro_http": 0, "erro": 0}

print(f"Testando {total} URLs...\n")

with open(SAIDA, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["SKU", "EAN", "Descrição", "URL", "Status", "Preço", "Detalhe"])
    for i, p in enumerate(produtos, 1):
        url = p["url_1001"] or ""
        status, preco, detalhe = checar(url) if url else ("sem_url", None, "")
        contagem[status] = contagem.get(status, 0) + 1
        preco_fmt = f"{preco:.2f}".replace(".", ",") if preco else ""
        w.writerow([p["sku"], p["ean"], p["descricao"], url, status, preco_fmt, detalhe])
        icone = "✅" if status == "ok" else ("⚠️" if status == "indisponivel" else "❌")
        print(f"[{i:3d}/{total}] {icone} {p['descricao'][:45]:45s} {status}  {preco_fmt}")
        time.sleep(0.8)

print(f"\n{'='*60}")
print(f"Resultado final:")
for s, n in sorted(contagem.items(), key=lambda x: -x[1]):
    print(f"  {s:30s}: {n}")
print(f"\nCSV salvo em: {SAIDA.name}")
