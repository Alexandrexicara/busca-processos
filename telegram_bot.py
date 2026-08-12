"""
Bot do Telegram para consulta de processos judiciais e OAB.

Comandos disponíveis:
  /start             — Mensagem de boas-vindas
  /ajuda             — Lista de comandos
  /oab <UF> <numero> — Busca advogado no CNA/OAB  (ex: /oab ms 3616)
  /processo <numero> — Busca processo por número CNJ
  /busca <termo>     — Busca genérica (CPF, CNPJ, nome, número)

Variáveis de ambiente:
  TELEGRAM_BOT_TOKEN   — Token do bot (@BotFather)
  API_BASE_URL         — URL da API FastAPI (padrão: http://localhost:8000)
  API_KEY              — Chave de API (padrão: busca-processos-dev-key-2024)
  OAB_MOCK_MODE        — se definido, API responde com dados de teste
"""

import logging
import os
import sys

import aiohttp
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────────────────────── Config ─────────────────────────────────────────

BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_BASE    = os.environ.get("API_BASE_URL", "http://localhost:8000")
API_KEY     = os.environ.get("API_KEY", "busca-processos-dev-key-2024")

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}

# ──────────────────────────── Helpers ────────────────────────────────────────

def _escape(text: str) -> str:
    """Escapa caracteres especiais para MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


async def _api_post(path: str, payload: dict, timeout: int = 120) -> dict:
    url = f"{API_BASE}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                return await resp.json(content_type=None)
    except aiohttp.ClientConnectorError:
        return {"sucesso": False, "mensagem": "API indisponível — servidor não está rodando."}
    except Exception as exc:
        return {"sucesso": False, "mensagem": f"Erro de conexão: {exc}"}


def _fmt_advogado(adv: dict) -> str:
    if not adv:
        return "❌ Advogado não encontrado na base do CNA/OAB."
    lines = [
        f"👤 *{_escape(adv.get('nome', 'N/D'))}*",
        f"📋 OAB/{_escape(adv.get('uf', '??'))} {_escape(str(adv.get('oab', '')))}",
        f"✅ Situação: {_escape(adv.get('situacao', 'N/D'))}",
        f"🏷 Tipo: {_escape(adv.get('tipo', 'Advogado'))}",
    ]
    if adv.get("subSeccional"):
        lines.append(f"📍 Sub-secção: {_escape(adv['subSeccional'])}")
    if adv.get("email"):
        lines.append(f"📧 {_escape(adv['email'])}")
    if adv.get("telefone"):
        lines.append(f"📞 {_escape(adv['telefone'])}")
    fonte = adv.get("fonte", "CNA/OAB")
    if "(mock)" in fonte.lower():
        lines.append(f"⚠️ _Dados de teste \\(ambiente dev\\)_")
    return "\n".join(lines)


def _fmt_processo(p: dict) -> str:
    numero  = _escape(p.get("numero", p.get("numeroProcesso", "—")))
    classe  = _escape(p.get("classe", p.get("classeProcessual", "—")))
    tribunal = _escape(p.get("tribunal", "—"))
    assunto = _escape(p.get("assunto", p.get("assuntosPrincipais", "—")))
    return f"📄 `{numero}` | {tribunal} | {classe} | {assunto}"


# ──────────────────────────── Handlers ───────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        "👋 Olá\\! Sou o *Bot de Busca de Processos*\\.\n\n"
        "Consulto o CNA/OAB e tribunais de todo o Brasil\\.\n\n"
        "Use /ajuda para ver os comandos disponíveis\\."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_ajuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        "📚 *Comandos disponíveis:*\n\n"
        "`/oab <UF> <número>` — Busca advogado no CNA/OAB\n"
        "   _Exemplo:_ `/oab ms 3616`\n\n"
        "`/processo <número>` — Busca processo por número CNJ\n"
        "   _Exemplo:_ `/processo 0001234-56.2024.8.26.0100`\n\n"
        "`/busca <termo>` — Busca genérica \\(CPF, CNPJ, nome, OAB\\)\n"
        "   _Exemplo:_ `/busca OAB/SP 123456`\n\n"
        "/ajuda — Exibe esta mensagem"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_oab(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /oab <UF> <numero>
    Exemplos:
      /oab ms 3616
      /oab SP 123456
    """
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Uso correto: `/oab <UF> <número>`\nExemplo: `/oab ms 3616`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    estado = args[0].upper()
    numero = args[1].strip()

    await update.message.reply_text(
        f"🔍 Buscando OAB/{estado} {numero}\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    data = await _api_post("/api/v1/buscar/oab", {"estado": estado, "numero": numero})

    if not data.get("sucesso"):
        erro = _escape(data.get("mensagem", "Erro desconhecido"))
        await update.message.reply_text(f"❌ {erro}", parse_mode=ParseMode.MARKDOWN_V2)
        return

    dados = data.get("dados", {})
    adv   = dados.get("advogado")

    reply = _fmt_advogado(adv)

    processos = dados.get("processos", [])
    if processos:
        reply += f"\n\n📦 *{len(processos)} processo\\(s\\) vinculado\\(s\\):*\n"
        for p in processos[:5]:
            reply += f"\n{_fmt_processo(p)}"
        if len(processos) > 5:
            reply += f"\n_\\+{len(processos) - 5} mais\\.\\.\\._"

    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_processo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /processo <número CNJ>
    """
    if not ctx.args:
        await update.message.reply_text(
            "⚠️ Uso: `/processo <número>`\nEx: `/processo 0001234-56.2024.8.26.0100`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    numero = " ".join(ctx.args).strip()
    await update.message.reply_text(
        f"🔍 Buscando processo `{_escape(numero)}`\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    data = await _api_post("/api/v1/buscar", {"termo": numero, "tipo": "numero_processo"})

    if not data.get("sucesso"):
        await update.message.reply_text(
            f"❌ {_escape(data.get('mensagem', 'Erro desconhecido'))}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    dados     = data.get("dados", {})
    processos = dados.get("processos", [])
    total     = dados.get("total_resultados", len(processos))

    if not processos:
        await update.message.reply_text(
            "🔍 Nenhum processo encontrado para esse número\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    reply = f"📦 *{total} processo\\(s\\) encontrado\\(s\\):*\n"
    for p in processos[:10]:
        reply += f"\n{_fmt_processo(p)}"
    if total > 10:
        reply += f"\n_\\+{total - 10} mais\\.\\.\\._"

    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_busca(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /busca <termo>  — detecta tipo automaticamente
    """
    if not ctx.args:
        await update.message.reply_text(
            "⚠️ Uso: `/busca <termo>`\nExemplo: `/busca OAB/MS 3616`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    termo = " ".join(ctx.args).strip()
    await update.message.reply_text(
        f"🔍 Buscando: `{_escape(termo)}`\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    data = await _api_post("/api/v1/buscar", {"termo": termo})

    if not data.get("sucesso"):
        await update.message.reply_text(
            f"❌ {_escape(data.get('mensagem', 'Erro'))}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    dados      = data.get("dados", {})
    tipo_busca = dados.get("tipo_busca", "")

    if tipo_busca == "oab":
        adv   = dados.get("advogado")
        reply = _fmt_advogado(adv)
        processos = dados.get("processos", [])
        if processos:
            reply += f"\n\n📦 *{len(processos)} processo\\(s\\):*\n"
            for p in processos[:5]:
                reply += f"\n{_fmt_processo(p)}"
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN_V2)
        return

    processos = dados.get("processos", [])
    total     = dados.get("total_resultados", len(processos))

    if not processos:
        await update.message.reply_text(
            f"🔍 Nenhum resultado encontrado para `{_escape(termo)}`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    reply = f"📦 *{total} resultado\\(s\\):*\n"
    for p in processos[:10]:
        reply += f"\n{_fmt_processo(p)}"
    if total > 10:
        reply += f"\n_\\+{total - 10} mais\\.\\.\\._"
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN_V2)


async def on_unknown(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ Comando não reconhecido\\. Use /ajuda para ver os comandos disponíveis\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ──────────────────────────── Main ───────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN não definido")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("ajuda",    cmd_ajuda))
    app.add_handler(CommandHandler("help",     cmd_ajuda))
    app.add_handler(CommandHandler("oab",      cmd_oab))
    app.add_handler(CommandHandler("processo", cmd_processo))
    app.add_handler(CommandHandler("busca",    cmd_busca))
    app.add_handler(MessageHandler(filters.COMMAND, on_unknown))

    logger.info("Bot iniciado, aguardando mensagens…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
