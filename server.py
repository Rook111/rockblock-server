#!/usr/bin/env python3
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

RESET_KEY = os.environ.get("RESET_KEY", "changeme123")

LATEST = None
HISTORY = []  # raw Rock7 messages + parsed fields
ROWS = []     # ground-station formatted rows (dicts)

# Ground-station columns (TAB-separated output uses this exact order)
GS_COLUMNS = [
    "timestamp_iso",
    "timestamp_unix_s",
    "env_temp_C",
    "env_hum_pct",
    "env_press_hPa",
    "gps_time_str",
    "gps_lat",
    "gps_lon",
    "gps_alt_m",
    "ori_roll_deg",
    "ori_pitch_deg",
    "ori_yaw_deg",
    "watch1_event",
    "watch1_ard_ms",
    "watch1_adc",
    "watch1_mv",
    "watch1_dead_ms",
    "watch1_temp_C",
    "watch2_event",
    "watch2_ard_ms",
    "watch2_adc",
    "watch2_mv",
    "watch2_dead_ms",
    "watch2_temp_C",
]


def _to_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _to_int(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return int(float(s))
    except Exception:
        return None


def parse_mini_payload(text: str) -> dict:
    """
    Incoming mini payload from your Pi:
      met_s,temp,hum,press,lat,lon,alt,roll,pitch,yaw,coinc

    IMPORTANT: In your logger, met_s is "mission elapsed time" (seconds since start),
    not a true UNIX timestamp. :contentReference[oaicite:0]{index=0}

    So we will:
      - store met_s as-is
      - use server receive time for timestamp_iso / timestamp_unix_s
    """
    out = {}
    if not text:
        return out

    parts = [p.strip() for p in text.split(",")]
    out["payload_parts"] = parts

    if len(parts) >= 1:  out["met_s"] = _to_float(parts[0])
    if len(parts) >= 2:  out["temp_C"] = _to_float(parts[1])
    if len(parts) >= 3:  out["hum_pct"] = _to_float(parts[2])
    if len(parts) >= 4:  out["press_hPa"] = _to_float(parts[3])
    if len(parts) >= 5:  out["lat"] = _to_float(parts[4])
    if len(parts) >= 6:  out["lon"] = _to_float(parts[5])
    if len(parts) >= 7:  out["alt_m"] = _to_float(parts[6])
    if len(parts) >= 8:  out["roll_deg"] = _to_float(parts[7])
    if len(parts) >= 9:  out["pitch_deg"] = _to_float(parts[8])
    if len(parts) >= 10: out["yaw_deg"] = _to_float(parts[9])
    if len(parts) >= 11: out["coinc"] = _to_int(parts[10])

    return out


def build_gs_row(parsed: dict, received_dt_utc: datetime) -> dict:
    """
    Build a row in your ground-station schema.

    Since met_s is NOT absolute time (it's seconds since program start),
    we use the server receive time for timestamps.
    """
    row = {k: "" for k in GS_COLUMNS}

    # Use server receive time as the canonical timestamp
    ts_unix = received_dt_utc.replace(tzinfo=timezone.utc).timestamp()
    row["timestamp_unix_s"] = f"{ts_unix:.6f}"
    row["timestamp_iso"] = received_dt_utc.replace(tzinfo=None).isoformat(timespec="microseconds")

    # gps_time_str: your GS example is like "5:42:43"
    try:
        row["gps_time_str"] = received_dt_utc.strftime("%-H:%M:%S")
    except Exception:
        row["gps_time_str"] = received_dt_utc.strftime("%H:%M:%S").lstrip("0")

    # ENV
    if parsed.get("temp_C") is not None:
        row["env_temp_C"] = f"{parsed['temp_C']:.2f}"
    if parsed.get("hum_pct") is not None:
        row["env_hum_pct"] = f"{parsed['hum_pct']:.2f}"
    if parsed.get("press_hPa") is not None:
        row["env_press_hPa"] = f"{parsed['press_hPa']:.2f}"

    # GPS
    if parsed.get("lat") is not None:
        row["gps_lat"] = f"{parsed['lat']:.6f}"
    if parsed.get("lon") is not None:
        row["gps_lon"] = f"{parsed['lon']:.6f}"
    if parsed.get("alt_m") is not None:
        row["gps_alt_m"] = f"{parsed['alt_m']:.3f}"

    # ORI
    if parsed.get("roll_deg") is not None:
        row["ori_roll_deg"] = f"{parsed['roll_deg']:.2f}"
    if parsed.get("pitch_deg") is not None:
        row["ori_pitch_deg"] = f"{parsed['pitch_deg']:.2f}"
    if parsed.get("yaw_deg") is not None:
        row["ori_yaw_deg"] = f"{parsed['yaw_deg']:.2f}"

    # Put coinc into a known column so your GS can display it
    if parsed.get("coinc") is not None:
        row["watch1_event"] = str(parsed["coinc"])

    return row


def row_to_tsv(row: dict, include_header: bool = True) -> str:
    header = "\t".join(GS_COLUMNS)
    values = "\t".join(str(row.get(k, "")) for k in GS_COLUMNS)
    return (header + "\n" + values + "\n") if include_header else (values + "\n")


@app.route("/", methods=["GET"])
def index():
    return "RockBLOCK ground station backend is alive.", 200


@app.route("/rockblock", methods=["POST"])
def rockblock_in():
    """
    Rock7 HTTP_POST will send form-encoded fields like:
      imei, momsn, transmit_time, iridium_latitude, iridium_longitude, iridium_cep, data (hex)
    """
    global LATEST, HISTORY, ROWS

    payload = request.form or request.json or {}

    imei = payload.get("imei")
    momsn = payload.get("momsn")
    tx_time = payload.get("transmit_time")
    ir_lat = payload.get("iridium_latitude")
    ir_lon = payload.get("iridium_longitude")
    ir_cep = payload.get("iridium_cep")
    data_hex = payload.get("data")

    received_dt = datetime.utcnow()

    msg = {
        "received_at": received_dt.isoformat() + "Z",
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
            data_bytes = bytes.fromhex(str(data_hex).strip())
            text = data_bytes.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = None

    msg["data_text"] = text

    # Parse your mini payload
    parsed = parse_mini_payload(text or "")
    msg.update(parsed)

    # Build ground-station row (timestamps based on receive time)
    row = build_gs_row(parsed, received_dt_utc=received_dt)
    msg["gs_row"] = row

    HISTORY.append(msg)
    LATEST = msg
    ROWS.append(row)

    return "OK", 200


@app.route("/api/latest", methods=["GET"])
def api_latest():
    if not LATEST:
        return jsonify({"error": "no data yet"}), 404
    return jsonify(LATEST)


@app.route("/api/latest_row", methods=["GET"])
def api_latest_row():
    if not ROWS:
        return jsonify({"error": "no rows yet"}), 404
    return jsonify(ROWS[-1])


@app.route("/api/latest_tsv", methods=["GET"])
def api_latest_tsv():
    if not ROWS:
        return Response("no rows yet\n", mimetype="text/plain", status=404)
    return Response(row_to_tsv(ROWS[-1], include_header=True), mimetype="text/plain")


@app.route("/api/history", methods=["GET"])
def api_history():
    return jsonify(HISTORY[-100:])


@app.route("/api/history_tsv", methods=["GET"])
def api_history_tsv():
    """
    TSV of last N rows. Example: /api/history_tsv?n=100
    """
    try:
        n = int(request.args.get("n", "100"))
    except Exception:
        n = 100
    n = max(1, min(n, 5000))

    rows = ROWS[-n:]
    if not rows:
        return Response("no rows yet\n", mimetype="text/plain", status=404)

    lines = ["\t".join(GS_COLUMNS)]
    for r in rows:
        lines.append("\t".join(str(r.get(k, "")) for k in GS_COLUMNS))
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@app.route("/api/reset", methods=["POST"])
def api_reset():
    global LATEST, HISTORY, ROWS
    key = request.args.get("key") or request.form.get("key")
    if key != RESET_KEY:
        return jsonify({"error": "forbidden"}), 403

    LATEST = None
    HISTORY = []
    ROWS = []
    return jsonify({"status": "reset", "time": datetime.utcnow().isoformat() + "Z"}), 200


if __name__ == "__main__":
    # Render provides PORT
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
