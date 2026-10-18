import urllib.request

from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://emplea.inacap.cl/trabajo/trabajos-en-chile"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    html = resp.read().decode('utf-8', errors='ignore')
soup = BeautifulSoup(html, 'html.parser')

# Look for job links or articles
for a in soup.find_all('a', href=True):
    href = a['href']
    if '/oferta-de-trabajo/' in href or '/oferta/' in href or '/trabajo/' in href:
        text = a.get_text().strip()
        if len(text) > 5 and 'page=' not in href and text != 'Ver todas las ofertas':
            print("Link:", href)
            print("Text:", text[:80])
            print("---")
