import requests
import google.generativeai as genai
import os
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext, CommandHandler

# 🔹 تنظیمات API
TELEGRAM_BOT_TOKEN = "توکن ربات تلگرام"   # توکن ربات تلگرام خود را وارد کنید
GEMINI_API_KEY = "کلید API جمینای"       # کلید API جمینای خود را وارد کنید

# 🔹 مقداردهی مدل Google Gemini
genai.configure(api_key=GEMINI_API_KEY)

# 🛑 دیکشنری برای ذخیره وضعیت کاربران (لینک و عکس)
user_data = {}

# 📌 مسیر ذخیره‌سازی موقت در Render
TEMP_DIR = "/tmp/downloads"

# ایجاد پوشه downloads اگر وجود ندارد
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# 📌 شروع ربات - درخواست لینک
async def start(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    user_data[user_id] = {"step": "waiting_for_link"}
    
    await update.message.reply_text("👋 سلام! لطفاً لینک مطلب را ارسال کنید.")

# 📌 دریافت لینک و درخواست تصویر
async def handle_link(update: Update, context: CallbackContext):
    user_id = update.message.chat_id

    url = update.message.text.strip()

    if "vernoco.com" not in url:
        await update.message.reply_text("⚠️ لطفاً یک لینک معتبر از سایت vernoco.com ارسال کنید.")
        return

    # ذخیره لینک و تغییر وضعیت کاربر به دریافت تصویر
    user_data[user_id] = {"url": url}
    
    await update.message.reply_text("📸 لطفاً یک تصویر ارسال کنید.")

# 📌 دریافت متن مقاله از سایت
def get_page_content(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # دریافت عنوان از <h1> یا Meta Title
        title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)
        else:
            meta_title = soup.find("meta", property="og:title")
            title = meta_title["content"] if meta_title and meta_title["content"] else soup.title.string

        # دریافت متن مقاله (۵ پاراگراف اول)
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text() for p in paragraphs[:5])

        return title, text
    except Exception as e:
        return None, f"⚠️ خطا در دریافت محتوا: {e}"

# 📌 خلاصه‌سازی متن با Google Gemini
async def summarize_text(text):
    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(f"متن زیر را خلاصه کن:\n{text}")
        return response.text.strip()
    except Exception as e:
        return f"⚠️ خطا در خلاصه‌سازی: {e}"

# 📌 دریافت تصویر و ارسال نتیجه نهایی
async def handle_image(update: Update, context: CallbackContext):
    user_id = update.message.chat_id

    if user_id in user_data:
        url = user_data[user_id]["url"]

        # دریافت عنوان و متن مقاله
        title, text = get_page_content(url)
        if not text:
            await update.message.reply_text("⚠️ خطا در دریافت محتوای صفحه.")
            return

        # خلاصه‌سازی متن
        summarized_text = await summarize_text(text)

        # کپشن برای پیام با تصویر
        caption_with_image = f"🔻 {title}\n\n{summarized_text}\n\nبرای مطالعه کامل مقاله به لینک زیر مراجعه نمائید.\n[🔗 مطالعه کامل مقاله]({url})"
        
        # ارسال پیام همراه با تصویر
        if update.message.photo:
            # دریافت آخرین نسخه عکس با بالاترین کیفیت
            photo_file = await update.message.photo[-1].get_file()
            await context.bot.send_photo(chat_id=user_id, photo=photo_file.file_id, caption=caption_with_image, parse_mode="Markdown")

        elif update.message.document:
            # اگر فایل ارسال شده از نوع عکس بود، آن را دانلود و مجدداً ارسال می‌کنیم
            document = update.message.document
            if document.mime_type.startswith("image/"):  # بررسی اینکه فرمت فایل عکس است
                file_path = await document.get_file()
                file_name = f"{user_id}.jpg"
                local_path = os.path.join(TEMP_DIR, file_name)  # ذخیره در مسیر موقت Render

                # دانلود تصویر
                await file_path.download_to_drive(local_path)

                # ارسال عکس به همراه کپشن
                with open(local_path, "rb") as img:
                    await context.bot.send_photo(chat_id=user_id, photo=img, caption=caption_with_image, parse_mode="Markdown")

                # حذف فایل پس از ارسال
                os.remove(local_path)
            else:
                await update.message.reply_text("⚠️ لطفاً یک فایل تصویری معتبر ارسال کنید.")

        else:
            await update.message.reply_text("⚠️ لطفاً یک عکس یا فایل تصویری ارسال کنید.")

        # ارسال پیام بدون تصویر
        caption_without_image = f"🔻 {title}\n\n{summarized_text}\n\nبرای مطالعه کامل مقاله به سایت ورنو مراجعه نمائید.\n🌏 [www.vernoco.com]"
        await update.message.reply_text(caption_without_image, parse_mode="Markdown")

        # پاک کردن داده‌های کاربر پس از ارسال تصویر
        del user_data[user_id]
    else:
        await update.message.reply_text("⚠️ لطفاً ابتدا لینک را ارسال کنید.")

# 📌 راه‌اندازی ربات
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))

    application.run_polling()

if __name__ == "__main__":
    main()
