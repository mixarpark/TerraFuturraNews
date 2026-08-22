import os
import re
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
SERPER_API_KEY = os.getenv('SERPER_API_KEY')

EXISTING_SOURCES_FILE = "source_links.txt"

# Поисковые запросы и ключи для темы "Брендинг территорий"
SEARCH_QUERIES = [
    '"place branding" blog OR news',
    '"city branding" articles',
    '"destination marketing" rss'
]


# Keywords for News Parsing: Territorial Marketing, Tourism, Urban Dev & Talent Attraction

KEYWORDS = [
    # --- Core Place Marketing & Branding ---
    'place branding', 'place marketing', 'territorial branding', 'territorial marketing',
    'city branding', 'city marketing', 'destination branding', 'destination marketing',
    'regional branding', 'regional marketing', 'nation branding', 'location marketing',
    'place identity', 'place reputation', 'place image', 'destination management organization',
    
    # --- Tourism & Visitor Economy ---
    'visitor economy', 'sustainable tourism', 'ecotourism', 'smart tourism',
    'experiential travel', 'experiential tourism', 'cultural tourism', 'rural tourism',
    'tourism development', 'tourist attraction', 'destination management', 
    'digital nomad destination',
    
    # --- Urban Development & Placemaking ---
    'urban development', 'urban planning', 'placemaking', 'creative placemaking',
    'urban regeneration', 'urban revitalization', 'smart city', 'smart urbanism',
    'public space activation', 'urban design', 'tactical urbanism', '15-minute city',
    'transit-oriented development', 'sustainable urban development',
    
    # --- Livability & Resident Attractiveness ---
    'livability', 'liveability', 'quality of life', 'citizen well-being',
    'resident engagement', 'community engagement', 'resident retention', 'resident attraction',
    'urban amenities', 'vibrant community', 'community building', 'inclusive city',
    'social inclusion', 'green infrastructure', 'citizen happiness',
    
    # --- Skilled Migration, Talent & Economic Development ---
    'talent attraction', 'talent retention', 'skilled migration', 'global talent',
    'brain gain', 'human capital', 'knowledge economy', 'creative class',
    'innovation ecosystem', 'startup ecosystem', 'expat community', 'relocation hub',
    'economic development', 'foreign direct investment', 'innovation district'
]

# Exceptions to filter out corporate HR, digital marketing spam, and negative urban/tourism trends
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

# Пример логики для парсера (псевдокод/набросок для дальнейшего использования):
# match = any(keyword in text_lower for keyword in KEYWORDS) and not any(exception in text_lower for exception in EXCEPTIONS)


BLACKLIST_DOMAINS = {'youtube.com', 'facebook.com', 'twitter.com', 'wikipedia.org', 'reddit.com'}



HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsScoutBot/1.0"}

def get_existing_domains():
    if not os.path.exists(EXISTING_SOURCES_FILE):
        return set()
    with open(EXISTING_SOURCES_FILE, "r", encoding="utf-8") as f:
        urls = f.read().splitlines()
    return {urlparse(u).netloc.replace("www.", "") for u in urls if u}

def find_rss(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for link in soup.find_all('link', type=re.compile(r'application/(rss|atom)\+xml', re.IGNORECASE)):
            return urljoin(url, link.get('href'))
    except: pass
    return None

def validate_rss(rss_url):
    try:
        feed = feedparser.parse(requests.get(rss_url, headers=HEADERS, timeout=10).content)
        for entry in feed.entries[:10]:
            text = (getattr(entry, 'title', '') + " " + getattr(entry, 'summary', '')).lower()
            if any(kw in text for kw in KEYWORDS):
                return True, getattr(feed.feed, 'title', 'Новый источник')
    except: pass
    return False, ""

def send_alert(sources):
    if not sources or not BOT_TOKEN: return
    text = "🕵️‍♂️ **Разведчик нашел новые сайты:**\n\n"
    for title, url in sources.items(): text += f"- {title}\n🔗 {url}\n\n"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text})

print("🚀 Запуск Разведчика...")
existing_domains = get_existing_domains()
found_urls = set()

for query in SEARCH_QUERIES:
    try:
        resp = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': SERPER_API_KEY}, json={"q": query})
        for item in resp.json().get('organic', []):
            link = item.get('link', '')
            domain = urlparse(link).netloc.replace("www.", "")
            if domain and domain not in existing_domains and not any(bl in domain for bl in BLACKLIST_DOMAINS):
                found_urls.add(f"{urlparse(link).scheme}://{urlparse(link).netloc}")
    except Exception as e: print(f"Ошибка поиска: {e}")

valid_sources = {}
for base_url in found_urls:
    rss = find_rss(base_url)
    if rss:
        is_valid, title = validate_rss(rss)
        if is_valid: valid_sources[title] = rss

if valid_sources:
    with open(EXISTING_SOURCES_FILE, "a", encoding="utf-8") as f:
        for url in valid_sources.values(): f.write(f"{url}\n")
    send_alert(valid_sources)
    print(f"✅ Добавлено источников: {len(valid_sources)}")
else:
    print("🤷‍♂️ Новых источников не найдено.")
