import urllib.request

from bs4 import BeautifulSoup


def check_bne():
    print("--- Checking BNE ---")
    urls = [
        "https://www.bne.cl",
        "https://www.bne.gob.cl",
        "https://www.bne.cl/ofertas-empleo",
        "https://www.bne.gob.cl/ofertas-empleo",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for u in urls:
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"[BNE] {u} -> Status {resp.status}, final: {resp.geturl()}")
        except Exception as e:
            print(f"[BNE] {u} -> Error: {e}")

def check_inacap():
    print("--- Checking INACAP ---")
    urls = [
        "https://inacap.trabajando.cl",
        "https://empleaxchile.cl",
        "https://empleaxchile.cl/ofertas-laborales",
        "https://emplea.inacap.cl",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for u in urls:
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                print(f"[INACAP] {u} -> Status {resp.status}, len {len(html)}")
                soup = BeautifulSoup(html, 'html.parser')
                offers = soup.find_all(lambda tag: tag.name in ['div', 'a', 'article'] and any('oferta' in str(c).lower() or 'job' in str(c).lower() for c in (tag.get('class') or [])))
                print(f"[INACAP] Found potential offer elements: {len(offers)}")
        except Exception as e:
            print(f"[INACAP] {u} -> Error: {e}")

if __name__ == "__main__":
    check_bne()
    check_inacap()
