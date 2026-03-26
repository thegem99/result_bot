from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://www.bsebexam.com"
SUBJECTS = ["english","hindi","physics","chemistry","mathematics","biology"]

# ===== SCRAPER (same as yours) =====
def get_session():
    return requests.Session()

def get_token(session):
    res = session.get(BASE_URL)
    soup = BeautifulSoup(res.text, "html.parser")
    token = soup.find("input", {"name": "__RequestVerificationToken"})
    return token.get("value") if token else None

def normalize_subject(name):
    name = name.lower()
    if "math" in name: return "mathematics"
    if "bio" in name: return "biology"
    if "physic" in name: return "physics"
    if "chem" in name: return "chemistry"
    if "english" in name: return "english"
    if "hindi" in name: return "hindi"
    return None

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
        "Send:\n/result <rollcode> <rollno> [count]\n\nExample:\n/result 12345 67890 5"
    )

async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        rollcode = args[0]
        rollno = int(args[1])
        count = int(args[2]) if len(args) > 2 else 1
        count = min(count, 20)

        await update.message.reply_text("Fetching results...")

        session = get_session()

        def fetch(rn):
            token = get_token(session)
            return fetch_result(session, token, rollcode, str(rn))

        results = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(fetch, rollno+i) for i in range(count)]
            for f in as_completed(futures):
                results.append(f.result())

        results.sort(key=lambda x: int(x["roll_no"]))

        # TEXT RESPONSE
        msg = ""
        for r in results:
            msg += f"🎓 {r['name']}\n"
            msg += f"Roll: {r['roll_no']}\n"
            msg += f"Total: {r['total']}\n\n"

        await update.message.reply_text(msg[:4000])

        # SEND PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        y = 750

        for r in results:
            line = f"{r['roll_no']} | {r['name']} | {r['total']}"
            p.drawString(40, y, line)
            y -= 20

        p.save()
        buffer.seek(0)

        await update.message.reply_document(
            document=InputFile(buffer, filename="results.pdf")
        )

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ===== MAIN =====
app = ApplicationBuilder().token("8611852094:AAEg3BBP1_yLoNIZ1Okt-8EkvMYqSqdeTow").build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("result", result))

app.run_polling()
