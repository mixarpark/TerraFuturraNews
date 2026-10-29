from deep_translator import GoogleTranslator
import time
import os
import re
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# ==============================================================================
# 1. НАСТРОЙКИ И АВТОРИЗАЦИЯ
# ==============================================================================
WEBAPP_URL = os.getenv('WEBAPP_URL')
SERPER_API_KEY = os.getenv('SERPER_API_KEY')

REQ_TIMEOUT = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# ==============================================================================
# 2. МАТРИЦА ПОИСКОВЫХ ЗАПРОСОВ (БЕЗ ПЛАТНЫХ ОПЕРАТОРОВ)
# ==============================================================================
SEARCH_QUERIES = [
    # 1. Core Place & City Branding
    'place branding blog',
    'city branding articles',
    'territorial marketing case study',
    
    # 2. Tourism & Destination Management
    'destination management insights report',
    'sustainable tourism trends 2026',
    'visitor economy strategies',
    
    # 3. Urban Planning & Placemaking
    'creative placemaking articles',
    'tactical urbanism project case study',
    'urban regeneration news',
    
    # 4. Talent Attraction & Livability
    'talent attraction city strategy',
    'livability city index report',
    'quality of life urban research',
    
    # 5. Аналитические отчеты и Whitepapers (ищем PDF через текст)
    'nation branding whitepaper pdf',
    'economic development innovation district pdf',
    'place marketing research report pdf'
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



# ==============================================================================
# 5. ОСНОВНОЙ ЦИКЛ ПОИСКА И ОБРАБОТКИ
# ==============================================================================
print("🚀 Разведчик запускает масштабный мультиязычный сбор источников...")

if not SERPER_API_KEY:
    print("❌ Ошибка: SERPER_API_KEY не задан в секретах GitHub!")
    exit(1)

try:
    req = requests.post(WEBAPP_URL, json={"action": "get_all_experts_radars"}, timeout=30)
    experts_data = req.json().get('experts', [])
except Exception as e:
    print(f"❌ Ошибка связи с GAS: {e}")
    exit(1)

TARGET_LANGUAGES = ['es', 'pt', 'it', 'id', 'vi', 'hi', 'ur', 'tr', 'ka', 'hy', 'kk', 'zh-CN', 'ru', 'de', 'fr', 'ar', 'ja', 'ko']

for expert in experts_data:
    email = expert.get('email')
    existing_links = set(expert.get('sources', []))
    discovered_items = []
    print(f"\n📡 Разведка для эксперта: {email}")

    for base_query in SEARCH_QUERIES:
        for lang in TARGET_LANGUAGES:
            try:
                translated_query = GoogleTranslator(source='en', target=lang).translate(base_query)
                resp = requests.post(
                    "https://google.serper.dev/search",
                    headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
                    json={"q": translated_query, "num": 10, "hl": lang},
                    timeout=REQ_TIMEOUT
                )
                
                if resp.status_code == 200:
                    for item in resp.json().get('organic', []):
                        link = item.get('link', '')
                        snippet = item.get('snippet', '')
                        if not link: continue
                        domain = urlparse(link).netloc.replace("www.", "")
                        if domain and not any(bl in domain for bl in BLACKLIST_DOMAINS):
                            if link not in existing_links:
                                discovered_items.append((link, snippet))
                time.sleep(1)
            except:
                pass

    valid_new_sources = []
    for link, snippet in discovered_items:
        if link in existing_links: continue
        base_url = f"{urlparse(link).scheme}://{urlparse(link).netloc}"
        
        rss_url = find_rss_on_page(base_url)
        if rss_url and rss_url not in existing_links:
            is_valid, title = validate_rss(rss_url)
            if is_valid:
                valid_new_sources.append({"url": rss_url, "type": "RSS-лента", "title": title})
                existing_links.add(rss_url)
                continue
                
        is_valid, title = validate_web_page_or_doc(link, snippet)
        if is_valid:
            doc_type = "PDF" if link.lower().endswith('.pdf') else "Блог / Сайт"
            valid_new_sources.append({"url": link, "type": doc_type, "title": title})
            existing_links.add(link)

    if valid_new_sources:
        print(f"   [+] Найдено {len(valid_new_sources)} новых источников. Отправляем в Эксперториум...")
        try:
            requests.post(WEBAPP_URL, json={
                "action": "push_radar_findings", 
                "email": email, 
                "new_sources": valid_new_sources
            }, timeout=30)
        except Exception as e:
            print(f"   [!] Ошибка отправки: {e}")

print("\n🎉 Разведка для всех экспертов успешно завершена!")
