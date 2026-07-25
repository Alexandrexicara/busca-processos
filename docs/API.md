# Documentação da API de Busca de Processos

Esta documentação descreve como utilizar a API REST do Sistema de Busca de Processos, um sistema similar ao Escavador que permite consultas a tribunais de todo o Brasil.

## Autenticação

Todas as requisições para a API devem incluir o cabeçalho `X-API-Key` com a chave de autenticação fornecida.

**Exemplo:**
```http
X-API-Key: sua-chave-api-secreta-aqui
```

## Endpoints

### 1. Busca Automática

Detecta automaticamente o tipo de busca (Número, CPF, CNPJ, Nome ou OAB) e consulta os tribunais adequados.

**POST** `/api/v1/buscar`

**Body (JSON):**
```json
{
  "termo": "0001234-56.2024.8.26.0100",
  "tipo": null,
  "tribunais": []
}
```

**Parâmetros:**
* `termo` (string, obrigatório): O termo de busca.
* `tipo` (string, opcional): Pode ser `numero_processo`, `cpf`, `cnpj`, `nome` ou `oab`. Se omitido, o sistema tenta adivinhar.
* `tribunais` (array de strings, opcional): Lista de tribunais para restringir a busca. Ex: `["TJSP", "TRF1"]`.

---

### 2. Busca por Número de Processo

Consulta específica por número CNJ na base do DataJud (CNJ).

**POST** `/api/v1/buscar/processo?numero=0001234-56.2024.8.26.0100`

**Parâmetros de Query:**
* `numero` (string, obrigatório): Número do processo (formatado ou cru).
* `tribunais` (array de strings, opcional): Lista de tribunais para restringir a busca.

---

### 3. Busca por CPF

Consulta processos vinculados a um CPF nos tribunais estaduais e federais.

**POST** `/api/v1/buscar/cpf?cpf=123.456.789-00`

**Parâmetros de Query:**
* `cpf` (string, obrigatório): CPF formatado ou cru.
* `tribunais` (array de strings, opcional): Lista de tribunais.

---

### 4. Busca por CNPJ

Consulta processos vinculados a um CNPJ nos tribunais estaduais e federais.

**POST** `/api/v1/buscar/cnpj?cnpj=12.345.678/0001-99`

**Parâmetros de Query:**
* `cnpj` (string, obrigatório): CNPJ formatado ou cru.
* `tribunais` (array de strings, opcional): Lista de tribunais.

---

### 5. Busca por Nome

Consulta processos pelo nome da parte.

**POST** `/api/v1/buscar/nome?nome=João da Silva`

**Parâmetros de Query:**
* `nome` (string, obrigatório): Nome da parte.
* `tribunais` (array de strings, opcional): Lista de tribunais.

---

### 6. Busca por OAB

Consulta informações do advogado e seus processos vinculados.

**POST** `/api/v1/buscar/oab`

**Body (JSON):**
```json
{
  "estado": "MS",
  "numero": "3616"
}
```

**Parâmetros:**
* `estado` (string, obrigatório): Sigla do estado (ex: SP, MS, RJ).
* `numero` (string, obrigatório): Número da OAB (apenas números).

## Exemplos de Integração (Python)

```python
import requests

API_URL = "http://seu-servidor:8000"
API_KEY = "sua-chave-api-secreta-aqui"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Exemplo 1: Busca por número de processo
payload = {"termo": "0001234-56.2024.8.26.0100"}
response = requests.post(f"{API_URL}/api/v1/buscar", json=payload, headers=headers)
print(response.json())

# Exemplo 2: Busca por OAB
payload_oab = {"estado": "MS", "numero": "3616"}
response_oab = requests.post(f"{API_URL}/api/v1/buscar/oab", json=payload_oab, headers=headers)
print(response_oab.json())
```
