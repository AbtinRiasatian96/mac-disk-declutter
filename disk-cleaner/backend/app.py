"""Flask server for disk-cleaner."""

import asyncio
from flask import Flask, request, jsonify, send_from_directory
from backend.config import load_config, save_config
from backend.scanner import scan_all
from backend.analyzer import get_provider, analyze_items, build_scan_summary
from backend.cleaner import delete_items
from backend.llm.base import ChatMessage

app = Flask(__name__, static_folder="../frontend", static_url_path="")

# In-memory state
scan_results: list[dict] = []
chat_history: list[dict] = []


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    global scan_results
    config = load_config()
    data = request.json or {}
    deep = data.get("deep", False)
    items = scan_all(config, deep=deep)

    # Try LLM analysis; fall back to heuristic scores if unavailable
    try:
        provider = get_provider(config)
        loop = asyncio.new_event_loop()
        items = loop.run_until_complete(analyze_items(items, provider))
        loop.close()
    except Exception as e:
        # Assign heuristic scores based on category
        defaults = {"safe": 90, "review": 60, "personal": 30}
        descs = {
            "safe": "Cache/log data that can be safely regenerated.",
            "review": "May be useful; review before deleting.",
            "personal": "Personal files — use your judgment.",
        }
        for item in items:
            cat = item.get("category", "review")
            item.setdefault("safety_score", defaults.get(cat, 50))
            item.setdefault("description", descs.get(cat, ""))
            item.setdefault("consequence", "Review manually if unsure.")

    scan_results = items
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/delete", methods=["POST"])
def api_delete():
    global scan_results
    data = request.json
    paths = data.get("paths", [])
    method = data.get("method", "trash")
    if not paths:
        return jsonify({"error": "No paths provided"}), 400
    if method not in ("trash", "permanent"):
        return jsonify({"error": "Invalid method"}), 400

    results = delete_items(paths, method)
    # Remove deleted items from scan results
    deleted_set = set(results["success"])
    scan_results = [i for i in scan_results if i["path"] not in deleted_set]
    return jsonify(results)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    chat_history.append({"role": "user", "content": message})
    config = load_config()

    context = {
        "scan_summary": build_scan_summary(scan_results),
        "selected_items": data.get("selected_items", []),
    }

    try:
        provider = get_provider(config)
        messages = [ChatMessage(role=m["role"], content=m["content"]) for m in chat_history]
        loop = asyncio.new_event_loop()
        reply = loop.run_until_complete(provider.chat(messages, context))
        loop.close()
    except Exception as e:
        reply = f"LLM unavailable: {e}. Check your settings."

    chat_history.append({"role": "assistant", "content": reply})
    return jsonify({"reply": reply, "history": chat_history})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    config = load_config()
    # Don't expose full API key
    safe_config = {**config}
    key = safe_config.get("claude_api_key", "")
    if key:
        safe_config["claude_api_key"] = key[:8] + "..." if len(key) > 8 else "***"
    safe_config["claude_api_key_set"] = bool(key)
    return jsonify(safe_config)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json
    config = load_config()
    for key in ("llm_provider", "claude_api_key", "claude_model", "ollama_model", "ollama_url"):
        if key in data and data[key]:
            config[key] = data[key]
    save_config(config)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("Starting Disk Cleaner at http://localhost:5192")
    app.run(host="127.0.0.1", port=5192, debug=True)
