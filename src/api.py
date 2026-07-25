"""
API REST principal do Sistema de Busca de Processos.
Framework: FastAPI
Autenticação: API Key
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from config.settings import settings
from src.models.processo import (
    TipoBusca, StatusProcesso, ResultadoBusca, ApiResponse
)
from src.utils.validators import (
    formatar_processo, numero_processo_cru,
    validar_e_normalizar_cpf, validar_e_normalizar_cnpj,
    parsear_oab, detectar_tipo_busca,
    extrair_informacoes_tribunal_numero_processo,
    mascarar_cpf_cnpj,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Inicializar FastAPI
app = FastAPI(
    title="Sistema de Busca de Processos",
    description="""
## API de Consulta Processual Nacional

Sistema completo para consulta de processos judiciais em todo o Brasil.
Similar ao Escavador, com busca por número de processo, CPF, CNPJ, nome da parte e OAB.

### Funcionalidades:
- **Busca por Número do Processo**: Consulta em todos os tribunais via DataJud (CNJ)
- **Busca por CPF**: Consulta nos tribunais estaduais e federais
- **Busca por CNPJ**: Consulta nos tribunais estaduais e federais
- **Busca por Nome**: Consulta nos tribunais estaduais e federais
- **Busca por OAB**: Consulta de advogado e processos vinculados
- **Cobertura Nacional**: Todos os tribunais do Brasil
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Autenticação por API Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verificar_api_key(x_api_key: str = Header(None)) -> str:
    """Verifica a API Key fornecida."""
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API Key não fornecida. Inclua o header X-API-Key na requisição."
        )
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=403,
            detail="API Key inválida."
        )
    return x_api_key


# ============================================================================
# Modelos de Request
# ============================================================================

class BuscaRequest(BaseModel):
    """Modelo para requisição de busca."""
    termo: str = Field(..., description="Termo de busca (número do processo, CPF, CNPJ, nome ou OAB)")
    tipo: Optional[str] = Field(None, description="Tipo de busca: numero_processo, cpf, cnpj, nome, oab. Se não informado, será detectado automaticamente.")
    tribunais: Optional[List[str]] = Field(None, description="Lista de tribunais para buscar. Se não informado, busca em todos.")


class BuscaOABRequest(BaseModel):
    """Modelo para requisição de busca por OAB."""
    estado: str = Field(..., description="Sigla do estado (ex: SP, MS, RJ)")
    numero: str = Field(..., description="Número da OAB (ex: 3616, 123456)")


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/", tags=["Geral"])
async def root():
    """Página inicial da API."""
    return {
        "nome": "Sistema de Busca de Processos",
        "versao": "1.0.0",
        "documentacao": "/docs",
        "status": "ativo",
    }


@app.get("/health", tags=["Geral"])
async def health_check():
    """Verificação de saúde do sistema."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/v1/buscar", response_model=ApiResponse, tags=["Busca"])
async def buscar_processos(
    request: BuscaRequest,
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Busca Processos

    Busca processos judiciais por número, CPF, CNPJ, nome ou OAB.

    ### Exemplos:
    - **Número**: `{"termo": "0001234-56.2024.8.26.0100"}`
    - **CPF**: `{"termo": "123.456.789-00"}`
    - **CNPJ**: `{"termo": "12.345.678/0001-99"}`
    - **Nome**: `{"termo": "João da Silva"}`
    - **OAB**: `{"termo": "OAB/SP 123456"}`
    """
    inicio = time.time()
    termo = request.termo.strip()

    # Detectar tipo de busca
    tipo_busca = request.tipo or detectar_tipo_busca(termo)
    tipo_busca = TipoBusca(tipo_busca)

    try:
        processos = []
        erros = []
        tribunais_consultados = []

        if tipo_busca == TipoBusca.NUMERO_PROCESSO:
            # Busca por número do processo via DataJud
            numero_formatado = formatar_processo(termo)
            numero_cru = numero_processo_cru(numero_formatado)

            if len(numero_cru) < 20:
                return ApiResponse(
                    sucesso=False,
                    mensagem="Número do processo inválido. Deve conter 20 dígitos.",
                    erros=["Formato inválido"],
                )

            info_tribunal = extrair_informacoes_tribunal_numero_processo(termo)
            logger.info(f"Busca por processo: {numero_formatado} | Tribunal: {info_tribunal.get('tribunal', 'Todos')}")

            # Buscar via DataJud (nacional)
            from src.scrapers.datajud_scraper import buscar_por_numero_datajud

            if request.tribunais:
                # Buscar apenas no tribunal informado
                processos = await buscar_por_numero_datajud(
                    numero_formatado, numero_cru, request.tribunais
                )
            else:
                # Buscar em todos os tribunais
                processos = await buscar_por_numero_datajud(numero_formatado, numero_cru)

            tribunais_consultados = list(set(p.get("tribunal", "") for p in processos))

        elif tipo_busca in (TipoBusca.CPF, TipoBusca.CNPJ):
            # Busca por CPF ou CNPJ nos tribunais
            if tipo_busca == TipoBusca.CPF:
                documento = validar_e_normalizar_cpf(termo)
                if not documento:
                    return ApiResponse(
                        sucesso=False,
                        mensagem="CPF inválido.",
                        erros=["Formato ou dígito verificador inválido"],
                    )
                masked = mascarar_cpf_cnpj(documento)
                logger.info(f"Busca por CPF: {masked}")
            else:
                documento = validar_e_normalizar_cnpj(termo)
                if not documento:
                    return ApiResponse(
                        sucesso=False,
                        mensagem="CNPJ inválido.",
                        erros=["Formato ou dígito verificador inválido"],
                    )
                masked = mascarar_cpf_cnpj(documento)
                logger.info(f"Busca por CNPJ: {masked}")

            from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

            processos = await buscar_por_documento_tribunais(
                tipo_busca=tipo_busca.value,
                termo=documento,
                tribunais=request.tribunais,
            )
            tribunais_consultados = list(set(p.get("tribunal", "") for p in processos))

        elif tipo_busca == TipoBusca.NOME:
            # Busca por nome nos tribunais
            if len(termo) < 3:
                return ApiResponse(
                    sucesso=False,
                    mensagem="Nome muito curto. Mínimo 3 caracteres.",
                    erros=["Nome muito curto"],
                )

            logger.info(f"Busca por nome: {termo}")

            from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

            processos = await buscar_por_documento_tribunais(
                tipo_busca="nome",
                termo=termo,
                tribunais=request.tribunais,
            )
            tribunais_consultados = list(set(p.get("tribunal", "") for p in processos))

        elif tipo_busca == TipoBusca.OAB:
            # Busca por OAB
            estado, numero_oab = parsear_oab(termo)
            if not estado or not numero_oab:
                return ApiResponse(
                    sucesso=False,
                    mensagem="Formato OAB inválido. Use: OAB/UF número (ex: OAB/SP 123456)",
                    erros=["Formato OAB não reconhecido"],
                )

            logger.info(f"Busca por OAB: {estado}/{numero_oab}")

            from src.scrapers.oab_scraper import buscar_por_oab

            resultado_oab = await buscar_por_oab(estado, numero_oab)
            if resultado_oab is None:
                resultado_oab = {}
            advogado = resultado_oab.get("advogado") or {}
            processos = resultado_oab.get("processos", [])
            tribunais_consultados = list(set(p.get("tribunal", "") for p in processos))

            return ApiResponse(
                sucesso=True,
                mensagem=f"Busca por OAB concluída. Advogado: {advogado.get('nome', 'Não encontrado') if advogado else 'Não encontrado'}",
                dados={
                    "tipo_busca": "oab",
                    "termo_busca": termo,
                    "advogado": advogado if advogado else None,
                    "estado": estado,
                    "numero_oab": numero_oab,
                    "total_resultados": len(processos),
                    "tribunais_consultados": tribunais_consultados,
                    "processos": processos[:100],  # Limitar a 100 resultados
                },
            )

        tempo_total = round(time.time() - inicio, 2)

        return ApiResponse(
            sucesso=True,
            mensagem=f"Busca concluída. {len(processos)} processo(s) encontrado(s) em {len(tribunais_consultados)} tribunal(is).",
            dados={
                "tipo_busca": tipo_busca.value,
                "termo_busca": termo if tipo_busca != TipoBusca.CPF and tipo_busca != TipoBusca.CNPJ else mascarar_cpf_cnpj(termo),
                "total_resultados": len(processos),
                "tribunais_consultados": tribunais_consultados,
                "tempo_consulta": tempo_total,
                "processos": processos[:100],  # Limitar a 100 resultados
                "erros": erros[:10] if erros else None,
            },
        )

    except Exception as e:
        logger.error(f"Erro na busca: {e}", exc_info=True)
        return ApiResponse(
            sucesso=False,
            mensagem="Erro interno ao realizar a busca.",
            erros=[str(e)],
        )


@app.post("/api/v1/buscar/processo", response_model=ApiResponse, tags=["Busca"])
async def buscar_por_processo(
    numero: str = Query(..., description="Número do processo"),
    tribunais: Optional[List[str]] = Query(None, description="Tribunais específicos"),
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Buscar por Número de Processo

    Busca um processo específico por seu número CNJ em todos os tribunais do Brasil.

    ### Parâmetros:
    - **numero**: Número do processo (formatado ou cru)
    - **tribunais**: Lista de tribunais para buscar (opcional)
    """
    numero_formatado = formatar_processo(numero)
    numero_cru = numero_processo_cru(numero_formatado)

    if len(numero_cru) < 20:
        raise HTTPException(status_code=400, detail="Número do processo inválido.")

    from src.scrapers.datajud_scraper import buscar_por_numero_datajud

    resultados = await buscar_por_numero_datajud(numero_formatado, numero_cru, tribunais)

    return ApiResponse(
        sucesso=True,
        mensagem=f"{len(resultados)} processo(s) encontrado(s).",
        dados={
            "tipo_busca": "numero_processo",
            "numero_processo": numero_formatado,
            "total_resultados": len(resultados),
            "processos": resultados,
        },
    )


@app.post("/api/v1/buscar/cpf", response_model=ApiResponse, tags=["Busca"])
async def buscar_por_cpf(
    cpf: str = Query(..., description="CPF a buscar"),
    tribunais: Optional[List[str]] = Query(None, description="Tribunais específicos"),
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Buscar por CPF

    Busca todos os processos vinculados a um CPF em tribunais do Brasil.

    ### Parâmetros:
    - **cpf**: CPF formatado (123.456.789-00) ou cru (12345678900)
    - **tribunais**: Lista de tribunais para buscar (opcional)
    """
    cpf_formatado = validar_e_normalizar_cpf(cpf)
    if not cpf_formatado:
        raise HTTPException(status_code=400, detail="CPF inválido.")

    from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

    resultados = await buscar_por_documento_tribunais(
        tipo_busca="cpf",
        termo=cpf_formatado,
        tribunais=tribunais,
    )

    return ApiResponse(
        sucesso=True,
        mensagem=f"{len(resultados)} processo(s) encontrado(s) para CPF {mascarar_cpf_cnpj(cpf_formatado)}.",
        dados={
            "tipo_busca": "cpf",
            "cpf": mascarar_cpf_cnpj(cpf_formatado),
            "total_resultados": len(resultados),
            "tribunais_consultados": list(set(p.get("tribunal", "") for p in resultados)),
            "processos": resultados[:100],
        },
    )


@app.post("/api/v1/buscar/cnpj", response_model=ApiResponse, tags=["Busca"])
async def buscar_por_cnpj(
    cnpj: str = Query(..., description="CNPJ a buscar"),
    tribunais: Optional[List[str]] = Query(None, description="Tribunais específicos"),
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Buscar por CNPJ

    Busca todos os processos vinculados a um CNPJ em tribunais do Brasil.

    ### Parâmetros:
    - **cnpj**: CNPJ formatado (12.345.678/0001-99) ou cru (12345678000199)
    - **tribunais**: Lista de tribunais para buscar (opcional)
    """
    cnpj_formatado = validar_e_normalizar_cnpj(cnpj)
    if not cnpj_formatado:
        raise HTTPException(status_code=400, detail="CNPJ inválido.")

    from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

    resultados = await buscar_por_documento_tribunais(
        tipo_busca="cnpj",
        termo=cnpj_formatado,
        tribunais=tribunais,
    )

    return ApiResponse(
        sucesso=True,
        mensagem=f"{len(resultados)} processo(s) encontrado(s) para CNPJ {mascarar_cpf_cnpj(cnpj_formatado)}.",
        dados={
            "tipo_busca": "cnpj",
            "cnpj": mascarar_cpf_cnpj(cnpj_formatado),
            "total_resultados": len(resultados),
            "tribunais_consultados": list(set(p.get("tribunal", "") for p in resultados)),
            "processos": resultados[:100],
        },
    )


@app.post("/api/v1/buscar/nome", response_model=ApiResponse, tags=["Busca"])
async def buscar_por_nome(
    nome: str = Query(..., description="Nome da parte a buscar"),
    tribunais: Optional[List[str]] = Query(None, description="Tribunais específicos"),
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Buscar por Nome

    Busca processos por nome da parte em tribunais do Brasil.

    ### Parâmetros:
    - **nome**: Nome completo ou parcial da parte
    - **tribunais**: Lista de tribunais para buscar (opcional)
    """
    if len(nome.strip()) < 3:
        raise HTTPException(status_code=400, detail="Nome muito curto. Mínimo 3 caracteres.")

    from src.scrapers.tribunal_scraper import buscar_por_documento_tribunais

    resultados = await buscar_por_documento_tribunais(
        tipo_busca="nome",
        termo=nome.strip(),
        tribunais=tribunais,
    )

    return ApiResponse(
        sucesso=True,
        mensagem=f"{len(resultados)} processo(s) encontrado(s) para o nome '{nome}'.",
        dados={
            "tipo_busca": "nome",
            "nome_busca": nome,
            "total_resultados": len(resultados),
            "tribunais_consultados": list(set(p.get("tribunal", "") for p in resultados)),
            "processos": resultados[:100],
        },
    )


@app.post("/api/v1/buscar/oab", response_model=ApiResponse, tags=["Busca"])
async def buscar_por_oab(
    request: BuscaOABRequest,
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Buscar por OAB

    Busca informações de advogado e processos vinculados pelo número OAB.

    ### Exemplo:
    ```json
    {
        "estado": "MS",
        "numero": "3616"
    }
    ```
    """
    from src.scrapers.oab_scraper import buscar_por_oab

    estado = request.estado.upper()
    numero = request.numero.strip()

    if len(estado) != 2:
        raise HTTPException(status_code=400, detail="Estado deve ter 2 caracteres.")

    if not numero.isdigit():
        raise HTTPException(status_code=400, detail="Número OAB deve conter apenas dígitos.")

    resultado = await buscar_por_oab(estado, numero)
    if resultado is None:
        resultado = {}

    return ApiResponse(
        sucesso=True,
        mensagem=f"Busca por OAB/{estado} {numero} concluída.",
        dados={
            "tipo_busca": "oab",
            "estado": estado,
            "numero_oab": numero,
            "advogado": resultado.get("advogado"),
            "total_processos": len(resultado.get("processos", [])),
            "processos": resultado.get("processos", [])[:100],
        },
    )


@app.get("/api/v1/tribunais", tags=["Informações"])
async def listar_tribunais(
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Lista de Tribunais Suportados

    Retorna a lista de todos os tribunais suportados pelo sistema.
    """
    from src.scrapers.datajud_scraper import TRIBUNAL_ENDPOINTS
    from src.scrapers.tribunal_scraper import TRIBUNAL_CONFIG

    tribunais_datajud = list(TRIBUNAL_ENDPOINTS.keys())
    tribunais_scraper = list(TRIBUNAL_CONFIG.keys())

    return ApiResponse(
        sucesso=True,
        mensagem="Lista de tribunais suportados.",
        dados={
            "datajud": tribunais_datajud,
            "scraper": tribunais_scraper,
            "total_datajud": len(tribunais_datajud),
            "total_scraper": len(tribunais_scraper),
        },
    )


@app.get("/api/v1/info", tags=["Informações"])
async def info_sistema(
    api_key: str = Depends(verificar_api_key),
):
    """
    ## Informações do Sistema

    Retorna informações gerais sobre o sistema de busca.
    """
    return ApiResponse(
        sucesso=True,
        mensagem="Informações do sistema.",
        dados={
            "nome": "Sistema de Busca de Processos",
            "versao": "1.0.0",
            "fonte_dados": "DataJud (CNJ) + Scraping de Tribunais",
            "tipos_busca": ["numero_processo", "cpf", "cnpj", "nome", "oab"],
            "cobertura": "Nacional (todos os tribunais do Brasil)",
            "autenticacao": "API Key via header X-API-Key",
            "rate_limit": f"{settings.RATE_LIMIT_PER_MINUTE} requisições/minuto",
        },
    )


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handler para exceções HTTP."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            sucesso=False,
            mensagem=exc.detail,
            erros=[exc.detail],
        ).dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handler para exceções gerais."""
    logger.error(f"Erro não tratado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ApiResponse(
            sucesso=False,
            mensagem="Erro interno do servidor.",
            erros=[str(exc)],
        ).dict(),
    )
