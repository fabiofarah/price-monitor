"""
Busca produtos que ainda não têm link cadastrado em algum concorrente.

Sto. Antônio (VTEX): match por EAN — confiança alta, salva automaticamente.
Maria Chocolate:     match por nome — gera CSV para validação manual.
Nova Safra:          requer login; não suportado automaticamente neste módulo.

Como usar:
    python discovery.py
"""
import csv
import time
from pathlib import Path

from db import init_db, get_todos_produtos, update_url_produto
from scrapers import maria_chocolate, sto_antonio

CSV_VALIDACAO = Path(__file__).parent / "validacao_maria_chocolate.csv"


# ---------------------------------------------------------------------------
# Sto. Antônio — match automático por EAN
# ---------------------------------------------------------------------------

def discovery_sto_antonio(verbose: bool = True) -> int:
    """
    Para cada produto sem URL do Sto. Antônio, busca pelo EAN via VTEX API.
    Match exato por EAN → salva automaticamente no banco.
    Retorna número de produtos encontrados.
    """
    init_db()
    produtos = get_todos_produtos()
    sem_link = [p for p in produtos if not p["url_santo"]]

    if not sem_link:
        print("[Sto. Antônio] Todos os produtos já têm link.")
        return 0

    encontrados = 0
    for p in sem_link:
        ean = p["ean"]
        if not ean:
            if verbose:
                print(f"  [sem EAN] SKU {p['sku']} — {p['descricao']}")
            continue

        resultados = sto_antonio.buscar_por_ean(ean)
        if resultados:
            url = resultados[0]["url"]
            nome = resultados[0]["nome"]
            update_url_produto(p["sku"], "santo", url)
            encontrados += 1
            if verbose:
                print(f"  [OK EAN] SKU {p['sku']} -> {nome}  |  {url}")
        else:
            if verbose:
                print(f"  [não encontrado] SKU {p['sku']} — {p['descricao']}")

        time.sleep(0.5)

    print(f"\n[Sto. Antônio] {encontrados}/{len(sem_link)} produtos novos encontrados.")
    return encontrados


# ---------------------------------------------------------------------------
# Maria Chocolate — gera CSV para validação manual
# ---------------------------------------------------------------------------

def discovery_maria_chocolate(verbose: bool = True) -> int:
    """
    Para cada produto sem URL da Maria Chocolate, faz busca por nome.
    Gera um CSV com até 3 sugestões por produto para validação manual.

    Após preencher a coluna 'url_confirmada' no CSV, rode:
        python discovery.py --importar-maria
    """
    init_db()
    produtos = get_todos_produtos()
    sem_link = [p for p in produtos if not p["url_maria"]]

    if not sem_link:
        print("[Maria Chocolate] Todos os produtos já têm link.")
        return 0

    linhas = []
    for p in sem_link:
        descricao = p["descricao"] or ""
        fornecedor = p["fornecedor"] or ""
        query = f"{descricao} {fornecedor}".strip()

        sugestoes = maria_chocolate.buscar_produtos(query, max_resultados=3)

        linha = {
            "sku":             p["sku"],
            "ean":             p["ean"],
            "descricao_nossa": descricao,
            "sugestao_1_nome": "",
            "sugestao_1_url":  "",
            "sugestao_2_nome": "",
            "sugestao_2_url":  "",
            "sugestao_3_nome": "",
            "sugestao_3_url":  "",
            "url_confirmada":  "",   # ← preencha esta coluna
        }
        for i, s in enumerate(sugestoes[:3], start=1):
            linha[f"sugestao_{i}_nome"] = s["nome"]
            linha[f"sugestao_{i}_url"]  = s["url"]

        linhas.append(linha)
        if verbose:
            print(f"  SKU {p['sku']} - {descricao} -> {len(sugestoes)} sugestoes")
        time.sleep(1)

    _escrever_csv(linhas)
    print(f"\n[Maria Chocolate] CSV gerado: {CSV_VALIDACAO}")
    print("Preencha a coluna 'url_confirmada' e rode: python discovery.py --importar-maria")
    return len(linhas)


def importar_maria_chocolate_csv() -> int:
    """
    Lê o CSV de validação preenchido e salva as URLs confirmadas no banco.
    Retorna número de URLs importadas.
    """
    if not CSV_VALIDACAO.exists():
        print(f"Arquivo não encontrado: {CSV_VALIDACAO}")
        return 0

    importados = 0
    with open(CSV_VALIDACAO, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            url = row.get("url_confirmada", "").strip()
            sku = row.get("sku", "").strip()
            if url and sku:
                try:
                    update_url_produto(int(sku), "maria", url)
                    importados += 1
                    print(f"  [importado] SKU {sku} -> {url}")
                except Exception as e:
                    print(f"  [erro] SKU {sku}: {e}")

    print(f"\n[Maria Chocolate] {importados} URLs importadas.")
    return importados


def _escrever_csv(linhas: list[dict]):
    campos = [
        "sku", "ean", "descricao_nossa",
        "sugestao_1_nome", "sugestao_1_url",
        "sugestao_2_nome", "sugestao_2_url",
        "sugestao_3_nome", "sugestao_3_url",
        "url_confirmada",
    ]
    with open(CSV_VALIDACAO, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(linhas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--importar-maria" in sys.argv:
        importar_maria_chocolate_csv()
    else:
        print("=== Discovery: Sto. Antônio (automático) ===")
        discovery_sto_antonio()
        print()
        print("=== Discovery: Maria Chocolate (gera CSV para validação) ===")
        discovery_maria_chocolate()
