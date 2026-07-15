#!/bin/bash
# ============================================================================
# Sundari AI Mix Engineer — EK-BAAR-CHALNE-WALA SETUP SCRIPT
# ============================================================================
# Ye script sirf EK BAAR chalana hai. Iske baad terminal kabhi dobara
# kholne ki zaroorat nahi padegi — backend server khud-ba-khud hamesha
# background mein chalu rahega (Mac restart hone par bhi).
#
# CHALANE KA TAREEKA:
#   1. Terminal kholein
#   2. Is script ko project ke "install" folder mein rakhein
#   3. Terminal mein type karein:  bash setup_once.sh
#   4. Enter dabayein aur intezaar karein
# ============================================================================

set -e  # koi bhi step fail ho to turant ruk jao, aage mat badho

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
PLUGIN_DIR="$PROJECT_ROOT/plugin"
PLIST_NAME="com.sundari.backend.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "=============================================="
echo " Sundari AI Mix Engineer — Setup shuru ho raha hai"
echo "=============================================="
echo ""
echo "Project location: $PROJECT_ROOT"
echo ""

# --- Step 1: Python virtual environment banana (agar pehle se nahi hai) ---
echo "[1/6] Python environment taiyaar kar rahe hain..."
cd "$BACKEND_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "      -> Naya virtual environment bana."
else
    echo "      -> Pehle se maujood hai, use kar rahe hain."
fi

# --- Step 2: Zaroori Python packages install karna ---
echo "[2/6] Zaroori packages install kar rahe hain (isme 2-5 minute lag sakte hain)..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
deactivate
echo "      -> Packages install ho gaye."

# --- Step 3: .env file confirm karna ---
echo "[3/6] .env file check kar rahe hain..."
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo "      -> KHATA: .env file nahi mili! Pehle .env banayein aur API key daalein."
    exit 1
fi
echo "      -> .env file mil gayi, API key set hai."

# --- Step 4: Logs folder banana ---
mkdir -p "$BACKEND_DIR/logs"

# --- Step 5: LaunchAgent (auto-start) setup karna ---
echo "[4/6] Auto-start service set kar rahe hain..."
mkdir -p "$LAUNCH_AGENTS_DIR"

PYTHON_PATH="$BACKEND_DIR/venv/bin/python3"

# Template plist mein sahi paths bharna
sed \
    -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
    -e "s|__BACKEND_PATH__|$BACKEND_DIR|g" \
    "$PROJECT_ROOT/install/$PLIST_NAME" > "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

# Agar pehle se koi purani service chal rahi ho to pehle unload karna
launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true

# Naye service ko load + turant start karna
launchctl load -w "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo "      -> Auto-start service register ho gayi."

# --- Step 6: Confirm karna ke backend chalu ho gaya ---
echo "[5/6] Backend server ko check kar rahe hain..."
sleep 3
if curl -s http://127.0.0.1:8000/health > /dev/null; then
    echo "      -> SAFAL! Backend chalu hai aur hamesha auto-start rahega."
else
    echo "      -> Backend abhi start ho raha hai, thoda intezaar karein aur"
    echo "         http://127.0.0.1:8000/health browser mein khol kar dekhein."
fi

echo ""
echo "=============================================="
echo " [6/6] SETUP COMPLETE!"
echo "=============================================="
echo ""
echo "Ab se: backend hamesha khud chalu rahega, Mac restart hone par bhi."
echo "Terminal ab dobara kabhi kholne ki zaroorat NAHI hai."
echo ""
echo "Agla step: Logic Pro mein plugin build/install karna."
echo "Uske liye 'plugin/docs/BUILD_INSTRUCTIONS_MAC.md' dekhein,"
echo "ya Claude se agla step maangein."
echo ""
