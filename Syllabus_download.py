import os
import sys
import time
import urllib.request
from urllib.parse import urlparse

class Logger(object):
    def __init__(self, filename="run.log"):
        self.terminal = sys.stdout
        self.log = open(filename, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger("run.log")
sys.stderr = sys.stdout
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import re

from selenium.webdriver.support.ui import Select

# === CONFIG ===
LOGIN_URL = "https://app.acadoinformatics.com/syllabus/department/portal"
from config import SYLLABUS_USERNAME as USERNAME, SYLLABUS_PASSWORD as PASSWORD
# Use a subfolder in current directory to avoid messing up the workspace
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# === SETUP DRIVER ===
options = webdriver.ChromeOptions()
prefs = {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "plugins.always_open_pdf_externally": True
}
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get(LOGIN_URL)
time.sleep(2)

# === LOGIN STEP ===
driver.find_element(By.NAME, "username").send_keys(USERNAME)
driver.find_element(By.NAME, "password").send_keys(PASSWORD)
driver.find_element(By.NAME, "password").send_keys(Keys.ENTER)
time.sleep(3)

# === NAVIGATE TO COURSE COMPLETION ===
# Similar to clicking "Download Course Syllabi..."
try:
    link = driver.find_element(By.PARTIAL_LINK_TEXT, "Download Course Syllabi")
    link.click()
    time.sleep(3)
except Exception as e:
    print(f"❌ Could not find/click Syllabi link: {e}")
    exit(1)

# (wait_for_download removed in favor of direct urllib download)

def sanitize_filename(name):
    """Sanitizes strings to be safe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

# === HELPER: CHECK LOGIN & NAVIGATION ===
def ensure_on_portal():
    """Checks if we are on the tool page; if logged out, logs back in."""
    try:
        # Check if we are on login page
        if len(driver.find_elements(By.NAME, "username")) > 0:
            print("⚠️ Session expired. Logging in again...")
            driver.find_element(By.NAME, "username").send_keys(USERNAME)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            driver.find_element(By.NAME, "password").send_keys(Keys.ENTER)
            time.sleep(3)
        
        # Check if we need to navigate to the tool
        if len(driver.find_elements(By.ID, "select-semester")) == 0:
            print("🔄 Navigating to Course Completion tool...")
            driver.get("https://app.acadoinformatics.com/syllabus/department/tools/CourseCompletion")
            time.sleep(3)
            
            # Double check login after nav
            if len(driver.find_elements(By.NAME, "username")) > 0:
                 print("⚠️ Redirected to login. Logging in...")
                 driver.find_element(By.NAME, "username").send_keys(USERNAME)
                 driver.find_element(By.NAME, "password").send_keys(PASSWORD)
                 driver.find_element(By.NAME, "password").send_keys(Keys.ENTER)
                 time.sleep(3)
                 
    except Exception as e:
        print(f"❌ Error in session check: {e}")

# === GET SEMESTER OPTIONS ===
print("Fetching semester list...")
ensure_on_portal()

try:
    semester_select_elem = driver.find_element(By.ID, "select-semester")
    select = Select(semester_select_elem)
    semester_options_count = len(select.options)
    print(f"Found {semester_options_count} semesters.")
except Exception as e:
    print(f"❌ Could not find semester dropdown: {e}")
    exit(1)

# === BUILD RECORD DICT ACROSS ALL SEMESTERS ===
latest_entries = {}

# Iterate through all options
for i in range(semester_options_count):
    try:
        ensure_on_portal()
        
        # Re-find element to avoid StaleElementReferenceException
        semester_select_elem = driver.find_element(By.ID, "select-semester")
        select = Select(semester_select_elem)
        
        if i >= len(select.options):
            break
            
        option = select.options[i]
        semester_text = option.text
        
        if "Select" in semester_text:
            continue

        print(f"[{i+1}/{semester_options_count}] Scanning: {semester_text}")
        select.select_by_index(i)
        
        # Wait for table reload
        time.sleep(2) # Reduced sleep slightly for speed, but keep it safe

        # Scrape all tables (subcategories)
        subheaders = driver.find_elements(By.CSS_SELECTOR, "h3.table-title")
        count_for_sem = 0
        
        for subheader in subheaders:
            try:
                subcategory = subheader.text.strip()
                table = subheader.find_element(By.XPATH, "following-sibling::table[1]")
                rows = table.find_elements(By.TAG_NAME, "tr")
                
                for row in rows:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) < 5:
                            continue

                        # Column 0: Course Name
                        course_name = cells[0].text.strip()
                        
                        # Check for link
                        if len(cells[1].find_elements(By.TAG_NAME, "a")) == 0:
                            continue
                            
                        # Column 4: Date
                        date_uploaded = cells[4].text.strip()

                        # We store the Tpl (semester, subcategory, course)
                        # Note: We don't need 'row' object here anymore since we re-scrape later
                        # But loop expects it. We'll store None for row to save memory/confusion
                        key = (semester_text, subcategory, course_name)
                        latest_entries[key] = (None, date_uploaded, semester_text, subcategory)
                        count_for_sem += 1

                    except Exception:
                        pass
                        
            except Exception:
                pass
        
        if count_for_sem > 0:
            print(f"   -> Found {count_for_sem} syllabi.")

    except Exception as e:
        print(f"⚠️ Error processing semester index {i}: {e}")

# === PRINT SUMMARY ===
print("\n🗂️ Total Entries Found (to be downloaded):")
print(f"Total: {len(latest_entries)}\n")

# Removing input() to allow full automation
# x = input("Hit enter to start downloading")

# === DOWNLOAD ===
# Strategy: Group by semester to minimize switching
entries_by_semester = {}
for (sem_key, subcat_key, course_key), (_, date, sem, subcat) in latest_entries.items():
    if sem not in entries_by_semester:
        entries_by_semester[sem] = []
    entries_by_semester[sem].append((course_key, date, subcat))

print("Starting download process (grouped by semester)...")

TOOL_URL = "https://app.acadoinformatics.com/syllabus/department/tools/CourseCompletion"
failed_entries = []

for semester_text, courses in entries_by_semester.items():
    try:
        print(f"\n📂 Processing Semester: {semester_text}")
        ensure_on_portal()
        
        # Navigate to semester
        semester_select_elem = driver.find_element(By.ID, "select-semester")
        Select(semester_select_elem).select_by_visible_text(semester_text)
        time.sleep(3)
        
        # Re-scrape table in this semester context
        rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
        
        # Map current rows by course name for easy lookup
        current_semester_map = {}
        for r in rows:
            try:
                c_name = r.find_elements(By.TAG_NAME, "td")[0].text.strip()
                current_semester_map[c_name] = r
            except:
                pass
            
        # Download targeted courses
        for (course_name, date, subcat) in courses:
            # Note: We need to find the correct row again.
            # But wait, 'current_semester_map' was built by scanning the whole page again?
            # Re-scanning logic needs to be robust for subcategories too.
            
            if course_name in current_semester_map:
                try:
                    row_elem = current_semester_map[course_name]
                    cells = row_elem.find_elements(By.TAG_NAME, "td")
                    download_link = cells[1].find_element(By.TAG_NAME, "a")

                    # Check existence BEFORE download
                    safe_semester = sanitize_filename(semester_text.strip())
                    safe_subcat = sanitize_filename(subcat.strip())
                    target_dir = os.path.join(DOWNLOAD_DIR, safe_semester, safe_subcat)
                    safe_course = sanitize_filename(course_name)
                    
                    # Assume PDF for checking existence to save time
                    check_path = os.path.join(target_dir, f"{safe_course}.pdf")
                    
                    if os.path.exists(check_path):
                         print(f"⏩ Skipping {course_name} (already exists)")
                         continue

                    # If we are here, we need to download
                    os.makedirs(target_dir, exist_ok=True)
                    
                    file_url = download_link.get_attribute("href")
                    filename = os.path.basename(urlparse(file_url).path)
                    _, ext = os.path.splitext(filename)
                    if not ext:
                        ext = ".pdf"
                        
                    # New Filename
                    new_name = f"{safe_course}{ext}"
                    new_path = os.path.join(target_dir, new_name)
                    
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            urllib.request.urlretrieve(file_url, new_path)
                            print(f"✅ Downloaded to {safe_semester}/{safe_subcat}/: {new_name}")
                            break
                        except Exception as download_err:
                            if attempt < max_retries - 1:
                                print(f"   ⚠️ Download failed ({download_err}). Retrying {attempt + 1}/{max_retries}...")
                                time.sleep(2)
                            else:
                                raise download_err

                except TimeoutError:
                     print(f"❌ Timeout/Missing File for {course_name}. Checking for AWS Error...")
                     failed_entries.append(f"| {semester_text} | {subcat} | {course_name} | Timeout/File Missing/AWS Error |")

                     # If the click navigated us to an AWS error page, we need to go back
                     if "CourseCompletion" not in driver.current_url:
                         print("   ↩️ AWS Error Page detected. Going back...")
                         driver.back()
                         # Wait for page to be ready again
                         time.sleep(3)
                         
                         # Since we went back, the DOM might be stale.
                         # We can't continue smoothly without refreshing the map or relying on the outer loop re-check.
                         # But since we are iterating a map of *Elements*, they are definitely stale now!
                         # We MUST break the inner loop or re-fetch rows.
                         # Simple fix: Re-fetch the rows for the CURRENT semester context.
                         
                         # Re-fetching current_semester_map logic inline or marking a flag?
                         # Actually, if we go back, we are still in the 'processing semester' block.
                         # We can try to recover the specific row?
                         # No, simplest is to just LOG it and let the next iteration try. 
                         # BUT the next iteration uses `current_semester_map` elements which are STALE.
                         # Critical Fix: We need to re-find rows if we navigated away.
                         
                         print("   ⚠️ DOM is stale. Re-scanning current view...")
                         rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
                         current_semester_map = {}
                         for r in rows:
                            try:
                                c_name = r.find_elements(By.TAG_NAME, "td")[0].text.strip()
                                current_semester_map[c_name] = r
                            except:
                                pass
                         continue

                except Exception as e:
                    print(f"❌ Failed download {course_name}: {e}")
                    failed_entries.append(f"| {semester_text} | {subcat} | {course_name} | Error: {str(e)} |")
                    
                    # Check if we need to recover from navigation or stale element
                    needs_rescan = False
                    
                    if "stale element reference" in str(e).lower():
                         needs_rescan = True
                         print("   ⚠️ Stale Element detected.")

                    if "CourseCompletion" not in driver.current_url:
                        print("   ↩️ Navigated away (Error Page?). Going back...")
                        driver.back()
                        time.sleep(3)
                        needs_rescan = True
                    
                    if needs_rescan:
                        print("   🔄 Re-scanning DOM to fix stale references...")
                        rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
                        current_semester_map = {}
                        for r in rows:
                            try:
                                c_name = r.find_elements(By.TAG_NAME, "td")[0].text.strip()
                                current_semester_map[c_name] = r
                            except:
                                pass
                        continue
            else:
                print(f"⚠️ Could not find row for {course_name} in current view.")
                failed_entries.append(f"| {semester_text} | {subcat} | {course_name} | Row not found in re-scan |")

    except Exception as e:
        print(f"❌ Error handling semester {semester_text}: {e}")


print("Done.")

# === GENERATE REPORT ===
if failed_entries:
    report_path = "missing_syllabi_report.md"
    with open(report_path, "w") as f:
        f.write("# Missing Syllabi Report\n\n")
        f.write(f"Total Missing: {len(failed_entries)}\n\n")
        f.write("| Semester | Category | Course | Reason |\n")
        f.write("|---|---|---|---|\n")
        for entry in failed_entries:
            f.write(entry + "\n")
    print(f"\n📄 Report generated: {report_path}")
else:
    print("\n✅ All syllabi downloaded successfully!")

