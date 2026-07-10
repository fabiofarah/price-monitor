"""
Verifica todos os produtos da 1001 Festas via nova API (plataforma Regex Solutions v2).

O site migrou de JSON-LD/HTML para Angular SPA com API em:
  POST https://apiecommerce.regexsolutions.com.br/ecommerce/produto/getDetalhes
  Payload: {"produtoId": <int>, "filialId": 371, "modal": true}

O scraper usa Playwright UMA vez para capturar os headers de autenticacao
(JWT + headers customizados), depois faz todas as chamadas via requests.

Execute: python verificar_1001festas_api.py
"""
import csv
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from playwright.sync_api import sync_playwright

DB = Path(__file__).parent / "precos.db"
SAIDA = Path(__file__).parent / f"validacao_1001festas_api_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
LOJA_UUID = "382dd4bc-ba8b-42c4-a58d-6e578e209989"
FILIAL_ID = 371
API_URL = "https://apiecommerce.regexsolutions.com.br/ecommerce/produto/getDetalhes"
RE_PRODUTO_ID = re.compile(r"/p/d/(\d+)/")


def extrair_produto_id(url: str) -> int | None:
    m = RE_PRODUTO_ID.search(url or "")
    return int(m.group(1)) if m else None


def obter_headers_auth() -> dict:
    """Usa Playwright para capturar os headers de autenticação da 1001 Festas."""
    print("Obtendo headers de autenticacao via Playwright...")
    captured = {}

    def on_req(req):
        if "apiecommerce" in req.url and not captured:
            for k, v in req.headers.items():
                captured[k] = v

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.on("request", on_req)
        try:
            page.goto("https://1001festas.com.br/", wait_until="networkidle", timeout=30000)
        except Exception:
            pass
        # Aguardar um pouco para garantir que as chamadas de API foram feitas
        page.wait_for_timeout(2000)
        browser.close()

    if not captured:
        raise RuntimeError("Nao foi possivel capturar headers da API. Verifique a conexao.")

    print(f"  Headers capturados: {list(captured.keys())}")
    return captured


def checar_produto(session: requests.Session, headers: dict, produto_id: int) -> tuple[str, float | None, str]:
    """Retorna (status, preco, detalhe)."""
    if not produto_id:
        return "sem_url", None, "URL sem produto_id"

    payload = {"produtoId": produto_id, "filialId": FILIAL_ID, "modal": True}
    hdrs = dict(headers)
    hdrs["x-payload"] = quote(json.dumps(payload, separators=(",", ":")))

    try:
        r = session.post(API_URL, headers=hdrs, json=payload, timeout=15)
        if r.status_code != 200:
            return "erro_http", None, f"HTTP {r.status_code}"

        data = r.json()
        if not data:
            return "produto_nao_encontrado", None, "API retornou vazio (produtoId invalido)"

        # Estrutura esperada: {"produto": {...}, "oferta": {...}} ou similar
        # Verificar diferentes estruturas possíveis
        produto = data.get("produto") or data.get("data") or data
        if isinstance(produto, dict):
            # Procurar preço
            oferta = data.get("oferta") or data.get("offers") or {}
            preco = None
            for campo in ["preco", "preco_venda", "valor", "price", "precoVenda", "precoDesconto"]:
                v = oferta.get(campo) or produto.get(campo)
                if v and float(v) > 0:
                    preco = float(v)
                    break

            disponivel = data.get("disponivel", data.get("available", True))
            if not disponivel:
                return "indisponivel", preco, "produto indisponivel"
            if preco:
                return "ok", preco, ""
            return "sem_preco", None, f"campos: {list(data.keys())}"

        return "sem_preco", None, f"estrutura inesperada: {str(data)[:100]}"

    except Exception as e:
        return "erro", None, str(e)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    produtos = conn.execute(
        "SELECT sku, ean, descricao, url_1001 FROM produtos ORDER BY descricao"
    ).fetchall()
    conn.close()

    total = len(produtos)
    print(f"Encontrados {total} produtos no banco.\n")

    headers = obter_headers_auth()
    print()

    session = requests.Session()
    contagem = {}

    with open(SAIDA, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["SKU", "EAN", "Descricao", "URL", "ProdutoID", "Status", "Preco", "Detalhe"])

        for i, p in enumerate(produtos, 1):
            url = p["url_1001"] or ""
            produto_id = extrair_produto_id(url)

            status, preco, detalhe = checar_produto(session, headers, produto_id)
            contagem[status] = contagem.get(status, 0) + 1

            preco_fmt = f"{preco:.2f}".replace(".", ",") if preco else ""
            w.writerow([p["sku"], p["ean"], p["descricao"], url, produto_id or "", status, preco_fmt, detalhe])

            icone = "OK" if status == "ok" else ("--" if status == "indisponivel" else "XX")
            print(f"[{i:3d}/{total}] {icone} {p['descricao'][:50]:50s} {status}  {preco_fmt}")

            time.sleep(0.3)

    print(f"\n{'='*60}")
    print("Resultado final:")
    for s, n in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"  {s:35s}: {n}")
    print(f"\nCSV salvo em: {SAIDA.name}")

    # Listar os que nao retornaram pagina de produto
    nao_ok = [s for s in ["produto_nao_encontrado", "sem_preco", "sem_url", "erro_http", "erro"] if contagem.get(s, 0) > 0]
    if nao_ok:
        print(f"\n[ATENCAO] {sum(contagem.get(s,0) for s in nao_ok)} produtos sem pagina/preco valido.")
        print("Verifique o CSV para a lista completa.")


if __name__ == "__main__":
    main()
