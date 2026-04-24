# Outlook Account Generator (NopeCHA-free, mobile build)

A Selenium script that automates the Microsoft / Outlook signup flow.
The original project relied on the **NopeCHA** captcha-solving extension and
its paid API key. NopeCHA is no longer offered, so this build removes that
dependency entirely:

- Browser runs as a **mobile phone** (Pixel 7 by default — viewport, touch,
  user agent), exactly like signing up from a real phone.
- The browser window is **visible inside Replit's preview pane** via the
  workflow `outputType: vnc` (a virtual display + VNC).
- Captchas are solved manually by the user in that visible window — no key,
  no third-party service, no fakery.
- When automation can't auto-fill a step (Microsoft A/B-tests their form
  HTML constantly), the script enters **manual-takeover mode** instead of
  restarting in a tight loop. The browser stays open and you finish the
  step yourself.

## How to use

1. Workflow `Start application` is configured as `python3 main.py` with
   `outputType: vnc`. It starts automatically.
2. Open the workspace **Preview / VNC** tab — you'll see Chromium emulating
   a Pixel 7, opening `signup.live.com/signup?lic=1`.
3. The script auto-fills email + password, then advances through the form.
4. When it reaches Microsoft's puzzle (or any step it can't auto-fill), the
   script prints a `[!] MANUAL TAKEOVER NEEDED` banner and waits up to
   900s for the next page to load — finish that step yourself.
5. Once the post-captcha success page appears, the email + password are
   appended to `generated.txt`.

## Files

- `main.py` — main automation script (no NopeCHA references)
- `check_email.py` — checks whether a generated address is available
- `fake_data.py` — generates realistic names, passwords, birth dates
- `config.json` — proxy + headless + mobile + timeout settings
- `requirements.txt` — selenium, faker, requests, fake-useragent
- `inspect_birthday.py` — diagnostic that drives to the details page and
  dumps the live birthday DOM (used to confirm real selectors).

## Verified Microsoft mobile-signup DOM (April 2026)

Page order observed: **email → password → birthdate → name → captcha**.
(Microsoft sometimes shuffles name/birthdate; the script tries name both
before and after birthdate.)

Birthdate page elements:

- Country: `<button id="countryDropdownId" role="combobox">` —
  pre-filled to `IN` based on egress IP, untouched.
- Month: `<button id="BirthMonthDropdown" name="BirthMonth"
  role="combobox" aria-label="Birth month">`
  - Listbox is virtualized; option `.text` is empty in Selenium.
  - Use `textContent` from JS to match `January`..`December`.
- Day: `<button id="BirthDayDropdown" name="BirthDay" role="combobox"
  aria-label="Birth day">` — options have plain text `1`..`31`.
- Year: `<input type="number" name="BirthYear"
  aria-label="Birth year">` — plain `send_keys`.

Captcha step is Arkose Labs "Press and hold" (no third-party solver).

## config.json

```json
{
    "mode": 0,                              // 0=no proxy, 1=proxy, 2=proxy+auth
    "proxy_host": "",
    "proxy_port": "",
    "username": "",
    "password": "",
    "headless": false,                      // keep false: a human solves captchas
    "mobile_emulation": true,               // emulate a phone
    "device_name": "Pixel 7",               // or "iPhone 14 Pro", "Samsung Galaxy S22"
    "manual_captcha_wait_seconds": 600,
    "manual_takeover_wait_seconds": 900
}
```

## What was removed

- All `nopecha.com/f/ext.crx` downloads
- `chrome_options.add_extension('ext.crx')`
- `https://nopecha.com/setup#{api_key}` setup call
- The `api_key` config field

## What was added / fixed

- System Chromium 138 + matching ChromeDriver (Nix-installed)
- Mobile emulation (Pixel 7 / iPhone 14 Pro / Galaxy S22 profiles)
- Hybrid `select_value` helper that handles both native `<select>`
  dropdowns and Microsoft's new custom button-based dropdowns
- `safe_click` JS-click fallback (bypasses overlapping label overlays)
- Multiple fallback selectors for every form step (id / name /
  aria-label / autocomplete / data-testid)
- Disabled Chromium's "Save password?" popup (was covering the form)
- Manual-takeover mode instead of restart loop, so the browser stays
  visible in the preview pane during interactive steps
- Browser persists at end of run for further inspection

## System dependencies

- `chromium` (Nix)
- `chromedriver` (Nix)
- Python 3.11
