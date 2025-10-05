import os
import logging
import io
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches
from docx.oxml.ns import qn
from dotenv import load_dotenv
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import time
import random

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
) = range(28)

user_data = {}

class WordGenerator:
    @staticmethod
    def generate_application_docx(data):
        """Генерация Word документа с заявкой для менеджера"""
        doc = Document()
        
        # Заголовок
        title = doc.add_heading('ЗАЯВКА НА ОСАГО', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Информация о типе полиса
        policy_info = doc.add_paragraph()
        policy_info.add_run("ИНФОРМАЦИЯ О ЗАЯВКЕ\n").bold = True
        policy_info.add_run(f"Тип заявки: {data.get('policy_type', 'Не указано')}\n")
        
        if data.get('current_policy_data'):
            policy_info.add_run(f"Данные текущего полиса: {data.get('current_policy_data', 'Не указано')}\n")
        
        # Дата
        date_info = doc.add_paragraph()
        date_info.add_run(f"Дата формирования заявки: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n").bold = True
        
        doc.add_paragraph()
        
        # Срок страхования
        insurance_info = doc.add_paragraph()
        insurance_info.add_run("СРОК СТРАХОВАНИЯ:\n").bold = True
        insurance_info.add_run(f"Начало: {data.get('insurance_start_date', 'Не указано')}\n")
        insurance_info.add_run(f"Период: {data.get('insurance_period', 'Не указано')} месяцев\n")
        
        # Расчет даты окончания
        if data.get('insurance_start_date') and data.get('insurance_period'):
            try:
                start_date = datetime.strptime(data['insurance_start_date'], '%d.%m.%Y')
                end_date = start_date + timedelta(days=30 * int(data['insurance_period']))
                insurance_info.add_run(f"Окончание: {end_date.strftime('%d.%m.%Y')}\n")
            except:
                pass
        
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
            f"Адрес регистрации: {data.get('insurer_registration', 'Не указано')}",
            f"Телефон: {data.get('insurer_phone', 'Не указан')}"
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
        
        # Информация о фото документах
        doc.add_heading('ПРИЛОЖЕННЫЕ ФОТОГРАФИИ', level=1)
        photo_info = []
        
        if data.get('insurer_passport_main_photo'):
            photo_info.append("✅ Фото главной страницы паспорта страхователя")
        if data.get('insurer_passport_registration_photo'):
            photo_info.append("✅ Фото страницы с пропиской страхователя")
        if data.get('owner_passport_main_photo'):
            photo_info.append("✅ Фото главной страницы паспорта собственника")
        if data.get('owner_passport_registration_photo'):
            photo_info.append("✅ Фото страницы с пропиской собственника")
        if data.get('vehicle_doc_front_photo'):
            photo_info.append("✅ Фото лицевой стороны СТС/ПТС")
        if data.get('vehicle_doc_back_photo'):
            photo_info.append("✅ Фото обратной стороны СТС/ПТС")
        if data.get('driver_license_front_photo'):
            photo_info.append("✅ Фото лицевой стороны водительского удостоверения")
        if data.get('driver_license_back_photo'):
            photo_info.append("✅ Фото обратной стороны водительского удостоверения")
        
        for info in photo_info:
            doc.add_paragraph(info)
        
        # Подпись
        doc.add_paragraph()
        doc.add_paragraph("Заявка успешно оформлена!").bold = True
        doc.add_paragraph("Требуется проверка менеджером и оформление полиса")
        doc.add_paragraph("С Уважением, Бот ОСАГО АО 'Альфастрахование'").bold = True
        
        return doc

    @staticmethod
    def generate_sample_policy(data):
        """Генерация образца полиса ОСАГО в фирменном стиле"""
        doc = Document()
        
        # Настройка полей документа
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.5)
            section.bottom_margin = Inches(0.5)
            section.left_margin = Inches(0.5)
            section.right_margin = Inches(0.5)
        
        # Заголовок - фирменный стиль АльфаСтрахование
        title = doc.add_paragraph()
        title_run = title.add_run("АО «АльфаСтрахование»\n")
        title_run.font.size = Pt(14)
        title_run.bold = True
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Название документа
        doc_title = doc.add_paragraph()
        doc_title_run = doc_title.add_run("ПОЛИС ОСАГО\n")
        doc_title_run.font.size = Pt(16)
        doc_title_run.bold = True
        doc_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Номер полиса (генерируем случайный)
        policy_number = f"АОС {random.randint(100000, 999999)}"
        policy_num_para = doc.add_paragraph()
        policy_num_run = policy_num_para.add_run(f"№ {policy_number}\n")
        policy_num_run.font.size = Pt(12)
        policy_num_run.bold = True
        policy_num_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph()
        
        # Таблица с основной информацией
        table = doc.add_table(rows=8, cols=2)
        table.style = 'Table Grid'
        
        # Заполняем таблицу
        cells = table.rows[0].cells
        cells[0].text = "Страхователь"
        cells[1].text = data.get('insurer_fio', 'Не указано')
        
        cells = table.rows[1].cells
        cells[0].text = "Документ"
        cells[1].text = f"Паспорт: {data.get('insurer_passport_series_number', 'Не указано')}"
        
        cells = table.rows[2].cells
        cells[0].text = "Адрес"
        cells[1].text = data.get('insurer_registration', 'Не указано')
        
        cells = table.rows[3].cells
        cells[0].text = "Транспортное средство"
        cells[1].text = f"{data.get('vehicle_brand', 'Не указано')} {data.get('vehicle_model', 'Не указано')}"
        
        cells = table.rows[4].cells
        cells[0].text = "VIN"
        cells[1].text = data.get('vehicle_vin', 'Не указано')
        
        cells = table.rows[5].cells
        cells[0].text = "Госномер"
        cells[1].text = data.get('vehicle_reg_number', 'Не указано')
        
        # Расчет дат
        start_date = data.get('insurance_start_date', 'Не указано')
        period = data.get('insurance_period', '12')
        
        if start_date != 'Не указано':
            try:
                start_dt = datetime.strptime(start_date, '%d.%m.%Y')
                end_dt = start_dt + timedelta(days=30 * int(period))
                end_date = end_dt.strftime('%d.%m.%Y')
            except:
                end_date = 'Не указано'
        else:
            end_date = 'Не указано'
        
        cells = table.rows[6].cells
        cells[0].text = "Период действия"
        cells[1].text = f"с {start_date} по {end_date}"
        
        cells = table.rows[7].cells
        cells[0].text = "Страховая премия"
        cells[1].text = "РАСЧЕТНАЯ"
        
        doc.add_paragraph()
        
        # Водители
        drivers_para = doc.add_paragraph()
        drivers_para.add_run("Допущенные к управлению водители:\n").bold = True
        
        drivers = data.get('drivers', [])
        if drivers:
            for i, driver in enumerate(drivers, 1):
                doc.add_paragraph(f"{i}. {driver.get('fio', 'Не указано')} - {driver.get('license', 'Не указано')}")
        else:
            doc.add_paragraph("Без ограничений")
        
        doc.add_paragraph()
        
        # Особые отметки
        notes_para = doc.add_paragraph()
        notes_para.add_run("Особые отметки:\n").bold = True
        doc.add_paragraph("• Полис оформлен через Telegram-бота")
        doc.add_paragraph("• Требуется подтверждение менеджера")
        
        doc.add_paragraph()
        
        # Водяной знак "ОБРАЗЕЦ" по диагонали
        # Добавляем несколько крупных текстовых элементов под углом
        for i in range(3):
            sample_para = doc.add_paragraph()
            sample_run = sample_para.add_run("О Б Р А З Е Ц")
            sample_run.font.size = Pt(48)
            sample_run.font.color.rgb = RGBColor(200, 200, 200)
            sample_run.bold = True
            sample_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Информация о том, что это образец
        info_para = doc.add_paragraph()
        info_para.add_run("\nДанный документ является образцом полиса.\n").bold = True
        info_para.add_run("Для получения оригинального полиса обратитесь к менеджеру.")
        info_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        return doc

# Остальной код остается без изменений (функции навигации, обработчики состояний и т.д.)
# Для краткости не повторяю весь код, только измененные части

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

# ... остальные функции обработки состояний остаются без изменений ...

async def send_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение и отправка данных"""
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("Пожалуйста, начните с команды /start")
        return ConversationHandler.END
        
    data = user_data[user_id]
    
    try:
        # Создаем Word документ с заявкой для менеджера
        doc = WordGenerator.generate_application_docx(data)
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        file_stream.name = f"Заявка_ОСАГО_{data.get('insurer_fio', 'Клиент')}_{datetime.now().strftime('%d%m%Y_%H%M')}.docx"
        
        # Отправляем Word документ менеджеру
        MANAGER_CHAT_ID = os.getenv('MANAGER_CHAT_ID')
        if MANAGER_CHAT_ID:
            try:
                await context.bot.send_document(
                    chat_id=int(MANAGER_CHAT_ID),
                    document=file_stream,
                    caption=f"📄 Новая заявка ОСАГО от {data.get('insurer_fio', 'Клиент')}\n"
                           f"Телефон: {data.get('insurer_phone', 'Не указан')}"
                )
                print(f"✅ Заявка отправлена менеджеру {MANAGER_CHAT_ID}")
                
                # Также отправляем все фото документов менеджеру
                photo_fields = [
                    ('insurer_passport_main_photo', '📷 Фото главной страницы паспорта страхователя'),
                    ('insurer_passport_registration_photo', '📷 Фото прописки страхователя'),
                    ('owner_passport_main_photo', '📷 Фото главной страницы паспорта собственника'),
                    ('owner_passport_registration_photo', '📷 Фото прописки собственника'),
                    ('vehicle_doc_front_photo', '📷 Фото лицевой стороны СТС/ПТС'),
                    ('vehicle_doc_back_photo', '📷 Фото обратной стороны СТС/ПТС'),
                    ('driver_license_front_photo', '📷 Фото лицевой стороны в/у'),
                    ('driver_license_back_photo', '📷 Фото обратной стороны в/у')
                ]
                
                for field, caption in photo_fields:
                    if data.get(field):
                        try:
                            await context.bot.send_photo(
                                chat_id=int(MANAGER_CHAT_ID),
                                photo=data[field],
                                caption=caption
                            )
                        except Exception as e:
                            print(f"❌ Ошибка отправки фото {field}: {e}")
                
            except Exception as e:
                print(f"❌ Ошибка отправки менеджеру: {e}")
        
        # Генерируем и отправляем образец полиса пользователю
        sample_doc = WordGenerator.generate_sample_policy(data)
        sample_stream = io.BytesIO()
        sample_doc.save(sample_stream)
        sample_stream.seek(0)
        sample_stream.name = f"Образец_полиса_ОСАГО_{datetime.now().strftime('%d%m%Y_%H%M')}.docx"
        
        # Отправляем подтверждение клиенту
        await update.message.reply_text(
            "✅ Заявка успешно отправлена!\n\n"
            "В течении 1 часа с Вами свяжется менеджер для подтверждения деталей "
            "и оформления оригинального полиса.\n\n"
            "С Уважением, АО 'Альфастрахование'",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Отправляем образец полиса клиенту
        await update.message.reply_document(
            document=sample_stream,
            caption="📄 Образец вашего полиса ОСАГО\n"
                   "Это предварительный вариант. Оригинальный полис будет оформлен после подтверждения менеджером."
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

# ... остальной код без изменений ...

def main():
    """Запуск бота"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logging.error("❌ Ошибка: не задан TELEGRAM_BOT_TOKEN")
        return
    
    try:
        application = Application.builder().token(TOKEN).build()
        
        # Основной ConversationHandler (код без изменений)
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                # ... все состояния без изменений ...
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
        application.add_handler(CommandHandler('help', help_request))
        
        logging.info("🤖 Бот запускается...")
        print("=== БОТ ОСАГО ЗАПУЩЕН ===")
        
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
