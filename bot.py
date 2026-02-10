import google.generativeai as genai
import json
from datetime import datetime 
from dotenv import load_dotenv
import os
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
# Added CommandHandler
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
import nest_asyncio

load_dotenv()
nest_asyncio.apply() 

api_key=os.getenv("GOOGLE_API_KEY")
telegram_token=os.getenv("TELEGRAM_TOKEN")

if not api_key or not telegram_token:
    print("❌ ERROR: Missing keys!")
    
genai.configure(api_key=api_key)

model = genai.GenerativeModel("gemini-flash-latest", generation_config={"response_mime_type": "application/json"})

# --- HELPER FUNCTIONS ---

def get_sheet_data():
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds=Credentials.from_service_account_file("credentials.json",scopes=scopes)
        client=gspread.authorize(creds)
        sheet=client.open("ExpenseTracker").sheet1
        data=sheet.get_all_values()
        return data
    except Exception as e:
        print(f"Error {e}")
        return []

def calculate_total():
    data=get_sheet_data()
    if not data:
        return 0.0
    total=0.0
    for row in data[1:]:
        try:
            val_str = row[3].replace(',', '.')
            value=float(val_str)
            total+=value 
        except:
            continue
    return total

def delete_last_transaction():
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds=Credentials.from_service_account_file("credentials.json",scopes=scopes)
        client=gspread.authorize(creds)
        sheet=client.open("ExpenseTracker").sheet1
        data=get_sheet_data()
        n_rows=len(data)
        if n_rows>1:
            sheet.delete_rows(n_rows)
            return True
        else:
            return False
    except Exception as e:
        print(f"Delete Error: {e}")
        return False

# --- CORE LOGIC ---

def analyze_expenses(user_text):
    data_oggi = datetime.now().strftime("%d-%m-%Y")
    prompt = f"""
    Sei un assistente contabile preciso.
    CONTESTO TEMPORALE: Oggi è il giorno {data_oggi}.
    Analizza: "{user_text}"
    Estrai JSON:
    {{
        "oggetto": "cosa è stato acquistato",
        "importo": numero (usa il punto per i decimali, es. 12.50),
        "categoria": "scegli una tra [Cibo, Trasporti, Casa, Svago, Investimenti]",
        "data": "data della spesa in formato DD-MM-YYYY"
    }}
    """
    try:
        response = model.generate_content(prompt)
        clean_data = json.loads(response.text)
        return clean_data
    except Exception as e:
        print(f"AI Error: {e}")
        return None # FIXED: Return None on error

def save_on_sheet(data_json):
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds=Credentials.from_service_account_file("credentials.json",scopes=scopes)
        client=gspread.authorize(creds)
        sheet=client.open("ExpenseTracker").sheet1
        row=[data_json.get("data"),
            data_json.get("categoria"),
            data_json.get("oggetto"),
            data_json.get("importo")
            ]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"Sheet Error: {e}")
        return False

# --- TELEGRAM HANDLERS ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    await update.message.reply_text(
        "👋 **Ciao! Sono il tuo ExpenseBot.**\n\n"
        "Ecco cosa posso fare:\n"
        "📝 Scrivi una spesa (es: 'Pizza 15 euro')\n"
        "💰 /report - Vedi quanto hai speso\n"
        "🔙 /undo - Cancella l'ultima spesa"
    )

async def handle_message(update:Update, context: ContextTypes.DEFAULT_TYPE):
    user_text=update.message.text
    # await update.message.reply_text("Analyzing expenses...") 
    data=analyze_expenses(user_text)

    if data:
        save_on_sheet(data)
        await update.message.reply_text(f"Saved: [{data['oggetto']}] - [{data['importo']}]")
    else:
        await update.message.reply_text("I did not understand")

# Handler for /undo
async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if delete_last_transaction():
        await update.message.reply_text("🗑️ Last transaction deleted.")
    else:
        await update.message.reply_text("❌ Error: Cannot delete (File empty or error).")

# Handler for /report
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tot = calculate_total()
    await update.message.reply_text(f"💰 Total Expenses: {tot:.2f}")

# --- MAIN ---

if __name__ == "__main__":
    application = ApplicationBuilder().token(telegram_token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("undo", cmd_undo))
    application.add_handler(CommandHandler("report", cmd_report))

    handler_messages = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    application.add_handler(handler_messages)

    print("Bot started!...")
    application.run_polling()