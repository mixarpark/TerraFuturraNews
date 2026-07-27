import os
import re
import requests
import feedparser
import pdfplumber
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# ==========================================
# 1. КОНФИГУРАЦИЯ И НАСТРОЙКИ
# ==========================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

FOLDER_PATH = "library_files"
SOURCE_LINKS_FILE = "source_links.txt"
HISTORY_FILE = "sent_articles.txt"

KEYWORDS = ['ar', 'phygital', 'audio', 'immersive', 'xr', 'augmented reality', 
            'spatial audio', 'immsersive audio', 'mixed reality', 
            'spatial computing', 'interactive', 'smart glasses', 'ai']
EXCEPTIONS = ['vr', 'virtual reality']

# Предварительная компиляция регулярных выражений для СУПЕР-быстрого поиска
# Ищем любое из ключевых слов как самостоятельное слово (без учета регистра)
KW_PATTERN = re.compile(rf"\b({'|'.join(map(re.escape, KEYWORDS))})\b", re.IGNORECASE)
EXC_PATTERN = re.compile(rf"\b({'|'.join(map(re.escape, EXCEPTIONS))})\b", re.IGNORECASE)

# Заголовки для обхода блокировок парсинга
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}

translator = GoogleTranslator(source='auto', target='ru')

# ==========================================
# 2. ФУНКЦИИ ИЗВЛЕЧЕНИЯ ССЫЛОК
# ==========================================
def extract_links_from_pdf(file_path):
    found_urls = set()
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # Ищем ссылки сразу на странице, не скапливая мега-строку
                    urls = re.findall(r"https?://[^\s\)]+", text)
                    found_urls.update(urls)
    except Exception as e:
        print(f"❌ Ошибка чтения PDF {file_path}: {e}")
    return found_urls

def extract_links_from_txt(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            return set(re.findall(r"https?://[^\s\)]+", file.read()))
    except Exception as e:
        print(f"❌ Ошибка чтения TXT {file_path}: {e}")
        return set()

def send_to_telegram(title, url, keyword):
    """Единая функция для перевода и отправки сообщения в Telegram"""
    try:
        translated_title = translator.translate(title)
    except Exception as e:
        print(f"⚠️ Ошибка перевода: {e}")
        translated_title = title # Фолбек: отправляем без перевода, если API отвалился

    hashtag = f"#{keyword.replace(' ', '_')}"
    message_text = f"📰 Найдено по тегу {hashtag}\n\n🇷🇺 {translated_title}\n🇬🇧 {title}\n\n🔗 {url}"
    
    tg_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        # Обязательно используем timeout!
        requests.post(tg_api, data={"chat_id": CHAT_ID, "text": message_text}, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")

# ==========================================
# 3. ПОДГОТОВКА ИСТОЧНИКОВ (ПАРСИНГ ПАПКИ)
# ==========================================
all_links = set() # Сразу используем множество для исключения дубликатов

if os.path.exists(FOLDER_PATH):
    all_files = os.listdir(FOLDER_PATH)
    print(f"📁 Найдено файлов в {FOLDER_PATH}: {len(all_files)}")
    
    for file_name in all_files:
        full_path = os.path.join(FOLDER_PATH, file_name)
        if file_name.lower().endswith(".pdf"):
            print(f"📄 Читаем PDF: {file_name}")
            all_links.update(extract_links_from_pdf(full_path))
        elif file_name.lower().endswith(".txt"):
            print(f"📝 Читаем TXT: {file_name}")
            all_links.update(extract_links_from_txt(full_path))
            
    # Сохраняем уникальные ссылки
    with open(SOURCE_LINKS_FILE, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")
    print(f"✅ Готово! Сохранено уникальных ссылок: {len(all_links)}")
else:
    print(f"⚠️ Папка {FOLDER_PATH} не найдена.")

# ==========================================
# 4. ПОИСК, ФИЛЬТРАЦИЯ И ОТПРАВКА
# ==========================================
# Загрузка источников
rss_urls = []
if os.path.exists(SOURCE_LINKS_FILE):
    with open(SOURCE_LINKS_FILE, "r", encoding="utf-8") as file:
        rss_urls = file.read().splitlines()

# Загрузка истории (используем SET для быстрого поиска)
sent_links = set()
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        sent_links = set(file.read().splitlines())

print("\n🚀 Начинаем проверку лент...")

for url in rss_urls:
    print(f"📡 Подключаемся к: {url}")
    
    try:
        # САМОЕ ВАЖНОЕ: Жесткий таймаут на запрос, чтобы скрипт не завис!
        response = requests.get(url, headers=HEADERS, timeout=15)
        # Отдаем скачанный контент feedparser'у
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"⚠️ Ошибка сети или таймаут. Пропускаем. Причина: {e}")
        continue

    # ================= ЛОГИКА: ОБЫЧНЫЕ ВЕБ-СТРАНИЦЫ =================
    if not feed.entries:
        if url in sent_links:
            print(f"⏭️ Пропускаем: {url} (уже отправлено)")
            continue
            
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            full_clean_text = soup.get_text(separator=' ').lower()
            
            # Быстрый поиск через скомпилированные регулярки
            match_kw = KW_PATTERN.search(full_clean_text)
            match_exc = EXC_PATTERN.search(full_clean_text)
            
            print(f"🤖 Анализ | Ключи: {bool(match_kw)} | Исключения: {bool(match_exc)}")
            
            if match_kw and not match_exc:
                page_title = soup.title.string.strip() if soup.title and soup.title.string else "Без заголовка"
                found_word = match_kw.group(1).lower() # Достаем то самое слово, которое совпало
                
                print(f"✅ Отправляем: {page_title}")
                send_to_telegram(page_title, url, found_word)
                
                with open(HISTORY_FILE, "a", encoding="utf-8") as file:
                    file.write(url + "\n")
                sent_links.add(url)
                
        except Exception as e:
            print(f"⚠️ Ошибка обработки HTML {url}: {e}")

    # ================= ЛОГИКА: RSS-ЛЕНТЫ =================
    else:
        for article in feed.entries:
            link = getattr(article, 'link', '')
            if not link or link in sent_links:
                continue
                
            title = getattr(article, 'title', '')
            summary = getattr(article, 'summary', '')
            combined_text = f"{title} {summary}".lower()
            
            match_kw = KW_PATTERN.search(combined_text)
            match_exc = EXC_PATTERN.search(combined_text)
            
            if not match_kw or match_exc:
                continue
                
            found_word = match_kw.group(1).lower()
            print(f"✅ Отправляем RSS: {title}")
            
            send_to_telegram(title, link, found_word)
            
            with open(HISTORY_FILE, "a", encoding="utf-8") as file:
                file.write(link + "\n")
            sent_links.add(link)

print("🎉 Проверка успешно завершена!")
