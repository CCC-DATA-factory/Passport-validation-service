import os
import requests
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configuration
main_url = "https://passportcloud.net/passport.html"
save_folder = "passport_images"
alt_pattern = re.compile(r"^[A-Za-z\s]+ Passport-1$", re.IGNORECASE)  # Case-insensitive match

# Your Edge configuration
driver_path = r"C:\Users\atef nasri\Documents\SeleniumDrivers/msedgedriver.exe"

def setup_driver():
    """Configure Edge WebDriver with your specific settings"""
    edge_options = EdgeOptions()
    edge_options.add_argument("start-maximized")
    
    # Create service with your driver path
    service = EdgeService(executable_path=driver_path)
    
    # Initialize driver with your configuration
    driver = webdriver.Edge(service=service, options=edge_options)
    driver.implicitly_wait(10)
    return driver

def process_page(driver, url):
    """Process individual passport page and download valid images"""
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "img"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
        img_tags = soup.find_all("img", onclick=True)
        
        for img in img_tags:
            alt_text = img.get("alt", "").strip()
            if not alt_pattern.match(alt_text):
                print(f"Skipping {url}: Alt '{alt_text}' doesn't match pattern")
                continue
                
            # Extract image URL from onclick attribute
            onclick = img.get("onclick", "")
            if not onclick or "'" not in onclick:
                continue
                
            img_path = onclick.split("'")[1]
            img_url = urljoin(url, img_path)
            download_image(img_url, alt_text)

    except Exception as e:
        print(f"Error processing {url}: {str(e)}")

def download_image(url, filename):
    """Download and save an image with error handling"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Sanitize filename
        with open(os.path.join(save_folder, f"{safe_filename}.jpg"), "wb") as f:
            f.write(response.content)
        print(f"Downloaded: {safe_filename}")
    except Exception as e:
        print(f"Failed to download {filename}: {str(e)}")

def main():
    driver = setup_driver()
    os.makedirs(save_folder, exist_ok=True)
    
    try:
        driver.get(main_url)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Get unique item links
        passport_links = {
            urljoin(main_url, a["href"]) 
            for a in soup.find_all("a", href=lambda h: h and "items/" in h)
        }
        
        for link in passport_links:
            process_page(driver, link)
            
    finally:
        driver.quit()
        print("Processing completed. Check downloaded images in:", save_folder)

if __name__ == "__main__":
    main()