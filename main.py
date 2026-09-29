import os
import time
from datetime import datetime, timezone
import feedparser
import requests
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.cnet.com/rss/news/",
    "https://arstechnica.com/feed/",
    "https://www.wired.com/feed/rss"
]

def run():
    print("Checking environment variables...")
    if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Missing secrets!")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    today_date = datetime.now(timezone.utc).date()

    for feed_url in RSS_FEEDS:
        print(f"Fetching feed: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                continue
            
            for entry in feed.entries[:5]:
                published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_parsed:
                    entry_date = datetime(*published_parsed[:6], tzinfo=timezone.utc).date()
                    if entry_date != today_date:
                        print(f"Skipped old story ({entry_date}): {entry.get('title')}")
                        continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")

                content = f"Title: {title}\nSummary: {summary}\nLink: {link}"

prompt = f"""
تۆ سەرنووسەر و ڕۆژنامەنووسێکی باڵای بواری تەکنەلۆژیایت و شارەزاییەکی قووڵت لە داڕشتنی هەواڵی زانستی بە زمانی کوردیی سۆرانی هەیە

ئەرکی سەرەکی:
١ هەڵسەنگاندن ئەگەر ناوەڕۆکی بابەتەکە بایەخێکی گەورەی نییە لەسەر جیهانی تەکنەلۆژیا و داهاتوو تەنها و تەنها بنووسە IGNORE
٢ ئەگەر هەواڵەکە شایەنی بڵاوکردنەوە بوو تەواوی بابەتەکە بە زمانێکی کوردیی سۆرانیی پاراو فەرمی زانستی و زۆر ڕێکوپێک دابڕێژەرەوە بەبێ زیاد و کەمی زانیارییەکان

یاساکانی داڕشتن و ڕێنووس زۆر گرنگە بە توندی پەیڕەویان بکە:
- بە هیچ جۆرێک هیچ نیشانەیەکی خاڵبەندی بەکارمەهێنە وەک خاڵ فاریزە سەرسوڕمان پرسیار دووخاڵ کەوانە بەڵکو با ڕستەکان لە ڕێگەی ئامرازەکانی بەستنەوە بە شێوەیەکی سروشتی پێکەوە ببەسترێنەوە
- ڕێنووسی دروستی کوردی پەیڕەو بکە وەک بەکارهێنانی پیتی قەڵەو و جیاکردنەوەی پیتە بزوێنەکان
- ناوە بیانی و تەکنیکییە ناسراوەکان وەک ئەپڵ گووگڵ مێتا جێمینای مایکرۆسۆفت یان زاراوە ناسراوەکانی وەک کلەود و ئەلگۆریتم بە شێوازی باوی کوردی یان ناوی ڕەسەنی خۆیان بنووسە
- دەقەکە پێویستە جەوهەری تەواوی ڕووداوەکە لەخۆ بگرێت بەبێ کورتکردنەوەی زیاد لە پێویست کە ماناکەی بشێوێنێت و بەبێ درێژدادڕی

فۆرماتی وەڵامدانەوە بە تەواوی بەم شێوازە دەبێت:

سەردێڕ
[لێرەدا سەردێڕێکی هەواڵیی بەهێز ڕوون سەرنجڕاکێش و پوخت بنووسە بێ خاڵبەندی]

دەقی هەواڵ
[لێرەدا ناوەڕۆکی هەواڵەکە بە تەواوی و بە داڕشتنێکی یەکگرتووی زانستی و هاوشێوەی ژووری هەواڵ بنووسە بێ بەکارهێنانی خاڵبەندی]

🔗 سەرچاوە {link}

دەقی خاوی هەواڵەکە بۆ شیکردنەوە و داڕشتنەوە:
{content}
"""

                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                )

                result_text = response.text.strip()

                if "IGNORE" in result_text or len(result_text) < 20:
                    print(f"Skipped low-priority story: {title}")
                    continue

                telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": result_text,
                    "disable_web_page_preview": False
                }
                res = requests.post(telegram_url, json=payload)
                print(f"Sent to Telegram: {title} (Status: {res.status_code})")

                time.sleep(5)

        except Exception as e:
            print(f"Error processing {feed_url}: {e}")

if __name__ == "__main__":
    run()
