"""Локальный веб-интерфейс: python app.py → http://127.0.0.1:5000"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from textnavigator.pipeline import analyze

STATIC = Path(__file__).resolve().parent / "static"
MAX_FILES, MAX_BYTES = 50, 2 * 1024 * 1024

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILES * MAX_BYTES


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(STATIC, name)


@app.post("/api/analyze")
def api_analyze():
    """multipart: files[] (TXT), check_date (ГГГГ-ММ-ДД). Сервер ничего не хранит."""
    uploads = request.files.getlist("files")
    if not uploads:
        return jsonify(error="Не выбраны файлы"), 400
    if len(uploads) > MAX_FILES:
        return jsonify(error=f"Не больше {MAX_FILES} файлов за раз"), 400
    try:
        check = date.fromisoformat(request.form.get("check_date", "2026-03-10"))
    except ValueError:
        return jsonify(error="Дата проверки должна быть в формате ГГГГ-ММ-ДД"), 400

    files = []
    for f in uploads:
        if not f.filename.lower().endswith(".txt"):
            return jsonify(error=f"{f.filename}: поддерживаются только TXT"), 400
        files.append((Path(f.filename).name, f.read()))
    try:
        return jsonify(analyze(files, check))
    except ValueError as e:
        return jsonify(error=str(e)), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
