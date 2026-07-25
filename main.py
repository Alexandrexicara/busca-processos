"""
Ponto de entrada do Sistema de Busca de Processos.
"""
import uvicorn
from config.settings import settings
from src.api import app

if __name__ == "__main__":
    print("=" * 60)
    print("  SISTEMA DE BUSCA DE PROCESSOS JUDICIAIS")
    print("  Cobertura Nacional - Todos os Tribunais do Brasil")
    print("=" * 60)
    print(f"  Host: {settings.HOST}:{settings.PORT}")
    print(f"  API Key: {settings.API_KEY}")
    print(f"  Documentação: http://localhost:{settings.PORT}/docs")
    print("=" * 60)

    uvicorn.run(
        "src.api:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
