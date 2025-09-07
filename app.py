import os
import io
import requests
from flask import Flask, jsonify, send_file, request, abort
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image
from dotenv import load_dotenv

# === Load .env ===
load_dotenv()
MIST_TOKEN = os.getenv("MIST_API_TOKEN")
ORG_ID = os.getenv("MIST_ORG_ID")
LOGO_PATH = "logo.png"

# Flask app
app = Flask(__name__)

# Mist API Base URL (adjust region if required)
MIST_BASE_URL = "https://api.ac5.mist.com/api/v1"


# === Helpers ===
def get_ap_info(serial=None):
    """Search AP by serial across all sites in Mist org."""
    if not serial:
        return None

    headers = {"Authorization": f"Token {MIST_TOKEN}"}
    try:
        sites_resp = requests.get(f"{MIST_BASE_URL}/orgs/{ORG_ID}/sites", headers=headers, timeout=10)
        sites_resp.raise_for_status()
        sites = sites_resp.json()

        for site in sites:
            site_id = site["id"]
            site_name = site.get("name", "Unknown Site")
            ap_resp = requests.get(f"{MIST_BASE_URL}/sites/{site_id}/devices", headers=headers, timeout=10)
            ap_resp.raise_for_status()

            for ap in ap_resp.json():
                if ap.get("serial", "").lower() == serial.lower():
                    # Found matching AP
                    return {
                        "device_name": ap.get("name", "Unknown"),
                        "model": ap.get("model", "Unknown"),
                        "serial_number": ap.get("serial"),
                        "mac": ap.get("mac", "Unknown"),
                        "site": site_name,
                        "live_stats": ap,  # full AP JSON
                    }

    except Exception as e:
        return {"error": f"Failed to fetch data: {e}"}

    return None


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

    # Static details
    c.setFont("Helvetica", 12)
    y = height - 120
    c.drawString(50, y, f"Device Name: {ap_info['device_name']}")
    y -= 20
    c.drawString(50, y, f"Model: {ap_info['model']}")
    y -= 20
    c.drawString(50, y, f"Serial Number: {ap_info['serial_number']}")
    y -= 20
    c.drawString(50, y, f"MAC Address: {ap_info['mac']}")
    y -= 20
    c.drawString(50, y, f"Site: {ap_info.get('site', 'Unknown')}")

    # Live stats
    live = ap_info.get("live_stats", {})
    y -= 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Live Stats")
    c.setFont("Helvetica", 12)

    if isinstance(live, dict):
        for k, v in live.items():
            if isinstance(v, (str, int, float)):
                y -= 20
                c.drawString(70, y, f"{k.capitalize()}: {v}")

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
    fname = f"{info['device_name']}_{info['serial_number']}.pdf"
    return send_file(pdf_buffer, download_name=fname, as_attachment=True)


# === Main ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
