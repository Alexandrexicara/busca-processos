"""
Consulta cadastro CNA/OAB e metadados processuais do DataJud.
A validação humana eventualmente exigida pelo portal CNA não é contornada.
OAB_MOCK_MODE ativa exclusivamente dados fictícios para desenvolvimento.
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
    Verifica o acesso ao portal CNA com Chromium/Playwright.
    Não tenta automatizar nem contornar o reCAPTCHA: quando o portal exige
    validação humana, a consulta é interrompida e registrada como indisponível.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright não está instalado na imagem de produção")
        return None

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = await browser.new_page()
                response = await page.goto(CNA_SITE, wait_until="domcontentloaded", timeout=30000)
                if response and response.status >= 400:
                    logger.warning("Portal CNA retornou HTTP %s", response.status)
                    return None
                await page.wait_for_timeout(1500)
                captcha_visible = await page.locator(
                    "iframe[src*='recaptcha'], iframe[title*='reCAPTCHA']"
                ).count()
                if captcha_visible:
                    logger.warning(
                        "Portal CNA exige reCAPTCHA. Playwright/Chromium está instalado, "
                        "mas a consulta automática foi interrompida para não contornar a proteção."
                    )
                    return None
                logger.info("Portal CNA acessível pelo Chromium; não foi emitido token de consulta.")
                return None
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning("Verificação do portal CNA com Playwright falhou: %s", exc)
        return None


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

    # O portal CNA pode exigir validação reCAPTCHA. Não usar serviços externos
    # nem tentativas automatizadas para contornar essa proteção.
    await _get_v2_token_playwright(estado, numero)

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

    # O XSD do CNJ define a inscrição como UF + 7 dígitos + sufixo de tipo.
    # Usar prefixo com wildcard final inclui o sufixo sem pesquisar outros campos.
    inscricao_prefixo = f"{estado.upper()}{numero.zfill(7)}"
    query_oab = f"partes.advogados.inscricao:{inscricao_prefixo}*"
    logger.info("DataJud OAB: consultando %s tribunais; inscrição iniciada por %s",
                len(tribunais), inscricao_prefixo)

    async def buscar_tribunal(tribunal: str) -> List[Dict]:
        # Sessão por chamada, com poucas tentativas e espera explícita para HTTP 429.
        timeout = aiohttp.ClientTimeout(total=12, connect=5, sock_read=8)
        for tentativa in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{DATAJUD_URL}/{tribunal}/_search",
                        headers={
                            "Authorization": DATAJUD_KEY,
                            "Content-Type": "application/json",
                        },
                        json={
                            "size": 25,
                            "query": {"query_string": {"query": query_oab}},
                            "_source": ["numeroProcesso", "tribunal", "classe",
                                        "assuntos", "dataAjuizamento", "orgaoJulgador",
                                        "valorCausa", "dataHoraUltimaAtualizacao",
                                        "partes"],
                        },
                    ) as resp:
                        if resp.status == 429:
                            espera = 2 ** (tentativa + 1)
                            logger.warning(
                                "DataJud OAB %s: limite 429; nova tentativa em %ss (%s/3)",
                                tribunal, espera, tentativa + 1
                            )
                            if tentativa < 2:
                                await asyncio.sleep(espera)
                                continue
                            return []
                        if not resp.ok:
                            if resp.status in (401, 403):
                                logger.error(
                                    "DataJud OAB %s: autenticação recusada (HTTP %s). "
                                    "A consulta não pode ser considerada concluída.",
                                    tribunal, resp.status
                                )
                            else:
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
                logger.warning("Erro na consulta DataJud OAB %s: %r", tribunal, exc)
                return []

    # Consulta poucos tribunais simultaneamente para reduzir o tempo total sem sobrecarregar o DataJud.
    sem = asyncio.Semaphore(3)

    async def buscar_limitado(tribunal: str):
        async with sem:
            return await buscar_tribunal(tribunal)

    tarefas = [buscar_limitado(t) for t in tribunais]
    resultados_raw = await asyncio.gather(*tarefas, return_exceptions=True)

    unicos: Dict[str, Dict] = {}
    for lista in resultados_raw:
        if isinstance(lista, list):
            for p in lista:
                if p.get("numero") and p["numero"] not in unicos:
                    unicos[p["numero"]] = p

    if unicos:
        logger.info("DataJud OAB %s/%s: %s processos encontrados", estado, numero, len(unicos))
    else:
        logger.warning(
            "DataJud OAB %s/%s: nenhum processo retornado. "
            "Verifique os avisos HTTP acima; HTTP 401/403 significa falha de autenticação, "
            "não confirmação de que o advogado não possui processos.",
            estado, numero
        )
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
