from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# CHANGE THIS to something secret (do NOT commit a real secret in a public repo in the future;
# but for now this is okay for testing)
RESET_KEY = "changeme123"

LATEST = None
HISTORY = []  # in-memory history; consider a DB/file later


def parse_payload_text(text: str) -> dict:
    """
    Adjust this to match your payload format.
    CURRENT ASSUMPTION: 'lat,lon,alt,...'
    Example: "35.1234,-82.9876,1500,25.3,101325,3.7"
    """
    data = {}
    if not text:
        return data

    parts = [p.strip() for p in text.split(",")]

    try:
        if len(parts) >= 2:
            data["gps_lat"] = float(parts[0])
            data["gps_lon"] = float(parts[1])
        if len(parts) >= 3:
            data["gps_alt"] = float(parts[2])
    except ValueError:
        # if not numeric, we just skip GPS parsing
        pass

    data["payload_parts"] = parts
    return data


@app.route("/", methods=["GET"])
def index():
    return "RockBLOCK ground station backend is alive.", 200


@app.route("/rockblock", methods=["POST"])
def rockblock_in():
    """
    RockBLOCK (Ground Control) will POST here.

    Expected form fields:
      imei, momsn, transmit_time, iridium_latitude, iridium_longitude,
      iridium_cep, data (hex-encoded payload)
    """
    global LATEST, HISTORY

    payload = request.form or request.json or {}

    imei = payload.get("imei")
    momsn = payload.get("momsn")
    tx_time = payload.get("transmit_time")
    ir_lat = payload.get("iridium_latitude")
    ir_lon = payload.get("iridium_longitude")
    ir_cep = payload.get("iridium_cep")
    data_hex = payload.get("data")

    msg = {
        "received_at": datetime.utcnow().isoformat() + "Z",
        "imei": imei,
        "momsn": momsn,
        "transmit_time": tx_time,
        "iridium_latitude": ir_lat,
        "iridium_longitude": ir_lon,
        "iridium_cep": ir_cep,
        "data_hex": data_hex,
    }

    # Decode hex payload to text
    text = None
    if data_hex:
        try:
            data_bytes = bytes.fromhex(data_hex)
            text = data_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = None

    msg["data_text"] = text

    # Parse GPS and other fields from the text payload
    if text:
        msg.update(parse_payload_text(text))

    HISTORY.append(msg)
    LATEST = msg

    # RockBLOCK wants HTTP 200 to consider the delivery successful
    return "OK", 200


@app.route("/api/latest", methods=["GET"])
def api_latest():
    """Return the latest message."""
    if not LATEST:
        return jsonify({"error": "no data yet"}), 404
    return jsonify(LATEST)


@app.route("/api/history", methods=["GET"])
def api_history():
    """Return the last 100 messages."""
    return jsonify(HISTORY[-100:])


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """
    Clear all in-memory data for a new flight.
    Requires ?key=RESET_KEY or form key=RESET_KEY
    """
    global LATEST, HISTORY

    key = request.args.get("key") or request.form.get("key")
    if key != RESET_KEY:
        return jsonify({"error": "forbidden"}), 403

    LATEST = None
    HISTORY = []
    return jsonify({
        "status": "reset",
        "time": datetime.utcnow().isoformat() + "Z"
    }), 200


if __name__ == "__main__":
    # Local testing
    app.run(host="0.0.0.0", port=5000)
