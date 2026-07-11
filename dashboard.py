import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from db import upsert_produto

SCRIPT_MAIN = Path(__file__).parent / "main.py"

DB_PATH = Path(__file__).parent / "precos.db"

LOJAS = {
    "1001festas": "1001 Festas",
    "maria_chocolate": "Maria Chocolate",
    "sto_antonio": "Sto. Antônio",
}

CORES = {
    "1001festas": "#e63946",
    "maria_chocolate": "#f4a261",
    "sto_antonio": "#457b9d",
}


@st.cache_data
def carregar_produtos():
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT id, sku, descricao FROM produtos ORDER BY descricao", con)
    con.close()
    return df


def carregar_historico(produto_id: int) -> pd.DataFrame:
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT loja, preco, capturado_em
        FROM historico_precos
        WHERE produto_id = ? AND preco IS NOT NULL AND erro IS NULL
        ORDER BY capturado_em
        """,
        con,
        params=(produto_id,),
    )
    con.close()
    df["capturado_em"] = pd.to_datetime(df["capturado_em"])
    return df


def buscar_produto_por_sku(sku: int) -> dict | None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM produtos WHERE sku = ?", (sku,)).fetchone()
    con.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Config e navegação
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Monitor de Preços", layout="wide")


def _verificar_login():
    if st.session_state.get("autenticado"):
        return
    st.title("Monitor de Preços")
    with st.form("login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary")
    if entrar:
        creds = st.secrets["auth"]
        if usuario == creds["usuario"] and senha == creds["senha"]:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")
    st.stop()


_verificar_login()

if st.sidebar.button("Sair"):
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.divider()

processo_todos: subprocess.Popen | None = st.session_state.get("bot_processo_todos")
bot_todos_rodando = processo_todos is not None and processo_todos.poll() is None

if bot_todos_rodando:
    st.sidebar.info("⏳ Atualizando todos os preços…")
    if st.sidebar.button("↻ Verificar status"):
        st.rerun()
else:
    if processo_todos is not None:
        if processo_todos.returncode == 0:
            st.sidebar.success("✅ Todos os preços atualizados!")
        else:
            st.sidebar.warning(f"⚠️ Erro ao atualizar (código {processo_todos.returncode}).")
    if st.sidebar.button("🔄 Atualizar todos os preços"):
        p = subprocess.Popen([sys.executable, str(SCRIPT_MAIN)])
        st.session_state["bot_processo_todos"] = p
        st.rerun()

st.sidebar.divider()

pagina = st.sidebar.radio("", ["Consulta de Preços", "Cadastrar Produto", "Histórico de Atualizações"])

# ---------------------------------------------------------------------------
# Página: Consulta de Preços
# ---------------------------------------------------------------------------

if pagina == "Consulta de Preços":
    st.title("Monitor de Preços")

    produtos = carregar_produtos()
    produtos["label"] = produtos["sku"].astype(str) + " — " + produtos["descricao"]

    busca = st.text_input("Buscar por SKU ou descrição", placeholder="ex: 21463 ou CHOCOLATE GAROTO")

    if busca:
        mask = (
            produtos["sku"].astype(str).str.contains(busca, case=False)
            | produtos["descricao"].str.contains(busca, case=False, na=False)
        )
        opcoes = produtos[mask]
    else:
        opcoes = produtos

    if opcoes.empty:
        st.warning("Nenhum produto encontrado.")
        st.stop()

    label_selecionado = st.selectbox("Produto", opcoes["label"].tolist(), index=0)

    produto_id  = int(opcoes.loc[opcoes["label"] == label_selecionado, "id"].iloc[0])
    produto_sku = int(opcoes.loc[opcoes["label"] == label_selecionado, "sku"].iloc[0])

    historico = carregar_historico(produto_id)

    if historico.empty:
        st.info("Sem histórico de preços disponível para este produto.")
        st.stop()

    fig = go.Figure()

    for loja_key, loja_nome in LOJAS.items():
        dados = historico[historico["loja"] == loja_key]
        if dados.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=dados["capturado_em"],
                y=dados["preco"],
                mode="lines+markers",
                name=loja_nome,
                line=dict(color=CORES[loja_key], width=2),
                marker=dict(size=6),
                hovertemplate="%{x|%d/%m/%Y %H:%M}<br>R$ %{y:.2f}<extra>" + loja_nome + "</extra>",
            )
        )

    fig.update_layout(
        xaxis_title="Data",
        yaxis_title="Preço (R$)",
        yaxis_tickprefix="R$ ",
        yaxis_tickformat=",.2f",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        height=480,
        margin=dict(l=0, r=0, t=40, b=0),
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Último preço registrado")

    ultimos = (
        historico.sort_values("capturado_em")
        .groupby("loja")
        .last()
        .reset_index()
    )
    ultimos["loja"] = ultimos["loja"].map(LOJAS)
    ultimos["preco"] = ultimos["preco"].apply(
        lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    ultimos["capturado_em"] = ultimos["capturado_em"].dt.strftime("%d/%m/%Y %H:%M")
    ultimos = ultimos.rename(columns={"loja": "Loja", "preco": "Preço", "capturado_em": "Coletado em"})

    st.dataframe(ultimos[["Loja", "Preço", "Coletado em"]], hide_index=True, use_container_width=True)

    # ---------------------------------------------------------------------------
    # Botão: Rodar bot de atualização
    # ---------------------------------------------------------------------------
    st.divider()

    processo: subprocess.Popen | None = st.session_state.get("bot_processo")
    bot_rodando = processo is not None and processo.poll() is None

    if bot_rodando:
        st.info("⏳ Atualizando preços… aguarde alguns minutos.")
        if st.button("↻ Verificar status"):
            st.rerun()
    else:
        if processo is not None:
            if processo.returncode == 0:
                st.success("✅ Preços atualizados com sucesso!")
            else:
                st.warning(f"⚠️ Bot finalizou com erro (código {processo.returncode}).")

        if st.button("🔄 Atualizar preço deste produto"):
            p = subprocess.Popen([sys.executable, str(SCRIPT_MAIN), "--sku", str(produto_sku)])
            st.session_state["bot_processo"] = p
            st.rerun()


# ---------------------------------------------------------------------------
# Página: Cadastrar Produto
# ---------------------------------------------------------------------------

elif pagina == "Cadastrar Produto":
    st.title("Cadastrar / Editar Produto")

    # Busca para pré-carregar produto existente
    sku_busca = st.number_input("SKU para editar (deixe 0 para novo produto)", min_value=0, step=1, value=0)

    existente = None
    if sku_busca:
        existente = buscar_produto_por_sku(int(sku_busca))
        if existente:
            st.success(f"Produto encontrado: {existente['descricao']}")
        else:
            st.warning("SKU não encontrado. Preencha o formulário para cadastrar.")

    def val(campo: str, padrao="") -> str:
        if existente and existente.get(campo):
            return str(existente[campo])
        return padrao

    st.divider()

    with st.form("form_produto"):
        st.subheader("Dados do produto")

        col1, col2 = st.columns(2)
        with col1:
            sku = st.number_input("SKU *", min_value=1, step=1, value=int(val("sku", 1)))
            descricao = st.text_input("Descrição *", value=val("descricao"))
        with col2:
            ean = st.text_input("EAN", value=val("ean"))
            fornecedor = st.text_input("Fornecedor", value=val("fornecedor"))

        st.subheader("Links dos concorrentes")

        url_1001  = st.text_input("URL 1001 Festas",     value=val("url_1001"))
        url_maria = st.text_input("URL Maria Chocolate", value=val("url_maria"))
        url_santo = st.text_input("URL Sto. Antônio",    value=val("url_santo"))

        with st.expander("Campos avançados"):
            codigo_regex = st.number_input(
                "Código interno 1001 Festas (codigo_regex)",
                min_value=0, step=1,
                value=int(val("codigo_regex", 0)),
                help="Código numérico interno da plataforma Regex Solutions. Deixe 0 se não souber.",
            )

        salvar = st.form_submit_button("Salvar produto", type="primary")

    if salvar:
        if not descricao.strip():
            st.error("Descrição é obrigatória.")
        else:
            try:
                upsert_produto({
                    "sku":          int(sku),
                    "ean":          ean.strip() or None,
                    "codigo_regex": int(codigo_regex) if codigo_regex else None,
                    "descricao":    descricao.strip(),
                    "fornecedor":   fornecedor.strip() or None,
                    "url_1001":     url_1001.strip() or None,
                    "url_maria":    url_maria.strip() or None,
                    "url_nova":     None,
                    "url_santo":    url_santo.strip() or None,
                })
                acao = "atualizado" if existente else "cadastrado"
                st.success(f"Produto {acao} com sucesso!")
                carregar_produtos.clear()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    # Tabela de produtos cadastrados
    st.divider()
    st.subheader("Produtos cadastrados")

    con = sqlite3.connect(DB_PATH)
    df_todos = pd.read_sql(
        "SELECT sku, ean, descricao, fornecedor, url_1001, url_maria, url_santo FROM produtos ORDER BY descricao",
        con,
    )
    con.close()

    busca_tabela = st.text_input("Filtrar tabela", placeholder="SKU ou descrição")
    if busca_tabela:
        mask = (
            df_todos["sku"].astype(str).str.contains(busca_tabela, case=False)
            | df_todos["descricao"].str.contains(busca_tabela, case=False, na=False)
        )
        df_todos = df_todos[mask]

    df_todos = df_todos.rename(columns={
        "sku": "SKU", "ean": "EAN", "descricao": "Descrição",
        "fornecedor": "Fornecedor", "url_1001": "1001 Festas",
        "url_maria": "Maria Chocolate", "url_santo": "Sto. Antônio",
    })
    st.dataframe(df_todos, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# Página: Histórico de Atualizações
# ---------------------------------------------------------------------------

else:
    st.title("Histórico de Atualizações")
    st.caption("Registro de melhorias e correções do Monitor de Preços · 1001 Festas")

    st.divider()

    st.subheader("11 de julho de 2026")

    with st.container(border=True):
        st.markdown("🎯 **Nova funcionalidade · Sto. Antônio — preço do Clube da Meire**")
        st.markdown(
            "O sistema passou a capturar o preço do **Clube da Meire** na Loja Santo Antônio, "
            "quando disponível. Antes, só era registrado o preço normal (à vista). Agora o painel "
            "mostra o preço com o desconto do clube para quem tem o cartão Meire."
        )
        st.warning(
            "⚠️ **Atenção:** os registros anteriores a esta data refletem o preço normal (sem desconto "
            "do clube). A partir de hoje, o preço coletado da Sto. Antônio pode ser menor do que os "
            "registros anteriores — isso é esperado e correto.",
            icon=None,
        )

    with st.container(border=True):
        st.markdown("🔍 **Correção · Sto. Antônio — produtos com nomes internos diferentes**")
        st.markdown(
            "Alguns produtos usam nomes internos diferentes do nome exibido no site "
            "(ex.: \"gold\" em vez de \"Nobre\"). O sistema agora faz uma busca extra pela descrição "
            "do produto quando não o encontra pelo link da URL, resolvendo casos como o SKU 402453 "
            "(Chocolate Branco Nobre Sicao 2,05kg)."
        )

    with st.container(border=True):
        st.markdown("📦 **Correção · Sto. Antônio — produtos sem estoque agora são encontrados**")
        st.markdown(
            "A API da Sto. Antônio ocultava produtos temporariamente sem estoque nas buscas. "
            "O sistema agora força a exibição de todos os produtos (disponíveis ou não), "
            "evitando registros em branco para itens que existem mas estão indisponíveis."
        )

    st.divider()

    st.subheader("10 de julho de 2026")

    with st.container(border=True):
        st.markdown("🖱️ **Nova funcionalidade · Painel — botão de atualização por produto**")
        st.markdown(
            "Adicionado botão \"Atualizar preço deste produto\" na página de consulta. "
            "Agora é possível atualizar o preço de um único produto sem precisar rodar "
            "a coleta completa de todos os ~180 itens."
        )

    with st.container(border=True):
        st.markdown("🔗 **Correção · 1001 Festas — atualização das URLs dos produtos**")
        st.markdown(
            "As URLs da 1001 Festas mudaram de formato. Os links foram atualizados no banco "
            "para o novo padrão, e o sistema agora corrige automaticamente os links antigos "
            "antes de cada consulta."
        )

    with st.container(border=True):
        st.markdown("🚀 **Lançamento · Monitor de Preços entra em operação**")
        st.markdown(
            "Sistema de monitoramento de preços colocado em operação. Coleta automática "
            "diária para três concorrentes: 1001 Festas, Maria Chocolate e Loja Santo Antônio. "
            "Painel web com gráfico histórico e tabela de últimos preços por produto."
        )
