import os
import shutil
import zipfile
import json
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from fake_data import generate_fake_data
from check_email import check_email


with open('config.json', 'r') as f:
    config = json.load(f)

proxy_host = config.get('proxy_host', '')
proxy_port = config.get('proxy_port', '')
username = config.get('username', '')
password = config.get('password', '')
HEADLESS = bool(config.get('headless', False))
CAPTCHA_WAIT = int(config.get('manual_captcha_wait_seconds', 600))


def create_proxy_extension_v3(proxy_host, proxy_port, username=None, password=None):
    """Build a small Chrome extension that routes traffic through a proxy
    (with optional basic auth)."""

    manifest_json = """
{
    "version": "1.0.0",
    "manifest_version": 3,
    "name": "proxy_auth",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "webRequest",
        "webRequestAuthProvider"
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


class AccGen:
    def __init__(self, proxy_host=None, proxy_port=None,
                 username=None, password=None):
        self.driver = None
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.username = username
        self.password = password

    def _build_chrome_options(self):
        chrome_options = Options()
        chrome_options.add_argument("--lang=en")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1280,900")
        chrome_options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )
        chrome_options.add_experimental_option("useAutomationExtension", False)

        if HEADLESS:
            # Headless mode is supported but Microsoft's captcha cannot be
            # solved without a human, so headless is strongly discouraged.
            chrome_options.add_argument("--headless=new")

        mode = config.get('mode', 0)
        if mode == 0:
            print("[*] Not using a proxy")
        elif mode == 1:
            print(f"[*] Using proxy {self.proxy_host}:{self.proxy_port} (no auth)")
            chrome_options.add_extension(
                create_proxy_extension_v3(self.proxy_host, self.proxy_port)
            )
        elif mode == 2:
            print(f"[*] Using proxy {self.proxy_host}:{self.proxy_port} (with auth)")
            chrome_options.add_extension(
                create_proxy_extension_v3(
                    self.proxy_host, self.proxy_port,
                    self.username, self.password
                )
            )
        return chrome_options

    def _build_driver(self):
        chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
        chromedriver_path = shutil.which("chromedriver")

        chrome_options = self._build_chrome_options()
        if chromium_path:
            chrome_options.binary_location = chromium_path

        if chromedriver_path:
            service = Service(executable_path=chromedriver_path)
            return webdriver.Chrome(service=service, options=chrome_options)
        return webdriver.Chrome(options=chrome_options)

    def open_signup_page(self):
        if self.driver is None:
            self.driver = self._build_driver()

        # Warm up so the proxy/extension settles before hitting Microsoft.
        self.driver.get('https://www.google.com')
        time.sleep(2)
        self.driver.get('https://signup.live.com/signup')
        time.sleep(2)

    def fill_signup_form(self):
        # The "use existing email" toggle (older flow). Click it if present.
        try:
            element = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.ID, "liveSwitch"))
            )
            element.click()
        except TimeoutException:
            pass

        email_input = WebDriverWait(self.driver, 30).until(
            EC.presence_of_element_located((By.ID, "usernameInput"))
        )

        # Find an available email
        login = first_name = last_name = None
        password_value = None
        birth_date = None
        email = None
        while True:
            login, password_value, first_name, last_name, birth_date = generate_fake_data()
            email = login + "@outlook.com"
            try:
                check = check_email(email) or {}
            except Exception as e:
                print(f"[!] Email availability check failed ({e}); retrying.")
                continue
            if check.get('isAvailable'):
                print(f"[+] {email} is available, continuing ...")
                break
            print(f"[-] {email} is taken, generating new one ...")

        email_input.send_keys(login)

        next_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "nextButton"))
        )
        next_button.click()

        password_input = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "Password"))
        )
        password_input.send_keys(password_value)

        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "nextButton"))
        ).click()

        # If Microsoft rejects the password, restart from the signup page.
        try:
            WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.ID, "PasswordError"))
            )
            print("[!] Password rejected, restarting ...")
            self.driver.get('https://signup.live.com/signup')
            return self.fill_signup_form()
        except TimeoutException:
            pass

        first_name_input = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "firstNameInput"))
        )
        first_name_input.send_keys(first_name)

        last_name_input = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "lastNameInput"))
        )
        last_name_input.send_keys(last_name)

        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "nextButton"))
        ).click()

        birth_month_select = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthMonth"))
        )
        Select(birth_month_select).select_by_value(str(birth_date.month))

        birth_day_select = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthDay"))
        )
        Select(birth_day_select).select_by_value(str(birth_date.day))

        birth_year_input = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthYear"))
        )
        birth_year_input.send_keys(str(birth_date.year))

        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "nextButton"))
        ).click()

        # If Microsoft demands SMS verification, the proxy/IP is flagged.
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//label[contains(text(), "Phone number")]')
                )
            )
            print("[!] SMS verification required. Change your IP/proxy and retry.")
            self.driver.quit()
            return
        except TimeoutException:
            pass

        # ------------------------------------------------------------------
        # Manual captcha step (no NopeCHA, no paid solvers).
        # The user must complete Microsoft's puzzle in the visible browser
        # window. We then wait for the post-captcha screen to appear.
        # ------------------------------------------------------------------
        print("=" * 60)
        print("[!] CAPTCHA STEP")
        print("    Please solve Microsoft's puzzle in the browser window.")
        print(f"    Waiting up to {CAPTCHA_WAIT} seconds for you to finish ...")
        print("=" * 60)

        success_xpath = (
            '//span[@class="ms-Button-label label-117" and @id="id__0"]'
            ' | //a[contains(@href, "outlook")]'
            ' | //*[contains(text(), "Welcome")]'
            ' | //*[contains(text(), "account.microsoft.com")]'
        )
        WebDriverWait(self.driver, CAPTCHA_WAIT).until(
            EC.presence_of_element_located((By.XPATH, success_xpath))
        )

        print("[+] Captcha cleared! Account created.")

        with open('generated.txt', 'a') as f:
            if os.path.exists('generated.txt') and os.path.getsize('generated.txt') > 0:
                f.write("\n")
            f.write(f"Email: {email}\n")
            f.write(f"Password: {password_value}\n")
        print("[+] Saved to generated.txt")

    def create_account(self):
        while True:
            try:
                self.open_signup_page()
                self.fill_signup_form()
                break
            except TimeoutException:
                print("[!] Timeout, restarting account creation ...")
                if self.driver is not None:
                    try:
                        self.driver.get('https://signup.live.com/signup')
                    except Exception:
                        pass


if __name__ == '__main__':
    print("=" * 60)
    print(" Outlook account generator (NopeCHA-free build)")
    print(" Captchas are solved manually in the visible browser window.")
    print("=" * 60)
    acc_gen = AccGen(
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        username=username,
        password=password,
    )
    acc_gen.create_account()
