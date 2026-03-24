import os
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL e SUPABASE_KEY precisam estar no .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def ler_relatorio(arquivo):
    tentativas = [
        {"sep": ";", "encoding": "latin1"},
        {"sep": ";", "encoding": "utf-8"},
        {"sep": ",", "encoding": "latin1"},
        {"sep": ",", "encoding": "utf-8"},
        {"sep": "\t", "encoding": "latin1"},
    ]

    ultimo_erro = None

    for cfg in tentativas:
        try:
            df = pd.read_csv(arquivo, **cfg)
            if len(df.columns) > 1:
                return df
        except Exception as e:
            ultimo_erro = e

    raise Exception(f"Não consegui ler o arquivo {arquivo}. Erro: {ultimo_erro}")


def normalizar_nome_coluna(col):
    return (
        str(col)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
    )


def limpar_colunas(df):
    df = df.copy()
    df.columns = [normalizar_nome_coluna(c) for c in df.columns]
    return df


def tratar_dataframe(df):
    df = limpar_colunas(df)

    # remove colunas inúteis tipo unnamed
    df = df.loc[:, ~df.columns.str.startswith("unnamed")].copy()

    # renomeia cabeçalhos reais do seu relatório para o padrão da tabela
    mapa = {
        "cotacao": "cotacao",
        "data_hora_inclusao": "data_hora_inclusao",
        "usuario_inclusao": "usuario_inclusao",
        "cnpj_pagador": "cnpj_cpf_pagador",
        "nome_pagador": "nome_pagador",
        "origem": "origem",
        "destino": "destino",
        "tipo_frete": "tipo_frete",
        "situacao": "situacao",
        "proposta_atual": "proposta_atual",
        "frete_ntc": "frete_ntc",
        "validade": "validade",
        "ctrc": "ctrc",
        "observacao": "observacoes",
    }

    renomear = {}
    for col in df.columns:
        if col in mapa:
            renomear[col] = mapa[col]

    df = df.rename(columns=renomear)

    if "cotacao" not in df.columns:
        raise Exception(f"Coluna 'cotacao' não encontrada. Colunas atuais: {list(df.columns)}")

    # remove linhas vazias
    df = df[df["cotacao"].notna()].copy()

    # converte cotacao
    df["cotacao"] = pd.to_numeric(df["cotacao"], errors="coerce")
    df = df[df["cotacao"].notna()].copy()
    df["cotacao"] = df["cotacao"].astype(int)

    # numéricos
    for col in ["proposta_atual", "frete_ntc"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # data/hora
    if "data_hora_inclusao" in df.columns:
        df["data_hora_inclusao"] = pd.to_datetime(
            df["data_hora_inclusao"],
            errors="coerce",
            dayfirst=True
        )

    agora = datetime.now()
    df["mes_referencia"] = agora.replace(day=1).date()
    df["data_extracao"] = agora
    df["updated_at"] = agora

    colunas_tabela = [
        "cotacao",
        "data_hora_inclusao",
        "usuario_inclusao",
        "cnpj_cpf_pagador",
        "nome_pagador",
        "origem",
        "destino",
        "tipo_frete",
        "situacao",
        "proposta_atual",
        "frete_ntc",
        "validade",
        "ctrc",
        "observacoes",
        "mes_referencia",
        "data_extracao",
        "updated_at",
    ]

    for c in colunas_tabela:
        if c not in df.columns:
            df[c] = None

    df = df[colunas_tabela].copy()

    return df


def enviar_para_supabase(df):
    df = df.copy()

    # datas para string ISO
    colunas_data = ["data_hora_inclusao", "mes_referencia", "data_extracao", "updated_at"]
    for col in colunas_data:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: x.isoformat() if pd.notnull(x) and hasattr(x, "isoformat") else None
            )

    # colunas texto: troca NaN por None e força texto quando houver valor
    colunas_texto = [
        "usuario_inclusao",
        "cnpj_cpf_pagador",
        "nome_pagador",
        "origem",
        "destino",
        "tipo_frete",
        "situacao",
        "validade",
        "ctrc",
        "observacoes",
    ]

    for col in colunas_texto:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else str(x).strip())

    # colunas numéricas: troca NaN por None
    colunas_numericas = ["cotacao", "proposta_atual", "frete_ntc"]
    for col in colunas_numericas:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)

    # conversão final registro a registro para garantir que não sobre nenhum NaN
    registros = []
    for registro in df.to_dict(orient="records"):
        limpo = {}
        for k, v in registro.items():
            if pd.isna(v):
                limpo[k] = None
            else:
                limpo[k] = v
        registros.append(limpo)

    tamanho_lote = 500
    for i in range(0, len(registros), tamanho_lote):
        lote = registros[i:i + tamanho_lote]
        supabase.table("ssw_cotacoes").upsert(
            lote,
            on_conflict="cotacao"
        ).execute()