"""
Orquestrador principal do monitor de preços.

Uso:
    python main.py                        # raspa todos os concorrentes
    python main.py --lojas 1001 maria sto # raspa lojas específicas

O banco é inicializado automaticamente na primeira execução.
Os produtos são importados do Excel se o banco estiver vazio.
"""
import sys
import time
from datetime import datetime

from db import init_db, get_todos_produtos, registrar_preco
from loader import carregar_produtos
from scrapers import festas_1001, maria_chocolate, sto_antonio


def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def _precisa_importar() -> bool:
    from db import get_todos_produtos
    return len(get_todos_produtos()) == 0


def run(lojas: set[str] | None = None, sku: int | None = None):
    init_db()
    if _precisa_importar():
        _log("Banco vazio — importando produtos do Excel...")
        carregar_produtos()

    produtos = get_todos_produtos()

    if sku is not None:
        produtos = [p for p in produtos if p["sku"] == sku]
        if not produtos:
            _log(f"SKU {sku} não encontrado no banco.")
            return
        _log(f"Atualizando apenas SKU {sku}: {produtos[0]['descricao']}.")
    else:
        _log(f"{len(produtos)} produtos carregados.")

    # ----------------------------------------------------------------
    # 1001 Festas
    # ----------------------------------------------------------------
    if lojas is None or "1001" in lojas:
        _log("=== 1001 Festas ===")
        ok = erro = 0
        for p in produtos:
            url = p["url_1001"]
            if not url:
                continue
            url = festas_1001.corrigir_url(url, p["descricao"])
            result = festas_1001.get_preco(url)
            registrar_preco(p["id"], "1001festas", url, result.preco, result.disponivel, result.erro)
            if result.erro:
                _log(f"  [erro] SKU {p['sku']} — {result.erro}")
                erro += 1
            else:
                ok += 1
            time.sleep(1)
        _log(f"  Concluído: {ok} ok, {erro} com erro.")

    # ----------------------------------------------------------------
    # Maria Chocolate
    # ----------------------------------------------------------------
    if lojas is None or "maria" in lojas:
        _log("=== Maria Chocolate ===")
        ok = erro = sem_link = 0
        for p in produtos:
            url = p["url_maria"]
            if not url:
                sem_link += 1
                continue
            result = maria_chocolate.get_preco(url)
            registrar_preco(p["id"], "maria_chocolate", url, result.preco, result.disponivel, result.erro)
            if result.erro:
                _log(f"  [erro] SKU {p['sku']} — {result.erro}")
                erro += 1
            else:
                ok += 1
            time.sleep(1)
        _log(f"  Concluído: {ok} ok, {erro} com erro, {sem_link} sem link.")

    # ----------------------------------------------------------------
    # Sto. Antônio (VTEX API — sem delay agressivo)
    # ----------------------------------------------------------------
    if lojas is None or "sto" in lojas:
        _log("=== Sto. Antônio (VTEX API) ===")
        ok = erro = sem_link = 0
        for p in produtos:
            url = p["url_santo"]
            if not url:
                sem_link += 1
                continue
            result = sto_antonio.get_preco(url, ean=p["ean"])
            registrar_preco(p["id"], "sto_antonio", url, result.preco, result.disponivel, result.erro)
            if result.erro:
                _log(f"  [erro] SKU {p['sku']} — {result.erro}")
                erro += 1
            else:
                ok += 1
            time.sleep(0.5)
        _log(f"  Concluído: {ok} ok, {erro} com erro, {sem_link} sem link.")

    _log("=== Coleta finalizada ===")


if __name__ == "__main__":
    lojas_selecionadas = None
    sku_selecionado = None

    if "--lojas" in sys.argv:
        idx = sys.argv.index("--lojas")
        lojas_selecionadas = set(sys.argv[idx + 1:])

    if "--sku" in sys.argv:
        idx = sys.argv.index("--sku")
        try:
            sku_selecionado = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            _log("Argumento --sku inválido.")
            sys.exit(1)

    run(lojas_selecionadas, sku=sku_selecionado)
