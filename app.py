import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Environment variables from Render
MIST_TOKEN = os.getenv("MIST_API_TOKEN")
MIST_ORG_ID = os.getenv("MIST_ORG_ID")
MIST_BASE_URL = "https://api.ac5.mist.com/api/v1"

if not MIST_TOKEN or not MIST_ORG_ID:
    raise ValueError("Please set MIST_API_TOKEN and MIST_ORG_ID in environment variables.")

HEADERS = {"Authorization": f"Token {MIST_TOKEN}"}

@app.route("/")
def home():
    return jsonify({"message": "Mist QR API is running 🚀"})

@app.route("/ap-info", methods=["GET"])
def ap_info():
    """
    Query AP info by MAC or Serial across all sites.
    Example: /ap-info?mac=aa:bb:cc:dd:ee:ff
             /ap-info?serial=A123456789
    """
    ap_mac = request.args.get("mac")
    ap_serial = request.args.get("serial")

    if not ap_mac and not ap_serial:
        return jsonify({"error": "Please provide ?mac=<AP-MAC> or ?serial=<AP-Serial>"}), 400

    # 1. Fetch all sites in the org
    try:
        sites_resp = requests.get(
            f"{MIST_BASE_URL}/orgs/{MIST_ORG_ID}/sites", headers=HEADERS
        )
        sites_resp.raise_for_status()
        sites = sites_resp.json()
    except Exception as e:
        return jsonify({"error": "Failed to fetch sites", "details": str(e)}), 500

    # 2. Loop through each site and find the device
    for site in sites:
        site_id = site.get("id")
        try:
            devices_resp = requests.get(
                f"{MIST_BASE_URL}/sites/{site_id}/devices", headers=HEADERS
            )
            devices_resp.raise_for_status()
            devices = devices_resp.json()
        except Exception as e:
            continue  # skip site if API call fails

        for device in devices:
            if (ap_mac and device.get("mac") == ap_mac) or (ap_serial and device.get("serial") == ap_serial):
                device_id = device.get("id")
                try:
                    stats_resp = requests.get(
                        f"{MIST_BASE_URL}/sites/{site_id}/stats/devices/{device_id}", headers=HEADERS
                    )
                    stats_resp.raise_for_status()
                    stats = stats_resp.json()
                except Exception as e:
                    return jsonify({"error": "Failed to fetch device stats", "details": str(e)}), 500

                # Build response
                response = {
                    "site_name": site.get("name"),
                    "ap_name": stats.get("name"),
                    "serial": stats.get("serial"),
                    "mac": stats.get("mac"),
                    "model": stats.get("model"),
                    "version": stats.get("version"),
                    "status": stats.get("status"),
                    "lldp_neighbor": stats.get("lldp_stat", {}).get("system_name"),
                    "lldp_port": stats.get("lldp_stat", {}).get("port_id"),
                    "clients_5GHz": stats.get("radio_stat", {}).get("band_5", {}).get("num_clients", 0),
                    "clients_6GHz": stats.get("radio_stat", {}).get("band_6", {}).get("num_clients", 0)
                }
                return jsonify(response)

    return jsonify({"error": "AP not found in any site"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
