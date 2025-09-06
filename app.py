import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

MIST_TOKEN = os.getenv("MIST_API_TOKEN")
ORG_ID = os.getenv("MIST_ORG_ID")
MIST_BASE_URL = "https://api.ac5.mist.com/api/v1"

app = Flask(__name__)
HEADERS = {"Authorization": f"Token {MIST_TOKEN}"}


def epoch_to_gmt_local(epoch, tz_offset_minutes):
    """Convert epoch to GMT and site local time"""
    dt_gmt = datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    local_dt = datetime.utcfromtimestamp(epoch) + pytz.timedelta(minutes=tz_offset_minutes)
    dt_local = local_dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt_gmt, dt_local


@app.route("/")
def home():
    return jsonify({"message": "Mist QR API is running 🚀"})


@app.route("/ap-info", methods=["GET"])
def ap_info():
    ap_mac = request.args.get("mac")
    ap_serial = request.args.get("serial")

    if not ap_mac and not ap_serial:
        return jsonify({"error": "Provide ?mac=<MAC> or ?serial=<Serial>"}), 400

    # Step 1: Fetch all sites
    try:
        sites_resp = requests.get(f"{MIST_BASE_URL}/orgs/{ORG_ID}/sites", headers=HEADERS)
        sites_resp.raise_for_status()
        sites = sites_resp.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to fetch sites: {str(e)}"}), 500

    # Step 2: Loop through each site
    for site in sites:
        site_id = site.get("id")
        site_name = site.get("name")
        tz_offset = site.get("tzoffset", 0)

        # Device stats endpoint
        device_url = f"{MIST_BASE_URL}/sites/{site_id}/stats/devices/{ap_mac if ap_mac else ap_serial}"

        try:
            dev_resp = requests.get(device_url, headers=HEADERS)
            if dev_resp.status_code == 404:
                continue  # AP not in this site
            dev_resp.raise_for_status()
            ap_data = dev_resp.json()

            # Add extra fields
            ap_data_clean = {
                "ap_name": ap_data.get("name"),
                "model": ap_data.get("model")
                "mac": ap_data.get("mac"),
                "serial": ap_data.get("serial"),
                "status": ap_data.get("status"),
                "version": ap_data.get("version"),
                "site_name": site_name,
                "clients_2_4GHz": ap_data.get("clients_2GHz", 0),
                "clients_5GHz": ap_data.get("clients_5GHz", 0),
                "clients_6GHz": ap_data.get("clients_6GHz", 0),
                "lldp_neighbor": ap_data.get("lldp_neighbor"),
                "lldp_port": ap_data.get("lldp_port"),
                "last_seen": ap_data.get("last_seen"),
            }

            # Optional: add timestamps if present
            if "last_seen" in ap_data:
                gmt, local = epoch_to_gmt_local(ap_data["last_seen"], tz_offset)
                ap_data_clean["last_seen_gmt"] = gmt
                ap_data_clean["last_seen_local"] = local

            return jsonify(ap_data_clean)

        except requests.exceptions.RequestException:
            continue  # Skip site on error

    return jsonify({"error": "AP not found in any site"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
