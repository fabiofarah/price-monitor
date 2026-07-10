"""
Scraper para www.novasafra.com.br (requer login).
Usa Playwright (navegador headless Chromium) para autenticar e extrair preços.

Credenciais lidas de variáveis de ambiente NOVA_SAFRA_EMAIL e NOVA_SAFRA_SENHA.
Cookies da sessão são salvos em .nova_safra_session.json para reuso.

AJUSTE se necessário:
  - LOGIN_URL: URL da página de login
  - SEL_EMAIL / SEL_SENHA / SEL_SUBMIT: seletores CSS dos campos do formulário
"""
import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext
from .base import ScrapeResult, parse_preco

LOGIN_URL    = "https://www.novasafra.com.br/login"
CONTA_URL    = "https://www.novasafra.com.br/minha-conta"
BASE_DOMAIN  = "novasafra.com.br"

# Seletores do formulário de login — ajuste se o site mudar
SEL_EMAIL  = '#credentialToLogin'
SEL_SENHA  = '#inputPassword'
SEL_SUBMIT = 'button[type="submit"]'

COOKIES_FILE = Path(__file__).parent.parent / ".nova_safra_session.json"
CEP_PADRAO = "30110-072"
DELAY_ENTRE_PAGINAS = 2  # segundos entre requisições


async def _carregar_cookies(context: BrowserContext):
    if COOKIES_FILE.exists():
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        await context.add_cookies(cookies)


async def _salvar_cookies(context: BrowserContext):
    cookies = await context.cookies()
    COOKIES_FILE.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def _esta_logado(page: Page) -> bool:
    """Verifica se estamos autenticados navegando para a página de conta."""
    await page.goto(CONTA_URL, timeout=30_000)
    await page.wait_for_load_state("networkidle", timeout=30_000)
    return "login" not in page.url.lower() and "entrar" not in page.url.lower()


async def _fechar_popup_localizacao(page: Page):
    """Preenche o popup de CEP caso apareça."""
    try:
        campo_cep = page.locator("input[placeholder='CEP *'], input[id*='cep'], input[name*='cep']").first
        await campo_cep.wait_for(timeout=3000)
        await page.locator("input[type='radio']").first.check()
        await campo_cep.fill(CEP_PADRAO)
        await page.locator("button:has-text('Confirmar')").first.click()
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass  # popup não presente


async def _fazer_login(page: Page, email: str, senha: str):
    await page.goto(LOGIN_URL, timeout=30_000)
    await page.wait_for_load_state("networkidle", timeout=30_000)
    await page.locator(SEL_EMAIL).first.fill(email)
    await page.locator(SEL_SENHA).first.fill(senha)
    await page.locator(SEL_SUBMIT).first.click()
    await page.wait_for_load_state("networkidle", timeout=30_000)

    if "login" in page.url.lower() or "entrar" in page.url.lower():
        raise RuntimeError(
            "Login falhou — verifique NOVA_SAFRA_EMAIL e NOVA_SAFRA_SENHA no .env"
        )


async def _scrape_urls(
    urls_com_id: list[tuple[int, str]],
    email: str,
    senha: str,
) -> list[tuple[int, ScrapeResult]]:
    """Abre uma sessão do navegador, loga e raspa todos os URLs de uma vez."""
    resultados: list[tuple[int, ScrapeResult]] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
        )
        await _carregar_cookies(context)
        page = await context.new_page()

        # Verifica/faz login
        if not await _esta_logado(page):
            await _fazer_login(page, email, senha)
            await _salvar_cookies(context)

        for produto_id, url in urls_com_id:
            url = url.strip()
            try:
                await page.goto(url, timeout=30_000)
                await page.wait_for_load_state("networkidle", timeout=30_000)

                # Se caiu na tela de login novamente, tenta reautenticar
                if "login" in page.url.lower():
                    await _fazer_login(page, email, senha)
                    await _salvar_cookies(context)
                    await page.goto(url, timeout=30_000)
                    await page.wait_for_load_state("networkidle", timeout=30_000)

                await _fechar_popup_localizacao(page)
                texto = await page.inner_text("body")
                preco = parse_preco(texto)

                if preco is None:
                    indisponivel = any(
                        kw in texto.lower()
                        for kw in ("indisponível", "fora de estoque", "esgotado")
                    )
                    resultado = ScrapeResult(
                        preco=None, disponivel=False, url=url,
                        erro="preço não encontrado" + (" (indisponível)" if indisponivel else ""),
                    )
                else:
                    resultado = ScrapeResult(preco=preco, disponivel=True, url=url)

            except Exception as e:
                resultado = ScrapeResult(preco=None, disponivel=False, url=url, erro=str(e))

            resultados.append((produto_id, resultado))
            await asyncio.sleep(DELAY_ENTRE_PAGINAS)

        await browser.close()

    return resultados


def scrape_todos(
    urls_com_id: list[tuple[int, str]],
    email: str,
    senha: str,
) -> list[tuple[int, ScrapeResult]]:
    """
    Interface síncrona. Recebe lista de (produto_id, url).
    Retorna lista de (produto_id, ScrapeResult) na mesma ordem.
    """
    return asyncio.run(_scrape_urls(urls_com_id, email, senha))
