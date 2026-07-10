import sqlite3, json, requests

conn = sqlite3.connect("precos.db")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT url_santo FROM produtos WHERE url_santo IS NOT NULL LIMIT 1").fetchone()
url = row["url_santo"]
print("URL:", url)

partes = url.rstrip("/").split("/")
slug = partes[-1] if partes[-1] != "p" else partes[-2]
query = " ".join(slug.replace("-", " ").split()[:6])
print("Query:", query)

resp = requests.get(
    "https://www.lojasantoantonio.com.br/_v/api/intelligent-search/product_search/",
    params={"query": query, "count": 1},
    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    timeout=15,
)
data = resp.json()
if data.get("products"):
    prod = data["products"][0]
    oferta = prod["items"][0]["sellers"][0]["commertialOffer"]
    print(json.dumps(oferta, indent=2, ensure_ascii=False))
else:
    print("Nenhum produto retornado")
