import os
import time
import feedparser
import requests
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# لیستی ئارەزوومەندانەی سایتەکان (دەتوانیت گۆڕانکاری لەم لیستەدا بکەیت)
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.cnet.com/rss/news/",
    "https://arstechnica.com/feed/",              # Ars Technica
    "https://www.engadget.com/rss.xml",           # Engadget
    "https://9to5mac.com/feed/",                  # 9to5Mac (ئەپڵ و تەکنەلۆژیا)
    "https://androidcentral.com/feed",            # Android Central
    "https://www.tomshardware.com/feeds/all"      # Tom's Hardware (هاردوێر و کۆمپیوتەر)
    
]

def run():
    print("Checking environment variables...")
    if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Missing secrets!")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)

    for feed_url in RSS_FEEDS:
        print(f"Fetching feed: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                print(f"No entries found for {feed_url}")
                continue
            
            # وەرگرتنی تەنها ٢ هەواڵی یەکەمی هەر سایتێک بۆ ئەوەی ڕێژەی API نەبەزێنێت
            top_entries = feed.entries[:2]

            for entry in top_entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")

                print(f"Processing story: {title}")
                content = f"Title: {title}\nSummary: {summary}\nLink: {link}"

                prompt = f"""
تۆ ڕۆژنامەنووسێکی پیشەگەری باری تەکنەلۆژیایت.

ئەم هەواڵە تەکنەلۆژیایە بە زمانی کوردی سۆرانی، بە شێوازی ئەکادیمی و ڕۆژنامەوانی زانستی و بێ خاڵبەندی دایبڕێژەرەوە.

شێوازی داڕشتن:
- سەردێڕێکی بەهێز
- ناوەڕۆک بە بڕگەی ڕێک و پوخت و بێ وشەی زیادە
- لە کۆتاییدا: لینک: {link}

دەقی هەواڵەکە:
{content}
"""

                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                )

                result_text = response.text.strip()

                telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": result_text,
                    "disable_web_page_preview": False
                }
                res = requests.post(telegram_url, json=payload)
                print(f"Telegram response code: {res.status_code}")

                # وەستان بۆ ماوەی ٥ چڕکە لە نێوان هەر هەواڵێکدا بۆ ڕێگریکردن لە هەڵەی Quota Exceeded
                time.sleep(5)

        except Exception as e:
            print(f"Error processing {feed_url}: {e}")

if __name__ == "__main__":
    run()
