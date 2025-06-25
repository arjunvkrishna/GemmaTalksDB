# In telegram_bot/bot.py, replace the existing handle_message function

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all non-command text messages with improved error handling."""
    chat_id = update.effective_chat.id
    user_message = update.message.text

    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    
    chat_histories[chat_id].append({"role": "user", "content": user_message})

    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        payload = {"history": chat_histories[chat_id]}
        response = requests.post(API_URL, json=payload)
        response.raise_for_status() # This will raise HTTPError for 4xx/5xx responses
        data = response.json()
        
        # Add AI response to history. The content is the full dictionary.
        chat_histories[chat_id].append({"role": "assistant", "content": data})
        await send_formatted_reply(update, data)

    except requests.exceptions.HTTPError as e:
        # --- NEW: Robust Error Parsing ---
        error_message = "An API error occurred."
        suggested_fix = None
        try:
            error_data = e.response.json()
            # Handle FastAPI's validation error (422) which has a list in 'detail'
            if 'detail' in error_data and isinstance(error_data['detail'], list):
                error_message = error_data['detail'][0].get('msg', str(error_data['detail']))
            # Handle our custom error format (400) which has a dict in 'detail'
            elif 'detail' in error_data and isinstance(error_data['detail'], dict):
                error_message = error_data['detail'].get('error', 'Unknown database error.')
                suggested_fix = error_data['detail'].get('suggested_fix')
            # Handle other possible JSON error structures
            else:
                 error_message = str(error_data)
        except json.JSONDecodeError:
            error_message = e.response.text

        reply = f"😥 *API Error*: `{error_message}`"
        if suggested_fix:
            reply += f"\n\n🤖 *AI Suggested Fix*:\n```sql\n{suggested_fix}\n```"
        
        # Remove the last user message from history so they can try again
        chat_histories[chat_id].pop()
        await update.message.reply_markdown(reply)
        
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Connection Error: Could not reach the AISavvy API. Details: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await update.message.reply_text(f"An unexpected error occurred: {e}")