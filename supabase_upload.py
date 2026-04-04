import os
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)


def _clean_env(name: str):
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip().strip('"').strip("'")
    return value if value else None


SUPABASE_URL = _clean_env("SUPABASE_URL")
SUPABASE_KEY = _clean_env("SUPABASE_KEY")

print("ENV_PATH_USADO:", ENV_PATH, flush=True)
print("SUPABASE_URL_DEBUG:", repr(SUPABASE_URL), flush=True)
print("SUPABASE_KEY_PREFIX:", SUPABASE_KEY[:20] if SUPABASE_KEY else None, flush=True)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL e SUPABASE_KEY precisam estar definidos")

host = urlparse(SUPABASE_URL).netloc
print("SUPABASE_HOST_EXTRAIDO:", repr(host), flush=True)

try:
    ip = socket.gethostbyname(host)
    print("DNS_OK_IP:", ip, flush=True)
except Exception as e:
    raise Exception(
        f"DNS_FALHOU para host {host}. "
        f"Confira SUPABASE_URL no .env. Erro real: {e}"
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


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


def ler_relatorio(arquivo):
    caminho = Path(str(arquivo))
    ext = caminho.suffix.lower()

    print(f"ARQUIVO_RECEBIDO: {caminho}", flush=True)
    print(f"EXTENSAO_DETECTADA: {ext}", flush=True)

    # 1) Excel real
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(caminho, dtype=str)
        print(f"LINHAS_LIDAS_EXCEL: {len(df)}", flush=True)
        print(f"COLUNAS_EXCEL: {list(df.columns)}", flush=True)
        return df

    # 2) CSV / TXT / exportações texto do SSW
    if ext in [".csv", ".txt", ".sswweb", ".xml", ""]:
        tentativas = [
            {"sep": ";", "encoding": "utf-8-sig"},
            {"sep": ";", "encoding": "latin1"},
            {"sep": ";", "encoding": "utf-8"},
            {"sep": ",", "encoding": "utf-8-sig"},
            {"sep": ",", "encoding": "latin1"},
            {"sep": ",", "encoding": "utf-8"},
            {"sep": "\t", "encoding": "utf-8-sig"},
            {"sep": "\t", "encoding": "latin1"},
            {"sep": "|", "encoding": "utf-8-sig"},
            {"sep": "|", "encoding": "latin1"},
        ]

        ultimo_erro = None

        for cfg in tentativas:
            try:
                print(f"TENTANDO_LER_CSV: {cfg}", flush=True)
                df = pd.read_csv(caminho, dtype=str, **cfg)

                # válido quando realmente dividiu em colunas
                if len(df.columns) > 1:
                    print(f"LEITURA_OK_COM: {cfg}", flush=True)
                    print(f"LINHAS_LIDAS: {len(df)}", flush=True)
                    print(f"COLUNAS_LIDAS: {list(df.columns)}", flush=True)
                    return df
            except Exception as e:
                ultimo_erro = e

        # fallback: tenta detectar se é arquivo de uma coluna só mas com cabeçalho útil
        try:
            df = pd.read_csv(caminho, dtype=str, encoding="utf-8-sig")
            print("FALLBACK_UTF8_SIG_EXECUTADO", flush=True)
            print(f"COLUNAS_FALLBACK: {list(df.columns)}", flush=True)
            return df
        except Exception as e:
            ultimo_erro = e

        try:
            df = pd.read_csv(caminho, dtype=str, encoding="latin1")
            print("FALLBACK_LATIN1_EXECUTADO", flush=True)
            print(f"COLUNAS_FALLBACK: {list(df.columns)}", flush=True)
            return df
        except Exception as e:
            ultimo_erro = e

        raise Exception(f"Não consegui ler o arquivo {caminho}. Erro final: {ultimo_erro}")

    raise Exception(f"Extensão não suportada para leitura: {caminho}")


def tratar_dataframe(df):
    if df is None or df.empty:
        raise Exception("DataFrame vazio após leitura do relatório.")

    df = limpar_colunas(df)
    df = df.loc[:, ~df.columns.str.startswith("unnamed")].copy()

    print("COLUNAS_NORMALIZADAS:", list(df.columns), flush=True)
    print("HEAD_ORIGINAL:", flush=True)
    print(df.head(10).to_string(), flush=True)

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

    # mapa para ajustar nomes comuns do arquivo exportado
    renomear = {
        "cotação": "cotacao",
        "cotacao": "cotacao",
        "unidade_de_inclusao": "unidade_inclusao",
        "usuario": "usuario_inclusao",
        "usuario_de_inclusao": "usuario_inclusao",
        "pagador": "nome_pagador",
        "cnpj_do_pagador": "cnpj_pagador",
        "nome_do_pagador": "nome_pagador",
        "praça_coleta": "praca_coleta",
        "praça_comercial": "praca_comercial",
        "cnpj_do_destinatario": "cnpj_destinatario",
        "nome_do_destinatario": "nome_destinatario",
        "quantidade_volumes": "qtd_volumes",
        "quantidade_pares": "qtd_pares",
        "peso_cálculo": "peso_calculo",
        "peso_calculo": "peso_calculo",
        "frete_ntc_": "frete_ntc",
        "proposta_inicial_": "proposta_inicial",
        "proposta_atual_": "proposta_atual",
        "descrição_ntc": "desc_ntc",
        "descricao_ntc": "desc_ntc",
        "descrição_inicial": "desc_inicial",
        "descricao_inicial": "desc_inicial",
        "tabela_de_cálculo": "tabela_de_calculo",
        "tabela_de_calculo": "tabela_de_calculo",
        "data_hora_de_inclusao": "data_hora_inclusao",
        "data_emissão_ctrc": "data_emissao_ctrc",
        "data_emissao_ctrc": "data_emissao_ctrc",
        "frete_do_ctrc": "frete_ctrc",
    }

    df = df.rename(columns=renomear)

    if "cotacao" not in df.columns:
        raise Exception(
            f"Coluna 'cotacao' não encontrada. Colunas atuais: {list(df.columns)}"
        )

    df = df[df["cotacao"].notna()].copy()
    df["cotacao"] = df["cotacao"].astype(str).str.strip()
    df = df[df["cotacao"] != ""].copy()

    for col in ["data_hora_inclusao", "data_emissao_ctrc", "validade"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    for col in colunas_tabela:
        if col in df.columns and col not in ["data_hora_inclusao", "data_emissao_ctrc", "validade"]:
            df[col] = df[col].apply(
                lambda x: None if pd.isna(x) else str(x).strip()
            )

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

    print("COLUNAS_FINAIS:", df.columns.tolist(), flush=True)
    print("HEAD_DF_TRATADO:", flush=True)
    print(df.head(20).to_string(), flush=True)

    return df


def enviar_para_supabase(df):
    df = df.copy()

    colunas_data = [
        "data_hora_inclusao",
        "data_emissao_ctrc",
        "validade",
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

    print("UPLOAD_CONCLUIDO", flush=True)