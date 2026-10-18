import urllib.request

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://www.bne.cl/static/scripts/js/public/ofertas/listaOfertasBNE.js"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    js = resp.read().decode('utf-8', errors='ignore')

lines = js.splitlines()
for i, line in enumerate(lines):
    if 'URL_OFERTAS' in line:
        for j in range(max(0, i-5), min(len(lines), i+40)):
            print(lines[j])
        break

