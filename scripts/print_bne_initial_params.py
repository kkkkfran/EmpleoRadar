import urllib.request

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://www.bne.cl/static/scripts/js/public/ofertas/listaOfertasBNE.js"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    js = resp.read().decode('utf-8', errors='ignore')

for line in js.splitlines():
    if '_criteriosBusqueda =' in line or 'var _criteriosBusqueda' in line:
        idx = js.find(line)
        print(js[idx:idx+1000])
        break
