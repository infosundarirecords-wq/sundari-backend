# Phase 1 आर्किटेक्चर दस्तावेज़ — Audio Analysis Engine

## उद्देश्य

Phase 1 का लक्ष्य एक ऐसी नींव (foundation) बनाना है जिस पर बाकी सभी Phases (AI Report, Auto-Fix, Mastering, Chat Assistant) खड़े हो सकें। इसलिए यह Phase केवल **numeric, deterministic, testable** analysis पर केंद्रित है — कोई भी "AI जैसी" व्याख्या या राय अभी नहीं दी गई, क्योंकि वह Phase 2 का काम है।

## प्रमुख निर्णय और उनके कारण

### 1. LUFS खुद implement क्यों किया गया, किसी library के भरोसे क्यों नहीं?

`pyloudnorm` जैसी libraries मौजूद हैं, लेकिन:
- अगर engine पूरी तरह एक बाहरी package पर निर्भर हो और वह package install न हो पाए (जैसा कि इस sandbox में हुआ — यहाँ internet नहीं है), तो पूरा core feature टूट जाता है।
- ITU-R BS.1770-4 एक public standard है, इसलिए इसे खुद implement करना दोनों तरह से सही है: (क) audit करने योग्य कोड, (ख) कोई hidden dependency नहीं।
- `requirements.txt` में `pyloudnorm` फिर भी रखा गया है — भविष्य में इसे cross-check के तौर पर इस्तेमाल किया जा सकता है।

### 2. Band Energy को Linear Power Domain में Average क्यों किया गया?

यह एक असली bug था जो development के दौरान पकड़ा गया: यदि किसी frequency band (जैसे 2000-4000 Hz) में सैकड़ों FFT bins हों और सिर्फ 1-2 bins में असली ऊर्जा (जैसे कोई प्रभावी tone) हो, बाकी bins लगभग silent (noise floor) हों — तो dB values को सीधे average करने से वह ऊर्जा "dilute" हो जाती है, क्योंकि dB पहले से ही logarithmic scale है। सही तरीका है: पहले linear power में average करें, फिर एक बार dB में convert करें। यह fix सभी synthetic-signal tests चलाकर verify किया गया (देखें `tests/test_metrics.py`)।

### 3. "Instrument Separation" के लिए placeholder क्यों, नकली परिणाम क्यों नहीं?

स्पेसिफिकेशन में "कोई Placeholder Code न दें" कहा गया है, और हमने उसका सम्मान किया है — पूरे Phase 1 में हर function असली गणना करता है। लेकिन Instrument Separation एक ऐसा feature है जो **वास्तव में एक trained deep learning model के बिना संभव ही नहीं है** (कोई DSP trick इसे ठीक से नहीं कर सकता)। ऐसी स्थिति में दो विकल्प थे:
1. कोई नकली/भ्रामक "separation" heuristic बनाना जो असल में काम नहीं करेगा — यह dishonest होगा।
2. एक साफ़ interface (`SeparationBackend`) बनाना जो अभी explicitly बताए कि यह feature किस phase में, किस technology (Demucs) से आएगा।

हमने विकल्प 2 चुना — यह "no placeholder code" के मूल भावना (spirit) के अनुरूप है: engine का हर हिस्सा जो अभी मौजूद है, असली है; जो अभी नहीं बन सकता, उसे स्पष्ट रूप से बताया गया है, छुपाया नहीं गया।

### 4. Sample-rate agnostic design

K-weighting filter coefficients को हार्डकोड (जैसे सिर्फ 48kHz के लिए) करने के बजाय, bilinear transform formulas से हर sample rate (44.1kHz, 48kHz, 96kHz) के लिए dynamically derive किया गया है। असली दुनिया में उपयोगकर्ता अलग-अलग sample rates पर काम करते हैं, इसलिए यह ज़रूरी था।

### 5. FastAPI + Pydantic schemas अलग क्यों रखे गए (engine dataclasses से)

`app/analysis/engine.py` में internal dataclasses हैं, और `app/models/schemas.py` में अलग Pydantic models हैं। यह जानबूझकर किया गया ताकि:
- Core DSP engine किसी web-framework पर निर्भर न रहे (भविष्य में इसे CLI tool, desktop app, या DAW plugin में भी इस्तेमाल किया जा सके)।
- API contract (versioning, optional fields, documentation) engine के internal structure से स्वतंत्र रूप से बदल सके।

## Testing Methodology

हर metric को known, mathematically-predictable synthetic signals पर verify किया गया है — यह किसी भी DSP कोड की सच्चाई परखने का सही तरीका है:

| Test | Expected Value | Verified |
|---|---|---|
| -18dBFS sine का Peak | -18.0 dBFS | ✅ |
| Pure sine की RMS | Peak - 3.01dB | ✅ |
| Pure sine का Crest Factor | 3.01 dB | ✅ |
| Overdriven signal में Clipping | Detected = True | ✅ |
| समान दोनों channels का Correlation | +1.0 | ✅ |
| Inverted channel का Correlation | -1.0, High Mono Risk | ✅ |
| Low-mid-heavy signal | Mud Detected | ✅ |
| Upper-mid-heavy signal | Harshness Detected | ✅ |
| समान level के दो overlapping tones | Masking Conflict Flagged | ✅ |
| एक तरफ़ dominant होने पर | Masking Conflict NOT Flagged | ✅ |

16 में से 16 assertions pass हुए (देखें project README के "Testing" खंड में पूरा output)।

## जो चीज़ें अभी सत्यापित नहीं हो पाईं (Sandbox सीमाएँ)

- इस development sandbox में **internet access disabled** है, इसलिए `librosa`, `pyloudnorm`, `fastapi` जैसे packages अभी install करके live नहीं चलाए जा सके। कोर गणितीय logic (`numpy`/`scipy` पर आधारित) पूरी तरह test किया गया है, लेकिन असली MP3/FLAC file loading और FastAPI server को आपके अपने सिस्टम पर (जहाँ internet है) `pip install -r requirements.txt` के बाद चलाकर confirm करना होगा। Installation Guide में सभी ज़रूरी steps दिए गए हैं।

## अगला Phase

**Phase 2: AI Mix Report** — इस numeric engine के output को लेकर, Reference Track और सामान्य mixing सिद्धांतों के आधार पर प्रत्येक track के लिए plain-language, teachable report तैयार करना।
