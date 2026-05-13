"""
Chief of Staff Telegram Bot - Full Version
===========================================
Features:
- Tasks, follow-ups, deadlines management
- Persistent memory across restarts
- Long-term memory notes (/remember)
- Archive search (/search)
- OCR — send any image, bot extracts and saves the text
- Daily briefing
"""

import os
from dotenv import load_dotenv
import json
import base64
import logging
from datetime import datetime, time
import pytz

# Load .env file
SCRIPT_DIR_TEMP = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR_TEMP, ".env"))
from groq import Groq
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CHAT_ID = 1365478870
IST = pytz.timezone("Asia/Kolkata")
BRIEFING_HOUR = 8
BRIEFING_MINUTE = 0
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "chief_data.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── DATA STORE ───────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data.setdefault("tasks", [])
    data.setdefault("followups", [])
    data.setdefault("deadlines", [])
    data.setdefault("chat_history", [])
    data.setdefault("memories", [])
    data.setdefault("ocr_archive", [])
    return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_context(data):
    today = datetime.now(IST).strftime("%A, %d %b %Y")
    pending_tasks = [t for t in data["tasks"] if not t.get("done")]
    pending_fus = [f for f in data["followups"] if not f.get("done")]
    pending_dls = [d for d in data["deadlines"] if not d.get("done")]
    memories = data.get("memories", [])
    return (
        f"Today is {today} IST.\n"
        f"Pending tasks ({len(pending_tasks)}): {json.dumps(pending_tasks)}\n"
        f"Pending follow-ups ({len(pending_fus)}): {json.dumps(pending_fus)}\n"
        f"Upcoming deadlines ({len(pending_dls)}): {json.dumps(pending_dls)}\n"
        f"Permanent memories ({len(memories)}): {json.dumps(memories)}"
    )

SYSTEM_PROMPT = """You are Nikhil Kulkarni's calm, firm personal chief of staff.
You manage his tasks, follow-ups, deadlines, and help him stay focused as a structural engineer.
No drama, no fluff. Be direct and specific.
When he adds items, confirm clearly and suggest priority if obvious.
When he asks for a briefing, be concise — what matters most today, what is overdue, what he might be avoiding.
You have access to his permanent memory notes — refer to them when relevant.
Keep replies under 200 words. Use plain text, no markdown formatting (this is Telegram)."""

# ─── AI CALL ──────────────────────────────────────────────────────────────────
def ask_ai(user_message: str, data: dict) -> str:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        history = data.get("chat_history", [])[-50:]
        context_msg = f"[Current data: {get_context(data)}]\n\n{user_message}"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": context_msg}]
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=500,
            messages=messages
        )
        reply = response.choices[0].message.content
        data["chat_history"].append({"role": "user", "content": user_message})
        data["chat_history"].append({"role": "assistant", "content": reply})
        if len(data["chat_history"]) > 5000:
            data["chat_history"] = data["chat_history"][-5000:]
        save_data(data)
        return reply
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "I hit a snag connecting to AI. Your data is safe. Try again in a moment."

# ─── OCR via Groq Vision ──────────────────────────────────────────────────────
def ocr_image(image_bytes: bytes) -> str:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                    },
                    {
                        "type": "text",
                        "text": "Extract ALL text from this image exactly as it appears. Include every word, number, and symbol. If it is a document or note, preserve the structure. If there is no text, describe what you see briefly."
                    }
                ]
            }]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return None

# ─── BRIEFING ─────────────────────────────────────────────────────────────────
async def send_briefing(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    reply = ask_ai(
        "Give Nikhil his morning briefing. What must he do today? "
        "What is overdue? What follow-up is he probably avoiding? "
        "End with one clear instruction for where to start.",
        data
    )
    await context.bot.send_message(chat_id=CHAT_ID, text=f"Good morning, Nikhil.\n\n{reply}")

# ─── COMMANDS ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Chief of Staff online, Nikhil.\n\n"
        "TASK MANAGEMENT:\n"
        "/task <text> — add a task\n"
        "/followup <text> — add a follow-up\n"
        "/deadline <text> | <YYYY-MM-DD> — add a deadline\n"
        "/list — show everything pending\n"
        "/done <text> — mark something done\n"
        "/clear — remove completed items\n\n"
        "MEMORY:\n"
        "/remember <text> — save something permanently\n"
        "/memories — show all memory notes\n"
        "/forget <text> — delete a memory note\n\n"
        "SEARCH:\n"
        "/search <keyword> — search all history and archive\n\n"
        "BRIEFING:\n"
        "/brief — get your briefing now\n\n"
        "OCR:\n"
        "Send any photo — bot extracts and saves the text\n\n"
        "Or just type anything naturally."
    )

async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /task Follow up on RCC drawing approval")
        return
    data = load_data()
    data["tasks"].append({"text": text, "priority": "today", "done": False,
                           "added": datetime.now(IST).strftime("%d %b %Y %H:%M")})
    save_data(data)
    reply = ask_ai(f"Task added: '{text}'. Acknowledge briefly and suggest priority.", data)
    await update.message.reply_text(reply)

async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /followup Client XYZ re: invoice")
        return
    data = load_data()
    data["followups"].append({"text": text, "when": "today", "done": False,
                               "added": datetime.now(IST).strftime("%d %b %Y %H:%M")})
    save_data(data)
    reply = ask_ai(f"Follow-up added: '{text}'. Acknowledge and flag if overdue.", data)
    await update.message.reply_text(reply)

async def cmd_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args)
    if "|" in raw:
        parts = raw.split("|")
        text = parts[0].strip()
        date_str = parts[1].strip()
    else:
        text = raw
        date_str = ""
    if not text:
        await update.message.reply_text("Usage: /deadline Submit drawings | 2026-05-20")
        return
    data = load_data()
    entry = {"text": text, "date": date_str, "done": False,
             "added": datetime.now(IST).strftime("%d %b %Y %H:%M")}
    if date_str:
        try:
            dl = datetime.strptime(date_str, "%Y-%m-%d")
            diff = (dl.date() - datetime.now(IST).date()).days
            entry["diff"] = diff
            entry["status"] = "overdue" if diff < 0 else "today" if diff == 0 else "urgent" if diff <= 3 else "soon"
        except:
            entry["diff"] = 99
            entry["status"] = "soon"
    data["deadlines"].append(entry)
    save_data(data)
    reply = ask_ai(f"Deadline added: '{text}' on {date_str}. Should I be worried?", data)
    await update.message.reply_text(reply)

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    lines = []
    pending_tasks = [t for t in data["tasks"] if not t.get("done")]
    pending_fus = [f for f in data["followups"] if not f.get("done")]
    pending_dls = [d for d in data["deadlines"] if not d.get("done")]
    if pending_tasks:
        lines.append("TASKS:")
        for t in pending_tasks:
            lines.append(f"  - {t['text']} [{t.get('priority','today')}]")
    if pending_fus:
        lines.append("\nFOLLOW-UPS:")
        for f in pending_fus:
            lines.append(f"  - {f['text']}")
    if pending_dls:
        lines.append("\nDEADLINES:")
        for d in pending_dls:
            suffix = f" ({d['date']})" if d.get("date") else ""
            lines.append(f"  - {d['text']}{suffix}")
    if not lines:
        await update.message.reply_text("Nothing pending. Add tasks with /task, /followup, or /deadline.")
        return
    await update.message.reply_text("\n".join(lines))

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).lower()
    if not text:
        await update.message.reply_text("Usage: /done <part of task name>")
        return
    data = load_data()
    matched = False
    for lst in [data["tasks"], data["followups"], data["deadlines"]]:
        for item in lst:
            if text in item["text"].lower() and not item.get("done"):
                item["done"] = True
                matched = True
                break
    save_data(data)
    if matched:
        await update.message.reply_text("Marked done. Good. What is next?")
    else:
        await update.message.reply_text(f"Could not find '{text}' in pending items. Check /list.")

async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    reply = ask_ai("Give me a sharp briefing. What is most important, what is overdue, what am I avoiding?", data)
    await update.message.reply_text(reply)

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    before = sum(1 for lst in [data["tasks"], data["followups"], data["deadlines"]] for x in lst if x.get("done"))
    data["tasks"] = [t for t in data["tasks"] if not t.get("done")]
    data["followups"] = [f for f in data["followups"] if not f.get("done")]
    data["deadlines"] = [d for d in data["deadlines"] if not d.get("done")]
    save_data(data)
    await update.message.reply_text(f"Cleared {before} completed items. List is clean.")

# ─── MEMORY COMMANDS ──────────────────────────────────────────────────────────
async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /remember Client ABC prefers calls after 5 PM")
        return
    data = load_data()
    data["memories"].append({
        "text": text,
        "saved": datetime.now(IST).strftime("%d %b %Y %H:%M")
    })
    save_data(data)
    await update.message.reply_text(f"Remembered permanently:\n\"{text}\"\n\nI will refer to this in every future conversation.")

async def cmd_memories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    memories = data.get("memories", [])
    if not memories:
        await update.message.reply_text("No memories saved yet. Use /remember <text> to save something permanently.")
        return
    lines = ["PERMANENT MEMORIES:\n"]
    for i, m in enumerate(memories, 1):
        lines.append(f"{i}. {m['text']}\n   saved: {m.get('saved', '?')}")
    await update.message.reply_text("\n".join(lines))

async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).lower()
    if not text:
        await update.message.reply_text("Usage: /forget <part of memory text>")
        return
    data = load_data()
    before = len(data["memories"])
    data["memories"] = [m for m in data["memories"] if text not in m["text"].lower()]
    removed = before - len(data["memories"])
    save_data(data)
    if removed:
        await update.message.reply_text(f"Removed {removed} memory note(s) matching '{text}'.")
    else:
        await update.message.reply_text(f"No memory found matching '{text}'. Check /memories.")

# ─── SEARCH COMMAND ───────────────────────────────────────────────────────────
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = " ".join(context.args).lower()
    if not keyword:
        await update.message.reply_text("Usage: /search ramesh")
        return
    data = load_data()
    results = []

    for t in data["tasks"]:
        if keyword in t["text"].lower():
            status = "done" if t.get("done") else "pending"
            results.append(f"[TASK/{status}] {t['text']} (added: {t.get('added','?')})")

    for f in data["followups"]:
        if keyword in f["text"].lower():
            status = "done" if f.get("done") else "pending"
            results.append(f"[FOLLOWUP/{status}] {f['text']} (added: {f.get('added','?')})")

    for d in data["deadlines"]:
        if keyword in d["text"].lower():
            status = "done" if d.get("done") else "pending"
            results.append(f"[DEADLINE/{status}] {d['text']} {d.get('date','')} (added: {d.get('added','?')})")

    for m in data.get("memories", []):
        if keyword in m["text"].lower():
            results.append(f"[MEMORY] {m['text']} (saved: {m.get('saved','?')})")

    for o in data.get("ocr_archive", []):
        if keyword in o["text"].lower():
            preview = o["text"][:150] + "..." if len(o["text"]) > 150 else o["text"]
            results.append(f"[IMAGE TEXT/{o.get('date','?')}] {preview}")

    chat_hits = 0
    for msg in data.get("chat_history", []):
        if keyword in msg.get("content", "").lower() and chat_hits < 5:
            preview = msg["content"][:120] + "..." if len(msg["content"]) > 120 else msg["content"]
            role = "You" if msg["role"] == "user" else "Bot"
            results.append(f"[CHAT/{role}] {preview}")
            chat_hits += 1

    if not results:
        await update.message.reply_text(f"No results for '{keyword}' across tasks, follow-ups, deadlines, memories, OCR archive, or chat history.")
        return

    header = f"Results for '{keyword}' ({len(results)} found):\n\n"
    body = "\n\n".join(results[:20])
    if len(results) > 20:
        body += f"\n\n...and {len(results) - 20} more."
    await update.message.reply_text(header + body)

# ─── OCR — IMAGE HANDLER ──────────────────────────────────────────────────────
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Reading image, please wait...")
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        extracted_text = ocr_image(bytes(image_bytes))
        if not extracted_text:
            await update.message.reply_text("Could not extract text. Try a clearer photo.")
            return
        data = load_data()
        data["ocr_archive"].append({
            "text": extracted_text,
            "date": datetime.now(IST).strftime("%d %b %Y %H:%M"),
            "file_id": photo.file_id
        })
        save_data(data)
        reply = f"Text extracted and saved:\n\n{extracted_text[:800]}"
        if len(extracted_text) > 800:
            reply += f"\n\n...({len(extracted_text) - 800} more characters saved)"
        reply += "\n\nUse /search <keyword> to find this later."
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Image error: {e}")
        await update.message.reply_text("Something went wrong. Try again.")

# ─── TEXT MESSAGE HANDLER ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    data = load_data()
    reply = ask_ai(text, data)
    await update.message.reply_text(reply)

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler("followup", cmd_followup))
    app.add_handler(CommandHandler("deadline", cmd_deadline))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("memories", cmd_memories))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = app.job_queue
    briefing_time = time(hour=BRIEFING_HOUR, minute=BRIEFING_MINUTE, tzinfo=IST)
    job_queue.run_daily(send_briefing, time=briefing_time, name="daily_briefing")

    logger.info("Chief of Staff bot is running...")

    async def on_startup(app):
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="Chief of Staff back online. New features:\n\n"
                 "/remember — save permanent notes\n"
                 "/memories — view all memories\n"
                 "/forget — delete a memory\n"
                 "/search — search everything\n"
                 "Send a photo — extracts and saves text\n\n"
                 "Type /start to see all commands."
        )

    app.post_init = on_startup
    app.run_polling()

if __name__ == "__main__":
    main()
