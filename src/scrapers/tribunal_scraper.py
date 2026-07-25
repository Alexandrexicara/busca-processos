"""
Scrapers para portais de tribunais estaduais e federais.
Busca por CPF, CNPJ, nome e OAB nos portais dos tribunais.
"""
import asyncio
import logging
import re
import time
from typing import List, Dict, Any, Optional
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Configuração dos tribunais com seus portais e métodos de busca
# ============================================================================

TRIBUNAL_CONFIG = {
    "TJSP": {
        "sistema": "esaj",
        "portal": "https://esaj.tjsp.jus.br",
        "consulta_processo": "https://esaj.tjsp.jus.br/cpopg/search.do",
        "consulta_1grau": "https://esaj.tjsp.jus.br/cpo/pg/search.do",
        "consulta_2grau": "https://esaj.tjsp.jus.br/cposg/search.do",
    },
    "TJRJ": {
        "sistema": "projudi",
        "portal": "https://www.tjrj.jus.br",
        "consulta_1grau": "https://www4.tjrj.jus.br/Consultas/SESAO/ConsultaProcesso?tipoPesquisa=NP",
        "consulta_2grau": "https://www4.tjrj.jus.br/Consultas/SESAO/ConsultaProcesso?tipoPesquisa=NP",
    },
    "TJMG": {
        "sistema": "esaj",
        "portal": "https://www.tjmg.jus.br",
        "consulta": "https://api.tjmg.jus.br/api/v1/processo/",
    },
    "TJDF": {
        "sistema": "pje",
        "portal": "https://pje.tjdf.jus.br",
        "consulta": "https://pje.tjdf.jus.br/consulta-processual/consulta-publica/processo",
    },
    "TJRS": {
        "sistema": "projudi",
        "portal": "https://www.tjrs.jus.br",
        "consulta_1grau": "https://www.tjrs.jus.br/site/consulta_processo/1_grau",
        "consulta_2grau": "https://www.tjrs.jus.br/site/consulta_processo/2_grau",
    },
    "TJPR": {
        "sistema": "projudi",
        "portal": "https://www.tjpr.jus.br",
        "consulta": "https://www.tjpr.jus.br/cpopg/open.do",
    },
    "TJPE": {
        "sistema": "esaj",
        "portal": "https://www.tjpe.jus.br",
        "consulta": "https://www.tjpe.jus.br/cpopg/open.do",
    },
    "TJCE": {
        "sistema": "esaj",
        "portal": "https://www.tjce.jus.br",
        "consulta": "https://www.tjce.jus.br/cpopg/open.do",
    },
    "TJGO": {
        "sistema": "projudi",
        "portal": "https://www.tjgo.jus.br",
        "consulta": "https://www.tjgo.jus.br/cpopg/open.do",
    },
    "TJSC": {
        "sistema": "projudi",
        "portal": "https://www.tjsc.jus.br",
        "consulta": "https://www.tjsc.jus.br/cpopg/open.do",
    },
    "TJBA": {
        "sistema": "projudi",
        "portal": "https://www.tjba.jus.br",
        "consulta": "https://www.tjba.jus.br/cpopg/open.do",
    },
    "TJES": {
        "sistema": "esaj",
        "portal": "https://www.tjes.jus.br",
        "consulta": "https://www.tjes.jus.br/cpopg/open.do",
    },
    "TJAL": {
        "sistema": "esaj",
        "portal": "https://www.tjal.jus.br",
        "consulta": "https://www.tjal.jus.br/cpopg/open.do",
    },
    "TJRN": {
        "sistema": "esaj",
        "portal": "https://www.tjrn.jus.br",
        "consulta": "https://www.tjrn.jus.br/cpopg/open.do",
    },
    "TJMS": {
        "sistema": "esaj",
        "portal": "https://www.tjms.jus.br",
        "consulta": "https://www.tjms.jus.br/cpopg/open.do",
    },
    "TJMT": {
        "sistema": "projudi",
        "portal": "https://www.tjmt.jus.br",
        "consulta": "https://www.tjmt.jus.br/cpopg/open.do",
    },
    "TJRO": {
        "sistema": "projudi",
        "portal": "https://www.tjro.jus.br",
        "consulta": "https://www.tjro.jus.br/cpopg/open.do",
    },
    "TJPA": {
        "sistema": "projudi",
        "portal": "https://www.tjpa.jus.br",
        "consulta": "https://www.tjpa.jus.br/cpopg/open.do",
    },
    "TJAM": {
        "sistema": "projudi",
        "portal": "https://www.tjam.jus.br",
        "consulta": "https://www.tjam.jus.br/cpopg/open.do",
    },
    "TRF1": {
        "sistema": "pje",
        "portal": "https://www1.trf1.jus.br",
        "consulta": "https://www1.trf1.jus.br/consulta-processual/processo.htm",
    },
    "TRF2": {
        "sistema": "pje",
        "portal": "https://www.trf2.jus.br",
        "consulta": "https://www.trf2.jus.br/consulta-processual/processo.htm",
    },
    "TRF3": {
        "sistema": "pje",
        "portal": "https://www.trf3.jus.br",
        "consulta": "https://www.trf3.jus.br/consulta-processual/processo.htm",
    },
    "TRF4": {
        "sistema": "pje",
        "portal": "https://www.trf4.jus.br",
        "consulta": "https://www.trf4.jus.br/consulta-processual/processo.htm",
    },
    "TRF5": {
        "sistema": "pje",
        "portal": "https://www.trf5.jus.br",
        "consulta": "https://www.trf5.jus.br/consulta-processual/processo.htm",
    },
    "STJ": {
        "sistema": "saaj",
        "portal": "https://processo.stj.jus.br",
        "consulta": "https://processo.stj.jus.br/SCON/livre/visao.jsp",
    },
    "STF": {
        "sistema": "saaj",
        "portal": "https://portal.stf.jus.br",
        "consulta": "https://portal.stf.jus.br/processos/",
    },
}


def _clean_text(text: str) -> str:
    """Limpa texto extraído de HTML."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _parse_tjsp_esaj(html: str, tribunal: str) -> List[Dict[str, Any]]:
    """
    Parse resultado de busca do ESAJ (TJSP e similares).
    """
    processos = []
    soup = BeautifulSoup(html, "html.parser")

    # Buscar tabela de resultados
    tabela = soup.find("table", {"id": "tabela"}) or soup.find("table", class_="tabela")
    if not tabela:
        return processos

    linhas = tabela.find_all("tr")
    for linha in linhas[1:]:  # Pular cabeçalho
        cols = linha.find_all("td")
        if len(cols) >= 5:
            try:
                numero = _clean_text(cols[0].get_text())
                classe = _clean_text(cols[1].get_text())
                assunto = _clean_text(cols[2].get_text())
                partes = _clean_text(cols[3].get_text())
                status = _clean_text(cols[4].get_text())

                if numero:
                    processos.append({
                        "numero_processo": numero,
                        "classe": classe,
                        "assunto": assunto,
                        "tribunal": tribunal,
                        "partes_texto": partes,
                        "status": status,
                        "fonte": f"Scraper {tribunal}",
                    })
            except (IndexError, AttributeError):
                continue

    return processos


def _parse_projudi(html: str, tribunal: str) -> List[Dict[str, Any]]:
    """
    Parse resultado de busca do PROJUDI.
    """
    processos = []
    soup = BeautifulSoup(html, "html.parser")

    # Busca por divs de resultado
    resultados = soup.find_all("div", class_="resultado") or soup.find_all("tr", class_="linha")
    if not resultados:
        resultados = soup.find_all("table")
        if resultados:
            tabela = resultados[0]
            linhas = tabela.find_all("tr")
            for linha in linhas[1:]:
                cols = linha.find_all("td")
                if len(cols) >= 3:
                    processos.append({
                        "numero_processo": _clean_text(cols[0].get_text()),
                        "classe": _clean_text(cols[1].get_text()),
                        "assunto": _clean_text(cols[2].get_text()),
                        "tribunal": tribunal,
                        "fonte": f"Scraper {tribunal}",
                    })
            return processos

    for resultado in resultados:
        texts = resultado.get_text(separator=" ", strip=True)
        if texts:
            processos.append({
                "numero_processo": texts[:25],
                "tribunal": tribunal,
                "texto_completo": texts,
                "fonte": f"Scraper {tribunal}",
            })

    return processos


def _parse_stj(html: str, tribunal: str) -> List[Dict[str, Any]]:
    """Parse resultado de busca do STJ."""
    processos = []
    soup = BeautifulSoup(html, "html.parser")

    # STJ usa estrutura específica
    processos_encontrados = soup.find_all("div", class_="processo")
    if not processos_encontrados:
        return processos

    for proc in processos_encontrados:
        numero = proc.get("data-numero", "")
        classe = _clean_text(proc.find("span", class_="classe") or "")
        processos.append({
            "numero_processo": numero,
            "classe": classe,
            "tribunal": tribunal,
            "fonte": f"Scraper {tribunal}",
        })

    return processos


async def _consultar_tribunal_generic(
    session: aiohttp.ClientSession,
    tribunal: str,
    tipo_busca: str,
    termo: str,
    config: dict,
) -> List[Dict[str, Any]]:
    """Consulta genérica em um tribunal."""
    resultados = []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        sistema = config.get("sistema", "")

        if sistema == "esaj":
            # ESAJ - Consulta por número de processo
            url = config.get("consulta", "")
            if not url:
                url = config.get("consulta_processo", "")

            params = {
                "conversationId": "",
            }

            if tipo_busca == "numero_processo":
                params["cbPesquisa"] = "NUMPROC"
                params["numeroProcessoUnificado"] = termo
            elif tipo_busca == "nome":
                params["cbPesquisa"] = "NOMEPARTE"
                params["nomeParte"] = termo
            elif tipo_busca == "cpf":
                params["cbPesquisa"] = "DOCPARTE"
                params["cpfCnpj"] = termo
            elif tipo_busca == "cnpj":
                params["cbPesquisa"] = "DOCPARTE"
                params["cpfCnpj"] = termo
            elif tipo_busca == "oab":
                params["cbPesquisa"] = "NOMEADVOG"
                params["nomeAdvogado"] = termo

            try:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        resultados.extend(_parse_tjsp_esaj(html, tribunal))
            except Exception as e:
                logger.warning(f"Erro ESAJ {tribunal}: {e}")

        elif sistema == "projudi":
            url = config.get("consulta", "")
            if not url:
                return resultados

            params = {}
            if tipo_busca == "numero_processo":
                params["numeroProcesso"] = termo
            elif tipo_busca == "nome":
                params["nomeParte"] = termo
            elif tipo_busca in ("cpf", "cnpj"):
                params["cpfCnpj"] = termo

            try:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        resultados.extend(_parse_projudi(html, tribunal))
            except Exception as e:
                logger.warning(f"Erro PROJUDI {tribunal}: {e}")

        elif sistema == "pje":
            url = config.get("consulta", "")
            if not url:
                return resultados

            params = {}
            if tipo_busca == "numero_processo":
                params["numeroProcesso"] = termo

            try:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        resultados.extend(_parse_projudi(html, tribunal))
            except Exception as e:
                logger.warning(f"Erro PJe {tribunal}: {e}")

    except Exception as e:
        logger.error(f"Erro genérico ao consultar {tribunal}: {e}")

    return resultados


async def buscar_por_documento_tribunais(
    tipo_busca: str,
    termo: str,
    tribunais: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Busca em múltiplos tribunais por documento (CPF, CNPJ, nome, OAB).

    Args:
        tipo_busca: 'cpf', 'cnpj', 'nome', 'oab'
        termo: termo de busca
        tribunais: lista de siglas de tribunais

    Returns:
        Lista de processos encontrados
    """
    if tribunais is None:
        tribunais = list(TRIBUNAL_CONFIG.keys())

    resultados = []
    erros = []
    timeout = aiohttp.ClientTimeout(total=settings.SCRAPE_TIMEOUT)

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        semaphore = asyncio.Semaphore(3)

        async def consultar_com_sem(tribunal: str):
            async with semaphore:
                config = TRIBUNAL_CONFIG.get(tribunal, {})
                if not config:
                    return tribunal, [], f"Config não encontrada para {tribunal}"
                try:
                    result = await _consultar_tribunal_generic(
                        session, tribunal, tipo_busca, termo, config
                    )
                    return tribunal, result, None
                except Exception as e:
                    return tribunal, [], str(e)

        tasks = [consultar_com_sem(t) for t in tribunais]
        results = await asyncio.gather(*tasks)

        for tribunal, procs, error in results:
            if error:
                erros.append(f"{tribunal}: {error}")
            else:
                resultados.extend(procs)

    return resultados
