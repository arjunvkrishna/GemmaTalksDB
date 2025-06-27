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
STT_API_URL = os.getenv("STT_API_URL", "http://stt-service:8080/inference")

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
        "👋 Welcome to AISavvy!\n\nI now understand voice notes! "
        "Send me a typed question or a voice message to get started."
    )
    await update.message.reply_text(welcome_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears the conversation history."""
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    await update.message.reply_text("Conversation history cleared. Let's start fresh!")

# --- Core Logic ---
async def process_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Core logic to call the API and send a reply. Now correctly accepts 'context'."""
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    try:
        payload = {"history": chat_histories[chat_id]}
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Add AI's full response dictionary to history for grounding
        chat_histories[chat_id].append({"role": "assistant", "content": data})
        
        await send_formatted_reply(update, data)
    except requests.exceptions.HTTPError as e:
        error_message = "An API error occurred."
        suggested_fix = None
        try:
            error_data = e.response.json()
            if 'detail' in error_data and isinstance(error_data['detail'], list):
                error_message = error_data['detail'][0].get('msg', str(error_data['detail']))
            elif 'detail' in error_data and isinstance(error_data['detail'], dict):
                error_message = error_data['detail'].get('error', 'Unknown database error.')
                suggested_fix = error_data['detail'].get('suggested_fix')
            else:
                 error_message = str(error_data)
        except json.JSONDecodeError:
            error_message = e.response.text

        reply = f"😥 *API Error*: `{error_message}`"
        if suggested_fix:
            reply += f"\n\n🤖 *AI Suggested Fix*:\n```sql\n{suggested_fix}\n```"
        
        # On error, remove the last user message from history so it's not poisoned
        if chat_histories.get(chat_id) and chat_histories[chat_id][-1].get('role') == 'user':
            chat_histories[chat_id].pop()
            
        await update.message.reply_markdown(reply)
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Connection Error: Could not reach the AISavvy API. Details: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await update.message.reply_text(f"An unexpected error occurred: {e}")

# --- Message Handlers ---
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text messages."""
    chat_id = update.effective_chat.id
    user_message = update.message.text
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    
    chat_histories[chat_id].append({"role": "user", "content": user_message})
    await process_and_reply(update, context, chat_id)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles voice messages by transcribing them first."""
    chat_id = update.effective_chat.id
    voice = update.message.voice
    await update.message.reply_text("Received your voice note, transcribing now...")
    try:
        voice_file = await voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        
        files = {'file': ('audio.ogg', bytes(voice_bytes), 'audio/ogg')}
        stt_response = requests.post(STT_API_URL, files=files)
        stt_response.raise_for_status()
        transcribed_text = stt_response.json().get('text', '').strip()

        if not transcribed_text:
            await update.message.reply_text("Sorry, I couldn't understand the audio. Please try again.")
            return

        await update.message.reply_text(f"I heard: \"_{transcribed_text}_\"\nNow, let me find an answer...", parse_mode='Markdown')
        
        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
        chat_histories[chat_id].append({"role": "user", "content": transcribed_text})
        await process_and_reply(update, context, chat_id)

    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await update.message.reply_text("Sorry, there was an error processing your voice message.")

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

    if len(df) < 20 and len(df.to_string()) < 4000:
        reply_text = f"```\n{df.to_string(index=False)}\n```"
        await update.message.reply_markdown(reply_text)
    else:
        csv_buffer = BytesIO()
        csv_buffer.write(df.to_csv(index=False).encode('utf-8'))
        csv_buffer.seek(0)
        csv_buffer.name = 'data_export.csv'
        await update.message.reply_document(document=csv_buffer, caption="The result set was too large, so here it is as a CSV file.")

async def send_chart_as_image(update: Update, df: pd.DataFrame, spec: dict) -> bool:
    """Generates and sends a Matplotlib chart as a photo."""
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
        plt.close(fig)
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
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    logger.info("Telegram bot with voice support is running...")
    application.run_polling()

if __name__ == "__main__":
    main()