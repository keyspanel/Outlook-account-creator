#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

RED='\033[0;31m'

say()  { echo -e "${CYAN}[*]${RESET} $*"; }
ok()   { echo -e "${GREEN}[+]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
fail() { echo -e "${RED}[x]${RESET} $*"; }

VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
DISPLAY_NUM="${DISPLAY_NUM:-:1}"
export DISPLAY="$DISPLAY_NUM"

if [ -z "${SCREEN_SIZE:-}" ]; then
    DEFAULT_SCREEN="1300x920x24"
    if [ -f config.json ] && command -v python3 >/dev/null 2>&1; then
        DETECTED="$(python3 - <<'PY' 2>/dev/null
import json, sys
try:
    cfg = json.load(open('config.json'))
except Exception:
    sys.exit(0)
mobile = bool(cfg.get('mobile_emulation', False))
device = cfg.get('device_name', 'Pixel 7')
profiles = {
    'Pixel 7':           (412, 915),
    'iPhone 14 Pro':     (393, 852),
    'Samsung Galaxy S22':(360, 780),
}
if mobile:
    w, h = profiles.get(device, (412, 915))
    print(f"{w + 30}x{h + 140}x24")
else:
    print("1300x920x24")
PY
)"
        if [ -n "$DETECTED" ]; then
            SCREEN_SIZE="$DETECTED"
        else
            SCREEN_SIZE="$DEFAULT_SCREEN"
        fi
    else
        SCREEN_SIZE="$DEFAULT_SCREEN"
    fi
fi

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    fi
fi

is_snap_path() {
    local b="$1"
    [ -z "$b" ] && return 1
    local real
    real="$(readlink -f "$b" 2>/dev/null || echo "$b")"
    [ "$real" = "/usr/bin/snap" ] && return 0
    [[ "$real" == */snap/* ]] && return 0
    [[ "$b" == /snap/* ]] && return 0
    return 1
}

snap_chromium_present() {
    [ -L /snap/bin/chromium ] && return 0
    [ -d /snap/chromium ] && return 0
    if command -v snap >/dev/null 2>&1; then
        snap list 2>/dev/null | awk '{print $1}' | grep -qx chromium && return 0
    fi
    return 1
}

find_real_browser() {
    local p
    for n in google-chrome google-chrome-stable; do
        p="$(command -v "$n" 2>/dev/null || true)"
        if [ -n "$p" ] && ! is_snap_path "$p"; then
            echo "$p"
            return 0
        fi
    done
    for n in chromium chromium-browser; do
        p="$(command -v "$n" 2>/dev/null || true)"
        if [ -n "$p" ] && ! is_snap_path "$p"; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

find_browser() {
    find_real_browser \
        || command -v chromium 2>/dev/null \
        || command -v chromium-browser 2>/dev/null \
        || true
}

is_snap_browser() {
    is_snap_path "$1" && return 0
    snap_chromium_present && return 0
    return 1
}

install_google_chrome() {
    say "Installing Google Chrome (.deb) — works reliably with Selenium ..."
    $SUDO apt-get install -y wget gnupg ca-certificates >/dev/null
    wget -qO /tmp/google-chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    $SUDO apt-get install -y /tmp/google-chrome.deb || {
        $SUDO apt-get install -f -y
        $SUDO dpkg -i /tmp/google-chrome.deb || true
    }
    rm -f /tmp/google-chrome.deb
}

DOCTOR_PASS=0
DOCTOR_WARN=0
DOCTOR_FAIL=0

dr_pass() { ok   "$*"; DOCTOR_PASS=$((DOCTOR_PASS+1)); }
dr_warn() { warn "$*"; DOCTOR_WARN=$((DOCTOR_WARN+1)); }
dr_fail() { fail "$*"; DOCTOR_FAIL=$((DOCTOR_FAIL+1)); }

run_doctor() {
    echo -e "${BOLD}=================================================================${RESET}"
    echo -e "${BOLD} Outlook Generator — VPS Doctor${RESET}"
    echo -e "${BOLD} Read-only checks. Nothing will be installed or changed.${RESET}"
    echo -e "${BOLD}=================================================================${RESET}"
    echo

    echo -e "${BOLD}[ System ]${RESET}"
    if [ -r /etc/os-release ]; then
        OS_NAME="$(. /etc/os-release && echo "$PRETTY_NAME")"
        dr_pass "OS: $OS_NAME"
    else
        dr_warn "Cannot read /etc/os-release"
    fi

    ARCH="$(uname -m)"
    if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
        dr_pass "Architecture: $ARCH (Google Chrome supports this)"
    else
        dr_fail "Architecture: $ARCH (Google Chrome .deb only supports x86_64/amd64)"
    fi

    if command -v free >/dev/null 2>&1; then
        MEM_MB=$(free -m | awk '/^Mem:/{print $2}')
        if [ "${MEM_MB:-0}" -ge 900 ]; then
            dr_pass "RAM: ${MEM_MB} MB"
        else
            dr_warn "RAM: ${MEM_MB} MB (Chrome may crash with <1 GB)"
        fi
    fi

    DISK_FREE=$(df -m . | awk 'NR==2{print $4}')
    if [ "${DISK_FREE:-0}" -ge 1500 ]; then
        dr_pass "Disk free in $(pwd): ${DISK_FREE} MB"
    else
        dr_warn "Disk free in $(pwd): ${DISK_FREE} MB (recommend >= 1.5 GB)"
    fi

    echo
    echo -e "${BOLD}[ Browser ]${RESET}"
    BROWSER="$(find_browser)"
    if [ -z "$BROWSER" ]; then
        dr_fail "No browser found. Run ./run_vps.sh to auto-install Google Chrome."
    else
        REAL="$(readlink -f "$BROWSER")"
        if is_snap_browser "$BROWSER"; then
            dr_fail "Browser is the SNAP version: $REAL"
            dr_fail "    Snap Chromium does NOT work with Selenium."
            dr_fail "    Run ./run_vps.sh to replace it with Google Chrome."
        else
            dr_pass "Browser: $REAL"
            VER="$("$BROWSER" --version 2>/dev/null | head -n1 || echo unknown)"
            dr_pass "Browser version: $VER"
            if "$BROWSER" --headless=new --disable-gpu --no-sandbox \
                --dump-dom about:blank >/dev/null 2>&1; then
                dr_pass "Browser launches headlessly (Selenium will work)"
            else
                dr_fail "Browser failed to launch headlessly. Likely missing libs."
                dr_fail "    Try: $SUDO apt install -y libnss3 libxss1 libasound2 libgbm1"
            fi
        fi
    fi

    if command -v chromedriver >/dev/null 2>&1; then
        dr_pass "chromedriver: $(command -v chromedriver)"
    else
        dr_warn "chromedriver not found (Selenium 4 will auto-download one)"
    fi

    echo
    echo -e "${BOLD}[ Display & VNC tools ]${RESET}"
    for cmd in Xvfb x11vnc websockify; do
        if command -v "$cmd" >/dev/null 2>&1; then
            dr_pass "$cmd: $(command -v $cmd)"
        else
            dr_fail "$cmd missing  ->  $SUDO apt install -y xvfb x11vnc websockify"
        fi
    done
    NOVNC_WEB=""
    for d in /usr/share/novnc /usr/share/webapps/novnc; do
        [ -d "$d" ] && NOVNC_WEB="$d" && break
    done
    if [ -n "$NOVNC_WEB" ]; then
        dr_pass "noVNC web files: $NOVNC_WEB"
    else
        dr_fail "noVNC web files missing  ->  $SUDO apt install -y novnc"
    fi

    echo
    echo -e "${BOLD}[ Python ]${RESET}"
    if command -v python3 >/dev/null 2>&1; then
        dr_pass "python3: $(python3 --version 2>&1)"
    else
        dr_fail "python3 missing  ->  $SUDO apt install -y python3 python3-venv"
    fi
    if [ -d "venv" ]; then
        dr_pass "venv exists at ./venv"
        if ./venv/bin/python -c "import selenium, faker, requests" >/dev/null 2>&1; then
            dr_pass "venv has selenium, faker, requests installed"
        else
            dr_warn "venv is missing some deps. Re-run ./run_vps.sh to install them."
        fi
    else
        dr_warn "venv not created yet (./run_vps.sh will create it)"
    fi

    echo
    echo -e "${BOLD}[ Network ]${RESET}"
    PUBLIC_IP="$(curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null \
                || curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
                || hostname -I 2>/dev/null | awk '{print $1}')"
    if [ -n "$PUBLIC_IP" ]; then
        dr_pass "Public IP: $PUBLIC_IP"
        ORG="$(curl -fsS --max-time 5 https://ipinfo.io/${PUBLIC_IP}/org 2>/dev/null || true)"
        if [ -n "$ORG" ]; then
            dr_pass "IP belongs to: $ORG"
            if echo "$ORG" | grep -Eqi 'amazon|aws|google|gcp|microsoft|azure|digitalocean|linode|vultr|hetzner|ovh|contabo|oracle|scaleway|hostinger'; then
                dr_warn "  ^ Datacenter IP — Microsoft often asks for SMS verification."
                dr_warn "    Consider setting a residential proxy in config.json."
            fi
        fi
    else
        dr_fail "Could not determine public IP (no outbound HTTPS?)"
    fi

    if curl -fsS --max-time 8 -o /dev/null -w "%{http_code}\n" https://signup.live.com/signup?lic=1 \
        2>/dev/null | grep -q "^2"; then
        dr_pass "signup.live.com reachable from this VPS"
    else
        dr_warn "signup.live.com did not return 2xx (network blocked, or Microsoft is throttling this IP)"
    fi

    echo
    echo -e "${BOLD}[ Ports & firewall ]${RESET}"
    if command -v ss >/dev/null 2>&1; then
        for p in "$VNC_PORT" "$NOVNC_PORT"; do
            if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${p}\$"; then
                dr_warn "Port $p is already in use (likely a leftover service from a previous run)"
            else
                dr_pass "Port $p is free locally"
            fi
        done
    else
        dr_warn "ss not available, skipping local port check"
    fi

    if command -v ufw >/dev/null 2>&1; then
        UFW_STATUS="$($SUDO ufw status 2>/dev/null | head -n1 || echo "")"
        if echo "$UFW_STATUS" | grep -qi inactive; then
            dr_warn "ufw is INACTIVE (firewall not blocking, but also not protecting)"
        elif $SUDO ufw status 2>/dev/null | grep -q "${NOVNC_PORT}.*ALLOW"; then
            dr_pass "ufw allows port $NOVNC_PORT"
        else
            dr_warn "ufw is active but port $NOVNC_PORT not allowed  ->  $SUDO ufw allow ${NOVNC_PORT}/tcp"
        fi
    else
        dr_warn "ufw not installed; check your VPS firewall manually for port $NOVNC_PORT"
    fi

    echo
    echo -e "${BOLD}[ Leftover processes ]${RESET}"
    LEFTOVERS=0
    for proc in "Xvfb $DISPLAY_NUM" "x11vnc.*-rfbport $VNC_PORT" "websockify.*$NOVNC_PORT"; do
        if pgrep -f "$proc" >/dev/null 2>&1; then
            dr_warn "Running: $proc  (the launcher will clean it up automatically)"
            LEFTOVERS=$((LEFTOVERS+1))
        fi
    done
    [ "$LEFTOVERS" -eq 0 ] && dr_pass "No leftover Xvfb / x11vnc / websockify processes"

    echo
    echo -e "${BOLD}=================================================================${RESET}"
    echo -e " Summary:  ${GREEN}${DOCTOR_PASS} passed${RESET}   ${YELLOW}${DOCTOR_WARN} warnings${RESET}   ${RED}${DOCTOR_FAIL} failed${RESET}"
    if [ "$DOCTOR_FAIL" -eq 0 ]; then
        echo -e " ${GREEN}${BOLD}You're good to go. Run: ./run_vps.sh${RESET}"
    else
        echo -e " ${RED}${BOLD}Fix the failures above before running ./run_vps.sh${RESET}"
    fi
    echo -e "${BOLD}=================================================================${RESET}"

    [ "$DOCTOR_FAIL" -eq 0 ]
}

if [ "${1:-}" = "--doctor" ] || [ "${1:-}" = "-d" ] || [ "${1:-}" = "doctor" ]; then
    run_doctor
    exit $?
fi

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    cat <<EOF
Usage: ./run_vps.sh [command]

Commands:
  (none)        Set up everything and start generating accounts.
  --doctor      Run read-only checks for common breakages and exit.
  --help        Show this help.

Environment variables:
  VNC_PORT      VNC server port (default 5900)
  NOVNC_PORT    noVNC web bridge port (default 6080)
  DISPLAY_NUM   Virtual display number (default :1)
  SCREEN_SIZE   Virtual screen geometry (default 432x1035x24)
EOF
    exit 0
fi

if command -v apt-get >/dev/null 2>&1; then
    missing=()
    command -v Xvfb       >/dev/null 2>&1 || missing+=(xvfb)
    command -v x11vnc     >/dev/null 2>&1 || missing+=(x11vnc)
    command -v websockify >/dev/null 2>&1 || missing+=(websockify novnc)
    command -v curl       >/dev/null 2>&1 || missing+=(curl)
    command -v wget       >/dev/null 2>&1 || missing+=(wget)
    if [ ${#missing[@]} -gt 0 ]; then
        say "Installing missing system packages: ${missing[*]}"
        $SUDO apt-get update -y
        $SUDO apt-get install -y "${missing[@]}"
    fi

    command -v file >/dev/null 2>&1 || $SUDO apt-get install -y file >/dev/null

    if snap_chromium_present || command -v chromium-browser >/dev/null 2>&1; then
        warn "Snap-packaged Chromium detected — it cannot be driven by Selenium."
        warn "Removing it now ..."
        $SUDO snap remove chromium 2>/dev/null || true
        $SUDO apt-get remove --purge -y chromium-browser chromium chromium-chromedriver 2>/dev/null || true
        $SUDO rm -f /usr/bin/chromium-browser /snap/bin/chromium 2>/dev/null || true
    fi

    if ! command -v google-chrome >/dev/null 2>&1 \
       && ! command -v google-chrome-stable >/dev/null 2>&1; then
        install_google_chrome
    fi
fi

if ! command -v google-chrome >/dev/null 2>&1 \
   && ! command -v google-chrome-stable >/dev/null 2>&1; then
    fail "Google Chrome was not installed successfully."
    fail "Run manually:"
    fail "  wget -qO /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
    fail "  $SUDO apt-get install -y /tmp/chrome.deb"
    exit 1
fi
ok "Browser ready: $(command -v google-chrome || command -v google-chrome-stable)"

if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is not installed. Install it and re-run this script."
    exit 1
fi

if [ ! -d "venv" ]; then
    say "Creating Python virtual environment ..."
    python3 -m venv venv || {
        warn "python3 -m venv failed. Try: $SUDO apt install -y python3-venv"
        exit 1
    }
fi

source venv/bin/activate

if ! python -c "import selenium" >/dev/null 2>&1; then
    say "Installing Python dependencies ..."
    pip install --upgrade pip >/dev/null
    pip install -r requirements.txt
fi

PUBLIC_IP="$(curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null \
            || curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
            || hostname -I 2>/dev/null | awk '{print $1}')"
if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP="YOUR_VPS_IP"
fi

NOVNC_URL="http://${PUBLIC_IP}:${NOVNC_PORT}/vnc.html?autoconnect=1&resize=scale"
export NOVNC_URL

say "Cleaning up any leftover background processes ..."
pkill -f "Xvfb $DISPLAY_NUM"           >/dev/null 2>&1 || true
pkill -f "x11vnc.*-rfbport $VNC_PORT"   >/dev/null 2>&1 || true
pkill -f "websockify.*$NOVNC_PORT"      >/dev/null 2>&1 || true
sleep 1

say "Starting virtual display ($DISPLAY_NUM @ $SCREEN_SIZE) ..."
Xvfb "$DISPLAY_NUM" -screen 0 "$SCREEN_SIZE" >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 1

say "Starting VNC server on port $VNC_PORT ..."
x11vnc -display "$DISPLAY_NUM" -nopw -forever -shared \
       -rfbport "$VNC_PORT" -quiet >/tmp/x11vnc.log 2>&1 &
VNC_PID=$!
sleep 1

NOVNC_WEB=""
for d in /usr/share/novnc /usr/share/webapps/novnc; do
    [ -d "$d" ] && NOVNC_WEB="$d" && break
done
if [ -z "$NOVNC_WEB" ]; then
    warn "noVNC web files not found. Install with: $SUDO apt install -y novnc"
    kill "$XVFB_PID" "$VNC_PID" 2>/dev/null || true
    exit 1
fi

say "Starting noVNC web bridge on port $NOVNC_PORT ..."
websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:$VNC_PORT" \
    >/tmp/websockify.log 2>&1 &
WS_PID=$!
sleep 2

cleanup() {
    echo
    say "Stopping background services ..."
    kill "$XVFB_PID" "$VNC_PID" "$WS_PID" 2>/dev/null || true
    pkill -f "Xvfb $DISPLAY_NUM"           >/dev/null 2>&1 || true
    pkill -f "x11vnc.*-rfbport $VNC_PORT"   >/dev/null 2>&1 || true
    pkill -f "websockify.*$NOVNC_PORT"      >/dev/null 2>&1 || true
    ok "Cleaned up. Bye."
}
trap cleanup EXIT INT TERM

echo
echo -e "${BOLD}=================================================================${RESET}"
echo -e "${BOLD} ✓ Setup complete${RESET}"
echo
echo -e "${BOLD} Open this URL in your phone or laptop browser:${RESET}"
echo -e "   ${GREEN}${BOLD}${NOVNC_URL}${RESET}"
echo
echo -e "${BOLD} Make sure port ${NOVNC_PORT} is open in your VPS firewall:${RESET}"
echo -e "   ${CYAN}${SUDO} ufw allow ${NOVNC_PORT}/tcp${RESET}"
echo
echo -e " The script auto-fills email, password, name, and birthday."
echo -e " ${BOLD}Only the captcha needs you${RESET} — press and hold the puzzle button"
echo -e " in the browser tab when it appears. Microsoft may show 2-3 puzzles"
echo -e " in a row — solve them all and the script will continue automatically."
echo
echo -e " ${BOLD}One-command install on a fresh VPS:${RESET}"
echo -e "   ${CYAN}curl -fsSL https://raw.githubusercontent.com/keyspanel/Outlook-account-creator/main/install.sh | sudo bash${RESET}"
echo -e "${BOLD}=================================================================${RESET}"
echo

if [ -x ./venv/bin/python ]; then
    PYBIN="./venv/bin/python"
else
    PYBIN="python3"
fi
"$PYBIN" main.py
