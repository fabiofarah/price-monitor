"""
Abre o navegador para login manual na Nova Safra e salva os cookies de sessão.
Execute este script sempre que a sessão expirar (normalmente alguns dias).

Uso:
    python salvar_sessao_nova_safra.py
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

COOKIES_FILE = Path(__file__).parent / ".nova_safra_session.json"
LOGIN_URL = "https://www.novasafra.com.br/login"
CONTA_URL = "https://www.novasafra.com.br/minha-conta"
CEP = "30110-072"
PRODUTO_TESTE = "https://www.novasafra.com.br/product/116760/acucar-de-confeiteiro-impalpavel-harald-1kg"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(LOGIN_URL)

        print("Navegador aberto. Faça login normalmente (e-mail, senha e CAPTCHA).")
        print("Aguardando você completar o login... (até 3 minutos)")

        # Aguarda sair da página de login automaticamente
        try:
            await page.wait_for_url(
                lambda url: "login" not in url.lower() and "entrar" not in url.lower(),
                timeout=180_000,
            )
            print("Login detectado!")
        except Exception:
            print("Tempo esgotado — tente novamente.")
            await browser.close()
            return

        if "login" in page.url.lower() or "entrar" in page.url.lower():
            print("Não parece que o login foi concluído. Tente novamente.")
            await browser.close()
            return

        # Abre produto de teste para acionar e preencher o popup de localização
        print("Configurando localização (CEP)...")
        await page.goto(PRODUTO_TESTE, timeout=60000)
        await page.wait_for_load_state("domcontentloaded", timeout=60000)

        popup = page.locator("input[placeholder='CEP *'], input[id*='cep'], input[name*='cep']").first
        try:
            await popup.wait_for(timeout=5000)
            # Seleciona Pessoa Física (primeiro radio)
            await page.locator("input[type='radio']").first.check()
            await popup.fill(CEP)
            await page.locator("button:has-text('Confirmar')").first.click()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            print("Localização configurada.")
        except Exception:
            print("Popup de localização não encontrado — pode já estar configurado.")

        cookies = await context.cookies()
        COOKIES_FILE.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Sessão salva em {COOKIES_FILE.name} — pode fechar o navegador.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
