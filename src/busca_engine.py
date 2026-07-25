"""
Engine de Busca Unificada.
Orquestra todas as buscas (DataJud + Scrapers) e consolida resultados.
"""
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional

from config.settings import settings
from src.utils.validators import (
    formatar_processo, numero_processo_cru,
    validar_e_normalizar_cpf, validar_e_normalizar_cnpj,
    parsear_oab, detectar_tipo_busca,
    extrair_informacoes_tribunal_numero_processo,
    mascarar_cpf_cnpj,
)

logger = logging.getLogger(__name__)


class BuscaEngine:
    """
    Engine principal de busca que orquestra todos os scrapers.
    """

    async def buscar_por_numero_processo(
        self,
        numero: str,
        tribunais: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Busca por número de processo usando DataJud (CNJ).
        Cobre todos os tribunais do Brasil.
        """
        from src.scrapers.datajud_scraper import buscar_por_numero_datajud

        numero_formatado = formatar_processo(numero)
        numero_cru = numero_processo_cru(numero_formatado)

        if len(numero_cru) < 20:
            return {
                "sucesso": False,
                "erro": "Número do processo inválido. Deve conter 20 dígitos.",
            }

        resultados = await buscar_por_numero_datajud(
            numero_formatado, numero_cru, tribunais
        )

        return {
            "sucesso": True,
            "tipo_busca": "numero_processo",
            "numero_processo": numero_formatado,
            "total_resultados": len(resultados),
            "processos": resultados,
            "tribunais": list(set(p.get("tribunal", "") for p in resultados)),
        }

    async def buscar_por_cpf(
        self,
        cpf: str,
        tribunais: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Busca por CPF nos tribunais estaduais e federais.
        """
        from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

        cpf_formatado = validar_e_normalizar_cpf(cpf)
        if not cpf_formatado:
            return {"sucesso": False, "erro": "CPF inválido."}

        resultados = await buscar_por_documento_tribunais(
            tipo_busca="cpf",
            termo=cpf_formatado,
            tribunais=tribunais,
        )

        return {
            "sucesso": True,
            "tipo_busca": "cpf",
            "cpf": mascarar_cpf_cnpj(cpf_formatado),
            "total_resultados": len(resultados),
            "processos": resultados[:100],
            "tribunais": list(set(p.get("tribunal", "") for p in resultados)),
        }

    async def buscar_por_cnpj(
        self,
        cnpj: str,
        tribunais: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Busca por CNPJ nos tribunais estaduais e federais.
        """
        from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

        cnpj_formatado = validar_e_normalizar_cnpj(cnpj)
        if not cnpj_formatado:
            return {"sucesso": False, "erro": "CNPJ inválido."}

        resultados = await buscar_por_documento_tribunais(
            tipo_busca="cnpj",
            termo=cnpj_formatado,
            tribunais=tribunais,
        )

        return {
            "sucesso": True,
            "tipo_busca": "cnpj",
            "cnpj": mascarar_cpf_cnpj(cnpj_formatado),
            "total_resultados": len(resultados),
            "processos": resultados[:100],
            "tribunais": list(set(p.get("tribunal", "") for p in resultados)),
        }

    async def buscar_por_nome(
        self,
        nome: str,
        tribunais: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Busca por nome da parte nos tribunais.
        """
        from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

        if len(nome.strip()) < 3:
            return {"sucesso": False, "erro": "Nome muito curto."}

        resultados = await buscar_por_documento_tribunais(
            tipo_busca="nome",
            termo=nome.strip(),
            tribunais=tribunais,
        )

        return {
            "sucesso": True,
            "tipo_busca": "nome",
            "nome_busca": nome.strip(),
            "total_resultados": len(resultados),
            "processos": resultados[:100],
            "tribunais": list(set(p.get("tribunal", "") for p in resultados)),
        }

    async def buscar_por_oab(
        self,
        estado: str,
        numero: str,
    ) -> Dict[str, Any]:
        """
        Busca por OAB: informações do advogado + processos vinculados.
        """
        from src.scrapers.oab_scraper import buscar_por_oab

        resultado = await buscar_por_oab(estado.upper(), numero.strip())

        return {
            "sucesso": True,
            "tipo_busca": "oab",
            "estado": estado.upper(),
            "numero_oab": numero.strip(),
            "advogado": resultado.get("advogado"),
            "total_processos": len(resultado.get("processos", [])),
            "processos": resultado.get("processos", [])[:100],
        }

    async def busca_automatica(
        self,
        termo: str,
        tribunais: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Busca automática: detecta o tipo e executa a busca adequada.
        """
        tipo = detectar_tipo_busca(termo)

        inicio = time.time()

        if tipo == "numero_processo":
            resultado = await self.buscar_por_numero_processo(termo, tribunais)
        elif tipo == "cpf":
            resultado = await self.buscar_por_cpf(termo, tribunais)
        elif tipo == "cnpj":
            resultado = await self.buscar_por_cnpj(termo, tribunais)
        elif tipo == "oab":
            estado, numero = parsear_oab(termo)
            if estado and numero:
                resultado = await self.buscar_por_oab(estado, numero)
            else:
                resultado = {"sucesso": False, "erro": "Formato OAB inválido."}
        else:
            resultado = await self.buscar_por_nome(termo, tribunais)

        resultado["tempo_consulta"] = round(time.time() - inicio, 2)
        return resultado


# Instância global
engine = BuscaEngine()
