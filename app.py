from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import asyncio

BASE_URL = "https://www.bsebexam.com"

# ===== SCRAPER =====
def get_session():
    return requests.Session()

def get_token(session):
    res = session.get(BASE_URL)
    soup = BeautifulSoup(res.text, "html.parser")
    token = soup.find("input", {"name": "__RequestVerificationToken"})
    return token.get("value") if token else None

def normalize_subject(name):
    return name.strip().lower() if name else None

def fetch_result(session, token, rollcode, rollno):
    url = BASE_URL + "/Result/GetResult"
    payload = {
        "rollcode": rollcode,
        "rollno": rollno,
        "captcha": "123456",
        "__RequestVerificationToken": token
    }

    res = session.post(url, data=payload)
    soup = BeautifulSoup(res.text, "html.parser")

    data = {
        "name": "", "father": "", "roll_no": rollno,
        "school": "", "total": "", "subjects": {}
    }

    for row in soup.find_all("tr"):
        cols = [c.get_text(" ", strip=True) for c in row.find_all(["td","th"])]
        if len(cols) < 2: continue

        key = cols[0].lower()
        val = cols[-1]

        if "student" in key: data["name"] = val
        elif "father" in key: data["father"] = val
        elif "school" in key: data["school"] = val
        elif "aggregate" in key: data["total"] = val
        elif len(cols) >= 5:
            sub = normalize_subject(cols[0])
            if sub: data["subjects"][sub] = val

    return data

# ===== COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send:\n/result <rollcode> <rollno> [count]\n\nExample:\n/result 31082 26010001 100"
    )

async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        rollcode = args[0]
        rollno = int(args[1])
        count = int(args[2]) if len(args) > 2 else 1

        await update.message.reply_text(f"Fetching {count} results. This may take a while...")

        session = get_session()

        def fetch(rn):
            token = get_token(session)
            return fetch_result(session, token, rollcode, str(rn))

        results = []
        batch_size = 20  # adjust for safety
        total_batches = math.ceil(count / batch_size)

        for b in range(total_batches):
            start_roll = rollno + b*batch_size
            end_roll = min(rollno + count, start_roll + batch_size)
            # Number of threads = min(count in this batch, 100)
            threads = min(end_roll - start_roll, 100)
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futures = [ex.submit(fetch, r) for r in range(start_roll, end_roll)]
                for f in as_completed(futures):
                    results.append(f.result())
            await asyncio.sleep(0.5)

        results.sort(key=lambda x: int(x["roll_no"]))

        # ===== TEXT RESPONSE =====
        msg = ""
        for r in results:
            msg += f"🎓 {r['name']}\nRoll: {r['roll_no']}\nTotal: {r['total']}\n"
            if r['subjects']:
                for sub, marks in r['subjects'].items():
                    msg += f"{sub.capitalize()}: {marks}  "
            msg += "\n\n"

            if len(msg) > 3500:
                await update.message.reply_text(msg)
                msg = ""
        if msg:
            await update.message.reply_text(msg)

        # ===== PDF RESPONSE =====
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        y = 750
        for r in results:
            p.drawString(40, y, f"{r['roll_no']} | {r['name']} | {r['total']}")
            y -= 20
            for sub, marks in r['subjects'].items():
                p.drawString(60, y, f"{sub.capitalize()}: {marks}")
                y -= 15
            y -= 10
            if y < 50:
                p.showPage()
                y = 750
        p.save()
        buffer.seek(0)

        await update.message.reply_document(InputFile(buffer, filename="results.pdf"))

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ===== MAIN =====
BOT_TOKEN = "8611852094:AAEg3BBP1_yLoNIZ1Okt-8EkvMYqSqdeTow"
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("result", result))
app.run_polling()
