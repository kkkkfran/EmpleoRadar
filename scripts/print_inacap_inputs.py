import urllib.request

from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
req = urllib.request.Request('https://emplea.inacap.cl/trabajo/trabajos-en-chile', headers=headers)
html = urllib.request.urlopen(req, timeout=12).read().decode('utf-8')
soup = BeautifulSoup(html, 'html.parser')

inputs = soup.find_all(['input', 'select'])
for inp in inputs:
    name = inp.get('name')
    if name and 'Search' in name:
        print(f"Input: {name} (type: {inp.get('type')})")
        if inp.name == 'select':
            options = inp.find_all('option')
            print("  Options count:", len(options), [(o.get('value'), o.get_text().strip()) for o in options[:5]])
