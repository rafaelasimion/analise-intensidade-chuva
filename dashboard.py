import streamlit as st
import pandas as pd
import requests
import os
import plotly.express as px
from datetime import timedelta, datetime

st.set_page_config(
    page_title="Análise de Intensidade de Chuva",
    page_icon="🌧️",
    layout="wide"
)

st.title("🌧️ Análise de Intensidade de Chuva ESALQ")

# garantir pasta
os.makedirs("dados", exist_ok=True)

# -------------------------------
# BOTÃO ATUALIZAR
# -------------------------------

if st.button("🔄 Atualizar dados da estação"):

    ano_atual = datetime.now().year
    csv_file = f"dados/dados_{ano_atual}.csv"

    if os.path.exists(csv_file):
        os.remove(csv_file)

    st.cache_data.clear()

    st.success("Dados da estação atualizados!")

st.divider()

# -------------------------------
# FUNÇÃO PARA CARREGAR DADOS
# -------------------------------

@st.cache_data(ttl=86400)
def carregar_ano(ano):

    csv_file = f"dados/dados_{ano}.csv"
    ano_atual = datetime.now().year

    if ano != ano_atual and os.path.exists(csv_file):
        df = pd.read_csv(csv_file, parse_dates=["TIMESTAMP"])
        return df

    url = f"http://www.leb.esalq.usp.br/leb/automatica/diario{ano}.xls"

    r = requests.get(url)

    if r.status_code != 200:
        raise Exception(f"Erro ao baixar dados do ano {ano}")

    xls_file = f"dados/temp_{ano}.xls"

    with open(xls_file, "wb") as f:
        f.write(r.content)

    preview = pd.read_excel(xls_file, header=None)

    header_row = None

    for i in range(10):
        linha = preview.iloc[i].astype(str).str.contains("TIMESTAMP").any()
        if linha:
            header_row = i
            break

    if header_row is None:
        os.remove(xls_file)
        raise Exception("Cabeçalho não encontrado")

    df = pd.read_excel(xls_file, header=header_row)

    df.columns = df.columns.str.strip()

    col_chuva = next((c for c in df.columns if "Chuva" in c), None)

    if col_chuva is None:
        os.remove(xls_file)
        raise Exception("Coluna de chuva não encontrada")

    df = df[["TIMESTAMP", col_chuva]]

    df = df.rename(columns={col_chuva: "Chuva_mm"})

    df = df[df["TIMESTAMP"] != "TS"]

    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")

    df = df.dropna(subset=["TIMESTAMP"])

    df["Chuva_mm"] = pd.to_numeric(df["Chuva_mm"], errors="coerce")

    # -------------------------------
    # LIMPEZA DO SENSOR
    # -------------------------------

    df.loc[df["Chuva_mm"].isin([6999, 7999, 9999]), "Chuva_mm"] = None

    df.loc[df["Chuva_mm"] > 150, "Chuva_mm"] = None

    df["prev"] = df["Chuva_mm"].shift(1)
    df["next"] = df["Chuva_mm"].shift(-1)

    erro = (
        (df["Chuva_mm"] > 100) &
        (df["prev"] < 1) &
        (df["next"] < 1)
    )

    df.loc[erro, "Chuva_mm"] = None

    df = df.drop(columns=["prev", "next"])

    # -------------------------------
    # INTERVALO
    # -------------------------------

    df["intervalo_horas"] = df["TIMESTAMP"].diff().dt.total_seconds() / 3600

    df.loc[df["intervalo_horas"] <= 0, "intervalo_horas"] = None
    df.loc[df["intervalo_horas"] > 0.5, "intervalo_horas"] = None

    # intensidade
    df["intensidade"] = df["Chuva_mm"] / df["intervalo_horas"]

    df.loc[df["intervalo_horas"] == 0, "intensidade"] = None
    df.loc[df["intensidade"] > 500, "intensidade"] = None

    # -------------------------------
    # ACUMULADO
    # -------------------------------

    df["data"] = df["TIMESTAMP"].dt.date

    df["chuva_acumulada"] = (
        df.groupby("data")["Chuva_mm"]
        .cumsum()
    )

    df["Ano"] = ano

    df.to_csv(csv_file, index=False)

    os.remove(xls_file)

    return df


# -------------------------------
# SELEÇÃO DE ANOS
# -------------------------------

st.subheader("📅 Filtrar período")

anos = st.multiselect(
    "Escolha os anos",
    [2026, 2025, 2024, 2023, 2022, 2021, 2020],
    default=[2026]
)

dfs = []

for ano in anos:
    dfs.append(carregar_ano(ano))

if not dfs:
    st.warning("Selecione ao menos um ano.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)

df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
df = df.dropna(subset=["TIMESTAMP"])

# -------------------------------
# FILTRO DE DATA
# -------------------------------

periodo = st.selectbox(
    "Período",
    ["Personalizado", "Últimos 7 dias", "Últimos 30 dias", "Esta semana", "Este mês"]
)

hoje = datetime.now().date()

if periodo == "Últimos 7 dias":

    data_inicio = hoje - timedelta(days=7)
    data_fim = hoje + timedelta(days=1)

elif periodo == "Últimos 30 dias":

    data_inicio = hoje - timedelta(days=30)
    data_fim = hoje + timedelta(days=1)

elif periodo == "Esta semana":

    data_inicio = hoje - timedelta(days=hoje.weekday())
    data_fim = hoje + timedelta(days=1)

elif periodo == "Este mês":

    data_inicio = hoje.replace(day=1)
    data_fim = hoje + timedelta(days=1)

else:

    col1, col2 = st.columns(2)

    with col1:

        data_inicio = st.date_input(
            "Data inicial",
            df["TIMESTAMP"].max().date() - timedelta(days=30)
        )

    with col2:

        data_fim = st.date_input(
            "Data final",
            df["TIMESTAMP"].max().date() + timedelta(days=1)
        )

filtro = df[
    (df["TIMESTAMP"] >= pd.to_datetime(data_inicio)) &
    (df["TIMESTAMP"] < pd.to_datetime(data_fim))
]

# -------------------------------
# ESTATÍSTICAS
# -------------------------------

st.divider()
st.subheader("📊 Estatísticas")

col1, col2, col3 = st.columns(3)

col1.metric(
    "🌧️ Chuva total (mm)",
    round(filtro["Chuva_mm"].sum(), 2)
)

col2.metric(
    "⚡ Intensidade máxima (mm/h)",
    round(filtro["intensidade"].max(), 2)
)

col3.metric(
    "📅 Registros",
    len(filtro)
)

# -------------------------------
# TABELA
# -------------------------------

st.divider()
st.subheader("📋 Dados para exportação")

tabela = filtro.sort_values("TIMESTAMP", ascending=False).copy()

tabela = tabela[tabela["Chuva_mm"].fillna(0) > 0]

tabela = tabela[[
    "TIMESTAMP",
    "Chuva_mm",
    "intensidade",
    "chuva_acumulada"
]]

tabela = tabela.rename(columns={
    "TIMESTAMP": "Data",
    "Chuva_mm": "Chuva (mm)",
    "intensidade": "Intensidade (mm/h)",
    "chuva_acumulada": "Total (mm)"
})

tabela_site = tabela.copy()

tabela_site["Data"] = tabela_site["Data"].dt.strftime("%d/%m/%Y %H:%M")

st.dataframe(tabela_site, use_container_width=True)

# -------------------------------
# DOWNLOAD CSV
# -------------------------------

tabela_excel = tabela.copy()

tabela_excel["Data"] = tabela_excel["Data"].dt.strftime("%d/%m/%Y")

for col in ["Chuva (mm)", "Intensidade (mm/h)", "Total (mm)"]:
    tabela_excel[col] = tabela_excel[col].map(
        lambda x: f"{x:.2f}".replace(".", ",")
    )

csv = tabela_excel.to_csv(index=False, sep=";").encode("utf-8")

st.download_button(
    "📥 Baixar dados",
    csv,
    "dados_chuva.csv",
    "text/csv"
)

# -------------------------------
# RESUMO MENSAL
# -------------------------------

st.divider()
st.subheader("📊 Intensidade média mensal")

mensal = filtro.copy()
mensal = mensal[mensal["Chuva_mm"] > 0]

mensal["AnoMes"] = mensal["TIMESTAMP"].dt.to_period("M")

idx_max = mensal.groupby("AnoMes")["intensidade"].idxmax()

eventos_max = mensal.loc[idx_max]

resumo_mensal = (
    mensal.groupby("AnoMes")
    .agg({
        "Chuva_mm": "sum",
        "intervalo_horas": "sum",
        "intensidade": "max"
    })
    .reset_index()
)

resumo_mensal["Intensidade média (mm/h)"] = (
    resumo_mensal["Chuva_mm"] /
    resumo_mensal["intervalo_horas"]
)

resumo_mensal["Intensidade máx (mm/h)"] = resumo_mensal["intensidade"]

resumo_mensal["Chuva total (mm)"] = resumo_mensal["Chuva_mm"]

eventos_max["Data I máx"] = eventos_max["TIMESTAMP"].dt.strftime("%d/%m/%Y %H:%M")
eventos_max["Chuva evento (mm)"] = eventos_max["Chuva_mm"]

eventos_max = eventos_max[[
    "AnoMes",
    "Data I máx",
    "Chuva evento (mm)"
]]

resumo_mensal = resumo_mensal.merge(
    eventos_max,
    on="AnoMes",
    how="left"
)

resumo_mensal["Mês"] = resumo_mensal["AnoMes"].dt.strftime("%b/%Y")

resumo_mensal = resumo_mensal[[
    "Mês",
    "Intensidade média (mm/h)",
    "Intensidade máx (mm/h)",
    "Data I máx",
    "Chuva evento (mm)",
    "Chuva total (mm)"
]]

for col in [
    "Intensidade média (mm/h)",
    "Intensidade máx (mm/h)",
    "Chuva evento (mm)",
    "Chuva total (mm)"
]:

    resumo_mensal[col] = (
        pd.to_numeric(resumo_mensal[col], errors="coerce")
        .apply(lambda x: f"{x:.2f}".replace(".", ",") if pd.notnull(x) else "")
    )

st.dataframe(resumo_mensal, use_container_width=True, hide_index=True)

csv2 = resumo_mensal.to_csv(index=False, sep=";").encode("utf-8")

st.download_button(
    "📥 Baixar resumo mensal",
    csv2,
    "resumo_mensal_chuva.csv",
    "text/csv"
)

# -------------------------------
# GRÁFICOS
# -------------------------------

st.divider()

intervalo = st.selectbox(
    "Intervalo do gráfico",
    ["15 minutos", "1 hora", "1 dia"]
)

dados = filtro.set_index("TIMESTAMP")

if intervalo == "15 minutos":
    grafico = dados.resample("15T").mean(numeric_only=True)

elif intervalo == "1 hora":
    grafico = dados.resample("1H").mean(numeric_only=True)

else:
    grafico = dados.resample("1D").mean(numeric_only=True)

st.subheader("☔ Intensidade da Chuva")

fig = px.line(
    grafico,
    y="intensidade"
)

st.plotly_chart(fig, use_container_width=True)

st.subheader("💧 Chuva acumulada")

fig2 = px.line(
    grafico,
    y="chuva_acumulada"
)

st.plotly_chart(fig2, use_container_width=True)

# -------------------------------
# CHUVA POR ANO
# -------------------------------

st.divider()

chuva_ano = df.groupby("Ano")["Chuva_mm"].sum().reset_index()

fig3 = px.bar(
    chuva_ano,
    x="Ano",
    y="Chuva_mm",
    labels={"Chuva_mm": "Chuva (mm)"}
)

st.plotly_chart(fig3, use_container_width=True)