import os
import feedparser
import requests
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

RSS_FEEDS = [
    "https://techcrunch.com/category/technology/feed/",
    "https://www.cnet.com/rss/technology/",
    "http://rss.cnn.com/rss/edition_technology.rss",
    "https://www.theverge.com/rss/index.xml"
]

def run():
    if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("کێشە لە شاردنەوەی کلیلەکاندا هەیە (Secrets setup error)!")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                continue
            
            top_entries = feed.entries[:5]

            for entry in top_entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")

                content = f"Title: {title}\nSummary: {summary}\nLink: {link}"

                prompt = f"""
تۆ ڕۆژنامەنووسێکی پیشەگەری باری تەکنەلۆژیایت.

ئەرکی تۆ:
١. سەرەتا هەڵسەنگاندن بۆ ئەم هەواڵە بکە: ئەگەر هەواڵەکە زۆر گرنگ و سەرنجڕاکێش نییە، تەنها بڵێ: IGNORE
٢. ئەگەر هەواڵەکە گرنگ بوو، ڕاستەوخۆ بە زمانی کوردی سۆرانی، بە شێوازی ئەکادیمی و ڕۆژنامەوانی زانستی و بێ خاڵبەندی دایبڕێژەرەوە.

شێوازی داڕشتنی هەواڵە گرنگەکان:
- سەردێڕێکی بەهێز
- ناوەڕۆک بە بڕگەی ڕێک و پوخت و بێ وشەی زیادە
- لە کۆتاییدا: لینک: {link}

دەقی هەواڵەکە:
{content}
"""

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )

                result_text = response.text.strip()

                if "IGNORE" in result_text or len(result_text) < 20:
                    print(f"Skipped low-priority news: {title}")
                    continue

                telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": result_text,
                    "disable_web_page_preview": False
                }
                res = requests.post(telegram_url, json=payload)
                print(f"Telegram status: {res.status_code}")

        except Exception as e:
            print(f"Error processing {feed_url}: {e}")

if __name__ == "__main__":
    run()
