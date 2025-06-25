import os
import logging
import requests
import json
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO

from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = os.getenv("API_URL", "http://app:8000/query")

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for chat histories, keyed by chat_id
chat_histories = {}

# --- Bot Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = [] # Clear history for a new session
    welcome_text = (
        "👋 Welcome to AISavvy!\n\nI'm your intelligent database assistant. "
        "Ask me questions about your database in plain English and I'll get the answers for you."
    )
    await update.message.reply_text(welcome_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears the conversation history."""
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    await update.message.reply_text("Conversation history cleared. Let's start fresh!")

# --- Message Processing ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all non-command text messages."""
    chat_id = update.effective_chat.id
    user_message = update.message.text

    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    
    chat_histories[chat_id].append({"role": "user", "content": user_message})

    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        payload = {"history": chat_histories[chat_id]}
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Add AI response to history for conversational context
        chat_histories[chat_id].append({"role": "assistant", "content": data})
        await send_formatted_reply(update, data)

    except requests.exceptions.HTTPError as e:
        error_data = e.response.json().get('detail', {})
        error_message = error_data.get('error', 'An API error occurred.')
        suggested_fix = error_data.get('suggested_fix')
        reply = f"😥 *API Error*: `{error_message}`"
        if suggested_fix:
            reply += f"\n\n🤖 *AI Suggested Fix*:\n```sql\n{suggested_fix}\n```"
        await update.message.reply_markdown(reply)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await update.message.reply_text(f"An unexpected error occurred: {e}")

async def send_formatted_reply(update: Update, data: dict):
    """Formats the API response into a user-friendly Telegram message."""
    result = data.get("result")
    chart_spec = data.get("chart_spec")

    if not result:
        await update.message.reply_text("Query executed successfully, but returned no results.")
        return

    df = pd.DataFrame(result)
    
    if chart_spec and chart_spec.get("chart_needed"):
        try:
            chart_sent = await send_chart_as_image(update, df, chart_spec)
            if chart_sent: return
        except Exception as e:
            logger.error(f"Failed to generate chart: {e}")

    # Fallback to sending data as formatted text or a file
    if len(df) < 20 and len(df.to_string()) < 4000:
        reply_text = f"```\n{df.to_string(index=False)}\n```"
        await update.message.reply_markdown(reply_text)
    else:
        csv_buffer = BytesIO()
        csv_buffer.write(df.to_csv(index=False).encode('utf-8'))
        csv_buffer.seek(0)
        csv_buffer.name = 'data_export.csv'
        await update.message.reply_document(document=csv_buffer, caption="The result was too large, so here it is as a CSV file.")

async def send_chart_as_image(update: Update, df: pd.DataFrame, spec: dict) -> bool:
    """Generates and sends a Matplotlib chart as a photo."""
    # ... (code for this function is the same as the previous full response)
    chart_type = spec.get("chart_type")
    x_col = spec.get("x_column")
    y_col = spec.get("y_column")

    if not all([chart_type, x_col, y_col]) or x_col not in df.columns or y_col not in df.columns:
        return False

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "bar":
        ax.bar(df[x_col], df[y_col])
    elif chart_type == "line":
        ax.plot(df[x_col], df[y_col])
    elif chart_type == "pie":
        ax.pie(df[y_col], labels=df[x_col], autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
    else:
        return False

    ax.set_title(f"{chart_type.capitalize()} Chart of {y_col} by {x_col}", fontsize=16)
    ax.set_xlabel(x_col, fontsize=12)
    ax.set_ylabel(y_col, fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.message.reply_photo(photo=buf)
    return True


async def post_init(application: Application):
    """Sets the bot's commands after initialization."""
    await application.bot.set_my_commands([
        BotCommand("/start", "Begin a new conversation"),
        BotCommand("/clear", "Clear the current conversation history")
    ])

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("FATAL: TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Telegram bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()