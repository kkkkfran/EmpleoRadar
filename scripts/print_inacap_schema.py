import json
import urllib.request

from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
url = "https://emplea.inacap.cl/trabajo/trabajos-en-chile"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=12) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

soup = BeautifulSoup(html, 'html.parser')
for s in soup.find_all('script', type='application/ld+json'):
    try:
        data = json.loads(s.string)
        print("Schema JSON type:", data.get('@type'))
        if 'itemListElement' in data:
            print("Items count:", len(data['itemListElement']))
            for item in data['itemListElement'][:3]:
                print(item)
        elif data.get('@type') == 'JobPosting':
            print("JobPosting:", data.get('title'), data.get('datePosted'))
        elif 'mainEntity' in data:
            print("Main entity:", data['mainEntity'])
    except Exception as e:
        print("Error parsing schema:", e)
