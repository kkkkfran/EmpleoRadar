import re
import urllib.request

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://www.bne.cl/ofertas"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

scripts = re.findall(r'<script[^>]*src=[\"\\\']([^\"\\\']+)[\"\\\']', html)
print("Scripts found in BNE:", scripts)

# Look for API endpoints in the html
apis = re.findall(r'[\"\\\'](/[a-zA-Z0-9_\-\/]*api[a-zA-Z0-9_\-\/]*)[\"\\\']', html)
print("API endpoints in HTML:", set(apis))

# Search for endpoints matching ofertas
endpoints = re.findall(r'[\"\\\'](/[a-zA-Z0-9_\-\/]*oferta[a-zA-Z0-9_\-\/]*)[\"\\\']', html)
print("Ofertas endpoints in HTML:", set(endpoints))
