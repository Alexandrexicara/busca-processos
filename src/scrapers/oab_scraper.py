"""
Scraper para consulta de advogados via OAB.
Busca informações do advogado pelo número OAB e estado.
"""
import asyncio
import logging
import re
from typing import Dict, Any, Optional, List

import aiohttp
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)

# URL da OAB Nacional para consulta
OAB_CONSULTA_URL = "https://cadastro.oab.org.br/listaadvogado.aspx"

# Mapeamento de estados para códigos OAB
ESTADOS_OAB = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco",
    "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}


def _parse_oab_result(html: str) -> Optional[Dict[str, Any]]:
    """
    Parse resultado da consulta OAB.
    Retorna informações do advogado.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Tentar encontrar tabela de resultados
    tabela = soup.find("table", id=re.compile(r"grdAdvogado|grid|tabela|result"))
    if not tabela:
        # Tentar encontrar div de resultado
        resultado = soup.find("div", class_=re.compile(r"result|advogado|dados"))
        if resultado:
            texts = resultado.get_text(separator="\n", strip=True)
            if texts:
                return {
                    "nome": texts[:100] if texts else "",
                    "texto_completo": texts,
                    "situacao": "Ativo",
                    "fonte": "OAB",
                }
        return None

    # Parse tabela
    linhas = tabela.find_all("tr")
    if len(linhas) < 2:
        return None

    # Cabeçalho
    cabecalho = linhas[0].find_all(["th", "td"])
    cols_result = linhas[1].find_all("td")

    if not cols_result:
        return None

    dados = {}
    for i, col in enumerate(cabecalho):
        header = _clean(col.get_text())
        if i < len(cols_result):
            dados[header.lower()] = _clean(cols_result[i].get_text())

    return {
        "nome": dados.get("nome", dados.get("advogado", "")),
        "oab": dados.get("oab", dados.get("inscrição", "")),
        "estado": dados.get("estado", dados.get("uf", "")),
        "situacao": dados.get("situação", "Ativo"),
        "fonte": "OAB",
    }


def _clean(text: str) -> str:
    """Limpa texto."""
    return re.sub(r"\s+", " ", text).strip()


async def consultar_advogado_oab(
    estado: str,
    numero: str,
) -> Optional[Dict[str, Any]]:
    """
    Consulta informações de um advogado pela OAB.

    Args:
        estado: Sigla do estado (ex: 'SP', 'MS', 'RJ')
        numero: Número da OAB (ex: '3616', '123456')

    Returns:
        Dict com informações do advogado ou None
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # Primeiro, acessar a página para obter session/cookies
            async with session.get(OAB_CONSULTA_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning(f"Erro ao acessar OAB: status {resp.status}")
                    return None

            # Montar dados do formulário
            estado_nome = ESTADOS_OAB.get(estado.upper(), estado)

            payload = {
                "NomeAdvogado": "",
                "NumeroInscricao": numero,
                "Seccional": estado.upper(),
            }

            async with session.post(OAB_CONSULTA_URL, data=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    return _parse_oab_result(html)
                else:
                    logger.warning(f"Erro ao consultar OAB: status {resp.status}")

    except asyncio.TimeoutError:
        logger.warning("Timeout ao consultar OAB")
    except Exception as e:
        logger.error(f"Erro ao consultar OAB: {e}")

    return None


async def buscar_por_oab(
    estado: str,
    numero: str,
) -> Dict[str, Any]:
    """
    Busca completa por OAB: informações do advogado + processos vinculados.

    Args:
        estado: Sigla do estado
        numero: Número OAB

    Returns:
        Dict com informações do advogado e processos
    """
    resultado = {
        "advogado": None,
        "processos": [],
        "estado": estado.upper(),
        "numero_oab": numero,
    }

    # Buscar informações do advogado
    advogado_info = await consultar_advogado_oab(estado, numero)
    resultado["advogado"] = advogado_info

    # Buscar processos vinculados nos tribunais
    if advogado_info:
        nome = advogado_info.get("nome", "")
        if nome:
            # Importar aqui para evitar circular import
            from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais
            processos = await buscar_por_documento_tribunais(
                tipo_busca="nome",
                termo=nome,
            )
            resultado["processos"] = processos

    return resultado
