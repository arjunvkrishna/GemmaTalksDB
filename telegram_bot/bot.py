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
        "👋 Welcome to AISavvy!\n\n"
        "I'm your intelligent database assistant. You can ask me questions about your database in plain English.\n\n"
        "Try asking something like:\n"
        "- *How many employees are there?*\n"
        "- *What is the total salary in the Sales department?*"
    )
    await update.message.reply_text(welcome_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears the conversation history for the current chat."""
    chat_id = update.effective_chat.id
    chat_histories[chat_id] = []
    await update.message.reply_text("Conversation history cleared. We can start fresh!")

# --- Message Processing ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all non-command text messages."""
    chat_id = update.effective_chat.id
    user_message = update.message.text

    # Ensure a history list exists for the user
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    
    # Add user's message to their history
    stashed_history = chat_histories[chat_id]
    stashed_history.append({"role": "user", "content": user_message})

    # Show a "typing..." status in Telegram
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    # Call our backend API
    try:
        payload = {"history": stashed_history}
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Add the AI's response to the history for future context
        stashed_history.append({"role": "assistant", "content": data})
        
        # Format and send the reply to the user
        await send_formatted_reply(update, data)

    except requests.exceptions.HTTPError as e:
        error_message = "An API error occurred."
        suggested_fix = None
        try:
            error_data = e.response.json()
            if 'detail' in error_data and isinstance(error_data['detail'], dict):
                error_message = error_data['detail'].get('error', 'Unknown database error.')
                suggested_fix = error_data['detail'].get('suggested_fix')
            elif 'detail' in error_data:
                 error_message = str(error_data['detail'])
        except json.JSONDecodeError:
            error_message = e.response.text

        reply = f"😥 *API Error*: `{error_message}`"
        if suggested_fix:
            reply += f"\n\n🤖 *AI Suggested Fix*:\n```sql\n{suggested_fix}\n```"
        
        # On error, remove the last user message from history so they can try again
        if stashed_history and stashed_history[-1].get('role') == 'user':
            stashed_history.pop()
            
        await update.message.reply_markdown(reply)
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Connection Error: Could not reach the AISavvy API. Details: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await update.message.reply_text(f"An unexpected error occurred: {e}")

async def send_formatted_reply(update: Update, data: dict):
    """Formats the API response into a user-friendly Telegram message."""
    # Handle clarification questions from the API
    if "clarification" in data:
        await update.message.reply_text(f"🤔 {data['clarification']}")
        return

    result = data.get("result")
    sql_query = data.get("sql_query", "N/A")
    explanation = data.get("explanation", "")

    reply_text = f"💡 *Explanation*: {explanation}\n\n"

    if not result:
        reply_text += "Query executed successfully, but returned no results."
        await update.message.reply_markdown(reply_text)
        return

    df = pd.DataFrame(result)
    
    # Send data as a formatted text table or a file
    if len(df) < 20 and len(df.to_string()) < 4000:
        reply_text += f"```\n{df.to_string(index=False)}\n```"
        await update.message.reply_markdown(reply_text)
    else:
        csv_buffer = BytesIO()
        csv_buffer.write(df.to_csv(index=False).encode('utf-8'))
        csv_buffer.seek(0)
        csv_buffer.name = 'data_export.csv'
        await update.message.reply_document(document=csv_buffer, caption=reply_text)
    
    # Optionally send the SQL query in a separate, less prominent message
    await update.message.reply_markdown(f"*Generated SQL:*\n```sql\n{sql_query}\n```", disable_notification=True)


async def post_init(application: Application):
    """Sets the bot's commands after initialization."""
    await application.bot.set_my_commands([
        BotCommand("/start", "Begin a new conversation"),
        BotCommand("/clear", "Clear the current conversation history")
    ])

# --- Main Bot Setup ---
def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("FATAL: TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("clear", clear_command))

    # Message handler for all non-command text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot until the user presses Ctrl-C
    logger.info("Telegram bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()