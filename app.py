import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Mist API settings from Render environment
MIST_TOKEN = os.getenv("MIST_API_TOKEN")
MIST_BASE_URL = "https://api.ac5.mist.com/api/v1"
ORG_ID = os.getenv("MIST_ORG_ID")

if not MIST_TOKEN or not ORG_ID:
    raise Exception("MIST_API_TOKEN and MIST_ORG_ID must be set in env variables!")

HEADERS = {"Authorization": f"Token {MIST_TOKEN}"}

@app.route("/")
def home():
    return jsonify({"message": "Mist QR API is running 🚀"})

@app.route("/ap-info", methods=["GET"])
def ap_info():
    """
    Look for AP by MAC or Serial across all sites in the org,
    then fetch live stats for that AP.
    Example: /ap-info?mac=aa:bb:cc:dd:ee:ff
             /ap-info?serial=A123456789
    """
    ap_mac = request.args.get("mac")
    ap_serial = request.args.get("serial")

    if not ap_mac and not ap_serial:
        return jsonify({"error": "Please provide ?mac=<AP-MAC> or ?serial=<AP-Serial>"}), 400

    try:
        # 1️⃣ Get all sites in the org
        resp = requests.get(f"{MIST_BASE_URL}/orgs/{ORG_ID}/sites", headers=HEADERS)
        resp.raise_for_status()
        sites = resp.json()
    except Exception as e:
        return jsonify({"error": "Failed to fetch sites", "details": str(e)}), 500

    # 2️⃣ Search each site for the AP
    for site in sites:
        site_id = site.get("id")
        site_name = site.get("name")
        try:
            r = requests.get(f"{MIST_BASE_URL}/sites/{site_id}/devices", headers=HEADERS)
            r.raise_for_status()
            devices = r.json()
        except Exception as e:
            continue  # skip this site if failed

        # 3️⃣ Check each device
        for device in devices:
            if (ap_mac and device.get("mac", "").lower() == ap_mac.lower()) or \
               (ap_serial and device.get("serial") == ap_serial):
                device_id = device.get("id")
                # 4️⃣ Fetch device stats
                stats_resp = requests.get(f"{MIST_BASE_URL}/sites/{site_id}/stats/devices/{device_id}", headers=HEADERS)
                if stats_resp.status_code != 200:
                    return jsonify({"error": "Failed to fetch AP stats", "site_id": site_id, "device_id": device_id}), 500
                stats = stats_resp.json()

                # 5️⃣ Extract relevant info
                result = {
                    "site_name": site_name,
                    "ap_name": stats.get("name"),
                    "serial": stats.get("serial"),
                    "mac": stats.get("mac"),
                    "model": stats.get("model"),
                    "version": stats.get("version"),
                    "status": stats.get("status"),
                    "power": stats.get("power_allocated") or stats.get("power_avail"),
                    "lldp_system_name": stats.get("lldp_stat", {}).get("system_name"),
                    "lldp_port": stats.get("lldp_stat", {}).get("port_id"),
                    "clients_5ghz": stats.get("radio_stat", {}).get("band_5", {}).get("num_clients", 0),
                    "clients_6ghz": stats.get("radio_stat", {}).get("band_6", {}).get("num_clients", 0)
                }
                return jsonify(result)

    return jsonify({"error": "AP not found in any site"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
