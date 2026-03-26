import os
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def _clean_env(name: str):
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


SUPABASE_URL = _clean_env("SUPABASE_URL")
SUPABASE_KEY = _clean_env("SUPABASE_KEY")

print("SUPABASE_URL_DEBUG:", repr(SUPABASE_URL), flush=True)
print(
    "SUPABASE_KEY_PREFIX:",
    SUPABASE_KEY[:20] if SUPABASE_KEY else None,
    flush=True
)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL e SUPABASE_KEY precisam estar definidos")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def ler_relatorio(arquivo):
    arquivo = str(arquivo)

    tentativas = [
        {"sep": ";", "encoding": "utf-8-sig"},
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

    colunas_tabela = [
        "cotacao",
        "unidade_inclusao",
        "usuario_inclusao",
        "cnpj_pagador",
        "nome_pagador",
        "abc",
        "vendedor",
        "origem",
        "praca_coleta",
        "praca_comercial",
        "destino",
        "cnpj_destinatario",
        "nome_destinatario",
        "ed",
        "tipo_frete",
        "mercadoria",
        "valor_nf",
        "qtd_volumes",
        "qtd_pares",
        "peso",
        "cubagem",
        "peso_calculo",
        "frete_ntc",
        "proposta_inicial",
        "proposta_atual",
        "desc_ntc",
        "rc",
        "desc_inicial",
        "tabela_de_calculo",
        "observacao",
        "data_hora_inclusao",
        "validade",
        "situacao",
        "ctrc",
        "data_emissao_ctrc",
        "frete_ctrc",
        "relatorio_comissao",
        "unidade_responsavel",
        "usuario_alteracao",
        "contato",
        "autorizado",
    ]

    if "cotacao" not in df.columns:
        raise Exception(f"Coluna 'cotacao' não encontrada. Colunas atuais: {list(df.columns)}")

    # remove linhas sem cotacao
    df = df[df["cotacao"].notna()].copy()

    # cotacao como texto para casar com a PK
    df["cotacao"] = df["cotacao"].astype(str).str.strip()
    df = df[df["cotacao"] != ""].copy()

    # datas
    for col in ["data_hora_inclusao", "data_emissao_ctrc"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # força texto nas outras colunas do arquivo
    for col in colunas_tabela:
        if col in df.columns and col not in ["data_hora_inclusao", "data_emissao_ctrc"]:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else str(x).strip())

    agora = datetime.now()
    df["mes_referencia"] = agora.replace(day=1).date()
    df["data_extracao"] = agora
    df["updated_at"] = agora

    colunas_finais = colunas_tabela + [
        "mes_referencia",
        "data_extracao",
        "updated_at",
    ]

    for c in colunas_finais:
        if c not in df.columns:
            df[c] = None

    df = df[colunas_finais].copy()

    return df


def enviar_para_supabase(df):
    df = df.copy()

    colunas_data = [
        "data_hora_inclusao",
        "data_emissao_ctrc",
        "mes_referencia",
        "data_extracao",
        "updated_at",
    ]

    for col in colunas_data:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: x.isoformat() if pd.notnull(x) and hasattr(x, "isoformat") else None
            )

    registros = []
    for registro in df.to_dict(orient="records"):
        limpo = {}
        for k, v in registro.items():
            if pd.isna(v):
                limpo[k] = None
            else:
                limpo[k] = v
        registros.append(limpo)

    print(f"ENVIANDO {len(registros)} REGISTROS PARA O SUPABASE", flush=True)

    tamanho_lote = 500
    for i in range(0, len(registros), tamanho_lote):
        lote = registros[i:i + tamanho_lote]
        print(f"LOTE {i} ATÉ {i + len(lote)}", flush=True)
        supabase.table("ssw_cotacoes").upsert(
            lote,
            on_conflict="cotacao"
        ).execute()