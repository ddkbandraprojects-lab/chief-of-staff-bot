"""
Chief of Staff Telegram Bot
============================
Your personal AI assistant on Telegram.
- Sends you a daily morning briefing at 8:00 AM IST
- Reply to add tasks, follow-ups, deadlines
- Ask it anything about your day

Setup: See README section at the bottom of this file.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, time
import pytz
from groq import Groq
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8435492336:AAH3pAPnfVG-5j2Uou0BuIJWgSNuWHavwEE")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
CHAT_ID = 1365478870
IST = pytz.timezone("Asia/Kolkata")
BRIEFING_HOUR = 8    # 8:00 AM IST
BRIEFING_MINUTE = 0
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "chief_data.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── DATA STORE ───────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"tasks": [], "followups": [], "deadlines": [], "chat_history": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_context(data):
    today = datetime.now(IST).strftime("%A, %d %b %Y")
    pending_tasks = [t for t in data["tasks"] if not t.get("done")]
    pending_fus = [f for f in data["followups"] if not f.get("done")]
    pending_dls = [d for d in data["deadlines"] if not d.get("done")]
    return (
        f"Today is {today} IST.\n"
        f"Pending tasks ({len(pending_tasks)}): {json.dumps(pending_tasks)}\n"
        f"Pending follow-ups ({len(pending_fus)}): {json.dumps(pending_fus)}\n"
        f"Upcoming deadlines ({len(pending_dls)}): {json.dumps(pending_dls)}"
    )

SYSTEM_PROMPT = """You are Nikhil Kulkarni's calm, firm personal chief of staff. 
You manage his tasks, follow-ups, deadlines, and help him stay focused as a structural engineer.
No drama, no fluff. Be direct and specific. 
When he adds items, confirm clearly and suggest priority if obvious.
When he asks for a briefing, be concise — what matters most today, what is overdue, what he might be avoiding.
Keep replies under 200 words. Use plain text, no markdown formatting (this is Telegram)."""

# ─── AI CALL ──────────────────────────────────────────────────────────────────
def ask_claude(user_message: str, data: dict) -> str:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        history = data.get("chat_history", [])[-50:]
        context_msg = f"[Current data: {get_context(data)}]\n\n{user_message}"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": context_msg}]
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=400,
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

# ─── BRIEFING ─────────────────────────────────────────────────────────────────
async def send_briefing(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    briefing_prompt = (
        "Give Nikhil his morning briefing. What must he do today? "
        "What is overdue? What follow-up is he probably avoiding? "
        "End with one clear instruction for where to start."
    )
    reply = ask_claude(briefing_prompt, data)
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"Good morning, Nikhil.\n\n{reply}"
    )

# ─── COMMANDS ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Chief of Staff online, Nikhil.\n\n"
        "Commands:\n"
        "/task <text> — add a task\n"
        "/followup <text> — add a follow-up\n"
        "/deadline <text> | <date YYYY-MM-DD> — add a deadline\n"
        "/list — show everything pending\n"
        "/done <task text> — mark something done\n"
        "/brief — get your briefing now\n"
        "/clear — clear all completed items\n\n"
        "Or just type anything and I will handle it."
    )

async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /task Buy cement samples")
        return
    data = load_data()
    data["tasks"].append({"text": text, "priority": "today", "done": False,
                           "added": datetime.now(IST).strftime("%d %b")})
    save_data(data)
    reply = ask_claude(f"I just added a task: '{text}'. Acknowledge briefly and tell me where it fits in today.", data)
    await update.message.reply_text(reply)

async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Usage: /followup Client XYZ re: invoice")
        return
    data = load_data()
    data["followups"].append({"text": text, "when": "today", "done": False,
                               "added": datetime.now(IST).strftime("%d %b")})
    save_data(data)
    reply = ask_claude(f"I just added a follow-up: '{text}'. Acknowledge and flag if this seems overdue.", data)
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
             "added": datetime.now(IST).strftime("%d %b")}
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
    reply = ask_claude(f"I just added a deadline: '{text}' on {date_str}. Acknowledge and tell me if I should be worried.", data)
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
        await update.message.reply_text("Nothing pending. Either you are very organised or you haven't added anything yet.")
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
        await update.message.reply_text(f"Marked done. Good. What is next?")
    else:
        await update.message.reply_text(f"Could not find '{text}' in your pending items. Check /list.")

async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    reply = ask_claude(
        "Give me a sharp briefing right now. What is most important, what is overdue, what am I avoiding?",
        data
    )
    await update.message.reply_text(reply)

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    before = sum(1 for lst in [data["tasks"], data["followups"], data["deadlines"]] for x in lst if x.get("done"))
    data["tasks"] = [t for t in data["tasks"] if not t.get("done")]
    data["followups"] = [f for f in data["followups"] if not f.get("done")]
    data["deadlines"] = [d for d in data["deadlines"] if not d.get("done")]
    save_data(data)
    await update.message.reply_text(f"Cleared {before} completed items. List is clean.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    data = load_data()
    reply = ask_claude(text, data)
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = app.job_queue
    briefing_time = time(hour=BRIEFING_HOUR, minute=BRIEFING_MINUTE, tzinfo=IST)
    job_queue.run_daily(send_briefing, time=briefing_time, name="daily_briefing")

    logger.info("Chief of Staff bot is running...")

    async def on_startup(app):
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="Chief of Staff is back online. Your tasks and history are intact. Type /brief to continue."
        )

    app.post_init = on_startup
    app.run_polling()

if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════════════════════
# README — HOW TO DEPLOY (FREE, 15 minutes)
# ═══════════════════════════════════════════════════════════════════════════════
#
# WHAT YOU NEED:
#   1. Your Telegram token (already in the script)
#   2. An Anthropic API key — get one free at https://console.anthropic.com
#   3. A free Railway account — https://railway.app (sign in with GitHub)
#
# STEP 1 — Get your Anthropic API key:
#   - Go to https://console.anthropic.com
#   - Sign up free → API Keys → Create Key
#   - Copy it
#
# STEP 2 — Deploy on Railway (free hosting):
#   - Go to https://railway.app → New Project → Deploy from GitHub
#   - OR use the simpler option: New Project → "Empty Project"
#   - Upload these two files:
#       chief_of_staff_bot.py   (this file)
#       requirements.txt        (see below)
#
# STEP 3 — Set environment variables in Railway:
#   TELEGRAM_TOKEN = 8435492336:AAH3pAPnfVG-5j2Uou0BuIJWgSNuWHavwEE
#   GROQ_API_KEY   = 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
#
# STEP 4 — requirements.txt contents:
#   python-telegram-bot[job-queue]==21.5
#   anthropic
#   pytz
#
# STEP 5 — Set start command in Railway:
#   python chief_of_staff_bot.py
#
# That is it. The bot will:
#   - Message you every morning at 8:00 AM IST with your briefing
#   - Respond to your messages all day
#   - Remember your tasks between sessions (saved in chief_data.json)
#
# COMMANDS SUMMARY:
#   /start              — show all commands
#   /task <text>        — add a task
#   /followup <text>    — add a follow-up
#   /deadline <text> | <YYYY-MM-DD>  — add a deadline with date
#   /list               — see everything pending
#   /done <text>        — mark an item done
#   /brief              — get your briefing now
#   /clear              — remove completed items
#   (or just type anything — the AI will handle it)
#
# SECURITY NOTE:
#   After setup, regenerate your Telegram token via @BotFather → /revoke
#   and update it in Railway environment variables.
# ═══════════════════════════════════════════════════════════════════════════════
