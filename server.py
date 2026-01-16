#!/usr/bin/env python3
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

RESET_KEY = os.environ.get("RESET_KEY", "changeme123")

LATEST = None
HISTORY = []
ROWS = []

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
    text: met_s,temp,hum,press,lat,lon,alt,roll,pitch,yaw,coinc
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


def build_gs_row(parsed: dict) -> dict:
    row = {k: "" for k in GS_COLUMNS}

    met_s = parsed.get("met_s")

    if met_s is not None:
        row["timestamp_unix_s"] = f"{float(met_s):.6f}"
        dt = datetime.fromtimestamp(float(met_s), tz=timezone.utc)
        row["timestamp_iso"] = dt.replace(tzinfo=None).isoformat()
        try:
            row["gps_time_str"] = dt.strftime("%-H:%M:%S")
        except Exception:
            row["gps_time_str"] = dt.strftime("%H:%M:%S").lstrip("0")
    else:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        row["timestamp_unix_s"] = f"{now.timestamp():.6f}"
        row["timestamp_iso"] = now.replace(tzinfo=None).isoformat()

    if parsed.get("temp_C") is not None:
        row["env_temp_C"] = f"{parsed['temp_C']:.2f}"
    if parsed.get("hum_pct") is not None:
        row["env_hum_pct"] = f"{parsed['hum_pct']:.2f}"
    if parsed.get("press_hPa") is not None:
        row["env_press_hPa"] = f"{parsed['press_hPa']:.2f}"

    if parsed.get("lat") is not None:
        row["gps_lat"] = f"{parsed['lat']:.6f}"
    if parsed.get("lon") is not None:
        row["gps_lon"] = f"{parsed['lon']:.6f}"
    if parsed.get("alt_m") is not None:
        row["gps_alt_m"] = f"{parsed['alt_m']:.3f}"

    if parsed.get("roll_deg") is not None:
        row["ori_roll_deg"] = f"{parsed['roll_deg']:.2f}"
    if parsed.get("pitch_deg") is not None:
        row["ori_pitch_deg"] = f"{parsed['pitch_deg']:.2f}"
    if parsed.get("yaw_deg") is not None:
        row["ori_yaw_deg"] = f"{parsed['yaw_deg']:.2f}"

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
    global LATEST, HISTORY, ROWS

    payload = request.form or request.json or {}

    data_hex = payload.get("data")

    msg = {
        "received_at": datetime.utcnow().isoformat() + "Z",
        "imei": payload.get("imei"),
        "momsn": payload.get("momsn"),
        "transmit_time": payload.get("transmit_time"),
        "iridium_latitude": payload.get("iridium_latitude"),
        "iridium_longitude": payload.get("iridium_longitude"),
        "iridium_cep": payload.get("iridium_cep"),
        "data_hex": data_hex,
    }

    text = None
    if data_hex:
        try:
            data_bytes = bytes.fromhex(str(data_hex).strip())
            text = data_bytes.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = None

    msg["data_text"] = text

    parsed = parse_mini_payload(text or "")
    msg.update(parsed)

    # FIX: mirror real GPS into common keys so clients don’t use Iridium lat/lon
    if parsed.get("lat") is not None:
        msg["gps_lat"] = parsed["lat"]
        msg["lat"] = parsed["lat"]
    if parsed.get("lon") is not None:
        msg["gps_lon"] = parsed["lon"]
        msg["lon"] = parsed["lon"]
    if parsed.get("alt_m") is not None:
        msg["gps_alt_m"] = parsed["alt_m"]
        msg["alt"] = parsed["alt_m"]

    row = build_gs_row(parsed)
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
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
