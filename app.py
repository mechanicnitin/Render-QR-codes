from flask import Flask, jsonify
import os
import requests

app = Flask(__name__)

# Mist token should be set in Render → Environment Variables
MIST_TOKEN = os.getenv("MIST_TOKEN")
SITE_ID = os.getenv("SITE_ID")  # Store site_id in Render too

@app.route("/")
def home():
    return jsonify({"message": "Mist QR API is running 🚀"})

@app.route("/ap_status/<ap_mac>")
def get_ap_status(ap_mac):
    """Fetch live AP status using Mist API"""
    if not MIST_TOKEN:
        return jsonify({"error": "Mist token not set"}), 401
    if not SITE_ID:
        return jsonify({"error": "SITE_ID not set"}), 401

    url = f"https://api.mist.com/api/v1/sites/{SITE_ID}/stats/devices/{ap_mac}"
    headers = {"Authorization": f"Token {MIST_TOKEN}"}

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

    return resp.json()

if __name__ == "__main__":
    # For local debugging, not used on Render
    app.run(host="0.0.0.0", port=5000, debug=True)
