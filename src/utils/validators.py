"""
Validadores e normalizadores para buscas de processos.
"""
import re
import string
from typing import Optional, Tuple


# Regex patterns
PROCESSO_FORMATADO_RE = re.compile(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$")
PROCESSO_RAW_RE = re.compile(r"^(\d{20})$")
CPF_FORMATADO_RE = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")
CPF_RAW_RE = re.compile(r"^\d{11}$")
CNPJ_FORMATADO_RE = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")
CNPJ_RAW_RE = re.compile(r"^\d{14}$")
OAB_RE = re.compile(
    r"^(?:oab)[\s\/\-]*(?:se|cc)?\s*([A-Z]{2})"
    r"[\s]*[nº°\.]*\s*([0-9][A-Za-z0-9/]*\d*)$",
    re.IGNORECASE
)


def limpar_caracteres(texto: str) -> str:
    """Remove caracteres especiais, mantendo apenas alfanuméricos."""
    return re.sub(r"[^\w\s]", "", texto).strip()


def formatar_processo(numero: str) -> str:
    """
    Formata número de processo para o padrão CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO
    Aceita formato formatado ou cru (20 dígitos).
    """
    numero = numero.strip()

    # Já está no formato CNJ
    match = PROCESSO_FORMATADO_RE.match(numero)
    if match:
        return numero

    # Formato cru (20 dígitos)
    match = PROCESSO_RAW_RE.match(numero)
    if match:
        raw = numero
        return f"{raw[0:7]}-{raw[7:9]}.{raw[9:13]}.{raw[13]}.{raw[14:16]}.{raw[16:20]}"

    # Tentar extrair números
    digitos = re.sub(r"\D", "", numero)
    if len(digitos) == 20:
        return f"{digitos[0:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13]}.{digitos[14:16]}.{digitos[16:20]}"
    if len(digitos) > 20:
        # Pode ter dígito verificador, pegar primeiros 20
        digitos = digitos[:20]
        return f"{digitos[0:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13]}.{digitos[14:16]}.{digitos[16:20]}"

    return numero


def numero_processo_cru(numero: str) -> str:
    """Retorna o número do processo sem formatação (20 dígitos)."""
    digitos = re.sub(r"\D", "", numero)
    if len(digitos) >= 20:
        return digitos[:20]
    return digitos


def validar_e_normalizar_cpf(cpf: str) -> Optional[str]:
    """
    Valida e normaliza CPF. Retorna CPF formatado ou None se inválido.
    """
    cpf = cpf.strip()
    digitos = re.sub(r"\D", "", cpf)

    if len(digitos) != 11:
        return None

    # Validação do dígito verificador
    def calc_dv(base: str, pesos: list) -> str:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    if digitos == "00000000000":
        return None

    dv1 = calc_dv(digitos[:9], list(range(10, 1, -1)))
    dv2 = calc_dv(digitos[:9] + dv1, list(range(11, 1, -1)))

    if digitos[9] != dv1 or digitos[10] != dv2:
        return None

    return f"{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:11]}"


def validar_e_normalizar_cnpj(cnpj: str) -> Optional[str]:
    """
    Valida e normaliza CNPJ. Retorna CNPJ formatado ou None se inválido.
    """
    cnpj = cnpj.strip()
    digitos = re.sub(r"\D", "", cnpj)

    if len(digitos) != 14:
        return None

    if digitos == "00000000000000":
        return None

    def calc_dv(base: str, pesos: list) -> str:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    dv1 = calc_dv(digitos[:12], pesos1)
    dv2 = calc_dv(digitos[:12] + dv1, pesos2)

    if digitos[12] != dv1 or digitos[13] != dv2:
        return None

    return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:14]}"


def parsear_oab(oab_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Faz parse do número OAB. Retorna (estado, numero) ou (None, None).
    Exemplos aceitos:
    - OAB/SP 123456
    - OAB/MS 3616
    - OAB/SP123456
    - OAB-SP 123456
    - OAB/SP n° 123456
    """
    oab_str = oab_str.strip()

    # Tentar regex
    match = OAB_RE.match(oab_str)
    if match:
        estado = match.group(1).upper()
        numero = match.group(2)
        return estado, numero

    # Tentar formato simplificado: OABXX12345
    simplificado = re.match(r"^(?:oab)[\s\/\-]*([A-Z]{2})\s*(\d[\dA-Za-z/]*)$", oab_str, re.IGNORECASE)
    if simplificado:
        return simplificado.group(1).upper(), simplificado.group(2)

    return None, None


def detectar_tipo_busca(termo: str) -> str:
    """
    Detecta automaticamente o tipo de busca baseado no termo.
    Retorna: 'numero_processo', 'cpf', 'cnpj', 'oab', 'nome'
    """
    termo = termo.strip()
    digitos = re.sub(r"\D", "", termo)

    # Verificar número de processo
    if len(digitos) >= 20:
        return "numero_processo"

    # Verificar OAB
    if re.match(r"^(?:oab)", termo, re.IGNORECASE):
        return "oab"

    # Verificar CPF
    if len(digitos) == 11:
        if validar_e_normalizar_cpf(termo):
            return "cpf"

    # Verificar CNPJ
    if len(digitos) == 14:
        if validar_e_normalizar_cnpj(termo):
            return "cnpj"

    # Verificar formato CPF com pontuação
    if CPF_FORMATADO_RE.match(termo):
        return "cpf"

    # Verificar formato CNPJ com pontuação
    if CNPJ_FORMATADO_RE.match(termo):
        return "cnpj"

    # Padrão: busca por nome
    return "nome"


def extrair_informacoes_tribunal_numero_processo(numero: str) -> dict:
    """
    Extrai informações do tribunal a partir do número do processo CNJ.
    Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
    J = segmento (8=Estadual, 4=Federal, 5=Trabalho, etc.)
    TR = código do tribunal
    """
    numero_limpo = re.sub(r"\D", "", numero)

    if len(numero_limpo) < 20:
        return {"segmento": None, "tribunal": None, "comarca": None}

    segmento = int(numero_limpo[13])
    codigo_tribunal = int(numero_limpo[14:16])
    comarca = numero_limpo[16:20]

    # Mapeamento de segmentos
    segmentos = {
        8: "Estadual",
        4: "Federal",
        5: "Trabalho",
        6: "Eleitoral",
        7: "Militar",
    }

    # Mapeamento de tribunais por segmento
    tribunais_map = {
        8: {  # Estadual
            1: "TJAC", 2: "TJAL", 3: "TJAP", 4: "TJAM", 5: "TJBA",
            6: "TJCE", 7: "TJDF", 8: "TJES", 9: "TJGO", 10: "TJMA",
            11: "TJMT", 12: "TJMS", 13: "TJMG", 14: "TJPA", 15: "TJPB",
            16: "TJPR", 17: "TJPE", 18: "TJPI", 19: "TJRJ", 20: "TJRN",
            21: "TJRS", 22: "TJRO", 23: "TJRR", 24: "TJSC", 25: "TJSP",
            26: "TJSE", 27: "TJTO",
        },
        4: {  # Federal
            1: "TRF1", 2: "TRF2", 3: "TRF3", 4: "TRF4", 5: "TRF5",
            6: "TRF6",
        },
        5: {  # Trabalho
            1: "TRT1", 2: "TRT2", 3: "TRT3", 4: "TRT4", 5: "TRT5",
            6: "TRT6", 7: "TRT7", 8: "TRT8", 9: "TRT9", 10: "TRT10",
            11: "TRT11", 12: "TRT12", 13: "TRT13", 14: "TRT14", 15: "TRT15",
            16: "TRT16", 17: "TRT17", 18: "TRT18", 19: "TRT19", 20: "TRT20",
            21: "TRT21", 22: "TRT22", 23: "TRT23", 24: "TRT24",
        },
    }

    segmento_nome = segmentos.get(segmento, "Desconhecido")
    tribunal = tribunais_map.get(segmento, {}).get(codigo_tribunal, "Desconhecido")

    return {
        "segmento": segmento_nome,
        "segmento_codigo": segmento,
        "tribunal": tribunal,
        "tribunal_codigo": codigo_tribunal,
        "comarca": comarca,
    }


def mascarar_cpf_cnpj(valor: str) -> str:
    """Mascara CPF ou CNPJ para exibição parcial."""
    if re.match(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$", valor):
        return "***.***.***-" + valor[-2:]
    elif re.match(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$", valor):
        return "**.***.***/****-" + valor[-2:]
    return valor
