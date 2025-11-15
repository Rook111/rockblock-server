from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

LATEST = None
HISTORY = []  # in-memory; later you can switch to a file/DB


def parse_payload_text(text: str) -> dict:
    """
    Adjust this later to match your payload.
    For now, assume: 'lat,lon,alt,...'
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
        # not numeric? just ignore for now
        pass

    data["payload_parts"] = parts
    return data


@app.route("/", methods=["GET"])
def index():
    return "RockBLOCK ground station backend is alive.", 200


@app.route("/rockblock", methods=["POST"])
def rockblock_in():
    """
    This is what RockBLOCK will POST to.
    Expected fields (form data):
      imei, momsn, transmit_time, iridium_latitude, iridium_longitude,
      iridium_cep, data (hex)
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

    # hex -> text
    text = None
    if data_hex:
        try:
            data_bytes = bytes.fromhex(data_hex)
            text = data_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = None

    msg["data_text"] = text

    # parse your own GPS/data from the text
    if text:
        msg.update(parse_payload_text(text))

    HISTORY.append(msg)
    LATEST = msg

    return "OK", 200


@app.route("/api/latest", methods=["GET"])
def api_latest():
    if not LATEST:
        return jsonify({"error": "no data yet"}), 404
    return jsonify(LATEST)


@app.route("/api/history", methods=["GET"])
def api_history():
    # last 100 messages
    return jsonify(HISTORY[-100:])


if __name__ == "__main__":
    # local testing only
    app.run(host="0.0.0.0", port=5000)
