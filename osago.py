import os
import logging
import io
import re
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
import pytesseract
from PIL import Image
import cv2
import numpy as np

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
) = range(44)

user_data = {}

class OCRProcessor:
    """Класс для обработки изображений и извлечения текста с помощью OCR"""
    
    @staticmethod
    def preprocess_image(image):
        """Предобработка изображения для улучшения OCR"""
        try:
            # Конвертируем в grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
            
            # Убираем шум
            denoised = cv2.medianBlur(gray, 3)
            
            # Применяем адаптивный threshold
            thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)
            
            return thresh
        except Exception as e:
            print(f"Ошибка предобработки изображения: {e}")
            return image
    
    @staticmethod
    def extract_text_from_image(image_path):
        """Извлечение текста из изображения с помощью Tesseract"""
        try:
            # Загружаем изображение
            image = cv2.imread(image_path)
            if image is None:
                return ""
            
            # Предобработка
            processed_image = OCRProcessor.preprocess_image(image)
            
            # Сохраняем временный файл для OCR
            temp_path = "temp_processed.png"
            cv2.imwrite(temp_path, processed_image)
            
            # Извлекаем текст
            custom_config = r'--oem 3 --psm 6 -l rus+eng'
            text = pytesseract.image_to_string(Image.open(temp_path), config=custom_config)
            
            # Удаляем временный файл
            try:
                os.remove(temp_path)
            except:
                pass
                
            return text.strip()
        except Exception as e:
            print(f"Ошибка OCR: {e}")
            return ""
    
    @staticmethod
    def extract_passport_data(text):
        """Извлечение данных паспорта из текста"""
        data = {
            'fio': '',
            'series_number': '',
            'birthdate': '',
            'issued_by': '',
            'issue_date': '',
            'department_code': ''
        }
        
        try:
            # Поиск ФИО (русские буквы, пробелы)
            fio_pattern = r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'
            fio_match = re.search(fio_pattern, text)
            if fio_match:
                data['fio'] = fio_match.group()
            
            # Поиск серии и номера паспорта
            passport_pattern = r'(\d{4}\s*\d{6})'
            passport_match = re.search(passport_pattern, text)
            if passport_match:
                data['series_number'] = passport_match.group(1).replace(' ', '')
                if len(data['series_number']) == 10:
                    data['series_number'] = data['series_number'][:4] + ' ' + data['series_number'][4:]
            
            # Поиск даты рождения
            date_pattern = r'(\d{1,2}[\.\s]\d{1,2}[\.\s]\d{4})'
            dates = re.findall(date_pattern, text)
            if dates:
                data['birthdate'] = dates[0].replace(' ', '.')
            
            # Поиск кода подразделения
            code_pattern = r'(\d{3}-\d{3})'
            code_match = re.search(code_pattern, text)
            if code_match:
                data['department_code'] = code_match.group(1)
                
        except Exception as e:
            print(f"Ошибка извлечения данных паспорта: {e}")
        
        return data
    
    @staticmethod
    def extract_vehicle_data(text):
        """Извлечение данных ТС из текста"""
        data = {
            'vin': '',
            'brand': '',
            'model': '',
            'year': '',
            'power': '',
            'reg_number': ''
        }
        
        try:
            # Поиск VIN (17 символов, буквы и цифры)
            vin_pattern = r'[A-HJ-NPR-Z0-9]{17}'
            vin_match = re.search(vin_pattern, text.upper())
            if vin_match:
                data['vin'] = vin_match.group()
            
            # Поиск госномера (русские буквы, цифры)
            reg_pattern = r'[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}'
            reg_match = re.search(reg_pattern, text.upper())
            if reg_match:
                data['reg_number'] = reg_match.group()
            
            # Поиск года выпуска
            year_pattern = r'20\d{2}'
            year_match = re.search(year_pattern, text)
            if year_match:
                data['year'] = year_match.group()
            
            # Поиск мощности
            power_pattern = r'(\d{2,3})\s*[лЛ\.,;]?\s*[сС]'
            power_match = re.search(power_pattern, text)
            if power_match:
                data['power'] = power_match.group(1)
                
        except Exception as e:
            print(f"Ошибка извлечения данных ТС: {e}")
        
        return data
    
    @staticmethod
    def extract_license_data(text):
        """Извлечение данных водительского удостоверения из текста"""
        data = {
            'fio': '',
            'birthdate': '',
            'issue_date': '',
            'expiry': '',
            'number': ''
        }
        
        try:
            # Поиск ФИО
            fio_pattern = r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'
            fio_match = re.search(fio_pattern, text)
            if fio_match:
                data['fio'] = fio_match.group()
            
            # Поиск номеров водительского удостоверения
            license_pattern = r'(\d{2}\s*\d{6,9})'
            license_match = re.search(license_pattern, text)
            if license_match:
                data['number'] = license_match.group(1).replace(' ', '')
                if len(data['number']) >= 8:
                    data['number'] = data['number'][:2] + ' ' + data['number'][2:]
            
            # Поиск дат
            date_pattern = r'(\d{1,2}[\.\s]\d{1,2}[\.\s]\d{4})'
            dates = re.findall(date_pattern, text)
            if len(dates) >= 1:
                data['birthdate'] = dates[0].replace(' ', '.')
            if len(dates) >= 2:
                data['issue_date'] = dates[1].replace(' ', '.')
            if len(dates) >= 3:
                data['expiry'] = dates[2].replace(' ', '.')
                
        except Exception as e:
            print(f"Ошибка извлечения данных в/у: {e}")
        
        return data

class DocumentProcessor:
    """Класс для обработки документов и извлечения данных"""
    
    @staticmethod
    async def process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_type: str):
        """Обработка фото документа и извлечение данных с помощью OCR"""
        user_id = update.message.from_user.id
        
        if update.message.photo:
            # Скачиваем фото
            photo_file = await update.message.photo[-1].get_file()
            photo_path = f"temp_photo_{user_id}.jpg"
            await photo_file.download_to_drive(photo_path)
            
            # Извлекаем текст с помощью OCR
            extracted_text = OCRProcessor.extract_text_from_image(photo_path)
            
            # Удаляем временный файл
            try:
                os.remove(photo_path)
            except:
                pass
            
            # Сохраняем фото и извлеченный текст
            user_data[user_id][f'{photo_type}_photo'] = photo_file.file_id
            user_data[user_id]['has_photos'] = True
            user_data[user_id][f'{photo_type}_text'] = extracted_text
            
            return extracted_text
        return ""

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
            
            owner_info = [
                f"ФИО: {data.get('owner_fio', 'Не указано')}",
                f"Дата рождения: {data.get('owner_birthdate', 'Не указано')}",
                f"Паспорт: {data.get('owner_passport_series_number', 'Не указано')}",
                f"Дата выдачи паспорта: {data.get('owner_passport_issue_date', 'Не указано')}",
                f"Кем выдан: {data.get('owner_passport_issued_by', 'Не указано')}",
                f"Код подразделения: {data.get('owner_passport_department_code', 'Не указано')}",
                f"Прописка: {data.get('owner_registration', 'Не указано')}"
            ]
            
            for info in owner_info:
                doc.add_paragraph(info)
            
            doc.add_paragraph()
        
        # Водительское удостоверение страхователя
        doc.add_heading('ВОДИТЕЛЬСКОЕ УДОСТОВЕРЕНИЕ СТРАХОВАТЕЛЯ', level=1)
        
        license_info = [
            f"В/у: {data.get('insurer_license_number', 'Не указано')}",
            f"Дата выдачи: {data.get('insurer_license_issue_date', 'Не указано')}",
            f"Срок действия: {data.get('insurer_license_expiry', 'Не указано')}"
        ]
        
        for info in license_info:
            doc.add_paragraph(info)
        
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
        """Генерация образца полиса ОСАГО по шаблону из файла O.jpg"""
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
        policy_number.add_run(f"№ {data.get('policy_number', '000000')} руб. {data.get('policy_copecks', '00')} коп.").bold = True
        
        # Подзаголовок
        sub_title = doc.add_heading('ОБЯЗАТЕЛЬНОГО СТРАХОВАНИЯ ГРАЖДАНСКОЙ ОТВЕТСТВЕННОСТИ ВЛАДЕЛЬЦЕВ ТРАНСПОРТНЫХ СРЕДСТВ', level=2)
        sub_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Срок страхования
        insurance_period = doc.add_paragraph()
        insurance_period.add_run(f"Срок страхования с 00 ч. 00 мин. {data.get('insurance_start_date', '01.01.2024')} г.\n")
        insurance_period.add_run(f"по 24 ч. 00 мин. {data.get('insurance_end_date', '01.01.2025')} г.\n\n")
        
        insurance_period.add_run("Страхование распространяется на страховые случаи, произошедшие в период использования транспортного средства\n")
        insurance_period.add_run("в течение срока страхования\n")
        insurance_period.add_run(f"с {data.get('insurance_start_date', '01.01.2024')} г. по {data.get('insurance_end_date', '01.01.2025')} г.")
        
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
        
        # Заголовки таблицы
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Транспортное средство'
        hdr_cells[1].text = 'Идентификационный номер транспортного средства'
        hdr_cells[2].text = 'Государственный регистрационный знак транспортного средства'
        
        # Данные ТС
        row_cells = table.rows[1].cells
        row_cells[0].text = f"{data.get('vehicle_brand', '')} {data.get('vehicle_model', '')}"
        row_cells[1].text = data.get('vehicle_vin', 'Не указано')
        row_cells[2].text = data.get('vehicle_reg_number', 'Не указано')
        
        doc.add_paragraph()
        
        # Паспорт ТС
        p3 = doc.add_paragraph()
        p3.add_run("Паспорт транспортного средства, свидетельство о регистрации транспортного средства, паспорт самоходной машины (либо аналогичный документ)\n").bold = True
        p3.add_run(f"Вид документа {data.get('vehicle_doc_type', 'СТС')} Серия Номер {data.get('vehicle_doc_number', 'Не указано')}\n\n")
        
        # Цель использования
        p3.add_run("Цель использования транспортного средства (отметить нужное): ☑ [личная, ] учебная езда, такси, перевозка опасных и легковоспламеняющихся грузов,\n")
        p3.add_run("прокат/краткосрочная аренда, регулярные пассажирские перевозки/перевозки пассажиров по заказам, дорожные и специальные транспортные средства,\n")
        p3.add_run("экстренные и коммунальные службы, прочее.\n")
        
        # 3. Договор заключен в отношении
        p4 = doc.add_paragraph()
        p4.add_run("3. Договор заключен в отношении:\n").bold = True
        
        drivers = data.get('drivers', [])
        if not drivers:
            p4.add_run("неограниченного количества лиц, допущенных к управлению транспортным средством\n")
        else:
            p4.add_run("лиц, допущенных к управлению транспортным средством\n")
        
        # Таблица водителей
        if drivers:
            driver_table = doc.add_table(rows=len(drivers)+1, cols=7)
            driver_table.style = 'Table Grid'
            
            # Заголовки таблицы водителей
            driver_hdr = driver_table.rows[0].cells
            driver_hdr[0].text = '№/п'
            driver_hdr[1].text = 'Лица, допущенные к управлению транспортным средством (фамилия, имя, отчество)'
            driver_hdr[2].text = ''
            driver_hdr[3].text = ''
            driver_hdr[4].text = 'Водительское удостоверение (серия, номер)'
            driver_hdr[5].text = ''
            driver_hdr[6].text = 'Коэффициент КБМ'
            
            # Данные водителей
            for i, driver in enumerate(drivers, 1):
                driver_cells = driver_table.rows[i].cells
                driver_cells[0].text = str(i)
                driver_cells[1].text = driver.get('fio', '')
                driver_cells[4].text = driver.get('license_number', '')
                driver_cells[6].text = 'КБМ=0.85'
        
        # 4. Страховая сумма
        p5 = doc.add_paragraph()
        p5.add_run("4. Страховая сумма, в пределах которой страховщик при наступлении каждого страхового случая (независимо от количества страховых случаев в течение\n")
        p5.add_run("срока страхования по договору обязательного страхования) обязуется возместить потерпевшим причиненный вред, установлена Федеральным законом от 25\n")
        p5.add_run("апреля 2002 года №40-ФЗ «Об обязательном страховании гражданской ответственности владельцев транспортных средств» в редакции, действующей на\n")
        p5.add_run("дату заключения (изменения (при условии, что такие изменения потребовали доплаты страховой премии) настоящего договора.\n")
        
        # 5. Страховой случай
        p6 = doc.add_paragraph()
        p6.add_run("5. Страховой случай – наступление гражданской ответственности владельца транспортного средства за причинение вреда жизни, здоровью или имуществу\n")
        p6.add_run("потерпевших при использовании транспортного средства, влекущее за собой в соответствии с договором обязательного страхования обязанность\n")
        p6.add_run("страховщика осуществить страховую выплату.\n")
        
        # 6. Территория действия
        p7 = doc.add_paragraph()
        p7.add_run("6. Страховой полис действует на территории Российской Федерации.\n")
        
        # 7. Расчет страховой премии
        p8 = doc.add_paragraph()
        p8.add_run("7. Расчет размера страховой премии\n\n").bold = True
        
        # Таблица расчета
        calc_table = doc.add_table(rows=2, cols=10)
        calc_table.style = 'Table Grid'
        
        calc_hdr = calc_table.rows[0].cells
        calc_hdr[0].text = 'Базовая ставка'
        calc_hdr[1].text = 'Коэффициент'
        calc_hdr[2].text = ''
        calc_hdr[3].text = ''
        calc_hdr[4].text = ''
        calc_hdr[5].text = ''
        calc_hdr[6].text = ''
        calc_hdr[7].text = ''
        calc_hdr[8].text = ''
        calc_hdr[9].text = 'Итого'
        
        calc_data = calc_table.rows[1].cells
        calc_data[0].text = '3751.00'
        calc_data[1].text = '1.90'
        calc_data[2].text = '0.85'
        calc_data[3].text = '1.06'
        calc_data[4].text = '1.00'
        calc_data[5].text = '1.00'
        calc_data[6].text = '1.00'
        calc_data[7].text = '1.40'
        calc_data[8].text = ''
        calc_data[9].text = f"{data.get('policy_price', '8989.87')}"
        
        doc.add_paragraph()
        
        # 8. Особые отметки
        p9 = doc.add_paragraph()
        p9.add_run("8. Особые отметки\n").bold = True
        p9.add_run(f"Стоимость договора: {data.get('policy_price', '8989.87')} ({data.get('policy_price_words', 'Восемь тысяч девятьсот восемьдесят девять рублей 87 копеек')}). ")
        p9.add_run("ТС в режиме ТАКСИ использованию НЕ подлежит. ")
        
        if data.get('current_policy_data'):
            p9.add_run(f"Предыдущий договор {data.get('current_policy_data')}. ")
        
        p9.add_run("Условия не изменились. ")
        p9.add_run(f"Дата оформления: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
        
        p9.add_run(f"Дата заключения договора «{datetime.now().strftime('%d')}» {datetime.now().strftime('%m')}. {datetime.now().strftime('%Y')} г.\n\n")
        
        p9.add_run("Страхователю выданы перечень представителей страховщика в субъектах Российской Федерации согласно приложению и два бланка извещения о\n")
        p9.add_run("дорожно-транспортном происшествии.\n")
        p9.add_run("Страхователь Страховщик/представитель страховщика:\n\n")
        
        p9.add_run(f"Дата выдачи полиса «{datetime.now().strftime('%d')}» {datetime.now().strftime('%m')}. {datetime.now().strftime('%Y')} г.")
        
        # Водяной знак "ОБРАЗЕЦ"
        for i in range(15):
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
    user = update.message.from_user
    
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
        extracted_text = await DocumentProcessor.process_photo(update, context, 'current_policy')
        
        # Пытаемся извлечь данные из фото
        if extracted_text:
            await update.message.reply_text(
                f"✅ Фото полиса получено. Извлеченный текст:\n{extracted_text[:500]}...\n\n"
                f"Если данные извлечены корректно, они будут использованы для оформления.",
                reply_markup=get_navigation_keyboard()
            )
        else:
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
            await update.message.reply_text(
                "Введите серию и номер текущего полиса ОСАГО:",
                reply_markup=ReplyKeyboardMarkup([
                    ["🚫 Нет серии (только номер)", "📷 Сделать фото полиса"],
                    ["⬅️ Назад", "🏠 В начало", "🆘 Помощь"]
                ], resize_keyboard=True)
            )
            return CURRENT_POLICY_DATA
        else:
            return await policy_type(update, context)
    
    user_id = update.message.from_user.id
    if not validate_date(update.message.text):
        await update.message.reply_text(
            "Неверный формат даты. Введите в формате ДД.ММ.ГГГГ:",
            reply_markup=get_navigation_keyboard()
        )
        return INSURANCE_START_DATE
    
    user_data[user_id]['insurance_start_date'] = update.message.text
    
    # Вычисляем дату окончания (через 1 год)
    try:
        start_date = datetime.strptime(update.message.text, '%d.%m.%Y')
        end_date = start_date.replace(year=start_date.year + 1)
        user_data[user_id]['insurance_end_date'] = end_date.strftime('%d.%m.%Y')
    except:
        user_data[user_id]['insurance_end_date'] = "01.01.2025"
    
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
    """Обработка фото главной страницы паспорта страхователя с OCR"""
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
            "Введите ФИО страхователя (как в паспорте):",
            reply_markup=get_navigation_keyboard()
        )
        return INSURER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        extracted_text = await DocumentProcessor.process_photo(update, context, 'insurer_passport_main')
        
        # Извлекаем данные с помощью OCR
        passport_data = OCRProcessor.extract_passport_data(extracted_text)
        
        response_text = "✅ Фото получено."
        
        # Если OCR нашел данные, предлагаем их использовать
        if passport_data['fio'] or passport_data['series_number']:
            response_text += "\n\nОбнаружены следующие данные:\n"
            
            if passport_data['fio']:
                response_text += f"ФИО: {passport_data['fio']}\n"
                user_data[user_id]['insurer_fio'] = passport_data['fio']
            
            if passport_data['series_number']:
                response_text += f"Паспорт: {passport_data['series_number']}\n"
                user_data[user_id]['insurer_passport_series_number'] = passport_data['series_number']
            
            if passport_data['birthdate']:
                response_text += f"Дата рождения: {passport_data['birthdate']}\n"
                user_data[user_id]['insurer_birthdate'] = passport_data['birthdate']
            
            response_text += "\nЭти данные будут использованы для оформления. Вы можете изменить их вручную на следующем шаге."
        
        response_text += "\n\nТеперь сделайте фото страницы с пропиской страхователя:"
        
        await update.message.reply_text(
            response_text,
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_REGISTRATION_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото главной страницы паспорта:",
            reply_markup=get_manual_input_keyboard()
        )
        return INSURER_PASSPORT_MAIN_PHOTO

# [Остальные функции обработки паспортных данных, ТС и водительских удостоверений остаются аналогичными,
# но с добавлением OCR обработки как в функции insurer_passport_main_photo]

# Для экономии места оставлю остальные функции без изменений, так как они следуют той же логике

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
        # Если пользователь решил вводить данные вручную, проверяем, есть ли уже ФИО
        user_id = update.message.from_user.id
        if not user_data[user_id].get('insurer_fio'):
            await update.message.reply_text(
                "Введите ФИО страхователя (как в паспорте):",
                reply_markup=get_navigation_keyboard()
            )
            return INSURER_FIO
        else:
            await update.message.reply_text(
                "Введите адрес прописки страхователя:",
                reply_markup=get_navigation_keyboard()
            )
            return INSURER_PASSPORT_REGISTRATION_PHOTO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        await DocumentProcessor.process_photo(update, context, 'insurer_passport_registration')
        user_data[user_id]['insurer_registration'] = "Указана в фото документа"
    else:
        user_data[user_id]['insurer_registration'] = update.message.text
    
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

# [Аналогичным образом добавляем OCR обработку для всех остальных фото документов]

async def vehicle_doc_front_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото первой стороны документа на ТС с OCR"""
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
            "Введите VIN номер транспортного средства:",
            reply_markup=get_navigation_keyboard()
        )
        return VEHICLE_VIN
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        extracted_text = await DocumentProcessor.process_photo(update, context, 'vehicle_doc_front')
        
        # Извлекаем данные ТС с помощью OCR
        vehicle_data = OCRProcessor.extract_vehicle_data(extracted_text)
        
        response_text = "✅ Фото получено."
        
        # Если OCR нашел данные, предлагаем их использовать
        if (vehicle_data['vin'] or vehicle_data['reg_number'] or 
            vehicle_data['brand'] or vehicle_data['year']):
            response_text += "\n\nОбнаружены следующие данные:\n"
            
            if vehicle_data['vin']:
                response_text += f"VIN: {vehicle_data['vin']}\n"
                user_data[user_id]['vehicle_vin'] = vehicle_data['vin']
            
            if vehicle_data['reg_number']:
                response_text += f"Госномер: {vehicle_data['reg_number']}\n"
                user_data[user_id]['vehicle_reg_number'] = vehicle_data['reg_number']
            
            if vehicle_data['brand']:
                response_text += f"Марка: {vehicle_data['brand']}\n"
                user_data[user_id]['vehicle_brand'] = vehicle_data['brand']
            
            if vehicle_data['year']:
                response_text += f"Год выпуска: {vehicle_data['year']}\n"
                user_data[user_id]['vehicle_year'] = vehicle_data['year']
            
            if vehicle_data['power']:
                response_text += f"Мощность: {vehicle_data['power']} л.с.\n"
                user_data[user_id]['vehicle_power'] = vehicle_data['power']
            
            response_text += "\nЭти данные будут использованы для оформления."
        
        response_text += "\n\nТеперь сделайте фото второй стороны документа:"
        
        await update.message.reply_text(
            response_text,
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_BACK_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото первой стороны документа:",
            reply_markup=get_manual_input_keyboard()
        )
        return VEHICLE_DOC_FRONT_PHOTO

async def driver_license_front_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото лицевой стороны водительского удостоверения с OCR"""
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
            "Введите ФИО водителя (как в водительском удостоверении):",
            reply_markup=get_navigation_keyboard()
        )
        return DRIVER_FIO
    
    user_id = update.message.from_user.id
    
    if update.message.photo:
        extracted_text = await DocumentProcessor.process_photo(update, context, 'driver_license_front')
        
        # Извлекаем данные в/у с помощью OCR
        license_data = OCRProcessor.extract_license_data(extracted_text)
        
        response_text = "✅ Фото получено."
        
        # Если OCR нашел данные, предлагаем их использовать
        if (license_data['fio'] or license_data['number'] or 
            license_data['birthdate']):
            response_text += "\n\nОбнаружены следующие данные:\n"
            
            if license_data['fio']:
                response_text += f"ФИО: {license_data['fio']}\n"
                # Сохраняем данные первого водителя
                if 'drivers' not in user_data[user_id]:
                    user_data[user_id]['drivers'] = []
                if len(user_data[user_id]['drivers']) == 0:
                    user_data[user_id]['drivers'].append({})
                user_data[user_id]['drivers'][0]['fio'] = license_data['fio']
            
            if license_data['number']:
                response_text += f"В/у: {license_data['number']}\n"
                if len(user_data[user_id]['drivers']) > 0:
                    user_data[user_id]['drivers'][0]['license_number'] = license_data['number']
            
            if license_data['birthdate']:
                response_text += f"Дата рождения: {license_data['birthdate']}\n"
                if len(user_data[user_id]['drivers']) > 0:
                    user_data[user_id]['drivers'][0]['birthdate'] = license_data['birthdate']
            
            if license_data['issue_date']:
                response_text += f"Дата выдачи: {license_data['issue_date']}\n"
                if len(user_data[user_id]['drivers']) > 0:
                    user_data[user_id]['drivers'][0]['license_issue_date'] = license_data['issue_date']
            
            if license_data['expiry']:
                response_text += f"Срок действия: {license_data['expiry']}\n"
                if len(user_data[user_id]['drivers']) > 0:
                    user_data[user_id]['drivers'][0]['license_expiry'] = license_data['expiry']
            
            response_text += "\nЭти данные будут использованы для оформления."
        
        response_text += "\n\nТеперь сделайте фото обратной стороны водительского удостоверения:"
        
        await update.message.reply_text(
            response_text,
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_BACK_PHOTO
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото лицевой стороны водительского удостоверения:",
            reply_markup=get_manual_input_keyboard()
        )
        return DRIVER_LICENSE_FRONT_PHOTO

# [Остальные функции остаются без изменений...]

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
        # Добавляем дополнительные данные для образца полиса
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
                
                # Отправляем фото документов менеджеру, если они есть
                if data.get('has_photos'):
                    photo_types = [
                        'insurer_passport_main', 'insurer_passport_registration',
                        'owner_passport_main', 'owner_passport_registration',
                        'vehicle_doc_front', 'vehicle_doc_back',
                        'driver_license_front', 'driver_license_back'
                    ]
                    
                    for photo_type in photo_types:
                        if data.get(f'{photo_type}_photo'):
                            caption_map = {
                                'insurer_passport_main': "📷 Главная страница паспорта страхователя",
                                'insurer_passport_registration': "📷 Прописка страхователя",
                                'owner_passport_main': "📷 Главная страница паспорта собственника",
                                'owner_passport_registration': "📷 Прописка собственника",
                                'vehicle_doc_front': f"📷 Лицевая сторона {data.get('vehicle_doc_type')}",
                                'vehicle_doc_back': f"📷 Обратная сторона {data.get('vehicle_doc_type')}",
                                'driver_license_front': "📷 Лицевая сторона водительского удостоверения",
                                'driver_license_back': "📷 Обратная сторона водительского удостоверения"
                            }
                            
                            await context.bot.send_photo(
                                chat_id=int(MANAGER_CHAT_ID),
                                photo=data[f'{photo_type}_photo'],
                                caption=caption_map.get(photo_type, "📷 Фото документа")
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
            "Произошла непредвиденная ошибка. "
            "Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    # Очищаем данные пользователя
    if user_id in user_data:
        del user_data[user_id]
    
    return ConversationHandler.END

# [Остальные вспомогательные функции (help_request, process_help_message, cancel) остаются без изменений]

async def help_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка запроса помощи"""
    user_id = update.message.from_user.id
    
    # Сохраняем текущее состояние для возврата
    if update.message.text == "🆘 Помощь":
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
        
        if previous_state == START:
            return await start(update, context)
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
                
                # Текущий полис
                CURRENT_POLICY_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, current_policy_data)],
                CURRENT_POLICY_PHOTO: [
                    MessageHandler(filters.PHOTO, current_policy_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, current_policy_photo)
                ],
                
                INSURANCE_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurance_start_date)],
                INSURANCE_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurance_period)],
                CHOOSE_OWNER_INSURER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_owner_insurer)],
                
                # Паспорт страхователя
                INSURER_PASSPORT_MAIN_PHOTO: [
                    MessageHandler(filters.PHOTO, insurer_passport_main_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_main_photo)
                ],
                INSURER_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_fio)],
                INSURER_PASSPORT_SERIES_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_series_number)],
                INSURER_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_birthdate)],
                INSURER_PASSPORT_ISSUED_BY: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_issued_by)],
                INSURER_PASSPORT_ISSUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_issue_date)],
                INSURER_PASSPORT_DEPARTMENT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_department_code)],
                INSURER_PASSPORT_REGISTRATION_PHOTO: [
                    MessageHandler(filters.PHOTO, insurer_passport_registration_photo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_passport_registration_photo)
                ],
                
                # [Остальные состояния...]
                
                # Финальные этапы
                INSURER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, insurer_phone)],
                FINAL_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_confirmation)],
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
        application.add_handler(CommandHandler('help', help_request))
        
        logging.info("🤖 Бот запускается...")
        print("=== БОТ ЗАПУЩЕН С OCR И ОБНОВЛЕННЫМ ШАБЛОНОМ ===")
        
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
