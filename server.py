from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

RESET_KEY = "changeme123"

LATEST = None
HISTORY = []

def parse_payload_text(text: str) -> dict:
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
        pass

    data["payload_parts"] = parts
    return data


@app.route("/rockblock", methods=["POST"])
def rockblock_in():
    global LATEST, HISTORY

    # Robustly read either JSON or form POST
    if request.is_json:
        payload = request.get_json(silent=True) or {}
    else:
        payload = request.form.to_dict()  # plain dict

    imei = payload.get("imei")
    momsn = payload.get("momsn")
    tx_time = payload.get("transmit_time")
    ir_lat = payload.get("iridium_latitude")
    ir_lon = payload.get("iridium_longitude")
    ir_cep = payload.get("iridium_cep")
    data_hex = payload.get("data") or ""

    msg = {
        "received_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "imei": imei,
        "momsn": momsn,
        "transmit_time": tx_time,
        "iridium_latitude": ir_lat,
        "iridium_longitude": ir_lon,
        "iridium_cep": ir_cep,
        "data_hex": data_hex,
    }

    # Decode hex payload to bytes/text
    text = None
    if data_hex:
        try:
            clean_hex = data_hex.replace(" ", "").strip()
            data_bytes = bytes.fromhex(clean_hex)
            text = data_bytes.decode("utf-8", errors="replace")
            msg["data_bytes_len"] = len(data_bytes)
        except Exception as e:
            msg["decode_error"] = str(e)

    msg["data_text"] = text

    if text:
        msg.update(parse_payload_text(text))

    HISTORY.append(msg)
    LATEST = msg

    return "OK", 200
