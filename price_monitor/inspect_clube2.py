"""
Busca produtos com preço do Clube da Meire.
Estratégia: procura no HTML da página de produto pelo padrão de preço de clube.
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
    "SELECT url_santo, descricao FROM produtos WHERE url_santo IS NOT NULL"
).fetchall()

encontrados = 0
for row in rows:
    url = row["url_santo"]
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"  Erro em {url}: {e}")
        continue

    texto = resp.text

    # Procura por padrões de preço de clube: "clube" próximo de "R$"
    # ou elementos específicos de preço diferenciado
    if re.search(r"[Cc]lube.{0,300}R\$|R\$.{0,300}[Cc]lube", texto, re.DOTALL):
        # Descarta os que só têm menções ao menu/rodapé
        trechos = re.findall(r".{0,120}[Cc]lube.{0,120}R\$.{0,120}|.{0,120}R\$.{0,120}[Cc]lube.{0,120}", texto, re.DOTALL)
        trechos_filtrados = [t for t in trechos if "menu" not in t.lower() and "href" not in t.lower()[:50]]
        if trechos_filtrados:
            print(f"\n=== {row['descricao']} ===")
            print(f"    {url}")
            for t in trechos_filtrados[:3]:
                print("   ", t.replace("\n", " ").strip()[:250])
            encontrados += 1
            if encontrados >= 5:
                break

if encontrados == 0:
    print("Nenhum produto com preço de clube encontrado nos primeiros resultados.")
    print("Pode ser que o preço de clube venha de uma API separada ou só para membros logados.")
