"""
Modelos de dados para o sistema de busca de processos.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TipoBusca(str, Enum):
    """Tipos de busca suportados."""
    NUMERO_PROCESSO = "numero_processo"
    CPF = "cpf"
    CNPJ = "cnpj"
    NOME = "nome"
    OAB = "oab"


class StatusProcesso(str, Enum):
    """Status do processo."""
    TRAMITACAO = "em_tramitacao"
    ARQUIVADO = "arquivado"
    ENCERRADO = "encerrado"
    PROVISORIO = "provisorio"
    DESCONHECIDO = "desconhecido"


class ParteProcesso(BaseModel):
    """Informações de uma parte no processo."""
    nome: str = ""
    cpf_cnpj: Optional[str] = None
    tipo: str = "parte"  # autor, réu, terceiro, etc.
    advogado: Optional[str] = None
    oab: Optional[str] = None


class MovimentacaoProcesso(BaseModel):
    """Movimentação processual."""
    codigo: Optional[str] = None
    nome: str = ""
    data: Optional[str] = None
    descricao: Optional[str] = None
    documento: Optional[str] = None


class ProcessoDataJud(BaseModel):
    """Processo retornado da API DataJud."""
    numero_processo: str = ""
    classe_codigo: Optional[str] = None
    classe_nome: Optional[str] = None
    assunto_codigo: Optional[str] = None
    assunto_nome: Optional[str] = None
    tribunal: str = ""
    data_ajuizamento: Optional[str] = None
    data_atualizacao: Optional[str] = None
    partes: List[Dict[str, Any]] = Field(default_factory=list)
    movimentos: List[Dict[str, Any]] = Field(default_factory=list)
    grau: Optional[str] = None
    orgao_julgador: Optional[str] = None
    valor_causa: Optional[float] = None
    fonte: str = "DataJud"


class ProcessoScraper(BaseModel):
    """Processo retornado do scraping de tribunais."""
    numero_processo: str = ""
    classe: Optional[str] = None
    assunto: Optional[str] = None
    tribunal: str = ""
    comarca: Optional[str] = None
    vara: Optional[str] = None
    status: str = StatusProcesso.DESCONHECIDO
    data_distribuicao: Optional[str] = None
    partes: List[ParteProcesso] = Field(default_factory=list)
    movimentacoes: List[MovimentacaoProcesso] = Field(default_factory=list)
    fonte: str = "Scraper"
    url_processo: Optional[str] = None


class ResultadoBusca(BaseModel):
    """Resultado consolidado de uma busca."""
    tipo_busca: TipoBusca
    termo_busca: str
    total_resultados: int = 0
    tribunais_consultados: List[str] = Field(default_factory=list)
    processos: List[Dict[str, Any]] = Field(default_factory=list)
    tempo_consulta: Optional[float] = None
    erros: List[str] = Field(default_factory=list)


class InformacoesOAB(BaseModel):
    """Informações do advogado pela OAB."""
    nome: str = ""
    oab: str = ""
    estado: str = ""
    numero: str = ""
    situacao: str = ""
    processos_vinculados: List[Dict[str, Any]] = Field(default_factory=list)


class ApiResponse(BaseModel):
    """Formato padrão de resposta da API."""
    sucesso: bool = True
    mensagem: str = ""
    dados: Optional[Dict[str, Any]] = None
    erros: Optional[List[str]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# Formato de número de processo CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO
# Exemplo: 0001234-56.2024.8.26.0100
PROCESSO_CNJ_REGEX = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
# Formato sem pontuação: 00012345620248260100
PROCESSO_CNP_REGEX = r"^\d{20}$"
# Formato OAB: OAB/XX n° XXXXX ou OAB-XX XXXXX
OAB_REGEX = r"^(?i)(oab)[\s\/\-]*([A-Z]{2})[\s]*[nº°\.]*\s*(\d+)$"
# CPF
CPF_REGEX = r"^\d{3}\.\d{3}\.\d{3}-\d{2}$"
CPF_SOLIDO_REGEX = r"^\d{11}$"
# CNPJ
CNPJ_REGEX = r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$"
CNPJ_SOLIDO_REGEX = r"^\d{14}$"
