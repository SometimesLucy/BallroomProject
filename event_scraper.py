from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def event_scraper(URL):
    driver = webdriver.Chrome()
    wait = WebDriverWait(driver, 15)

    results = {}

    try:
        driver.get(URL)
        wait.until(EC.presence_of_element_located((By.ID, "selSkl")))

        # Get the list of skill option labels up front (excluding the blank "all" option)
        skill_select = Select(driver.find_element(By.ID, "selSkl"))
        skill_names = [opt.text.strip() for opt in skill_select.options if opt.get_attribute("value")]

        print(f"Found {len(skill_names)} skill levels: {skill_names}\n")

        for skill in skill_names:
            # Re-fetch the page fresh for each skill so filters don't compound
            driver.get(URL)
            wait.until(EC.presence_of_element_located((By.ID, "selSkl")))

            Select(driver.find_element(By.ID, "selSkl")).select_by_visible_text(skill)

            ok_button = driver.find_element(By.NAME, "submit")
            ok_button.click()
            wait.until(EC.staleness_of(ok_button))

            # Wait for either event links or the "too large" message / empty result
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='scoresheet3.asp']")))
            except Exception:
                # No events found for this skill level
                results[skill] = {}
                print(f"{skill}: 0 events found")
                continue

            event_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='scoresheet3.asp']")

            skill_dict = {}
            for link in event_links:
                name = link.text.strip()
                href = link.get_attribute("href")
                skill_dict[name] = href

            results[skill] = skill_dict
            print(f"{skill}: {len(skill_dict)} events found")

    finally:
        driver.quit()

if __name__ == "__main__":
    URL = "https://results.o2cm.com/event3.asp?event=mit26&bclr=%23FFFFFF&tclr=%23000000"
    event_scraper(URL)