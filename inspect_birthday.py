"""Drive through Microsoft's mobile signup until the 'Add some details'
page, then dump the actual DOM of the birthday widgets so we can write
selectors against the real markup."""

import json, time, shutil, sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from fake_data import generate_fake_data
from check_email import check_email


def build_driver():
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    })
    opts.add_experimental_option("mobileEmulation", {
        "deviceMetrics": {"width": 412, "height": 915, "pixelRatio": 2.625, "touch": True},
        "userAgent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36"
        ),
    })
    opts.add_argument("--window-size=432,1035")
    opts.binary_location = shutil.which("chromium")
    return webdriver.Chrome(
        service=Service(executable_path=shutil.which("chromedriver")),
        options=opts,
    )


def safe_click(d, el):
    try:
        d.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        el.click()
    except Exception:
        d.execute_script("arguments[0].click();", el)


def wait(d, selector, by=By.CSS_SELECTOR, t=20):
    return WebDriverWait(d, t).until(EC.presence_of_element_located((by, selector)))


def click_next(d):
    for sel in [
        (By.ID, "nextButton"),
        (By.CSS_SELECTOR, "button[data-testid='primaryButton']"),
        (By.CSS_SELECTOR, "button[type='submit']"),
    ]:
        try:
            btn = d.find_element(*sel)
            if btn.is_displayed():
                safe_click(d, btn)
                return
        except Exception:
            continue
    raise RuntimeError("no Next button found")


def main():
    login, password, first_name, last_name, birth_date = generate_fake_data()
    email = login + "@outlook.com"
    print(f"[*] Generated email: {email}")
    print(f"[*] Generated password: {password}")
    print(f"[*] Generated name: {first_name} {last_name}")
    print(f"[*] Generated birthdate: {birth_date}")

    avail = check_email(email)
    if not avail.get("isAvailable"):
        print(f"[!] {email} not available, regenerating once ...")
        login, password, first_name, last_name, birth_date = generate_fake_data()
        email = login + "@outlook.com"

    d = build_driver()
    try:
        d.get("https://signup.live.com/signup?lic=1")
        time.sleep(3)

        # Email
        e = wait(d, "input[type='email'], input#usernameInput, input[name='Username']")
        e.clear()
        e.send_keys(email)
        click_next(d)
        print("[+] Submitted email")
        time.sleep(3)

        # Password
        p = wait(d, "input[type='password'], #Password")
        p.clear()
        p.send_keys(password)
        click_next(d)
        print("[+] Submitted password")
        time.sleep(3)

        # Possible name page
        try:
            fn = WebDriverWait(d, 8).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "#firstNameInput, input[aria-label='First name'], "
                     "input[autocomplete='given-name']")
                )
            )
            fn.clear()
            fn.send_keys(first_name)
            ln = d.find_element(
                By.CSS_SELECTOR,
                "#lastNameInput, input[aria-label='Last name'], "
                "input[autocomplete='family-name']",
            )
            ln.clear()
            ln.send_keys(last_name)
            click_next(d)
            print("[+] Submitted name")
            time.sleep(3)
        except Exception:
            print("[*] No name page, continuing")

        # We should now be on the 'Add some details' page.
        time.sleep(3)
        print("\n" + "=" * 70)
        print("CURRENT URL:", d.current_url)
        print("PAGE TITLE :", d.title)
        print("=" * 70)

        # 1. Find the birth-date controls
        print("\n--- All buttons with role=combobox ---")
        for el in d.find_elements(By.CSS_SELECTOR, "[role='combobox']"):
            print({
                "tag": el.tag_name,
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "aria-label": el.get_attribute("aria-label"),
                "value": el.get_attribute("value") or el.text,
            })

        print("\n--- All <select> elements ---")
        for el in d.find_elements(By.TAG_NAME, "select"):
            print({
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "aria-label": el.get_attribute("aria-label"),
            })

        print("\n--- All inputs ---")
        for el in d.find_elements(By.TAG_NAME, "input"):
            t = el.get_attribute("type")
            if t in ("hidden", "submit", "button"):
                continue
            print({
                "type": t,
                "id": el.get_attribute("id"),
                "name": el.get_attribute("name"),
                "aria-label": el.get_attribute("aria-label"),
                "placeholder": el.get_attribute("placeholder"),
                "autocomplete": el.get_attribute("autocomplete"),
            })

        # 2. Click the Month dropdown and dump the popup
        print("\n--- Opening MONTH dropdown ---")
        try:
            month_btn = d.find_element(
                By.CSS_SELECTOR,
                "[id='BirthMonthDropdown'], [name='BirthMonth'], "
                "button[aria-label='Birth month']",
            )
            safe_click(d, month_btn)
            time.sleep(1.5)
            opts = d.find_elements(By.CSS_SELECTOR, "[role='option']")
            print(f"Found {len(opts)} option elements after opening month")
            for i, o in enumerate(opts[:15]):
                print(f"  [{i}] tag={o.tag_name} text={o.text!r} "
                      f"data-value={o.get_attribute('data-value')!r} "
                      f"value={o.get_attribute('value')!r}")
            # Listbox structure
            for lb in d.find_elements(By.CSS_SELECTOR, "[role='listbox']"):
                print(f"  listbox id={lb.get_attribute('id')!r} "
                      f"aria-label={lb.get_attribute('aria-label')!r}")
            # Save HTML of body for offline inspection
            with open("/tmp/page_with_month_open.html", "w") as f:
                f.write(d.page_source)
            print("Saved page source to /tmp/page_with_month_open.html")
            # Close it
            d.find_element(By.TAG_NAME, "body").click()
            time.sleep(1)
        except Exception as e:
            print(f"[!] Month dropdown probe failed: {e}")

        # 3. Click Day
        print("\n--- Opening DAY dropdown ---")
        try:
            day_btn = d.find_element(
                By.CSS_SELECTOR,
                "[id='BirthDayDropdown'], [name='BirthDay'], "
                "button[aria-label='Birth day']",
            )
            safe_click(d, day_btn)
            time.sleep(1.5)
            opts = d.find_elements(By.CSS_SELECTOR, "[role='option']")
            print(f"Found {len(opts)} option elements after opening day")
            for i, o in enumerate(opts[:15]):
                print(f"  [{i}] tag={o.tag_name} text={o.text!r}")
            d.find_element(By.TAG_NAME, "body").click()
            time.sleep(1)
        except Exception as e:
            print(f"[!] Day dropdown probe failed: {e}")

        # 4. Year — figure out if combobox or input
        print("\n--- Locating YEAR control ---")
        for sel in [
            "[id='BirthYearDropdown']",
            "[name='BirthYear']",
            "button[aria-label='Birth year']",
            "input[aria-label='Birth year']",
            "input[placeholder='Year']",
        ]:
            for el in d.find_elements(By.CSS_SELECTOR, sel):
                print(f"  selector {sel!r} -> tag={el.tag_name} "
                      f"id={el.get_attribute('id')!r} "
                      f"role={el.get_attribute('role')!r}")

        print("\n[*] Inspection finished. Sleeping 5s for screenshot ...")
        time.sleep(5)
    finally:
        try:
            d.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
