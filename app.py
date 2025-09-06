from flask import Flask, request, jsonify, render_template_string
import requests
import os

app = Flask(__name__)

MIST_TOKEN = os.getenv("MIST_API_TOKEN")
MIST_BASE_URL = "https://api.mist.com/api/v1"
ORG_ID = os.getenv("MIST_ORG_ID")

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

    headers = {"Authorization": f"Token {MIST_TOKEN}"}

    # Step 1: Get all sites in the org
    url_sites = f"{MIST_BASE_URL}/orgs/{ORG_ID}/sites"
    resp_sites = requests.get(url_sites, headers=headers)

    if resp_sites.status_code != 200:
        return jsonify({"error": "Failed to fetch sites", "details": resp_sites.text}), resp_sites.status_code

    sites = resp_sites.json()
    found_ap = None
    site_id = None

    # Step 2: Loop through sites, look for AP in /devices
    for site in sites:
        site_id = site["id"]
        site_name = site.get("name", "Unknown Site")

        url_devices = f"{MIST_BASE_URL}/sites/{site_id}/devices"
        resp_devices = requests.get(url_devices, headers=headers)

        if resp_devices.status_code != 200:
            continue  # skip site if error

        devices = resp_devices.json()

        for device in devices:
            if ((ap_mac and device.get("mac", "").lower() == ap_mac.lower()) or
                (ap_serial and device.get("serial", "").lower() == ap_serial.lower())):
                found_ap = device
                found_ap["site_name"] = site_name
                break

        if found_ap:
            break  # stop once device is found

    if not found_ap:
        return jsonify({"error": "Device not found in any site"}), 404

    # Step 3: Fetch stats for this device
    device_id = found_ap["id"]
    url_stats = f"{MIST_BASE_URL}/sites/{site_id}/stats/devices/{device_id}"
    resp_stats = requests.get(url_stats, headers=headers)

    if resp_stats.status_code != 200:
        return jsonify({"error": "Failed to fetch AP stats", "details": resp_stats.text}), resp_stats.status_code

    stats = resp_stats.json()

    result = {
        "site": found_ap.get("site_name"),
        "ap_name": found_ap.get("name", "Unknown"),
        "serial": found_ap.get("serial"),
        "mac": found_ap.get("mac"),
        "model": found_ap.get("model"),
        "version": found_ap.get("version"),
        "status": stats.get("status", "unknown"),
        "clients_5ghz": stats.get("radio_stat", {}).get("band_5", {}).get("num_clients", 0),
        "clients_6ghz": stats.get("radio_stat", {}).get("band_6", {}).get("num_clients", 0),
        "switch_name": stats.get("lldp_stat", {}).get("system_name", "N/A"),
        "switch_port": stats.get("lldp_stat", {}).get("port_id", "N/A"),
        "ip": stats.get("ip", "N/A")
    }

    # Technician-friendly HTML
    html_template = """
    <html>
        <head>
            <title>AP Info - {{ ap_name }}</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                h1 { color: #2E86C1; }
                .status-online { color: green; font-weight: bold; }
                .status-offline { color: red; font-weight: bold; }
                .box { border: 1px solid #ccc; padding: 15px; margin-top: 10px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <h1>Access Point Info</h1>
            <div class="box">
                <p><b>Site:</b> {{ site }}</p>
                <p><b>AP Name:</b> {{ ap_name }}</p>
                <p><b>Serial:</b> {{ serial }}</p>
                <p><b>MAC:</b> {{ mac }}</p>
                <p><b>Model:</b> {{ model }}</p>
                <p><b>Version:</b> {{ version }}</p>
                <p><b>Status:</b> 
                    {% if status == "connected" %}
                        <span class="status-online">✅ Online</span>
                    {% else %}
                        <span class="status-offline">❌ Offline</span>
                    {% endif %}
                </p>
                <p><b>Clients (5GHz):</b> {{ clients_5ghz }}</p>
                <p><b>Clients (6GHz):</b> {{ clients_6ghz }}</p>
                <p><b>Switch:</b> {{ switch_name }} (Port: {{ switch_port }})</p>
                <p><b>IP:</b> {{ ip }}</p>
            </div>
        </body>
    </html>
    """

    return render_template_string(html_template, **result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
