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

# =====================================
# تنظیمات
# =====================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

CHANNEL_1 = "@CUPiniran"
CHANNEL_2 = "@nabzegahan"

ADMIN_ID = 8085645948

logging.basicConfig(level=logging.INFO)

# =====================================
# دیتابیس
# =====================================

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    invited_by INTEGER,
    joined INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0
)
""")

db.commit()

# -------------------------------------
# سازگاری با دیتابیس قدیمی
# -------------------------------------

try:
    cur.execute("ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0")
    db.commit()
except sqlite3.OperationalError:
    pass


# =====================================
# ثبت / به‌روزرسانی کاربر
# =====================================

def add_user(user_id, username, first_name, invited_by=None):

    cur.execute(
        "SELECT id FROM users WHERE id=?",
        (user_id,)
    )

    existing = cur.fetchone()

    if existing:

        # دعوت‌کننده قبلی تغییر نکند
        cur.execute(
            """
            UPDATE users
            SET username=?, first_name=?
            WHERE id=?
            """,
            (
                username,
                first_name,
                user_id
            )
        )

    else:

        cur.execute(
            """
            INSERT INTO users
            (id, username, first_name, invited_by, joined, points)
            VALUES (?, ?, ?, ?, 0, 0)
            """,
            (
                user_id,
                username,
                first_name,
                invited_by
            )
        )

    db.commit()


# =====================================
# منوی اصلی
# =====================================

def menu():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📢 عضویت در کانال CUP",
                url="https://t.me/CUPiniran"
            )
        ],

        [
            InlineKeyboardButton(
                "📢 عضویت در کانال نبض جهان",
                url="https://t.me/nabzegahan"
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
                "⭐ امتیاز من",
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


# =====================================
# بررسی عضویت در هر دو کانال
# =====================================

async def check_one_channel(channel, user_id, context):

    try:

        member = await context.bot.get_chat_member(
            channel,
            user_id
        )

        return member.status in (
            "member",
            "administrator",
            "creator"
        )

    except Exception as e:

        logging.warning(
            f"Membership check failed for {channel}: {e}"
        )

        return False


async def check_membership(user_id, context):

    channel_1_joined = await check_one_channel(
        CHANNEL_1,
        user_id,
        context
    )

    channel_2_joined = await check_one_channel(
        CHANNEL_2,
        user_id,
        context
    )

    return channel_1_joined and channel_2_joined


# =====================================
# استارت
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    invited_by = None

    # ---------------------------------
    # بررسی لینک دعوت
    # ---------------------------------

    if context.args:

        try:

            ref_id = int(context.args[0])

            if ref_id != user.id:

                cur.execute(
                    "SELECT id FROM users WHERE id=?",
                    (ref_id,)
                )

                ref_exists = cur.fetchone()

                if ref_exists:
                    invited_by = ref_id

        except ValueError:
            pass

    # ---------------------------------
    # بررسی اولین استارت
    # ---------------------------------

    cur.execute(
        "SELECT id FROM users WHERE id=?",
        (user.id,)
    )

    existing_user = cur.fetchone()

    is_first_start = existing_user is None

    # ---------------------------------
    # ثبت کاربر
    # ---------------------------------

    add_user(
        user.id,
        user.username,
        user.first_name,
        invited_by
    )

    # ---------------------------------
    # اطلاع به ادمین فقط اولین استارت
    # ---------------------------------

    if is_first_start:

        username_text = (
            f"@{user.username}"
            if user.username
            else "ندارد"
        )

        first_name_text = (
            user.first_name
            if user.first_name
            else "نامشخص"
        )

        if invited_by:

            cur.execute(
                """
                SELECT username, first_name
                FROM users
                WHERE id=?
                """,
                (invited_by,)
            )

            inviter = cur.fetchone()

            if inviter:

                inviter_username = inviter[0]
                inviter_first_name = inviter[1]

                if inviter_username:
                    inviter_text = f"@{inviter_username}"

                else:
                    inviter_text = (
                        inviter_first_name
                        or str(invited_by)
                    )

            else:
                inviter_text = str(invited_by)

        else:
            inviter_text = "مستقیم / بدون لینک دعوت"

        admin_text = (
            "🆕 کاربر جدید ربات را استارت کرد\n\n"
            f"👤 نام: {first_name_text}\n"
            f"🔹 Username: {username_text}\n"
            f"🆔 ID: {user.id}\n"
            f"👥 دعوت‌کننده: {inviter_text}"
        )

        try:

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text
            )

        except Exception as e:

            logging.warning(
                f"Failed to notify admin: {e}"
            )

    # ---------------------------------
    # پیام خوش‌آمدگویی
    # ---------------------------------

    await update.message.reply_text(
        "سلام، خوش اومدی 👋\n\n"
        "برای دریافت امتیاز باید عضو هر دو کانال زیر باشی:\n\n"
        "📢 CUPiniran\n"
        "📢 نبض جهان\n\n"
        "⭐ عضویت موفق در هر دو کانال = ۱ امتیاز\n"
        "👥 هر دعوت موفق = ۱ امتیاز\n\n"
        "از منوی زیر استفاده کن 👇",
        reply_markup=menu()
    )


# =====================================
# دکمه‌ها
# =====================================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    # =================================
    # بررسی عضویت
    # =================================

    if query.data == "check":

        joined = await check_membership(
            user_id,
            context
        )

        # ---------------------------------
        # عضویت موفق
        # ---------------------------------

        if joined:

            # وضعیت قبلی و امتیاز فعلی
            cur.execute(
                """
                SELECT joined, points, invited_by
                FROM users
                WHERE id=?
                """,
                (user_id,)
            )

            result = cur.fetchone()

            if result:

                was_joined = result[0]
                current_points = result[1]
                invited_by = result[2]

            else:

                was_joined = 0
                current_points = 0
                invited_by = None

            # ---------------------------------
            # فقط اولین تأیید امتیاز بده
            # ---------------------------------

            if was_joined == 0:

                # یک امتیاز برای عضویت
                cur.execute(
                    """
                    UPDATE users
                    SET joined=1,
                        points=points+1,
                        username=?,
                        first_name=?
                    WHERE id=?
                    """,
                    (
                        query.from_user.username,
                        query.from_user.first_name,
                        user_id
                    )
                )

                # ---------------------------------
                # یک امتیاز برای دعوت‌کننده
                # ---------------------------------

                if invited_by:

                    cur.execute(
                        """
                        UPDATE users
                        SET points=points+1
                        WHERE id=?
                        """,
                        (invited_by,)
                    )

                db.commit()

                # امتیاز جدید
                cur.execute(
                    "SELECT points FROM users WHERE id=?",
                    (user_id,)
                )

                new_points = cur.fetchone()[0]

                await query.message.reply_text(
                    "✅ عضویت شما در هر دو کانال تأیید شد.\n\n"
                    "⭐ ۱ امتیاز بابت عضویت دریافت کردی!\n\n"
                    f"🏆 امتیاز فعلی شما: {new_points}",
                    reply_markup=menu()
                )

            else:

                cur.execute(
                    "SELECT points FROM users WHERE id=?",
                    (user_id,)
                )

                points = cur.fetchone()[0]

                await query.message.reply_text(
                    "✅ عضویت شما قبلاً تأیید شده است.\n\n"
                    f"🏆 امتیاز شما: {points}",
                    reply_markup=menu()
                )

        # ---------------------------------
        # عضویت ناقص
        # ---------------------------------

        else:

            await query.message.reply_text(
                "❌ عضویت شما کامل نیست.\n\n"
                "ابتدا در هر دو کانال عضو شوید:\n\n"
                "📢 @CUPiniran\n"
                "📢 @nabzegahan\n\n"
                "سپس دوباره روی «بررسی عضویت» بزنید.",
                reply_markup=menu()
            )


    # =================================
    # پروفایل / امتیاز
    # =================================

    elif query.data == "profile":

        cur.execute(
            """
            SELECT points, joined
            FROM users
            WHERE id=?
            """,
            (user_id,)
        )

        result = cur.fetchone()

        if result:

            points = result[0]
            joined = result[1]

        else:

            points = 0
            joined = 0

        status = (
            "✅ تأیید شده"
            if joined
            else "❌ تأیید نشده"
        )

        # تعداد دعوت موفق
        cur.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE invited_by=?
            AND joined=1
            """,
            (user_id,)
        )

        referrals = cur.fetchone()[0]

        await query.message.reply_text(
            "👤 حساب من\n\n"
            f"🆔 شناسه: {user_id}\n"
            f"📢 وضعیت عضویت: {status}\n"
            f"👥 دعوت‌های موفق: {referrals}\n"
            f"⭐ امتیاز: {points}",
            reply_markup=menu()
        )


    # =================================
    # لینک دعوت
    # =================================

    elif query.data == "ref":

        bot_username = context.bot.username

        link = (
            f"https://t.me/"
            f"{bot_username}"
            f"?start={user_id}"
        )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE invited_by=?
            AND joined=1
            """,
            (user_id,)
        )

        count = cur.fetchone()[0]

        cur.execute(
            "SELECT points FROM users WHERE id=?",
            (user_id,)
        )

        points = cur.fetchone()[0]

        await query.message.reply_text(
            "👥 دعوت دوستان\n\n"
            f"تعداد دعوت موفق: {count}\n"
            f"⭐ امتیاز فعلی: {points}\n\n"
            "🔗 لینک اختصاصی شما:\n"
            f"{link}\n\n"
            "لینک را برای دوستانت بفرست.\n"
            "هر شخصی که با لینک تو وارد شود، "
            "عضویت هر دو کانال را تأیید کند، "
            "۱ امتیاز برای تو ثبت می‌شود.",
            reply_markup=menu()
        )


# =====================================
# پنل مدیریت
# =====================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute(
        "SELECT COUNT(*) FROM users"
    )

    total = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE joined=1
        """
    )

    joined = cur.fetchone()[0]

    cur.execute(
        "SELECT COALESCE(SUM(points), 0) FROM users"
    )

    total_points = cur.fetchone()[0]

    await update.message.reply_text(
        "🛠 پنل مدیریت\n\n"
        f"👥 کل کاربران: {total}\n"
        f"✅ اعضای تأییدشده: {joined}\n"
        f"⭐ مجموع امتیازها: {total_points}\n\n"
        "دستورهای مدیریت:\n\n"
        "/stats - آمار و رتبه امتیازها\n"
        "/members - لیست اعضا و امتیازها\n"
        "/broadcast - ارسال پیام همگانی"
    )


# =====================================
# آمار و رتبه‌بندی امتیازها
# =====================================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute(
        "SELECT COUNT(*) FROM users"
    )

    total = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE joined=1
        """
    )

    joined = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE joined=0
        """
    )

    not_joined = cur.fetchone()[0]

    cur.execute(
        "SELECT COALESCE(SUM(points), 0) FROM users"
    )

    total_points = cur.fetchone()[0]

    # ---------------------------------
    # رتبه‌بندی بر اساس امتیاز
    # ---------------------------------

    cur.execute(
        """
        SELECT
            id,
            username,
            first_name,
            points
        FROM users
        WHERE points > 0
        ORDER BY points DESC, id ASC
        LIMIT 30
        """
    )

    users = cur.fetchall()

    text = (
        "📊 آمار ربات\n\n"
        f"👥 کل کاربران: {total}\n"
        f"✅ اعضای تأییدشده: {joined}\n"
        f"❌ تأییدنشده: {not_joined}\n"
        f"⭐ مجموع امتیازها: {total_points}\n\n"
        "🏆 برترین کاربران بر اساس امتیاز:\n\n"
    )

    if not users:

        text += "هنوز امتیازی ثبت نشده."

    else:

        for i, row in enumerate(users, start=1):

            user_id = row[0]
            username = row[1]
            first_name = row[2]
            points = row[3]

            if username:
                name = f"@{username}"

            else:
                name = first_name or str(user_id)

            text += (
                f"{i}. {name}\n"
                f"   🆔 ID: {user_id}\n"
                f"   ⭐ امتیاز: {points}\n\n"
            )

    # تلگرام محدودیت طول پیام دارد
    if len(text) <= 4000:

        await update.message.reply_text(text)

    else:

        await update.message.reply_text(
            text[:4000]
        )


# =====================================
# لیست اعضا + امتیاز
# =====================================

async def members(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute(
        """
        SELECT
            id,
            username,
            first_name,
            invited_by,
            points,
            joined
        FROM users
        ORDER BY points DESC, id DESC
        """
    )

    rows = cur.fetchall()

    if not rows:

        await update.message.reply_text(
            "👥 هنوز کاربری ثبت نشده."
        )

        return

    text = "👥 لیست کاربران\n\n"

    for i, row in enumerate(rows, start=1):

        user_id = row[0]
        username = row[1]
        first_name = row[2]
        invited_by = row[3]
        points = row[4]
        joined = row[5]

        if username:
            name = f"@{username}"

        else:
            name = first_name or str(user_id)

        status = "✅" if joined else "❌"

        text += (
            f"{i}. {name}\n"
            f"   🆔 ID: {user_id}\n"
            f"   📢 عضویت: {status}\n"
            f"   ⭐ امتیاز: {points}\n"
            f"   👥 دعوت‌کننده: "
            f"{invited_by if invited_by else 'ندارد'}\n\n"
        )

        # جلوگیری از عبور از محدودیت تلگرام
        if len(text) > 3500:

            await update.message.reply_text(text)

            text = "👥 ادامه لیست:\n\n"

    if text.strip() != "👥 ادامه لیست:":

        await update.message.reply_text(text)


# =====================================
# ارسال پیام همگانی
# =====================================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:

        await update.message.reply_text(
            "نحوه استفاده:\n\n"
            "/broadcast متن پیام"
        )

        return

    message = " ".join(context.args)

    cur.execute(
        "SELECT id FROM users"
    )

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


# =====================================
# اجرای ربات
# =====================================

def main():

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin
        )
    )

    app.add_handler(
        CommandHandler(
            "stats",
            stats
        )
    )

    app.add_handler(
        CommandHandler(
            "members",
            members
        )
    )

    app.add_handler(
        CommandHandler(
            "broadcast",
            broadcast
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            buttons
        )
    )

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
```
