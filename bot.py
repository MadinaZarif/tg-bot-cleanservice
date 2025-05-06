import os
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import requests
from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")  # <-- ЭТО ОБЯЗАТЕЛЬНО!
print("TOKEN:", BOT_TOKEN)


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Steps
NAME, ADDRESS_METHOD, ADDRESS, PHONE, DATE, COMMENT, CONFIRM, CORRECTION = range(8)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("tgbot-458722-913ca77a3418.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Order").sheet1

# Helper: reverse geocode coordinates to address (free OpenStreetMap)
def reverse_geocode(lat, lon):
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "json", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": "telegram-bot"}
        )
        data = response.json()
        return data.get("display_name", f"{lat}, {lon}")
    except Exception as e:
        logger.error(f"Geocode error: {e}")
        return f"{lat}, {lon}"

def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("👋 Hello!\n\n"
        "I'm your assistant bot for finding a cleaner for your home. 🧹🏠\n\n"
        "To match you with the right person, I’ll need a few details: "
        "your name, address, contact phone number, and the preferred date for the service.\n\n"
        "Let’s get started! What’s your full name?")
    return NAME

def get_name(update: Update, context: CallbackContext) -> int:
    name = update.message.text
    if not name.replace(" ", "").isalpha() or len(name) < 4:
        update.message.reply_text("Please enter a valid full name.")
        return NAME
    context.user_data["name"] = name
    reply_keyboard = [["📍 Share location", "✍️ Enter address manually"]]
    update.message.reply_text("How would you like to provide your address?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ADDRESS_METHOD

def choose_address_method(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    if "location" in text.lower():
        location_button = KeyboardButton(text="📍 Send location", request_location=True)
        markup = ReplyKeyboardMarkup([[location_button]], resize_keyboard=True)
        update.message.reply_text("Please share your location:", reply_markup=markup)
        return ADDRESS
    else:
        update.message.reply_text("Please enter your address:", reply_markup=ReplyKeyboardRemove())
        return ADDRESS

def save_location(update: Update, context: CallbackContext) -> int:
    location = update.message.location
    address = reverse_geocode(location.latitude, location.longitude)
    context.user_data["address"] = address
    
def save_location(update: Update, context: CallbackContext) -> int:
    print("Received location:", update)
    update.message.reply_text("Now please enter your phone number (e.g. +49123456789):")
    return PHONE

def get_address(update: Update, context: CallbackContext) -> int:
    context.user_data["address"] = update.message.text
    update.message.reply_text("Now please enter your phone number (e.g. +49123456789):")
    return PHONE

def get_phone(update: Update, context: CallbackContext) -> int:
    phone = update.message.text
    if not phone.startswith("+") or len(phone) < 10:
        update.message.reply_text("Please enter a valid phone number.")
        return PHONE
    context.user_data["phone"] = phone
    update.message.reply_text("Please enter the date you want the service (e.g. 2025-05-24):")
    return DATE

def get_date(update: Update, context: CallbackContext) -> int:
    context.user_data["date"] = update.message.text
    update.message.reply_text("Any comments or special instructions?")
    return COMMENT

def get_comment(update: Update, context: CallbackContext) -> int:
    context.user_data["comment"] = update.message.text
    return confirm_data(update, context)

def confirm_data(update: Update, context: CallbackContext) -> int:
    user_data = context.user_data
    text = (
        f"Please confirm your data:\n\n"
        f"👤 Name: {user_data['name']}\n"
        f"📍 Address: {user_data['address']}\n"
        f"📞 Phone: {user_data['phone']}\n"
        f"📅 Date: {user_data['date']}\n"
        f"📝 Comment: {user_data['comment']}\n\n"
        f"Is everything correct?"
    )
    reply_keyboard = [["✅ Yes", "✏️ Edit"]]
    update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    return CONFIRM

def confirm_response(update: Update, context: CallbackContext) -> int:
    if "yes" in update.message.text.lower():
        sheet.append_row([
            context.user_data["name"],
            update.message.from_user.id,
            context.user_data["address"],
            context.user_data["phone"],
            context.user_data["date"],
            context.user_data["comment"]
        ])
        update.message.reply_text("Thank you! Your data has been successfully saved. ✅", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    else:
        reply_keyboard = [["Name", "Address"], ["Phone", "Date"], ["Comment"]]
        update.message.reply_text("Which field would you like to edit?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        return CORRECTION

def correct_field(update: Update, context: CallbackContext) -> int:
    context.user_data["correction_field"] = update.message.text.lower()
    update.message.reply_text(f"Please enter the new value for: {update.message.text}")
    return CORRECTION + 1

def save_correction(update: Update, context: CallbackContext) -> int:
    field = context.user_data.get("correction_field")
    if field == "name":
        context.user_data["name"] = update.message.text
    elif field == "address":
        context.user_data["address"] = update.message.text
    elif field == "phone":
        context.user_data["phone"] = update.message.text
    elif field == "date":
        context.user_data["date"] = update.message.text
    elif field == "comment":
        context.user_data["comment"] = update.message.text
    return confirm_data(update, context)

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(Filters.text & ~Filters.command, get_name)],
            ADDRESS_METHOD: [MessageHandler(Filters.text & ~Filters.command, choose_address_method)],
           ADDRESS: [
            MessageHandler(Filters.location, save_location),
            MessageHandler(Filters.text & ~Filters.command, get_address)
        ],

            PHONE: [MessageHandler(Filters.text & ~Filters.command, get_phone)],
            DATE: [MessageHandler(Filters.text & ~Filters.command, get_date)],
            COMMENT: [MessageHandler(Filters.text & ~Filters.command, get_comment)],
            CONFIRM: [MessageHandler(Filters.text & ~Filters.command, confirm_response)],
            CORRECTION: [MessageHandler(Filters.text & ~Filters.command, correct_field)],
            CORRECTION + 1: [MessageHandler(Filters.text & ~Filters.command, save_correction)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
