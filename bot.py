import logging
import os
import json
import re
import io

from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    Contact,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from telegram.request import HTTPXRequest

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# -----------------------------
# ПАРАМЕТРЫ
# -----------------------------
TOKEN = os.environ.get("TOKEN")  # Убедитесь, что на Railway переменная называется именно TOKEN
TARGET_CHAT_ID = -4694840761      # ID чата/группы, куда отправляются замеры

# Файл с разрешёнными номерами
ALLOWED_NUMBERS_FILE = "allowed_numbers.json"

try:
    with open(ALLOWED_NUMBERS_FILE, "r", encoding="utf-8") as f:
        ALLOWED_NUMBERS = json.load(f)  # пример: {"79123816215": "Владимир"}
except Exception as e:
    logging.error("Не удалось загрузить базу номеров: %s", e)
    ALLOWED_NUMBERS = {}

# Тексты для кнопок
LAUNCH_TEXT = "Запустить"
STOP_TEXT = "Отключить бота"

SKIP_TEXT = "Пропустить"
DONE_TEXT = "Готово"

# -----------------------------
# СОСТОЯНИЯ
# -----------------------------
LAUNCH, AUTH, MENU, GET_NAME, GET_PHONE, GET_ADDRESS = range(6)
(
    ENTER_ROOM,
    ENTER_DOOR_TYPE,
    ENTER_DOOR_TYPE_CUSTOM,
    ENTER_DIMENSIONS,
    ENTER_CANVAS,
    ENTER_DOBOR,
    ENTER_DOBOR_CUSTOM,
    ENTER_DOBOR_COUNT,
    ENTER_DOBOR_COUNT_CUSTOM,
    ENTER_NALICHNIKI_CHOICE,
    ENTER_NALICHNIKI_CUSTOM,
    ENTER_THRESHOLD_CHOICE,
    ENTER_DEMONTAGE_CHOICE,
    ENTER_OPENING_CHOICE,
    ENTER_OPENING_CUSTOM,
    ENTER_COMMENT,
    ENTER_PHOTOS,
    OPENING_MENU
) = range(6, 24)

EDIT_CHOICE, EDIT_FIELD, EDIT_VALUE, DELETE_CHOICE, DELETE_CONFIRM = range(24, 29)
CHECK_MEASURE = 29

# -----------------------------
# 1) Генерация таблицы (PNG)
# -----------------------------
def generate_measurement_image(client_data: dict) -> io.BytesIO:
    """
    Генерирует PNG-таблицу с данными по замерам.
    """
    # ... (код идентичен предыдущим примерам, только перенесён сюда)
    col_widths = [50, 150, 200, 200, 100, 100, 110, 110, 80, 100, 120, 200]
    headers = [
        "№", "Комната", "Тип двери", "Размеры", "Полотно",
        "Добор", "Кол-во доборов", "Наличники",
        "Порог", "Демонтаж", "Открывание", "Комментарий"
    ]
    openings = client_data.get("openings", [])
    rows = [headers]
    for i, op in enumerate(openings, start=1):
        row = [
            str(i),
            op["room"],
            op["door_type"],
            op["dimensions"],
            op["canvas"],
            op["dobor"],
            op["dobor_count"],
            op["nalichniki"],
            op["threshold"],
            op["demontage"],
            op["opening"],
            op["comment"]
        ]
        rows.append(row)

    client_info = (
        f"Имя: {client_data.get('client_name', '')}\n"
        f"Телефон: {client_data.get('client_phone', '')}\n"
        f"Адрес: {client_data.get('client_address', '')}\n"
    )
    try:
        font = ImageFont.truetype("Montserrat-Regular.ttf", 16)
    except:
        font = ImageFont.load_default()

    temp_img = Image.new("RGB", (10, 10))
    draw_temp = ImageDraw.Draw(temp_img)

    def get_text_size(text, font_obj):
        left, top, right, bottom = draw_temp.textbbox((0, 0), text, font=font_obj)
        return (right - left, bottom - top)

    def wrap_text(text, max_width):
        words = text.split()
        lines = []
        if not words:
            return [""]
        current_line = words[0]
        for w in words[1:]:
            test_line = current_line + " " + w
            w_test, _ = get_text_size(test_line, font)
            if w_test <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = w
        lines.append(current_line)
        return lines

    cell_padding = 10
    line_spacing = 5
    row_lines = []
    row_heights = []

    for row_idx, row_data in enumerate(rows):
        max_height = 0
        row_lines.append([])
        for col_idx, cell_text in enumerate(row_data):
            cell_text = str(cell_text)
            effective_width = col_widths[col_idx] - 2 * cell_padding
            lines = wrap_text(cell_text, effective_width)
            _, line_h = get_text_size("A", font)
            line_height_with_spacing = line_h + line_spacing
            cell_height = len(lines) * line_height_with_spacing + 3 * cell_padding
            if cell_height > max_height:
                max_height = cell_height
            row_lines[row_idx].append(lines)
        row_heights.append(max_height)

    margin = 50
    table_width = sum(col_widths) + margin * 2

    info_lines = client_info.strip().split("\n")
    _, line_h = get_text_size("A", font)
    info_block_height = line_h * len(info_lines) + 40

    logo_path = "Logo_rusdver.png"
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((150, 9999))
        logo_width, logo_height = logo.size
    except:
        logo = None
        logo_width, logo_height = 0, 0

    top_block_height = max(info_block_height, logo_height) + 20
    table_height = sum(row_heights) + margin * 2
    total_height = top_block_height + table_height

    img = Image.new("RGB", (table_width, total_height), color="white")
    draw = ImageDraw.Draw(img)

    y_offset = 20
    draw.text((margin, y_offset), client_info, font=font, fill="black")

    if logo:
        x_logo = table_width - margin - logo_width
        y_logo = 20
        img.paste(logo, (x_logo, y_logo), logo)

    y_offset = top_block_height
    for row_idx, row_data in enumerate(rows):
        row_h = row_heights[row_idx]
        x_offset = margin
        for col_idx, _ in enumerate(row_data):
            w_col = col_widths[col_idx]
            draw.rectangle(
                [x_offset, y_offset, x_offset + w_col, y_offset + row_h],
                outline="black",
                width=1
            )
            lines = row_lines[row_idx][col_idx]
            text_x = x_offset + cell_padding
            text_y = y_offset + cell_padding
            _, line_h = get_text_size("A", font)
            line_height_with_spacing = line_h + line_spacing
            for line in lines:
                draw.text((text_x, text_y), line, font=font, fill="black")
                text_y += line_height_with_spacing
            x_offset += w_col
        y_offset += row_h

    bio = io.BytesIO()
    bio.name = "zamery.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

# -----------------------------
# 2) Наложение текста на фото
# -----------------------------
async def overlay_text_on_photo(context: ContextTypes.DEFAULT_TYPE, file_id: str, text: str) -> io.BytesIO:
    temp_path = "temp_photo.jpg"
    file_obj = await context.bot.get_file(file_id)
    await file_obj.download_to_drive(temp_path)
    img = Image.open(temp_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("Montserrat-Regular.ttf", 24)
    except:
        font = ImageFont.load_default()

    text_x = 20
    text_y = img.height - 60
    text_w, text_h = draw.textsize(text, font=font)
    box = [text_x - 10, text_y - 10, text_x + text_w + 10, text_y + text_h + 10]
    draw.rectangle(box, fill=(0, 0, 0, 128))
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    out_buf = io.BytesIO()
    out_buf.name = "photo.png"
    img.save(out_buf, "PNG")
    out_buf.seek(0)

    if os.path.exists(temp_path):
        os.remove(temp_path)
    return out_buf

async def send_photos_with_overlay_as_album(context: ContextTypes.DEFAULT_TYPE, chat_id: int, photo_overlays: list):
    from telegram import InputMediaPhoto
    media_group = []
    album_caption = "Все фото с подписями"
    for i, (file_id, overlay_text) in enumerate(photo_overlays):
        processed_img = await overlay_text_on_photo(context, file_id, overlay_text)
        if i == 0:
            media_group.append(InputMediaPhoto(processed_img, caption=album_caption))
        else:
            media_group.append(InputMediaPhoto(processed_img))
    await context.bot.send_media_group(chat_id=chat_id, media=media_group)

# -----------------------------
# 3) ЛОГИКА АВТОРИЗАЦИИ
# -----------------------------
async def show_launch_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Как только пользователь пишет что‑либо в чат (или заново заходит),
    показываем кнопки «Запустить» и «Отключить бота».
    """
    keyboard = [
        [KeyboardButton(LAUNCH_TEXT)],
        [KeyboardButton(STOP_TEXT)]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Нажмите «Запустить» для проверки номера или «Отключить бота» для выключения.",
        reply_markup=markup
    )
    return LAUNCH

async def launch_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == STOP_TEXT:
        # Если нажали «Отключить бота»
        keyboard = [[KeyboardButton(LAUNCH_TEXT)]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Бот выключен. Для включения нажмите «Запустить».",
            reply_markup=markup
        )
        return LAUNCH  # Остаёмся в том же состоянии LAUNCH
    elif text == LAUNCH_TEXT:
        # Переходим к запросу контакта
        keyboard = [
            [KeyboardButton("Поделиться контактом", request_contact=True)],
            [KeyboardButton(STOP_TEXT)]
        ]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Для авторизации, пожалуйста, поделитесь своим контактом.",
            reply_markup=markup
        )
        return AUTH
    else:
        await update.message.reply_text("Нажмите «Запустить» или «Отключить бота».")
        return LAUNCH

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Получаем контакт, нормализуем номер, проверяем в базе.
    """
    if update.message.text == STOP_TEXT:
        # Отключили бота
        keyboard = [[KeyboardButton(LAUNCH_TEXT)]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Бот выключен. Для включения нажмите «Запустить».",
            reply_markup=markup
        )
        return LAUNCH

    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Контакт не получен. Нажмите «Поделиться контактом».")
        return AUTH

    # Убираем все нецифровые символы
    phone = re.sub(r"\D", "", contact.phone_number or "")
    # Смотрим, есть ли он в базе
    if phone in ALLOWED_NUMBERS:
        user_name = ALLOWED_NUMBERS[phone]
        context.user_data["authorized_name"] = user_name
        # Переходим в основное меню
        keyboard = [
            [KeyboardButton("Новый замер")],
            [KeyboardButton(STOP_TEXT)]
        ]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"Здравствуйте, {user_name}! Для начала замера нажмите «Новый замер».",
            reply_markup=markup
        )
        return MENU
    else:
        await update.message.reply_text("Извините, ваш номер не найден в базе. Доступ закрыт.")
        # Возвращаемся в LAUNCH, чтобы снова могли нажать "Запустить"
        keyboard = [[KeyboardButton(LAUNCH_TEXT)]]
        markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Бот выключен. Для включения нажмите «Запустить».",
            reply_markup=markup
        )
        return LAUNCH

# -----------------------------
# 4) "Отключить бота" (cancel)
# -----------------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    При нажатии «Отключить бота» завершаем текущий диалог,
    но показываем снова кнопку «Запустить».
    """
    keyboard = [[KeyboardButton(LAUNCH_TEXT)]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Бот выключен. Для включения нажмите «Запустить».",
        reply_markup=markup
    )
    return LAUNCH  # Возвращаемся в состояние LAUNCH

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Любое непредвиденное сообщение в состоянии,
    где мы не ждём такой ввод.
    """
    keyboard = [
        [KeyboardButton(LAUNCH_TEXT)],
        [KeyboardButton(STOP_TEXT)]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Непредвиденная команда или сообщение.\n"
        "Нажмите «Запустить» для проверки номера или «Отключить бота» для выключения.",
        reply_markup=markup
    )
    return LAUNCH

# -----------------------------
# 5) Основная логика замера
# -----------------------------
# Далее идёт та же логика, что и раньше:
# MENU -> GET_NAME -> GET_PHONE -> GET_ADDRESS -> ... -> ENTER_PHOTOS -> ...
# С кнопкой "Отключить бота" в каждом шаге, если хотите.
# Здесь приведён укороченный вариант, чтобы не дублировать слишком много кода.

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == STOP_TEXT:
        return await cancel(update, context)
    if text == "Новый замер":
        # Сбрасываем данные
        context.user_data["openings"] = []
        context.user_data.pop("client_name", None)
        context.user_data.pop("client_phone", None)
        context.user_data.pop("client_address", None)
        await update.message.reply_text("Введите имя клиента:", reply_markup=ReplyKeyboardRemove())
        return GET_NAME
    else:
        await update.message.reply_text("Нажмите кнопку 'Новый замер' или 'Отключить бота'.")
        return MENU

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == STOP_TEXT:
        return await cancel(update, context)
    context.user_data["client_name"] = update.message.text
    await update.message.reply_text("Введите телефон клиента:")
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == STOP_TEXT:
        return await cancel(update, context)
    context.user_data["client_phone"] = update.message.text
    await update.message.reply_text("Введите адрес клиента:")
    return GET_ADDRESS

async def get_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == STOP_TEXT:
        return await cancel(update, context)
    context.user_data["client_address"] = update.message.text
    # Переходим к вводу первого проёма
    return await start_opening(update, context)

# ... здесь вставляется весь код по шагам (ENTER_ROOM, ENTER_DOOR_TYPE, etc.) ...
# ... где в каждом шаге, если text == STOP_TEXT, вызываем cancel(update, context) ...

# В конце — проверка, редактирование, завершение, как в предыдущем коде.
# -----------------------------

def main():
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)
    app = Application.builder().token(TOKEN).request(request).build()

    conv_handler = ConversationHandler(
        entry_points=[
            # Когда пользователь пишет ЛЮБОЕ сообщение в "новом" чате, покажем кнопки "Запустить" / "Отключить"
            MessageHandler(filters.ALL & ~filters.UpdateType.EDITED, show_launch_menu)
        ],
        states={
            LAUNCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, launch_choice)
            ],
            AUTH: [
                # Ожидаем контакт
                MessageHandler(filters.CONTACT, handle_contact),
                # Если текст = "Отключить бота"
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contact)
            ],
            MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)
            ],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            GET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_address)],

            # Здесь вставляем остальные шаги: ENTER_ROOM, ENTER_DOOR_TYPE, ... OPENING_MENU, CHECK_MEASURE и т.д.
            # с той же логикой, что была в предыдущем коде.

            # Пример:
            # ENTER_ROOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_room)],
            # ...
        },
        fallbacks=[
            # Если в любом состоянии введут /cancel
            CommandHandler("cancel", cancel),
            # Или что-то неподходящее
            MessageHandler(filters.COMMAND | filters.TEXT, fallback)
        ]
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
