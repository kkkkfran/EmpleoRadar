import urllib.request

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://www.bne.cl/static/scripts/js/public/ofertas/listaOfertasBNE.js"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    js = resp.read().decode('utf-8', errors='ignore')

for line in js.splitlines():
    if 'buscarListas' in line or 'ajax' in line.lower() or 'url:' in line:
        print(line[:120])
