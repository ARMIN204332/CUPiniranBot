
import os
import sqlite3
import logging
import secrets
from datetime import datetime, timezone

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================================================
# تنظیمات
# ==================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "bot.db")

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ==================================================
# دیتابیس
# ==================================================

def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect_db() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploader_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploaded_files (
                file_key TEXT PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_name TEXT,
                caption TEXT,
                file_size INTEGER,
                downloads INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        conn.commit()


def save_user(user):
    with connect_db() as conn:
        conn.execute("""
            INSERT INTO uploader_users
            (user_id, username, first_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            datetime.now(timezone.utc).isoformat(),
        ))

        conn.commit()


def save_file(
    file_key,
    owner_id,
    file_id,
    file_type,
    file_name,
    caption,
    file_size
):
    with connect_db() as conn:
        conn.execute("""
            INSERT INTO uploaded_files (
                file_key,
                owner_id,
                file_id,
                file_type,
                file_name,
                caption,
                file_size,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_key,
            owner_id,
            file_id,
            file_type,
            file_name or "",
            caption or "",
            file_size or 0,
            datetime.now(timezone.utc).isoformat(),
        ))

        conn.commit()


def find_file(file_key):
    with connect_db() as conn:
        return conn.execute(
            "SELECT * FROM uploaded_files WHERE file_key = ?",
            (file_key,)
        ).fetchone()


def count_download(file_key):
    with connect_db() as conn:
        conn.execute("""
            UPDATE uploaded_files
            SET downloads = downloads + 1
            WHERE file_key = ?
        """, (file_key,))

        conn.commit()


def change_file_status(file_key, enabled):
    with connect_db() as conn:
        cur = conn.execute("""
            UPDATE uploaded_files
            SET enabled = ?
            WHERE file_key = ?
        """, (int(enabled), file_key))

        conn.commit()
        return cur.rowcount > 0


def remove_file(file_key):
    with connect_db() as conn:
        cur = conn.execute(
            "DELETE FROM uploaded_files WHERE file_key = ?",
            (file_key,)
        )

        conn.commit()
        return cur.rowcount > 0


def get_stats():
    with connect_db() as conn:

        users = conn.execute(
            "SELECT COUNT(*) FROM uploader_users"
        ).fetchone()[0]

        total = conn.execute(
            "SELECT COUNT(*) FROM uploaded_files"
        ).fetchone()[0]

        active = conn.execute("""
            SELECT COUNT(*) FROM uploaded_files
            WHERE enabled = 1
        """).fetchone()[0]

        downloads = conn.execute("""
            SELECT COALESCE(SUM(downloads), 0)
            FROM uploaded_files
        """).fetchone()[0]

    return users, total, active, downloads


def recent_files(limit=15):
    with connect_db() as conn:
        return conn.execute("""
            SELECT
                file_key,
                owner_id,
                file_name,
                file_type,
                downloads,
                enabled
            FROM uploaded_files
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


# ==================================================
# ابزارهای کمکی
# ==================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def make_membership_keyboard(file_key):
    rows = []

    for _, url, label in REQUIRED_CHANNELS:
        rows.append([
            InlineKeyboardButton(label, url=url)
        ])

    rows.append([
        InlineKeyboardButton(
            "✅ بررسی عضویت و دریافت فایل",
            callback_data=f"getfile:{file_key}"
        )
    ])

    return InlineKeyboardMarkup(rows)


# ==================================================
# بررسی عضویت
# ==================================================

async def check_required_membership(context, user_id):

    for channel, _, _ in REQUIRED_CHANNELS:

        try:
            logger.info(
                "Starting membership check: channel=%s user_id=%s",
                channel,
                user_id
            )

            member = await context.bot.get_chat_member(
                chat_id=channel,
                user_id=user_id
            )

            status = member.status

            logger.info(
                "Membership result: channel=%s user_id=%s status=%s",
                channel,
                user_id,
                status
            )

            if status in (
                ChatMemberStatus.LEFT,
                ChatMemberStatus.BANNED
            ):
                return False

            if (
                status == ChatMemberStatus.RESTRICTED
                and not member.is_member
            ):
                return False

        except Exception:
            logger.exception(
                "MEMBERSHIP API ERROR: channel=%s user_id=%s",
                channel,
                user_id
            )

            return None

    return True


# ==================================================
# ارسال فایل
# ==================================================

async def send_file_to_user(chat_id, row, context):

    file_id = row["file_id"]
    caption = row["caption"] or None
    kind = row["file_type"]

    if kind == "photo":
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=file_id,
            caption=caption
        )

    elif kind == "video":
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=caption
        )

    elif kind == "audio":
        await context.bot.send_audio(
            chat_id=chat_id,
            audio=file_id,
            caption=caption
        )

    elif kind == "voice":
        await context.bot.send_voice(
            chat_id=chat_id,
            voice=file_id,
            caption=caption
        )

    elif kind == "animation":
        await context.bot.send_animation(
            chat_id=chat_id,
            animation=file_id,
            caption=caption
        )

    elif kind == "video_note":
        await context.bot.send_video_note(
            chat_id=chat_id,
            video_note=file_id
        )

        if caption:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption
            )

    elif kind == "sticker":
        await context.bot.send_sticker(
            chat_id=chat_id,
            sticker=file_id
        )

    else:
        await context.bot.send_document(
            chat_id=chat_id,
            document=file_id,
            caption=caption
        )


# ==================================================
# تشخیص فایل ارسالی
# ==================================================

def get_media(message):

    if message.document:
        m = message.document
        return "document", m.file_id, m.file_name or "file", m.file_size

    if message.photo:
        m = message.photo[-1]
        return "photo", m.file_id, "photo.jpg", m.file_size

    if message.video:
        m = message.video
        return "video", m.file_id, m.file_name or "video.mp4", m.file_size

    if message.audio:
        m = message.audio
        return "audio", m.file_id, m.file_name or "audio", m.file_size

    if message.voice:
        m = message.voice
        return "voice", m.file_id, "voice.ogg", m.file_size

    if message.animation:
        m = message.animation
        return "animation", m.file_id, m.file_name or "animation.gif", m.file_size

    if message.video_note:
        m = message.video_note
        return "video_note", m.file_id, "video_note.mp4", m.file_size

    if message.sticker:
        m = message.sticker
        return "sticker", m.file_id, "sticker", None

    return None


# ==================================================
# دستور شروع
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not update.message:
        return

    save_user(user)

    if not context.args:
        return

    argument = context.args[0]

    if not argument.startswith("file_"):
        return

    file_key = argument[5:]
    row = find_file(file_key)

    if row is None or not row["enabled"]:
        await update.message.reply_text(
            "این لینک معتبر نیست یا فایل غیرفعال شده است."
        )
        return

    if not is_admin(user.id):

        membership = await check_required_membership(
            context,
            user.id
        )

        if membership is False:

            await update.message.reply_text(
                "برای دریافت فایل ابتدا باید عضو کانال زیر شوی:",
                reply_markup=make_membership_keyboard(file_key)
            )

            return

        if membership is None:

            await update.message.reply_text(
                "در حال حاضر بررسی عضویت ممکن نیست. "
                "لطفاً کمی بعد دوباره تلاش کن."
            )

            return

    try:

        await send_file_to_user(
            update.effective_chat.id,
            row,
            context
        )

        count_download(file_key)

    except Exception:

        logger.exception(
            "File delivery failed: key=%s",
            file_key
        )

        await update.message.reply_text(
            "ارسال فایل با خطا مواجه شد. لطفاً دوباره تلاش کن."
        )


# ==================================================
# آپلود فایل توسط ادمین
# ==================================================

async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    save_user(user)

    message = update.effective_message
    media = get_media(message)

    if not media:
        return

    file_type, file_id, file_name, file_size = media
    caption = message.caption or ""

    file_key = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:13]

    try:

        save_file(
            file_key,
            user.id,
            file_id,
            file_type,
            file_name,
            caption,
            file_size
        )

        bot_info = await context.bot.get_me()

        link = (
            f"https://t.me/{bot_info.username}"
            f"?start=file_{file_key}"
        )

        await message.reply_text(
            "✅ فایل با موفقیت ثبت شد.\n\n"
            f"نام فایل: {file_name}\n"
            f"نوع فایل: {file_type}\n\n"
            "🔗 لینک اختصاصی:\n"
            f"{link}\n\n"
            "برای دریافت فایل، کاربران باید عضو "
            "@MAN_O_2_NEWS باشند."
        )

    except Exception:

        logger.exception("File upload failed")

        await message.reply_text(
            "ثبت فایل با خطا مواجه شد."
        )


# ==================================================
# دکمه بررسی عضویت
# ==================================================

async def membership_check_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query or not query.data:
        return

    if not query.data.startswith("getfile:"):
        await query.answer()
        return

    file_key = query.data.split(":", 1)[1]
    row = find_file(file_key)

    if row is None or not row["enabled"]:

        await query.answer(
            "این لینک معتبر نیست یا فایل غیرفعال شده است.",
            show_alert=True
        )

        return

    if not is_admin(query.from_user.id):

        membership = await check_required_membership(
            context,
            query.from_user.id
        )

        if membership is False:

            await query.answer(
                "هنوز عضو کانال نشده‌ای.",
                show_alert=True
            )

            return

        if membership is None:

            await query.answer(
                "بررسی عضویت ناموفق بود. کمی بعد دوباره تلاش کن.",
                show_alert=True
            )

            return

    await query.answer()

    try:

        await query.edit_message_text(
            "✅ عضویت تأیید شد؛ فایل در پیام بعدی ارسال می‌شود."
        )

        await send_file_to_user(
            query.message.chat_id,
            row,
            context
        )

        count_download(file_key)

    except Exception:

        logger.exception(
            "File delivery after membership check failed: key=%s",
            file_key
        )

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="ارسال فایل با خطا مواجه شد. دوباره تلاش کن."
        )


# ==================================================
# پنل مدیریت
# ==================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📊 آمار ربات",
                callback_data="admin:stats"
            )
        ],
        [
            InlineKeyboardButton(
                "🗂 فایل‌های اخیر",
                callback_data="admin:files"
            )
        ],
    ]

    await update.message.reply_text(
        "پنل مدیریت\n\n"
        "دستورهای مدیریتی:\n"
        "/stats - آمار کلی\n"
        "/files - فایل‌های اخیر\n"
        "/disable KEY - غیرفعال‌کردن لینک\n"
        "/enable KEY - فعال‌کردن لینک\n"
        "/delete_file KEY - حذف فایل",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    users, total, active, downloads = get_stats()

    await update.message.reply_text(
        "📊 آمار ربات\n\n"
        f"کاربران ثبت‌شده: {users}\n"
        f"کل فایل‌ها: {total}\n"
        f"لینک‌های فعال: {active}\n"
        f"تعداد دریافت موفق: {downloads}"
    )


async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    rows = recent_files()

    if not rows:
        await update.message.reply_text(
            "هنوز فایلی ثبت نشده است."
        )
        return

    lines = ["🗂 فایل‌های اخیر"]

    for row in rows:

        status = "فعال" if row["enabled"] else "غیرفعال"

        lines.append(
            f"\nکلید: {row['file_key']}\n"
            f"نام: {row['file_name'] or '-'}\n"
            f"نوع: {row['file_type']}\n"
            f"دریافت: {row['downloads']}\n"
            f"وضعیت: {status}\n"
            f"آپلودکننده: {row['owner_id']}"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


async def file_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "کلید فایل را وارد کن. مثال: /disable ABC123"
        )
        return

    command = (
        update.message.text
        .split()[0]
        .split("@")[0]
        .lower()
    )

    file_key = context.args[0].strip()

    if command == "/disable":

        ok = change_file_status(file_key, False)

        result = (
            "لینک غیرفعال شد."
            if ok else
            "فایلی با این کلید پیدا نشد."
        )

    elif command == "/enable":

        ok = change_file_status(file_key, True)

        result = (
            "لینک فعال شد."
            if ok else
            "فایلی با این کلید پیدا نشد."
        )

    else:

        ok = remove_file(file_key)

        result = (
            "فایل از دیتابیس حذف شد."
            if ok else
            "فایلی با این کلید پیدا نشد."
        )

    await update.message.reply_text(result)


async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer()
        return

    await query.answer()

    if query.data == "admin:stats":

        users, total, active, downloads = get_stats()

        await query.edit_message_text(
            "📊 آمار ربات\n\n"
            f"کاربران ثبت‌شده: {users}\n"
            f"کل فایل‌ها: {total}\n"
            f"لینک‌های فعال: {active}\n"
            f"تعداد دریافت موفق: {downloads}"
        )

    elif query.data == "admin:files":

        rows = recent_files()

        if not rows:
            await query.edit_message_text(
                "هنوز فایلی ثبت نشده است."
            )
            return

        lines = ["🗂 فایل‌های اخیر"]

        for row in rows:

            status = "فعال" if row["enabled"] else "غیرفعال"

            lines.append(
                f"\n{row['file_key']} | "
                f"{row['file_name'] or '-'}\n"
                f"{row['file_type']} | "
                f"دریافت: {row['downloads']} | {status}"
            )

        await query.edit_message_text(
            "\n".join(lines)
        )


# ==================================================
# مدیریت خطا
# ==================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):

    logger.error(
        "Unhandled exception while processing update",
        exc_info=context.error
    )


# ==================================================
# اجرای ربات
# ==================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN در فایل .env تنظیم نشده است."
        )

    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin_panel)
    )

    app.add_handler(
        CommandHandler("stats", stats_command)
    )

    app.add_handler(
        CommandHandler("files", files_command)
    )

    app.add_handler(
        CommandHandler(
            ["disable", "enable", "delete_file"],
            file_admin_action
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            membership_check_button,
            pattern=r"^getfile:"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_button,
            pattern=r"^admin:"
        )
    )

    media_filter = (
        filters.Document.ALL
        | filters.PHOTO
        | filters.VIDEO
        | filters.AUDIO
        | filters.VOICE
        | filters.ANIMATION
        | filters.VIDEO_NOTE
        | filters.Sticker.ALL
    )

    app.add_handler(
        MessageHandler(
            media_filter & ~filters.COMMAND,
            upload_file
        )
    )

    app.add_error_handler(error_handler)

    logger.info("File uploader bot is starting...")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
