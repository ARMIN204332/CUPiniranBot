```python
import os
import sqlite3
import logging
import html

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# آیدی عددی اکانت ادمین
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

CHANNELS = [
    (
        "@CUPiniran",
        "📢 کانال CUPiniran",
        "https://t.me/CUPiniran"
    ),
    (
        "@nabzegahan",
        "📢 کانال نبض جهان",
        "https://t.me/nabzegahan"
    ),
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


def add_or_update_user(
    user_id,
    username,
    first_name,
    invited_by=None
):
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

        # invited_by قبلی حفظ می‌شود
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
# ADMIN
# =========================

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


async def admin_only(update: Update):
    user = update.effective_user

    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text(
                "⛔ شما اجازه دسترسی به پنل مدیریت را ندارید."
            )
        return False

    return True


# =========================
# ADMIN MENU
# =========================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📊 آمار کلی",
                callback_data="admin_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 لیست کاربران",
                callback_data="admin_users"
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 رتبه‌بندی امتیازات",
                callback_data="admin_top"
            )
        ],
        [
            InlineKeyboardButton(
                "🔗 دعوت‌ها",
                callback_data="admin_referrals"
            )
        ],
    ]

    await update.message.reply_text(
        "🔐 پنل مدیریت\n\n"
        "یکی از گزینه‌های زیر را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ADMIN STATS
# =========================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = get_db()

    total = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    joined_cup = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE joined_cup = 1"
    ).fetchone()["c"]

    joined_nabz = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE joined_nabz = 1"
    ).fetchone()["c"]

    fully_joined = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE joined_cup = 1
        AND joined_nabz = 1
    """).fetchone()["c"]

    referral_users = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE invited_by IS NOT NULL
    """).fetchone()["c"]

    total_points = conn.execute("""
        SELECT COALESCE(SUM(points), 0) AS s
        FROM users
    """).fetchone()["s"]

    conn.close()

    text = (
        "📊 <b>آمار کلی بات</b>\n\n"
        f"👥 کل کاربران: <b>{total}</b>\n"
        f"📢 عضو CUPiniran: <b>{joined_cup}</b>\n"
        f"📢 عضو نبض جهان: <b>{joined_nabz}</b>\n"
        f"✅ عضویت کامل: <b>{fully_joined}</b>\n"
        f"🔗 کاربران دارای دعوت‌کننده: <b>{referral_users}</b>\n"
        f"⭐ مجموع امتیازات: <b>{total_points}</b>"
    )

    keyboard = [[
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_home"
        )
    ]]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ADMIN USERS
# =========================

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = get_db()

    users = conn.execute("""
        SELECT *
        FROM users
        ORDER BY created_at DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    if not users:
        text = "👥 هنوز هیچ کاربری ثبت نشده."
    else:

        lines = [
            "👥 <b>آخرین کاربران</b>\n"
        ]

        for index, user in enumerate(users, 1):

            name = html.escape(
                user["first_name"] or "بدون نام"
            )

            username = (
                f"@{html.escape(user['username'])}"
                if user["username"]
                else "بدون یوزرنیم"
            )

            inviter = (
                str(user["invited_by"])
                if user["invited_by"]
                else "بدون دعوت‌کننده"
            )

            joined = "✅" if (
                user["joined_cup"]
                and user["joined_nabz"]
            ) else "❌"

            lines.append(
                f"{index}. {name} | {username}\n"
                f"🆔 <code>{user['id']}</code>\n"
                f"🔗 دعوت‌کننده: <code>{inviter}</code>\n"
                f"⭐ امتیاز: <b>{user['points']}</b>\n"
                f"📢 عضویت کامل: {joined}\n"
            )

        text = "\n".join(lines)

    keyboard = [[
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_home"
        )
    ]]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ADMIN TOP
# =========================

async def admin_top(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = get_db()

    users = conn.execute("""
        SELECT *
        FROM users
        ORDER BY points DESC, created_at ASC
        LIMIT 50
    """).fetchall()

    conn.close()

    if not users:
        text = "🏆 هنوز کاربری وجود ندارد."

    else:

        lines = [
            "🏆 <b>رتبه‌بندی امتیازات</b>\n"
        ]

        medals = ["🥇", "🥈", "🥉"]

        for index, user in enumerate(users, 1):

            name = html.escape(
                user["first_name"] or "بدون نام"
            )

            username = (
                f"@{html.escape(user['username'])}"
                if user["username"]
                else ""
            )

            medal = (
                medals[index - 1]
                if index <= 3
                else f"{index}."
            )

            lines.append(
                f"{medal} {name} {username}\n"
                f"🆔 <code>{user['id']}</code> "
                f"⭐ <b>{user['points']}</b>\n"
            )

        text = "\n".join(lines)

    keyboard = [[
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_home"
        )
    ]]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ADMIN REFERRALS
# =========================

async def admin_referrals(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = get_db()

    users = conn.execute("""
        SELECT
            u.id,
            u.first_name,
            u.username,
            u.invited_by,
            u.points,
            u.referral_rewarded
        FROM users u
        WHERE u.invited_by IS NOT NULL
        ORDER BY u.created_at DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    if not users:
        text = "🔗 هنوز کسی با لینک دعوت وارد نشده."

    else:

        lines = [
            "🔗 <b>لیست دعوت‌ها</b>\n"
        ]

        for index, user in enumerate(users, 1):

            name = html.escape(
                user["first_name"] or "بدون نام"
            )

            rewarded = (
                "✅ امتیاز دعوت ثبت شده"
                if user["referral_rewarded"]
                else "⏳ هنوز پاداش ثبت نشده"
            )

            lines.append(
                f"{index}. {name}\n"
                f"🆔 کاربر: <code>{user['id']}</code>\n"
                f"👤 دعوت‌کننده: <code>{user['invited_by']}</code>\n"
                f"⭐ امتیاز کاربر: <b>{user['points']}</b>\n"
                f"{rewarded}\n"
            )

        text = "\n".join(lines)

    keyboard = [[
        InlineKeyboardButton(
            "🔙 پنل مدیریت",
            callback_data="admin_home"
        )
    ]]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ADMIN HOME CALLBACK
# =========================

async def admin_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📊 آمار کلی",
                callback_data="admin_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 لیست کاربران",
                callback_data="admin_users"
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 رتبه‌بندی امتیازات",
                callback_data="admin_top"
            )
        ],
        [
            InlineKeyboardButton(
                "🔗 دعوت‌ها",
                callback_data="admin_referrals"
            )
        ],
    ]

    await query.edit_message_text(
        "🔐 <b>پنل مدیریت</b>\n\n"
        "مدیریت کاربران و امتیازات:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# USER SEARCH
# =========================

async def user_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "مثال:\n"
            "/user 123456789"
        )
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ آیدی باید عددی باشد."
        )
        return

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    if not user:
        await update.message.reply_text(
            "❌ این کاربر در دیتابیس پیدا نشد."
        )
        return

    name = html.escape(
        user["first_name"] or "بدون نام"
    )

    username = (
        f"@{html.escape(user['username'])}"
        if user["username"]
        else "بدون یوزرنیم"
    )

    inviter = (
        str(user["invited_by"])
        if user["invited_by"]
        else "ندارد"
    )

    text = (
        "👤 <b>اطلاعات کاربر</b>\n\n"
        f"نام: {name}\n"
        f"یوزرنیم: {username}\n"
        f"🆔 ID: <code>{user['id']}</code>\n"
        f"⭐ امتیاز: <b>{user['points']}</b>\n"
        f"🔗 دعوت‌کننده: <code>{inviter}</code>\n"
        f"📢 CUPiniran: "
        f"{'✅' if user['joined_cup'] else '❌'}\n"
        f"📢 نبض جهان: "
        f"{'✅' if user['joined_nabz'] else '❌'}\n"
        f"🎁 پاداش دعوت: "
        f"{'✅' if user['referral_rewarded'] else '❌'}\n"
        f"🕐 ثبت: {user['created_at']}"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================
# MEMBERSHIP
# =========================

async def check_channel_membership(
    bot,
    user_id,
    channel
):

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

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

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
        "برای فعال شدن حساب امتیازی، ابتدا "
        "در کانال‌های زیر عضو شو:\n\n"
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

async def check_membership(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

    conn.execute("""
        UPDATE users
        SET joined_cup = ?, joined_nabz = ?
        WHERE id = ?
    """, (
        1 if cup else 0,
        1 if nabz else 0,
        user.id,
    ))

    # امتیاز عضویت CUP
    if cup and not old_cup:

        conn.execute("""
            UPDATE users
            SET points = points + 1
            WHERE id = ?
        """, (user.id,))

    # امتیاز عضویت نبض
    if nabz and not old_nabz:

        conn.execute("""
            UPDATE users
            SET points = points + 1
            WHERE id = ?
        """, (user.id,))

    conn.commit()

    # =====================
    # REFERRAL REWARD
    # =====================

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

async def my_points(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

async def invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

    keyboard = [[
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="back_home"
        )
    ]]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# HOME
# =========================

async def back_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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
# TEXT ADMIN COMMANDS
# =========================

async def admin_text_commands(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    text = update.message.text.strip().lower()

    if text == "admin":
        await admin(update, context)

    elif text in ("stats", "stast"):
        await admin_stats_direct(update, context)

    elif text == "users":
        await admin_users_direct(update, context)

    elif text == "top":
        await admin_top_direct(update, context)

    elif text == "referrals":
        await admin_referrals_direct(update, context)


# =========================
# DIRECT ADMIN COMMAND VERSIONS
# =========================

async def admin_stats_direct(update, context):

    conn = get_db()

    total = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    cup = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE joined_cup=1"
    ).fetchone()["c"]

    nabz = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE joined_nabz=1"
    ).fetchone()["c"]

    full = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE joined_cup=1 AND joined_nabz=1
    """).fetchone()["c"]

    referrals = conn.execute("""
        SELECT COUNT(*) AS c
        FROM users
        WHERE invited_by IS NOT NULL
    """).fetchone()["c"]

    points = conn.execute("""
        SELECT COALESCE(SUM(points),0) AS s
        FROM users
    """).fetchone()["s"]

    conn.close()

    await update.message.reply_text(
        "📊 آمار کلی\n\n"
        f"👥 کل کاربران: {total}\n"
        f"📢 CUPiniran: {cup}\n"
        f"📢 نبض جهان: {nabz}\n"
        f"✅ عضویت کامل: {full}\n"
        f"🔗 دارای دعوت‌کننده: {referrals}\n"
        f"⭐ مجموع امتیازات: {points}"
    )


async def admin_users_direct(update, context):

    conn = get_db()

    users = conn.execute("""
        SELECT *
        FROM users
        ORDER BY created_at DESC
        LIMIT 30
    """).fetchall()

    conn.close()

    if not users:
        await update.message.reply_text(
            "👥 هنوز کاربری ثبت نشده."
        )
        return

    lines = ["👥 آخرین کاربران:\n"]

    for i, user in enumerate(users, 1):

        name = user["first_name"] or "بدون نام"

        inviter = (
            str(user["invited_by"])
            if user["invited_by"]
            else "ندارد"
        )

        lines.append(
            f"{i}. {name}\n"
            f"🆔 {user['id']}\n"
            f"🔗 دعوت‌کننده: {inviter}\n"
            f"⭐ امتیاز: {user['points']}\n"
            f"📅 {user['created_at']}\n"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


async def admin_top_direct(update, context):

    conn = get_db()

    users = conn.execute("""
        SELECT *
        FROM users
        ORDER BY points DESC, created_at ASC
        LIMIT 30
    """).fetchall()

    conn.close()

    if not users:
        await update.message.reply_text(
            "🏆 کاربری وجود ندارد."
        )
        return

    lines = ["🏆 رتبه‌بندی:\n"]

    for i, user in enumerate(users, 1):

        name = user["first_name"] or "بدون نام"

        lines.append(
            f"{i}. {name}\n"
            f"🆔 {user['id']}\n"
            f"⭐ {user['points']} امتیاز\n"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


async def admin_referrals_direct(update, context):

    conn = get_db()

    users = conn.execute("""
        SELECT *
        FROM users
        WHERE invited_by IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 30
    """).fetchall()

    conn.close()

    if not users:
        await update.message.reply_text(
            "🔗 هنوز دعوتی ثبت نشده."
        )
        return

    lines = ["🔗 دعوت‌ها:\n"]

    for i, user in enumerate(users, 1):

        name = user["first_name"] or "بدون نام"

        reward = (
            "✅ پاداش ثبت شده"
            if user["referral_rewarded"]
            else "⏳ پاداش ثبت نشده"
        )

        lines.append(
            f"{i}. {name}\n"
            f"🆔 {user['id']}\n"
            f"👤 دعوت‌کننده: {user['invited_by']}\n"
            f"{reward}\n"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


# =========================
# MAIN
# =========================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is not set."
        )

    if ADMIN_ID == 0:
        raise RuntimeError(
            "ADMIN_ID environment variable is not set."
        )

    init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # =====================
    # USER COMMANDS
    # =====================

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("user", user_command)
    )

    # =====================
    # ADMIN COMMANDS
    # =====================

    application.add_handler(
        CommandHandler("admin", admin)
    )

    application.add_handler(
        CommandHandler("stats", admin_stats_direct)
    )

    application.add_handler(
        CommandHandler("users", admin_users_direct)
    )

    application.add_handler(
        CommandHandler("top", admin_top_direct)
    )

    application.add_handler(
        CommandHandler("referrals", admin_referrals_direct)
    )

    # =====================
    # CALLBACKS
    # =====================

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

    application.add_handler(
        CallbackQueryHandler(
            admin_home,
            pattern="^admin_home$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_stats,
            pattern="^admin_stats$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_users,
            pattern="^admin_users$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_top,
            pattern="^admin_top$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_referrals,
            pattern="^admin_referrals$"
        )
    )

    # =====================
    # PLAIN TEXT ADMIN
    # =====================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text_commands
        )
    )

    logger.info("Bot is starting...")

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
```
