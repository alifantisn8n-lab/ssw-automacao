import os
import time
import pandas as pd
from datetime import datetime
from pathlib import Path
from io import StringIO

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from supabase_upload import ler_relatorio, tratar_dataframe, enviar_para_supabase

load_dotenv()

SSW_URL = os.getenv("SSW_URL")
DOMINIO = os.getenv("SSW_DOMINIO")
CPF = os.getenv("SSW_CPF")
USUARIO = os.getenv("SSW_USUARIO")
SENHA = os.getenv("SSW_SENHA")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def log(msg):
    print(msg, flush=True)


def arquivos_na_pasta():
    return {p.name: p.stat().st_mtime for p in DOWNLOAD_DIR.glob("*") if p.is_file()}


def esperar_novo_arquivo(antes, timeout=60):
    inicio = time.time()
    while time.time() - inicio < timeout:
        atuais = arquivos_na_pasta()
        novos = [nome for nome in atuais if nome not in antes]
        if novos:
            novos.sort(key=lambda n: atuais[n], reverse=True)
            return DOWNLOAD_DIR / novos[0]
        time.sleep(1)
    return None


def registrar_dialogos(page):
    def on_dialog(dialog):
        try:
            dialog.accept()
        except Exception:
            pass
    page.on("dialog", on_dialog)


def login(page):
    inputs = page.locator("input")
    campos = []

    for i in range(inputs.count()):
        inp = inputs.nth(i)
        try:
            tipo = (inp.get_attribute("type") or "").lower()
            if inp.is_visible() and tipo in ["text", "password", ""]:
                campos.append(inp)
        except Exception:
            pass

    if len(campos) < 4:
        raise Exception("Campos de login não encontrados.")

    campos[0].fill(DOMINIO)
    campos[1].fill(CPF)
    campos[2].fill(USUARIO)
    campos[3].fill(SENHA)

    try:
        box = campos[3].bounding_box()
        x = box["x"] + box["width"] + 28
        y = box["y"] + (box["height"] / 2)
        page.mouse.click(x, y)
    except Exception:
        campos[3].press("Tab")
        page.keyboard.press("Enter")

    page.wait_for_timeout(4000)


def fechar_popup(page, context):
    for tecla in ["Enter", "Escape"]:
        try:
            page.keyboard.press(tecla)
            page.wait_for_timeout(300)
        except Exception:
            pass

    for pg in context.pages[1:]:
        try:
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(300)
            pg.close()
        except Exception:
            pass


def abrir_tela_2(page, context):
    inputs = page.locator("input")
    campo_opcao = None

    for i in range(inputs.count()):
        inp = inputs.nth(i)
        try:
            tipo = (inp.get_attribute("type") or "").lower()
            valor = ""
            try:
                valor = inp.input_value().strip()
            except Exception:
                pass

            if inp.is_visible() and tipo in ["text", "number", ""] and len(valor) <= 2:
                campo_opcao = inp
                break
        except Exception:
            pass

    if campo_opcao is None:
        raise Exception("Campo da opção não encontrado.")

    paginas_antes = len(context.pages)

    campo_opcao.click()
    campo_opcao.fill("")
    campo_opcao.type("2", delay=100)

    try:
        with context.expect_page(timeout=5000) as nova_pagina_info:
            campo_opcao.press("Enter")
        tela2 = nova_pagina_info.value
        registrar_dialogos(tela2)
        tela2.wait_for_load_state("domcontentloaded", timeout=15000)
        tela2.wait_for_timeout(2000)
        return tela2
    except Exception:
        page.wait_for_timeout(3000)

    if len(context.pages) > paginas_antes:
        tela2 = context.pages[-1]
        registrar_dialogos(tela2)
        tela2.wait_for_load_state("domcontentloaded", timeout=15000)
        tela2.wait_for_timeout(2000)
        return tela2

    return page


def preencher_tela_2(page):
    hoje = datetime.now()
    data_inicial = hoje.replace(day=1).strftime("%d%m%y")
    data_final = hoje.strftime("%d%m%y")

    campos = []
    inputs = page.locator("input")

    for i in range(inputs.count()):
        inp = inputs.nth(i)
        try:
            tipo = (inp.get_attribute("type") or "").lower()
            if inp.is_visible() and tipo in ["text", "number", ""]:
                campos.append(inp)
        except Exception:
            pass

    if len(campos) < 11:
        raise Exception("Campos da Tela 2 não encontrados corretamente.")

    campo_listar = campos[1]
    campo_obs = campos[4]
    campo_unid_inc = campos[5]
    campo_unid_orig = campos[6]
    campo_usuario = campos[7]
    campo_cnpj = campos[8]
    campo_data_ini = campos[9]
    campo_data_fim = campos[10]

    campo_listar.fill("")
    campo_listar.type("E", delay=100)

    campo_obs.fill("")
    campo_obs.type("S", delay=100)

    for campo in [campo_unid_inc, campo_unid_orig, campo_usuario, campo_cnpj]:
        campo.fill("")

    campo_data_ini.fill("")
    campo_data_ini.type(data_inicial, delay=100)

    campo_data_fim.fill("")
    campo_data_fim.type(data_final, delay=100)


def clicar_play_final(page):
    js = """
    () => {
        function visible(el) {
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' &&
                   s.visibility !== 'hidden' &&
                   r.width > 0 &&
                   r.height > 0;
        }

        const dtIni = document.querySelector('input[name="f17"]');
        const dtFim = document.querySelector('input[name="f18"]');

        if (!dtIni || !dtFim) return null;

        const r1 = dtIni.getBoundingClientRect();
        const r2 = dtFim.getBoundingClientRect();

        const refX = Math.min(r1.left, r2.left);
        const refY = Math.max(r1.bottom, r2.bottom);

        const candidatos = Array.from(document.querySelectorAll(
            'input[type="image"], img, button, a, input[type="submit"]'
        ))
        .filter(visible)
        .map(el => {
            const r = el.getBoundingClientRect();
            const dx = Math.abs(r.left - refX);
            const dy = Math.abs(r.top - refY);
            const dist = Math.sqrt(dx * dx + dy * dy);
            return {
                x: r.left + r.width / 2,
                y: r.top + r.height / 2,
                top: r.top,
                left: r.left,
                dist: dist,
                area: r.width * r.height
            };
        })
        .filter(x =>
            x.area > 20 &&
            x.top >= (refY - 40) &&
            x.top <= (refY + 120) &&
            x.left <= (refX + 120)
        )
        .sort((a, b) => a.dist - b.dist);

        return candidatos.length ? candidatos[0] : null;
    }
    """

    alvo = page.evaluate(js)

    if alvo:
        page.mouse.click(alvo["x"], alvo["y"])
        return True

    try:
        campo_f18 = page.locator('input[name="f18"]').first
        campo_f18.click()
        page.wait_for_timeout(200)
        campo_f18.press("Tab")
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        return True
    except Exception:
        return False


def gerar_relatorio(page):
    print("Gerando relatório...", flush=True)

    clicou = clicar_play_final(page)
    if not clicou:
        raise Exception("Não consegui clicar no play final.")

    time.sleep(8)

    if "ssw1601" in page.url.lower():
        print(f"Relatório abriu em HTML: {page.url}", flush=True)

        texto = page.locator("body").inner_text()
        destino = DOWNLOAD_DIR / f"relatorio_{int(time.time())}.txt"

        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)

        print(f"OK - relatório salvo em texto: {destino}", flush=True)
        print("INICIO_TEXTO_RELATORIO", flush=True)
        print(texto[:4000], flush=True)
        print("FIM_TEXTO_RELATORIO", flush=True)

        return destino

    antes = arquivos_na_pasta()
    arquivo = esperar_novo_arquivo(antes, timeout=20)
    if arquivo:
        print(f"OK - relatório salvo em: {arquivo}", flush=True)
        return arquivo

    raise Exception("Nenhum relatório foi encontrado após clicar no play final.")

def processar_relatorio_e_enviar(arquivo):
    log("Lendo relatório...")
    df = ler_relatorio(arquivo)
    print("COLUNAS_LIDAS:", df.columns.tolist(), flush=True)
print("HEAD_DF:", flush=True)
print(df.head(20).to_string(), flush=True)

    log("Tratando dados...")
    df = tratar_dataframe(df)

    log(f"Total de registros para envio: {len(df)}")

    log("Enviando para Supabase...")
    enviar_para_supabase(df)

    log("OK - dados enviados para o Supabase")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            slow_mo=200,
            downloads_path=str(DOWNLOAD_DIR)
        )

        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1366, "height": 768}
        )

        page = context.new_page()
        registrar_dialogos(page)

        try:
            log("Abrindo SSW...")
            page.goto(SSW_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            log("Fazendo login...")
            login(page)

            log("Fechando popup...")
            fechar_popup(page, context)

            log("Abrindo Tela 2...")
            tela2 = abrir_tela_2(page, context)

            log("Preenchendo Tela 2...")
            preencher_tela_2(tela2)

            log("Gerando relatório...")
            arquivo = gerar_relatorio(tela2)

            log(f"OK - relatório salvo em: {arquivo}")

            processar_relatorio_e_enviar(arquivo)

            log("Processo finalizado com sucesso.")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()