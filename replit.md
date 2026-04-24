# Outlook Account Generator (NopeCHA-free build)

A Selenium script that automates the Microsoft / Outlook signup flow.
The original project relied on the **NopeCHA** captcha-solving extension and
its paid API key. NopeCHA is no longer offered, so this build removes that
dependency entirely — captchas are now solved manually by the user in the
visible browser window.

## How it works on Replit

The workflow `Start application` runs `python3 main.py` with `outputType: vnc`.
Replit provides a virtual display and shows the Chromium window in the
preview pane, so you can solve Microsoft's puzzle yourself when prompted.
After you finish the captcha, the script detects the success page and saves
the credentials to `generated.txt`.

## Files

- `main.py` — main automation script (no NopeCHA references)
- `check_email.py` — checks whether a generated address is available
- `fake_data.py` — generates realistic names, passwords, birth dates
- `config.json` — proxy mode + headless flag + manual captcha timeout
- `requirements.txt` — selenium, faker, requests, fake-useragent

## config.json

```json
{
    "mode": 0,                          // 0 = no proxy, 1 = proxy, 2 = proxy+auth
    "proxy_host": "",
    "proxy_port": "",
    "username": "",
    "password": "",
    "headless": false,                  // keep false so you can solve the captcha
    "manual_captcha_wait_seconds": 600  // how long the script waits for you
}
```

## What was removed

- All `nopecha.com/f/ext.crx` downloads
- `chrome_options.add_extension('ext.crx')`
- `https://nopecha.com/setup#{api_key}` setup call
- The `api_key` config field

## What was added / fixed

- Uses the system Chromium + ChromeDriver (Nix-installed, version 138)
- `--no-sandbox`, `--disable-dev-shm-usage`, anti-automation flags
- Removed the duplicate "Next" click that broke the password step
- Robust success detection that works on multiple post-captcha pages
- `headless` is configurable but defaults to `false` (a human is required)

## System dependencies

- `chromium` (Nix)
- `chromedriver` (Nix)
- Python 3.11
