# Mac mini M4 par Plugin Build karne ke Poore Steps

Yeh guide maan kar chalti hai ki aapko terminal commands copy-paste karna
aata hai — koi coding experience zaroori nahi.

## Zaroori Cheezein Install Karna (ek baar)

### 1. Xcode Command Line Tools
```bash
xcode-select --install
```
Ek popup aayega, "Install" dabayein, kuch minute lagenge.

### 2. Homebrew (agar pehle se nahi hai)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3. CMake
```bash
brew install cmake
```

## Plugin Build Karna

### Step 1: Is poore project ko apne Mac par le jaayein
Zip file ko extract karein, terminal mein us folder ke andar jaayein:
```bash
cd ~/Downloads/sundari-ai-mix-engineer/plugin
```

### Step 2: CMake configure karein
Yeh command JUCE library ko automatically download karega (pehli baar
mein internet chahiye, 5-10 minute lag sakte hain):
```bash
cmake -B build -G Xcode
```

### Step 3: Build karein
```bash
cmake --build build --config Release
```

Yeh 10-20 minute le sakta hai (pehli baar mein — JUCE bada framework
hai). Agar koi error aaye, use hume batayein — main fix kar dunga
(kyunki main khud is code ko Mac par compile karke test nahi kar paaya,
kuch chhote syntax issues ho sakte hain jo Mac ke compiler par hi pata
chalenge).

### Step 4: Plugin apne aap sahi jagah install ho jaata hai
`COPY_PLUGIN_AFTER_BUILD TRUE` (CMakeLists.txt mein already set hai)
ki wajah se, build complete hone par plugin automatically yahan copy ho
jaata hai:
- **AU**: `~/Library/Audio/Plug-Ins/Components/Sundari AI Mix Engineer.component`
- **VST3**: `~/Library/Audio/Plug-Ins/VST3/Sundari AI Mix Engineer.vst3`

## Logic Pro mein Use Karna

### Step 1: Logic Pro ko naya plugin scan karne dein
Logic Pro kholein → **Logic Pro menu → Preferences → Audio → Plug-In Manager**
→ "Reset & Rescan Selection" ya "Rescan Selection" dabayein (agar Logic
Pro pehle se khula tha jab aapne build kiya).

Agar Logic Pro pehli baar plugin dekhega, to macOS ek security prompt
degа ("Sundari AI Mix Engineer ko verify nahi kiya ja saka") — yeh normal
hai kyunki humne Apple Developer certificate se sign nahi kiya (woh paid
Apple Developer account maangta hai, $99/year). Isse allow karne ke liye:
```bash
xattr -cr "/Users/$(whoami)/Library/Audio/Plug-Ins/Components/Sundari AI Mix Engineer.component"
xattr -cr "/Users/$(whoami)/Library/Audio/Plug-Ins/VST3/Sundari AI Mix Engineer.vst3"
```

### Step 2: Plugin ko kisi bhi track par insert karein
Kisi track ke **Audio FX** slot par click karein → **Audio Units → Sundari
AI → Sundari AI Mix Engineer**.

### Step 3: Python Backend chalayein (plugin isse baat karta hai)
Plugin khud koi AI nahi karta — woh humare Python backend (jo humne pehle
Phases mein banaya) ko call karta hai. Isliye plugin use karne se pehle,
ek alag Terminal window mein:
```bash
cd ~/Downloads/sundari-ai-mix-engineer/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# .env file banayein aur kam se kam ek API key daalein (.env.example dekhein)
cp .env.example .env
nano .env   # ANTHROPIC_API_KEY= ke aage apni key daalein, save karein (Ctrl+O, Enter, Ctrl+X)
uvicorn app.main:app --port 8000
```
Yeh terminal window khuli rakhni hai jab tak aap Logic Pro mein plugin
use kar rahe hon.

### Step 4: Plugin mein "Analyze" dabayein
Track ko play karein (kam se kam kuch second), phir plugin window mein
role select karein (jaise "lead_vocal"), aur **"AI se Analyze aur Suggest
karein"** button dabayein. Kuch second mein AI ka jawab EQ/Compression
apply kar dega, aur neeche explanation panel mein poori teaching mil
jaayegi.

## Agar Kuch Kaam Na Kare

| Samasya | Kya karein |
|---|---|
| CMake configure fail ho | `cmake --version` check karein (3.22+ chahiye), `brew upgrade cmake` |
| Build mein C++ errors aayein | Poora error message copy karke hume bhejein — main fix dunga |
| Logic Pro mein plugin dikhta nahi | Plug-In Manager mein "Reset & Rescan" try karein, Logic Pro restart karein |
| "AI se connect nahi ho paya" error | Terminal mein backend (`uvicorn`) chal raha hai ya nahi check karein |
| Plugin crash ho jaaye | Console.app kholkar crash log dekhein, hume bhejein |

## Ek Zaroori ईमानदार Baat

Maine yeh code apne training/knowledge ke aadhar par likha hai, JUCE ke
standard patterns follow karke — lekin maine khud isse kisi Mac par
compile karke verify nahi kiya (mere paas yahan macOS nahi hai). Real-
world mein pehli compile try mein 100% clean build hona kam hi hota hai
— agar koi chhota syntax/API-mismatch error aaye (JUCE version updates
ke saath API kabhi-kabhi badalta hai), to woh normal hai. Bas error
message mujhe bhej dein, main turant fix kar dunga.
