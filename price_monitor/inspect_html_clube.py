"""
Busca no HTML da página de produto o trecho relacionado a 'clube' ou 'Meire'.
Testa os primeiros N produtos da Sto. Antônio.
"""
import sqlite3, re, requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

conn = sqlite3.connect("precos.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT url_santo, descricao FROM produtos WHERE url_santo IS NOT NULL LIMIT 50"
).fetchall()

for row in rows:
    url = row["url_santo"]
    resp = requests.get(url, headers=HEADERS, timeout=15)
    texto = resp.text

    if re.search(r"[Cc]lube|[Mm]eire", texto):
        print(f"\n=== {row['descricao']} ===")
        print(f"    {url}")
        # Pega contexto ao redor da palavra
        for m in re.finditer(r".{0,80}[Cc]lube.{0,80}|.{0,80}[Mm]eire.{0,80}", texto):
            trecho = m.group().strip().replace("\n", " ")
            if len(trecho) > 10:
                print("   ", trecho[:200])
        break  # Mostra só o primeiro que encontrar
