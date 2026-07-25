"""
Configurações do sistema de busca de processos.
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Settings:
    """Configurações globais do sistema."""

    # API Key para autenticação
    API_KEY: str = field(default_factory=lambda: os.getenv("API_KEY", "busca-processos-dev-key-2024"))

    # Host e porta
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    # DataJud API
    DATAJUD_BASE_URL: str = "https://api-publica.datajud.cnj.jus.br"
    DATAJUD_API_KEY: str = os.getenv("DATAJUD_API_KEY", "APIKey cDZHYzlZa0JadVREZDJCendFbXNpMDI=")

    # Timeouts
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    SCRAPE_TIMEOUT: int = int(os.getenv("SCRAPE_TIMEOUT", "60"))

    # Tribuinais suportados
    TRIBUNAIS: List[str] = field(default_factory=lambda: [
        "tjsp", "tjrj", "tjmg", "tjdf", "tjba", "tjrs", "tjpe",
        "tjce", "tjgo", "tjpr", "tjsc", "tjes", "tjal",
        "tjrn", "tjpb", "tjmt", "tjms", "tjpi", "tjse",
        "tjro", "tjap", "tjam", "tjac", "tjto", "tjma", "tjpa", "tjrr",
        "trf1", "trf2", "trf3", "trf4", "trf5", "trf6",
        "stj", "stf", "trt1", "trt2", "trt3", "trt4", "trt5",
        "trt6", "trt7", "trt8", "trt9", "trt10", "trt11",
        "trt12", "trt13", "trt14", "trt15", "trt16", "trt17",
        "trt18", "trt19", "trt20", "trt21", "trt22", "trt23", "trt24"
    ])

    # Tribunais para scraping direto (busca por CPF/CNPJ/OAB/nome)
    TRIBUNAIS_SCRAPING: List[dict] = field(default_factory=lambda: [
        {"sigla": "TJSP", "sistema": "esaj", "portal": "https://esaj.tjsp.jus.br/cpopg/"},
        {"sigla": "TJRJ", "sistema": "projudi", "portal": "https://www.tjrj.jus.br/web/consultas/processos"},
        {"sigla": "TJMG", "sistema": "esaj", "portal": "https://api.tjmg.jus.br/"},
        {"sigla": "TJDF", "sistema": "pje", "portal": "https://pje.tjdf.jus.br/"},
        {"sigla": "TJRS", "sistema": "projudi", "portal": "https://www.tjrs.jus.br/"},
        {"sigla": "TJPE", "sistema": "esaj", "portal": "https://www.tjpe.jus.br/"},
        {"sigla": "TJCE", "sistema": "esaj", "portal": "https://www.tjce.jus.br/"},
        {"sigla": "TJGO", "sistema": "projudi", "portal": "https://www.tjgo.jus.br/"},
        {"sigla": "TJPR", "sistema": "projudi", "portal": "https://www.tjpr.jus.br/"},
        {"sigla": "TJSC", "sistema": "projudi", "portal": "https://www.tjsc.jus.br/"},
        {"sigla": "TJBA", "sistema": "projudi", "portal": "https://www.tjba.jus.br/"},
        {"sigla": "TJES", "sistema": "esaj", "portal": "https://www.tjes.jus.br/"},
        {"sigla": "TJAL", "sistema": "esaj", "portal": "https://www.tjal.jus.br/"},
        {"sigla": "TJRN", "sistema": "esaj", "portal": "https://www.tjrn.jus.br/"},
        {"sigla": "TJMS", "sistema": "esaj", "portal": "https://www.tjms.jus.br/"},
        {"sigla": "TJMT", "sistema": "projudi", "portal": "https://www.tjmt.jus.br/"},
        {"sigla": "TJRO", "sistema": "projudi", "portal": "https://www.tjro.jus.br/"},
        {"sigla": "TJPA", "sistema": "projudi", "portal": "https://www.tjpa.jus.br/"},
        {"sigla": "TJAM", "sistema": "projudi", "portal": "https://www.tjam.jus.br/"},
        {"sigla": "TRF1", "sistema": "pje", "portal": "https://www1.trf1.jus.br/"},
        {"sigla": "TRF2", "sistema": "pje", "portal": "https://www.trf2.jus.br/"},
        {"sigla": "TRF3", "sistema": "pje", "portal": "https://www.trf3.jus.br/"},
        {"sigla": "TRF4", "sistema": "pje", "portal": "https://www.trf4.jus.br/"},
        {"sigla": "TRF5", "sistema": "pje", "portal": "https://www.trf5.jus.br/"},
    ])


# Instância global
settings = Settings()
