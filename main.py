import os
import re
import json
import time
import html
import calendar
from datetime import datetime, timedelta, timezone
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

# مۆدێلەکان بەپێی ئەولەویەت، ئەگەر یەکەمیان کار نەکرد یان quotaی تەواو بوو دووەمیان تاقی دەکاتەوە
# (quotaی بەخۆڕایی بۆ هەر مۆدێلێک جیاوازە)
GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-flash-latest",
]

MAX_AGE_HOURS = 24           # تەنها هەواڵی ٢٤ کاتژمێری ڕابردوو
MAX_PER_FEED = 8             # چەند هەواڵی نوێ لە هەر سایتێک دەپشکنرێت
MAX_STORIES_PER_RUN = 5      # زۆرترین هەواڵ کە لە هەر run دەنێردرێت
SEEN_FILE = "seen.json"
SEEN_LIMIT = 1000

# ئەم وشانە لە سەردێڕدا بن، هەواڵەکە بێ بانگکردنی Gemini پشتگوێ دەخرێت
SKIP_KEYWORDS = ["promo code", "coupon", "% off", "discount code", "deals", "prime day"]


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen[-SEEN_LIMIT:], f, ensure_ascii=False, indent=2)


class AllModelsFailed(Exception):
    pass


_working_model_index = 0


def generate_text(client, prompt):
    """مۆدێلەکان بە ڕیز تاقی دەکاتەوە، و بۆ هەڵەی 503 چەند جارێک دووبارە هەوڵ دەدات"""
    global _working_model_index
    errors = {}
    for i in range(_working_model_index, len(GEMINI_MODELS)):
        model = GEMINI_MODELS[i]
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                _working_model_index = i
                return (response.text or "").strip()
            except Exception as e:
                msg = str(e)
                errors[model] = msg[:160]
                print(f"Model {model} failed (attempt {attempt + 1}): {msg[:200]}")
                if "503" in msg or "UNAVAILABLE" in msg:
                    time.sleep(15)   # داواکاری زۆرە، کەمێک چاوەڕێ دەکەین
                    continue
                break                # 404 / 429 ... دەچینە مۆدێلی دواتر
    summary = "\n\n".join(f"{m}: {err}" for m, err in errors.items())
    raise AllModelsFailed(summary)


def send_alert(text, seen, seen_set):
    """ئاگادارکردنەوە بۆ تیلیگرام، تەنها یەکجار لە ڕۆژێکدا"""
    key = f"ALERT:{datetime.now(timezone.utc).date()}"
    if key in seen_set:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text[:3900]},
            timeout=30,
        )
        seen.append(key)
        seen_set.add(key)
    except Exception as e:
        print(f"Could not send alert: {e}")


def clean_text(text, limit=300):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


STOP_WORDS = set(
    "the and for with from that this have has had are was were will can could how why what who "
    "its new says said after over into about than more your you out not but all".split()
)


def title_tokens(title):
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}


def is_similar(a, b):
    """پشکنینی خێرای هاوشێوەیی سەردێڕەکان (تەنها وەک پاراستنی زیادە)"""
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return False
    common = len(ta & tb)
    return common >= 3 and common / min(len(ta), len(tb)) >= 0.4


def recent_sent_titles(seen, n=40):
    titles = [x[6:] for x in seen if x.startswith("TITLE:")]
    return titles[-n:]


def build_prompt(candidates, previous_titles):
    items = []
    for n, c in enumerate(candidates, start=1):
        items.append(f"[{n}] Title: {c['title']}\nSummary: {c['summary']}")
    items_text = "\n\n".join(items)

    if previous_titles:
        previous_text = "\n".join(f"- {t}" for t in previous_titles)
        previous_block = f"\nهەواڵە نێردراوەکانی پێشوو ئەمانەن و هیچ هەواڵێکی هاوشێوەیان هەڵمەبژێرە\n{previous_text}\n"
    else:
        previous_block = ""

    return f"""
تۆ سەرنووسەر و ڕۆژنامەنووسێکی باڵای بواری تەکنەلۆژیایت و شارەزاییەکی قووڵت لە داڕشتنی هەواڵی زانستی بە زمانی کوردیی سۆرانی هەیە

لە خوارەوە لیستی هەواڵە نوێیەکان هەیە و هەر یەکەیان ژمارەیەکی هەیە

ئەرکی سەرەکی:
١ هەموو هەواڵەکان هەڵبسەنگێنە و تەنها باشترین و گرنگترین هەواڵەکان هەڵبژێرە بە زۆرترین {MAX_STORIES_PER_RUN} هەواڵ
ئەو هەواڵانە پشتگوێ بخە کە ڕیکلام یان کۆپۆن یان ڕیڤیۆی بچووک یان گۆڕانکاری بێبایەخن یان پەیوەندییان بە جیهانی تەکنەلۆژیاوە نییە
ئەگەر چەند هەواڵێک لە سایتی جیاوازەوە باسی هەمان ڕووداو یان هەمان بابەت دەکەن تەنها یەکێکیان هەڵبژێرە کە تەواوترین زانیاری تێدایە و هەرگیز دووبارەی مەکەرەوە
ئەو هەواڵانەش هەڵمەبژێرە کە هەمان ڕووداوی هەواڵە نێردراوەکانی پێشوون
ئەگەر هیچ هەواڵێک شایەنی بڵاوکردنەوە نەبوو تەنها و تەنها بنووسە IGNORE
٢ هەر هەواڵێکی هەڵبژێردراو بە زمانێکی کوردیی سۆرانیی پاراو فەرمی زانستی و زۆر ڕێکوپێک دابڕێژەرەوە بەبێ زیاد و کەمی زانیارییەکان

یاساکانی داڕشتن و ڕێنووس زۆر گرنگە بە توندی پەیڕەویان بکە:
-هەوالەکە زۆر کورت نەبێ لە دارشتنی هەوالەکە هەروەها زۆر دڕێژ نەبێ 
- بە هیچ جۆرێک هیچ نیشانەیەکی خاڵبەندی بەکارمەهێنە وەک خاڵ فاریزە سەرسوڕمان پرسیار دووخاڵ کەوانە بەڵکو با ڕستەکان لە ڕێگەی ئامرازەکانی بەستنەوە بە شێوەیەکی سروشتی پێکەوە ببەسترێنەوە
- ڕێنووسی دروستی کوردی پەیڕەو بکە وەک بەکارهێنانی پیتی قەڵەو و جیاکردنەوەی پیتە بزوێنەکان
- ناوە بیانی و تەکنیکییە ناسراوەکان وەک ئەپڵ گووگڵ مێتا جێمینای مایکرۆسۆفت یان زاراوە ناسراوەکانی وەک کلەود و ئەلگۆریتم بە شێوازی باوی کوردی یان ناوی ڕەسەنی خۆیان بنووسە
- دەقەکە پێویستە جەوهەری تەواوی ڕووداوەکە لەخۆ بگرێت بەبێ کورتکردنەوەی زیاد لە پێویست کە ماناکەی بشێوێنێت و بەبێ درێژدادڕی
- لینکی سەرچاوە مەنووسە چونکە خۆکارانە زیاد دەکرێت

فۆرماتی وەڵامدانەوە بە تەواوی بەم شێوازە دەبێت و بۆ هەر هەواڵێکی هەڵبژێردراو دووبارەی بکەرەوە
دێڕی یەکەم هەمیشە ###ITEM بێت لەگەڵ ژمارەی هەواڵەکە بە ژمارەی ئینگلیزی وەک ###ITEM 3

###ITEM [ژمارەی هەواڵەکە]
سەردێڕ
[لێرەدا سەردێڕێکی هەواڵیی بەهێز ڕوون سەرنجڕاکێش و پوخت بنووسە بێ خاڵبەندی]

دەقی هەواڵ
[لێرەدا ناوەڕۆکی هەواڵەکە بە تەواوی و بە داڕشتنێکی یەکگرتووی زانستی و هاوشێوەی ژووری هەواڵ بنووسە بێ بەکارهێنانی خاڵبەندی]

{previous_block}
لیستی هەواڵەکان:

{items_text}
"""


def parse_stories(result_text, count):
    """وەڵامی Gemini دەکاتە لیستی (ژمارە، دەق)"""
    parts = re.split(r"###ITEM\s+(\d+)", result_text)
    stories = []
    # parts = [پێش یەکەم، id1، دەق1، id2، دەق2، ...]
    for k in range(1, len(parts) - 1, 2):
        idx = int(parts[k])
        body = parts[k + 1].strip()
        if 1 <= idx <= count and len(body) >= 20:
            stories.append((idx - 1, body))
    return stories


def run():
    print("Checking environment variables...")
    if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Missing secrets!")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)

    seen = load_seen()
    seen_set = set(seen)

    # ---------- ١. کۆکردنەوەی هەواڵە نوێیەکان (بێ بانگکردنی Gemini) ----------
    candidates = []
    for feed_url in RSS_FEEDS:
        print(f"Fetching feed: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                print("No entries found in this feed")
                continue

            taken = 0
            for entry in feed.entries:
                if taken >= MAX_PER_FEED:
                    break

                title = html.unescape(entry.get("title", "")).strip()
                link = entry.get("link", "")
                if not link or not title or link in seen_set:
                    continue

                published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_parsed:
                    published = datetime.fromtimestamp(
                        calendar.timegm(published_parsed), tz=timezone.utc
                    )
                    if published < cutoff:
                        print(f"Skipped old story ({published.date()}): {title}")
                        continue

                if any(k in title.lower() for k in SKIP_KEYWORDS):
                    print(f"Skipped promo story: {title}")
                    seen.append(link)
                    seen_set.add(link)
                    continue

                candidates.append({
                    "title": title,
                    "summary": clean_text(entry.get("summary", "")),
                    "link": link,
                })
                taken += 1
        except Exception as e:
            print(f"Error reading {feed_url}: {e}")

    print(f"New candidate stories: {len(candidates)}")

    if not candidates:
        save_seen(seen)
        print("Done.")
        return

    # ---------- ٢. تەنها یەک بانگ بۆ Gemini بۆ هەموو هەواڵەکان ----------
    try:
        previous_titles = recent_sent_titles(seen)
        result_text = generate_text(client, build_prompt(candidates, previous_titles))
    except AllModelsFailed as e:
        print(f"ALL GEMINI MODELS FAILED: {e}")
        send_alert(
            "⚠️ بۆتی هەواڵە تەکنەلۆژییەکان وەستاوە\n\n"
            "هیچ یەکێک لە مۆدێلەکانی Gemini کاری نەکرد\n"
            "ڕەنگە quotaی ڕۆژانە تەواو بووبێت یان ناوی مۆدێلەکان گۆڕابێت\n"
            "لیستی GEMINI_MODELS لە main.py بپشکنە\n\n"
            f"هەڵەی هەر مۆدێلێک:\n{str(e)[:1500]}",
            seen,
            seen_set,
        )
        save_seen(seen)
        print("Done.")
        return

    stories = parse_stories(result_text, len(candidates))

    # پاراستنی زیادە: هەواڵی هاوشێوە لەنێو ئەم run یان لەگەڵ نێردراوەکانی پێشوو لادەبرێت
    unique_stories = []
    accepted_titles = list(previous_titles)
    for idx, body in stories:
        title = candidates[idx]["title"]
        if any(is_similar(title, t) for t in accepted_titles):
            print(f"Skipped duplicate story: {title}")
            continue
        accepted_titles.append(title)
        unique_stories.append((idx, body))
    stories = unique_stories

    if not stories:
        if result_text.upper().startswith("IGNORE") or "###ITEM" in result_text:
            print("Gemini: no story worth publishing")
            for c in candidates:
                seen.append(c["link"])
                seen_set.add(c["link"])
        else:
            print("WARNING: could not parse Gemini output, will retry next run")
            print(result_text[:300])
        save_seen(seen)
        print("Done.")
        return

    # هەواڵە هەڵنەبژێردراوەکان تۆمار دەکرێن بۆ ئەوەی دووبارە نەپشکنرێنەوە
    selected_idx = {idx for idx, _ in stories}
    for i, c in enumerate(candidates):
        if i not in selected_idx:
            seen.append(c["link"])
            seen_set.add(c["link"])

    # ---------- ٣. ناردن بۆ تیلیگرام ----------
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for idx, body in stories[:MAX_STORIES_PER_RUN]:
        c = candidates[idx]
        text = f"{body}\n\n🔗 سەرچاوە {c['link']}"
        if len(text) > 4000:
            text = text[:3990] + "..."
        try:
            res = requests.post(
                telegram_url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "disable_web_page_preview": False,
                },
                timeout=30,
            )
            if res.ok:
                print(f"Sent to Telegram: {c['title']} (Status: {res.status_code})")
                seen.append(c["link"])
                seen_set.add(c["link"])
                seen.append("TITLE:" + c["title"])
            else:
                print(f"TELEGRAM ERROR {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Telegram request failed: {e}")
        time.sleep(3)

    save_seen(seen)
    print("Done.")


if __name__ == "__main__":
    run()
