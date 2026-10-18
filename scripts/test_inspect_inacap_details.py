import urllib.request

from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://emplea.inacap.cl/trabajo/trabajos-en-chile"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    html = resp.read().decode('utf-8', errors='ignore')
soup = BeautifulSoup(html, 'html.parser')

offers = soup.find_all(lambda tag: tag.name == 'a' and '/oferta-de-trabajo/' in tag.get('href', ''))
print(f"Total offer links: {len(offers)}")

seen = set()
for a in offers:
    href = a.get('href')
    if href in seen:
        continue
    seen.add(href)
    # Find card container
    parent = a.find_parent(class_=lambda c: c and any(k in str(c) for k in ['item', 'card', 'box', 'oferta', 'job', 'list']))
    if not parent:
        parent = a.parent.parent.parent
    title = parent.find(['h1', 'h2', 'h3', 'h4', 'h5', 'strong'])
    print(f"URL: https://emplea.inacap.cl{href}")
    print(f"Title: {title.get_text().strip() if title else 'No title'}")
    print(f"Full text snippet: {parent.get_text(separator=' | ').strip()[:150]}")
    print("="*40)
    if len(seen) >= 5:
        break
