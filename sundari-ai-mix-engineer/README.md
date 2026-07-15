# Sundari AI Mix Engineer

एक AI-आधारित Mixing & Mastering Software, जो किसी भी ऑडियो प्रोजेक्ट को Analyze करे, समस्याएँ पहचाने, उन्हें ठीक करे, और साथ-साथ सिखाए भी कि हर बदलाव क्यों किया गया।

## प्रोजेक्ट की स्थिति

यह प्रोजेक्ट **Phases** में बनाया जा रहा है। हर Phase पूरी तरह काम करने वाला (working), tested code deliver करता है — कोई placeholder नहीं।

| Phase | नाम | स्थिति |
|---|---|---|
| **1** | **Backend Architecture + Audio Analysis Engine** | ✅ पूरा |
| **2** | **AI Mix Report + Learning Mode (rule-based expert system)** | ✅ पूरा |
| **4** | **Multi-Provider Intelligent Decision Engine** | 🔶 आंशिक |
| **Plugin** | **JUCE VST3/AU Plugin (Logic Pro Integration)** | 🔶 Code पूरा, आपके Mac पर compile करना बाकी |
| 5 | Reference Track Comparison | आगामी |
| 5 | Reference Track Comparison | आगामी |
| 6 | AI Mastering Presets (Spotify, YouTube, Apple Music, Club, Broadcast) | आगामी |
| 7 | AI Chat Assistant | आगामी |
| 8 | Frontend (Dark Theme Dashboard, Meters, Spectrum Analyzer) | आगामी |
| 9 | Cloud Sync, Auth, Licensing, Subscription | आगामी |
| 10 | Documentation Suite (Install/User/API/Testing/Deployment Guides) | आगामी |

> **नोट:** मूल स्पेसिफिकेशन में Phase 2 (AI Mix Report) और Phase 3 (Learning Mode) अलग-अलग थे। आपके "teaching-style report" चुनाव के आधार पर इन्हें एक साथ बनाया गया है, क्योंकि हर finding में पहले से ही "यह समस्या क्यों है" और "कैसे ठीक करें" दोनों शामिल हैं — इन्हें अलग बनाना सिर्फ duplication होता।

## Plugin (Logic Pro Integration): क्या बना है

`plugin/` folder में एक **JUCE-based VST3/AU Plugin** का पूरा C++ source code है — यह Logic Pro के अंदर insert होकर काम करता है।

**ज़रूरी सच्चाई:** मैं Linux sandbox में हूँ, यहाँ macOS/Xcode नहीं है, इसलिए **मैं इस plugin को compile करके खुद test नहीं कर सका।** Source code JUCE के standard, सही patterns से लिखा गया है, लेकिन पहली compile try में कोई छोटी सी syntax/API चीज़ अटक सकती है — अगर ऐसा हो, तो error message भेज दें, मैं तुरंत ठीक कर दूँगा।

### Plugin Architecture

```
plugin/
├── CMakeLists.txt              # JUCE modern CMake build (VST3 + AU + Standalone)
├── Source/
│   ├── PluginProcessor.h/.cpp  # Core AudioProcessor — real-time DSP chain
│   ├── PluginEditor.h/.cpp     # UI — Dark theme, Analyze button, AI Teacher panel
│   ├── DSP/
│   │   ├── EQBand.h            # Real IIR filter (juce::dsp), AI-parameterized
│   │   ├── DynamicsChain.h     # Real Compressor + Limiter (juce::dsp)
│   │   └── StereoWidthProcessor.h  # Mid-Side stereo width, real-time
│   └── AI/
│       └── DecisionClient.h/.cpp   # Background-thread HTTP client → Python backend
└── docs/
    └── BUILD_INSTRUCTIONS_MAC.md   # Xcode/CMake/Logic Pro तक पूरे कदम
```

### यह कैसे काम करता है

1. Plugin **खुद कोई AI नहीं है** — वह हमारे Phase 4 Python backend (`/api/v1/decision/project`) को call करता है, जो Claude/OpenAI/Gemini/Local LLM में से जो भी configured हो, उससे genuine निर्णय लेता है।
2. Audio thread (real-time, कभी block नहीं होता) सिर्फ **actual DSP** चलाता है — EQ, Compression, Limiter, Stereo Width — जो पूरी तरह functional JUCE code है, कोई placeholder नहीं।
3. "Analyze" button दबाने पर, plugin पिछले ~10 सेकंड के audio को एक temp WAV में लिखता है, background thread पर backend को भेजता है (audio thread कभी network call का wait नहीं करता — यह real-time audio का सबसे ज़रूरी नियम है)।
4. AI का response आने पर, EQ/Compression parameters safely audio thread में लागू होते हैं, aur "AI Teacher" panel में पूरी teaching explanation (समस्या, कारण, बदलाव, अगर न बदलते तो) दिखती है।

### Build कैसे करें

पूरे step-by-step (Xcode install से लेकर Logic Pro में plugin दिखने तक): **`plugin/docs/BUILD_INSTRUCTIONS_MAC.md`** देखें।

संक्षेप में:
```bash
cd plugin
cmake -B build -G Xcode
cmake --build build --config Release
# Plugin apne aap ~/Library/Audio/Plug-Ins/ mein install ho jaata hai
```
साथ में backend भी चलाना होगा (`uvicorn app.main:app --port 8000`) क्योंकि plugin उसी से बात करता है।

## Phase 4 में क्या बना है: Multi-Provider Intelligent Decision Engine

> **महत्वपूर्ण बदलाव:** आपने Phase 2 में rule-based system चुना था, लेकिन बाद में स्पष्ट किया कि आप **कोई भी fixed threshold/preset-based decision-making नहीं चाहते** — आप चाहते हैं कि AI हर project को असल में समझकर, स्वयं निर्णय ले। यह genuinely सिर्फ एक reasoning-capable AI (LLM) से संभव है, इसलिए Phase 4 अब **Multi-Provider LLM Decision Engine** है, Rule Engine नहीं। Phase 2 का rule-based system अभी भी मौजूद है — वह अब सिर्फ **numeric measurement + reference context** देता है, जिसे LLM अपने context में इस्तेमाल करता है, लेकिन final निर्णय LLM खुद लेता है, कोई if-else नहीं।

### आर्किटेक्चर

```
backend/app/decision_engine/
├── providers/
│   ├── base.py              # LLMProvider abstract interface (Strategy Pattern)
│   ├── claude_provider.py   # Anthropic Claude (tool-use से structured output)
│   ├── openai_provider.py   # OpenAI GPT-5 (json_schema structured output)
│   ├── gemini_provider.py   # Google Gemini (response_schema)
│   └── local_llm_provider.py# Ollama/local models (REST API, defensive JSON parsing)
├── provider_registry.py     # Factory + Fallback Chain (ek provider fail ho to agla try ho)
├── decision_schema.py       # पूरा mixing decision + AI Teacher explanation का Pydantic schema
├── context_builder.py       # Phase 1/2 का data + musical features → LLM-ready context
└── engine.py                 # Orchestrator: context बनाना → provider call → schema validation
```

### Multi-Provider कैसे काम करता है

हर provider (`ClaudeProvider`, `OpenAIProvider`, `GeminiProvider`, `LocalLLMProvider`) एक ही `LLMProvider` interface implement करता है। `ProviderChain` एक ordered list लेता है (`.env` में `DECISION_PROVIDER_ORDER` से configurable) — अगर पहला provider fail हो (rate limit, downtime), तो अपने-आप अगले provider पर fallback होता है। **नया provider भविष्य में जोड़ना** सिर्फ एक नई file लिखने और `register_provider()` call करने जितना आसान है — कहीं और कोई if/else नहीं बदलना पड़ता।

यह Registry + Fallback Chain logic **5 tests के साथ verify किया गया है** (mock providers से, बिना real API keys के) — सब pass।

### AI Teacher Schema

हर track decision के साथ 7 अनिवार्य fields होते हैं (Pydantic level पर enforced):
समस्या क्या थी, क्यों थी, क्या बदला, क्यों बदला, इससे क्या अंतर आया, अगर न बदलते तो क्या होता, और professional engineers ऐसा क्यों करते हैं।

### BPM और Musical Key — असली DSP से (Genre/Mood के साथ ईमानदार सीमा)

- **BPM**: Onset-envelope + autocorrelation से genuinely detect होता है। Test: 120 BPM click track → 120.2 BPM detect हुआ ✅
- **Musical Key**: Chroma features + Krumhansl-Schmuckler key profiles से genuinely detect होता है। Test: C Major scale → "C Major" detect हुआ ✅
- **Genre/Mood**: यह भौतिक रूप से measure नहीं किया जा सकता (यह style/perception है, waveform property नहीं)। हम objective descriptive features (tempo, brightness, dynamic range, rhythmic density) निकालते हैं और LLM को context के रूप में देते हैं — LLM एक "सुनकर लगता है" जैसा qualitative interpretation देता है, न कि कोई pakka classifier result। यह जानबूझकर किया गया है ताकि कोई नकली "genre classifier" न बने जो असल में काम नहीं करता।

### अभी क्या बाकी है (ईमानदारी से)

- **Iterative Mixing Loop**: स्पेसिफिकेशन के अनुसार, एक track बदलने पर पूरे mix का दोबारा analysis होना चाहिए, जब तक "professional quality" न आए। Schema में `iteration_number` और `ready_for_mastering` fields इसके लिए तैयार हैं, लेकिन loop-controller (कब रोकना है, "professional quality" कैसे measure करें) अभी नहीं बना — यह अगला काम है।
- **API endpoint testing with real keys**: यह sandbox environment में internet access नहीं है, इसलिए `pydantic` package तक install नहीं हो पाया — इसलिए `decision_schema.py` (जो पूरी तरह Pydantic पर बना है) और असली Claude/OpenAI/Gemini API calls **आपके अपने सिस्टम पर, internet के साथ, test करनी होंगी**। Registry/Fallback logic (जो सिर्फ Python dataclasses पर बना है, pydantic-independent) पूरी तरह यहीं test हो चुका है।
- Provider pricing constants (Claude/OpenAI cost-per-token) approximate हैं — production से पहले official pricing pages से confirm करें।

## Phase 2 में क्या बना है: AI Mix Report + Learning Mode

एक **100% offline, deterministic rule-based expert system** (कोई LLM call नहीं, कोई cost नहीं, कोई randomness नहीं) — जो Phase 1 के numeric analysis को लेकर हर finding के लिए 4 चीज़ें देता है:

1. **Title** — समस्या क्या है (एक लाइन में)
2. **Why (क्यों)** — यह समस्या तकनीकी रूप से क्यों होती है, कान को कैसी सुनाई देती है
3. **How to Fix (कैसे ठीक करें)** — practical steps, EQ ranges, compressor settings
4. **Professional Tip** — professional engineers इसके बारे में क्या सोचते/करते हैं

### कवर किए गए Rules (`backend/app/reporting/knowledge_base.py`)

- Clipping detection
- True Peak headroom (mastering-safe -1 dBTP)
- Compression Too Little / Too Much (role-specific crest-factor targets — vocal, kick, snare, bass, guitar, keys, master अलग-अलग)
- Mud detection
- Harshness detection
- Sibilance detection (केवल vocal roles के लिए)
- Mono Compatibility risk (stereo phase issues)
- Bass Balance (boomy / thin)
- Vocal Presence (buried / recessed / forward) — vocal stem को full mix से तुलना करके
- Frequency Masking (जैसे स्पेसिफिकेशन का Kick vs Bass उदाहरण) — कोई भी दो tracks compare कर सकते हैं
- Master Loudness Target — Spotify / YouTube / Apple Music / Club / Broadcast के हिसाब से LUFS check

हर track report में findings **severity के हिसाब से sorted** होते हैं (severe पहले), और एक `overall_status` (`excellent` / `good` / `needs_attention` / `critical`) दिया जाता है।

### Design निर्णय: Thresholds एक ही जगह क्यों रखे गए

सभी numeric thresholds (जैसे crest-factor की "healthy range" हर role के लिए) `knowledge_base.py` में constants के रूप में हैं। यह जानबूझकर किया गया है ताकि **Phase 4 (Auto-Fix)** इन्हीं thresholds को reuse कर सके — जब report कहे "compression कम है", Auto-Fix को पता होना चाहिए किस target crest-factor तक compress करना है, ताकि दोनों Phases में अलग-अलग "सही" values न हों।

### API Endpoints (Phase 2)

| Method | Path | काम |
|---|---|---|
| POST | `/api/v1/report/track` | एक track (+ `track_role`, optional `platform`) upload करें, पूरी teaching-style report मिले |
| POST | `/api/v1/report/masking` | दो tracks upload करें, clash/masking की पूरी व्याख्या मिले |
| POST | `/api/v1/report/vocal-in-mix` | Vocal stem + full mix, presence finding merged report में मिले |

`track_role` विकल्प: `lead_vocal`, `backing_vocal`, `kick`, `snare`, `bass`, `guitar`, `keys`, `master`, `generic`
`platform` (सिर्फ़ master role के लिए): `spotify`, `youtube`, `apple_music`, `club`, `broadcast`

### Testing

Phase 2 के सभी **9 scenario tests** (muddy vocal, over/under-compression, clipping, out-of-phase stereo, kick/bass masking, master loudness target, severity sorting, vocal presence merge) synthetic signals पर verify किए गए — सब pass।

## Phase 1 में क्या बना है

एक असली, गणितीय रूप से सत्यापित (verified) Audio Analysis Engine:

- **Loudness**: Integrated LUFS, Momentary Max, Short-Term Max, Loudness Range — ITU-R BS.1770-4 standard को खुद implement किया गया है (किसी एक बाहरी library पर निर्भर नहीं)।
- **Level**: Peak (dBFS), True Peak (dBTP, oversampling से inter-sample peaks पकड़ता है), RMS।
- **Dynamics**: Crest Factor, DR-meter-style Dynamic Range value।
- **Clipping Detection**: sample-level + consecutive-run detection।
- **Stereo Analysis**: Phase Correlation, Stereo Width (Mid/Side energy ratio), Mono Compatibility Risk।
- **Spectral Analysis**: 7-band frequency energy breakdown, Mud Detection, Harshness Detection, Sibilance Detection (short-time energy spikes)।
- **Frequency Masking Detection**: दो tracks की तुलना (जैसे Kick vs Bass) करके बताता है कि कौन-सा frequency band "clash" कर रहा है।
- **Bass Balance**: Sub-bass vs Bass ratio से "boomy / thin / balanced" स्थिति।
- **Vocal Presence**: Vocal stem को full mix से तुलना करके presence score।

### ईमानदार तकनीकी सीमा: Instrument Separation

स्पेसिफिकेशन में "Instrument Separation" माँगा गया है। सच यह है कि एक mixed stereo track को वापस अलग-अलग instruments में तोड़ना (true source separation) सिर्फ DSP/spectral heuristics से भरोसेमंद तरीके से नहीं हो सकता — इसके लिए एक trained deep neural network चाहिए। इसलिए:

- Phase 1 में `SeparationBackend` नाम का एक clean interface बना दिया गया है, जो अभी जानबूझकर `NotImplementedError` देता है (कोई नकली/भ्रामक परिणाम नहीं देता)।
- आगे के Phase में इसे **Demucs** (Meta AI, MIT license, free & open-source, GPU-accelerated, पूरी तरह local चलता है) से जोड़ा जाएगा — यही सबसे अच्छा और honest free/open-source विकल्प है।
- तब तक, अगर आप पहले से अलग किए हुए stems (vocal, drums, bass, other) upload करते हैं, तो हर instrument का पूरा विश्लेषण अभी भी उपलब्ध है।

## Folder Structure

```
sundari-ai-mix-engineer/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint
│   │   ├── core/
│   │   │   └── config.py            # Settings (env vars, DB URL, आदि)
│   │   ├── analysis/
│   │   │   ├── loader.py            # WAV/MP3/AIFF/FLAC loading
│   │   │   ├── metrics.py           # LUFS, Peak, RMS, Dynamic Range, Clipping
│   │   │   ├── stereo.py            # Correlation, Width, Mono compatibility
│   │   │   ├── spectral.py          # Spectrum, Mud/Harshness/Sibilance, Masking
│   │   │   ├── detectors.py         # Bass Balance, Vocal Presence, Separation interface
│   │   │   └── engine.py            # AnalysisEngine orchestrator
│   │   ├── reporting/                        # Phase 2
│   │   │   ├── knowledge_base.py    # Rules: thresholds + why/how/tip (Hindi)
│   │   │   └── report_generator.py  # Orchestrator: findings -> sorted report
│   │   ├── api/
│   │   │   ├── routes_analysis.py   # /analysis/track, /analysis/masking, आदि
│   │   │   └── routes_report.py     # /report/track, /report/masking, /report/vocal-in-mix
│   │   └── models/
│   │       └── schemas.py           # Pydantic request/response contracts
│   ├── tests/
│   │   ├── test_metrics.py          # Phase 1: synthetic-signal validated unit tests
│   │   └── test_report_generator.py # Phase 2: rule-trigger validated unit tests
│   └── requirements.txt
└── docs/
    └── PHASE_1_ARCHITECTURE.md
```

## चलाने का तरीका (Installation)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

# MP3 support के लिए ffmpeg system-level चाहिए:
#   Ubuntu/Debian:  sudo apt install ffmpeg
#   macOS:          brew install ffmpeg
#   Windows:        https://ffmpeg.org/download.html

uvicorn app.main:app --reload --port 8000
```

फिर browser में खोलें: **http://localhost:8000/docs** — यहाँ interactive Swagger API documentation मिलेगी जहाँ से audio file upload करके सीधे test कर सकते हैं।

## Testing

```bash
cd backend
pip install pytest
pytest tests/ -v
```

Phase 1 के सभी 16 core assertions (known sine-wave levels, clipping, phase correlation, mud/harshness/masking detection) is sandbox के अंदर numpy/scipy के साथ manually चलाकर verify किए जा चुके हैं — सब pass हैं।

## API Endpoints (Phase 1)

| Method | Path | काम |
|---|---|---|
| POST | `/api/v1/analysis/track` | एक audio file upload करें, पूरी analysis report वापस मिले |
| POST | `/api/v1/analysis/masking` | दो tracks upload करें, frequency masking conflicts मिलें |
| POST | `/api/v1/analysis/vocal-presence` | Vocal stem + full mix upload करें, presence score मिले |
| GET | `/health` | Health check |

पूरी request/response schema `/docs` पर auto-generated Swagger UI में देखें।

## अगला कदम

**Phase 4 पूरा करना (Iterative Loop)**, फिर Phase 5 (Reference Track), Phase 6 (Mastering), Phase 7 (Chat Assistant), Phase 8 (Frontend), Phase 9 (Cloud/Auth), Phase 10 (Documentation)। बताएँ अगर क्रम बदलना है।
