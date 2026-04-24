#!/usr/bin/env bash
set -e

REPO_URL="${REPO_URL:-https://github.com/keyspanel/Outlook-account-creator.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/outlook-gen}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

say()  { echo -e "${CYAN}[*]${RESET} $*"; }
ok()   { echo -e "${GREEN}[+]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
fail() { echo -e "${RED}[x]${RESET} $*"; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        fail "This installer needs root or sudo. Run as root or install sudo."
        exit 1
    fi
fi

echo -e "${BOLD}================================================================${RESET}"
echo -e "${BOLD} Outlook Account Generator — One-Command Installer${RESET}"
echo -e "${BOLD}================================================================${RESET}"
echo
say "This will:"
echo "    1) Remove broken snap-packaged Chromium (if any)"
echo "    2) Install Google Chrome, Python, Xvfb, x11vnc, websockify, noVNC"
echo "    3) Clone (or update) the project to $INSTALL_DIR"
echo "    4) Start the generator"
echo

if command -v snap >/dev/null 2>&1; then
    if snap list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx chromium \
       || [ -L /snap/bin/chromium ] || [ -d /snap/chromium ]; then
        say "Removing snap-packaged Chromium (incompatible with Selenium) ..."
        $SUDO snap remove --purge chromium 2>/dev/null \
            || $SUDO snap remove chromium 2>/dev/null \
            || true
    fi
fi
$SUDO apt-get remove --purge -y chromium-browser chromium chromium-chromedriver 2>/dev/null || true
$SUDO rm -f /usr/bin/chromium-browser /snap/bin/chromium 2>/dev/null || true

say "Updating apt index ..."
$SUDO apt-get update -y >/dev/null

say "Installing system packages (this can take a couple of minutes) ..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git python3 python3-venv python3-pip \
    xvfb x11vnc websockify novnc \
    wget curl ca-certificates gnupg file \
    libnss3 libxss1 libgbm1 libasound2 \
    fonts-liberation xdg-utils >/dev/null

if ! command -v google-chrome >/dev/null 2>&1 \
   && ! command -v google-chrome-stable >/dev/null 2>&1; then
    say "Downloading Google Chrome stable .deb ..."
    wget -qO /tmp/google-chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    say "Installing Google Chrome ..."
    $SUDO apt-get install -y /tmp/google-chrome.deb >/dev/null 2>&1 \
        || { $SUDO apt-get install -f -y >/dev/null; $SUDO dpkg -i /tmp/google-chrome.deb || true; }
    rm -f /tmp/google-chrome.deb
fi

if ! command -v google-chrome >/dev/null 2>&1 \
   && ! command -v google-chrome-stable >/dev/null 2>&1; then
    fail "Google Chrome installation failed."
    fail "Run manually:"
    fail "  wget -qO /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
    fail "  $SUDO apt install -y /tmp/chrome.deb"
    exit 1
fi

CHROME_VERSION="$(google-chrome --version 2>/dev/null || google-chrome-stable --version 2>/dev/null || echo unknown)"
ok "Google Chrome ready: $CHROME_VERSION"

if [ ! -d "$INSTALL_DIR/.git" ]; then
    if [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
        warn "$INSTALL_DIR exists but isn't a git repo. Backing up to ${INSTALL_DIR}.bak.$$"
        $SUDO mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$$"
    fi
    say "Cloning project to $INSTALL_DIR ..."
    $SUDO git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
else
    say "Updating project at $INSTALL_DIR ..."
    (cd "$INSTALL_DIR" && $SUDO git pull --ff-only || true)
fi

if [ "$(id -u)" -ne 0 ]; then
    $SUDO chown -R "$(id -u):$(id -g)" "$INSTALL_DIR" 2>/dev/null || true
fi

cd "$INSTALL_DIR"
chmod +x run_vps.sh
[ -f install.sh ] && chmod +x install.sh

ok "Project ready at $INSTALL_DIR"
echo
echo -e "${BOLD}================================================================${RESET}"
echo -e "${BOLD} Setup complete. Starting the generator now ...${RESET}"
echo -e "${BOLD}================================================================${RESET}"
echo

exec ./run_vps.sh
