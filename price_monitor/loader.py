"""
Lê o arquivo Excel e popula a tabela de produtos no banco.
Execute este módulo uma vez antes de rodar o monitor.
"""
from pathlib import Path
import openpyxl
from db import init_db, upsert_produto

EXCEL_PATH = Path(__file__).parent.parent / "Lista produtos.xlsx"

_LOJAS = ("maria", "nova", "santo")


def _url_valida(valor) -> str | None:
    if not valor:
        return None
    s = str(valor).strip()
    return s if s.startswith("http") else None


def carregar_produtos() -> int:
    """Importa todos os produtos do Excel para o banco. Retorna a contagem."""
    init_db()
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb.active

    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        sku = row[1]
        if not sku:
            continue

        produto = {
            "sku":          int(sku),
            "ean":          str(row[2]).strip() if row[2] else None,
            "codigo_regex": int(row[3]) if row[3] else None,
            "descricao":    row[4],
            "fornecedor":   row[0],
            "url_1001":     _url_valida(row[5]),   # lê o link direto da célula
            "url_maria":    _url_valida(row[6]),
            "url_nova":     _url_valida(row[7]),
            "url_santo":    _url_valida(row[8]),
        }
        upsert_produto(produto)
        count += 1

    print(f"{count} produtos importados para o banco.")
    return count


if __name__ == "__main__":
    carregar_produtos()
