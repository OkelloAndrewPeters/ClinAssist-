"""
app.py — Flask API server for ClinAssist Uganda

Endpoints:
    GET  /                        → serve index.html
    POST /api/analyse             → symptom analysis (RAG)
    POST /api/drug                → drug reference query
    GET  /api/health              → system health check
    GET  /api/stats               → knowledge base stats
    POST /api/ingest              → trigger PDF ingestion (admin)
"""

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from engine   import analyse_symptoms, query_drug, check_llm_health
from database import collection_stats, collection_is_empty

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")
CORS(app)  # allow requests from the frontend dev server if needed

STATIC_DIR = Path(__file__).parent / "static"


# ── Static ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)


# ── Symptom Analysis ───────────────────────────────────────────────────────────

@app.route("/api/analyse", methods=["POST"])
def analyse():
    """
    POST /api/analyse
    Body: { symptoms, age_group, duration, setting }
    Returns: structured clinical assessment JSON
    """
    data = request.get_json(silent=True) or {}

    symptoms  = (data.get("symptoms")  or "").strip()
    age_group = (data.get("age_group") or "Adult (18+)").strip()
    duration  = (data.get("duration")  or "1–3 days").strip()
    setting   = (data.get("setting")   or "Outpatient").strip()

    if not symptoms:
        return jsonify({"error": "symptoms field is required"}), 400

    logger.info(f"Analysis request | age={age_group} | duration={duration} | symptoms={symptoms[:80]}")

    result = analyse_symptoms(
        symptoms=symptoms,
        age_group=age_group,
        duration=duration,
        setting=setting,
    )

    if "error" in result and len(result) == 1:
        return jsonify(result), 500

    return jsonify(result)


# ── Drug Reference ─────────────────────────────────────────────────────────────

@app.route("/api/drug", methods=["POST"])
def drug():
    """
    POST /api/drug
    Body: { query }
    Returns: structured drug reference JSON
    """
    data  = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()

    if not query:
        return jsonify({"error": "query field is required"}), 400

    logger.info(f"Drug query: {query}")
    result = query_drug(query)

    if "error" in result and len(result) == 1:
        return jsonify(result), 500

    return jsonify(result)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    """GET /api/health — system status."""
    llm   = check_llm_health()
    stats = collection_stats()

    return jsonify({
        "status": "ok",
        "llm": llm,
        "knowledge_base": {
            "loaded":       not collection_is_empty(),
            "total_chunks": stats["total_chunks"],
            "documents":    len(stats["documents"]),
        },
    })


# ── Stats ──────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    """GET /api/stats — knowledge base breakdown."""
    return jsonify(collection_stats())


# ── Ingestion trigger (admin) ──────────────────────────────────────────────────

@app.route("/api/ingest", methods=["POST"])
def ingest():
    """
    POST /api/ingest
    Body: { reset: bool } (optional)
    Triggers PDF ingestion in the background.
    Note: for production, move this to a Celery task.
    """
    import threading
    from knowledge_base import ingest_all, DOCS_DIR
    from database import delete_collection

    data  = request.get_json(silent=True) or {}
    reset = bool(data.get("reset", False))

    def _run():
        if reset:
            logger.warning("Resetting knowledge base...")
            delete_collection()
        ingest_all(DOCS_DIR)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        "status": "ingestion started",
        "reset": reset,
        "message": "Check /api/stats in a few minutes to see progress.",
    })


# ── Dev helper: example request ────────────────────────────────────────────────

@app.route("/api/example")
def example():
    """GET /api/example — returns a sample request payload."""
    return jsonify({
        "endpoint": "POST /api/analyse",
        "body": {
            "symptoms":  "fever for 3 days, severe headache, chills, joint pain, vomiting",
            "age_group": "Adult (18+)",
            "duration":  "1–3 days",
            "setting":   "Outpatient",
        },
    })


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    logger.info("=" * 55)
    logger.info("  ClinAssist Uganda — Clinical Decision Support")
    logger.info("=" * 55)
    logger.info(f"  Server  : http://localhost:{port}")
    logger.info(f"  Debug   : {debug}")
    logger.info(f"  Static  : {STATIC_DIR}")

    stats = collection_stats()
    if stats["total_chunks"] == 0:
        logger.warning("  KB      : EMPTY — run python knowledge_base.py first")
    else:
        logger.info(f"  KB      : {stats['total_chunks']} chunks from {len(stats['documents'])} docs")

    logger.info("=" * 55)

    app.run(host="0.0.0.0", port=port, debug=debug)