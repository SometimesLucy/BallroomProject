from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import lxml

url = "https://results.o2cm.com/scoresheet3.asp?event=mit26&heatid=40328530&bclr=#FFFFFF&tclr=#000000"

parsed = urlparse(url)
params = parse_qs(parsed.query)
event = params.get("event", ["unknown"])[0]
heat_id = params.get("heatid", ["unknown"])[0]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

response = requests.get(url, headers=headers, timeout=15)
response.raise_for_status()
soup = BeautifulSoup(response.text, "lxml")

tables = soup.find_all("table")

results_dict = {}
dance_list = ['Waltz', 'Tango', 'Foxtrot', 'Viennese Waltz']

for table in tables:
    # Extracting tables that contain dance results based on first row containing dance name
    rows = table.find_all('tr')
    header_cells = rows[0].find_all(["th", "td"])
    try:
        #table_name = header_cells[0].get_text(strip=True)
        table_name = rows[0].get_text(strip=True)
    except:
        table_name = '' #Populated null value if no dance found

    if table_name == 'Couples':
        rows = [tr for tr in table.find_all('tr') if tr.find('td')]

        couples = {}
        judges = {}
        current_dict = None

        for row in rows:
            cells = row.find_all('td')
            code = cells[0].get_text(strip=True)
            name = cells[1].get_text(strip=True).split(" -")[0]

            if name == 'Couples':
                current_dict = couples
            elif name == 'Judges':
                current_dict = judges
            elif code and name and current_dict is not None:
                current_dict[code] = name

for table in tables:
    # Extracting tables that contain dance results based on first row containing dance name
    rows = table.find_all('tr')
    header_cells = rows[0].find_all(["th", "td"])
    try:
        #table_name = header_cells[0].get_text(strip=True)
        table_name = rows[0].get_text(strip=True)
    except:
        table_name = '' #Populated null value if no dance found

    if table_name in dance_list:
        results_dict[table_name] = {}
        # Extracting list of judge codes for each dance
        # Redundant to do for each dance in event fix later
        judge_list = []

        for i in range(1, len(rows)):
            items = rows[i].find_all('td')
            if i == 1:
                for j in range(1, len(items)):
                    item = items[j].get_text(strip=True)
                    if  item == '&nbsp':
                        break
                    else:
                        judge_list.append(item)

            else:
                results_dict[table_name][couples[items[0].get_text(strip=True)]] = {}
                for j in range(1, len(items)):
                    item = items[j].get_text(strip=True)
                    if item == '&nbsp':
                        break
                    else:
                        results_dict[table_name][couples[items[0].get_text(strip=True)]][judges[judge_list[j-1]]] = item

response = requests.get('https://results.o2cm.com/event3.asp?event=mit26&bclr=%23FFFFFF&tclr=%23000000', headers=headers, timeout=15)
response.raise_for_status()
soup = BeautifulSoup(response.text, "lxml")

rows = soup.find_all(href=True)
for row in rows:
    print(row['href'])