import os
import asyncio
import threading
import uuid
from flask import Flask, Response
from pyrogram import Client, filters
from pyrogram.types import Message

# ===== Render Environment Variables থেকে মান নেওয়া =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BIN_CHANNEL = int(os.environ.get("BIN_CHANNEL"))
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", f"http://0.0.0.0:{PORT}")

FILE_STORE = {}

app_bot = Client(
    "file_link_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=4
)

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "✅ Bot is running! Forward a file to the bot to get a download link."


def stream_from_telegram(msg, inline=False):
    """Telegram API থেকে ফাইল স্ট্রিম করা"""
    file_name = getattr(msg, "file_name", None) or "file.mp4"
    mime_type = getattr(msg, "mime_type", None) or "video/mp4"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    file_path = loop.run_until_complete(
        app_bot.download_media(msg, file_name=f"/tmp/{uuid.uuid4()}_{file_name}")
    )

    def generate():
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        try:
            os.remove(file_path)
        except:
            pass

    disposition = "inline" if inline else "attachment"
    return Response(
        generate(),
        mimetype=mime_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Content-Length": str(msg.file_size or 0)
        }
    )


@flask_app.route("/download/<file_id>")
def download_file(file_id):
    if file_id not in FILE_STORE:
        return "❌ File not found or expired.", 404
    try:
        msg = app_bot.get_messages(BIN_CHANNEL, FILE_STORE[file_id])
        if not msg or not msg.media:
            return "❌ File not found.", 404
        return stream_from_telegram(msg, inline=False)
    except Exception as e:
        return f"❌ Error: {str(e)}", 500


@flask_app.route("/stream/<file_id>")
def stream_file(file_id):
    if file_id not in FILE_STORE:
        return "❌ File not found.", 404
    try:
        msg = app_bot.get_messages(BIN_CHANNEL, FILE_STORE[file_id])
        if not msg or not msg.media:
            return "❌ File not found.", 404
        return stream_from_telegram(msg, inline=True)
    except Exception as e:
        return f"❌ Error: {str(e)}", 500


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


@app_bot.on_message(filters.private & filters.command("start"))
async def start_handler(client, message: Message):
    await message.reply(
        "👋 **Welcome!**\n\n"
        "📤 Send me any file (video, document, etc.) and I will generate a direct download link.\n\n"
        "⚡ Download or play directly in your browser — no Telegram needed!"
    )


@app_bot.on_message(filters.private & (filters.video | filters.document | filters.audio | filters.photo))
async def file_handler(client, message: Message):
    try:
        await message.reply("⏳ Processing your file, please wait...")
        forwarded = await message.copy(BIN_CHANNEL)

        file_id = str(uuid.uuid4())[:12].upper()
        FILE_STORE[file_id] = forwarded.id

        download_url = f"{HOST}/download/{file_id}"
        stream_url = f"{HOST}/stream/{file_id}"

        file_name = "file"
        file_size = 0
        if message.document:
            file_name = message.document.file_name
            file_size = message.document.file_size
        elif message.video:
            file_name = message.video.file_name or "video.mp4"
            file_size = message.video.file_size

        await message.reply(
            f"✅ **File Saved!**\n\n"
            f"📁 `{file_name}`\n"
            f"💾 `{round(file_size / 1024 / 1024, 2)} MB`\n\n"
            f"🔗 **Download Link:**\n`{download_url}`\n\n"
            f"▶️ **Stream Link:**\n`{stream_url}`\n\n"
            f"💡 Click to download/play directly in browser!"
        )
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("🚀 Starting bot...")
    app_bot.run()
