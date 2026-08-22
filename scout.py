import os
import re
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# ==============================================================================
# 1. НАСТРОЙКИ И АВТОРИЗАЦИЯ
# ==============================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
SERPER_API_KEY = os.getenv('SERPER_API_KEY')

EXISTING_SOURCES_FILE = "source_links.txt"
PENDING_FILE = "pending_sources.txt"

REQ_TIMEOUT = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# ==============================================================================
# 2. МАТРИЦА ПОИСКОВЫХ ЗАПРОСОВ (ГЛУБОКИЙ ПОИСК ПО ВСЕМ ФОРМАТАМ)
# ==============================================================================
SEARCH_QUERIES = [
    # 1. Core Place & City Branding
    '"place branding" OR "city branding" blog OR articles',
    '"destination branding" OR "territorial marketing" case study',
    
    # 2. Tourism & Destination Management
    '"sustainable tourism" OR "destination management" insights OR report',
    '"smart tourism" OR "visitor economy" trends 2026',
    
    # 3. Urban Planning & Placemaking
    '"creative placemaking" OR "tactical urbanism" articles',
    '"urban regeneration" OR "15-minute city" project case study',
    
    # 4. Talent Attraction & Livability
    '"talent attraction" OR "skilled migration" city strategy',
    '"livability" OR "quality of life" city index report',
    
    # 5. Аналитические отчеты и Whitepapers (включая PDF)
    '"place marketing" OR "nation branding" filetype:pdf report',
    '"economic development" "innovation district" insights filetype:pdf'
]

# ==============================================================================
# 3. КЛЮЧЕВЫЕ СЛОВА И ИСКЛЮЧЕНИЯ
# ==============================================================================
KEYWORDS = [
    # Core Place Marketing & Branding
    'place branding', 'place marketing', 'territorial branding', 'territorial marketing',
    'city branding', 'city marketing', 'destination branding', 'destination marketing',
    'regional branding', 'regional marketing', 'nation branding', 'location marketing',
    'place identity', 'place reputation', 'place image', 'destination management organization',
    
    # Tourism & Visitor Economy
    'visitor economy', 'sustainable tourism', 'ecotourism', 'smart tourism',
    'experiential travel', 'experiential tourism', 'cultural tourism', 'rural tourism',
    'tourism development', 'tourist attraction', 'destination management', 
    'digital nomad destination',
    
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

# Высокопроизводительная компиляция регулярных выражений
KW_PATTERN = re.compile(rf"\b({'|'.join(map(re.escape, KEYWORDS))})\b", re.IGNORECASE)
EXC_PATTERN = re.compile(rf"\b({'|'.join(map(re.escape, EXCEPTIONS))})\b", re.IGNORECASE)

BLACKLIST_DOMAINS = {
    'youtube.com', 'facebook.com', 'twitter.com', 'x.com', 'instagram.com',
    'linkedin.com', 'wikipedia.org', 'amazon.com', 'reddit.com', 'pinterest.com',
    'tiktok.com', 'quora.com', 'medium.com'
}

# ==============================================================================
# 4. СЛУЖЕБНЫЕ ФУНКЦИИ ИЗВЛЕЧЕНИЯ И ВАЛИДАЦИИ
# ==============================================================================
def get_existing_links():
    """Считывает уже имеющиеся ссылки, чтобы исключить дубликаты."""
    if not os.path.exists(EXISTING_SOURCES_FILE):
        return set()
    with open(EXISTING_SOURCES_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def find_rss_on_page(url):
    """Ищет RSS/Atom ленту в заголовке HTML."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            rss_links = soup.find_all('link', type=re.compile(r'application/(rss|atom)\+xml', re.IGNORECASE))
            for link in rss_links:
                href = link.get('href')
                if href:
                    return urljoin(url, href)
    except:
        pass
    return None

def validate_rss(rss_url):
    """Проверяет валидность и релевантность RSS-ленты."""
    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=REQ_TIMEOUT)
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            return False, ""
        
        for entry in feed.entries[:10]:
            text = f"{getattr(entry, 'title', '')} {getattr(entry, 'summary', '')}"
            if KW_PATTERN.search(text) and not EXC_PATTERN.search(text):
                title = getattr(feed.feed, 'title', 'RSS Источник')
                return True, title
    except:
        pass
    return False, ""

def validate_web_page_or_doc(url, snippet=""):
    """
    Валидирует статьи, блоги, PDF и отчеты без RSS.
    Использует сниппет поисковика + анализ содержимого страницы.
    """
    # 1. Экспресс-проверка по сниппету Google
    if snippet and KW_PATTERN.search(snippet) and not EXC_PATTERN.search(snippet):
        return True, "Статья / Аналитический отчет"
        
    # 2. Если это PDF-документ
    if url.lower().endswith('.pdf'):
        return True, "PDF Отчет / Whitepaper"
        
    # 3. Анализ HTML-страницы
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            page_text = soup.get_text(separator=' ')
            page_title = soup.title.string.strip() if soup.title and soup.title.string else "Публикация"
            
            if KW_PATTERN.search(page_text) and not EXC_PATTERN.search(page_text):
                return True, page_title
    except:
        pass
    return False, ""

def send_telegram_report(new_sources):
    """Отправляет структурированный отчет в Telegram."""
    if not new_sources or not BOT_TOKEN or not CHAT_ID:
        return
        
    text = f"🕵️‍♂️ <b>Разведчик: найдено {len(new_sources)} новых источников</b>\n\n"
    for i, (url, info) in enumerate(list(new_sources.items())[:20], 1):
        text += f"{i}. <b>{info['type']}</b>: {info['title']}\n🔗 {url}\n\n"
        
    text += "<i>Все ссылки добавлены в базу и готовы к мониторингу.</i>"
    
    tg_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(tg_api, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"⚠️ Ошибка отправки отчета в Telegram: {e}")

# ==============================================================================
# 5. ОСНОВНОЙ ЦИКЛ ПОИСКА И ОБРАБОТКИ
# ==============================================================================
print("🚀 Разведчик запускает масштабный сбор источников...")

if not SERPER_API_KEY:
    print("❌ Ошибка: SERPER_API_KEY не задан в секретах GitHub!")
    exit(1)

existing_links = get_existing_links()
discovered_items = [] # Список кортежей: (url, snippet, base_domain)

for query in SEARCH_QUERIES:
    print(f"📡 Поиск: {query}")
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            json={"q": query, "num": 20}, # Запрашиваем 20 результатов на каждый запрос
            timeout=REQ_TIMEOUT
        )
        
        if resp.status_code != 200:
            print(f"⚠️ Ошибка Serper ({resp.status_code}): {resp.text}")
            continue
            
        for item in resp.json().get('organic', []):
            link = item.get('link', '')
            snippet = item.get('snippet', '')
            if not link:
                continue
                
            domain = urlparse(link).netloc.replace("www.", "")
            if domain and not any(bl in domain for bl in BLACKLIST_DOMAINS):
                if link not in existing_links:
                    discovered_items.append((link, snippet))
    except Exception as e:
        print(f"❌ Сбой запроса к API: {e}")

print(f"🔍 Всего кандидатов на проверку: {len(discovered_items)}")

# Валидация и категоризация
valid_new_sources = {}

for link, snippet in discovered_items:
    if link in existing_links or link in valid_new_sources:
        continue
        
    base_url = f"{urlparse(link).scheme}://{urlparse(link).netloc}"
    
    # А. Попытка 1: Проверяем наличие RSS-ленты у сайта
    rss_url = find_rss_on_page(base_url)
    if rss_url and rss_url not in existing_links:
        is_valid, title = validate_rss(rss_url)
        if is_valid:
            print(f"   [+] Найдена RSS-лента: {title} ({rss_url})")
            valid_new_sources[rss_url] = {"title": title, "type": "📡 RSS-лента"}
            existing_links.add(rss_url)
            continue
            
    # Б. Попытка 2: Проверяем прямую страницу/блог/PDF-отчет
    is_valid, title = validate_web_page_or_doc(link, snippet)
    if is_valid:
        doc_type = "📄 PDF Отчет" if link.lower().endswith('.pdf') else "🌐 Статья / Блог"
        print(f"   [+] Найден материал ({doc_type}): {title} ({link})")
        valid_new_sources[link] = {"title": title, "type": doc_type}
        existing_links.add(link)

# Сохранение и отчет
if valid_new_sources:
    with open(EXISTING_SOURCES_FILE, "a", encoding="utf-8") as f:
        for url in valid_new_sources.keys():
            f.write(f"{url}\n")
            
    send_telegram_report(valid_new_sources)
    print(f"🎉 Разведка завершена! Добавлено {len(valid_new_sources)} новых источников.")
else:
    print("🤷‍♂️ Новых валидных источников в этом цикле не найдено.")
