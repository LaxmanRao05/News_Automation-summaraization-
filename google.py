
import json
import csv
import re
import time
import calendar
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
import feedparser
from bs4 import BeautifulSoup


# Publisher RSS feeds
RSS_SOURCES = {
    "KDnuggets": "https://www.kdnuggets.com/feed/",
    "Towards Data Science": "https://towardsdatascience.com/feed/",
    "Analytics Vidhya": "https://www.analyticsvidhya.com/feed/"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 NewsDiscoveryProject/1.0"
}


# Clean HTML content
def clean_html(html):
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return " ".join(soup.get_text(" ", strip=True).split())


# Get publication date
def get_date(entry):
    date = entry.get("published_parsed") or entry.get("updated_parsed")

    if not date:
        return None

    try:
        return datetime.fromtimestamp(
            calendar.timegm(date), timezone.utc
        )
    except (ValueError, OverflowError, OSError):
        return None


# Extract article text from public webpages
def extract_article(url, excerpt):
    try:
        response = requests.get(
            url, headers=HEADERS, timeout=15
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup([
            "script", "style", "nav", "footer",
            "header", "aside", "noscript"
        ]):
            tag.decompose()

        containers = soup.find_all(["article", "main"])
        paragraphs = []

        for container in containers:
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in container.find_all("p")
                if len(p.get_text(" ", strip=True)) > 40
            ]

            if sum(map(len, paragraphs)) >= 300:
                break
            paragraphs = []

        if not paragraphs:
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(" ", strip=True)) > 40
            ]

        text = re.sub(r"\s+", " ", " ".join(paragraphs)).strip()

        if len(text) >= 300:
            return text, "article_text"

    except requests.RequestException as error:
        print("Article extraction failed:", error)

    excerpt = clean_html(excerpt)

    if len(excerpt) > 50:
        return excerpt, "rss_excerpt"

    return "", "headline_only"


# Check topic relevance
def is_relevant(title, text, topic):
    words = [
        word.lower()
        for word in re.findall(r"[a-zA-Z0-9]+", topic)
        if len(word) > 2
    ]

    if not words:
        return True

    content = (title + " " + text).lower()
    matches = sum(
        1 for word in set(words)
        if re.search(r"\b" + re.escape(word) + r"\b", content)
    )

    return matches >= max(1, (len(set(words)) + 1) // 2)


# Generate a short extractive summary
def make_summary(text, max_sentences=3):
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 120:
        return "Insufficient article content for a reliable summary."

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        return "No complete sentences available."

    return " ".join(sentences[:max_sentences])


# Collect articles from one publisher
def fetch_from_source(source, feed_url, topic):
    articles = []

    try:
        response = requests.get(
            feed_url, headers=HEADERS, timeout=15
        )
        response.raise_for_status()

        feed = feedparser.parse(response.content)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=7)

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            published = get_date(entry)

            if not title or not url or not published:
                continue

            if published < cutoff or published > now:
                continue

            excerpt = clean_html(
                entry.get("summary", "")
                or entry.get("description", "")
            )

            content, content_type = extract_article(url, excerpt)

            if not content:
                content = title

            if not is_relevant(title, content, topic):
                continue

            summary = (
                make_summary(content)
                if content_type != "headline_only"
                else "Only the headline was available."
            )

            articles.append({
                "title": title,
                "source": source,
                "url": url,
                "published_at": published.isoformat(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "content_type": content_type,
                "article_text": content,
                "summary": summary
            })

    except requests.RequestException as error:
        print(f"{source} feed error:", error)

    except Exception as error:
        print(f"{source} processing error:", error)

    print(f"{source}: {len(articles)} matching articles")
    return articles


# Collect, filter and remove duplicate articles
def fetch_news(topic, limit=5):
    if not topic.strip():
        print("Please enter a topic.")
        return []

    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    print("\nSearching publisher RSS feeds...")
    articles = []
    seen_urls = set()
    seen_titles = set()

    for source, feed_url in RSS_SOURCES.items():
        results = fetch_from_source(source, feed_url, topic)

        for article in results:
            url = article["url"].split("#")[0].rstrip("/").lower()
            title = re.sub(r"[^a-z0-9]", "", article["title"].lower())

            if url in seen_urls or title in seen_titles:
                continue

            seen_urls.add(url)
            seen_titles.add(title)
            articles.append(article)

        time.sleep(1)

    articles.sort(
        key=lambda item: item["published_at"],
        reverse=True
    )

    # Prefer different publishers
    selected = []
    used_publishers = set()

    for article in articles:
        if len(selected) >= limit:
            break

        if article["source"] not in used_publishers:
            selected.append(article)
            used_publishers.add(article["source"])

    for article in articles:
        if len(selected) >= limit:
            break

        if article not in selected:
            selected.append(article)

    print("\nArticles collected:", len(selected))
    print("Different publishers:", len({
        a["source"] for a in selected
    }))

    if len(selected) < limit:
        print("Fewer matching articles were available.")

    return selected


# Save results as JSON, CSV and Markdown
def save_outputs(topic, articles):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = re.sub(r"[^a-zA-Z0-9_-]", "_", topic)

    folder = Path("output")
    folder.mkdir(parents=True, exist_ok=True)

    json_file = folder / f"{safe_topic}_{timestamp}.json"
    csv_file = folder / f"{safe_topic}_{timestamp}.csv"
    md_file = folder / f"{safe_topic}_{timestamp}.md"

    data = {
        "topic": topic,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(articles),
        "publishers": sorted({a["source"] for a in articles}),
        "articles": articles
    }

    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    fields = [
        "title", "source", "url", "published_at",
        "retrieved_at", "content_type", "article_text", "summary"
    ]

    with open(csv_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(articles)

    with open(md_file, "w", encoding="utf-8") as file:
        file.write(f"# News Digest: {topic}\n\n")
        file.write(f"Total articles: {len(articles)}\n\n")

        for i, article in enumerate(articles, 1):
            file.write(f"## {i}. {article['title']}\n\n")
            file.write(f"**Publisher:** {article['source']}  \n")
            file.write(f"**Published:** {article['published_at']}  \n")
            file.write(f"**Content type:** {article['content_type']}  \n")
            file.write(f"**Summary:** {article['summary']}\n\n")
            file.write(f"**Article link:** {article['url']}\n\n")
            file.write("---\n\n")

    return {
        "json": json_file.name,
        "csv": csv_file.name,
        "markdown": md_file.name
    }


# Run program from terminal
if __name__ == "__main__":
    print("AUTOMATED NEWS DISCOVERY SYSTEM")

    topic = input("Enter news topic: ").strip()

    try:
        limit = int(input("Maximum number of articles (1-50): "))

        if not 1 <= limit <= 50:
            raise ValueError

    except ValueError:
        print("Enter a valid limit between 1 and 50.")
        raise SystemExit

    articles = fetch_news(topic, limit)

    print("\n========== NEWS REPORT ==========")

    for i, article in enumerate(articles, 1):
        print(f"\nARTICLE {i}")
        print("Title:", article["title"])
        print("Publisher:", article["source"])
        print("Published:", article["published_at"])
        print("Content type:", article["content_type"])
        print("Summary:", article["summary"])
        print("Link:", article["url"])

    files = save_outputs(topic, articles)

    print("\nOutput files generated successfully:")
    print(files)
