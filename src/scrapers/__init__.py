from .datajud_scraper import buscar_por_numero_datajud, TRIBUNAL_ENDPOINTS
from .tribunal_scraper import buscar_por_documento_tribunais, TRIBUNAL_CONFIG
from .oab_scraper import buscar_por_oab, consultar_advogado_oab

__all__ = [
    "buscar_por_numero_datajud",
    "TRIBUNAL_ENDPOINTS",
    "buscar_por_documento_tribunais",
    "TRIBUNAL_CONFIG",
    "buscar_por_oab",
    "consultar_advogado_oab",
]
