```python
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

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CHANNELS = [
    ("@CUPiniran", "📢 کانال CUPiniran", "https://t.me/CUPiniran"),
    ("@nabzegahan", "📢 کانال نبض جهان", "https://t.me/nabzegahan"),
]

DB_FILE = "bot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            invited_by INTEGER,
            points INTEGER DEFAULT 0,
            joined_cup INTEGER DEFAULT 0,
            joined_nabz INTEGER DEFAULT 0,
            referral_rewarded INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def add_or_update_user(user_id, username, first_name, invited_by=None):
    conn = get_db()

    existing = conn.execute(
        "SELECT id, invited_by FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if existing is None:
        # جلوگیری از دعوت کردن خودش
        if invited_by == user_id:
            invited_by = None

        conn.execute("""
            INSERT INTO users
            (id, username, first_name, invited_by)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            username,
            first_name,
            invited_by,
        ))
    else:
        # invited_by قبلی را حفظ می‌کنیم
        conn.execute("""
            UPDATE users
            SET username = ?, first_name = ?
            WHERE id = ?
        """, (
            username,
            first_name,
            user_id,
        ))

    conn.commit()
    conn.close()


# =========================
# MEMBERSHIP
# =========================

async def check_channel_membership(bot, user_id, channel):
    try:
        member = await bot.get_chat_member(
            chat_id=channel,
            user_id=user_id
        )

        return member.status in (
            "member",
            "administrator",
            "creator",
        )

    except Exception as e:
        logger.warning(
            "Membership check failed for %s in %s: %s",
            user_id,
            channel,
            e,
        )
        return False


async def check_all_memberships(bot, user_id):
    cup = await check_channel_membership(
        bot,
        user_id,
        "@CUPiniran"
    )

    nabz = await check_channel_membership(
        bot,
        user_id,
        "@nabzegahan"
    )

    return cup, nabz


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user:
        return

    # دریافت پارامتر دعوت
    invited_by = None

    if context.args:
        try:
            invited_by = int(context.args[0])
        except ValueError:
            invited_by = None

    add_or_update_user(
        user.id,
        user.username,
        user.first_name,
        invited_by,
    )

    keyboard = []

    for _, title, url in CHANNELS:
        keyboard.append([
            InlineKeyboardButton(
                title,
                url=url
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "✅ بررسی عضویت",
            callback_data="check_membership"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏆 امتیاز من",
            callback_data="my_points"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "👥 دعوت دوستان",
            callback_data="invite"
        )
    ])

    text = (
        f"سلام {user.first_name} 👋\n\n"
        "به ربات خوش آمدی.\n\n"
        "برای فعال شدن حساب امتیازی، ابتدا در کانال‌های زیر عضو شو:\n\n"
        "📢 CUPiniran\n"
        "📢 نبض جهان\n\n"
        "بعد از عضویت روی «بررسی عضویت» بزن."
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# MEMBERSHIP CHECK
# =========================

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    user = query.from_user

    cup, nabz = await check_all_memberships(
        context.bot,
        user.id
    )

    conn = get_db()

    row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user.id,)
    ).fetchone()

    if row is None:
        conn.close()
        return

    old_cup = row["joined_cup"]
    old_nabz = row["joined_nabz"]

    # ذخیره وضعیت عضویت
    conn.execute("""
        UPDATE users
        SET joined_cup = ?, joined_nabz = ?
        WHERE id = ?
    """, (
        1 if cup else 0,
        1 if nabz else 0,
        user.id,
    ))

    # هر عضویت موفق فقط یک بار امتیاز می‌گیرد
    if cup and not old_cup:
        conn.execute("""
            UPDATE users
            SET points = points + 1
            WHERE id = ?
        """, (user.id,))

    if nabz and not old_nabz:
        conn.execute("""
            UPDATE users
            SET points = points + 1
            WHERE id = ?
        """, (user.id,))

    conn.commit()

    # بررسی دعوت موفق
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user.id,)
    ).fetchone()

    if (
        cup
        and nabz
        and row["invited_by"]
        and row["referral_rewarded"] == 0
        and row["invited_by"] != user.id
    ):
        inviter = row["invited_by"]

        inviter_exists = conn.execute(
            "SELECT id FROM users WHERE id = ?",
            (inviter,)
        ).fetchone()

        if inviter_exists:
            conn.execute("""
                UPDATE users
                SET points = points + 1
                WHERE id = ?
            """, (inviter,))

            conn.execute("""
                UPDATE users
                SET referral_rewarded = 1
                WHERE id = ?
            """, (user.id,))

    conn.commit()

    final_row = conn.execute(
        "SELECT points FROM users WHERE id = ?",
        (user.id,)
    ).fetchone()

    conn.close()

    points = final_row["points"]

    if cup and nabz:
        text = (
            "✅ عضویت شما با موفقیت تأیید شد!\n\n"
            "🏆 سیستم امتیازدهی برای شما فعال است.\n\n"
            f"⭐ امتیاز فعلی: {points}"
        )
    else:
        missing = []

        if not cup:
            missing.append("📢 CUPiniran")

        if not nabz:
            missing.append("📢 نبض جهان")

        text = (
            "❌ عضویت کامل تأیید نشد.\n\n"
            "لطفاً در این کانال‌ها عضو شوید:\n\n"
            + "\n".join(missing)
            + "\n\n"
            "سپس دوباره «بررسی عضویت» را بزنید."
        )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 بررسی دوباره",
                callback_data="check_membership"
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 امتیاز من",
                callback_data="my_points"
            )
        ],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# POINTS
# =========================

async def my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    user = query.from_user

    conn = get_db()

    row = conn.execute(
        "SELECT points FROM users WHERE id = ?",
        (user.id,)
    ).fetchone()

    conn.close()

    points = row["points"] if row else 0

    text = (
        "🏆 امتیازات شما\n\n"
        f"⭐ امتیاز فعلی: {points}\n\n"
        "روش‌های دریافت امتیاز:\n"
        "📢 عضویت موفق در هر کانال: ۱ امتیاز\n"
        "👥 دعوت موفق هر نفر: ۱ امتیاز"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "👥 دعوت دوستان",
                callback_data="invite"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="back_home"
            )
        ],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# REFERRAL
# =========================

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    user = query.from_user

    bot_username = context.bot.username

    referral_link = (
        f"https://t.me/{bot_username}?start={user.id}"
    )

    text = (
        "👥 دعوت دوستان\n\n"
        "لینک اختصاصی دعوت شما:\n\n"
        f"{referral_link}\n\n"
        "هر کاربری که از لینک شما وارد شود، "
        "در هر دو کانال عضو شود و عضویتش را تأیید کند، "
        "برای شما ۱ امتیاز ثبت می‌شود. ⭐"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="back_home"
            )
        ]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# HOME
# =========================

async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    keyboard = []

    for _, title, url in CHANNELS:
        keyboard.append([
            InlineKeyboardButton(
                title,
                url=url
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "✅ بررسی عضویت",
            callback_data="check_membership"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏆 امتیاز من",
            callback_data="my_points"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "👥 دعوت دوستان",
            callback_data="invite"
        )
    ])

    text = (
        f"سلام {query.from_user.first_name} 👋\n\n"
        "به منوی اصلی برگشتی."
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# MAIN
# =========================

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is not set."
        )

    init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CallbackQueryHandler(
            check_membership,
            pattern="^check_membership$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            my_points,
            pattern="^my_points$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            invite,
            pattern="^invite$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            back_home,
            pattern="^back_home$"
        )
    )

    logger.info("Bot is starting...")

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
```
