"""
Módulo de banco de dados SQLite.
Gerencia schema, inserções e consultas do histórico de preços.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "precos.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sku           INTEGER UNIQUE NOT NULL,
    ean           TEXT,
    codigo_regex  INTEGER,
    descricao     TEXT,
    fornecedor    TEXT,
    url_1001      TEXT,
    url_maria     TEXT,
    url_nova      TEXT,
    url_santo     TEXT
);

CREATE TABLE IF NOT EXISTS historico_precos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id     INTEGER NOT NULL REFERENCES produtos(id),
    loja           TEXT NOT NULL,
    url            TEXT,
    preco          REAL,
    preco_anterior REAL,
    disponivel     INTEGER NOT NULL DEFAULT 1,
    erro           TEXT,
    capturado_em   DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hist_produto_loja
    ON historico_precos(produto_id, loja);
CREATE INDEX IF NOT EXISTS idx_hist_data
    ON historico_precos(capturado_em);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_produto(p: dict) -> int:
    """Insere ou atualiza um produto. Retorna o id interno."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO produtos
                (sku, ean, codigo_regex, descricao, fornecedor,
                 url_1001, url_maria, url_nova, url_santo)
            VALUES
                (:sku, :ean, :codigo_regex, :descricao, :fornecedor,
                 :url_1001, :url_maria, :url_nova, :url_santo)
            ON CONFLICT(sku) DO UPDATE SET
                ean          = excluded.ean,
                codigo_regex = excluded.codigo_regex,
                descricao    = excluded.descricao,
                fornecedor   = excluded.fornecedor,
                url_1001     = excluded.url_1001,
                url_maria    = excluded.url_maria,
                url_nova     = excluded.url_nova,
                url_santo    = excluded.url_santo
        """, p)
        row = conn.execute(
            "SELECT id FROM produtos WHERE sku = ?", (p["sku"],)
        ).fetchone()
        return row["id"]


def update_url_produto(sku: int, loja: str, url: str):
    """Atualiza a URL de um concorrente para um produto após discovery."""
    col = {"maria": "url_maria", "nova": "url_nova", "santo": "url_santo"}[loja]
    with get_conn() as conn:
        conn.execute(f"UPDATE produtos SET {col} = ? WHERE sku = ?", (url, sku))


def get_ultimo_preco(produto_id: int, loja: str) -> float | None:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT preco FROM historico_precos
            WHERE produto_id = ? AND loja = ? AND preco IS NOT NULL
            ORDER BY capturado_em DESC LIMIT 1
        """, (produto_id, loja)).fetchone()
        return float(row["preco"]) if row else None


def registrar_preco(
    produto_id: int,
    loja: str,
    url: str | None,
    preco: float | None,
    disponivel: bool = True,
    erro: str | None = None,
):
    preco_anterior = get_ultimo_preco(produto_id, loja)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO historico_precos
                (produto_id, loja, url, preco, preco_anterior,
                 disponivel, erro, capturado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            produto_id, loja, url, preco, preco_anterior,
            int(disponivel), erro, datetime.now().isoformat(timespec="seconds"),
        ))


def get_todos_produtos() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM produtos ORDER BY descricao").fetchall()


def get_ultimos_precos() -> list[sqlite3.Row]:
    """Retorna o último preço registrado de cada produto × loja."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT
                p.id, p.sku, p.ean, p.descricao, p.fornecedor,
                h.loja, h.url, h.preco, h.preco_anterior,
                h.disponivel, h.erro, h.capturado_em
            FROM produtos p
            JOIN historico_precos h ON h.produto_id = p.id
            WHERE h.id = (
                SELECT id FROM historico_precos h2
                WHERE h2.produto_id = p.id AND h2.loja = h.loja
                ORDER BY capturado_em DESC LIMIT 1
            )
            ORDER BY p.descricao, h.loja
        """).fetchall()
