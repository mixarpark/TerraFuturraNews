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
WEBAPP_URL = os.getenv('WEBAPP_URL')
if not WEBAPP_URL:
    print("❌ Ошибка: WEBAPP_URL не задан!")
    exit(1)

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

# ==========================================
# 3. ОСНОВНОЙ ЦИКЛ (ОПРОС БАЗ ЭКСПЕРТОВ ЧЕРЕЗ API)
# ==========================================
print("🚀 Запрашиваем базы всех экспертов из Эксперториума...")
try:
    req = requests.post(WEBAPP_URL, json={"action": "get_all_experts_radars"}, timeout=30)
    experts_data = req.json().get('experts', [])
except Exception as e:
    print(f"❌ Ошибка связи с GAS: {e}")
    exit(1)

if not experts_data:
    print("🤷‍♂️ Активных экспертов с базами не найдено.")
    exit(0)

print(f"✅ Получено экспертов для обхода: {len(experts_data)}")

for expert in experts_data:
    email = expert.get('email')
    sources = expert.get('sources', [])
    history = set(expert.get('sent_articles', []))
    found_items = []
    
    print(f"\n📡 Обработка эксперта: {email} (Источников: {len(sources)})")

    for url in sources:
        if not url.strip() or url in history: continue
        try:
            response = requests.get(url, headers=HEADERS, timeout=12)
            if response.status_code != 200: continue
            feed = feedparser.parse(response.content)
        except:
            continue

        if not feed.entries:
            try:
                soup = BeautifulSoup(response.text, 'html.parser')
                text_elements = soup.find_all(['title', 'h1', 'h2', 'h3', 'p', 'meta'])
                clean_text = ' '.join(elem.get_text(separator=' ', strip=True) for elem in text_elements).lower()
                
                match_kw = KW_PATTERN.search(clean_text)
                match_exc = EXC_PATTERN.search(clean_text)
                if match_kw and not match_exc:
                    page_title = soup.title.string.strip() if soup.title and soup.title.string else url
                    try:
                        ru_t = translator.translate(page_title)
                    except:
                        ru_t = page_title
                    found_items.append({"title": page_title, "ru_title": ru_t, "url": url, "keyword": match_kw.group(1).lower()})
                    history.add(url)
            except: pass
        else:
            for article in feed.entries:
                link = getattr(article, 'link', '')
                if not link or link in history: continue
                title = getattr(article, 'title', '')
                summary = getattr(article, 'summary', '')
                combined_text = f"{title} {summary}".lower()
                
                match_kw = KW_PATTERN.search(combined_text)
                match_exc = EXC_PATTERN.search(combined_text)
                if match_kw and not match_exc:
                    try:
                        ru_t = translator.translate(title)
                    except:
                        ru_t = title
                    found_items.append({"title": title, "ru_title": ru_t, "url": link, "keyword": match_kw.group(1).lower()})
                    history.add(link)

    # 4. Отправляем находки обратно в Модерацию Эксперториума
    if found_items:
        print(f"   [+] Отправляем {len(found_items)} новых статей эксперту {email}...")
        try:
            requests.post(WEBAPP_URL, json={
                "action": "push_radar_findings", 
                "email": email, 
                "items": found_items
            }, timeout=30)
        except Exception as e:
            print(f"   [!] Ошибка отправки: {e}")

print("\n🎉 Все базы экспертов успешно проверены!")
