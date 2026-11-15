
from flask import Flask, jsonify, request, send_from_directory, send_file
from datetime import datetime, timezone
from pathlib import Path

from google import fetch_news, save_outputs

app = Flask(__name__, static_folder="static")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


@app.route("/")
def home():
    return send_from_directory(".", "news_digest.html")


@app.route("/api/search", methods=["POST"])
def search_news():

    data = request.get_json(silent=True) or {}

    topic = str(data.get("topic", "")).strip()

    try:
        limit = int(data.get("limit", 5))
    except (ValueError, TypeError):
        return jsonify({"error": "Enter a valid article limit."}), 400

    if not topic:
        return jsonify({"error": "Please enter a topic."}), 400

    if limit < 1 or limit > 50:
        return jsonify({"error": "Limit must be between 1 and 50."}), 400

    try:
        articles = fetch_news(topic, limit)

        files = save_outputs(topic, articles)

        publishers = list(set(
            article.get("source", "Unknown")
            for article in articles
        ))

        return jsonify({
            "topic": topic,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "total_articles": len(articles),
            "distinct_publishers": len(publishers),
            "articles": articles,
            "files": files
        })

    except Exception:
        app.logger.exception("News search failed")
        return jsonify({
            "error": "Unable to complete news search. Check the terminal."
        }), 500


@app.route("/download/<filename>")
def download_file(filename):

    allowed_files = {"news.json", "news.csv", "news.md"}

    if filename not in allowed_files:
        return jsonify({"error": "Invalid file."}), 404

    file_path = OUTPUT_DIR / filename

    if not file_path.exists():
        return jsonify({"error": "File not found."}), 404

    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
