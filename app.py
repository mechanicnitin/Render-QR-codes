import os
import io
import requests
from flask import Flask, send_file, abort
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from datetime import datetime

app = Flask(__name__)

# Load secrets from env (Render Dashboard -> Environment variables)
MIST_API_TOKEN = os.getenv("MIST_API_TOKEN")
MIST_ORG_ID = os.getenv("MIST_ORG_ID")
MIST_BASE_URL = os.getenv("MIST_BASE_URL", "https://api.ac5.mist.com")

# Path to logo inside app (upload logo.png in repo)
LOGO_PATH = "cba_small.png"


@app.route("/pdf/<serial_or_mac>")
def ap_pdf(serial_or_mac):
    """
    Generate a branded PDF with live AP stats.
    """
    headers = {"Authorization": f"Token {MIST_API_TOKEN}"}

    # 1. Fetch all sites for the org
    sites_url = f"{MIST_BASE_URL}/api/v1/orgs/{MIST_ORG_ID}/sites"
    resp = requests.get(sites_url, headers=headers)
    if resp.status_code != 200:
        return abort(403, description="Failed to fetch sites from Mist API")
    sites = resp.json()

    # 2. Loop through sites & fetch APs until we find match
    ap_data = None
    for site in sites:
        site_id = site["id"]
        aps_url = f"{MIST_BASE_URL}/api/v1/sites/{site_id}/devices"
        aps_resp = requests.get(aps_url, headers=headers)
        if aps_resp.status_code == 200:
            aps = aps_resp.json()
            for ap in aps:
                if ap.get("serial") == serial_or_mac or ap.get("mac") == serial_or_mac:
                    ap_data = {**ap, "site_name": site["name"]}
                    break
        if ap_data:
            break

    if not ap_data:
        return abort(404, description="AP not found")

    # 3. Generate PDF in memory
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Logo
    try:
        c.drawImage(LOGO_PATH, width - 60*mm, height - 30*mm, width=40*mm, height=20*mm, preserveAspectRatio=True)
    except:
        pass

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2, height - 40*mm, "CBA Access Point Live Report")

    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(width/2, height - 50*mm, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Device Info
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30*mm, height - 70*mm, "Device Information")

    c.setFont("Helvetica", 10)
    info_y = height - 80*mm
    info_lines = [
        f"Device Name : {ap_data.get('name', 'N/A')}",
        f"Model       : {ap_data.get('model', 'N/A')}",
        f"Serial No.  : {ap_data.get('serial', 'N/A')}",
        f"MAC Address : {ap_data.get('mac', 'N/A')}",
        f"Site Name   : {ap_data.get('site_name', 'N/A')}",
        f"Status      : {ap_data.get('status', 'N/A')}",
    ]
    for line in info_lines:
        c.drawString(35*mm, info_y, line)
        info_y -= 7*mm

    # Live Stats
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30*mm, info_y - 10*mm, "Live Stats")

    c.setFont("Helvetica", 10)
    stats_y = info_y - 20*mm
    stats_lines = [
        f"Clients (2.4GHz): {ap_data.get('clients_24', 0)}",
        f"Clients (5GHz)  : {ap_data.get('clients_5', 0)}",
        f"Clients (6GHz)  : {ap_data.get('clients_6', 0)}",
        f"Software Version: {ap_data.get('version', 'N/A')}",
        f"LLDP Neighbor   : {ap_data.get('lldp_neighbor', 'N/A')}",
        f"LLDP Port       : {ap_data.get('lldp_port', 'N/A')}",
    ]
    for line in stats_lines:
        c.drawString(35*mm, stats_y, line)
        stats_y -= 7*mm

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width/2, 15*mm, "Report auto-generated from Mist API via CBA Wireless Portal")

    c.showPage()
    c.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{ap_data.get('name','AP')}_Report.pdf",
        mimetype="application/pdf"
    )


@app.route("/")
def home():
    return "✅ CBA AP PDF Generator is running!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
