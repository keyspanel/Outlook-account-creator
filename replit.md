# Outlook Account Generator (Mobile, Manual Captcha Only)

A Selenium script that automates the Microsoft / Outlook signup flow on a
mobile-emulated Chromium browser. **Everything is automatic except the
captcha** — the script fills email, password, name, and birthday, then
hands the puzzle to a human to press-and-hold through any normal browser.

## Three ways to run it

### 1. On a VPS (recommended — easiest, fastest, runs 24/7)

```bash
git clone <this-repo> outlook-gen
cd outlook-gen
./run_vps.sh
```

The launcher does everything for you:

- installs Chromium, Xvfb, x11vnc, noVNC, websockify if missing
- creates a Python virtualenv
- installs Python dependencies
- starts a virtual display, VNC server, and noVNC web bridge
- detects your VPS public IP
- prints **one URL** that you open in any phone or laptop browser to
  see and tap through the captcha
- starts the generator

Make sure port 6080 is open in your VPS firewall:

```bash
sudo ufw allow 6080/tcp
```

Stop with `Ctrl-C` — the launcher cleans up all the background services.

### 2. On Replit

The `Start application` workflow runs `python3 main.py` with
`outputType: vnc`, so the browser appears in the Replit Preview pane.
Solve the captcha there. Selenium plus Chromium are pre-installed via Nix.

### 3. On Termux (Android phone)

Install proot-distro and run Ubuntu inside Termux:

```bash
pkg install proot-distro
proot-distro install ubuntu
proot-distro login ubuntu
# inside Ubuntu:
git clone <this-repo> outlook-gen
cd outlook-gen
./run_vps.sh
```

Then open `http://localhost:6080/vnc.html` in your phone's Chrome app.

## What the script does for you automatically

| Step | Automatic |
|---|---|
| Opens Microsoft signup as a Pixel 7 | yes |
| Generates a unique available email address | yes |
| Generates a strong password | yes |
| Fills first name and last name | yes |
| Picks a random birthday — year **1980–2004**, valid month + day | yes |
| Submits each step | yes |
| **Solves the Arkose "press and hold" captcha** | **NO — you do this** |
| Saves the credentials to `generated.txt` | yes |
| Loops to create the next account | yes |

## Configuration (`config.json`)

```json
{
    "mode": 0,
    "proxy_host": "",
    "proxy_port": "",
    "username": "",
    "password": "",
    "headless": false,
    "mobile_emulation": true,
    "device_name": "Pixel 7",
    "manual_captcha_wait_seconds": 600,
    "manual_takeover_wait_seconds": 900,
    "birth_year_min": 1980,
    "birth_year_max": 2004,
    "accounts_to_create": 0,
    "pause_between_accounts_seconds": 5
}
```

Key settings:

- `accounts_to_create`: `0` = unlimited (loop until you press Ctrl-C),
  `1` = make one and stop, or any positive number for a fixed batch.
- `birth_year_min` / `birth_year_max`: random year range. Defaults to
  1980–2004. The month and day are also chosen randomly (with valid
  day-of-month for each month, leap years respected).
- `device_name`: `"Pixel 7"`, `"iPhone 14 Pro"`, or `"Samsung Galaxy S22"`.
- `mode`: `0` = no proxy, `1` = proxy without auth, `2` = proxy with auth.
- `manual_captcha_wait_seconds`: how long the script waits for you to
  solve the captcha before giving up (default 10 minutes).

## Files

- `run_vps.sh` — one-command launcher for VPS / Termux-Ubuntu
- `main.py` — the Selenium automation
- `fake_data.py` — generates realistic name, password, birthday
- `check_email.py` — checks whether a generated address is available
- `config.json` — all user-editable settings
- `requirements.txt` — Python dependencies
- `inspect_birthday.py` — diagnostic that dumps the live birthday DOM
- `generated.txt` — created at runtime, holds successful accounts

## Output

Each successful account is appended to `generated.txt`:

```
Email: someuser123@outlook.com
Password: SuperSecretPass99

Email: another456@outlook.com
Password: AnotherStrong42
```

## Notes / hardening

- The script never restarts on its own when an unexpected page appears —
  it switches to manual takeover mode so the visible browser stays open
  and you can finish the step yourself.
- For volume use, set a residential proxy in `config.json` (`mode: 1` or
  `2`). A bare VPS IP gets rate-limited by Microsoft fairly quickly.
- For security on a public VPS, prefer the SSH-tunnel pattern instead of
  exposing port 6080:
  ```bash
  ssh -L 6080:localhost:6080 root@YOUR_VPS_IP
  ```
  Then visit `http://localhost:6080/vnc.html` on your local machine.

## What was removed from earlier versions

- All NopeCHA references (extension, API key, paid solver)

## What was added / fixed

- One-command VPS launcher (`run_vps.sh`) with auto-install
- Multi-account loop with configurable batch size
- Random birthday in the 1980–2004 range with valid day-of-month
- Captcha banner now prints the exact noVNC URL to open in your browser
- Beginner-friendly startup banner showing device, target count, and
  the captcha URL
- Per-account browser session (clean state between accounts)
