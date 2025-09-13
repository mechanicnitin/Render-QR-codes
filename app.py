import os
import io
import requests
from flask import Flask, jsonify, send_file, request, abort, Response
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image
import html

# === Mist API config from Render environment ===
MIST_TOKEN = os.getenv("MIST_API_TOKEN") or os.getenv("MIST_TOKEN")
ORG_ID = os.getenv("MIST_ORG_ID")
LOGO_PATH = os.getenv("LOGO_PATH", "cba_small.png")

# Role PSKs (set these on Render)
PSK_SUPER = os.getenv("MIST_PSK_SUPERUSER")
PSK_MANAGER = os.getenv("MIST_PSK_MANAGER")  # also used for field tech

# Flask app
app = Flask(__name__)

# Mist API Base URL (adjust region if required)
MIST_BASE_URL = "https://api.ac5.mist.com/api/v1"


# === Helpers ===
def get_ap_info(serial=None):
    """Return AP info by serial (loop through all sites) and fetch stats endpoint.
       Returns a dict with keys used by PDF generator or None if not found.
    """
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
            # Use devices endpoint then stats endpoint like you had
            ap_resp = requests.get(f"{MIST_BASE_URL}/sites/{site_id}/devices", headers=headers, timeout=10)
            ap_resp.raise_for_status()
            for ap in ap_resp.json():
                if ap.get("serial", "").lower() == serial.lower():
                    # Found the AP → now fetch detailed stats (stats/devices/{device_id})
                    device_id = ap.get("id")
                    if not device_id:
                        continue
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
                        "clients_5g": stats.get("radio_stat", {}).get("band_5", {}).get("num_clients", 0),
                        "clients_6g": stats.get("radio_stat", {}).get("band_6", {}).get("num_clients", 0),
                        "status": stats.get("status", "N/A"),
                    }
                    break
            if ap_info:
                break
    except Exception as e:
        # Log error server-side, return None to indicate not found / failure
        print(f"❌ Error fetching AP info: {e}")
        return None

    return ap_info


def _draw_logo(c, width, height):
    """Draw logo at top-right (handles PNG transparency)."""
    try:
        if os.path.exists(LOGO_PATH):
            logo = Image.open(LOGO_PATH)
            if logo.mode != "RGBA":
                logo = logo.convert("RGBA")
            white_bg = Image.new("RGBA", logo.size, (255, 255, 255, 255))
            logo_with_white_bg = Image.alpha_composite(white_bg, logo)
            logo_rgb = logo_with_white_bg.convert("RGB")
            logo_width = 100
            logo_height = int((logo_width / logo.width) * logo.height)
            temp_logo = "temp_logo.png"
            logo_rgb.save(temp_logo, "PNG")
            c.drawImage(
                temp_logo,
                width - logo_width - 40,
                height - logo_height - 40,
                width=logo_width,
                height=logo_height,
                mask='auto'
            )
            if os.path.exists(temp_logo):
                os.remove(temp_logo)
    except Exception as e:
        print(f"⚠️ Could not insert logo: {e}")


def generate_pdf_for_role(ap_info, role="public"):
    """
    role: "public", "manager", "super"
    Return BytesIO with PDF content.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # logo
    _draw_logo(c, width, height)

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 80, "CBA Access Point Report")

    # Use safe values if ap_info missing keys
    def safe(k, default="N/A"):
        return html.escape(str(ap_info.get(k, default))) if ap_info else default

    y = height - 120
    c.setFont("Helvetica", 12)

    # Public: only AP name + model
    if role == "public":
        c.drawString(50, y, f"AP Name: {safe('name')}")
        y -= 20
        c.drawString(50, y, f"Model: {safe('model')}")
        y -= 20

    # Manager / Field Tech: name, model, serial, mac
    elif role == "manager":
        c.drawString(50, y, f"AP Name: {safe('name')}")
        y -= 20
        c.drawString(50, y, f"Model: {safe('model')}")
        y -= 20
        c.drawString(50, y, f"Serial Number: {safe('serial')}")
        y -= 20
        c.drawString(50, y, f"MAC Address: {safe('mac')}")
        y -= 20

    # Superuser: full live stats (only the required fields)
    elif role == "super":
        fields = [
            ("AP Name", "name"),
            ("Model", "model"),
            ("Serial Number", "serial"),
            ("MAC Address", "mac"),
            ("Version", "version"),
            ("Status", "status"),
            ("Connected Switch", "switch_name"),
            ("Switch Port", "switch_port"),
            ("Clients (5GHz)", "clients_5g"),
            ("Clients (6GHz)", "clients_6g"),
        ]
        for label, key in fields:
            c.drawString(50, y, f"{label}: {safe(key)}")
            y -= 20

    # if unknown role, show public fallback
    else:
        c.drawString(50, y, f"AP Name: {safe('name')}")
        y -= 20
        c.drawString(50, y, f"Model: {safe('model')}")
        y -= 20

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def validate_key_role(key):
    """Return role string for a valid key, else None."""
    if not key:
        return None
    if PSK_SUPER and key == PSK_SUPER:
        return "super"
    if PSK_MANAGER and key == PSK_MANAGER:
        return "manager"
    return None


# ==== HTML form served when no key provided ====
HTML_FORM = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>CBA AP Access</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 40px; background:#f9f9f9; }}
      .card {{ max-width: 640px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px; background:#fff; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }}
      .logo {{ display:block; margin:0 auto 20px auto; max-height:80px; }}
      label {{ display:block; margin-top:10px; }}
      input[type="text"], input[type="password"] {{ width:100%; padding:8px; margin-top:6px; box-sizing:border-box; }}
      .row {{ display:flex; gap:10px; margin-top:12px; align-items:center; }}
      .muted {{ color:#666; font-size:0.9em; }}
      button {{ margin-top:16px; padding:10px 16px; background:#1e88e5; color:white; border:none; border-radius:4px; cursor:pointer; }}
      button:disabled {{ background:#aaa; }}
    </style>
  </head>
  <body>
    <div class="card">
      <img src="cba_small.png" alt="CBA Logo" class="logo"/>
      <h2>CBA AP Access</h2>
      <p class="muted">Serial: <strong>{serial_safe}</strong></p>

      <form method="post" action="/ap-info">
        <input type="hidden" name="serial" value="{serial_escaped}" />
        <label>
          <input type="checkbox" id="no_pass" name="no_pass" />
          Proceed without password (public view)
        </label>

        <label id="pwd_label">Enter Access Password (for Field Tech / Manager / Superuser)
          <input type="password" id="pw" name="pw" placeholder="Enter password" />
        </label>

        <div class="row">
          <button type="submit">Proceed</button>
        </div>
      </form>

      <p class="muted">If you have an internal access password, enter it to get more details. Otherwise select "Proceed without password" for public info (AP name, model).</p>
    </div>

    <script>
      const checkbox = document.getElementById('no_pass');
      const pwInput = document.getElementById('pw');
      const pwdLabel = document.getElementById('pwd_label');

      checkbox.addEventListener('change', () => {{
        if (checkbox.checked) {{
          pwInput.disabled = true;
          pwInput.value = '';
          pwdLabel.style.opacity = 0.5;
        }} else {{
          pwInput.disabled = false;
          pwdLabel.style.opacity = 1;
        }}
      }});
    </script>
  </body>
</html>
"""




# === Flask Endpoints ===
@app.route("/")
def home():
    return jsonify({"message": "Mist QR API running 🚀"})


@app.route("/ap-info", methods=["GET", "POST"])
def ap_info_endpoint():
    # allow both GET and POST so form posts back here
    if request.method == "GET":
        # GET flow: if key provided in query string, bypass form and return PDF
        serial = request.args.get("serial")
        if not serial:
            return jsonify({"error": "serial parameter required"}), 400

        key = request.args.get("key")
        role = validate_key_role(key)

        ap_info = get_ap_info(serial=serial)
        if not ap_info:
            return abort(404, description="AP not found in Mist")

        if role:
            # valid key provided — return role-specific PDF directly
            pdf_buffer = generate_pdf_for_role(ap_info, role=role)
            fname = f"{ap_info.get('name','AP')}_{ap_info.get('serial','')}.pdf"
            return send_file(pdf_buffer, download_name=fname, as_attachment=True)

        # no valid key: show HTML form so user can enter password or proceed without password
        # sanitize serial in HTML
        serial_safe = html.escape(serial)
        return Response(HTML_FORM.format(serial_safe=serial_safe, serial_escaped=serial_safe), mimetype="text/html")

    # POST flow: form submission
    serial = request.form.get("serial") or request.args.get("serial")
    if not serial:
        return jsonify({"error": "serial parameter required"}), 400

    no_pass = request.form.get("no_pass")  # 'on' if checked
    pw = request.form.get("pw", "")

    # Fetch AP
    ap_info = get_ap_info(serial=serial)
    if not ap_info:
        return abort(404, description="AP not found in Mist")

    # Decide role
    if no_pass:
        role = "public"
    else:
        role = validate_key_role(pw)
        if not role:
            # invalid password -> treat as public but you could also return 403
            role = "public"

    pdf_buffer = generate_pdf_for_role(ap_info, role=role)
    fname = f"{ap_info.get('name','AP')}_{ap_info.get('serial','')}_{role}.pdf"
    return send_file(pdf_buffer, download_name=fname, as_attachment=True)


# === Main ===
if __name__ == "__main__":
    # For local testing
    app.run(host="0.0.0.0", port=5001, debug=True)
