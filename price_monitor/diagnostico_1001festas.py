"""
Diagnóstico do scraper da 1001 Festas.
Execute na pasta price_monitor:
    python diagnostico_1001festas.py
"""
import json
import re
import requests
from scrapers.base import HEADERS_PADRAO

URL_TESTE = "https://1001festas.com.br/p/d/2055054/a/p"  # Açúcar Impalpável Harald

session = requests.Session()
session.headers.update(HEADERS_PADRAO)

print(f"Acessando: {URL_TESTE}\n")

try:
    resp = session.get(URL_TESTE, timeout=20)
    print(f"Status HTTP : {resp.status_code}")
    print(f"URL final   : {resp.url}")
    print(f"Tamanho HTML: {len(resp.text):,} caracteres")
    print(f"Server      : {resp.headers.get('Server', 'n/a')}")
    print(f"Cloudflare? : {'cf-ray' in resp.headers}")
    print()

    html = resp.text

    # ── 1. JSON-LD presente? ──────────────────────────────────────────
    RE_JSONLD = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )
    blocos = RE_JSONLD.findall(html)
    print(f"Blocos JSON-LD encontrados: {len(blocos)}")
    for i, bloco in enumerate(blocos):
        try:
            d = json.loads(bloco)
            tipo = d.get("@type", "?")
            print(f"  [{i}] @type={tipo}", end="")
            if tipo == "Product":
                print(f"  | name={d.get('name','?')} | sku={d.get('sku','?')}", end="")
                oferta = d.get("offers", {})
                print(f"  | price={oferta.get('price','AUSENTE')} | avail={oferta.get('availability','?')}")
            else:
                print()
        except json.JSONDecodeError as e:
            print(f"  [{i}] JSON inválido: {e}")

    # ── 2. Preço aparece em algum lugar no HTML? ─────────────────────
    print()
    ocorrencias_rs = re.findall(r'R\$\s*[\d.,]+', html)
    print(f"Ocorrências de 'R$' no HTML: {len(ocorrencias_rs)}")
    if ocorrencias_rs:
        print(f"  Exemplos: {ocorrencias_rs[:5]}")

    # ── 3. Palavra "price" em scripts ────────────────────────────────
    print()
    scripts_com_price = []
    for s in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        if '"price"' in s or "'price'" in s:
            scripts_com_price.append(s[:300])
    print(f"Scripts com 'price': {len(scripts_com_price)}")
    for trecho in scripts_com_price[:2]:
        print(f"  ---\n  {trecho.strip()[:200]}")

    # ── 4. Cloudflare / desafio? ─────────────────────────────────────
    print()
    if "Just a moment" in html or "cf-browser-verification" in html:
        print("⚠️  CLOUDFLARE detectado — a página retornou um desafio JS.")
        print("   O requests não consegue resolver. Solução: usar Playwright.")
    elif len(html) < 5000:
        print("⚠️  HTML muito pequeno — possível bloqueio ou redirect inesperado.")
        print(f"   Primeiros 500 chars:\n{html[:500]}")
    else:
        print("✅  HTML parece completo (sem bloqueio visível).")

    # ── Salvar HTML para inspeção manual ─────────────────────────────
    with open("debug_1001festas.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\n💾 HTML salvo em debug_1001festas.html — abra no navegador para inspecionar.")

except Exception as e:
    print(f"ERRO: {e}")
