import os
import shutil
import zipfile
import json
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from fake_data import generate_fake_data
from check_email import check_email


with open('config.json', 'r') as f:
    config = json.load(f)

PROXY_HOST = config.get('proxy_host', '')
PROXY_PORT = config.get('proxy_port', '')
PROXY_USER = config.get('username', '')
PROXY_PASS = config.get('password', '')
HEADLESS = bool(config.get('headless', False))
MOBILE = bool(config.get('mobile_emulation', True))
DEVICE_NAME = config.get('device_name', 'Pixel 7')
CAPTCHA_WAIT = int(config.get('manual_captcha_wait_seconds', 600))
TAKEOVER_WAIT = int(config.get('manual_takeover_wait_seconds', 900))
ACCOUNTS_TO_CREATE = int(config.get('accounts_to_create', 0))
PAUSE_BETWEEN = int(config.get('pause_between_accounts_seconds', 5))

NOVNC_URL = os.environ.get('NOVNC_URL', '').strip()

# A few realistic mobile profiles. Selenium's mobileEmulation accepts either
# a built-in Chrome device name OR a custom deviceMetrics + userAgent block.
DEVICE_PROFILES = {
    "Pixel 7": {
        "deviceMetrics": {"width": 412, "height": 915, "pixelRatio": 2.625, "touch": True},
        "userAgent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36"
        ),
    },
    "iPhone 14 Pro": {
        "deviceMetrics": {"width": 393, "height": 852, "pixelRatio": 3.0, "touch": True},
        "userAgent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        ),
    },
    "Samsung Galaxy S22": {
        "deviceMetrics": {"width": 360, "height": 780, "pixelRatio": 3.0, "touch": True},
        "userAgent": (
            "Mozilla/5.0 (Linux; Android 13; SM-S901U) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36"
        ),
    },
}


def banner(msg):
    print("=" * 64)
    print(msg)
    print("=" * 64)


def create_proxy_extension_v3(proxy_host, proxy_port, username=None, password=None):
    """Build a small Chrome extension that routes traffic through a proxy
    (with optional basic auth)."""
    manifest_json = """
{
    "version": "1.0.0",
    "manifest_version": 3,
    "name": "proxy_auth",
    "permissions": [
        "proxy", "tabs", "unlimitedStorage", "storage",
        "webRequest", "webRequestAuthProvider"
    ],
    "host_permissions": ["<all_urls>"],
    "background": { "service_worker": "background.js" },
    "minimum_chrome_version": "108"
}
"""
    background_js = """
var config = {
    mode: "fixed_servers",
    rules: {
        singleProxy: { scheme: "http", host: "%s", port: %s },
        bypassList: ["localhost"]
    }
};
chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
""" % (proxy_host, proxy_port)

    if username and password:
        background_js += """
function callbackFn(details) {
    return { authCredentials: { username: "%s", password: "%s" } };
}
chrome.webRequest.onAuthRequired.addListener(
    callbackFn, { urls: ["<all_urls>"] }, ['blocking']
);
""" % (username, password)

    pluginfile = 'proxy_auth_plugin.zip'
    with zipfile.ZipFile(pluginfile, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    return pluginfile


def build_driver():
    chrome_options = Options()
    chrome_options.add_argument("--lang=en")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    # Stop Chromium from popping its own "Save password?" dialog, which
    # otherwise covers Microsoft's form during the birth-date step.
    chrome_options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.password_manager_leak_detection": False,
        "autofill.profile_enabled": False,
    })
    chrome_options.add_argument("--password-store=basic")
    chrome_options.add_argument("--disable-features=PasswordManagerOnboarding,AutofillServerCommunication")

    if MOBILE:
        profile = DEVICE_PROFILES.get(DEVICE_NAME, DEVICE_PROFILES["Pixel 7"])
        chrome_options.add_experimental_option("mobileEmulation", profile)
        # A phone-shaped window so the chrome around the page also looks mobile.
        w = profile["deviceMetrics"]["width"]
        h = profile["deviceMetrics"]["height"]
        chrome_options.add_argument(f"--window-size={w + 20},{h + 120}")
    else:
        chrome_options.add_argument("--window-size=1280,900")

    if HEADLESS:
        chrome_options.add_argument("--headless=new")

    mode = config.get('mode', 0)
    if mode == 1:
        print(f"[*] Proxy: {PROXY_HOST}:{PROXY_PORT} (no auth)")
        chrome_options.add_extension(create_proxy_extension_v3(PROXY_HOST, PROXY_PORT))
    elif mode == 2:
        print(f"[*] Proxy: {PROXY_HOST}:{PROXY_PORT} (with auth)")
        chrome_options.add_extension(
            create_proxy_extension_v3(PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASS)
        )
    else:
        print("[*] No proxy")

    browser_path = (
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if browser_path and "/snap/" in os.path.realpath(browser_path):
        print("[!] Detected snap-packaged browser at "
              f"{os.path.realpath(browser_path)}.\n"
              "    Snap Chromium does not work with Selenium. Install\n"
              "    Google Chrome (.deb) instead — see run_vps.sh.")
    if browser_path:
        chrome_options.binary_location = browser_path

    chromedriver_path = shutil.which("chromedriver")
    if chromedriver_path:
        return webdriver.Chrome(service=Service(executable_path=chromedriver_path),
                                options=chrome_options)
    return webdriver.Chrome(options=chrome_options)


# ---------------------------------------------------------------------------
# Helpers that try several selectors, since Microsoft's signup HTML changes.
# ---------------------------------------------------------------------------

def first_present(driver, selectors, timeout=20):
    """Wait until any one of the (by, value) selectors is present, return it."""
    end = time.time() + timeout
    last_err = None
    while time.time() < end:
        for by, value in selectors:
            try:
                el = driver.find_element(by, value)
                if el.is_displayed():
                    return el
            except Exception as e:
                last_err = e
        time.sleep(0.5)
    raise TimeoutException(f"None of the selectors became visible: {selectors}")


def click_next(driver):
    """Click whatever 'Next' / primary submit button is visible right now."""
    candidates = [
        (By.ID, "nextButton"),
        (By.CSS_SELECTOR, "button[data-testid='primaryButton']"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[normalize-space()='Next']"),
        (By.XPATH, "//input[@type='submit']"),
    ]
    btn = first_present(driver, candidates, timeout=15)
    btn.click()


def fill(driver, selectors, value, timeout=20):
    el = first_present(driver, selectors, timeout=timeout)
    el.clear()
    el.send_keys(value)
    return el


MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def safe_click(driver, el):
    """Click that survives overlapping labels / animations by falling back
    to a JavaScript click."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)


def select_fluent_option(driver, button_selectors, option_text, timeout=20):
    """Open a Fluent UI <button role='combobox'> dropdown and click the
    option whose textContent equals `option_text`.

    Verified against the real Microsoft mobile signup DOM:
      - Listbox is rendered with role='listbox' (id like 'fluent-listboxNN')
      - Options have role='option' and their text is in nested spans, so
        Selenium's `.text` returns '' for off-screen virtualized rows.
        Using JS textContent matches reliably.
    """
    btn = first_present(driver, button_selectors, timeout=timeout)
    # Open via JS — bypasses the overlapping <label> click intercept.
    driver.execute_script("arguments[0].click();", btn)
    time.sleep(0.6)

    # Try several times to find + click the option (listbox can take a moment
    # to render after the click).
    end = time.time() + 10
    while time.time() < end:
        clicked = driver.execute_script("""
            const wanted = arguments[0];
            // Pick the most recently opened, currently visible listbox.
            const lbs = Array.from(document.querySelectorAll('[role=listbox]'))
                .filter(lb => lb.offsetParent !== null);
            const target = lbs[lbs.length - 1] || document;
            for (const opt of target.querySelectorAll('[role=option]')) {
                if ((opt.textContent || '').trim() === wanted) {
                    opt.scrollIntoView({block: 'center'});
                    opt.click();
                    return true;
                }
            }
            return false;
        """, option_text)
        if clicked:
            time.sleep(0.4)
            return True
        time.sleep(0.4)
    raise TimeoutException(f"Couldn't click Fluent option {option_text!r}")


def select_value(driver, selectors, value, label=None, timeout=20):
    """Hybrid select: native <select>, Fluent UI combobox button, or input."""
    el = first_present(driver, selectors, timeout=timeout)
    tag = el.tag_name.lower()
    role = (el.get_attribute("role") or "").lower()

    if tag == "select":
        Select(el).select_by_value(str(value))
        return

    if tag == "input":
        el.clear()
        el.send_keys(str(value))
        return

    if role == "combobox" or tag == "button":
        select_fluent_option(driver, selectors,
                             label if label is not None else str(value),
                             timeout=timeout)
        return

    # Fallback: try clicking it like a button
    safe_click(driver, el)


# ---------------------------------------------------------------------------
# Manual fallback. Instead of restarting and closing the window the user is
# trying to look at, we PAUSE so they can finish the step in the visible
# browser (which is exactly what they're already doing for the captcha).
# ---------------------------------------------------------------------------

def _browser_hint():
    if NOVNC_URL:
        return (f"    >>> Open this link in YOUR phone or laptop browser: <<<\n"
                f"    {NOVNC_URL}\n")
    return "    Use the browser preview pane to continue.\n"


def wait_for_user(driver, reason, success_selectors, timeout):
    banner(f"[!] MANUAL STEP NEEDED — {reason}\n"
           f"\n"
           f"{_browser_hint()}"
           f"    Finish this step yourself, then the script will continue.\n"
           f"    Waiting up to {timeout}s for the next page to load ...")
    end = time.time() + timeout
    while time.time() < end:
        for by, value in success_selectors:
            try:
                for el in driver.find_elements(by, value):
                    if el.is_displayed():
                        print("[+] Detected next page, resuming automation.")
                        return True
            except Exception:
                pass
        time.sleep(2)
    print("[!] Manual takeover window expired.")
    return False


# ---------------------------------------------------------------------------

class AccGen:
    def __init__(self):
        self.driver = None

    def open_signup_page(self):
        if self.driver is None:
            self.driver = build_driver()
        self.driver.get('https://signup.live.com/signup?lic=1')
        time.sleep(3)

    def fill_signup_form(self):
        d = self.driver

        # Step 1 — email
        try:
            login = password_value = first_name = last_name = None
            birth_date = None
            email = None

            # Some flows show a "use existing email" toggle first. Click it
            # if it's there; ignore if it isn't.
            try:
                d.find_element(By.ID, "liveSwitch").click()
                time.sleep(1)
            except Exception:
                pass

            email_selectors = [
                (By.ID, "usernameInput"),
                (By.NAME, "Username"),
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[name='MemberName']"),
                (By.CSS_SELECTOR, "input[autocomplete='username']"),
            ]

            # Make sure the email field is actually there before we burn cycles
            # generating addresses.
            first_present(d, email_selectors, timeout=20)

            while True:
                login, password_value, first_name, last_name, birth_date = generate_fake_data()
                email = login + "@outlook.com"
                try:
                    check = check_email(email) or {}
                except Exception as e:
                    print(f"[!] availability check failed ({e}); retrying.")
                    continue
                if check.get('isAvailable'):
                    print(f"[+] {email} is available")
                    break
                print(f"[-] {email} is taken")

            # Microsoft's current form expects the full address, not just the
            # local part — typing only `login` triggers a format error.
            fill(d, email_selectors, email)
            click_next(d)
        except TimeoutException:
            wait_for_user(
                d, "could not find the email field on Microsoft's page",
                [(By.ID, "Password"), (By.CSS_SELECTOR, "input[type='password']")],
                TAKEOVER_WAIT,
            )
            return

        # Step 2 — password
        try:
            password_selectors = [
                (By.ID, "Password"),
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.CSS_SELECTOR, "input[name='Password']"),
                (By.CSS_SELECTOR, "input[aria-label='Password']"),
                (By.CSS_SELECTOR, "input[autocomplete='new-password']"),
            ]
            fill(d, password_selectors, password_value)
            click_next(d)

            try:
                WebDriverWait(d, 2).until(
                    EC.presence_of_element_located((By.ID, "PasswordError"))
                )
                print("[!] Password rejected by Microsoft, regenerating ...")
                self.driver.get('https://signup.live.com/signup?lic=1')
                return self.fill_signup_form()
            except TimeoutException:
                pass
        except TimeoutException:
            wait_for_user(
                d, "password step did not appear",
                [(By.ID, "firstNameInput"), (By.NAME, "FirstName")],
                TAKEOVER_WAIT,
            )

        # Step 3 — name page (Microsoft sometimes skips it; that's fine)
        first_name_selectors = [
            (By.ID, "firstNameInput"), (By.NAME, "FirstName"),
            (By.CSS_SELECTOR, "input[aria-label='First name']"),
            (By.CSS_SELECTOR, "input[name='firstNameInput']"),
            (By.CSS_SELECTOR, "input[autocomplete='given-name']"),
        ]
        last_name_selectors = [
            (By.ID, "lastNameInput"), (By.NAME, "LastName"),
            (By.CSS_SELECTOR, "input[aria-label='Last name']"),
            (By.CSS_SELECTOR, "input[name='lastNameInput']"),
            (By.CSS_SELECTOR, "input[autocomplete='family-name']"),
        ]
        try:
            fill(d, first_name_selectors, first_name, timeout=8)
            print(f"[+] Filled first name: {first_name}")
            fill(d, last_name_selectors, last_name, timeout=5)
            print(f"[+] Filled last name: {last_name}")
            click_next(d)
            print("[+] Submitted name page")
            time.sleep(2)
        except TimeoutException:
            print("[*] Name page not present, continuing to details page.")

        # Step 4 — Birth date — REAL Microsoft mobile DOM:
        #   Month: <button id="BirthMonthDropdown" name="BirthMonth"
        #                  role="combobox" aria-label="Birth month">
        #          options: textContent in {'January'..'December'}
        #   Day:   <button id="BirthDayDropdown"   name="BirthDay"
        #                  role="combobox" aria-label="Birth day">
        #          options: textContent in {'1'..'31'}
        #   Year:  <input type="number" name="BirthYear" aria-label="Birth year">
        try:
            month_selectors = [
                (By.ID, "BirthMonthDropdown"),
                (By.NAME, "BirthMonth"),
                (By.CSS_SELECTOR, "button[aria-label='Birth month']"),
            ]
            day_selectors = [
                (By.ID, "BirthDayDropdown"),
                (By.NAME, "BirthDay"),
                (By.CSS_SELECTOR, "button[aria-label='Birth day']"),
            ]
            year_selectors = [
                (By.NAME, "BirthYear"),
                (By.CSS_SELECTOR, "input[aria-label='Birth year']"),
                (By.CSS_SELECTOR, "input[type='number'][name='BirthYear']"),
            ]

            month_label = MONTH_NAMES[birth_date.month]
            print(f"[*] Selecting birth month: {month_label}")
            select_fluent_option(d, month_selectors, month_label)
            print(f"[+] Birth month set to {month_label}")
            time.sleep(0.6)

            day_label = str(birth_date.day)
            print(f"[*] Selecting birth day: {day_label}")
            select_fluent_option(d, day_selectors, day_label)
            print(f"[+] Birth day set to {day_label}")
            time.sleep(0.6)

            year_label = str(birth_date.year)
            print(f"[*] Typing birth year: {year_label}")
            fill(d, year_selectors, year_label)
            print(f"[+] Birth year set to {year_label}")
            time.sleep(0.5)

            print(f"[+] BIRTHDATE FILLED: {month_label} {day_label}, {year_label}")
            click_next(d)
            print("[+] Submitted birthdate page")
            time.sleep(2)

            # Microsoft has been observed to show the name page AFTER the
            # birthdate page. Try once more here.
            try:
                fill(d, first_name_selectors, first_name, timeout=8)
                print(f"[+] Filled first name (post-birthdate): {first_name}")
                fill(d, last_name_selectors, last_name, timeout=5)
                print(f"[+] Filled last name (post-birthdate): {last_name}")
                click_next(d)
                print("[+] Submitted name page (post-birthdate)")
                time.sleep(2)
            except TimeoutException:
                print("[*] No name page after birthdate either, continuing.")

        except TimeoutException as e:
            print(f"[!] Birth-date controls didn't appear in time: {e}")
            wait_for_user(
                d, "please complete the birthdate manually and tap Next",
                [(By.XPATH,
                  "//iframe[contains(@src,'arkoselabs') or contains(@src,'enforcement')]"
                  " | //*[contains(text(), 'Press and hold')]"
                  " | //*[contains(text(), 'puzzle')]")],
                TAKEOVER_WAIT,
            )
        except Exception as e:
            print(f"[!] Birth-date automation hit an error ({e}).")
            wait_for_user(
                d, "please complete the birthdate manually and tap Next",
                [(By.XPATH,
                  "//iframe[contains(@src,'arkoselabs') or contains(@src,'enforcement')]"
                  " | //*[contains(text(), 'Press and hold')]"
                  " | //*[contains(text(), 'puzzle')]")],
                TAKEOVER_WAIT,
            )

        # Step 5 — SMS check (we just bail; that means IP is flagged)
        try:
            WebDriverWait(d, 8).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//label[contains(text(), "Phone number")]')
                )
            )
            banner("[!] Microsoft is asking for SMS verification.\n"
                   "    Your IP/proxy is flagged. Change network and try again.")
            return
        except TimeoutException:
            pass

        # Step 6 — captcha (manual). Confirm the challenge actually appeared
        # before counting down, so we know we really got there.
        captcha_present_xpath = (
            "//iframe[contains(@src,'arkoselabs') or contains(@src,'enforcement')"
            " or contains(@src,'fc/') or contains(@src,'funcaptcha')]"
            " | //*[contains(translate(text(), 'PRESHOLD', 'preshold'), 'press and hold')]"
            " | //*[@id='enforcementFrame']"
            " | //*[contains(text(), 'puzzle')]"
        )
        try:
            WebDriverWait(d, 30).until(
                EC.presence_of_element_located((By.XPATH, captcha_present_xpath))
            )
            banner(f"[+] CAPTCHA appeared — your turn!\n"
                   f"\n"
                   f"{_browser_hint()}"
                   f"    Press and hold the puzzle button until it finishes.\n"
                   f"    Waiting up to {CAPTCHA_WAIT}s for you ...")
        except TimeoutException:
            print("[!] Captcha challenge did not appear within 30s — Microsoft\n"
                  "    may have shown a different verification step. Continuing\n"
                  "    to wait for the success page anyway.")

        success_xpath = (
            "//*[contains(text(), 'Welcome')]"
            " | //*[contains(text(), 'Stay signed in')]"
            " | //a[contains(@href, 'outlook.live.com')]"
            " | //a[contains(@href, 'outlook.office')]"
            " | //a[contains(@href, 'account.microsoft')]"
        )
        try:
            WebDriverWait(d, CAPTCHA_WAIT).until(
                lambda dr: (
                    "account.microsoft.com" in dr.current_url
                    or "outlook.live.com" in dr.current_url
                    or "outlook.office.com" in dr.current_url
                    or len(dr.find_elements(By.XPATH, success_xpath)) > 0
                )
            )
        except TimeoutException:
            print("[!] Captcha wait expired without seeing a success page.")
            return

        banner(f"[+] ACCOUNT CREATED SUCCESSFULLY!\n"
               f"    Email:    {email}\n"
               f"    Password: {password_value}\n"
               f"    Final URL: {d.current_url}")
        with open('generated.txt', 'a') as f:
            if os.path.exists('generated.txt') and os.path.getsize('generated.txt') > 0:
                f.write("\n")
            f.write(f"Email: {email}\n")
            f.write(f"Password: {password_value}\n")
        print("[+] Saved to generated.txt")

    def run_once(self):
        self.open_signup_page()
        self.fill_signup_form()


def main():
    target = "unlimited" if ACCOUNTS_TO_CREATE == 0 else str(ACCOUNTS_TO_CREATE)
    banner(f" Outlook Account Generator — Mobile Build\n"
           f" Device:        {DEVICE_NAME if MOBILE else 'desktop'}\n"
           f" Headless:      {HEADLESS}\n"
           f" Accounts:      {target}\n"
           f" Output file:   generated.txt\n"
           f" Solve captcha: {NOVNC_URL or '(use the browser preview pane)'}")

    n = 0
    try:
        while ACCOUNTS_TO_CREATE == 0 or n < ACCOUNTS_TO_CREATE:
            n += 1
            banner(f" >>> Creating account #{n} <<<")
            gen = AccGen()
            try:
                gen.run_once()
            except WebDriverException as e:
                print(f"[!] Browser error: {e}")
            except Exception as e:
                print(f"[!] Unexpected error: {e}")
            finally:
                if gen.driver:
                    try:
                        gen.driver.quit()
                    except Exception:
                        pass

            done = ACCOUNTS_TO_CREATE != 0 and n >= ACCOUNTS_TO_CREATE
            if not done:
                print(f"\n[*] Next account in {PAUSE_BETWEEN}s ...  "
                      f"(press Ctrl-C to stop)\n")
                time.sleep(PAUSE_BETWEEN)
    except KeyboardInterrupt:
        print("\n[*] Stopped by user.")

    banner(f" All done. Created {n} account(s).\n"
           f" Saved to generated.txt")


if __name__ == '__main__':
    main()
