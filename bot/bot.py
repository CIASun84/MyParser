from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import schedule
import requests
import logging
import os
import json
from datetime import datetime
import traceback

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("parser.log", encoding='utf-8'),  # Добавлен параметр encoding='utf-8'
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# --- Настройки ---
BASE_URL = "https://www.rabota.md/ru/jobs-moldova"
KEYWORDS = ["по сменному графику", "part-time", "în ture", "contabil", "бухгалтер", "operator"]  # Ключевые слова для фильтрации
MAX_PAGES = 5  # Количество страниц для парсинга

# --- Telegram ---
TOKEN = "8174406929:AAFbPL1rePiPe7J4Jxps3MNEtSFJfGVth5c"  # Замени на токен твоего бота
CHAT_ID = "6137830790"   # Замени на твой chat_id

def send_to_telegram(message):
    """Отправляет сообщение в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, data=payload)
        response_data = response.json()

        if response.status_code == 200 and response_data.get('ok'):
            logger.info("Сообщение успешно отправлено в Telegram")
        else:
            logger.error(f"Ошибка при отправке в Telegram: {response_data}")

        return response_data
    except Exception as e:
        logger.error(f"Исключение при отправке в Telegram: {str(e)}")
        return None

def save_found_jobs(job_links):
    """Сохраняет список найденных вакансий в файл"""
    try:
        with open("found_jobs.json", "w", encoding="utf-8") as f:
            json.dump(job_links, f, ensure_ascii=False)
        logger.info(f"Сохранено {len(job_links)} ID вакансий")
    except Exception as e:
        logger.error(f"Ошибка при сохранении найденных вакансий: {str(e)}")

def load_found_jobs():
    """Загружает список найденных вакансий из файла"""
    try:
        if os.path.exists("found_jobs.json"):
            with open("found_jobs.json", "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Ошибка при загрузке найденных вакансий: {str(e)}")
        return []

def setup_driver():
    """Настраивает и возвращает драйвер Chrome"""
    try:
        # Настройка Selenium с Chrome
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36')

        # Попробуем создать Service объект, это требуется для Selenium 4+
        try:
            # Если ChromeDriver находится в PATH
            driver = webdriver.Chrome(options=options)
        except:
            # Если ChromeDriver не в PATH, нужно указать путь
            # Укажите путь к chromedriver.exe для Windows или chromedriver для Linux/Mac
            driver_path = "./chromedriver"  # Измените на правильный путь
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=options)

        logger.info("WebDriver успешно инициализирован")
        return driver
    except Exception as e:
        logger.error(f"Ошибка при настройке драйвера: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def get_html(url, driver):
    """Открывает страницу в браузере Chrome и возвращает HTML-код"""
    try:
        logger.info(f"Загрузка страницы: {url}")
        driver.get(url)

        # Ждем загрузки страницы с помощью явного ожидания
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # Делаем скриншот для отладки
        #driver.save_screenshot(f"page_{int(time.time())}.png")

        # Получаем исходный код страницы
        page_source = driver.page_source
        logger.info(f"Страница загружена, длина HTML: {len(page_source)} символов")

        # Для отладки сохраним HTML
        with open(f"page_{int(time.time())}.html", "w", encoding="utf-8") as f:
            f.write(page_source)

        return page_source
    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы {url}: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def parse_jobs(html):
    """Извлекает вакансии и фильтрует их по ключевым словам"""
    try:
        if not html:
            logger.error("HTML пуст или не был получен")
            return []

        logger.info("Начинаем парсинг HTML")
        soup = BeautifulSoup(html, "lxml")

        # Используем более надежный селектор
        vacancy_links = soup.select(".vacancies-feed a.vacancyShowPopup")
        logger.info(f"Найдено ссылок на вакансии: {len(vacancy_links)}")

        # Если основной селектор не сработал, попробуем альтернативные
        if not vacancy_links:
            logger.warning("Селектор '.vacancies-feed a.vacancyShowPopup' не нашел результатов, пробуем альтернативные")

            # Альтернативные селекторы
            vacancy_links = soup.select("a.vacancyShowPopup")
            if not vacancy_links:
                vacancy_links = soup.select(".card a[href*='/vacancy/']")
                if not vacancy_links:
                    vacancy_links = soup.select("div.vacancy-block a")
                    if not vacancy_links:
                        vacancy_links = soup.select("div.job-title")

        logger.info(f"После проверки альтернативных селекторов найдено ссылок: {len(vacancy_links)}")

        results = []
        for link in vacancy_links:
            title = link.text.strip()
            url = link.get("href", "")
            if not url.startswith("http"):
                url = "https://www.rabota.md" + url

            logger.debug(f"Обрабатываемая вакансия: {title}, URL: {url}")

            # Проверяем ключевые слова
            if any(word.lower() in title.lower() for word in KEYWORDS):
                logger.info(f"Вакансия соответствует фильтру: {title}")
                results.append(f"🔹 <b>{title}</b>\n<a href='{url}'>Смотреть вакансию</a>")
            else:
                logger.debug(f"Вакансия не соответствует фильтру: {title}")

        logger.info(f"Найдено вакансий, соответствующих фильтру: {len(results)}")
        return results
    except Exception as e:
        logger.error(f"Ошибка при парсинге страницы: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def scrape_all_pages(driver):
    """Парсит несколько страниц сайта"""
    all_results = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}?page={page}"
        logger.info(f"Парсим страницу {page} из {MAX_PAGES}: {url}")

        html = get_html(url, driver)
        if html:
            results = parse_jobs(html)
            all_results.extend(results)
            logger.info(f"На странице {page} найдено {len(results)} вакансий")
        else:
            logger.error(f"Не удалось получить HTML для страницы {page}")

        # Задержка между запросами
        time.sleep(5)

    logger.info(f"Всего найдено {len(all_results)} вакансий")
    return all_results

def job():
    logger.info(f"=== Запуск парсера {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    # Загружаем ранее найденные вакансии
    found_jobs = load_found_jobs()
    logger.info(f"Загружено {len(found_jobs)} ранее найденных вакансий")

    # Настройка драйвера
    driver = setup_driver()
    if not driver:
        logger.error("Не удалось инициализировать драйвер. Прерываем выполнение.")
        return

    # Парсим вакансии
    try:
        vacancies = scrape_all_pages(driver)
    except Exception as e:
        logger.error(f"Ошибка при парсинге: {str(e)}")
        logger.error(traceback.format_exc())
        vacancies = []
    finally:
        try:
            driver.quit()
            logger.info("Драйвер закрыт")
        except:
            logger.warning("Не удалось корректно закрыть драйвер")

    if not vacancies:
        logger.warning("Вакансии не найдены")
        # Отправим тестовое сообщение для проверки работы Telegram API
        send_to_telegram("🔄 Проверка работы бота. На данный момент вакансий не найдено.")
        return

    # Фильтрация только новых вакансий
    new_vacancies = []
    new_links = []

    for vacancy in vacancies:
        try:
            link = vacancy.split("'")[1]  # Извлекаем ссылку
            if link not in found_jobs:
                new_vacancies.append(vacancy)
                new_links.append(link)
        except Exception as e:
            logger.error(f"Ошибка при обработке вакансии: {vacancy}, ошибка: {str(e)}")

    # Сохраняем новые вакансии
    if new_links:
        found_jobs.extend(new_links)
        save_found_jobs(found_jobs)

    if new_vacancies:
        message = f"📢 Найдены новые вакансии ({len(new_vacancies)}):\n\n" + "\n\n".join(new_vacancies)

        # Разбиваем большие сообщения на части
        max_length = 4000
        for i in range(0, len(message), max_length):
            chunk = message[i:i + max_length]
            send_to_telegram(chunk)
            time.sleep(1)  # Пауза между отправками

        logger.info(f"Отправлено {len(new_vacancies)} новых вакансий в Telegram")
    else:
        logger.info("Новых вакансий не найдено")

def test_connection():
    """Проверяет соединение с сайтом и API Telegram"""
    logger.info("=== Запуск тестирования соединения ===")

    # Проверка соединения с сайтом
    try:
        response = requests.get(BASE_URL, timeout=10)
        logger.info(f"Соединение с сайтом: статус {response.status_code}")
        if response.status_code == 200:
            logger.info("Соединение с сайтом установлено успешно")
        else:
            logger.error(f"Не удалось подключиться к сайту, код статуса: {response.status_code}")
    except Exception as e:
        logger.error(f"Ошибка при подключении к сайту: {str(e)}")

    # Проверка API Telegram
    try:
        result = send_to_telegram("🔄 Тестирование соединения с Telegram API")
        if result and result.get('ok'):
            logger.info("Соединение с Telegram API успешно")
        else:
            logger.error(f"Ошибка при подключении к Telegram API: {result}")
    except Exception as e:
        logger.error(f"Исключение при подключении к Telegram API: {str(e)}")

    # Тестирование Selenium
    try:
        driver = setup_driver()
        if driver:
            logger.info("Тест Selenium успешен, драйвер инициализирован")
            driver.quit()
        else:
            logger.error("Не удалось инициализировать драйвер Selenium")
    except Exception as e:
        logger.error(f"Ошибка при тестировании Selenium: {str(e)}")
        logger.error(traceback.format_exc())

    logger.info("=== Завершение тестирования соединения ===")

if __name__ == "__main__":
    try:
        # Проверка соединения при запуске
        test_connection()

        # Запускаем парсер сразу
        job()

        # Настраиваем регулярный запуск
        schedule.every(8).hours.do(job)

        logger.info("⏳ Парсер запущен и настроен на выполнение каждые 8 часов... Нажмите Ctrl+C для остановки.")
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Парсер остановлен пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}")
        logger.critical(traceback.format_exc())
