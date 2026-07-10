"""
Verifica todos os produtos da 1001 Festas pesquisando pelo DOM renderizado.

O site usa Angular SPA + API criptografada. O DOM renderizado contém:
  {SKU}
  {Nome do produto}
  R${Preco} {unidade}
  Adicionar

Buscamos por termos-chave (marcas) e extraímos SKU + preço do DOM.
"""
import csv
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

DB = Path(__file__).parent / "precos.db"
SAIDA = Path(__file__).parent / f"validacao_1001festas_dom_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

RE_PRODUTO_BLOCO = re.compile(
    r'(\d{5,7})\n(.+?)\n(?:De R\$[\d,\. ]+por\n)?R\$\s*([\d,.]+)\s*\w*\n(?:Preço por quilo[^\n]*\n)?Adicionar',
    re.MULTILINE | re.DOTALL
)
RE_PRECO = re.compile(r'([\d]+[.,][\d]+)')


def extrair_produtos_do_texto(texto: str) -> dict[str, dict]:
    """Extrai {sku: {nome, preco}} do texto renderizado do DOM."""
    resultado = {}
    for m in RE_PRODUTO_BLOCO.finditer(texto):
        sku = m.group(1).strip()
        nome = m.group(2).strip()
        preco_str = m.group(3).strip().replace('.', '').replace(',', '.')
        try:
            preco = float(preco_str)
        except ValueError:
            preco = None
        resultado[sku] = {'nome': nome, 'preco': preco}
    return resultado


def buscar_paginas(page, url_busca: str) -> str:
    """Navega para uma URL de busca e carrega todas as páginas (Carregar mais)."""
    page.goto(url_busca, wait_until='load', timeout=30000)
    page.wait_for_timeout(3000)

    # Clicar em "Carregar mais" até não haver mais
    tentativas = 0
    while tentativas < 10:
        btn = page.query_selector('button:has-text("Carregar mais")')
        if not btn:
            break
        btn.click()
        page.wait_for_timeout(2000)
        tentativas += 1

    return page.evaluate('() => document.body.innerText')


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    produtos_db = conn.execute(
        "SELECT sku, ean, descricao, url_1001 FROM produtos ORDER BY sku"
    ).fetchall()
    conn.close()

    # Mapear sku -> produto
    db_por_sku = {str(p["sku"]): p for p in produtos_db}
    total = len(db_por_sku)
    print(f"Produtos no banco: {total}")

    # Termos de busca para cobrir todos os produtos
    termos = ['melken', 'sicao', 'garoto', 'genuine', 'norcau', 'maval',
              'nestle', 'unique', 'inovare', 'mycryo', 'calleb']

    encontrados = {}  # sku -> {nome, preco}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
        page_pw = ctx.new_page()

        # Primeiro acesso para inicializar o Angular
        page_pw.goto('https://1001festas.com.br/', wait_until='load', timeout=30000)
        page_pw.wait_for_timeout(2000)

        for i, termo in enumerate(termos, 1):
            print(f"\n[{i}/{len(termos)}] Buscando: {termo}...")
            url_busca = f'https://1001festas.com.br/p/busca/{termo}'
            try:
                texto = buscar_paginas(page_pw, url_busca)
                novos = extrair_produtos_do_texto(texto)
                print(f"  Encontrados {len(novos)} produtos no DOM")
                for sku, dados in novos.items():
                    if sku in db_por_sku and sku not in encontrados:
                        encontrados[sku] = dados
                        print(f"    OK {sku}: {dados['nome'][:50]} -> R${dados['preco']}")
            except Exception as e:
                print(f"  Erro: {e}")
            time.sleep(1)

        browser.close()

    # Gerar relatório
    print(f"\n{'='*60}")
    print(f"Encontrados no site: {len(encontrados)} de {total}")
    nao_encontrados = [s for s in db_por_sku if s not in encontrados]
    print(f"Nao encontrados: {len(nao_encontrados)}")

    with open(SAIDA, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['SKU', 'EAN', 'Descricao_DB', 'Nome_Site', 'Status', 'Preco', 'URL_Antiga'])

        for sku, p_db in sorted(db_por_sku.items()):
            if sku in encontrados:
                dados = encontrados[sku]
                preco_fmt = f"{dados['preco']:.2f}".replace('.', ',') if dados['preco'] else ''
                status = 'ok' if dados['preco'] else 'sem_preco'
                w.writerow([sku, p_db['ean'], p_db['descricao'], dados['nome'], status, preco_fmt, p_db['url_1001'] or ''])
                print(f"  OK  {sku}: {p_db['descricao'][:50]} -> R${preco_fmt}")
            else:
                w.writerow([sku, p_db['ean'], p_db['descricao'], '', 'nao_encontrado', '', p_db['url_1001'] or ''])
                print(f"  XX  {sku}: {p_db['descricao'][:50]}")

    print(f"\nCSV salvo em: {SAIDA.name}")


if __name__ == "__main__":
    main()
