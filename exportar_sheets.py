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
from datetime import date, datetime, timedelta
from pathlib import Path

import gspread

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

CREDENTIALS  = Path(__file__).parent / "monitor-precos-1001.json"
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

def _buscar_datas_coleta() -> list[str]:
    """
    Retorna 4 datas de coleta: hoje, hoje-7, hoje-14 e hoje-21 dias.
    Se não houver coleta exata nessa data, usa a data disponível mais próxima.
    Retorna em ordem cronológica, sem duplicatas.
    """
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """
        SELECT DISTINCT date(capturado_em) as data
        FROM historico_precos
        WHERE preco IS NOT NULL AND erro IS NULL
        ORDER BY data
        """,
    ).fetchall()
    con.close()

    datas_disponiveis = [row[0] for row in rows]
    if not datas_disponiveis:
        return []

    hoje = date.today()
    alvos = [hoje - timedelta(weeks=i) for i in range(3, -1, -1)]  # [hoje-21, hoje-14, hoje-7, hoje]

    resultado = []
    vistas: set = set()
    for alvo in alvos:
        mais_proxima = min(
            datas_disponiveis,
            key=lambda d: abs((datetime.strptime(d, "%Y-%m-%d").date() - alvo).days),
        )
        if mais_proxima not in vistas:
            vistas.add(mais_proxima)
            resultado.append(mais_proxima)

    return resultado


def _buscar_precos_na_data(data: str) -> dict:
    """Retorna {produto_id: {loja: preco}} com o preço mais recente do dia informado."""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """
        SELECT produto_id, loja, preco
        FROM historico_precos
        WHERE date(capturado_em) = ? AND preco IS NOT NULL AND erro IS NULL
        ORDER BY capturado_em DESC
        """,
        (data,),
    ).fetchall()
    con.close()

    resultado: dict = {}
    for produto_id, loja, preco in rows:
        if produto_id not in resultado:
            resultado[produto_id] = {}
        if loja not in resultado[produto_id]:  # pega só o mais recente do dia
            resultado[produto_id][loja] = float(preco)
    return resultado


def _buscar_produtos_e_precos() -> list[dict]:
    """Retorna lista de produtos com o último preço registrado por loja."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    produtos = con.execute(
        "SELECT id, sku, descricao FROM produtos ORDER BY descricao"
    ).fetchall()

    resultado = []
    for p in produtos:
        item = {"id": p["id"], "sku": p["sku"], "descricao": p["descricao"], "precos": {}}
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
        return ""
    return round(preco, 2)


def exportar():
    hoje = date.today().strftime("%d/%m")

    print(f"Conectando ao Google Sheets...")
    gc = gspread.service_account(filename=str(CREDENTIALS))
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.sheet1

    dados_existentes = ws.get_all_values()

    # -----------------------------------------------------------------------
    # Primeira execução: monta estrutura base (SKU, Descrição + cabeçalhos)
    # Detecta pela presença do cabeçalho "SKU" na célula A1
    # -----------------------------------------------------------------------
    cabecalho_existe = (
        dados_existentes
        and dados_existentes[0]
        and dados_existentes[0][0] == "SKU"
    )

    if not cabecalho_existe:
        print("Planilha vazia — criando estrutura com as últimas 4 semanas...")
        produtos = _buscar_produtos_e_precos()
        datas = _buscar_datas_coleta()

        # Cabeçalho: SKU, Descrição + 3 colunas por data
        cabecalho = ["SKU", "Descrição"]
        for data in datas:
            dd_mm = datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m")
            for _, sigla in LOJAS:
                cabecalho.append(f"{sigla} {dd_mm}")

        # Preços por data
        precos_por_data = {data: _buscar_precos_na_data(data) for data in datas}

        linhas = [cabecalho]
        for p in produtos:
            linha = [str(p["sku"]), p["descricao"]]
            for data in datas:
                precos_data = precos_por_data[data]
                for loja_key, _ in LOJAS:
                    preco = precos_data.get(p["id"], {}).get(loja_key)
                    linha.append(_formatar_preco(preco))
            linhas.append(linha)

        ws.update(range_name="A1", values=linhas)
        print(f"Planilha criada com {len(produtos)} produtos e {len(datas)} semanas.")
        return

    # -----------------------------------------------------------------------
    # Execuções seguintes: adiciona 3 colunas novas à direita
    # -----------------------------------------------------------------------
    print("Adicionando colunas da semana...")
    produtos = _buscar_produtos_e_precos()

    # Descobre a próxima coluna livre pela quantidade de colunas no cabeçalho
    proxima_col = len([c for c in dados_existentes[0] if c])  # ignora colunas vazias

    # Mapa SKU → índice de linha no Sheets (1-based, linha 1 = cabeçalho)
    sku_para_linha = {}
    for i, linha in enumerate(dados_existentes[1:], start=2):  # start=2 = linha 2 no Sheets
        if linha and linha[0]:
            sku_para_linha[str(linha[0]).split(".")[0]] = i  # remove ".0" do pandas

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
            continue  # produto novo — não estava na planilha
        for j, (loja_key, _) in enumerate(LOJAS):
            celula = gspread.utils.rowcol_to_a1(idx_linha, proxima_col + 1 + j)
            atualizacoes.append({
                "range": celula,
                "values": [[_formatar_preco(p["precos"][loja_key])]],
            })

    if atualizacoes:
        ws.batch_update(atualizacoes)

    print(f"Concluído: {len(produtos)} produtos exportados para a semana {hoje}.")


if __name__ == "__main__":
    exportar()
