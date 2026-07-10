"""Inspeciona a página de ofertas do Clube da Meire para encontrar produtos com preço de clube."""
import json, re, requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Tenta via Intelligent Search com filtro de coleção/categoria do clube
resp = requests.get(
    "https://www.lojasantoantonio.com.br/_v/api/intelligent-search/product_search/",
    params={"query": "clube", "count": 5},
    headers={**HEADERS, "Accept": "application/json"},
    timeout=15,
)
data = resp.json()
produtos = data.get("products", [])
print(f"Busca 'clube': {len(produtos)} produtos")
for p in produtos[:3]:
    oferta = p["items"][0]["sellers"][0]["commertialOffer"]
    print(f"  {p['productName']}: Price={oferta.get('Price')} spot={oferta.get('spotPrice')} teasers={oferta.get('teasers')}")

# Busca a página de ofertas do clube
print("\n--- Página /ofertas-clube-da-meire ---")
resp2 = requests.get(
    "https://www.lojasantoantonio.com.br/ofertas-clube-da-meire",
    headers=HEADERS,
    timeout=15,
)
# Procura por links de produtos
urls_produtos = re.findall(r'"(https://www\.lojasantoantonio\.com\.br/[^"]+/p)"', resp2.text)
urls_produtos = list(dict.fromkeys(urls_produtos))  # deduplica mantendo ordem
print(f"Produtos encontrados na página: {len(urls_produtos)}")
for u in urls_produtos[:5]:
    print(" ", u)

# Inspeciona o primeiro produto da página de ofertas
if urls_produtos:
    print("\n--- Inspecionando 1º produto da página de ofertas ---")
    url_prod = urls_produtos[0]
    partes = url_prod.rstrip("/").split("/")
    slug = partes[-1] if partes[-1] != "p" else partes[-2]
    query = " ".join(slug.replace("-", " ").split()[:6])

    resp3 = requests.get(
        "https://www.lojasantoantonio.com.br/_v/api/intelligent-search/product_search/",
        params={"query": query, "count": 1},
        headers={**HEADERS, "Accept": "application/json"},
        timeout=15,
    )
    data3 = resp3.json()
    if data3.get("products"):
        oferta = data3["products"][0]["items"][0]["sellers"][0]["commertialOffer"]
        print(json.dumps(oferta, indent=2, ensure_ascii=False))
