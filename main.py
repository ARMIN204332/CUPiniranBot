
import os
import sqlite3
import secrets
import logging

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = {
    7433705943,
    122351848,
    1183224377,
    5478649107,
}

REQUIRED_CHANNELS = [
    (
        "@MAN_O_2_NEWS",
        "https://t.me/MAN_O_2_NEWS",
        "📢 عضویت در کانال اول",
    ),
    (
        "@nabzegahan",
        "https://t.me/nabzegahan",
        "📢 عضویت در کانال دوم",
    ),
]

DB_NAME = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------- DATABASE ----------------

def db_connect():
    return sqlite3.connect(DB_NAME)


def init_db():
    with db_connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_key TEXT PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                source_chat_id INTEGER NOT NULL,
                source_message_id INTEGER NOT NULL,
                file_name TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def save_user(user_id):
    with db_connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,),
        )


def save_file(file_key, admin_id, chat_id, message_id, file_name):
    with db_connect() as db:
        db.execute("""
            INSERT INTO files (
                file_key, admin_id, source_chat_id,
                source_message_id, file_name
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            file_key,
            admin_id,
            chat_id,
            message_id,
            file_name,
        ))


def get_file(file_key):
    with db_connect() as db:
        return db.execute("""
            SELECT file_key, admin_id, source_chat_id,
                   source_message_id, file_name, active
            FROM files
            WHERE file_key = ?
        """, (file_key,)).fetchone()


def get_all_files():
    with db_connect() as db:
        return db.execute("""
            SELECT file_key, file_name, active
            FROM files
            ORDER BY created_at DESC
        """).fetchall()


# ---------------- HELPERS ----------------

def is_admin(user_id):
    return user_id in ADMIN_IDS


def get_file_name(message):
    if message.document:
        return message.document.file_name or "Document"
    if message.video:
        return message.video.file_name or "Video"
    if message.audio:
        return message.audio.file_name or "Audio"
    if message.photo:
        return "Photo"
    if message.animation:
        return "Animation"
    if message.voice:
        return "Voice"
    if message.video_note:
        return "Video note"
    if message.sticker:
        return "Sticker"
    return "Telegram media"


async def check_required_membership(bot, user_id):
    for channel, _, _ in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(
                chat_id=channel,
                user_id=user_id,
            )

            if member.status in ("left", "kicked"):
                logger.info(
                    "User %s is not a member of %s",
                    user_id,
                    channel,
                )
                return False

        except Exception:
            logger.exception(
                "Membership check failed: channel=%s user_id=%s",
                channel,
                user_id,
            )
            return False

    return True


def membership_keyboard(file_key):
    buttons = []

    for _, url, label in REQUIRED_CHANNELS:
        buttons.append([
            InlineKeyboardButton(label, url=url)
        ])

    buttons.append([
        InlineKeyboardButton(
            "✅ بررسی عضویت و دریافت فایل",
            callback_data=f"check:{file_key}",
        )
    ])

    return InlineKeyboardMarkup(buttons)


# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    save_user(user.id)

    # /start معمولی هیچ پیامی ارسال نمی‌کند
    if not context.args:
        return

    argument = context.args[0]

    if not argument.startswith("file_"):
        return

    file_key = argument.replace("file_", "", 1)
    file_data = get_file(file_key)

    if not file_data or not file_data[5]:
        await update.message.reply_text(
            "❌ این لینک معتبر نیست یا غیرفعال شده است."
        )
        return

    # ادمین‌ها بدون بررسی عضویت فایل را دریافت می‌کنند
    if is_admin(user.id):
        await send_file_to_user(
            context,
            user.id,
            file_data[2],
            file_data[3],
        )
        return

    await update.message.reply_text(
        "برای دریافت فایل، ابتدا عضو هر دو کانال زیر شو و بعد دکمه بررسی عضویت رو بزن:",
        reply_markup=membership_keyboard(file_key),
    )


# ---------------- SEND FILE ----------------

async def send_file_to_user(
    context,
    user_id,
    source_chat_id,
    source_message_id,
):
    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=source_chat_id,
            message_id=source_message_id,
        )
    except Exception:
        logger.exception("Could not send file to user %s", user_id)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ ارسال فایل با مشکل مواجه شد. لطفاً بعداً دوباره امتحان کن.",
            )
        except Exception:
            pass


# ---------------- MEMBERSHIP CALLBACK ----------------

async def check_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    file_key = query.data.split(":", 1)[1]

    file_data = get_file(file_key)

    if not file_data or not file_data[5]:
        await query.edit_message_text(
            "❌ این لینک معتبر نیست یا غیرفعال شده است."
        )
        return

    if not is_admin(user_id):
        is_member = await check_required_membership(
            context.bot,
            user_id,
        )

        if not is_member:
            await query.answer(
                "هنوز عضویت هر دو کانال تأیید نشده است.",
                show_alert=True,
            )
            return

    await query.edit_message_text(
        "✅ عضویت تأیید شد. فایل در حال ارسال است..."
    )

    await send_file_to_user(
        context,
        user_id,
        file_data[2],
        file_data[3],
    )


# ---------------- ADMIN UPLOAD ----------------

async def handle_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    # کاربران عادی کاملاً نادیده گرفته می‌شوند
    if not is_admin(user.id):
        return

    file_key = secrets.token_urlsafe(8)
    file_name = get_file_name(message)

    save_file(
        file_key,
        user.id,
        message.chat_id,
        message.message_id,
        file_name,
    )

    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=file_{file_key}"

    await message.reply_text(
        "✅ فایل با موفقیت ثبت شد.\n\n"
        f"📁 نام فایل: {file_name}\n"
        f"🔗 لینک اختصاصی:\n{link}"
    )


# ---------------- ADMIN STATS ----------------

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    with db_connect() as db:
        users_count = db.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        files_count = db.execute(
            "SELECT COUNT(*) FROM files"
        ).fetchone()[0]

        active_count = db.execute(
            "SELECT COUNT(*) FROM files WHERE active = 1"
        ).fetchone()[0]

    await update.message.reply_text(
        "📊 آمار ربات\n\n"
        f"👥 تعداد کاربران ثبت‌شده: {users_count}\n"
        f"📁 تعداد کل فایل‌ها: {files_count}\n"
        f"🟢 لینک‌های فعال: {active_count}"
    )


# ---------------- ADMIN FILE LIST ----------------

async def files_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    files = get_all_files()

    if not files:
        await update.message.reply_text("هنوز فایلی ثبت نشده است.")
        return

    for file_key, file_name, active in files:
        status = "🟢 فعال" if active else "🔴 غیرفعال"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔴 غیرفعال کردن" if active else "🟢 فعال کردن",
                    callback_data=f"toggle:{file_key}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 حذف لینک",
                    callback_data=f"delete:{file_key}",
                )
            ],
        ])

        bot_info = await context.bot.get_me()
        link = (
            f"https://t.me/{bot_info.username}"
            f"?start=file_{file_key}"
        )

        await update.message.reply_text(
            f"📁 فایل: {file_name}\n"
            f"🔑 شناسه: {file_key}\n"
            f"وضعیت: {status}\n\n"
            f"🔗 {link}",
            reply_markup=keyboard,
        )


# ---------------- ADMIN FILE CONTROLS ----------------

async def file_control(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.answer()
        return

    await query.answer()

    action, file_key = query.data.split(":", 1)

    with db_connect() as db:
        if action == "toggle":
            row = db.execute(
                "SELECT active FROM files WHERE file_key = ?",
                (file_key,),
            ).fetchone()

            if not row:
                await query.edit_message_text("فایل پیدا نشد.")
                return

            new_status = 0 if row[0] else 1

            db.execute(
                "UPDATE files SET active = ? WHERE file_key = ?",
                (new_status, file_key),
            )

            await query.edit_message_text(
                "✅ وضعیت لینک تغییر کرد."
            )

        elif action == "delete":
            db.execute(
                "DELETE FROM files WHERE file_key = ?",
                (file_key,),
            )

            await query.edit_message_text(
                "🗑 لینک فایل حذف شد."
            )


# ---------------- ERROR HANDLER ----------------

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Unhandled exception:",
        exc_info=context.error,
    )


# ---------------- MAIN ----------------

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN در فایل .env تنظیم نشده است."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("files", files_command))

    app.add_handler(
        CallbackQueryHandler(
            check_callback,
            pattern=r"^check:",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            file_control,
            pattern=r"^(toggle|delete):",
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            handle_upload,
        )
    )

    app.add_error_handler(error_handler)

    logger.info("Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
