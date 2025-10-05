import os
import logging
import io
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from dotenv import load_dotenv
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import time

# ==================== ПРОСТОЙ ВЕБ-СЕРВЕР ДЛЯ RENDER ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html_content = """
                <html>
                    <head><title>Insurance Bot</title></head>
                    <body>
                        <h1>🤖 Бот страхования работает!</h1>
                        <p>Insurance Bot is ONLINE and ready to receive applications.</p>
                        <p>🕒 Статус: <strong>Активен</strong></p>
                        <p>📅 Время сервера: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
                    </body>
                </html>
            """
            self.wfile.write(html_content.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_health_check():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"✅ Веб-сервер запущен на порту {port}")
    server.serve_forever()

# Запускаем веб-сервер в фоне
health_thread = Thread(target=run_health_check, daemon=True)
health_thread.start()

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ====================
load_dotenv()

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

print("🚀 Начинается запуск Telegram бота...")

# ==================== СОСТОЯНИЯ РАЗГОВОРА ====================
(
    START, POLICY_TYPE, CURRENT_POLICY_INPUT, CURRENT_POLICY_PHOTO, 
    INSURANCE_START_DATE, INSURANCE_PERIOD, CHOOSE_OWNER_INSURER,
    INSURER_PASSPORT_MAIN_PHOTO, INSURER_PASSPORT_REGISTRATION_PHOTO,
    INSURER_PASSPORT_MAIN_MANUAL, INSURER_PASSPORT_REGISTRATION_MANUAL,
    OWNER_PASSPORT_MAIN_PHOTO, OWNER_PASSPORT_REGISTRATION_PHOTO,
    OWNER_PASSPORT_MAIN_MANUAL, OWNER_PASSPORT_REGISTRATION_MANUAL,
    VEHICLE_DOC_TYPE, VEHICLE_DOC_FRONT_PHOTO, VEHICLE_DOC_BACK_PHOTO,
    VEHICLE_DOC_MANUAL, DRIVERS_CHOICE, DRIVER_LICENSE_FRONT_PHOTO,
    DRIVER_LICENSE_BACK_PHOTO, DRIVER_LICENSE_MANUAL, ADD_DRIVER,
    INSURER_PHONE, CONFIRMATION, HELP_REQUEST, FINAL_CONFIRMATION
) = range(29)

user_data = {}

class WordGenerator:
    @staticmethod
    def generate_application_docx(data):
        """Генерация Word документа с заявкой"""
        doc = Document()
        
        # Заголовок
        title = doc.add_heading('ЗАЯВКА НА ОСАГО', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Информация о типе полиса
        policy_type = doc.add_paragraph()
        policy_type.add_run(f"Тип заявки: {data.get('policy_type', 'Не указано')}").bold = True
        
        if data.get('current_policy_data'):
            policy_type.add_run(f"\nДанные текущего полиса: {data.get('current_policy_data', 'Не указано')}")
        
        # Дата
        date_paragraph = doc.add_paragraph()
        date_paragraph.add_run(f"Дата формирования: {datetime.now().strftime('%d.%m.%Y %H:%M')}").bold = True
        doc.add_paragraph()
        
        # Срок страхования
        insurance_period = doc.add_paragraph()
        insurance_period.add_run("СРОК СТРАХОВАНИЯ:\n").bold = True
        insurance_period.add_run(f"Начало: {data.get('insurance_start_date', 'Не указано')}\n")
        insurance_period.add_run(f"Период: {data.get('insurance_period', 'Не указано')} месяцев")
        doc.add_paragraph()
        
        # Раздел: Страхователь
        doc.add_heading('СТРАХОВАТЕЛЬ', level=1)
        
        insurer_info = [
            f"ФИО: {data.get('insurer_fio', 'Не указано')}",
            f"Дата рождения: {data.get('insurer_birthdate', 'Не указано')}",
            f"Паспорт: {data.get('insurer_passport_series_number', 'Не указано')}",
            f"Дата выдачи паспорта: {data.get('insurer_passport_issue_date', 'Не указано')}",
            f"Кем выдан: {data.get('insurer_passport_issued_by', 'Не указано')}",
            f"Код подразделения: {data.get('insurer_passport_department_code', 'Не указано')}",
            f"Прописка: {data.get('insurer_registration', 'Не указано')}"
        ]
        
        for info in insurer_info:
            doc.add_paragraph(info)
        
        doc.add_paragraph()
        
        # Раздел: Собственник
        doc.add_heading('СОБСТВЕННИК', level=1)
        
        if not data.get('is_same_person', True):
            owner_info = [
                f"ФИО: {data.get('owner_fio', 'Не указано')}",
                f"Дата рождения: {data.get('owner_birthdate', 'Не указано')}",
                f"Паспорт: {data.get('owner_passport_series_number', 'Не указано')}",
                f"Дата выдачи паспорта: {data.get('owner_passport_issue_date', 'Не указано')}",
                f"Кем выдан: {data.get('owner_passport_issued_by', 'Не указано')}",
                f"Код подразделения: {data.get('owner_passport_department_code', 'Не указано')}"
            ]
            
            for info in owner_info:
                doc.add_paragraph(info)
        else:
            doc.add_paragraph("Собственник и страхователь - одно лицо")
        
        doc.add_paragraph()
        
        # Водительское удостоверение страхователя
        doc.add_heading('ВОДИТЕЛЬСКОЕ УДОСТОВЕРЕНИЕ СТРАХОВАТЕЛЯ', level=1)
        
        license_info = [
            f"В/у: {data.get('insurer_license', 'Не указано')}",
            f"Дата выдачи: {data.get('insurer_license_issue_date', 'Не указано')}",
            f"Срок действия: {data.get('insurer_license_expiry', 'Не указано')}"
        ]
        
        for info in license_info:
            doc.add_paragraph(info)
        
        doc.add_paragraph()
        
        # Раздел: Транспортное средство
        doc.add_heading('ТРАНСПОРТНОЕ СРЕДСТВО', level=1)
        
        vehicle_info = [
            f"Марка: {data.get('vehicle_brand', 'Не указано')}",
            f"Модель: {data.get('vehicle_model', 'Не указано')}",
            f"Год выпуска: {data.get('vehicle_year', 'Не указано')}",
            f"Мощность: {data.get('vehicle_power', 'Не указано')} л.с.",
            f"Госномер: {data.get('vehicle_reg_number', 'Не указано')}",
            f"VIN: {data.get('vehicle_vin', 'Не указано')}",
            f"Документ: {data.get('vehicle_doc_type', 'Не указано')} {data.get('vehicle_doc_details', 'Не указано')}",
            f"Дата выдачи документа: {data.get('vehicle_doc_issue_date', 'Не указано')}"
        ]
        
        for info in vehicle_info:
            doc.add_paragraph(info)
        
        doc.add_paragraph()
        
        # Раздел: Водители
        doc.add_heading('ВОДИТЕЛИ', level=1)
        
        drivers = data.get('drivers', [])
        if drivers:
            for i, driver in enumerate(drivers, 1):
                driver_paragraph = doc.add_paragraph()
                driver_paragraph.add_run(f'Водитель {i}: ').bold = True
                driver_paragraph.add_run(f"{driver.get('fio', 'Не указано')}")
                
                doc.add_paragraph(f"   В/у: {driver.get('license', 'Не указано')}")
                doc.add_paragraph(f"   Дата выдачи: {driver.get('license_issue_date', 'Не указано')}")
                doc.add_paragraph(f"   Срок действия: {driver.get('license_expiry', 'Не указано')}")
                doc.add_paragraph()
        else:
            doc.add_paragraph("Без ограничений")
        
        # Телефон
        doc.add_paragraph()
        phone_paragraph = doc.add_paragraph()
        phone_paragraph.add_run("Телефон для связи: ").bold = True
        phone_paragraph.add_run(f"{data.get('insurer_phone', 'Не указан')}")
        
        # Подпись
        doc.add_paragraph()
        doc.add_paragraph("Заявка успешно оформлена!").bold = True
        doc.add_paragraph("В течении 1 часа с Вами свяжется менеджер, для возможного уточнения деталей и дальнейшего оформления!")
        doc.add_paragraph("С Уважением, АО 'Альфастрахование'").bold = True
        
        return doc

    @staticmethod
    def generate_sample_policy(data):
        """Генерация образца полиса с водяным знаком"""
        doc = Document()
        
        # Заголовок
        title = doc.add_heading('ПОЛИС ОСАГО', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Водяной знак "ОБРАЗЕЦ"
        for i in range(10):  # Добавляем несколько строк с текстом "ОБРАЗЕЦ" под разными углами
            watermark = doc.add_paragraph()
            watermark_run = watermark.add_run("О Б Р А З Е Ц")
            watermark_run.font.size = Pt(48)
            watermark_run.font.color.rgb = RGBColor(200, 200, 200)  # Серый цвет
            watermark.alignment = WD_ALIGN_PARAGRAPH.CENTER
            watermark.paragraph_format.space_after = Pt(30)
        
        # Основная информация (полупрозрачная)
        info_section = doc.add_paragraph()
        info_section.add_run("ИНФОРМАЦИЯ О ПОЛИСЕ\n").bold = True
        info_section.add_run(f"Страхователь: {data.get('insurer_fio', 'Не указано')}\n")
        info_section.add_run(f"ТС: {data.get('vehicle_brand', 'Не указано')} {data.get('vehicle_model', 'Не указано')}\n")
        info_section.add_run(f"Госномер: {data.get('vehicle_reg_number', 'Не указано')}\n")
        info_section.add_run(f"VIN: {data.get('vehicle_vin', 'Не указано')}\n")
        info_section.add_run(f"Период страхования: {data.get('insurance_period', 'Не указано')} месяцев\n")
        info_section.add_run(f"Начало действия: {data.get('insurance_start_date', 'Не указано')}")
        
        # Делаем текст информации тоже полупрозрачным
        for run in info_section.runs:
            run.font.color.rgb = RGBColor(100, 100, 100)
        
        info_section.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Добавляем крупный текст ОБРАЗЕЦ поверх
        sample_text = doc.add_paragraph()
        sample_run = sample_text.add_run("ОБРАЗЕЦ")
        sample_run.font.size = Pt(72)
        sample_run.font.color.rgb = RGBColor(150, 150, 150)
        sample_run.bold = True
        sample_text.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        return doc

def get_navigation_keyboard():
    """Клавиатура для навигации"""
    return ReplyKeyboardMarkup([
        ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
    ], resize_keyboard=True)

def get_manual_input_keyboard():
    """Клавиатура с опцией ручного ввода"""
    return ReplyKeyboardMarkup([
        ["📷 Сделать фото", "⌨️ Ввести вручную"],
        ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало разговора"""
    user = update.message.from_user
    
    welcome_text = (
        "Добро пожаловать!\n\n"
        "Здесь Вы сможете оформить ОСАГО для легковых автомобилей категории В "
        "от АО 'АльфаСтрахование', а также есть возможность перехода из другой "
        "страховой компании.\n\n"
        "Данный бот собирает персональную информацию на основании 152-ФЗ РФ. "
        "Ознакомиться с политикой можно по ссылке: https://www.alfastrah.ru/about/confidential/\n\n"
        "После сбора информации все данные передаются представителю организации "
        "для дальнейшего оформления полиса."
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup([
            ["📄 Первоначальный полис", "🔄 Переход из другой страховой"],
            ["🆘 Помощь"]
        ], one_time_keyboard=True, resize_keyboard=True)
    )
    return POLICY_TYPE

async def policy_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора типа полиса"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    
    user_id = update.message.from_user.id
    choice = update.message.text
    
    user_data[user_id] = {
        'policy_type': choice,
        'drivers': []
    }
    
    if choice == "🔄 Переход из другой страховой":
        await update.message.reply_text(
            "Выберите способ ввода данных текущего полиса:",
            reply_markup=ReplyKeyboardMarkup([
                ["⌨️ Ввести данные полиса вручную", "📷 Сделать фото полиса"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return CURRENT_POLICY_INPUT
    else:
        await update.message.reply_text(
            "Введите дату начала действия страховки (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE

async def current_policy_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода данных текущего полиса"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        return await start(update, context)
    
    user_id = update.message.from_user.id
    
    if update.message.text == "⌨️ Ввести данные полиса вручную":
        await update.message.reply_text(
            "Введите данные текущего полиса (номер, серия, срок действия):",
            reply_markup=get_navigation_keyboard()
        )
        return CURRENT_POLICY_INPUT
    elif update.message.text == "📷 Сделать фото полиса":
        await update.message.reply_text(
            "Сделайте фото текущего полиса ОСАГО:",
            reply_markup=get_navigation_keyboard()
        )
        return CURRENT_POLICY_PHOTO
    else:
        # Сохраняем введенные вручную данные
        user_data[user_id]['current_policy_data'] = update.message.text
        await update.message.reply_text(
            "Введите дату начала действия страховки (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE

async def current_policy_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото текущего полиса"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        return await current_policy_input(update, context)
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        # Сохраняем информацию о фото
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['current_policy_photo'] = photo_file.file_id
        
        # Здесь должна быть логика распознавания данных из фото
        # Пока просто переходим к следующему шагу
        await update.message.reply_text(
            "✅ Фото полиса получено. Теперь введите дату начала действия новой страховки (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото полиса:",
            reply_markup=get_navigation_keyboard()
        )
        return CURRENT_POLICY_PHOTO

async def insurance_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение даты начала страхования"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        user_id = update.message.from_user.id
        if user_data.get(user_id, {}).get('policy_type') == "🔄 Переход из другой страховой":
            return await current_policy_input(update, context)
        else:
            return await policy_type(update, context)
    
    user_id = update.message.from_user.id
    try:
        datetime.strptime(update.message.text, '%d.%m.%Y')
        user_data[user_id]['insurance_start_date'] = update.message.text
    except ValueError:
        await update.message.reply_text(
            "Неверный формат даты. Введите в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE
    
    await update.message.reply_text(
        "Выберите период страхования:",
        reply_markup=ReplyKeyboardMarkup([
            ["✅ Период равен 12 месяцев"],
            ["3 месяца", "4 месяца", "5 месяцев", "6 месяцев"],
            ["7 месяцев", "8 месяцев", "9 месяцев", "10 месяцев"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return INSURANCE_PERIOD

async def insurance_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение периода страхования"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату начала действия страховки:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE
    
    user_id = update.message.from_user.id
    
    if update.message.text == "✅ Период равен 12 месяцев":
        user_data[user_id]['insurance_period'] = "12"
    else:
        # Извлекаем число из текста
        period = ''.join(filter(str.isdigit, update.message.text))
        user_data[user_id]['insurance_period'] = period
    
    await update.message.reply_text(
        "Страхователь и Собственник - одно лицо?",
        reply_markup=ReplyKeyboardMarkup([
            ["✅ Одно лицо", "❌ Разные лица"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return CHOOSE_OWNER_INSURER

async def choose_owner_insurer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора типа собственника/страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Выберите период страхования:",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Период равен 12 месяцев"],
                ["3 месяца", "4 месяца", "5 месяцев", "6 месяцев"],
                ["7 месяцев", "8 месяцев", "9 месяцев", "10 месяцев"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return INSURANCE_PERIOD
    
    user_id = update.message.from_user.id
    choice = update.message.text
    
    user_data[user_id]['is_same_person'] = choice == "✅ Одно лицо"
    
    await update.message.reply_text(
        "Сделайте фото главной страницы паспорта страхователя (с ФИО и датой рождения):",
        reply_markup=get_manual_input_keyboard()
    )
    return INSURER_PASSPORT_MAIN_PHOTO

async def insurer_passport_main_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото главной страницы паспорта страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Страхователь и Собственник - одно лицо?",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Одно лицо", "❌ Разные лица"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return CHOOSE_OWNER_INSURER
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные паспорта страхователя (серия, номер, ФИО, дата рождения, место рождения):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_MAIN_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['insurer_passport_main_photo'] = photo_file.file_id
        
        await update.message.reply_text(
            "✅ Фото получено. Теперь сделайте фото страницы с пропиской страхователя:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_REGISTRATION_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото главной страницы паспорта:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO

async def insurer_passport_main_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод данных паспорта страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото главной страницы паспорта страхователя:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO
    
    user_id = update.message.from_user.id
    user_data[user_id]['insurer_passport_main_manual'] = update.message.text
    
    await update.message.reply_text(
        "Теперь введите данные прописки страхователя:",
        reply_markup=get_navigation_keyboard()
    )
    return INSURER_PASSPORT_REGISTRATION_MANUAL

async def insurer_passport_registration_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото прописки страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото главной страницы паспорта страхователя:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные прописки страхователя:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_REGISTRATION_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['insurer_passport_registration_photo'] = photo_file.file_id
        
        # Проверяем, нужно ли запрашивать данные собственника
        if user_data[user_id]['is_same_person']:
            await update.message.reply_text(
                "✅ Данные страхователя собраны. Теперь выберите тип документа на транспортное средство:",
                reply_markup=ReplyKeyboardMarkup([
                    ["📋 СТС", "📋 ПТС"],
                    ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
                ], resize_keyboard=True)
            )
            return VEHICLE_DOC_TYPE
        else:
            await update.message.reply_text(
                "✅ Данные страхователя собраны. Теперь сделайте фото главной страницы паспорта собственника:",
                reply_markup=get_manual_input_keyboard()
            )
            return OWNER_PASSPORT_MAIN_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото страницы с пропиской:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_REGISTRATION_PHOTO

async def insurer_passport_registration_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод прописки страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите данные паспорта страхователя:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_MAIN_MANUAL
    
    user_id = update.message.from_user.id
    user_data[user_id]['insurer_passport_registration_manual'] = update.message.text
    
    # Проверяем, нужно ли запрашивать данные собственника
    if user_data[user_id]['is_same_person']:
        await update.message.reply_text(
            "✅ Данные страхователя собраны. Теперь выберите тип документа на транспортное средство:",
            reply_markup=ReplyKeyboardMarkup([
                ["📋 СТС", "📋 ПТС"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return VEHICLE_DOC_TYPE
    else:
        await update.message.reply_text(
            "✅ Данные страхователя собраны. Теперь введите данные главной страницы паспорта собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_MAIN_MANUAL

# Аналогичные функции для собственника (если лица разные)
async def owner_passport_main_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото главной страницы паспорта собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото страницы с пропиской страхователя:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_REGISTRATION_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные паспорта собственника:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_MAIN_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['owner_passport_main_photo'] = photo_file.file_id
        
        await update.message.reply_text(
            "✅ Фото получено. Теперь сделайте фото страницы с пропиской собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_REGISTRATION_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото главной страницы паспорта собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_MAIN_PHOTO

async def owner_passport_main_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод данных паспорта собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото главной страницы паспорта собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_MAIN_PHOTO
    
    user_id = update.message.from_user.id
    user_data[user_id]['owner_passport_main_manual'] = update.message.text
    
    await update.message.reply_text(
        "Теперь введите данные прописки собственника:",
        reply_markup=get_navigation_keyboard()
    )
    return OWNER_PASSPORT_REGISTRATION_MANUAL

async def owner_passport_registration_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото прописки собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото главной страницы паспорта собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_MAIN_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные прописки собственника:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_REGISTRATION_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['owner_passport_registration_photo'] = photo_file.file_id
        
        await update.message.reply_text(
            "✅ Данные собственника собраны. Теперь выберите тип документа на транспортное средство:",
            reply_markup=ReplyKeyboardMarkup([
                ["📋 СТС", "📋 ПТС"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return VEHICLE_DOC_TYPE
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото страницы с пропиской собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_REGISTRATION_PHOTO

async def owner_passport_registration_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод прописки собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите данные паспорта собственника:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_MAIN_MANUAL
    
    user_id = update.message.from_user.id
    user_data[user_id]['owner_passport_registration_manual'] = update.message.text
    
    await update.message.reply_text(
        "✅ Данные собственника собраны. Теперь выберите тип документа на транспортное средство:",
        reply_markup=ReplyKeyboardMarkup([
            ["📋 СТС", "📋 ПТС"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return VEHICLE_DOC_TYPE

async def vehicle_doc_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор типа документа на транспортное средство"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        user_id = update.message.from_user.id
        if user_data[user_id]['is_same_person']:
            await update.message.reply_text(
                "Введите данные прописки страхователя:",
                reply_markup=get_navigation_keyboard()
            )
            return INSURER_PASSPORT_REGISTRATION_MANUAL
        else:
            await update.message.reply_text(
                "Введите данные прописки собственника:",
                reply_markup=get_navigation_keyboard()
            )
            return OWNER_PASSPORT_REGISTRATION_MANUAL
    
    user_id = update.message.from_user.id
    user_data[user_id]['vehicle_doc_type'] = update.message.text
    
    await update.message.reply_text(
        f"Сделайте фото первой стороны {update.message.text}:",
        reply_markup=get_manual_input_keyboard()
    )
    return VEHICLE_DOC_FRONT_PHOTO

async def vehicle_doc_front_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото первой стороны документа на ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Выберите тип документа на транспортное средство:",
            reply_markup=ReplyKeyboardMarkup([
                ["📋 СТС", "📋 ПТС"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return VEHICLE_DOC_TYPE
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные транспортного средства (марка, модель, VIN, год выпуска, мощность, госномер):",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_DOC_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['vehicle_doc_front_photo'] = photo_file.file_id
        
        await update.message.reply_text(
            "✅ Фото получено. Теперь сделайте фото второй стороны документа:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_BACK_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото первой стороны документа:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_FRONT_PHOTO

async def vehicle_doc_back_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото второй стороны документа на ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото первой стороны документа:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_FRONT_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_DOC_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['vehicle_doc_back_photo'] = photo_file.file_id
        
        await update.message.reply_text(
            "✅ Данные транспортного средства собраны. Теперь выберите вариант допущенных к управлению:",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Без ограничений"],
                ["👤 Добавить водителя"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return DRIVERS_CHOICE
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото второй стороны документа:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_BACK_PHOTO

async def vehicle_doc_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод данных транспортного средства"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото первой стороны документа:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_FRONT_PHOTO
    
    user_id = update.message.from_user.id
    user_data[user_id]['vehicle_doc_manual'] = update.message.text
    
    await update.message.reply_text(
        "✅ Данные транспортного средства собраны. Теперь выберите вариант допущенных к управлению:",
        reply_markup=ReplyKeyboardMarkup([
            ["✅ Без ограничений"],
            ["👤 Добавить водителя"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return DRIVERS_CHOICE

async def drivers_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор варианта водителей"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото второй стороны документа:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_BACK_PHOTO
    
    user_id = update.message.from_user.id
    
    if update.message.text == "✅ Без ограничений":
        await update.message.reply_text(
            "Введите телефон для связи:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PHONE
    elif update.message.text == "👤 Добавить водителя":
        await update.message.reply_text(
            "Сделайте фото лицевой стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO

async def driver_license_front_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото лицевой стороны водительского удостоверения"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Выберите вариант допущенных к управлению:",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Без ограничений"],
                ["👤 Добавить водителя"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return DRIVERS_CHOICE
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные водительского удостоверения (серия, номер, ФИО, дата выдачи, срок действия):",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['driver_license_front_photo'] = photo_file.file_id
        
        await update.message.reply_text(
            "✅ Фото получено. Теперь сделайте фото обратной стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_BACK_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото лицевой стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO

async def driver_license_back_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото обратной стороны водительского удостоверения"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото лицевой стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите данные водительского удостоверения:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_MANUAL
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        user_data[user_id]['driver_license_back_photo'] = photo_file.file_id
        
        await update.message.reply_text(
            "✅ Данные водителя собраны. Хотите добавить еще одного водителя?",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Завершить добавление"],
                ["👤 Добавить еще водителя"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return ADD_DRIVER
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото обратной стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_BACK_PHOTO

async def driver_license_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ручной ввод данных водительского удостоверения"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото лицевой стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO
    
    user_id = update.message.from_user.id
    user_data[user_id]['driver_license_manual'] = update.message.text
    
    await update.message.reply_text(
        "✅ Данные водителя собраны. Хотите добавить еще одного водителя?",
        reply_markup=ReplyKeyboardMarkup([
            ["✅ Завершить добавление"],
            ["👤 Добавить еще водителя"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return ADD_DRIVER

async def add_driver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка добавления дополнительных водителей"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото обратной стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_BACK_PHOTO
    
    user_id = update.message.from_user.id
    
    if update.message.text == "✅ Завершить добавление":
        await update.message.reply_text(
            "Введите телефон для связи:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PHONE
    elif update.message.text == "👤 Добавить еще водителя":
        await update.message.reply_text(
            "Сделайте фото лицевой стороны водительского удостоверения следующего водителя:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO

async def insurer_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение телефона для связи"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Хотите добавить еще одного водителя?",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Завершить добавление"],
                ["👤 Добавить еще водителя"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return ADD_DRIVER
    
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("Пожалуйста, начните с команды /start")
        return ConversationHandler.END
        
    user_data[user_id]['insurer_phone'] = update.message.text
    
    # Генерируем образец полиса для предварительного просмотра
    try:
        sample_doc = WordGenerator.generate_sample_policy(user_data[user_id])
        file_stream = io.BytesIO()
        sample_doc.save(file_stream)
        file_stream.seek(0)
        file_stream.name = f"Образец_полиса_{datetime.now().strftime('%d%m%Y_%H%M')}.docx"
        
        await update.message.reply_text(
            "✅ Все данные собраны! Вот образец вашего полиса. Проверьте информацию:",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Всё верно, отправить"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        
        await update.message.reply_document(
            document=file_stream,
            caption="📄 Образец полиса ОСАГО"
        )
        
        return FINAL_CONFIRMATION
        
    except Exception as e:
        print(f"❌ Ошибка генерации образца: {e}")
        await update.message.reply_text(
            "✅ Все данные собраны!",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Подтвердить и отправить"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return CONFIRMATION

async def final_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финальное подтверждение после просмотра образца"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите телефон для связи:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PHONE
    
    user_id = update.message.from_user.id
    
    if update.message.text == "✅ Всё верно, отправить":
        return await send_confirmation(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, подтвердите отправку данных:",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Всё верно, отправить"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return FINAL_CONFIRMATION

async def confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения заявки (старая версия)"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите телефон для связи:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PHONE
    
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("Пожалуйста, начните с команды /start")
        return ConversationHandler.END
        
    return await send_confirmation(update, context)

async def send_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение и отправка данных"""
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("Пожалуйста, начните с команды /start")
        return ConversationHandler.END
        
    data = user_data[user_id]
    
    try:
        # Создаем Word документ для менеджера
        doc = WordGenerator.generate_application_docx(data)
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        file_stream.name = f"Заявка_{data.get('insurer_fio', 'Клиент')}_{datetime.now().strftime('%d%m%Y_%H%M')}.docx"
        
        # Отправляем Word документ менеджеру
        MANAGER_CHAT_ID = os.getenv('MANAGER_CHAT_ID')
        if MANAGER_CHAT_ID:
            try:
                await context.bot.send_document(
                    chat_id=int(MANAGER_CHAT_ID),
                    document=file_stream,
                    caption=f"📄 Новая заявка ОСАГО от {data.get('insurer_fio', 'Клиент')}"
                )
                print(f"✅ Word документ отправлен менеджеру {MANAGER_CHAT_ID}")
            except Exception as e:
                print(f"❌ Ошибка отправки Word менеджеру: {e}")
        
        # Генерируем и отправляем образец полиса пользователю
        sample_doc = WordGenerator.generate_sample_policy(data)
        sample_stream = io.BytesIO()
        sample_doc.save(sample_stream)
        sample_stream.seek(0)
        sample_stream.name = f"Образец_полиса_{datetime.now().strftime('%d%m%Y_%H%M')}.docx"
        
        # Отправляем подтверждение клиенту
        await update.message.reply_text(
            "✅ Заявка успешно отправлена!\n\n"
            "В течении 1 часа с Вами свяжется менеджер, для возможного уточнения деталей и дальнейшего оформления!\n\n"
            "С Уважением, АО 'Альфастрахование'",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Отправляем образец полиса клиенту
        await update.message.reply_document(
            document=sample_stream,
            caption="📄 Образец вашего полиса ОСАГО"
        )
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        await update.message.reply_text(
            "Произошла непредвиденная ошибка. "
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    # Очищаем данные пользователя
    if user_id in user_data:
        del user_data[user_id]
    
    return ConversationHandler.END

async def help_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка запроса помощи"""
    user_id = update.message.from_user.id
    
    # Сохраняем текущее состояние для возврата
    if update.message.text == "🆘 Помощь":
        # Определяем текущее состояние на основе контекста
        current_state = context.user_data.get('current_state', START)
        context.user_data['previous_state'] = current_state
    
    await update.message.reply_text(
        "Опишите вашу проблему или вопрос. Вы можете отправить текст или фото:",
        reply_markup=ReplyKeyboardMarkup([
            ["⬅️ Назад к форме", "🏠 В начало"]
        ], resize_keyboard=True)
    )
    
    return HELP_REQUEST

async def process_help_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка сообщения помощи"""
    user_id = update.message.from_user.id
    
    if update.message.text == "⬅️ Назад к форме":
        previous_state = context.user_data.get('previous_state', START)
        context.user_data.pop('previous_state', None)
        
        # Возвращаемся к предыдущему состоянию
        if previous_state == START:
            return await start(update, context)
        # Здесь нужно добавить логику возврата к другим состояниям
        else:
            return await start(update, context)
    elif update.message.text == "🏠 В начало":
        context.user_data.pop('previous_state', None)
        return await start(update, context)
    
    # Отправляем сообщение менеджеру
    MANAGER_CHAT_ID = os.getenv('MANAGER_CHAT_ID')
    if MANAGER_CHAT_ID:
        help_text = f"🆘 ПОМОЩЬ от пользователя {update.message.from_user.first_name} (@{update.message.from_user.username or 'N/A'}):\n\n"
        
        if update.message.text:
            help_text += update.message.text
        elif update.message.caption:
            help_text += update.message.caption
        
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            await context.bot.send_photo(
                chat_id=int(MANAGER_CHAT_ID),
                photo=photo_file.file_id,
                caption=help_text
            )
        else:
            await context.bot.send_message(
                chat_id=int(MANAGER_CHAT_ID),
                text=help_text
            )
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено менеджеру. Мы свяжемся с вами в ближайшее время.",
        reply_markup=ReplyKeyboardMarkup([
            ["⬅️ Назад к форме", "🏠 В начало"]
        ], resize_keyboard=True)
    )
    
    return HELP_REQUEST

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена разговора"""
    user_id = update.message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    await update.message.reply_text(
        "Заявка отменена.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main():
    """Запуск бота"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logging.error("❌ Ошибка: не задан TELEGRAM_BOT_TOKEN")
        return
    
    try:
        application = Application.builder().token(TOKEN).build()
        
        # Основной ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                POLICY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_type)],
                CURRENT_POLICY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, current_policy_input)],
                CURRENT_POLICY_PHOTO: [
                    MessageHandler(filters.PHOTO, current_policy_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, current_policy_photo)
                ],
                INSURANCE_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurance_start_date)],
                INSURANCE_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurance_period)],
                CHOOSE_OWNER_INSURER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_owner_insurer)],
                INSURER_PASSPORT_MAIN_PHOTO: [
                    MessageHandler(filters.PHOTO, insurer_passport_main_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_main_photo)
                ],
                INSURER_PASSPORT_MAIN_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_main_manual)],
                INSURER_PASSPORT_REGISTRATION_PHOTO: [
                    MessageHandler(filters.PHOTO, insurer_passport_registration_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_registration_photo)
                ],
                INSURER_PASSPORT_REGISTRATION_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_registration_manual)],
                OWNER_PASSPORT_MAIN_PHOTO: [
                    MessageHandler(filters.PHOTO, owner_passport_main_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_main_photo)
                ],
                OWNER_PASSPORT_MAIN_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_main_manual)],
                OWNER_PASSPORT_REGISTRATION_PHOTO: [
                    MessageHandler(filters.PHOTO, owner_passport_registration_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_registration_photo)
                ],
                OWNER_PASSPORT_REGISTRATION_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_registration_manual)],
                VEHICLE_DOC_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_doc_type)],
                VEHICLE_DOC_FRONT_PHOTO: [
                    MessageHandler(filters.PHOTO, vehicle_doc_front_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_doc_front_photo)
                ],
                VEHICLE_DOC_BACK_PHOTO: [
                    MessageHandler(filters.PHOTO, vehicle_doc_back_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_doc_back_photo)
                ],
                VEHICLE_DOC_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_doc_manual)],
                DRIVERS_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, drivers_choice)],
                DRIVER_LICENSE_FRONT_PHOTO: [
                    MessageHandler(filters.PHOTO, driver_license_front_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, driver_license_front_photo)
                ],
                DRIVER_LICENSE_BACK_PHOTO: [
                    MessageHandler(filters.PHOTO, driver_license_back_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, driver_license_back_photo)
                ],
                DRIVER_LICENSE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, driver_license_manual)],
                ADD_DRIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_driver)],
                INSURER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_phone)],
                CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmation_handler)],
                FINAL_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_confirmation)],
                HELP_REQUEST: [
                    MessageHandler(filters.TEXT | filters.PHOTO, process_help_message)
                ],
            },
            fallbacks=[
                CommandHandler('start', start),
                CommandHandler('cancel', cancel),
                CommandHandler('help', help_request),
                MessageHandler(filters.Regex('^🆘 Помощь$'), help_request),
                MessageHandler(filters.Regex('^🏠 В начало$'), start)
            ]
        )
        
        application.add_handler(conv_handler)
        
        # Отдельный обработчик для команды help
        application.add_handler(CommandHandler('help', help_request))
        
        logging.info("🤖 Бот запускается...")
        print("=== БОТ ЗАПУЩЕН НА RENDER ===")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )
        
    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {e}")
        print("Бот остановлен из-за ошибки:", e)
        time.sleep(10)
        main()

if __name__ == '__main__':
    main()
