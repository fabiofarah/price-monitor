"""
Exporta os preços mais recentes do banco para o Google Sheets.

Estrutura da planilha:
  Coluna A: SKU
  Coluna B: Descrição
  A partir da coluna C: grupos de 3 colunas por semana
    - "{loja} DD/MM" para cada uma das três lojas

Uso:
    python exportar_sheets.py

Cron (ex: toda segunda às 7h):
    0 7 * * 1 /home/fabio/price-monitor/venv/bin/python /home/fabio/price-monitor/exportar_sheets.py
"""

import sqlite3
from datetime import date
from pathlib import Path

import gspread

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

CREDENTIALS  = Path(__file__).parent / "monitor-precos-1001-1fe60bf0df5e.json"
SHEET_ID     = "1RW6kCGUGY2cvQltFux7IcnGS26erxrdI1BLLR0JeX_k"

DB_PATH      = Path(__file__).parent / "precos.db"

LOJAS = [
    ("1001festas",     "1001F"),
    ("sto_antonio",    "Sto.A"),
    ("maria_chocolate","Maria"),
]


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

def _buscar_produtos_e_precos() -> list[dict]:
    """
    Retorna lista de produtos com o último preço registrado por loja.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    produtos = con.execute(
        "SELECT id, sku, descricao FROM produtos ORDER BY descricao"
    ).fetchall()

    resultado = []
    for p in produtos:
        item = {"sku": p["sku"], "descricao": p["descricao"], "precos": {}}
        for loja_key, _ in LOJAS:
            row = con.execute(
                """
                SELECT preco FROM historico_precos
                WHERE produto_id = ? AND loja = ? AND preco IS NOT NULL AND erro IS NULL
                ORDER BY capturado_em DESC
                LIMIT 1
                """,
                (p["id"], loja_key),
            ).fetchone()
            item["precos"][loja_key] = float(row["preco"]) if row else None
        resultado.append(item)

    con.close()
    return resultado


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def _formatar_preco(preco: float | None) -> str:
    if preco is None:
        return "—"
    return f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def exportar():
    hoje = date.today().strftime("%d/%m")

    print(f"Conectando ao Google Sheets...")
    gc = gspread.service_account(filename=str(CREDENTIALS))
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.sheet1

    dados_existentes = ws.get_all_values()

    # -----------------------------------------------------------------------
    # Primeira execução: monta estrutura base (SKU, Descrição + cabeçalhos)
    # -----------------------------------------------------------------------
    if not dados_existentes:
        print("Planilha vazia — criando estrutura inicial...")
        produtos = _buscar_produtos_e_precos()

        cabecalho = ["SKU", "Descrição"]
        for _, sigla in LOJAS:
            cabecalho.append(f"{sigla} {hoje}")

        linhas = [cabecalho]
        for p in produtos:
            linha = [str(p["sku"]), p["descricao"]]
            for loja_key, _ in LOJAS:
                linha.append(_formatar_preco(p["precos"][loja_key]))
            linhas.append(linha)

        ws.update(range_name="A1", values=linhas)
        print(f"Planilha criada com {len(produtos)} produtos.")
        return

    # -----------------------------------------------------------------------
    # Execuções seguintes: adiciona 3 colunas novas à direita
    # -----------------------------------------------------------------------
    print("Adicionando colunas da semana...")
    produtos = _buscar_produtos_e_precos()

    # Descobre a próxima coluna livre (linha de cabeçalho é índice 0)
    proxima_col = len(dados_existentes[0])  # índice 0-based da nova coluna

    # Mapa SKU → índice de linha (linha 0 = cabeçalho)
    sku_para_linha = {}
    for i, linha in enumerate(dados_existentes[1:], start=1):
        if linha:
            sku_para_linha[str(linha[0])] = i

    # Cabeçalhos das 3 novas colunas
    col_letra_inicio = gspread.utils.rowcol_to_a1(1, proxima_col + 1)
    col_letra_fim    = gspread.utils.rowcol_to_a1(1, proxima_col + 3)

    novos_cabecalhos = [[f"{sigla} {hoje}" for _, sigla in LOJAS]]
    ws.update(
        range_name=f"{col_letra_inicio}:{col_letra_fim.replace('1', '1')}",
        values=novos_cabecalhos,
    )

    # Preenche os preços linha a linha
    atualizacoes = []
    for p in produtos:
        idx_linha = sku_para_linha.get(str(p["sku"]))
        if idx_linha is None:
            continue  # produto novo — não estava na planilha (pode-se tratar depois)
        for j, (loja_key, _) in enumerate(LOJAS):
            celula = gspread.utils.rowcol_to_a1(idx_linha + 1, proxima_col + 1 + j)
            atualizacoes.append({
                "range": celula,
                "values": [[_formatar_preco(p["precos"][loja_key])]],
            })

    if atualizacoes:
        ws.batch_update(atualizacoes)

    print(f"Concluído: {len(produtos)} produtos exportados para a semana {hoje}.")


if __name__ == "__main__":
    exportar()
