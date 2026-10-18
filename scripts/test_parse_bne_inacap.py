import urllib.request

from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def test_bne_ofertas():
    print("=== Testing BNE /ofertas ===")
    url = "https://www.bne.cl/ofertas?mostrar=empleo&numPaginaRecuperar=1&numResultadosPorPagina=20&clasificarYPaginar=true"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            # Look for job cards
            cards = soup.find_all(class_=lambda c: c and any(w in str(c).lower() for w in ['card', 'oferta', 'item', 'result']))
            print(f"HTML len: {len(html)}, cards found: {len(cards)}")
            # Let's inspect some links in soup
            job_links = [a['href'] for a in soup.find_all('a', href=True) if 'oferta' in a['href'].lower()]
            print("Job links found in BNE:", len(job_links), job_links[:5])
    except Exception as e:
        print("BNE error:", e)

def test_inacap_ofertas():
    print("=== Testing Emplea INACAP /trabajo/trabajos-en-chile ===")
    url = "https://emplea.inacap.cl/trabajo/trabajos-en-chile"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            cards = soup.find_all(class_=lambda c: c and any(w in str(c).lower() for w in ['card', 'oferta', 'item', 'job', 'box']))
            print(f"HTML len: {len(html)}, cards found: {len(cards)}")
            job_links = [a['href'] for a in soup.find_all('a', href=True) if '/trabajo/' in a['href'] or '/oferta/' in a['href']]
            print("Job links found in INACAP:", len(job_links), job_links[:5])
    except Exception as e:
        print("INACAP error:", e)

if __name__ == "__main__":
    test_bne_ofertas()
    test_inacap_ofertas()
