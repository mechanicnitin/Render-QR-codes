import os
import pandas as pd
from flask import Flask, jsonify, send_file, request, abort
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from PIL import Image
import io
import requests
from dotenv import load_dotenv

# === Load .env ===
load_dotenv()
MIST_TOKEN = os.getenv("MIST_API_TOKEN")
ORG_ID = os.getenv("MIST_ORG_ID")
EXCEL_FILE = "Foundry_Devices.xlsx"
LOGO_PATH = "logo.png"

# Flask app
app = Flask(__name__)

# Load Excel data once at startup
df_devices = pd.read_excel(EXCEL_FILE)
df_devices.fillna("", inplace=True)

# Mist API Base URL (adjust ac5 or region if required)
MIST_BASE_URL = "https://api.ac5.mist.com/api/v1"

# === Helpers ===
def get_ap_info(mac=None, serial=None):
    """Return AP info from Excel first, then live stats from Mist API."""
    if mac:
        row = df_devices[df_devices['MAC Address'].str.lower() == mac.lower()]
    elif serial:
        row = df_devices[df_devices['Serial Number'].str.lower() == serial.lower()]
    else:
        return None

    if row.empty:
        return None

    device = row.iloc[0].to_dict()

    # Fetch live AP stats from Mist
    headers = {"Authorization": f"Token {MIST_TOKEN}"}
    # Loop through all sites to find AP (simplified: using first site)
    try:
        sites_resp = requests.get(f"{MIST_BASE_URL}/orgs/{ORG_ID}/sites", headers=headers)
        sites_resp.raise_for_status()
        sites = sites_resp.json()
        live_info = None
        for site in sites:
            site_id = site['id']
            ap_resp = requests.get(f"{MIST_BASE_URL}/sites/{site_id}/aps", headers=headers)
            ap_resp.raise_for_status()
            aps = ap_resp.json()
            for ap in aps:
                if mac and ap.get('mac', '').lower() == mac.lower():
                    live_info = ap
                    break
                if serial and ap.get('serial', '').lower() == serial.lower():
                    live_info = ap
                    break
            if live_info:
                break
    except Exception as e:
        return {"error": f"Failed to fetch live info: {e}"}

    # Merge Excel + live info
    result = {
        "device_name": device.get("Device Name"),
        "model": device.get("Model"),
        "serial_number": device.get("Serial Number"),
        "mac": device.get("MAC Address"),
        "live_stats": live_info
    }
    return result

def generate_pdf(ap_info):
    """Create PDF for AP info and return as BytesIO"""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Logo
    try:
        logo = Image.open(LOGO_PATH)
        logo_width = 80
        logo_height = int((logo_width / logo.width) * logo.height)
        logo.save("temp_logo.png")
        c.drawImage("temp_logo.png", width - logo_width - 40, height - logo_height - 40,
                    width=logo_width, height=logo_height)
    except Exception as e:
        print(f"⚠️ Could not insert logo: {e}")

    # Device Info
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, height - 80, "CBA Access Point Details")
    c.setFont("Helvetica", 12)
    c.drawString(100, height - 130, f"Device Name: {ap_info['device_name']}")
    c.drawString(100, height - 150, f"Model: {ap_info['model']}")
    c.drawString(100, height - 170, f"Serial Number: {ap_info['serial_number']}")
    c.drawString(100, height - 190, f"MAC Address: {ap_info['mac']}")

    # Live stats
    c.drawString(100, height - 220, f"Status: {ap_info['live_stats'].get('status','N/A')}")
    c.drawString(100, height - 240, f"AP Name: {ap_info['live_stats'].get('ap_name','N/A')}")
    c.drawString(100, height - 260, f"Clients 5GHz: {ap_info['live_stats'].get('clients_5GHz','N/A')}")
    c.drawString(100, height - 280, f"Clients 6GHz: {ap_info['live_stats'].get('clients_6GHz','N/A')}")
    c.drawString(100, height - 300, f"LLDP Neighbor: {ap_info['live_stats'].get('lldp_neighbor','N/A')}")

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
    mac = request.args.get("mac")
    serial = request.args.get("serial")
    info = get_ap_info(mac, serial)
    if not info:
        abort(404, description="AP not found in Excel or Mist")
    return jsonify(info)

@app.route("/ap-pdf")
def ap_pdf_endpoint():
    mac = request.args.get("mac")
    serial = request.args.get("serial")
    info = get_ap_info(mac, serial)
    if not info:
        abort(404, description="AP not found in Excel or Mist")
    pdf_buffer = generate_pdf(info)
    fname = f"{info['device_name']}_{info['serial_number']}.pdf"
    return send_file(pdf_buffer, download_name=fname, as_attachment=True)

# === Main ===
if __name__ == "__main__":
    # For local testing
    app.run(host="0.0.0.0", port=5000, debug=True)
