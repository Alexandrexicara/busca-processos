"""
Scraper para consulta de advogados via CNA/OAB (cna.oab.org.br).

Fluxo de resolução de reCAPTCHA:
  1. Abre Playwright headful (requer Xvfb em DISPLAY :99)
  2. Preenche o formulário e clica Pesquisar
  3. API retorna 428 → Angular renderiza widget reCAPTCHA V2
  4. Clica no checkbox → Google exibe image challenge
  5. Screenshot do grid → Claude classifica objetos → clicks nas células corretas
  6. VERIFY → se aceito, Angular chama API com X-Recaptcha-V2-Token
  7. Capturamos o token via interceptação e retornamos os dados do advogado

Variáveis de ambiente:
  DISPLAY             — display Xvfb, padrão :99
  TWOCAPTCHA_API_KEY  — chave do 2captcha.com (opcional, alternativa ao solver LLM)
  OAB_MOCK_MODE       — qualquer valor != "" ativa dados de teste sem browser
  BTY_LLM_SERVER_BASE_URL — gateway LLM (definido pelo ambiente)
  BTY_LLM_SERVER_API_KEY  — chave do gateway LLM (definido pelo ambiente)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)

# ──────────────────────────── Constantes ──────────────────────────────────────

CNA_SITE          = "https://cna.oab.org.br/"
CNA_API_BASE      = "https://cna.oab.org.br/cna-interno/api"
RECAPTCHA_V2_SITE_KEY = "6LcZ0vIrAAAAAGrnTvAlD8c-6sIo8JRf3qG4dMOS"

_CHROMIUM_PATH = (
    "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)

ESTADOS_OAB = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

# ──────────────────────────── Mock para desenvolvimento ───────────────────────

_MOCK_DATA: Dict[str, Dict[str, Any]] = {
    "MS/3616": {
        "nome": "ADVOGADO TESTE (mock)",
        "oab": "3616",
        "uf": "MS",
        "situacao": "Ativo",
        "tipo": "Advogado",
        "email": "",
        "telefone": "",
        "subSeccional": "",
        "raw": {},
        "fonte": "CNA/OAB (mock)",
    },
}


def _get_mock(estado: str, numero: str) -> Optional[Dict[str, Any]]:
    key = f"{estado.upper()}/{numero.strip()}"
    return _MOCK_DATA.get(key)


# ──────────────────────────── Normalização de resposta ────────────────────────

def _parse_cna_response(data: Any) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    items: List[dict] = []
    if isinstance(data, dict):
        items = data.get("items") or data.get("Items") or []
        if not items and data.get("nome"):
            items = [data]
    elif isinstance(data, list):
        items = data
    if not items:
        return None
    adv = items[0]
    return {
        "nome":        adv.get("nome") or adv.get("Nome") or "",
        "oab":         adv.get("inscricao") or adv.get("Inscricao") or adv.get("numeroinscricao") or "",
        "uf":          adv.get("uf") or adv.get("Uf") or adv.get("seccional") or "",
        "situacao":    adv.get("situacao") or adv.get("Situacao") or adv.get("status") or "Ativo",
        "tipo":        adv.get("tipoInscricao") or adv.get("TipoInscricao") or "Advogado",
        "email":       adv.get("email") or adv.get("Email") or "",
        "telefone":    adv.get("telefone") or adv.get("Telefone") or "",
        "subSeccional": adv.get("subSeccional") or adv.get("SubSeccional") or "",
        "raw":         adv,
        "fonte":       "CNA/OAB",
    }


# ──────────────────────────── Chamada à API CNA ───────────────────────────────

async def _call_cna_api(
    estado: str,
    numero: str,
    token: str,
    token_type: str = "v2",   # "v2" | "v3"
    timeout: int = 20,
) -> Optional[Dict[str, Any]]:
    url = f"{CNA_API_BASE}/advogado/search"
    params = {"Uf": estado.upper(), "TipoInscricao": "1", "Inscricao": numero}
    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ),
        "Referer": CNA_SITE,
        "Origin": "https://cna.oab.org.br",
        "Accept": "application/json, text/plain, */*",
    }
    if token_type == "v2":
        headers = {**base_headers, "X-Recaptcha-V2-Token": token}
    else:
        headers = {**base_headers, "X-Recaptcha-Token": token, "X-Recaptcha-Action": "lawyer_search"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    return _parse_cna_response(await resp.json(content_type=None))
                if resp.status == 428:
                    return None  # precisa V2
                logger.warning(f"CNA API {resp.status}: {await resp.text()[:200]}")
    except asyncio.TimeoutError:
        logger.warning("Timeout na API CNA")
    except Exception as exc:
        logger.error(f"Erro na API CNA: {exc}")
    return None


# ──────────────────────────── Solver LLM visual ───────────────────────────────

async def _classify_grid_llm(screenshot_b64: str, task: str) -> List[int]:
    """
    Envia screenshot do grid ao Claude e retorna índices de células com o objeto pedido.
    """
    base_url = os.environ.get("BTY_LLM_SERVER_BASE_URL", "")
    api_key  = os.environ.get("BTY_LLM_SERVER_API_KEY", "")
    if not base_url or not api_key:
        logger.debug("LLM env vars ausentes, sem solver visual")
        return []

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "x-bty-business": "ReActUs",
        "x-bty-workspace": "default",
    }
    body = {
        "model": "claude-sonnet-4.6",
        "max_tokens": 100,
        "stream": False,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64},
                },
                {
                    "type": "text",
                    "text": (
                        f"reCAPTCHA image grid challenge. "
                        f"Task: select all images with '{task}'. "
                        f"Cells are numbered 0–8 (3×3, left-to-right top-to-bottom) "
                        f"or 0–15 (4×4). "
                        f"Reply ONLY with a JSON array of matching cell indices, e.g. [0,3,7] or []. "
                        f"No explanation."
                    ),
                },
            ],
        }],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/messages",
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json(content_type=None)
                text = data.get("content", [{}])[0].get("text", "[]").strip()
                m = re.search(r"\[[\d,\s]*\]", text)
                result: List[int] = json.loads(m.group()) if m else []
                logger.debug(f"LLM classify({task!r}): {result}")
                return result
    except Exception as exc:
        logger.warning(f"Erro no solver LLM: {exc}")
        return []


# ──────────────────────────── Solver via 2captcha ─────────────────────────────

async def _get_token_2captcha() -> Optional[str]:
    api_key = os.environ.get("TWOCAPTCHA_API_KEY", "")
    if not api_key:
        return None
    try:
        submit_data = {
            "key": api_key,
            "method": "userrecaptcha",
            "googlekey": RECAPTCHA_V2_SITE_KEY,
            "pageurl": CNA_SITE,
            "json": "1",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://2captcha.com/in.php",
                data=submit_data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json(content_type=None)
                if data.get("status") != 1:
                    logger.warning(f"2captcha submit erro: {data}")
                    return None
                task_id = data["request"]

            for _ in range(24):
                await asyncio.sleep(5)
                async with session.get(
                    "http://2captcha.com/res.php",
                    params={"key": api_key, "action": "get", "id": task_id, "json": "1"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    res = await resp.json(content_type=None)
                    if res.get("status") == 1:
                        return res["request"]
                    if res.get("request") != "CAPCHA_NOT_READY":
                        logger.warning(f"2captcha erro: {res}")
                        return None
    except Exception as exc:
        logger.error(f"Erro 2captcha: {exc}")
    return None


# ──────────────────────────── Solver Playwright + LLM ────────────────────────

async def _get_v2_token_playwright(estado: str, numero: str) -> Optional[str]:
    """
    Abre browser headful, resolve reCAPTCHA V2 via LLM visual,
    e retorna o X-Recaptcha-V2-Token capturado da chamada à API.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright não instalado")
        return None

    display = os.environ.get("DISPLAY", ":99")
    exec_path = _CHROMIUM_PATH if os.path.isfile(_CHROMIUM_PATH) else None

    token_holder: Dict[str, Optional[str]] = {"token": None}
    api_status:   Dict[str, Optional[int]]  = {"status": None}

    async with async_playwright() as pw:
        launch_kw: Dict[str, Any] = {
            "headless": False,
            "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"],
            "env": {**os.environ, "DISPLAY": display},
        }
        if exec_path:
            launch_kw["executable_path"] = exec_path

        browser = await pw.chromium.launch(**launch_kw)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()

        async def _capture_api(response):
            if "cna-interno" in response.url:
                api_status["status"] = response.status
                tok = response.request.headers.get("x-recaptcha-v2-token")
                if tok:
                    token_holder["token"] = tok
                    logger.debug(f"Token V2 capturado: {tok[:30]}…")
        page.on("response", _capture_api)

        try:
            await page.goto(CNA_SITE, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(4000)
            await page.type("input[name='registration']", numero, delay=120)
            await page.wait_for_timeout(800)
            await page.select_option("select[name='sectional']", value=estado.upper())
            await page.wait_for_timeout(800)
            await page.select_option("select[name='registrationType']", label="Advogado")
            await page.wait_for_timeout(1500)
            await page.click("button:has-text('Pesquisar')")
            await page.wait_for_timeout(6000)

            # Aguardar widget V2
            iframe_v2 = await page.wait_for_selector("iframe[width='304']", timeout=15000)
            if not iframe_v2:
                logger.warning("Widget V2 não apareceu")
                return None

            bbox = await iframe_v2.bounding_box()
            if not bbox:
                return None

            # Clicar no checkbox para abrir challenge
            await page.mouse.click(bbox["x"] + 24, bbox["y"] + bbox["height"] / 2)
            await page.wait_for_timeout(5000)

            frames = page.frames
            bf_frames  = [f for f in frames if "bframe" in f.url]
            anc_frames = [f for f in frames if "6LcZ0vIr" in f.url and "anchor" in f.url]
            if not bf_frames:
                logger.warning("bframe não encontrado")
                return None

            bf        = bf_frames[0]
            bframe_el = await page.query_selector("iframe[src*='bframe']")

            # ── Loop de resolução do challenge ──────────────────────────────
            for attempt in range(25):
                # Verificar se já resolveu
                if token_holder["token"]:
                    break
                if anc_frames:
                    checked = await anc_frames[0].evaluate(
                        "() => document.querySelector('#recaptcha-anchor')?.getAttribute('aria-checked')"
                    )
                    if checked == "true":
                        await page.wait_for_timeout(4000)
                        break

                info = await bf.evaluate("""() => ({
                    task:          document.querySelector('.rc-imageselect-desc strong, .rc-imageselect-desc-no-canonical strong')?.innerText?.trim() || '',
                    has_doscaptcha: !!document.querySelector('.rc-doscaptcha-header'),
                    has_skip:      !!document.querySelector('.rc-button-default'),
                    cell_count:    document.querySelectorAll('td.rc-imageselect-tile').length,
                    is_dynamic:    (document.querySelector('.rc-imageselect-desc')?.innerText || '').includes('none left')
                })""")

                task       = info.get("task", "").strip()
                cell_count = info.get("cell_count", 0)

                logger.debug(
                    f"V2 attempt {attempt + 1}: task={task!r} cells={cell_count} "
                    f"skip={info.get('has_skip')} dos={info.get('has_doscaptcha')}"
                )

                if info.get("has_doscaptcha"):
                    logger.warning("reCAPTCHA rate limit, aguardando 12s…")
                    await page.wait_for_timeout(12000)
                    continue

                if not task:
                    await page.wait_for_timeout(2000)
                    continue

                # Grids 4×4 → usar SKIP quando disponível
                if info.get("has_skip") and cell_count == 16:
                    await bf.click(".rc-button-default", force=True, timeout=5000)
                    await page.wait_for_timeout(2500)
                    continue

                # ── Resolver via LLM ────────────────────────────────────────
                bframe_bbox = await bframe_el.bounding_box()
                if not bframe_bbox:
                    await page.wait_for_timeout(2000)
                    continue

                shot = await page.screenshot(
                    clip={
                        "x": bframe_bbox["x"], "y": bframe_bbox["y"],
                        "width": bframe_bbox["width"], "height": bframe_bbox["height"],
                    }
                )
                indices = await _classify_grid_llm(base64.b64encode(shot).decode(), task)

                if not indices:
                    # Nenhuma célula correta → verificar (novo challenge ou aprovação)
                    try:
                        await bf.click("#recaptcha-verify-button", force=True, timeout=5000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(3000)
                    continue

                # Clicar nas células corretas via JS (mais confiável que mouse)
                await bf.evaluate(f"""() => {{
                    const cells = Array.from(document.querySelectorAll('td.rc-imageselect-tile'));
                    const idx = {json.dumps(indices)};
                    idx.forEach(i => {{
                        if (i < cells.length)
                            cells[i].dispatchEvent(new MouseEvent('click', {{
                                bubbles: true, cancelable: true, view: window
                            }}));
                    }});
                }}""")
                await page.wait_for_timeout(2000)

                # Para challenges dinâmicos, aguardar novas imagens
                if info.get("is_dynamic"):
                    await page.wait_for_timeout(2000)

                # Clicar VERIFY
                try:
                    await bf.click("#recaptcha-verify-button", force=True, timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(4000)

        except Exception as exc:
            logger.error(f"Erro no Playwright solver: {exc}")
        finally:
            await browser.close()

    return token_holder.get("token")


# ──────────────────────────── Função pública principal ───────────────────────

async def _get_v3_token_headless(estado: str, numero: str) -> Optional[str]:
    """
    Tenta obter token reCAPTCHA V3 via chamada direta à API do Google
    (sem browser). Funciona quando o IP tem score suficiente.
    """
    try:
        v3_site_key = "6LecMcgsAAAAAMfCE4QBHHbHHsKUhCHCDJD4z-Ng"
        url = f"https://www.google.com/recaptcha/api2/anchor?ar=1&k={v3_site_key}&co=aHR0cHM6Ly9jbmEub2FiLm9yZy5icjo0NDM.&hl=pt-BR&v=rAnd0m&size=invisible&cb=xyz"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Referer": CNA_SITE,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                html = await resp.text()
                m = re.search(r'"recaptcha-token" value="([^"]+)"', html)
                if m:
                    token = m.group(1)
                    # Trocar pelo token real via reload
                    reload_url = "https://www.google.com/recaptcha/api2/reload"
                    data = f"v={v3_site_key}&reason=q&c={token}&k={v3_site_key}&co=aHR0cHM6Ly9jbmEub2FiLm9yZy5icjo0NDM."
                    async with session.post(reload_url, data=data,
                                            headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                                            timeout=aiohttp.ClientTimeout(total=10)) as r2:
                        body = await r2.text()
                        m2 = re.search(r'"rresp","([^"]+)"', body)
                        if m2:
                            return m2.group(1)
    except Exception as exc:
        logger.debug(f"V3 headless falhou: {exc}")
    return None


async def consultar_advogado_oab(
    estado: str,
    numero: str,
) -> Optional[Dict[str, Any]]:
    """
    Consulta o CNA/OAB pelo número de inscrição e UF.

    Estratégia (em ordem):
      1. Mock mode (OAB_MOCK_MODE != "") → retorna dado de teste
      2. Token V2 via 2captcha (TWOCAPTCHA_API_KEY configurado) — recomendado produção
      3. Token V3 headless (sem browser) — funciona em IPs com bom score
      4. Token V2 via Playwright + solver LLM visual — requer Xvfb/display

    Returns:
        Dict com dados do advogado ou None se não encontrado/falha
    """
    estado = estado.upper().strip()
    numero = numero.strip()

    if estado not in ESTADOS_OAB:
        logger.warning(f"UF inválida: {estado!r}")
        return None

    # ── Mock mode ───────────────────────────────────────────────────────────
    if os.environ.get("OAB_MOCK_MODE"):
        logger.info(f"OAB mock mode: {estado}/{numero}")
        return _get_mock(estado, numero)

    logger.info(f"OAB: buscando {estado}/{numero}…")

    # ── Opção 1: 2captcha (melhor para produção sem display) ────────────────
    v2_token = await _get_token_2captcha()
    if v2_token:
        result = await _call_cna_api(estado, numero, v2_token, token_type="v2")
        if result is not None:
            logger.info(f"OAB via 2captcha: {result.get('nome')!r}")
            return result

    # ── Opção 2: V3 headless (sem browser, IP com bom score) ───────────────
    v3_token = await _get_v3_token_headless(estado, numero)
    if v3_token:
        result = await _call_cna_api(estado, numero, v3_token, token_type="v3")
        if result is not None:
            logger.info(f"OAB via V3: {result.get('nome')!r}")
            return result

    # ── Opção 3: Playwright + LLM (requer Xvfb) ────────────────────────────
    v2_token = await _get_v2_token_playwright(estado, numero)
    if v2_token:
        result = await _call_cna_api(estado, numero, v2_token, token_type="v2")
        if result is not None:
            logger.info(f"OAB via Playwright: {result.get('nome')!r}")
            return result

    logger.error(f"OAB: todas as estratégias falharam para {estado}/{numero}")
    return None


async def _buscar_processos_datajud(estado: str, numero: str) -> List[Dict[str, Any]]:
    """
    Busca processos no DataJud por número de OAB.
    Consulta todos os tribunais em paralelo.
    """
    DATAJUD_URL = settings.DATAJUD_BASE_URL.rstrip("/")
    DATAJUD_KEY = settings.DATAJUD_API_KEY.strip()
    if DATAJUD_KEY and not DATAJUD_KEY.lower().startswith("apikey "):
        DATAJUD_KEY = f"APIKey {DATAJUD_KEY}"

    # Tribunais priorizados pelo estado + nacionais
    estado_tribunal = {
        "MS": ["api_publica_tjms"], "SP": ["api_publica_tjsp"],
        "RJ": ["api_publica_tjrj"], "MG": ["api_publica_tjmg"],
        "RS": ["api_publica_tjrs"], "PR": ["api_publica_tjpr"],
        "BA": ["api_publica_tjba"], "CE": ["api_publica_tjce"],
        "GO": ["api_publica_tjgo"], "PE": ["api_publica_tjpe"],
        "SC": ["api_publica_tjsc"], "MT": ["api_publica_tjmt"],
        "MA": ["api_publica_tjma"], "PA": ["api_publica_tjpa"],
        "ES": ["api_publica_tjes"], "RN": ["api_publica_tjrn"],
        "PB": ["api_publica_tjpb"], "PI": ["api_publica_tjpi"],
        "SE": ["api_publica_tjse"], "AL": ["api_publica_tjal"],
        "RO": ["api_publica_tjro"], "AM": ["api_publica_tjam"],
        "AC": ["api_publica_tjac"], "TO": ["api_publica_tjto"],
        "AP": ["api_publica_tjap"], "RR": ["api_publica_tjrr"],
        "DF": ["api_publica_tjdft"],
    }
    tribunais_extras = [
        "api_publica_trf1", "api_publica_trf2", "api_publica_trf3",
        "api_publica_trf4", "api_publica_trf5",
        "api_publica_tst", "api_publica_stj",
    ]
    tribunais = estado_tribunal.get(estado.upper(), []) + tribunais_extras

    async def buscar_tribunal(tribunal: str) -> List[Dict]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{DATAJUD_URL}/{tribunal}/_search",
                    headers={
                        "Authorization": DATAJUD_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "size": 100,
                        "query": {
                            "query_string": {
                                "query": f"*{numero}*",
                            }
                        },
                        "_source": ["numeroProcesso", "tribunal", "classe",
                                    "assuntos", "dataAjuizamento", "orgaoJulgador",
                                    "valorCausa", "dataHoraUltimaAtualizacao",
                                    "partes"],
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 429:
                        logger.warning("DataJud OAB %s: limite de requisições (429)", tribunal)
                        await asyncio.sleep(2)
                        return []
                    if not resp.ok:
                        # Registra o status para diferenciar autenticação/endpoint de ausência de processos.
                        logger.warning("DataJud OAB %s retornou HTTP %s", tribunal, resp.status)
                        return []
                    data = await resp.json(content_type=None)
                    resultados = []
                    for hit in data.get("hits", {}).get("hits", []):
                        f = hit["_source"]

                        # Mapear partes (polo ativo e passivo)
                        partes_raw = f.get("partes") or []
                        partes = []
                        for parte in partes_raw:
                            advs = []
                            for adv in (parte.get("advogados") or []):
                                advs.append({
                                    "nome": adv.get("nome", ""),
                                    "cpf":  adv.get("cpf", ""),
                                })
                            doc_principal = parte.get("documento") or ""
                            partes.append({
                                "nome":      parte.get("nome", ""),
                                "polo":      parte.get("polo", ""),
                                "tipoPolo":  parte.get("tipoPolo", ""),
                                "cpf":       doc_principal if len(doc_principal) == 11 else "",
                                "cnpj":      doc_principal if len(doc_principal) == 14 else "",
                                "telefone":  parte.get("telefone", ""),
                                "email":     parte.get("email", ""),
                                "advogados": advs,
                            })

                        # Última movimentação
                        ultima_mov = f.get("dataHoraUltimaAtualizacao", "")
                        if ultima_mov:
                            ultima_mov = ultima_mov[:10]  # yyyy-mm-dd

                        resultados.append({
                            "numero":              f.get("numeroProcesso", ""),
                            "tribunal":            f.get("tribunal", tribunal.replace("api_publica_", "").upper()),
                            "classe":              f.get("classe", {}).get("nome", "") if isinstance(f.get("classe"), dict) else "",
                            "assunto":             ", ".join([a.get("nome","") for a in (f.get("assuntos") or [])]),
                            "data":                f.get("dataAjuizamento", ""),
                            "orgao":               f.get("orgaoJulgador", {}).get("nome", "") if isinstance(f.get("orgaoJulgador"), dict) else "",
                            "valor":               f.get("valorCausa", ""),
                            "dataUltimaMovimentacao": ultima_mov,
                            "partes":              partes,
                        })
                    return resultados
        except Exception as exc:
            logger.warning("Erro na consulta DataJud OAB %s: %s", tribunal, exc)
            return []

    tarefas = [buscar_tribunal(t) for t in tribunais]
    resultados_raw = await asyncio.gather(*tarefas, return_exceptions=True)

    unicos: Dict[str, Dict] = {}
    for lista in resultados_raw:
        if isinstance(lista, list):
            for p in lista:
                if p.get("numero") and p["numero"] not in unicos:
                    unicos[p["numero"]] = p

    logger.info(f"DataJud OAB {estado}/{numero}: {len(unicos)} processos encontrados")
    return list(unicos.values())


async def buscar_por_oab(estado: str, numero: str) -> Dict[str, Any]:
    """
    Busca completa por número OAB.
    - Advogado: via CNA/OAB (se reCAPTCHA resolver) ou None
    - Processos: via DataJud (todos os tribunais, sem reCAPTCHA)

    Returns:
        {
            "advogado": {...} | None,
            "processos": [...],
            "estado": "MS",
            "numero_oab": "3616",
        }
    """
    # Buscar advogado e processos em paralelo
    advogado_task  = consultar_advogado_oab(estado, numero)
    processos_task = _buscar_processos_datajud(estado, numero)

    advogado, processos = await asyncio.gather(advogado_task, processos_task)

    return {
        "advogado":   advogado,
        "processos":  processos,
        "estado":     estado.upper(),
        "numero_oab": numero,
    }
