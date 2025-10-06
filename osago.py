import os
import logging
import io
import re
import traceback
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
import tempfile

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
    START, POLICY_TYPE, CURRENT_POLICY_DATA, CURRENT_POLICY_PHOTO,
    INSURANCE_START_DATE, INSURANCE_PERIOD, CHOOSE_OWNER_INSURER,
    INSURER_PASSPORT_MAIN_PHOTO, INSURER_PASSPORT_REGISTRATION_PHOTO,
    INSURER_FIO, INSURER_PASSPORT_SERIES_NUMBER, INSURER_BIRTHDATE,
    INSURER_PASSPORT_ISSUED_BY, INSURER_PASSPORT_ISSUE_DATE, INSURER_PASSPORT_DEPARTMENT_CODE,
    OWNER_PASSPORT_MAIN_PHOTO, OWNER_PASSPORT_REGISTRATION_PHOTO,
    OWNER_FIO, OWNER_PASSPORT_SERIES_NUMBER, OWNER_BIRTHDATE,
    OWNER_PASSPORT_ISSUED_BY, OWNER_PASSPORT_ISSUE_DATE, OWNER_PASSPORT_DEPARTMENT_CODE,
    VEHICLE_DOC_TYPE, VEHICLE_DOC_FRONT_PHOTO, VEHICLE_DOC_BACK_PHOTO,
    VEHICLE_VIN, VEHICLE_BRAND, VEHICLE_MODEL, VEHICLE_YEAR, VEHICLE_POWER, VEHICLE_REG_NUMBER,
    DRIVERS_CHOICE, DRIVER_LICENSE_FRONT_PHOTO, DRIVER_LICENSE_BACK_PHOTO,
    DRIVER_FIO, DRIVER_BIRTHDATE, DRIVER_LICENSE_ISSUE_DATE, DRIVER_LICENSE_EXPIRY, DRIVER_LICENSE_NUMBER,
    ADD_DRIVER, INSURER_PHONE, CONFIRMATION, HELP_REQUEST, FINAL_CONFIRMATION
) = range(45)

user_data = {}

# ==================== OCR ПРОЦЕССОР ====================
OCR_AVAILABLE = False  # Временно отключаем OCR для стабильности

class OCRProcessor:
    """Заглушка для OCR - всегда возвращает пустые данные"""
    
    @staticmethod
    def is_available():
        return False
    
    @staticmethod
    def extract_text_from_image(image_path):
        return ""
    
    @staticmethod
    def extract_passport_data(text):
        return {}
    
    @staticmethod
    def extract_vehicle_data(text):
        return {}
    
    @staticmethod
    def extract_license_data(text):
        return {}
    
    @staticmethod
    def format_ocr_results(data_dict, data_type):
        return "Система распознавания документов временно недоступна. Пожалуйста, введите данные вручную."

class DocumentProcessor:
    """Класс для обработки документов и извлечения данных"""
    
    @staticmethod
    async def process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_type: str):
        """Обработка фото документа"""
        user_id = update.message.from_user.id
        
        if update.message.photo:
            try:
                # Скачиваем фото
                photo_file = await update.message.photo[-1].get_file()
                
                # Сохраняем фото
                if user_id not in user_data:
                    user_data[user_id] = {}
                
                user_data[user_id][f'{photo_type}_photo'] = photo_file.file_id
                user_data[user_id]['has_photos'] = True
                
                return True
                
            except Exception as e:
                print(f"Ошибка обработки фото: {e}")
                return False
        return False

class WordGenerator:
    @staticmethod
    def generate_application_docx(data):
        """Генерация Word документа с заявкой для менеджера"""
        doc = Document()
        
        # Заголовок
        title = doc.add_heading('ЗАЯВКА НА ОСАГО', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Информация о типе полиса
        policy_type = doc.add_paragraph()
        policy_type.add_run(f"Тип заявки: {data.get('policy_type', 'Не указано')}").bold = True
        
        if data.get('current_policy_data'):
            policy_info = f"Данные текущего полиса: {data.get('current_policy_data', 'Не указано')}"
            policy_type.add_run(f"\n{policy_info}")
        
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
        if not data.get('is_same_person', True):
            doc.add_heading('СОБСТВЕННИК', level=1)
            doc.add_paragraph(f"ФИО: {data.get('owner_fio', 'Не указано')}")
            doc.add_paragraph("Паспортные данные: предоставлены в фотографиях")
            doc.add_paragraph()
        
        # Раздел: Транспортное средство
        doc.add_heading('ТРАНСПОРТНОЕ СРЕДСТВО', level=1)
        
        vehicle_info = [
            f"VIN: {data.get('vehicle_vin', 'Не указано')}",
            f"Марка: {data.get('vehicle_brand', 'Не указано')}",
            f"Модель: {data.get('vehicle_model', 'Не указано')}",
            f"Год выпуска: {data.get('vehicle_year', 'Не указано')}",
            f"Мощность: {data.get('vehicle_power', 'Не указано')} л.с.",
            f"Госномер: {data.get('vehicle_reg_number', 'Не указано')}",
            f"Документ: {data.get('vehicle_doc_type', 'Не указано')}"
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
                
                doc.add_paragraph(f"   В/у: {driver.get('license_number', 'Не указано')}")
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
        
        # Информация о фото документах
        if data.get('has_photos'):
            doc.add_paragraph()
            photos_paragraph = doc.add_paragraph()
            photos_paragraph.add_run("ПРИЛОЖЕННЫЕ ФОТО ДОКУМЕНТОВ:").bold = True
            
            photo_types = {
                'insurer_passport_main': 'Главная страница паспорта страхователя',
                'insurer_passport_registration': 'Прописка страхователя',
                'owner_passport_main': 'Главная страница паспорта собственника',
                'owner_passport_registration': 'Прописка собственника',
                'vehicle_doc_front': f'Лицевая сторона {data.get("vehicle_doc_type")}',
                'vehicle_doc_back': f'Обратная сторона {data.get("vehicle_doc_type")}',
                'driver_license_front': 'Лицевая сторона водительского удостоверения',
                'driver_license_back': 'Обратная сторона водительского удостоверения'
            }
            
            for photo_key, description in photo_types.items():
                if data.get(f'{photo_key}_photo'):
                    photos_paragraph.add_run(f"\n- {description}")
        
        # Подпись
        doc.add_paragraph()
        doc.add_paragraph("Заявка успешно оформлена!").bold = True
        doc.add_paragraph("В течении 1 часа с Вами свяжется менеджер, для возможного уточнения деталей и дальнейшего оформления!")
        doc.add_paragraph("С Уважением, АО 'Альфастрахование'").bold = True
        
        return doc

    @staticmethod
    def generate_sample_policy(data):
        """Генерация образца полиса ОСАГО"""
        doc = Document()
        
        # Настройка стилей
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(10)
        
        # Заголовок
        title = doc.add_heading('Договор ОСАГО заключен в виде электронного документа', level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Основной заголовок
        main_title = doc.add_heading('СТРАХОВОЙ ПОЛИС', level=1)
        main_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Номер полиса и стоимость
        policy_number = doc.add_paragraph()
        policy_number.alignment = WD_ALIGN_PARAGRAPH.CENTER
        policy_number.add_run(f"№ 8989 руб. 87 коп.").bold = True
        
        # Подзаголовок
        sub_title = doc.add_heading('ОБЯЗАТЕЛЬНОГО СТРАХОВАНИЯ ГРАЖДАНСКОЙ ОТВЕТСТВЕННОСТИ ВЛАДЕЛЬЦЕВ ТРАНСПОРТНЫХ СРЕДСТВ', level=2)
        sub_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Срок страхования
        insurance_period = doc.add_paragraph()
        insurance_period.add_run(f"Срок страхования с 00 ч. 00 мин. {data.get('insurance_start_date', '01.01.2024')} г.\n")
        insurance_period.add_run(f"по 24 ч. 00 мин. {data.get('insurance_end_date', '01.01.2025')} г.\n\n")
        
        # 1. Страхователь и собственник
        p1 = doc.add_paragraph()
        p1.add_run("1. Страхователь (полное наименование юридического лица или фамилия, имя, отчество гражданина)\n").bold = True
        p1.add_run(f"{data.get('insurer_fio', 'Не указано')}\n\n")
        
        p1.add_run("Собственник транспортного средства (полное наименование юридического лица или фамилия, имя, отчество гражданина, коэффициент КБМ)\n").bold = True
        if data.get('is_same_person', True):
            p1.add_run(f"{data.get('insurer_fio', 'Не указано')}\n")
        else:
            p1.add_run(f"{data.get('owner_fio', 'Не указано')}\n")
        
        # 2. Транспортное средство
        p2 = doc.add_paragraph()
        p2.add_run("2. Транспортное средство используется с прицепом: □ да, ☑ нет\n\n").bold = True
        
        # Таблица с данными ТС
        table = doc.add_table(rows=2, cols=3)
        table.style = 'Table Grid'
        
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Транспортное средство'
        hdr_cells[1].text = 'Идентификационный номер транспортного средства'
        hdr_cells[2].text = 'Государственный регистрационный знак транспортного средства'
        
        row_cells = table.rows[1].cells
        row_cells[0].text = f"{data.get('vehicle_brand', '')} {data.get('vehicle_model', '')}"
        row_cells[1].text = data.get('vehicle_vin', 'Не указано')
        row_cells[2].text = data.get('vehicle_reg_number', 'Не указано')
        
        doc.add_paragraph()
        
        # Водяной знак "ОБРАЗЕЦ"
        for i in range(10):
            watermark = doc.add_paragraph()
            watermark_run = watermark.add_run("О Б Р А З Е Ц")
            watermark_run.font.size = Pt(72)
            watermark_run.font.color.rgb = RGBColor(200, 200, 200)
            watermark.alignment = WD_ALIGN_PARAGRAPH.CENTER
            watermark.paragraph_format.space_after = Pt(30)
        
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

def validate_date(date_text):
    """Проверка корректности даты"""
    try:
        datetime.strptime(date_text, '%d.%m.%Y')
        return True
    except ValueError:
        return False

def validate_passport_series_number(text):
    """Проверка формата серии и номера паспорта"""
    pattern = r'^\d{4} \d{6}$'
    return bool(re.match(pattern, text))

def validate_license_number(text):
    """Проверка формата номера водительского удостоверения"""
    pattern = r'^[0-9]{2} [0-9]{6,9}$'
    return bool(re.match(pattern, text))

def validate_vin(text):
    """Проверка формата VIN"""
    return len(text) >= 17

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало разговора"""
    welcome_text = (
        "Добро пожаловать!\n\n"
        "Здесь Вы сможете оформить ОСАГО от АО АльфаСтрахование, с возможностью перехода из другой страховой компании.\n\n"
        "Данный бот собирает персональную информацию на основании 152-ФЗ РФ ссылка для ознакомления https://www.consultant.ru/document/cons_doc_LAW_61801/\n\n"
        "После сбора информации все данные передаются представителю организации для дальнейшего оформления полиса."
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
        'drivers': [],
        'has_photos': False
    }
    
    if choice == "🔄 Переход из другой страховой":
        await update.message.reply_text(
            "Введите серию и номер текущего полиса ОСАГО (например: XXX 123456789):",
            reply_markup=ReplyKeyboardMarkup([
                ["🚫 Нет серии (только номер)", "📷 Сделать фото полиса"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return CURRENT_POLICY_DATA
    else:
        await update.message.reply_text(
            "Введите дату начала действия страховки (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE

async def current_policy_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод данных текущего полиса"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        return await start(update, context)
    elif update.message.text == "📷 Сделать фото полиса":
        await update.message.reply_text(
            "Сделайте фото текущего полиса ОСАГО:",
            reply_markup=get_navigation_keyboard()
        )
        return CURRENT_POLICY_PHOTO
    
    user_id = update.message.from_user.id
    
    if update.message.text == "🚫 Нет серии (только номер)":
        await update.message.reply_text(
            "Введите номер текущего полиса:",
            reply_markup=get_navigation_keyboard()
        )
        return CURRENT_POLICY_DATA
    else:
        user_data[user_id]['current_policy_data'] = update.message.text
        
        await update.message.reply_text(
            "Введите дату начала действия новой страховки (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE

async def current_policy_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото текущего полиса"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите серию и номер текущего полиса ОСАГО:",
            reply_markup=ReplyKeyboardMarkup([
                ["🚫 Нет серии (только номер)", "📷 Сделать фото полиса"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return CURRENT_POLICY_DATA
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        await DocumentProcessor.process_photo(update, context, 'current_policy')
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
    """Обработка даты начала страхования"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        return await start(update, context)
    
    user_id = update.message.from_user.id
    date_text = update.message.text
    
    if not validate_date(date_text):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE
    
    user_data[user_id]['insurance_start_date'] = date_text
    
    await update.message.reply_text(
        "Выберите период страхования:",
        reply_markup=ReplyKeyboardMarkup([
            ["3 месяца", "4 месяца", "5 месяцев", "6 месяцев"],
            ["7 месяцев", "8 месяцев", "9 месяцев", "10 месяцев"],
            ["11 месяцев", "12 месяцев"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return INSURANCE_PERIOD

async def insurance_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка периода страхования"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату начала действия страховки (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE
    
    user_id = update.message.from_user.id
    period = update.message.text
    
    # Проверяем, что выбран допустимый период
    valid_periods = ["3 месяца", "4 месяца", "5 месяцев", "6 месяцев", 
                    "7 месяцев", "8 месяцев", "9 месяцев", "10 месяцев", 
                    "11 месяцев", "12 месяцев"]
    
    if period not in valid_periods:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите период из предложенных вариантов:",
            reply_markup=ReplyKeyboardMarkup([
                ["3 месяца", "4 месяца", "5 месяцев", "6 месяцев"],
                ["7 месяцев", "8 месяцев", "9 месяцев", "10 месяцев"],
                ["11 месяцев", "12 месяцев"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return INSURANCE_PERIOD
    
    user_data[user_id]['insurance_period'] = period
    
    await update.message.reply_text(
        "Страхователь и собственник транспортного средства - это одно и то же лицо?",
        reply_markup=ReplyKeyboardMarkup([
            ["✅ Да, одно лицо", "❌ Нет, разные лица"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return CHOOSE_OWNER_INSURER

async def choose_owner_insurer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор, одно ли лицо страхователь и собственник"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Выберите период страхования:",
            reply_markup=ReplyKeyboardMarkup([
                ["3 месяца", "4 месяца", "5 месяцев", "6 месяцев"],
                ["7 месяцев", "8 месяцев", "9 месяцев", "10 месяцев"],
                ["11 месяцев", "12 месяцев"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return INSURANCE_PERIOD
    
    user_id = update.message.from_user.id
    choice = update.message.text
    
    if choice == "✅ Да, одно лицо":
        user_data[user_id]['is_same_person'] = True
        await update.message.reply_text(
            "Сделайте фото главной страницы паспорта (разворот с фото):",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO
    else:
        user_data[user_id]['is_same_person'] = False
        await update.message.reply_text(
            "Сделайте фото главной страницы паспорта страхователя (разворот с фото):",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO

async def insurer_passport_main_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото главной страницы паспорта страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Страхователь и собственник транспортного средства - это одно и то же лицо?",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Да, одно лицо", "❌ Нет, разные лица"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return CHOOSE_OWNER_INSURER
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите ФИО страхователя полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'insurer_passport_main')
        if success:
            await update.message.reply_text(
                "✅ Фото получено. Теперь сделайте фото страницы с пропиской:",
                reply_markup=get_manual_input_keyboard()
            )
            return INSURER_PASSPORT_REGISTRATION_PHOTO
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return INSURER_PASSPORT_MAIN_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото главной страницы паспорта:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO

async def insurer_passport_registration_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото страницы с пропиской страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото главной страницы паспорта страхователя (разворот с фото):",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите ФИО страхователя полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'insurer_passport_registration')
        if success:
            await update.message.reply_text(
                "✅ Фото прописки получено. Теперь введите ФИО страхователя полностью:",
                reply_markup=get_navigation_keyboard()
            )
            return INSURER_FIO
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return INSURER_PASSPORT_REGISTRATION_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото страницы с пропиской:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_REGISTRATION_PHOTO

async def insurer_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод ФИО страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото страницы с пропиской страхователя:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_REGISTRATION_PHOTO
    
    user_id = update.message.from_user.id
    user_data[user_id]['insurer_fio'] = update.message.text
    
    await update.message.reply_text(
        "Введите серию и номер паспорта страхователя (в формате 1234 567890):",
        reply_markup=get_navigation_keyboard()
    )
    return INSURER_PASSPORT_SERIES_NUMBER

async def insurer_passport_series_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод серии и номера паспорта страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите ФИО страхователя полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_FIO
    
    user_id = update.message.from_user.id
    passport_data = update.message.text
    
    if not validate_passport_series_number(passport_data):
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите серию и номер паспорта в формате 1234 567890:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_SERIES_NUMBER
    
    user_data[user_id]['insurer_passport_series_number'] = passport_data
    
    await update.message.reply_text(
        "Введите дату рождения страхователя (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_navigation_keyboard()
    )
    return INSURER_BIRTHDATE

async def insurer_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод даты рождения страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите серию и номер паспорта страхователя (в формате 1234 567890):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_SERIES_NUMBER
    
    user_id = update.message.from_user.id
    birthdate = update.message.text
    
    if not validate_date(birthdate):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_BIRTHDATE
    
    user_data[user_id]['insurer_birthdate'] = birthdate
    
    await update.message.reply_text(
        "Введите, кем выдан паспорт страхователя:",
        reply_markup=get_navigation_keyboard()
    )
    return INSURER_PASSPORT_ISSUED_BY

async def insurer_passport_issued_by(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод информации о том, кем выдан паспорт страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату рождения страхователя (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_BIRTHDATE
    
    user_id = update.message.from_user.id
    user_data[user_id]['insurer_passport_issued_by'] = update.message.text
    
    await update.message.reply_text(
        "Введите дату выдачи паспорта страхователя (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_navigation_keyboard()
    )
    return INSURER_PASSPORT_ISSUE_DATE

async def insurer_passport_issue_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод даты выдачи паспорта страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите, кем выдан паспорт страхователя:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_ISSUED_BY
    
    user_id = update.message.from_user.id
    issue_date = update.message.text
    
    if not validate_date(issue_date):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_ISSUE_DATE
    
    user_data[user_id]['insurer_passport_issue_date'] = issue_date
    
    await update.message.reply_text(
        "Введите код подразделения паспорта страхователя:",
        reply_markup=get_navigation_keyboard()
    )
    return INSURER_PASSPORT_DEPARTMENT_CODE

async def insurer_passport_department_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод кода подразделения паспорта страхователя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату выдачи паспорта страхователя (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_ISSUE_DATE
    
    user_id = update.message.from_user.id
    user_data[user_id]['insurer_passport_department_code'] = update.message.text
    
    # Если собственник и страхователь - разные лица, запрашиваем данные собственника
    if not user_data[user_id].get('is_same_person', True):
        await update.message.reply_text(
            "Теперь введите данные собственника транспортного средства. Сделайте фото главной страницы паспорта собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_MAIN_PHOTO
    else:
        # Если одно лицо, переходим к данным ТС
        await update.message.reply_text(
            "Выберите тип документа на транспортное средство:",
            reply_markup=ReplyKeyboardMarkup([
                ["ПТС", "СТС"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return VEHICLE_DOC_TYPE

async def owner_passport_main_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото главной страницы паспорта собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите код подразделения паспорта страхователя:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PASSPORT_DEPARTMENT_CODE
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите ФИО собственника полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'owner_passport_main')
        if success:
            await update.message.reply_text(
                "✅ Фото получено. Теперь сделайте фото страницы с пропиской собственника:",
                reply_markup=get_manual_input_keyboard()
            )
            return OWNER_PASSPORT_REGISTRATION_PHOTO
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return OWNER_PASSPORT_MAIN_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото главной страницы паспорта собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_MAIN_PHOTO

async def owner_passport_registration_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото страницы с пропиской собственника"""
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
            "Введите ФИО собственника полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'owner_passport_registration')
        if success:
            await update.message.reply_text(
                "✅ Фото прописки получено. Теперь введите ФИО собственника полностью:",
                reply_markup=get_navigation_keyboard()
            )
            return OWNER_FIO
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return OWNER_PASSPORT_REGISTRATION_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото страницы с пропиской собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_REGISTRATION_PHOTO

async def owner_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод ФИО собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото страницы с пропиской собственника:",
            reply_markup=get_manual_input_keyboard()
        )
        return OWNER_PASSPORT_REGISTRATION_PHOTO
    
    user_id = update.message.from_user.id
    user_data[user_id]['owner_fio'] = update.message.text
    
    await update.message.reply_text(
        "Введите серию и номер паспорта собственника (в формате 1234 567890):",
        reply_markup=get_navigation_keyboard()
    )
    return OWNER_PASSPORT_SERIES_NUMBER

async def owner_passport_series_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод серии и номера паспорта собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите ФИО собственника полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_FIO
    
    user_id = update.message.from_user.id
    passport_data = update.message.text
    
    if not validate_passport_series_number(passport_data):
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите серию и номер паспорта в формате 1234 567890:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_SERIES_NUMBER
    
    user_data[user_id]['owner_passport_series_number'] = passport_data
    
    await update.message.reply_text(
        "Введите дату рождения собственника (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_navigation_keyboard()
    )
    return OWNER_BIRTHDATE

async def owner_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод даты рождения собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите серию и номер паспорта собственника (в формате 1234 567890):",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_SERIES_NUMBER
    
    user_id = update.message.from_user.id
    birthdate = update.message.text
    
    if not validate_date(birthdate):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_BIRTHDATE
    
    user_data[user_id]['owner_birthdate'] = birthdate
    
    await update.message.reply_text(
        "Введите, кем выдан паспорт собственника:",
        reply_markup=get_navigation_keyboard()
    )
    return OWNER_PASSPORT_ISSUED_BY

async def owner_passport_issued_by(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод информации о том, кем выдан паспорт собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату рождения собственника (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_BIRTHDATE
    
    user_id = update.message.from_user.id
    user_data[user_id]['owner_passport_issued_by'] = update.message.text
    
    await update.message.reply_text(
        "Введите дату выдачи паспорта собственника (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_navigation_keyboard()
    )
    return OWNER_PASSPORT_ISSUE_DATE

async def owner_passport_issue_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод даты выдачи паспорта собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите, кем выдан паспорт собственника:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_ISSUED_BY
    
    user_id = update.message.from_user.id
    issue_date = update.message.text
    
    if not validate_date(issue_date):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_ISSUE_DATE
    
    user_data[user_id]['owner_passport_issue_date'] = issue_date
    
    await update.message.reply_text(
        "Введите код подразделения паспорта собственника:",
        reply_markup=get_navigation_keyboard()
    )
    return OWNER_PASSPORT_DEPARTMENT_CODE

async def owner_passport_department_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод кода подразделения паспорта собственника"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату выдачи паспорта собственника (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return OWNER_PASSPORT_ISSUE_DATE
    
    user_id = update.message.from_user.id
    user_data[user_id]['owner_passport_department_code'] = update.message.text
    
    await update.message.reply_text(
        "Выберите тип документа на транспортное средство:",
        reply_markup=ReplyKeyboardMarkup([
            ["ПТС", "СТС"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return VEHICLE_DOC_TYPE

async def vehicle_doc_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор типа документа на ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        if not user_data.get(update.message.from_user.id, {}).get('is_same_person', True):
            await update.message.reply_text(
                "Введите код подразделения паспорта собственника:",
                reply_markup=get_navigation_keyboard()
            )
            return OWNER_PASSPORT_DEPARTMENT_CODE
        else:
            await update.message.reply_text(
                "Введите код подразделения паспорта страхователя:",
                reply_markup=get_navigation_keyboard()
            )
            return INSURER_PASSPORT_DEPARTMENT_CODE
    
    user_id = update.message.from_user.id
    doc_type = update.message.text
    
    if doc_type not in ["ПТС", "СТС"]:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите тип документа из предложенных вариантов:",
            reply_markup=ReplyKeyboardMarkup([
                ["ПТС", "СТС"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return VEHICLE_DOC_TYPE
    
    user_data[user_id]['vehicle_doc_type'] = doc_type
    
    await update.message.reply_text(
        f"Сделайте фото лицевой стороны {doc_type}:",
        reply_markup=get_manual_input_keyboard()
    )
    return VEHICLE_DOC_FRONT_PHOTO

async def vehicle_doc_front_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото лицевой стороны документа ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Выберите тип документа на транспортное средство:",
            reply_markup=ReplyKeyboardMarkup([
                ["ПТС", "СТС"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return VEHICLE_DOC_TYPE
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите VIN номер транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_VIN
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'vehicle_doc_front')
        if success:
            await update.message.reply_text(
                f"✅ Фото лицевой стороны {user_data[user_id]['vehicle_doc_type']} получено. Теперь сделайте фото обратной стороны:",
                reply_markup=get_manual_input_keyboard()
            )
            return VEHICLE_DOC_BACK_PHOTO
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return VEHICLE_DOC_FRONT_PHOTO
    else:
        await update.message.reply_text(
            f"Пожалуйста, отправьте фото лицевой стороны {user_data[user_id]['vehicle_doc_type']}:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_FRONT_PHOTO

async def vehicle_doc_back_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото обратной стороны документа ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            f"Сделайте фото лицевой стороны {user_data[update.message.from_user.id]['vehicle_doc_type']}:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_FRONT_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите VIN номер транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_VIN
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'vehicle_doc_back')
        if success:
            await update.message.reply_text(
                "✅ Фото получено. Теперь введите VIN номер транспортного средства:",
                reply_markup=get_navigation_keyboard()
            )
            return VEHICLE_VIN
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return VEHICLE_DOC_BACK_PHOTO
    else:
        await update.message.reply_text(
            f"Пожалуйста, отправьте фото обратной стороны {user_data[user_id]['vehicle_doc_type']}:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_BACK_PHOTO

async def vehicle_vin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод VIN номера ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            f"Сделайте фото обратной стороны {user_data[update.message.from_user.id]['vehicle_doc_type']}:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_BACK_PHOTO
    
    user_id = update.message.from_user.id
    vin = update.message.text.upper()
    
    if not validate_vin(vin):
        await update.message.reply_text(
            "❌ VIN должен содержать не менее 17 символов. Пожалуйста, введите корректный VIN:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_VIN
    
    user_data[user_id]['vehicle_vin'] = vin
    
    await update.message.reply_text(
        "Введите марку транспортного средства:",
        reply_markup=get_navigation_keyboard()
    )
    return VEHICLE_BRAND

async def vehicle_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод марки ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите VIN номер транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_VIN
    
    user_id = update.message.from_user.id
    user_data[user_id]['vehicle_brand'] = update.message.text
    
    await update.message.reply_text(
        "Введите модель транспортного средства:",
        reply_markup=get_navigation_keyboard()
    )
    return VEHICLE_MODEL

async def vehicle_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод модели ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите марку транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_BRAND
    
    user_id = update.message.from_user.id
    user_data[user_id]['vehicle_model'] = update.message.text
    
    await update.message.reply_text(
        "Введите год выпуска транспортного средства:",
        reply_markup=get_navigation_keyboard()
    )
    return VEHICLE_YEAR

async def vehicle_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод года выпуска ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите модель транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_MODEL
    
    user_id = update.message.from_user.id
    year = update.message.text
    
    if not year.isdigit() or len(year) != 4 or int(year) < 1900 or int(year) > datetime.now().year + 1:
        await update.message.reply_text(
            "❌ Неверный формат года. Пожалуйста, введите корректный год выпуска (например: 2020):",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_YEAR
    
    user_data[user_id]['vehicle_year'] = year
    
    await update.message.reply_text(
        "Введите мощность транспортного средства в л.с.:",
        reply_markup=get_navigation_keyboard()
    )
    return VEHICLE_POWER

async def vehicle_power(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод мощности ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите год выпуска транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_YEAR
    
    user_id = update.message.from_user.id
    power = update.message.text
    
    if not power.isdigit() or int(power) <= 0:
        await update.message.reply_text(
            "❌ Неверный формат мощности. Пожалуйста, введите корректную мощность в л.с. (только цифры):",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_POWER
    
    user_data[user_id]['vehicle_power'] = power
    
    await update.message.reply_text(
        "Введите государственный регистрационный номер транспортного средства:",
        reply_markup=get_navigation_keyboard()
    )
    return VEHICLE_REG_NUMBER

async def vehicle_reg_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод госномера ТС"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите мощность транспортного средства в л.с.:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_POWER
    
    user_id = update.message.from_user.id
    user_data[user_id]['vehicle_reg_number'] = update.message.text.upper()
    
    await update.message.reply_text(
        "Выберите тип полиса по водителям:",
        reply_markup=ReplyKeyboardMarkup([
            ["👤 Без ограничений", "👥 С ограниченным списком"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return DRIVERS_CHOICE

async def drivers_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор типа полиса по водителям"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите государственный регистрационный номер транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_REG_NUMBER
    
    user_id = update.message.from_user.id
    choice = update.message.text
    
    if choice == "👤 Без ограничений":
        user_data[user_id]['unlimited_drivers'] = True
        await update.message.reply_text(
            "Введите телефон для связи:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PHONE
    else:
        user_data[user_id]['unlimited_drivers'] = False
        await update.message.reply_text(
            "Сделайте фото лицевой стороны водительского удостоверения первого водителя:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO

async def driver_license_front_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото лицевой стороны водительского удостоверения"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Выберите тип полиса по водителям:",
            reply_markup=ReplyKeyboardMarkup([
                ["👤 Без ограничений", "👥 С ограниченным списком"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return DRIVERS_CHOICE
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите ФИО водителя полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'driver_license_front')
        if success:
            await update.message.reply_text(
                "✅ Фото лицевой стороны получено. Теперь сделайте фото обратной стороны водительского удостоверения:",
                reply_markup=get_manual_input_keyboard()
            )
            return DRIVER_LICENSE_BACK_PHOTO
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return DRIVER_LICENSE_FRONT_PHOTO
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
            "Сделайте фото лицевой стороны водительского удостоверения первого водителя:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO
    elif update.message.text == "⌨️ Ввести вручную":
        await update.message.reply_text(
            "Введите ФИО водителя полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        success = await DocumentProcessor.process_photo(update, context, 'driver_license_back')
        if success:
            await update.message.reply_text(
                "✅ Фото получено. Теперь введите ФИО водителя полностью:",
                reply_markup=get_navigation_keyboard()
            )
            return DRIVER_FIO
        else:
            await update.message.reply_text(
                "❌ Ошибка обработки фото. Попробуйте еще раз:",
                reply_markup=get_manual_input_keyboard()
            )
            return DRIVER_LICENSE_BACK_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото обратной стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_BACK_PHOTO

async def driver_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод ФИО водителя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Сделайте фото обратной стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_BACK_PHOTO
    
    user_id = update.message.from_user.id
    
    # Создаем список водителей если его нет
    if 'drivers' not in user_data[user_id]:
        user_data[user_id]['drivers'] = []
    
    # Добавляем нового водителя
    user_data[user_id]['drivers'].append({
        'fio': update.message.text
    })
    
    await update.message.reply_text(
        "Введите дату рождения водителя (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_navigation_keyboard()
    )
    return DRIVER_BIRTHDATE

async def driver_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод даты рождения водителя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите ФИО водителя полностью:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_FIO
    
    user_id = update.message.from_user.id
    birthdate = update.message.text
    
    if not validate_date(birthdate):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_BIRTHDATE
    
    # Обновляем последнего водителя в списке
    user_data[user_id]['drivers'][-1]['birthdate'] = birthdate
    
    await update.message.reply_text(
        "Введите дату выдачи водительского удостоверения (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_navigation_keyboard()
    )
    return DRIVER_LICENSE_ISSUE_DATE

async def driver_license_issue_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод даты выдачи водительского удостоверения"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату рождения водителя (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_BIRTHDATE
    
    user_id = update.message.from_user.id
    issue_date = update.message.text
    
    if not validate_date(issue_date):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_ISSUE_DATE
    
    user_data[user_id]['drivers'][-1]['license_issue_date'] = issue_date
    
    await update.message.reply_text(
        "Введите срок действия водительского удостоверения (в формате ДД.ММ.ГГГГ):",
        reply_markup=get_navigation_keyboard()
    )
    return DRIVER_LICENSE_EXPIRY

async def driver_license_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод срока действия водительского удостоверения"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите дату выдачи водительского удостоверения (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_ISSUE_DATE
    
    user_id = update.message.from_user.id
    expiry_date = update.message.text
    
    if not validate_date(expiry_date):
        await update.message.reply_text(
            "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_EXPIRY
    
    user_data[user_id]['drivers'][-1]['license_expiry'] = expiry_date
    
    await update.message.reply_text(
        "Введите номер водительского удостоверения (в формате 12 3456789):",
        reply_markup=get_navigation_keyboard()
    )
    return DRIVER_LICENSE_NUMBER

async def driver_license_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ввод номера водительского удостоверения"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите срок действия водительского удостоверения (в формате ДД.ММ.ГГГГ):",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_EXPIRY
    
    user_id = update.message.from_user.id
    license_number = update.message.text
    
    if not validate_license_number(license_number):
        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите номер водительского удостоверения в формате 12 3456789:",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_NUMBER
    
    user_data[user_id]['drivers'][-1]['license_number'] = license_number
    
    await update.message.reply_text(
        "Хотите добавить еще одного водителя?",
        reply_markup=ReplyKeyboardMarkup([
            ["✅ Завершить добавление"],
            ["👤 Добавить еще водителя"],
            ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
        ], resize_keyboard=True)
    )
    return ADD_DRIVER

async def add_driver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление еще одного водителя"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите номер водительского удостоверения (в формате 12 3456789):",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_LICENSE_NUMBER
    
    user_id = update.message.from_user.id
    
    if update.message.text == "👤 Добавить еще водителя":
        await update.message.reply_text(
            "Сделайте фото лицевой стороны водительского удостоверения следующего водителя:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO
    else:
        await update.message.reply_text(
            "Введите телефон для связи:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PHONE

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
    
    try:
        # Генерируем образец полиса
        user_data[user_id]['policy_number'] = "8989"
        user_data[user_id]['policy_copecks'] = "87"
        user_data[user_id]['policy_price'] = "8989.87"
        user_data[user_id]['policy_price_words'] = "Восемь тысяч девятьсот восемьдесят девять рублей 87 копеек"
        
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

async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение перед отправкой"""
    if update.message.text == "🆘 Помощь":
        return await help_request(update, context)
    elif update.message.text in ["⬅️ Назад", "🏠 В начало"]:
        await update.message.reply_text(
            "Введите телефон для связи:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_PHONE
    
    user_id = update.message.from_user.id
    
    if update.message.text == "✅ Подтвердить и отправить":
        return await send_confirmation(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, подтвердите отправку данных:",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Подтвердить и отправить"],
                ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
            ], resize_keyboard=True)
        )
        return CONFIRMATION

async def final_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финальное подтверждение"""
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
                
                # Отправляем фото документов менеджеру
                if data.get('has_photos'):
                    photo_types = [
                        'insurer_passport_main', 'insurer_passport_registration',
                        'owner_passport_main', 'owner_passport_registration',
                        'vehicle_doc_front', 'vehicle_doc_back',
                        'driver_license_front', 'driver_license_back'
                    ]
                    
                    for photo_type in photo_types:
                        if data.get(f'{photo_type}_photo'):
                            captions = {
                                'insurer_passport_main': "📷 Главная страница паспорта страхователя",
                                'insurer_passport_registration': "📷 Прописка страхователя",
                                'vehicle_doc_front': f"📷 Лицевая сторона {data.get('vehicle_doc_type')}",
                                'driver_license_front': "📷 Лицевая сторона водительского удостоверения"
                            }
                            
                            await context.bot.send_photo(
                                chat_id=int(MANAGER_CHAT_ID),
                                photo=data[f'{photo_type}_photo'],
                                caption=captions.get(photo_type, "📷 Фото документа")
                            )
                    
                    print("✅ Фото документов отправлены менеджеру")
                        
            except Exception as e:
                print(f"❌ Ошибка отправки документов менеджеру: {e}")
        
        # Отправляем подтверждение клиенту
        await update.message.reply_text(
            "✅ Заявка успешно отправлена!\n\n"
            "В течении 1 часа с Вами свяжется менеджер, для возможного уточнения деталей и дальнейшего оформления!\n\n"
            "С Уважением, АО 'Альфастрахование'",
            reply_markup=ReplyKeyboardRemove()
        )
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        await update.message.reply_text(
            "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    # Очищаем данные пользователя
    if user_id in user_data:
        del user_data[user_id]
    
    return ConversationHandler.END

async def help_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка запроса помощи"""
    await update.message.reply_text(
        "Опишите вашу проблему или вопрос. Вы можете отправить текст или фото:",
        reply_markup=ReplyKeyboardMarkup([
            ["⬅️ Назад к форме", "🏠 В начало"]
        ], resize_keyboard=True)
    )
    
    return HELP_REQUEST

async def process_help_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка сообщения помощи"""
    if update.message.text == "⬅️ Назад к форме":
        return await start(update, context)
    elif update.message.text == "🏠 В начало":
        return await start(update, context)
    
    # Отправляем сообщение менеджеру
    MANAGER_CHAT_ID = os.getenv('MANAGER_CHAT_ID')
    if MANAGER_CHAT_ID:
        help_text = f"🆘 ПОМОЩЬ от пользователя {update.message.from_user.first_name}:\n\n"
        
        if update.message.text:
            help_text += update.message.text
        
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
                CURRENT_POLICY_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, current_policy_data)],
                CURRENT_POLICY_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, current_policy_photo)],
                INSURANCE_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurance_start_date)],
                INSURANCE_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurance_period)],
                CHOOSE_OWNER_INSURER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_owner_insurer)],
                INSURER_PASSPORT_MAIN_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, insurer_passport_main_photo)],
                INSURER_PASSPORT_REGISTRATION_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, insurer_passport_registration_photo)],
                INSURER_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_fio)],
                INSURER_PASSPORT_SERIES_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_series_number)],
                INSURER_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_birthdate)],
                INSURER_PASSPORT_ISSUED_BY: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_issued_by)],
                INSURER_PASSPORT_ISSUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_issue_date)],
                INSURER_PASSPORT_DEPARTMENT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_department_code)],
                OWNER_PASSPORT_MAIN_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, owner_passport_main_photo)],
                OWNER_PASSPORT_REGISTRATION_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, owner_passport_registration_photo)],
                OWNER_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_fio)],
                OWNER_PASSPORT_SERIES_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_series_number)],
                OWNER_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_birthdate)],
                OWNER_PASSPORT_ISSUED_BY: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_issued_by)],
                OWNER_PASSPORT_ISSUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_issue_date)],
                OWNER_PASSPORT_DEPARTMENT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_passport_department_code)],
                VEHICLE_DOC_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_doc_type)],
                VEHICLE_DOC_FRONT_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, vehicle_doc_front_photo)],
                VEHICLE_DOC_BACK_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, vehicle_doc_back_photo)],
                VEHICLE_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_vin)],
                VEHICLE_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_brand)],
                VEHICLE_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_model)],
                VEHICLE_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_year)],
                VEHICLE_POWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_power)],
                VEHICLE_REG_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_reg_number)],
                DRIVERS_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, drivers_choice)],
                DRIVER_LICENSE_FRONT_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, driver_license_front_photo)],
                DRIVER_LICENSE_BACK_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, driver_license_back_photo)],
                DRIVER_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, driver_fio)],
                DRIVER_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, driver_birthdate)],
                DRIVER_LICENSE_ISSUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, driver_license_issue_date)],
                DRIVER_LICENSE_EXPIRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, driver_license_expiry)],
                DRIVER_LICENSE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, driver_license_number)],
                ADD_DRIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_driver)],
                INSURER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_phone)],
                CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmation)],
                FINAL_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_confirmation)],
                HELP_REQUEST: [MessageHandler(filters.TEXT | filters.PHOTO, process_help_message)],
            },
            fallbacks=[
                CommandHandler('start', start),
                CommandHandler('cancel', cancel),
                CommandHandler('help', help_request),
            ]
        )
        
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler('help', help_request))
        
        logging.info("🤖 Бот запускается...")
        print("=== БОТ ЗАПУЩЕН ===")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {e}")
        print("Бот остановлен из-за ошибки:", e)
        traceback.print_exc()
        time.sleep(10)

if __name__ == '__main__':
    main()
