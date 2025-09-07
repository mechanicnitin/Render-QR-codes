import os
import io
import requests
from flask import Flask, jsonify, send_file, request, abort
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image

# === Mist API config from Render environment ===
MIST_TOKEN = os.getenv("MIST_API_TOKEN")
ORG_ID = os.getenv("MIST_ORG_ID")
LOGO_PATH = "cba_small.png"

# Flask app
app = Flask(__name__)

# Mist API Base URL (adjust region if required)
MIST_BASE_URL = "https://api.ac5.mist.com/api/v1"


# === Helpers ===
def get_ap_info(serial=None):
    """Return AP info by serial (loop through all sites)."""
    if not serial:
        return None

    headers = {"Authorization": f"Token {MIST_TOKEN}"}
    ap_info = None

    try:
        # Get all sites for the org
        sites_resp = requests.get(f"{MIST_BASE_URL}/orgs/{ORG_ID}/sites", headers=headers, timeout=10)
        sites_resp.raise_for_status()
        sites = sites_resp.json()

        # Search each site for the AP
        for site in sites:
            site_id = site["id"]
            ap_resp = requests.get(f"{MIST_BASE_URL}/sites/{site_id}/devices", headers=headers, timeout=10)
            ap_resp.raise_for_status()
            for ap in ap_resp.json():
                if ap.get("serial", "").lower() == serial.lower():
                    # Found the AP → now fetch detailed stats
                    device_id = ap["id"]
                    stats_url = f"{MIST_BASE_URL}/sites/{site_id}/stats/devices/{device_id}"
                    stats_resp = requests.get(stats_url, headers=headers, timeout=10)
                    stats_resp.raise_for_status()
                    stats = stats_resp.json()

                    ap_info = {
                        "name": stats.get("name", "N/A"),
                        "serial": stats.get("serial", serial),
                        "mac": stats.get("mac", "N/A"),
                        "model": stats.get("model", "N/A"),
                        "version": stats.get("version", "N/A"),
                        "switch_name": stats.get("lldp_stat", {}).get("system_name", "N/A"),
                        "switch_port": stats.get("lldp_stat", {}).get("port_id", "N/A"),
                        "clients_5g": stats.get("radio_stat", {}).get("band_5", {}).get("num_clients", "N/A"),
                        "clients_6g": stats.get("radio_stat", {}).get("band_6", {}).get("num_clients", "N/A"),
                        "status": stats.get("status", "N/A")
                    }
                    break
            if ap_info:
                break
    except Exception as e:
        print(f"❌ Error fetching AP info: {e}")
        return None

    return ap_info



def generate_pdf(ap_info):
    """Create PDF for AP info and return as BytesIO."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Logo top-right
    try:
        if os.path.exists(LOGO_PATH):
            logo = Image.open(LOGO_PATH)
            logo_width = 100
            logo_height = int((logo_width / logo.width) * logo.height)
            logo.save("temp_logo.png")
            c.drawImage(
                "temp_logo.png",
                width - logo_width - 40,
                height - logo_height - 40,
                width=logo_width,
                height=logo_height,
            )
    except Exception as e:
        print(f"⚠️ Could not insert logo: {e}")

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 80, "CBA Access Point Report")

    # Device Info
    c.setFont("Helvetica", 12)
    y = height - 120
    fields = [
        ("AP Name", ap_info["name"]),
        ("Model", ap_info["model"]),
        ("Serial Number", ap_info["serial"]),
        ("MAC Address", ap_info["mac"]),
        ("Version", ap_info["version"]),
        ("Status", ap_info["status"]),
        ("Switch Name", ap_info["switch_name"]),
        ("Switch Port", ap_info["switch_port"]),
        ("Clients (5GHz)", ap_info["clients_5g"]),
        ("Clients (6GHz)", ap_info["clients_6g"]),
    ]

    for label, value in fields:
        c.drawString(50, y, f"{label}: {value}")
        y -= 20

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer



# === Flask Endpoints ===
@app.route("/")
def home():
    return jsonify({"message": "Mist QR API running 🚀"})


@app.route("/ap-info")
def ap_info_endpoint():
    serial = request.args.get("serial")
    info = get_ap_info(serial=serial)
    if not info:
        abort(404, description="AP not found in Mist")
    pdf_buffer = generate_pdf(info)
    fname = f"{info['name']}_{info['serial']}.pdf"
    return send_file(pdf_buffer, download_name=fname, as_attachment=True)


# === Main ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
