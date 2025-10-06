import os
import logging
import re
from datetime import datetime
try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    import cv2
    import numpy as np
    OCR_AVAILABLE = True
except ImportError as e:
    logging.warning(f"OCR dependencies not available: {e}")
    OCR_AVAILABLE = False

class OCRProcessor:
    """Класс для обработки изображений и извлечения текста с помощью OCR"""
    
    @staticmethod
    def is_available():
        """Проверка доступности OCR"""
        return OCR_AVAILABLE
    
    @staticmethod
    def preprocess_image(image):
        """Предобработка изображения для улучшения OCR"""
        try:
            # Конвертируем PIL Image в OpenCV format если нужно
            if isinstance(image, Image.Image):
                image = np.array(image)
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            
            # Конвертируем в grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
            
            # Убираем шум
            denoised = cv2.medianBlur(gray, 3)
            
            # Увеличиваем контраст
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            contrast_enhanced = clahe.apply(denoised)
            
            # Применяем adaptive threshold
            thresh = cv2.adaptiveThreshold(contrast_enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)
            
            # Убираем мелкий шум
            kernel = np.ones((1, 1), np.uint8)
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            
            return opening
        except Exception as e:
            logging.error(f"Ошибка предобработки изображения: {e}")
            return image
    
    @staticmethod
    def extract_text_from_image(image_path):
        """Извлечение текста из изображения с помощью Tesseract"""
        if not OCR_AVAILABLE:
            return ""
            
        try:
            # Загружаем изображение
            image = cv2.imread(image_path)
            if image is None:
                logging.error(f"Не удалось загрузить изображение: {image_path}")
                return ""
            
            # Предобработка
            processed_image = OCRProcessor.preprocess_image(image)
            
            # Настройки Tesseract для лучшего распознавания
            custom_config = r'--oem 3 --psm 6 -l rus+eng'
            
            # Извлекаем текст
            text = pytesseract.image_to_string(processed_image, config=custom_config)
            
            # Очищаем текст
            cleaned_text = OCRProcessor.clean_extracted_text(text)
            
            logging.info(f"OCR извлек текст длиной {len(cleaned_text)} символов")
            return cleaned_text
            
        except Exception as e:
            logging.error(f"Ошибка OCR: {e}")
            return ""
    
    @staticmethod
    def clean_extracted_text(text):
        """Очистка извлеченного текста"""
        # Убираем лишние пробелы и переносы строк
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Исправляем частые OCR ошибки
        replacements = {
            '|': 'I',
            '0': 'O',
            '1': 'I',
            '5': 'S',
            '8': 'B'
        }
        
        for wrong, correct in replacements.items():
            text = text.replace(wrong, correct)
            
        return text
    
    @staticmethod
    def extract_passport_data(text):
        """Извлечение данных паспорта из текста"""
        data = {
            'fio': '',
            'series_number': '',
            'birthdate': '',
            'issued_by': '',
            'issue_date': '',
            'department_code': '',
            'registration': ''
        }
        
        try:
            lines = text.split('\n')
            lines = [line.strip() for line in lines if line.strip()]
            
            # Поиск ФИО (русские буквы, пробелы)
            fio_pattern = r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'
            for line in lines:
                fio_match = re.search(fio_pattern, line)
                if fio_match and len(fio_match.group().split()) == 3:
                    data['fio'] = fio_match.group()
                    break
            
            # Поиск серии и номера паспорта
            passport_pattern = r'(\d{4}\s*\d{6})'
            for line in lines:
                passport_match = re.search(passport_pattern, line)
                if passport_match:
                    series_number = passport_match.group(1).replace(' ', '')
                    if len(series_number) == 10:
                        data['series_number'] = series_number[:4] + ' ' + series_number[4:]
                    break
            
            # Поиск даты рождения
            date_pattern = r'(\d{1,2}[\.\s]\d{1,2}[\.\s]\d{4})'
            dates = []
            for line in lines:
                date_matches = re.findall(date_pattern, line)
                dates.extend(date_matches)
            
            if dates:
                # Первая дата обычно дата рождения
                data['birthdate'] = dates[0].replace(' ', '.')
            
            # Поиск кода подразделения
            code_pattern = r'(\d{3}-\d{3})'
            for line in lines:
                code_match = re.search(code_pattern, line)
                if code_match:
                    data['department_code'] = code_match.group(1)
                    break
            
            # Поиск места выдачи
            issued_patterns = [
                r'ОВД',
                r'УВД',
                r'МВД',
                r'отделением',
                r'выдан'
            ]
            
            for i, line in enumerate(lines):
                for pattern in issued_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Берем текущую строку и следующую как место выдачи
                        issued_text = line
                        if i + 1 < len(lines):
                            issued_text += ' ' + lines[i + 1]
                        data['issued_by'] = issued_text[:100]  # ограничиваем длину
                        break
            
            # Поиск даты выдачи (обычно вторая дата в документе)
            if len(dates) >= 2:
                data['issue_date'] = dates[1].replace(' ', '.')
                
        except Exception as e:
            logging.error(f"Ошибка извлечения данных паспорта: {e}")
        
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
            text_upper = text.upper()
            
            # Поиск VIN (17 символов, буквы и цифры)
            vin_pattern = r'[A-HJ-NPR-Z0-9]{17}'
            vin_match = re.search(vin_pattern, text_upper)
            if vin_match:
                data['vin'] = vin_match.group()
            
            # Поиск госномера (русские буквы, цифры)
            reg_patterns = [
                r'[А-Я]{1}\d{3}[А-Я]{2}\d{2,3}',  # стандартный
                r'[А-Я]{2}\d{3}\d{2,3}',           # старый формат
                r'\d{4}[А-Я]{2}\d{2,3}'            # другой вариант
            ]
            
            for pattern in reg_patterns:
                reg_match = re.search(pattern, text_upper)
                if reg_match:
                    data['reg_number'] = reg_match.group()
                    break
            
            # Поиск года выпуска
            year_pattern = r'(19|20)\d{2}'
            year_match = re.search(year_pattern, text)
            if year_match:
                data['year'] = year_match.group()
            
            # Поиск мощности
            power_patterns = [
                r'(\d{2,3})\s*[лЛ][\.\s]?[сС]',
                r'мощность\D*(\d{2,3})',
                r'power\D*(\d{2,3})'
            ]
            
            for pattern in power_patterns:
                power_match = re.search(pattern, text, re.IGNORECASE)
                if power_match:
                    data['power'] = power_match.group(1)
                    break
            
            # Поиск марки и модели
            brands = ['LADA', 'ВАЗ', 'VOLKSWAGEN', 'VW', 'SKODA', 'RENAULT', 
                     'HYUNDAI', 'KIA', 'TOYOTA', 'NISSAN', 'MAZDA', 'BMW', 
                     'MERCEDES', 'AUDI', 'FORD', 'CHEVROLET', 'OPEL', 'CITROEN', 
                     'PEUGEOT', 'MITSUBISHI', 'HONDA', 'SUZUKI', 'SUBARU']
            
            for brand in brands:
                if brand in text_upper:
                    data['brand'] = brand
                    # Пытаемся найти модель после марки
                    brand_index = text_upper.find(brand)
                    if brand_index != -1:
                        rest_of_text = text[brand_index + len(brand):brand_index + 50]
                        words = rest_of_text.split()[:3]
                        if words:
                            data['model'] = ' '.join(words).strip()
                    break
                    
        except Exception as e:
            logging.error(f"Ошибка извлечения данных ТС: {e}")
        
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
            lines = text.split('\n')
            lines = [line.strip() for line in lines if line.strip()]
            
            # Поиск ФИО
            fio_pattern = r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'
            for line in lines:
                fio_match = re.search(fio_pattern, line)
                if fio_match and len(fio_match.group().split()) == 3:
                    data['fio'] = fio_match.group()
                    break
            
            # Поиск номеров водительского удостоверения
            license_patterns = [
                r'(\d{2}\s*\d{6,9})',
                r'[A-Z]{2}\s*\d{6,9}',
                r'в\/у\s*[:\-]?\s*(\d{2}\s*\d{6,9})'
            ]
            
            for pattern in license_patterns:
                for line in lines:
                    license_match = re.search(pattern, line, re.IGNORECASE)
                    if license_match:
                        number = license_match.group(1) if license_match.groups() else license_match.group()
                        number = re.sub(r'\s+', '', number)
                        if len(number) >= 8:
                            data['number'] = number[:2] + ' ' + number[2:]
                        break
                if data['number']:
                    break
            
            # Поиск дат
            date_pattern = r'(\d{1,2}[\.\s]\d{1,2}[\.\s]\d{4})'
            dates = []
            for line in lines:
                date_matches = re.findall(date_pattern, line)
                dates.extend(date_matches)
            
            if len(dates) >= 1:
                data['birthdate'] = dates[0].replace(' ', '.')
            if len(dates) >= 2:
                data['issue_date'] = dates[1].replace(' ', '.')
            if len(dates) >= 3:
                data['expiry'] = dates[2].replace(' ', '.')
                
        except Exception as e:
            logging.error(f"Ошибка извлечения данных в/у: {e}")
        
        return data
    
    @staticmethod
    def format_ocr_results(data_dict, data_type):
        """Форматирование результатов OCR для пользователя"""
        if not any(data_dict.values()):
            return "Не удалось автоматически распознать данные. Пожалуйста, введите информацию вручную."
        
        result = f"📄 Автоматически распознанные данные ({data_type}):\n\n"
        
        fields_map = {
            'passport': {
                'fio': 'ФИО',
                'series_number': 'Серия и номер',
                'birthdate': 'Дата рождения',
                'issued_by': 'Кем выдан',
                'issue_date': 'Дата выдачи',
                'department_code': 'Код подразделения'
            },
            'vehicle': {
                'vin': 'VIN',
                'brand': 'Марка',
                'model': 'Модель',
                'year': 'Год выпуска',
                'power': 'Мощность',
                'reg_number': 'Госномер'
            },
            'license': {
                'fio': 'ФИО',
                'birthdate': 'Дата рождения',
                'issue_date': 'Дата выдачи',
                'expiry': 'Срок действия',
                'number': 'Номер удостоверения'
            }
        }
        
        fields = fields_map.get(data_type, {})
        for key, display_name in fields.items():
            value = data_dict.get(key, '')
            if value:
                result += f"• {display_name}: {value}\n"
        
        result += "\n✅ Эти данные будут использованы для оформления. Вы можете изменить их вручную на следующем шаге."
        return result