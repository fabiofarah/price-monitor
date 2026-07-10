"""
Inspeciona a resposta da API VTEX para produtos com Clube Meire.
Busca os primeiros 20 produtos da Sto. Antônio e imprime os que
têm teasers preenchidos ou preço spotPrice diferente do Price.
"""
import sqlite3, json, requests

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
BASE = "https://www.lojasantoantonio.com.br"

conn = sqlite3.connect("precos.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT url_santo FROM produtos WHERE url_santo IS NOT NULL LIMIT 30"
).fetchall()

for row in rows:
    url = row["url_santo"]
    partes = url.rstrip("/").split("/")
    slug = partes[-1] if partes[-1] != "p" else partes[-2]
    query = " ".join(slug.replace("-", " ").split()[:6])

    resp = requests.get(
        f"{BASE}/_v/api/intelligent-search/product_search/",
        params={"query": query, "count": 1},
        headers=HEADERS,
        timeout=15,
    )
    if not resp.ok:
        continue
    data = resp.json()
    produtos = data.get("products", [])
    if not produtos:
        continue

    oferta = produtos[0]["items"][0]["sellers"][0]["commertialOffer"]
    teasers = oferta.get("teasers", [])
    spot = oferta.get("spotPrice")
    price = oferta.get("Price")

    if teasers or (spot and spot != price):
        print(f"\n=== {url} ===")
        print(f"  Price={price}  spotPrice={spot}")
        print(f"  teasers={json.dumps(teasers, ensure_ascii=False)}")
