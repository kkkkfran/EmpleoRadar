import urllib.request

from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://www.bne.cl/ofertas?mostrar=empleo&numPaginaRecuperar=1&numResultadosPorPagina=20&clasificarYPaginar=true"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

soup = BeautifulSoup(html, 'html.parser')
# Find all h2, h3, h4 or links
print("Title:", soup.title.string if soup.title else "")
items = soup.find_all(lambda t: t.name in ['div', 'article', 'li'] and any(k in str(t.get('class', [])) for k in ['oferta', 'job', 'card', 'box-oferta', 'item']))
print("Items found:", len(items))
for idx, it in enumerate(items[:5]):
    print(f"--- Item {idx} ---")
    print("Classes:", it.get('class'))
    print("Text snippet:", it.get_text(separator=' | ').strip()[:200])

