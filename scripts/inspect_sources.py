import urllib.request

from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def inspect_page(url, name):
    print(f"=== {name} ({url}) ===")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            print("Title:", soup.title.string if soup.title else "No title")
            forms = soup.find_all('form')
            print("Forms count:", len(forms))
            for f in forms:
                print(" Form action:", f.get('action'), "method:", f.get('method'))
            links = set()
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(k in href.lower() for k in ['oferta', 'empleo', 'trabajo', 'postul', 'buscar', 'vacante']):
                    links.add((a.get_text().strip(), href))
            print(f"Relevant links ({len(links)}):")
            for text, href in list(links)[:10]:
                print(f" - [{text[:30]}] -> {href}")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    inspect_page("https://www.bne.cl", "BNE")
    inspect_page("https://emplea.inacap.cl", "Emplea INACAP")
    inspect_page("https://empleaxchile.cl", "Emplea X Chile")
