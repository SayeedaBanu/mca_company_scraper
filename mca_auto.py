import cv2              # Gotta use this for image stuff
import numpy as np      # NumPy for array magic
import pytesseract      # OCR tool, hope it works!
import time             # For those little pauses
import logging          # Logging to see what's up
import os               # File handling, you know
from PIL import Image   # PIL for image conversion
from selenium import webdriver  # Web automation, cool stuff
from selenium.webdriver.common.by import By  # For finding elements
from selenium.webdriver.support.ui import WebDriverWait  # Waiting game
from selenium.webdriver.support import expected_conditions as EC  # Conditions to check
from selenium.webdriver.chrome.options import Options  # Chrome options, nice
from typing import Optional, Dict  # Type hints, kinda fancy
import tempfile        # Temp files, temporary chaos
import re              # Regex for text validation

# My config, tweaked it a bit
CONFIG = {
    "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",  # Where Tesseract lives
    "url": "https://www.mca.gov.in/content/mca/global/en/mca/master-data/MDS.html",  # The site to hit
    "company_name": "Google",  # Company to search
    "max_retries": 5,  # Give it a few tries, why not?
    "retry_delay": 2,  # Wait a couple seconds between tries
    "timeout": 20,     # Max wait time, seems reasonable
    "output_file": "output.txt",  # Where to save the goods
    "log_file": "captcha_solver.log",  # Log everything here
    "headless": True   # Run it quiet, less screen clutter
}

# Set up logging, gotta track this mess
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG["log_file"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)  # My logger buddy

# Preprocess the captcha, my first attempt
def preprocess_captcha(image_path):  
    # Load the image and hope it works
    try:
        img_data = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img_data is None:
            raise ValueError("Oops, couldn't load the image!")

        # Make it bigger, might help the OCR
        img_data = cv2.resize(img_data, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        # Boost the contrast, makes it pop
        img_data = cv2.convertScaleAbs(img_data, alpha=1.5, beta=0)

        # Find those annoying lines and zap them
        edges = cv2.Canny(img_data, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=10, maxLineGap=10)
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(img_data, (x1, y1), (x2, y2), (255, 255, 255), 2)

        # Threshold it, magic numbers here
        binary_img = cv2.adaptiveThreshold(
            img_data, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )

        # Clean it up a bit
        kernel = np.ones((2, 2), np.uint8)
        binary_img = cv2.dilate(binary_img, kernel, iterations=1)
        binary_img = cv2.erode(binary_img, kernel, iterations=1)

        # Smooth it out
        binary_img = cv2.GaussianBlur(binary_img, (3, 3), 0)

        # Save for a peek, if I feel like it
        debug_path = "processed_captcha.png"
        cv2.imwrite(debug_path, binary_img)
        logger.debug(f"Saved processed image to {debug_path}")

        return binary_img
    except Exception as e:
        logger.error(f"Something went wrong preprocessing: {e}")
        raise

# Another way to preprocess, just in case
def preprocess_captcha_alternative(image_path):  
    # Different approach, let's see
    try:
        img_data = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img_data is None:
            raise ValueError("Image load failed again!")

        # Scale it up and sharpen, feels right
        img_data = cv2.resize(img_data, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        sharpen_kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        img_data = cv2.filter2D(img_data, -1, sharpen_kernel)

        # Try Otsu's method, sounds smart
        _, binary_img = cv2.threshold(img_data, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Clean up the noise
        kernel = np.ones((2, 2), np.uint8)
        binary_img = cv2.morphologyEx(binary_img, cv2.MORPH_CLOSE, kernel)

        # Save this one too, for fun
        debug_path = "processed_captcha_alt.png"
        cv2.imwrite(debug_path, binary_img)
        logger.debug(f"Saved alternative image to {debug_path}")

        return binary_img
    except Exception as e:
        logger.error(f"Alternative preprocess failed: {e}")
        raise

# Try to crack the captcha
def solve_captcha(captcha_element, temp_dir):  
    # Grab the image and process it
    try:
        captcha_path = os.path.join(temp_dir, "captcha.png")
        captcha_element.screenshot(captcha_path)
        logger.info(f"Got the captcha image at {captcha_path}")

        # First shot at it
        processed_img = preprocess_captcha(captcha_path)
        ocr_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        captcha_text = pytesseract.image_to_string(
            Image.fromarray(processed_img),
            config=ocr_config
        ).strip()

        # If it’s junk, try the backup
        if not captcha_text or not re.match(r'^[a-zA-Z0-9]{4,6}$', captcha_text):
            logger.warning("First try didn’t work, switching gears")
            processed_img = preprocess_captcha_alternative(captcha_path)
            captcha_text = pytesseract.image_to_string(
                Image.fromarray(processed_img),
                config=ocr_config
            ).strip()

        logger.info(f"Think I got: {captcha_text}")
        return captcha_text if captcha_text and re.match(r'^[a-zA-Z0-9]{4,6}$', captcha_text) else None
    except Exception as e:
        logger.error(f"Captcha solve blew up: {e}")
        return None

# The main automation class, my creation
class MCACaptchaSolver:
    def __init__(self, config):
        # Set up my stuff
        self.config = config
        self.driver = None
        self.temp_dir = tempfile.mkdtemp()

        # Check if Tesseract is where I left it
        pytesseract.pytesseract.tesseract_cmd = self.config["tesseract_path"]
        if not os.path.exists(self.config["tesseract_path"]):
            raise FileNotFoundError(f"Can't find Tesseract at {self.config['tesseract_path']}")

    def setup_driver(self):  
        # Get the browser ready
        chrome_opts = Options()
        if self.config["headless"]:
            chrome_opts.add_argument("--headless")
            chrome_opts.add_argument("--disable-gpu")
        chrome_opts.add_argument("--no-sandbox")
        chrome_opts.add_argument("--disable-dev-shm-usage")
        self.driver = webdriver.Chrome(options=chrome_opts)
        logger.info("Browser is up, let’s go!")

    def automate(self):  
        # Do the whole thing
        try:
            self.setup_driver()
            self.driver.get(self.config["url"])
            wait = WebDriverWait(self.driver, self.config["timeout"])

            # Click that view link, here we go
            view_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "View Company/LLP Master Data")))
            view_link.click()
            logger.info("Made it to the captcha page")

            # Type in the company name
            company_input = wait.until(EC.presence_of_element_located((By.ID, "companyLLPMasterData_CompanyName")))
            company_input.send_keys(self.config["company_name"])
            logger.info(f"Typed in {self.config['company_name']}")

            # Crack the captcha, fingers crossed
            captcha_img = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "img.captcha-img")))
            captcha_text = None
            for attempt in range(self.config["max_retries"]):
                captcha_text = solve_captcha(captcha_img, self.temp_dir)
                if captcha_text:
                    break
                logger.warning(f"Attempt {attempt + 1} failed, trying again...")
                try:
                    refresh_button = self.driver.find_element(By.ID, "captchaRefresh")
                    if refresh_button.is_displayed():
                        refresh_button.click()
                        time.sleep(self.config["retry_delay"])
                        captcha_img = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "img.captcha-img")))
                except:
                    logger.debug("No refresh button or it’s hiding")
                time.sleep(self.config["retry_delay"] * (2 ** attempt))

            if not captcha_text:
                raise Exception(f"Give up, couldn’t get captcha after {self.config['max_retries']} tries")

            # Submit the form, hope it works
            captcha_input = self.driver.find_element(By.ID, "companyLLPMasterData_captcha")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            submit_button = self.driver.find_element(By.ID, "companyLLPMasterData_0")
            submit_button.click()
            logger.info("Form sent, waiting...")

            # Grab the results
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            with open(self.config["output_file"], "w", encoding="utf-8") as file:
                file.write(self.driver.page_source)
            logger.info(f"Saved results to {self.config['output_file']}")

        except Exception as e:
            logger.error(f"Oops, something broke: {e}")
            raise
        finally:
            self.cleanup()

    def cleanup(self):  
        # Clean up my mess
        if self.driver:
            self.driver.quit()
            logger.info("Closed the browser")
        try:
            for file in os.listdir(self.temp_dir):
                os.remove(os.path.join(self.temp_dir, file))
            os.rmdir(self.temp_dir)
            logger.debug(f"Cleaned up temp folder {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Couldn’t clean up files: {e}")

# Run it, let’s see what happens
def main():
    try:
        solver = MCACaptchaSolver(CONFIG)
        solver.automate()
    except Exception as e:
        logger.error(f"Main run failed: {e}")
        raise

if __name__ == "__main__":
    main()