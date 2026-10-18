import re
import urllib.request

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
for script_name in [
    "resultadoOfertas.js",
    "buscadorOfertas.js",
    "listaOfertasBNE.js"
]:
    url = f"https://www.bne.cl/static/scripts/js/public/ofertas/{script_name}" if "lista" in script_name or "resultado" in script_name else f"https://www.bne.cl/static/scripts/js/public/{script_name}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            js = resp.read().decode('utf-8', errors='ignore')
            endpoints = re.findall(r'[\'"](/[a-zA-Z0-9_\-\/]+)[\'"]', js)
            print(f"=== {script_name} ===")
            print("Ajax / endpoints found:", [e for e in set(endpoints) if any(k in e for k in ['oferta', 'buscar', 'recuperar', 'list', 'data'])])
    except Exception as e:
        print(f"Error {script_name}: {e}")
