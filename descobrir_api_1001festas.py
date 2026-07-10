"""
Intercepta as chamadas de rede ao carregar uma página de produto da 1001 Festas.
Objetivo: descobrir o endpoint de API que retorna o preço.

Instale primeiro:
    pip install playwright
    playwright install chromium

Execute:
    python descobrir_api_1001festas.py
"""
import json
import asyncio
from playwright.async_api import async_playwright

URL = "https://1001festas.com.br/p/d/2055054/a/p"
CAPTURAR_DOMINIOS = ("regexsolutions", "1001festas", "api")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        chamadas: list[dict] = []

        async def capturar(response):
            url = response.url
            if any(d in url for d in CAPTURAR_DOMINIOS):
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    try:
                        body = await response.text()
                        chamadas.append({
                            "url": url,
                            "status": response.status,
                            "content_type": ct,
                            "body_inicio": body[:300],
                        })
                    except Exception:
                        pass

        page.on("response", capturar)

        print(f"Carregando: {URL}")
        await page.goto(URL, wait_until="networkidle", timeout=30000)

        # Aguarda o preço aparecer no DOM (máx 10s)
        try:
            await page.wait_for_selector(
                "text=/R\\$/", timeout=10000
            )
        except Exception:
            pass

        # Captura o preço do DOM renderizado
        preco_dom = await page.evaluate("""
            () => {
                const sels = [
                    '[class*="price"]', '[class*="preco"]', '[class*="valor"]',
                    '[itemprop="price"]', '.price', '.preco'
                ];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el && el.textContent.includes('R$'))
                        return el.textContent.trim();
                }
                // Busca qualquer R$ na página
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT
                );
                let node;
                while ((node = walker.nextNode())) {
                    if (node.textContent.match(/R\$\s*[\d.,]+/))
                        return node.textContent.trim();
                }
                return null;
            }
        """)

        await browser.close()

        print(f"\n{'='*60}")
        print(f"Preço encontrado no DOM renderizado: {preco_dom or 'NÃO ENCONTRADO'}")
        print(f"\nChamadas de API capturadas ({len(chamadas)}):")
        for c in chamadas:
            print(f"\n  URL    : {c['url']}")
            print(f"  Status : {c['status']}")
            print(f"  Type   : {c['content_type']}")
            print(f"  Body   : {c['body_inicio'][:200]}")
            # Se for JSON com preço, destaca
            try:
                data = json.loads(c["body_inicio"][:300] + "}")
                if any(k in str(data).lower() for k in ("price", "preco", "valor")):
                    print("  *** POSSÍVEL ENDPOINT DE PREÇO ***")
            except Exception:
                pass
        print(f"{'='*60}")
        print("\nCole a saída acima no chat para eu identificar o endpoint correto.")


asyncio.run(main())
