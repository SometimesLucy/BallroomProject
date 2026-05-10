"""
This program pulls all comps and their associated result url for all years listed
Only run if updating CompURLS.json. Otherwise can just load from there
"""

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import json

# Selenium code commented out due to lack of need
"""
driver = webdriver.Chrome()
driver.implicitly_wait(10)
driver.get("https://results.o2cm.com/")
year_field = driver.find_element(By.ID, "fy")
year_field.send_keys('2022')
go_button = driver.find_element(By.CSS_SELECTOR, "#FilterList input[type='submit']")
go_button.click()
print(driver.current_url)
"""

comp_dict = {}

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

year_list = ['2022', '2023', '2024', '2025', '2026']

for year in year_list:
    url = 'https://results.o2cm.com/default.asp?fFilter=1&fy=' + year + '&fm=&Go=Go'
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    tables = soup.find_all('table')
    for row in tables[0].find_all('tr'):
        if row.find("td", class_="year-header") != None:
            comp_dict[row.get_text(strip=True)] = {}
            year = row.get_text(strip=True)

        if row.find('a') != None:
            comp_dict[year][row.find('a').get_text(strip=True)] = row.find('a')['href']

with open("CompURLS.json", 'w') as file:
    json.dump(comp_dict, file)