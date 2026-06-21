import asyncio
import logging

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TELEGRAM_TOKEN, ADMIN_ID, DIGEST_INTERVAL_MIN, BREAKING_CHECK_MIN
from db import (
    init_db, is_paused, set_paused, cleanup_old,
    is_initialized, mark_initialized,
    add_user, remove_user, get_active_users, get_all_users, user_exists,
)
from aggregator import fetch_for_digest, fetch_breaking_only, fetch_and_mark_all_silent
from summarizer import create_digest, create_breaking_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp  = Dispatcher()
router = Router()
dp.include_router(router)


# ── Broadcast helper ─────────────────────────────────────────────────────────

async def broadcast(text: str):
    """Send message to all active users. Silently skips blocked/deactivated."""
    users = await get_active_users()
    for uid in users:
        try:
            await bot.send_message(
                uid, text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send to {uid}: {e}")


# ── Scheduled jobs ────────────────────────────────────────────────────────────

async def job_digest():
    if await is_paused():
        return
    try:
        articles = await fetch_for_digest()
        if not articles:
            logger.info("Digest: no new articles")
            return
        count = sum(len(v) for v in articles.values())
        logger.info(f"Digest: {count} articles → {len(await get_active_users())} users")
        digest = await create_digest(articles)
        if digest:
            await broadcast(digest)
    except Exception as e:
        logger.error(f"job_digest error: {e}")


async def job_breaking():
    if await is_paused():
        return
    try:
        breaking = await fetch_breaking_only()
        if not breaking:
            return
        logger.info(f"Breaking: {len(breaking)} articles")
        msg = await create_breaking_summary(breaking)
        if msg:
            await broadcast(msg)
    except Exception as e:
        logger.error(f"job_breaking error: {e}")


async def job_cleanup():
    await cleanup_old(days=5)
    logger.info("DB cleanup done")


# ── Access control ────────────────────────────────────────────────────────────

def is_admin(chat_id: int) -> bool:
    return chat_id == ADMIN_ID

async def is_authorized(chat_id: int) -> bool:
    return is_admin(chat_id) or await user_exists(chat_id)


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(msg: Message):
    uid   = msg.chat.id
    name  = msg.from_user.full_name or "Неизвестный"
    uname = msg.from_user.username or ""

    # Already a user
    if await is_authorized(uid):
        await msg.answer(
            "👋 Привет! Ты уже подключён к боту.\n\n"
            "/help — список команд",
        )
        return

    # Unknown person → notify admin
    await msg.answer(
        "👋 Привет!\n"
        "У тебя пока нет доступа. Запрос отправлен администратору.\n"
        "Подожди немного 🙏"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить",  callback_data=f"approve:{uid}:{name}")
    kb.button(text="❌ Отклонить", callback_data=f"reject:{uid}:{name}")
    kb.adjust(2)

    uname_str = f"@{uname}" if uname else "без юзернейма"
    await bot.send_message(
        ADMIN_ID,
        f"🔔 <b>Запрос доступа</b>\n\n"
        f"👤 {name} ({uname_str})\n"
        f"🆔 <code>{uid}</code>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


# ── Approve / Reject callbacks ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Нет доступа")
        return

    _, uid_str, *name_parts = call.data.split(":")
    uid  = int(uid_str)
    name = ":".join(name_parts)  # name might have colons

    await add_user(uid, name)
    await call.message.edit_text(
        call.message.text + f"\n\n✅ <b>Одобрен</b>", parse_mode="HTML"
    )
    await bot.send_message(
        uid,
        "✅ Доступ одобрен! Добро пожаловать.\n\n"
        "Ты будешь получать дайджест каждые 7 минут.\n"
        "/help — список команд",
    )
    await call.answer("Одобрено")


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Нет доступа")
        return

    _, uid_str, *_ = call.data.split(":")
    uid = int(uid_str)

    await call.message.edit_text(
        call.message.text + "\n\n❌ <b>Отклонён</b>", parse_mode="HTML"
    )
    await bot.send_message(uid, "❌ В доступе отказано.")
    await call.answer("Отклонено")


# ── User commands ─────────────────────────────────────────────────────────────

@router.message(Command("digest"))
async def cmd_digest(msg: Message):
    if not await is_authorized(msg.chat.id): return
    await msg.answer("🔄 Собираю дайджест...")
    await job_digest()


@router.message(Command("breaking"))
async def cmd_breaking(msg: Message):
    if not await is_authorized(msg.chat.id): return
    await msg.answer("🔄 Проверяю срочные...")
    await job_breaking()


@router.message(Command("help"))
async def cmd_help(msg: Message):
    if not await is_authorized(msg.chat.id): return
    admin_section = ""
    if is_admin(msg.chat.id):
        admin_section = (
            "\n\n👑 <b>Админ:</b>\n"
            "/users — список пользователей\n"
            "/removeuser <code>ID</code> — удалить\n"
            "/pause 2h — пауза для всех\n"
            "/resume — продолжить\n"
            "/status — статус бота"
        )
    await msg.answer(
        "📋 <b>Команды:</b>\n\n"
        "/digest — дайджест прямо сейчас\n"
        "/breaking — проверить срочные новости"
        + admin_section,
        parse_mode="HTML",
    )


# ── Admin commands ────────────────────────────────────────────────────────────

@router.message(Command("users"))
async def cmd_users(msg: Message):
    if not is_admin(msg.chat.id): return
    users = await get_all_users()
    if not users:
        await msg.answer("Пользователей нет")
        return

    lines = ["👥 <b>Пользователи:</b>\n"]
    for u in users:
        status = "✅" if u["is_active"] else "❌"
        uname  = f"@{u['username']}" if u["username"] else ""
        lines.append(
            f"{status} {u['name']} {uname}\n"
            f"   <code>{u['chat_id']}</code> · {u['added_at'][:10]}"
        )
    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("removeuser"))
async def cmd_removeuser(msg: Message):
    if not is_admin(msg.chat.id): return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Использование: /removeuser <code>chat_id</code>", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        await remove_user(uid)
        await msg.answer(f"✅ Пользователь <code>{uid}</code> удалён", parse_mode="HTML")
        await bot.send_message(uid, "⛔ Твой доступ был отозван.")
    except (ValueError, Exception) as e:
        await msg.answer(f"Ошибка: {e}")


@router.message(Command("pause"))
async def cmd_pause(msg: Message):
    if not is_admin(msg.chat.id): return
    parts = msg.text.split()
    minutes = 60
    if len(parts) > 1:
        arg = parts[1].lower()
        try:
            if arg.endswith("h"):   minutes = int(arg[:-1]) * 60
            elif arg.endswith("m"): minutes = int(arg[:-1])
            else:                   minutes = int(arg)
        except ValueError:
            pass
    await set_paused(minutes)
    h, m = divmod(minutes, 60)
    label = f"{h}ч {m}м" if h else f"{m}м"
    await msg.answer(f"⏸ Пауза на {label} (для всех пользователей)")


@router.message(Command("resume"))
async def cmd_resume(msg: Message):
    if not is_admin(msg.chat.id): return
    await set_paused(0)
    await msg.answer("▶️ Бот возобновлён")


@router.message(Command("status"))
async def cmd_status(msg: Message):
    if not is_admin(msg.chat.id): return
    paused  = await is_paused()
    users   = await get_active_users()
    status  = "⏸ На паузе" if paused else "✅ Активен"
    await msg.answer(
        f"{status}\n"
        f"👥 Пользователей: {len(users)}\n"
        f"📋 Дайджест: каждые {DIGEST_INTERVAL_MIN} мин\n"
        f"🚨 Breaking: каждые {BREAKING_CHECK_MIN} мин",
        parse_mode="HTML",
    )


# ── Startup ───────────────────────────────────────────────────────────────────

async def main():
    await init_db()

    # Ensure admin is always in the users table
    from db import add_user as _add
    await _add(ADMIN_ID, "Admin")

    if not await is_initialized():
        logger.info("First run — marking existing articles as seen")
        n = await fetch_and_mark_all_silent()
        await mark_initialized()
        logger.info(f"Marked {n} articles as seen")
        try:
            await bot.send_message(
                ADMIN_ID,
                "🤖 <b>Новостной бот запущен!</b>\n\n"
                f"📋 Дайджест каждые {DIGEST_INTERVAL_MIN} мин\n"
                f"🚨 Breaking каждые {BREAKING_CHECK_MIN} мин\n\n"
                "Первый дайджест придёт через несколько минут.\n"
                "/help — команды  |  /users — список юзеров",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not notify admin on first run: {e}")
    else:
        try:
            await bot.send_message(ADMIN_ID, "♻️ Бот перезапущен")
        except Exception as e:
            logger.warning(f"Could not notify admin on restart: {e}")

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(job_digest,  "interval", minutes=DIGEST_INTERVAL_MIN, id="digest")
    scheduler.add_job(job_breaking,"interval", minutes=BREAKING_CHECK_MIN,  id="breaking")
    scheduler.add_job(job_cleanup, "cron",     hour=4, minute=0,            id="cleanup")
    scheduler.start()

    logger.info("Bot started — entering manual poll loop")
    # dp.start_polling() crashes on Railway (SIGTERM handler kills loop after 31s)
    # Manual loop is stable
    await _raw_poll(bot, dp)


async def _raw_poll(bot: Bot, dp: Dispatcher):
    offset = None
    # Skip old updates on startup
    try:
        updates = await bot.get_updates(timeout=0)
        if updates:
            offset = updates[-1].update_id + 1
    except Exception:
        pass

    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=25)
            for update in updates:
                await dp.feed_update(bot=bot, update=update)
            if updates:
                offset = updates[-1].update_id + 1
        except Exception as e:
            logger.error(f"Poll error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
