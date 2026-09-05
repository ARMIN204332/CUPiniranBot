
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE joined=1")
    joined = cur.fetchone()[0]

    await update.message.reply_text(
        "🛠 پنل مدیریت\n\n"
        f"👥 کل کاربران: {total}\n"
        f"📢 اعضای تأییدشده: {joined}\n\n"
        "برای انتخاب برنده از دستور /winner استفاده کن."
    )


async def winner(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute(
        "SELECT id, username, first_name "
        "FROM users WHERE joined=1"
    )

    users = cur.fetchall()

    if not users:
        await update.message.reply_text(
            "❌ هنوز شرکت‌کننده‌ای وجود ندارد."
        )
        return

    selected = random.choice(users)

    user_id, username, first_name = selected

    await update.message.reply_text(
        "🏆 برنده قرعه‌کشی:\n\n"
        f"👤 {first_name}\n"
        f"🆔 {user_id}\n"
        f"Username: @{username if username else 'ندارد'}"
    )


def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("winner", winner))
    app.add_handler(CallbackQueryHandler(buttons))

    print("Bot started...")

    app.run_polling()


if name == "main":
    main()
