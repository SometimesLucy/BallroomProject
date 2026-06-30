"""
Full crawler for o2cm.com ballroom competition results.

Strategy:
  1. Fetch the homepage with requests to discover competitions.
  2. For each competition, use Selenium to open the event page and iterate
     through every dropdown option, collecting scoresheet links.
  3. Scrape each scoresheet with requests + BeautifulSoup.

Usage:
    python scrape_all.py
"""

from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
import time

BASE_URL = "https://results.o2cm.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
DANCE_LIST = ['Waltz', 'Tango', 'Foxtrot', 'Viennese Waltz']


# ---------------------------------------------------------------------------
# Scoresheet scraping (requests + BS4)
# ---------------------------------------------------------------------------

def scrape_scoresheet_dict(url):
    """Scrape an o2cm scoresheet and return results as a nested dict.

    Returns:
        {dance_name: {couple_name: {judge_name: placement}}}
    """
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    tables = soup.find_all("table")

    results_dict = {}
    couples = {}
    judges = {}

    # First pass: build couple/judge code-to-name lookup tables
    for table in tables:
        rows = table.find_all('tr')
        if not rows:
            continue
        table_name = rows[0].get_text(strip=True)

        if table_name == 'Couples':
            data_rows = [tr for tr in table.find_all('tr') if tr.find('td')]
            current_dict = None
            for row in data_rows:
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue
                code = cells[0].get_text(strip=True)
                name = cells[1].get_text(strip=True).split(" -")[0]
                if name == 'Couples':
                    current_dict = couples
                elif name == 'Judges':
                    current_dict = judges
                elif code and name and current_dict is not None:
                    current_dict[code] = name
            break

    # Second pass: extract per-dance scores
    for table in tables:
        rows = table.find_all('tr')
        if not rows:
            continue
        table_name = rows[0].get_text(strip=True)

        if table_name in DANCE_LIST:
            results_dict[table_name] = {}
            judge_list = []

            for i in range(1, len(rows)):
                items = rows[i].find_all('td')
                if i == 1:
                    for j in range(1, len(items)):
                        item = items[j].get_text(strip=True)
                        if item == '&nbsp':
                            break
                        judge_list.append(item)
                else:
                    couple_code = items[0].get_text(strip=True)
                    couple_name = couples.get(couple_code, couple_code)
                    results_dict[table_name][couple_name] = {}
                    for j in range(1, len(items)):
                        item = items[j].get_text(strip=True)
                        if item == '&nbsp':
                            break
                        judge_code = judge_list[j - 1]
                        judge_name = judges.get(judge_code, judge_code)
                        results_dict[table_name][couple_name][judge_name] = item

    return results_dict


# ---------------------------------------------------------------------------
# Homepage discovery (requests + BS4)
# ---------------------------------------------------------------------------

def get_competitions():
    """Fetch competition list from the o2cm homepage.

    Returns:
        list of dicts with keys 'name', 'code'
    """
    response = requests.get(BASE_URL + "/", headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    competitions = []
    seen_codes = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "event=" in href:
            params = parse_qs(urlparse(href).query)
            event_code = params.get("event", [None])[0]
            if event_code and event_code not in seen_codes:
                seen_codes.add(event_code)
                competitions.append({
                    "name": link.get_text(strip=True),
                    "code": event_code,
                })
    return competitions


# ---------------------------------------------------------------------------
# Event-page navigation (Selenium)
# ---------------------------------------------------------------------------

def _collect_scoresheet_links(driver):
    """Return all scoresheet hrefs visible on the current Selenium page."""
    links = []
    for element in driver.find_elements(By.TAG_NAME, "a"):
        href = element.get_attribute("href") or ""
        if "scoresheet" in href.lower() and "heatid=" in href:
            links.append(href)
    return links


def get_scoresheet_urls(driver, event_code, page_load_delay=1.5):
    """Use Selenium to navigate all dropdown options on an event page and
    collect every unique scoresheet URL.

    The event page at event3.asp has one or more <select> dropdowns that
    filter the displayed events by level/age/style.  We iterate every option
    in every dropdown, wait for the page to refresh, and harvest links.

    Args:
        driver: Active Selenium WebDriver instance.
        event_code: Competition code string, e.g. 'mit26'.
        page_load_delay: Seconds to wait after each dropdown change.

    Returns:
        Deduplicated list of full scoresheet URL strings.
    """
    event_url = f"{BASE_URL}/event3.asp?event={event_code}"
    driver.get(event_url)
    time.sleep(page_load_delay)

    all_urls = set()

    # Collect links already visible on the default page view
    all_urls.update(_collect_scoresheet_links(driver))

    # Find all dropdowns on the page
    select_elements = driver.find_elements(By.TAG_NAME, "select")
    if not select_elements:
        return list(all_urls)

    # Iterate through each dropdown independently
    for select_index in range(len(select_elements)):
        # Re-navigate to reset the page before working each dropdown
        driver.get(event_url)
        time.sleep(page_load_delay)

        selects = driver.find_elements(By.TAG_NAME, "select")
        if select_index >= len(selects):
            continue

        sel = Select(selects[select_index])
        num_options = len(sel.options)
        option_values = [opt.get_attribute("value") for opt in sel.options]
        option_labels = [opt.text for opt in sel.options]

        for i in range(num_options):
            # Re-find to avoid stale element references after page changes
            selects = driver.find_elements(By.TAG_NAME, "select")
            if select_index >= len(selects):
                break

            sel = Select(selects[select_index])
            sel.select_by_index(i)
            time.sleep(page_load_delay)

            links = _collect_scoresheet_links(driver)
            all_urls.update(links)
            print(f"    dropdown[{select_index}] '{option_labels[i]}': {len(links)} link(s)")

    return list(all_urls)


# ---------------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------------

def scrape_all_finals(request_delay=0.5, page_load_delay=1.5):
    """Crawl o2cm.com and scrape every final from every listed competition.

    Args:
        request_delay: Seconds between scoresheet HTTP requests.
        page_load_delay: Seconds to wait for Selenium page loads.

    Returns:
        {event_code: {"name": str, "finals": {heat_id: results_dict}}}
    """
    all_results = {}

    competitions = get_competitions()
    print(f"Found {len(competitions)} competition(s) on homepage.")

    driver = webdriver.Chrome()
    try:
        for comp in competitions:
            code = comp["code"]
            name = comp["name"]
            print(f"\n[{code}] {name}")

            scoresheet_urls = get_scoresheet_urls(driver, code, page_load_delay)
            print(f"  {len(scoresheet_urls)} unique scoresheet(s) found.")

            all_results[code] = {"name": name, "finals": {}}

            for url in scoresheet_urls:
                params = parse_qs(urlparse(url).query)
                heat_id = params.get("heatid", ["unknown"])[0]
                try:
                    result = scrape_scoresheet_dict(url)
                    all_results[code]["finals"][heat_id] = result
                    print(f"  Scraped heatid={heat_id} — dances: {list(result.keys())}")
                except Exception as e:
                    print(f"  ERROR heatid={heat_id}: {e}")
                time.sleep(request_delay)
    finally:
        driver.quit()

    return all_results


if __name__ == "__main__":
    results = scrape_all_finals()
    total_finals = sum(len(v["finals"]) for v in results.values())
    print(f"\nDone. Scraped {total_finals} final(s) across {len(results)} competition(s).")
