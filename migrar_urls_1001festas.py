"""
Migração pontual: atualiza as URLs da 1001 Festas no banco de dados,
convertendo o formato antigo (/a/p) para o novo (/{slug}/p).

Uso:
    python migrar_urls_1001festas.py
"""
import sqlite3
from pathlib import Path
from scrapers.festas_1001 import corrigir_url

DB_PATH = Path(__file__).parent / "precos.db"


def migrar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    produtos = con.execute(
        "SELECT id, descricao, url_1001 FROM produtos WHERE url_1001 IS NOT NULL"
    ).fetchall()

    atualizados = 0
    for p in produtos:
        url_antiga = p["url_1001"]
        url_nova = corrigir_url(url_antiga, p["descricao"])
        if url_nova != url_antiga:
            con.execute(
                "UPDATE produtos SET url_1001 = ? WHERE id = ?",
                (url_nova, p["id"]),
            )
            print(f"  SKU {p['id']:>6} | {url_antiga}")
            print(f"           → {url_nova}")
            atualizados += 1

    con.commit()
    con.close()
    print(f"\nPronto. {atualizados} URL(s) atualizada(s).")


if __name__ == "__main__":
    migrar()
