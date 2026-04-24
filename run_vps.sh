#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

say()  { echo -e "${CYAN}[*]${RESET} $*"; }
ok()   { echo -e "${GREEN}[+]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }

VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
DISPLAY_NUM="${DISPLAY_NUM:-:1}"
SCREEN_SIZE="${SCREEN_SIZE:-432x1035x24}"
export DISPLAY="$DISPLAY_NUM"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    fi
fi

is_snap_browser() {
    local b="$1"
    [ -z "$b" ] && return 1
    local real
    real="$(readlink -f "$b" 2>/dev/null || echo "$b")"
    [[ "$real" == */snap/* ]]
}

find_browser() {
    command -v google-chrome 2>/dev/null \
        || command -v google-chrome-stable 2>/dev/null \
        || command -v chromium 2>/dev/null \
        || command -v chromium-browser 2>/dev/null \
        || true
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

    BROWSER="$(find_browser)"
    if [ -z "$BROWSER" ] || is_snap_browser "$BROWSER"; then
        if [ -n "$BROWSER" ] && is_snap_browser "$BROWSER"; then
            warn "Detected snap-packaged browser at $(readlink -f "$BROWSER")."
            warn "Snap Chromium can't be driven by Selenium. Replacing with Google Chrome ..."
            $SUDO apt-get remove -y chromium-browser chromium chromium-chromedriver 2>/dev/null || true
            $SUDO snap remove chromium 2>/dev/null || true
        fi
        install_google_chrome
    fi
fi

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
echo -e " in the browser tab when it appears."
echo -e "${BOLD}=================================================================${RESET}"
echo

python3 main.py
