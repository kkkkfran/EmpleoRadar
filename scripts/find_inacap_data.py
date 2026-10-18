import re
import urllib.request

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://emplea.inacap.cl/trabajo/trabajos-en-chile"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

scripts = re.findall(r'<script[^>]*src=[\"\\\']([^\"\\\']+)[\"\\\']', html)
print("Scripts in Emplea INACAP:", [s for s in scripts if 'app' in s or 'job' in s or 'search' in s or 'trabajo' in s])

# Look for embedded JSON or api calls in inline scripts
inline_scripts = re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>', html, re.DOTALL)
for s in inline_scripts:
    if 'oferta' in s or 'jobs' in s or 'Search' in s or 'api' in s:
        print("Inline script snippet:", s[:300])
        print("="*40)
