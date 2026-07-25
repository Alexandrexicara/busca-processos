# Sistema de Busca de Processos Judiciais

Sistema completo de consulta processual nacional, similar ao Escavador, com API REST para integração com sistemas externos (como bots Telegram).

## Funcionalidades

| Funcionalidade | Descrição | Fonte de Dados |
|---|---|---|
| Busca por Número do Processo | Consulta em todos os tribunais do Brasil | DataJud (CNJ) |
| Busca por CPF | Consulta nos tribunais estaduais e federais | Scraping dos portais |
| Busca por CNPJ | Consulta nos tribunais estaduais e federais | Scraping dos portais |
| Busca por Nome | Consulta nos tribunais estaduais e federais | Scraping dos portais |
| Busca por OAB | Consulta de advogado e processos vinculados | OAB + Tribunais |

## Cobertura de Tribunais

O sistema cobre **todos os tribunais do Brasil**, incluindo:

- **27 Tribunais de Justiça estaduais** (TJSP, TJRJ, TJMG, TJBA, TJRS, etc.)
- **6 Tribunais Regionais Federais** (TRF1 a TRF6)
- **24 Tribunais Regionais do Trabalho** (TRT1 a TRT24)
- **27 Tribunais Regionais Eleitorais** (TRE1 a TRE27)
- **Tribunais Superiores** (STJ, STF, TST, TSE, STM)

## Instalação

### Requisitos

- Python 3.10+
- pip

### Passo a passo

```bash
# 1. Clonar ou baixar o projeto
cd busca-processos

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com sua API Key

# 4. Executar o servidor
python main.py
```

### Com Docker

```bash
# 1. Copiar e editar o .env
cp .env.example .env

# 2. Construir e executar
docker-compose up --build
```

O servidor será iniciado em `http://localhost:8000`.

## API Key

A autenticação é feita via header `X-API-Key`. Por padrão, a chave é:

```
busca-processos-dev-key-2024
```

Para alterar, edite a variável `API_KEY` no arquivo `.env`.

## Endpoints da API

### Autenticação

Todas as requisições devem incluir o header:

```http
X-API-Key: sua-chave-api-secreta-aqui
```

### Busca Automática (recomendado)

Detecta automaticamente o tipo de busca pelo termo informado.

```bash
POST /api/v1/buscar
Content-Type: application/json
X-API-Key: sua-chave

{
    "termo": "0001234-56.2024.8.26.0100",
    "tipo": null,
    "tribunais": []
}
```

Tipos de busca aceitos no campo `termo`:
- **Número do processo**: `0001234-56.2024.8.26.0100`
- **CPF**: `123.456.789-00` ou `12345678900`
- **CNPJ**: `12.345.678/0001-99` ou `12345678000199`
- **Nome**: `João da Silva`
- **OAB**: `OAB/MS 3616` ou `OAB/SP 123456`

### Endpoints Específicos

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/v1/buscar/processo?numero=...` | Buscar por número do processo |
| POST | `/api/v1/buscar/cpf?cpf=...` | Buscar por CPF |
| POST | `/api/v1/buscar/cnpj?cnpj=...` | Buscar por CNPJ |
| POST | `/api/v1/buscar/nome?nome=...` | Buscar por nome |
| POST | `/api/v1/buscar/oab` | Buscar por OAB (JSON body) |
| GET | `/api/v1/tribunais` | Listar tribunais suportados |
| GET | `/api/v1/info` | Informações do sistema |
| GET | `/health` | Health check |

### Exemplo de Resposta

```json
{
    "sucesso": true,
    "mensagem": "Busca concluída. 2 processo(s) encontrado(s) em 1 tribunal(is).",
    "dados": {
        "tipo_busca": "numero_processo",
        "termo_busca": "0001234-56.2024.8.26.0100",
        "total_resultados": 2,
        "tribunais_consultados": ["TJSP"],
        "tempo_consulta": 3.45,
        "processos": [
            {
                "numero_processo": "0001234-56.2024.8.26.0100",
                "classe_nome": "Procedimento Comum Cível",
                "assunto_nome": "Indenização por Dano Moral",
                "tribunal": "TJSP",
                "data_ajuizamento": "2024-03-15T08:32:00.000Z",
                "partes": [
                    {
                        "nome": "João da Silva",
                        "cpf_cnpj": "***.***.***-00",
                        "tipo": "autor"
                    }
                ],
                "movimentos": [
                    {
                        "codigo": "26",
                        "nome": "Distribuição",
                        "data": "2024-03-15T08:32:00.000Z"
                    }
                ],
                "fonte": "DataJud"
            }
        ],
        "erros": null
    },
    "erros": null,
    "timestamp": "2024-07-24T23:55:07.234690"
}
```

## Exemplos de Integração

### Python

```python
import requests

API_URL = "http://seu-servidor:8000"
API_KEY = "sua-chave-api-secreta-aqui"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Busca por número de processo
response = requests.post(
    f"{API_URL}/api/v1/buscar",
    json={"termo": "0001234-56.2024.8.26.0100"},
    headers=headers
)
print(response.json())

# Busca por OAB
response = requests.post(
    f"{API_URL}/api/v1/buscar/oab",
    json={"estado": "MS", "numero": "3616"},
    headers=headers
)
print(response.json())
```

### cURL

```bash
# Busca automática
curl -X POST "http://seu-servidor:8000/api/v1/buscar" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sua-chave-api-secreta-aqui" \
  -d '{"termo": "0001234-56.2024.8.26.0100"}'

# Busca por OAB
curl -X POST "http://seu-servidor:8000/api/v1/buscar/oab" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sua-chave-api-secreta-aqui" \
  -d '{"estado": "MS", "numero": "3616"}'
```

## Documentação Interativa

Após iniciar o servidor, acesse:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Deploy em Produção

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `API_KEY` | Chave de autenticação | `busca-processos-dev-key-2024` |
| `HOST` | Host do servidor | `0.0.0.0` |
| `PORT` | Porta do servidor | `8000` |
| `RATE_LIMIT_PER_MINUTE` | Limite de requisições/minuto | `60` |
| `DATAJUD_API_KEY` | Chave da API DataJud | Pública |
| `REQUEST_TIMEOUT` | Timeout em segundos | `30` |
| `SCRAPE_TIMEOUT` | Timeout scraping em segundos | `60` |

### Recomendações para Produção

1. Use um **process manager** (PM2, Supervisor, systemd)
2. Configure um **proxy reverso** (Nginx, Caddy)
3. Use **HTTPS** com certificado SSL
4. Configure **rate limiting** no proxy reverso
5. Monitore logs e use **log rotation**

### Exemplo com Nginx + Gunicorn

```bash
# Instalar gunicorn
pip install gunicorn

# Executar com gunicorn
gunicorn src.api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## Estrutura do Projeto

```
busca-processos/
├── main.py                    # Ponto de entrada
├── requirements.txt           # Dependências Python
├── Dockerfile                 # Docker
├── docker-compose.yml         # Docker Compose
├── .env.example               # Template de variáveis
├── config/
│   └── settings.py            # Configurações
├── src/
│   ├── api.py                 # API REST (FastAPI)
│   ├── busca_engine.py        # Engine de busca unificada
│   ├── models/
│   │   └── processo.py        # Modelos Pydantic
│   ├── scrapers/
│   │   ├── datajud_scraper.py # API DataJud (CNJ)
│   │   ├── tribunal_scraper.py# Scrapers de tribunais
│   │   └── oab_scraper.py     # Scraper OAB
│   └── utils/
│       └── validators.py      # Validadores e normalizadores
└── docs/
    └── API.md                 # Documentação da API
```

## Limitações e Considerações

1. **DataJud**: A API pública do CNJ tem latência de 15-30 dias e não suporta busca por CPF/CNPJ. Usada principalmente para busca por número de processo.

2. **Scraping**: O scraping dos portais dos tribunais pode ser afetado por mudanças na estrutura HTML dos sites, CAPTCHAs e rate limiting dos tribunais.

3. **Segredo de Justiça**: Processos em segredo de justiça não serão retornados em nenhuma consulta.

4. **LGPD**: CPFs e CNPJs são mascarados nas respostas para proteção de dados pessoais.

## Licença

Proprietária. Uso autorizado apenas pelo titular da licença.
