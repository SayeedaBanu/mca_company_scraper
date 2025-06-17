from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

# Setup WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get("https://www.mca.gov.in/content/mca/global/en/mca/master-data/MDS.html")

wait = WebDriverWait(driver, 20)

try:
    # Wait for and switch to iframe if present (check and adjust)
    # Example if iframe exists:
    # iframe = wait.until(EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "MDS")]')))
    # driver.switch_to.frame(iframe)

    # Wait for company name input
    input_box = wait.until(EC.presence_of_element_located((By.ID, "companyLLPMasterData_CompanyName")))
    company_name = input("Enter the Company Name to search: ")
    input_box.send_keys(company_name)

    # Captcha: Give user 60 seconds to enter manually
    time.sleep(2)
    print("Please solve the Captcha manually within 60 seconds.")
    time.sleep(60)

    # Click Search button
    search_btn = driver.find_element(By.ID, "companyLLPMasterData_search")
    search_btn.click()

    # Wait for Result to load
    result = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "result-data")))  # Adjust if needed
    company_details = result.text

    # Save to output file
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(f"Company Searched: {company_name}\n\n")
        f.write(company_details)

    print("✅ Output saved to 'output.txt'")

except Exception as e:
    print(f"❌ Error occurred: {e}")

finally:
    input("Press Enter to close the browser...")
    driver.quit()
