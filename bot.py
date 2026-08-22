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

KEYWORDS = [
    # Core Place Marketing & Branding
    'place branding', 'place marketing', 'territorial branding', 'territorial marketing',
    'city branding', 'city marketing', 'destination branding', 'destination marketing',
    'regional branding', 'regional marketing', 'nation branding', 'location marketing',
    'place identity', 'place reputation', 'place image', 'destination management organization',
    # Tourism & Visitor Economy
    'visitor economy', 'sustainable tourism', 'ecotourism', 'smart tourism',
    'experiential travel', 'experiential tourism', 'cultural tourism', 'rural tourism',
    'tourism development', 'tourist attraction', 'destination management', 'digital nomad destination',
    # Urban Development & Placemaking
    'urban development', 'urban planning', 'placemaking', 'creative placemaking',
    'urban regeneration', 'urban revitalization', 'smart city', 'smart urbanism',
    'public space activation', 'urban design', 'tactical urbanism', '15-minute city',
    'transit-oriented development', 'sustainable urban development',
    # Livability & Resident Attractiveness
    'livability', 'liveability', 'quality of life', 'citizen well-being',
    'resident engagement', 'community engagement', 'resident retention', 'resident attraction',
    'urban amenities', 'vibrant community', 'community building', 'inclusive city',
    'social inclusion', 'green infrastructure', 'citizen happiness',
    # Skilled Migration, Talent & Economic Development
    'talent attraction', 'talent retention', 'skilled migration', 'global talent',
    'brain gain', 'human capital', 'knowledge economy', 'creative class',
    'innovation ecosystem', 'startup ecosystem', 'expat community', 'relocation hub',
    'economic development', 'foreign direct investment', 'innovation district'
]

EXCEPTIONS = [
    # Marketing & Commercial Branding noise
    'digital marketing', 'email marketing', 'affiliate marketing', 'influencer marketing',
    'multi-level marketing', 'network marketing', 'brand ambassador', 'trademark', 
    'seo marketing', 'content marketing',
    # Negative or irrelevant Tourism
    'overtourism', 'tourist trap', 'dark tourism', 'space tourism', 'medical tourism',
    # Negative Migration & Corporate HR noise
    'brain drain', 'talent acquisition', 'talent management', 'talent show', 
    'corporate branding', 'employer branding', 
    # Unrelated Economy/Real Estate
    'real estate bubble', 'stock market', 'parking ticket'
]

# Сверхбыстрая компиляция регулярных выражений
KW_PATTERN = re.compile(rf"\b({'|'.join(map(re.escape, KEYWORDS))})\b", re.IGNORECASE)
EXC_PATTERN = re.compile(rf"\b({'|'.join(map(re.escape, EXCEPTIONS))})\b", re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

translator = GoogleTranslator(source='auto', target='ru')

# ==========================================
# 2. ФУНКЦИИ ИЗВЛЕЧЕНИЯ И ОТПРАВКИ
# ==========================================
def extract_links_from_pdf(file_path):
    found_urls = set()
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    found_urls.update(re.findall(r"https?://[^\s\)]+", text))
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
    try:
        translated_title = translator.translate(title)
    except:
        translated_title = title 

    hashtag = f"#{keyword.replace(' ', '_')}"
    message_text = f"📰 Найдено по тегу {hashtag}\n\n🇷🇺 {translated_title}\n🇬🇧 {title}\n\n🔗 {url}"
    
    tg_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(tg_api, data={"chat_id": CHAT_ID, "text": message_text}, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")

# ==========================================
# 3. ПОДГОТОВКА ИСТОЧНИКОВ (СБОР БАЗЫ)
# ==========================================
all_links = set()

# А. Сначала берем то, что УЖЕ есть (сохраняем работу Разведчика!)
if os.path.exists(SOURCE_LINKS_FILE):
    with open(SOURCE_LINKS_FILE, "r", encoding="utf-8") as f:
        all_links.update(f.read().splitlines())

# Б. Затем добавляем свежие ссылки из ручных файлов (PDF/TXT)
if os.path.exists(FOLDER_PATH):
    print(f"📁 Проверяем папку {FOLDER_PATH}...")
    for file_name in os.listdir(FOLDER_PATH):
        full_path = os.path.join(FOLDER_PATH, file_name)
        if file_name.lower().endswith(".pdf"):
            all_links.update(extract_links_from_pdf(full_path))
        elif file_name.lower().endswith(".txt"):
            all_links.update(extract_links_from_txt(full_path))

# В. Сохраняем объединенную базу без потери данных
with open(SOURCE_LINKS_FILE, "w", encoding="utf-8") as f:
    for link in sorted(all_links):
        if link.strip():
            f.write(link.strip() + "\n")

print(f"✅ База сформирована. Всего уникальных ссылок для проверки: {len(all_links)}")

# ==========================================
# 4. ПОИСК, ФИЛЬТРАЦИЯ И ОТПРАВКА НОВОСТЕЙ
# ==========================================
sent_links = set()
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        sent_links = set(file.read().splitlines())

print("\n🚀 Начинаем проверку сайтов и RSS-лент...")

for url in all_links:
    if not url.strip(): continue
    print(f"📡 Подключаемся к: {url}")
    
    try:
        # ОБЯЗАТЕЛЬНО используем headers, чтобы не получить 403 Forbidden
        response = requests.get(url, headers=HEADERS, timeout=12)
        if response.status_code != 200:
            print(f"⚠️ Сервер отклонил запрос (Код {response.status_code}). Пропускаем.")
            continue
            
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"⚠️ Ошибка сети или таймаут: {e}")
        continue

    # ================= ЛОГИКА 1: ОБЫЧНЫЕ ВЕБ-СТРАНИЦЫ =================
    if not feed.entries:
        if url in sent_links:
            print(f"⏭️ Пропускаем: {url} (уже отправлено)")
            continue
            
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем текст ТОЛЬКО в заголовках и абзацах (игнорируем меню и подвалы сайта)
            text_elements = soup.find_all(['title', 'h1', 'h2', 'h3', 'p', 'meta'])
            clean_text = ' '.join(elem.get_text(separator=' ', strip=True) for elem in text_elements).lower()
            
            match_kw = KW_PATTERN.search(clean_text)
            match_exc = EXC_PATTERN.search(clean_text)
            
            print(f"🤖 Анализ страницы | Ключи: {bool(match_kw)} | Исключения: {bool(match_exc)}")
            
            if match_kw and not match_exc:
                page_title = soup.title.string.strip() if soup.title and soup.title.string else url
                found_word = match_kw.group(1).lower()
                
                print(f"✅ Отправляем: {page_title}")
                send_to_telegram(page_title, url, found_word)
                
                with open(HISTORY_FILE, "a", encoding="utf-8") as file:
                    file.write(url + "\n")
                sent_links.add(url)
                
        except Exception as e:
            print(f"⚠️ Ошибка парсинга HTML {url}: {e}")

    # ================= ЛОГИКА 2: СТАНДАРТНЫЕ RSS-ЛЕНТЫ =================
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
            
            print(f"🤖 Анализ RSS: {title} | Ключевые: {bool(match_kw)} | Исключения: {bool(match_exc)}")
            
            if match_kw and not match_exc:
                found_word = match_kw.group(1).lower()
                print(f"✅ Отправляем RSS: {title}")
                
                send_to_telegram(title, link, found_word)
                
                with open(HISTORY_FILE, "a", encoding="utf-8") as file:
                    file.write(link + "\n")
                sent_links.add(link)

print("🎉 Проверка успешно завершена!")
