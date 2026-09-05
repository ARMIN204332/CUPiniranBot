import os
import sqlite3
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = "@CUPiniran"
ADMIN_ID = 8085645948

logging.basicConfig(level=logging.INFO)

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    invited_by INTEGER,
    joined INTEGER DEFAULT 0
)
""")

db.commit()


def add_user(user_id, username, first_name, invited_by=None):
    cur.execute(
        """
        INSERT OR IGNORE INTO users
        (id, username, first_name, invited_by)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, username, first_name, invited_by)
    )
    db.commit()


def menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 عضویت در کانال",
                url="https://t.me/CUPiniran"
            )
        ],
        [
            InlineKeyboardButton(
                "✅ بررسی عضویت",
                callback_data="check"
            )
        ],
        [
            InlineKeyboardButton(
                "👤 حساب من",
                callback_data="profile"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 دعوت دوستان",
                callback_data="ref"
            )
        ]
    ])


async def check_membership(user_id, context):
    try:
        member = await context.bot.get_chat_member(
            CHANNEL,
            user_id
        )

        return member.status in (
            "member",
            "administrator",
            "creator"
        )

    except Exception as e:
        logging.warning(f"Membership check failed: {e}")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    invited_by = None

    if context.args:
        try:
            ref_id = int(context.args[0])

            if ref_id != user.id:
                invited_by = ref_id

        except ValueError:
            pass

    add_user(
        user.id,
        user.username,
        user.first_name,
        invited_by
    )

    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\n"
        "به ربات خوش اومدی.\n\n"
        "برای استفاده از امکانات، ابتدا عضو کانال شو "
        "و سپس روی «بررسی عضویت» بزن.",
        reply_markup=menu()
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    # بررسی عضویت
    if query.data == "check":

        joined = await check_membership(
            user_id,
            context
        )

        if joined:

            cur.execute(
                "UPDATE users SET joined=1 WHERE id=?",
                (user_id,)
            )

            db.commit()

            await query.message.reply_text(
                "✅ عضویت شما تأیید شد.\n\n"
                "اکنون دسترسی شما فعال است.",
                reply_markup=menu()
            )

        else:

            await query.message.reply_text(
                "❌ عضویت شما هنوز تأیید نشده.\n\n"
                "ابتدا عضو کانال شوید و دوباره بررسی کنید.",
                reply_markup=menu()
            )

    # پروفایل
    elif query.data == "profile":

        # فقط دعوت‌هایی که عضویتشان تأیید شده
        cur.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE invited_by=? AND joined=1
            """,
            (user_id,)
        )

        referrals = cur.fetchone()[0]

        cur.execute(
            "SELECT joined FROM users WHERE id=?",
            (user_id,)
        )

        result = cur.fetchone()

        joined = result[0] if result else 0

        status = "✅ تأیید شده" if joined else "❌ تأیید نشده"

        await query.message.reply_text(
            "👤 اطلاعات حساب\n\n"
            f"🆔 شناسه: {user_id}\n"
            f"📢 وضعیت عضویت: {status}\n"
            f"👥 تعداد دعوت‌های تأییدشده: {referrals}",
            reply_markup=menu()
        )

    # لینک دعوت
    elif query.data == "ref":

        bot_username = context.bot.username

        link = (
            f"https://t.me/"
            f"{bot_username}"
            f"?start={user_id}"
        )

        # فقط کسانی که واقعاً عضو کانال شده‌اند
        cur.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE invited_by=? AND joined=1
            """,
            (user_id,)
        )

        count = cur.fetchone()[0]

        await query.message.reply_text(
            "👥 دعوت دوستان\n\n"
            f"تعداد دعوت‌های تأییدشده: {count}\n\n"
            "🔗 لینک اختصاصی شما:\n"
            f"{link}\n\n"
            "این لینک را برای دوستانت بفرست.\n"
            "فقط افرادی که عضو کانال شوند و عضویتشان تأیید شود، "
            "به عنوان دعوت موفق حساب می‌شوند.",
            reply_markup=menu()
        )


# پنل مدیریت
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE joined=1"
    )
    joined = cur.fetchone()[0]

    await update.message.reply_text(
        "🛠 پنل مدیریت\n\n"
        f"👥 کل کاربران: {total}\n"
        f"✅ اعضای تأییدشده: {joined}\n\n"
        "دستورهای مدیریت:\n"
        "/stats - آمار کامل و دعوت‌ها\n"
        "/broadcast - ارسال پیام همگانی"
    )


# آمار
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE joined=1"
    )
    joined = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE joined=0"
    )
    not_joined = cur.fetchone()[0]

    # رتبه‌بندی دعوت‌کننده‌ها
    # فقط کاربرانی که دعوت شده‌اند و عضویتشان تأیید شده
    cur.execute("""
        SELECT
            u.id,
            u.username,
            u.first_name,
            COUNT(r.id) AS referrals
        FROM users u
        LEFT JOIN users r
            ON r.invited_by = u.id
            AND r.joined = 1
        GROUP BY u.id
        HAVING referrals > 0
        ORDER BY referrals DESC
        LIMIT 20
    """)

    referrers = cur.fetchall()

    text = (
        "📊 آمار ربات\n\n"
        f"👥 کل کاربران: {total}\n"
        f"✅ عضو تأییدشده: {joined}\n"
        f"❌ تأییدنشده: {not_joined}\n\n"
        "🏆 برترین دعوت‌کننده‌ها:\n\n"
    )

    if not referrers:

        text += "هنوز دعوت تأییدشده‌ای ثبت نشده."

    else:

        for i, row in enumerate(referrers, start=1):

            user_id, username, first_name, referrals = row

            if username:
                name = f"@{username}"
            else:
                name = first_name or str(user_id)

            text += (
                f"{i}. {name}\n"
                f"   👥 دعوت موفق: {referrals} نفر\n"
            )

    await update.message.reply_text(text)


# ارسال پیام همگانی
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:

        await update.message.reply_text(
            "نحوه استفاده:\n"
            "/broadcast متن پیام"
        )

        return

    message = " ".join(context.args)

    cur.execute("SELECT id FROM users")
    users = cur.fetchall()

    success = 0
    failed = 0

    for row in users:

        user_id = row[0]

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )

            success += 1

        except Exception:

            failed += 1

    await update.message.reply_text(
        "📢 ارسال انجام شد.\n\n"
        f"✅ موفق: {success}\n"
        f"❌ ناموفق: {failed}"
    )


def main():

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin)
    )

    app.add_handler(
        CommandHandler("stats", stats)
    )

    app.add_handler(
        CommandHandler("broadcast", broadcast)
    )

    app.add_handler(
        CallbackQueryHandler(buttons)
    )

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
