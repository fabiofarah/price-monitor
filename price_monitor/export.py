"""
Exporta os últimos preços capturados para um arquivo CSV.
O CSV pode ser aberto diretamente no Excel.

Uso:
    python export.py                        # gera export_precos.csv
    python export.py --saida meu_arquivo.csv
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

from db import init_db, get_ultimos_precos

LOJAS_ORDEM = ["1001festas", "maria_chocolate", "sto_antonio"]
NOMES_LOJAS = {
    "1001festas":       "1001 Festas",
    "maria_chocolate":  "Maria Chocolate",
    "sto_antonio":      "Sto. Antônio",
}


def exportar(caminho_saida: Path | None = None) -> Path:
    init_db()
    rows = get_ultimos_precos()

    # Agrupa por produto
    produtos: dict[int, dict] = {}
    for r in rows:
        pid = r["id"]
        if pid not in produtos:
            produtos[pid] = {
                "sku":       r["sku"],
                "ean":       r["ean"],
                "descricao": r["descricao"],
                "fornecedor": r["fornecedor"],
            }
            for loja in LOJAS_ORDEM:
                produtos[pid][f"preco_{loja}"]      = ""
                produtos[pid][f"disponivel_{loja}"] = ""
                produtos[pid][f"capturado_{loja}"]  = ""

        loja = r["loja"]
        if loja in LOJAS_ORDEM:
            produtos[pid][f"preco_{loja}"]      = r["preco"] if r["preco"] is not None else ""
            produtos[pid][f"disponivel_{loja}"] = "sim" if r["disponivel"] else "não"
            produtos[pid][f"capturado_{loja}"]  = r["capturado_em"]

    if caminho_saida is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        caminho_saida = Path(__file__).parent / f"export_precos_{ts}.csv"

    campos = ["sku", "ean", "descricao", "fornecedor"]
    for loja in LOJAS_ORDEM:
        nome = NOMES_LOJAS[loja]
        campos += [
            f"preco_{nome}",
            f"disponivel_{nome}",
            f"capturado_{nome}",
        ]

    # Renomeia chaves para os cabeçalhos amigáveis
    linhas_saida = []
    for p in produtos.values():
        linha = {
            "sku":        p["sku"],
            "ean":        p["ean"],
            "descricao":  p["descricao"],
            "fornecedor": p["fornecedor"],
        }
        for loja in LOJAS_ORDEM:
            nome = NOMES_LOJAS[loja]
            linha[f"preco_{nome}"]      = p[f"preco_{loja}"]
            linha[f"disponivel_{nome}"] = p[f"disponivel_{loja}"]
            linha[f"capturado_{nome}"]  = p[f"capturado_{loja}"]
        linhas_saida.append(linha)

    with open(caminho_saida, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(linhas_saida)

    print(f"Exportado: {caminho_saida}  ({len(linhas_saida)} produtos)")
    return caminho_saida


if __name__ == "__main__":
    saida = None
    if "--saida" in sys.argv:
        idx = sys.argv.index("--saida")
        saida = Path(sys.argv[idx + 1])
    exportar(saida)
