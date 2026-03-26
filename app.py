from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    name = name.lower()
    if "math" in name: return "Mathematics"
    if "bio" in name: return "Biology"
    if "physic" in name: return "Physics"
    if "chem" in name: return "Chemistry"
    if "english" in name: return "English"
    if "hindi" in name: return "Hindi"
    return name.title()

def fetch_result(rollcode, rollno):
    try:
        session = get_session()           # New session per fetch
        token = get_token(session)        # Fresh token
        url = BASE_URL + "/Result/GetResult"
        payload = {
            "rollcode": rollcode,
            "rollno": str(rollno),
            "captcha": "123456",
            "__RequestVerificationToken": token
        }

        res = session.post(url, data=payload)
        soup = BeautifulSoup(res.text, "html.parser")

        data = {
            "name": "",
            "roll_no": str(rollno),
            "total": "",
            "subjects": {}
        }

        for row in soup.find_all("tr"):
            cols = [c.get_text(" ", strip=True) for c in row.find_all(["td","th"])]
            if len(cols) < 2:
                continue

            key = cols[0].lower()
            val = cols[-1]

            if "student" in key:
                data["name"] = val
            elif "aggregate" in key:
                data["total"] = val
            elif len(cols) >= 5:
                sub = normalize_subject(cols[0])
                if sub:
                    data["subjects"][sub] = val

        return data
    except Exception as e:
        # If fetching fails, return a placeholder
        return {"name":"N/A","roll_no":str(rollno),"total":"N/A","subjects":{}}

# ===== COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send:\n/result <rollcode> <rollno> [count]\n\nExample:\n/result 31082 26010001 5"
    )

async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Usage: /result <rollcode> <rollno> [count]")
            return

        rollcode = args[0]
        rollno = int(args[1])
        count = int(args[2]) if len(args) > 2 else 1

        await update.message.reply_text(f"Fetching {count} results... Please wait.")

        results = []
        with ThreadPoolExecutor(max_workers=min(count, 100)) as ex:
            futures = [ex.submit(fetch_result, rollcode, rollno+i) for i in range(count)]
            for f in as_completed(futures):
                results.append(f.result())

        results.sort(key=lambda x: int(x["roll_no"]))

        # ===== TEXT OUTPUT =====
        msg = ""
        for r in results:
            msg += f"🎓 {r['name']} (Roll: {r['roll_no']})\n"
            for sub, mark in r["subjects"].items():
                msg += f"   {sub:<12}: {mark}\n"
            msg += f"   {'Total':<12}: {r['total']}\n\n"

        await update.message.reply_text(msg[:4000])

        # ===== PDF OUTPUT =====
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        y = height - 40

        for r in results:
            p.setFont("Helvetica-Bold", 10)
            p.drawString(40, y, f"{r['roll_no']} | {r['name']} | Total: {r['total']}")
            y -= 15
            p.setFont("Helvetica", 9)
            for sub, mark in r["subjects"].items():
                p.drawString(60, y, f"{sub:<12}: {mark}")
                y -= 12
            y -= 10
            if y < 50:
                p.showPage()
                y = height - 40

        p.save()
        buffer.seek(0)

        await update.message.reply_document(
            document=InputFile(buffer, filename="results.pdf")
        )

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ===== MAIN =====
TOKEN = "8611852094:AAEg3BBP1_yLoNIZ1Okt-8EkvMYqSqdeTow"  # <-- Your bot token

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("result", result))
app.run_polling()
