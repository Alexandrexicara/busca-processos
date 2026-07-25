"""
Scraper da API Pública do DataJud (CNJ).
Usa a API oficial do Conselho Nacional de Justiça para busca por número de processo.
Cobre todos os tribunais do Brasil.
"""
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)

# Mapeamento de tribunais para endpoints do DataJud
TRIBUNAL_ENDPOINTS = {
    "tjsp": "api_publica_tjsp",
    "tjrj": "api_publica_tjrj",
    "tjmg": "api_publica_tjmg",
    "tjdf": "api_publica_tjdft",
    "tjba": "api_publica_tjba",
    "tjrs": "api_publica_tjrs",
    "tjpe": "api_publica_tjpe",
    "tjce": "api_publica_tjce",
    "tjgo": "api_publica_tjgo",
    "tjpr": "api_publica_tjpr",
    "tjsc": "api_publica_tjsc",
    "tjes": "api_publica_tjes",
    "tjal": "api_publica_tjal",
    "tjrn": "api_publica_tjrn",
    "tjpb": "api_publica_tjpb",
    "tjmt": "api_publica_tjmt",
    "tjms": "api_publica_tjms",
    "tjpi": "api_publica_tjpi",
    "tjse": "api_publica_tjse",
    "tjro": "api_publica_tjro",
    "tjap": "api_publica_tjap",
    "tjam": "api_publica_tjam",
    "tjac": "api_publica_tjac",
    "tjto": "api_publica_tjto",
    "tjma": "api_publica_tjma",
    "tjpa": "api_publica_tjpa",
    "tjrr": "api_publica_tjrr",
    "trf1": "api_publica_trf1",
    "trf2": "api_publica_trf2",
    "trf3": "api_publica_trf3",
    "trf4": "api_publica_trf4",
    "trf5": "api_publica_trf5",
    "trf6": "api_publica_trf6",
    "stj": "api_publica_stj",
    "stf": "api_publica_stf",
    "tst": "api_publica_tst",
    "tse": "api_publica_tse",
    "stm": "api_publica_stm",
}

# Tribunais do trabalho
for i in range(1, 25):
    key = f"trt{i}"
    value = f"api_publica_trt{i}"
    TRIBUNAL_ENDPOINTS[key] = value

# Tribunais eleitorais
TRIBUNAL_ENDPOINTS["tre1"] = "api_publica_tre1"
TRIBUNAL_ENDPOINTS["tre2"] = "api_publica_tre2"
TRIBUNAL_ENDPOINTS["tre3"] = "api_publica_tre3"
TRIBUNAL_ENDPOINTS["tre4"] = "api_publica_tre4"
TRIBUNAL_ENDPOINTS["tre5"] = "api_publica_tre5"
TRIBUNAL_ENDPOINTS["tre6"] = "api_publica_tre6"
TRIBUNAL_ENDPOINTS["tre7"] = "api_publica_tre7"
TRIBUNAL_ENDPOINTS["tre8"] = "api_publica_tre8"
TRIBUNAL_ENDPOINTS["tre9"] = "api_publica_tre9"
TRIBUNAL_ENDPOINTS["tre10"] = "api_publica_tre10"
TRIBUNAL_ENDPOINTS["tre11"] = "api_publica_tre11"
TRIBUNAL_ENDPOINTS["tre12"] = "api_publica_tre12"
TRIBUNAL_ENDPOINTS["tre13"] = "api_publica_tre13"
TRIBUNAL_ENDPOINTS["tre14"] = "api_publica_tre14"
TRIBUNAL_ENDPOINTS["tre15"] = "api_publica_tre15"
TRIBUNAL_ENDPOINTS["tre16"] = "api_publica_tre16"
TRIBUNAL_ENDPOINTS["tre17"] = "api_publica_tre17"
TRIBUNAL_ENDPOINTS["tre18"] = "api_publica_tre18"
TRIBUNAL_ENDPOINTS["tre19"] = "api_publica_tre19"
TRIBUNAL_ENDPOINTS["tre20"] = "api_publica_tre20"
TRIBUNAL_ENDPOINTS["tre21"] = "api_publica_tre21"
TRIBUNAL_ENDPOINTS["tre22"] = "api_publica_tre22"
TRIBUNAL_ENDPOINTS["tre23"] = "api_publica_tre23"
TRIBUNAL_ENDPOINTS["tre24"] = "api_publica_tre24"
TRIBUNAL_ENDPOINTS["tre25"] = "api_publica_tre25"
TRIBUNAL_ENDPOINTS["tre26"] = "api_publica_tre26"
TRIBUNAL_ENDPOINTS["tre27"] = "api_publica_tre27"


def _parse_movimentacoes(raw_movimentos: list) -> List[Dict[str, Any]]:
    """Parse movimentações do formato DataJud."""
    movimentacoes = []
    for mov in raw_movimentos:
        movimentacoes.append({
            "codigo": str(mov.get("codigo", "")),
            "nome": mov.get("nome", ""),
            "data": mov.get("dataHora", ""),
            "descricao": mov.get("descricao", ""),
        })
    return movimentacoes


def _parse_partes(raw_partes: list) -> List[Dict[str, Any]]:
    """Parse partes do formato DataJud."""
    partes = []
    for parte in raw_partes:
        pessoa = parte.get("pessoa", {})
        partes.append({
            "nome": pessoa.get("nome", ""),
            "cpf_cnpj": pessoa.get("numeroDocumento", ""),
            "tipo": parte.get("tipo", "parte"),
            "advogado": None,
            "oab": None,
        })
    return partes


def _parse_documento_datajud(doc: dict, tribunal: str) -> Optional[Dict[str, Any]]:
    """Parse um documento retornado pelo DataJud."""
    source = doc.get("_source", doc)
    numero = source.get("numeroProcesso", "")
    if not numero:
        return None

    # Extrair classe
    classe = source.get("classe", {})
    classe_nome = ""
    classe_codigo = None
    if isinstance(classe, dict):
        classe_nome = classe.get("nome", "")
        classe_codigo = str(classe.get("codigo", ""))
    elif isinstance(classe, str):
        classe_nome = classe

    # Extrair assuntos
    assuntos = source.get("assuntos", [])
    assunto_nome = ""
    assunto_codigo = None
    if assuntos:
        if isinstance(assuntos, list) and len(assuntos) > 0:
            a = assuntos[0]
            if isinstance(a, dict):
                assunto_nome = a.get("nome", "")
                assunto_codigo = str(a.get("codigo", ""))
            else:
                assunto_nome = str(a)

    # Extrair partes
    partes_raw = source.get("partes", [])
    partes = _parse_partes(partes_raw)

    # Extrair movimentações
    movimentos_raw = source.get("movimentos", [])
    movimentos = _parse_movimentacoes(movimentos_raw)

    # Último movimento (data atualização)
    data_atualizacao = ""
    if movimentos:
        data_atualizacao = movimentos[-1].get("data", "")

    return {
        "numero_processo": numero,
        "classe_codigo": classe_codigo,
        "classe_nome": classe_nome,
        "assunto_codigo": assunto_codigo,
        "assunto_nome": assunto_nome,
        "tribunal": tribunal.upper(),
        "data_ajuizamento": source.get("dataAjuizamento", ""),
        "data_atualizacao": data_atualizacao or source.get("dataAtualizacao", ""),
        "partes": partes,
        "movimentos": movimentos,
        "grau": source.get("grau", ""),
        "orgao_julgador": source.get("orgaoJulgador", {}).get("nome", "") if isinstance(source.get("orgaoJulgador"), dict) else str(source.get("orgaoJulgador", "")),
        "valor_causa": source.get("valorCausa"),
        "fonte": "DataJud",
    }


async def _buscar_em_tribunal(
    session: aiohttp.ClientSession,
    numero_cru: str,
    tribunal: str,
) -> Optional[Dict[str, Any]]:
    """Busca um processo em um tribunal específico via DataJud."""
    endpoint = TRIBUNAL_ENDPOINTS.get(tribunal.lower())
    if not endpoint:
        return None

    url = f"{settings.DATAJUD_BASE_URL}/{endpoint}/_search"

    payload = {
        "query": {
            "match": {
                "numeroProcesso": numero_cru
            }
        },
        "size": 10
    }

    headers = {
        "Authorization": settings.DATAJUD_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                hits = data.get("hits", {}).get("hits", [])
                if hits:
                    doc = hits[0]
                    return _parse_documento_datajud(doc, tribunal)
            elif resp.status == 429:
                logger.warning(f"Rate limit atingido no tribunal {tribunal}")
                await asyncio.sleep(2)
            elif resp.status != 404:
                logger.warning(f"Erro {resp.status} no tribunal {tribunal}")
    except asyncio.TimeoutError:
        logger.warning(f"Timeout no tribunal {tribunal}")
    except Exception as e:
        logger.warning(f"Erro ao buscar em {tribunal}: {e}")

    return None


async def buscar_por_numero_datajud(
    numero_processo: str,
    numero_cru: str,
    tribunais: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Busca um processo por número em todos os tribunais via DataJud.

    Args:
        numero_processo: Número formatado (para referência)
        numero_cru: Número sem formatação (20 dígitos)
        tribunais: Lista de tribunais para buscar (None = todos)

    Returns:
        Lista de processos encontrados
    """
    if tribunais is None:
        tribunais = list(TRIBUNAL_ENDPOINTS.keys())

    resultados = []
    erros = []

    timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Limitar concorrência a 5 requisições simultâneas
        semaphore = asyncio.Semaphore(5)

        async def buscar_com_sem(tribunal: str):
            async with semaphore:
                return await _buscar_em_tribunal(session, numero_cru, tribunal)

        tasks = [buscar_com_sem(t) for t in tribunais]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for tribunal, result in zip(tribunais, results):
            if isinstance(result, Exception):
                erros.append(f"Erro em {tribunal}: {str(result)}")
            elif result is not None:
                resultados.append(result)

    return resultados
