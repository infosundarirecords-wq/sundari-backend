"""
knowledge_base.py
==================
Phase 2 (AI Mix Report) + Phase 3 (Learning Mode) ka gyaan-aadhar (knowledge
base). Yeh module ek deterministic, rule-based expert system hai — koi LLM
call nahi, koi randomness nahi. Har rule ek fixed numeric threshold check
karta hai (jo Phase 1 ke AnalysisEngine se aata hai) aur agar woh trigger
hoti hai, to ek "Finding" object banata hai jisme charon cheezein hoti hain:

  1. title          -> samasya kya hai (ek line mein)
  2. why_explanation -> yeh samasya kyun hoti hai / kyun sunne mein aisi lagti hai
  3. how_to_fix      -> ise kaise theek kiya jaata hai (practical steps)
  4. professional_tip-> professional engineers is baare mein kya sochte/karte hain

Design decision: thresholds yahan file ke top par constants ke roop mein
rakhe gaye hain (ek jagah), taaki Phase 4 (Auto-Fix) inhi thresholds ka
reuse kar sake — jab report kahe "compression kam hai", Auto-Fix ko pata
hona chahiye ki kis target crest-factor tak compress karna hai. Yeh
knowledge base isliye "single source of truth" hai, sirf reporting ke liye
nahi.

Thresholds ki honest limitation: yeh ITU/AES jaise kisi formal standard se
nahi aate (kyunki "compression zyada/kam hai" jaisi cheezein perceptual
hain, physically-defined nahi) — balki common mixing/mastering practice
(mastering engineers ke widely-taught guidelines) se liye gaye hain. Inhe
Phase 2 ke baad, real mixes par test karke tune kiya ja sakta hai.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any


# ---------------------------------------------------------------------------
# Track roles — har role ke apne "normal" numeric ranges hote hain.
# ---------------------------------------------------------------------------

TRACK_ROLES = (
    "lead_vocal", "backing_vocal", "kick", "snare", "bass",
    "guitar", "keys", "master", "generic",
)

# Crest factor (dB) ke "healthy" range har role ke liye — inse bahar jaane
# par hi "compression kam/zyada hai" wali finding trigger hoti hai.
CREST_FACTOR_TARGET_RANGE = {
    "lead_vocal": (6.0, 11.0),
    "backing_vocal": (5.0, 10.0),
    "kick": (8.0, 16.0),
    "snare": (7.0, 14.0),
    "bass": (5.0, 10.0),
    "guitar": (6.0, 13.0),
    "keys": (7.0, 14.0),
    "master": (6.0, 12.0),
    "generic": (5.0, 15.0),
}

# Platform-specific target integrated LUFS (master bus ke liye)
MASTERING_LUFS_TARGETS = {
    "spotify": -14.0,
    "youtube": -14.0,
    "apple_music": -16.0,
    "club": -8.0,
    "broadcast": -23.0,
}

TRUE_PEAK_SAFE_CEILING_DBTP = -1.0   # ismse zyada hone par intersample clipping ka risk
MUD_SEVERITY_ORDER = {"none": 0, "mild": 1, "moderate": 2, "severe": 3}


@dataclass
class Finding:
    id: str
    category: str          # "loudness" | "dynamics" | "spectral" | "stereo" | "clipping" | "masking"
    severity: str           # "info" | "mild" | "moderate" | "severe"
    title: str
    why_explanation: str
    how_to_fix: str
    professional_tip: str
    measured_values: dict = field(default_factory=dict)


def _severity_rank(sev: str) -> int:
    return {"info": 0, "mild": 1, "moderate": 2, "severe": 3}.get(sev, 0)


# ---------------------------------------------------------------------------
# Individual rule functions
# Har function ek TrackAnalysisResult (dataclass, Phase 1 se) aur role
# leta hai, aur agar rule trigger ho to Finding return karta hai, warna None.
# ---------------------------------------------------------------------------

def rule_clipping(result, role: str) -> Optional[Finding]:
    if not result.clipping_detected:
        return None
    severity = "severe" if result.clipped_percentage > 1.0 else "moderate"
    return Finding(
        id="clipping",
        category="clipping",
        severity=severity,
        title=f"{result.track_name} mein Clipping ho rahi hai",
        why_explanation=(
            "Jab signal 0 dBFS (digital full scale) se upar jaata hai, to waveform "
            "ke peaks 'kat' (flatten) jaate hain. Yeh harmonic distortion paida "
            "karta hai jo kaan ko crunchy/harsh sunayi deta hai, khaaskar transients "
            "(jaise kick ya snare ki attack) mein."
        ),
        how_to_fix=(
            "Track ka input gain kam karein taaki peak level 0 dBFS se neeche rahe "
            "(ideally -1 dBTP tak headroom chhodein). Agar loudness chahiye to "
            "gain reduction ke baad ek limiter use karein, gain khud badhakar clip "
            "mat karein."
        ),
        professional_tip=(
            "Professional engineers pura mix chain mein hamesha headroom rakhte "
            "hain — har stage par kam se kam -6 dB headroom aam practice hai, "
            "final limiter tak. Clipping sirf tab jaanbujhkar ki jaati hai jab "
            "woh ek creative saturation/distortion effect ho, accident nahi."
        ),
        measured_values={"clipped_percentage": result.clipped_percentage},
    )


def rule_true_peak_headroom(result, role: str) -> Optional[Finding]:
    if result.true_peak_dbtp <= TRUE_PEAK_SAFE_CEILING_DBTP:
        return None
    is_master = role == "master"
    severity = "moderate" if result.true_peak_dbtp < 0.0 else "severe"
    return Finding(
        id="true_peak_headroom",
        category="loudness",
        severity=severity,
        title=(
            "Master mein Headroom kam hai" if is_master
            else f"{result.track_name} mein True Peak headroom kam hai"
        ),
        why_explanation=(
            f"True Peak (inter-sample peak) {result.true_peak_dbtp} dBTP hai, jo "
            f"{TRUE_PEAK_SAFE_CEILING_DBTP} dBTP ki safe limit se upar hai. Jab "
            "audio ko MP3/AAC mein convert kiya jaata hai ya D/A convertor se "
            "guzarta hai, to samples ke beech ke waastavik peaks sample-peak "
            "reading se zyada ho sakte hain — isse distortion/clipping ho sakti "
            "hai chahe aapka meter 0 dBFS na dikhaye."
        ),
        how_to_fix=(
            "Master/track ke output par ek True Peak Limiter lagayein jiska "
            "ceiling -1.0 dBTP ya usse neeche set ho. Zyada aggressive loudness "
            "chahiye to limiter ke input gain ko badhayein, ceiling ko nahi."
        ),
        professional_tip=(
            "Broadcast aur streaming platforms (Spotify, YouTube, Apple Music) "
            "sabhi -1 dBTP ceiling recommend karte hain taaki unka apna encoding "
            "process clip na kare. Bina isko follow kiye master 'loud' to lagega "
            "streaming se pehle, par platform ke baad distorted sunayi de sakta hai."
        ),
        measured_values={"true_peak_dbtp": result.true_peak_dbtp},
    )


def rule_compression_amount(result, role: str) -> Optional[Finding]:
    lo, hi = CREST_FACTOR_TARGET_RANGE.get(role, CREST_FACTOR_TARGET_RANGE["generic"])
    cf = result.crest_factor_db

    if lo <= cf <= hi:
        return None

    if cf > hi:
        severity = "moderate" if cf < hi + 5 else "severe"
        return Finding(
            id="compression_too_little",
            category="dynamics",
            severity=severity,
            title=f"{result.track_name} mein Compression kam hai",
            why_explanation=(
                f"Crest factor (peak aur RMS ke beech ka antar) {cf} dB hai, jo "
                f"is role ke liye expected range ({lo}-{hi} dB) se zyada hai. "
                "Iska matlab loud transients aur quiet portions ke beech bahut "
                "zyada farak hai — track mix mein 'peeche' chali jaati hai kyunki "
                "uska average (perceived) loudness kam rehta hai, chahe peaks "
                "kaafi loud ho."
            ),
            how_to_fix=(
                "Ek compressor lagayein — moderate ratio (jaise 3:1 se 4:1) se "
                "shuru karein, attack thoda slow (10-30ms) rakhein taaki transient "
                "ki punch bachi rahe, aur release ko material ke tempo ke saath "
                "match karein. Gain reduction 3-6 dB ke aas-paas target karein, "
                "phir makeup gain se level wapas la'ayein."
            ),
            professional_tip=(
                "Professional engineers compression ko 'level karne' ke tareeke "
                "ki tarah use karte hain, na ki sirf loud banane ke liye — "
                "maksad hota hai performance ki consistency badhaana taaki track "
                "mix mein stable rahe, bina apni dynamics/emotion khoye."
            ),
            measured_values={"crest_factor_db": cf, "target_range_db": [lo, hi]},
        )
    else:
        severity = "moderate" if cf > lo - 4 else "severe"
        return Finding(
            id="compression_too_much",
            category="dynamics",
            severity=severity,
            title=f"{result.track_name} mein Compression zyada hai",
            why_explanation=(
                f"Crest factor {cf} dB hai, jo expected range ({lo}-{hi} dB) se "
                "kam hai — matlab peaks aur average level bahut close hain. "
                "Isse track 'flat', 'jaan-rahit' (lifeless), ya 'over-squashed' "
                "sunayi de sakti hai, aur natural dynamics/expression kho jaate "
                "hain."
            ),
            how_to_fix=(
                "Compressor ka ratio kam karein, threshold thoda upar (compression "
                "kam trigger ho) rakhein, ya gain reduction amount seedhe kam "
                "karein. Agar multiple compressors series mein lage hain, to "
                "unki total gain reduction check karein — kai baar problem ek "
                "compressor nahi, poora chain hota hai."
            ),
            professional_tip=(
                "Ek achha rule-of-thumb: agar aapko meter dekhe bina hi lagta hai "
                "ki kuch 'jam' gaya hai ya track boring lag rahi hai, to compression "
                "zyada hone ka pehla shak karein. Kam compression se shuru karke "
                "dheere-dheere badhaana, ulta karne se behtar hota hai."
            ),
            measured_values={"crest_factor_db": cf, "target_range_db": [lo, hi]},
        )


def rule_mud(result, role: str) -> Optional[Finding]:
    if not result.mud_detected or result.mud_severity == "none":
        return None
    return Finding(
        id="mud",
        category="spectral",
        severity=result.mud_severity,
        title=f"{result.track_name} Muddy (dhundhla/boxy) lag rahi hai",
        why_explanation=(
            f"Low-mid range (250-500 Hz) mein energy expected se "
            f"{result.band_energy_db.get('low_mid', 0)} dB ke aas-paas zyada hai. "
            "Yeh range 'boxy' ya 'muddy' character deta hai — jab bahut saare "
            "instruments (guitar, keys, vocal body, ya kai bass instruments) "
            "isi range mein overlap karte hain, to mix unclear/undefined lagta hai."
        ),
        how_to_fix=(
            "300-400 Hz ke aas-paas ek narrow-Q EQ cut lagayein (typically 2-4 dB), "
            "aur sunte hue Q/frequency adjust karein jab tak muddiness saaf na ho "
            "jaaye. High-pass filter bhi madad kar sakta hai agar track ko sub-low "
            "energy ki zaroorat nahi (jaise guitar, vocal — inhe 80-100 Hz se "
            "neeche filter karna aam practice hai)."
        ),
        professional_tip=(
            "Professional engineers har track ko cut karke 'space banate hain' "
            "before boost karne ke — mud fix karne ka behtareen tareeka hai poore "
            "mix mein 200-500 Hz range mein har instrument ko thoda-thoda carve "
            "karna, sirf ek track par bhaari cut lagane se behtar."
        ),
        measured_values={"low_mid_relative_excess_db": result.mud_severity},
    )


def rule_harshness(result, role: str) -> Optional[Finding]:
    if not result.harshness_detected or result.harshness_severity == "none":
        return None
    return Finding(
        id="harshness",
        category="spectral",
        severity=result.harshness_severity,
        title=f"{result.track_name} mein Harshness hai",
        why_explanation=(
            "Upper-mid range (2-4 kHz) mein energy expected se zyada hai. Yeh "
            "range human ear ke liye sabse zyada sensitive hoti hai (Fletcher-"
            "Munson curve ke hisaab se) — thodi si bhi excess energy yahan "
            "'fatiguing' ya 'piercing' lagti hai, khaaskar lambe samay tak "
            "sunne par."
        ),
        how_to_fix=(
            "2-4 kHz range mein ek dynamic EQ ya narrow cut (typically 2-3 dB) "
            "lagayein. Dynamic EQ behtar hai kyunki yeh sirf tab kaam karega jab "
            "harshness actually present ho (jaise loud vocal phrases mein), "
            "static cut poori track ki brightness kam kar sakta hai."
        ),
        professional_tip=(
            "Yeh galti aksar tab hoti hai jab engineer 'clarity' ya 'presence' "
            "add karne ki koshish mein upper-mids ko zyada boost kar dete hain. "
            "Professional approach hai: presence ke liye 5-8 kHz range try "
            "karein, jo bina harshness ke bhi clarity de sakta hai."
        ),
        measured_values={"upper_mid_relative_excess_db": result.harshness_severity},
    )


def rule_sibilance(result, role: str) -> Optional[Finding]:
    if role not in ("lead_vocal", "backing_vocal"):
        return None
    if not result.sibilance_detected or result.sibilance_severity == "none":
        return None
    return Finding(
        id="sibilance",
        category="spectral",
        severity=result.sibilance_severity,
        title=f"{result.track_name} mein Sibilance (tez 'S'/'T' sounds) hai",
        why_explanation=(
            "5-9 kHz range mein baar-baar short energy spikes detect hui hain, "
            "jo 's', 'sh', 'ch', 't' jaisi consonant sounds ke saath match "
            "karti hain. Yeh microphone ki proximity, singer ki technique, ya "
            "excessive high-frequency boost/compression se badh jaati hai."
        ),
        how_to_fix=(
            "Ek De-Esser plugin lagayein, jo specifically 5-9 kHz range mein "
            "compression karta hai sirf tab jab woh spike ho (baaki frequency "
            "range untouched rehta hai). Static EQ cut se bachein — woh poori "
            "vocal ki brightness kam kar dega, sirf 's' sounds ko nahi."
        ),
        professional_tip=(
            "De-essing ko hamesha EQ/compression ke baad karein, kyunki woh "
            "processing khud sibilance ko badha sakti hai. Bahut zyada de-essing "
            "se vocal 'lisping' jaisi lagne lagti hai — target hai natural "
            "sunna, robotic nahi."
        ),
        measured_values={"peaks_per_10s": result.sibilance_severity},
    )


def rule_stereo_mono_compat(result, role: str) -> Optional[Finding]:
    if result.is_mono or result.mono_compatibility_risk == "low":
        return None
    severity = "moderate" if result.mono_compatibility_risk == "medium" else "severe"
    return Finding(
        id="mono_compatibility",
        category="stereo",
        severity=severity,
        title=f"{result.track_name} Mono mein bajane par gayab/kamzor ho sakti hai",
        why_explanation=(
            f"Stereo correlation {result.stereo_correlation} hai. Jab correlation "
            "0 ke aas-paas ya negative hoti hai, to left/right channels "
            "'out-of-phase' jaisa behave karte hain — jab dono ko mono mein "
            "jod'a jaata hai (jaise club speakers, TV, phone speaker), to woh "
            "frequencies partially ya poori tarah cancel ho jaati hain."
        ),
        how_to_fix=(
            "Stereo widening plugins ka amount kam karein, ya M/S (Mid-Side) EQ "
            "se side channel ki low frequencies ko high-pass filter karein "
            "(bass/kick jaisi cheezein hamesha mid mein mono rakhna behtar hai). "
            "Agar dual-mic recording hai, to phase alignment check karein."
        ),
        professional_tip=(
            "Professional engineers regularly apne mix ko mono mein switch "
            "karke sunte hain — yeh ek standard quality-check step hai, kyunki "
            "kai real-world playback systems (club PA, Bluetooth speakers, "
            "TV) abhi bhi mono ya near-mono hote hain."
        ),
        measured_values={"correlation": result.stereo_correlation},
    )


def rule_bass_balance(result, role: str) -> Optional[Finding]:
    if role not in ("bass", "kick", "master"):
        return None
    if result.bass_balance_status == "balanced":
        return None
    if result.bass_balance_status == "boomy":
        return Finding(
            id="bass_boomy",
            category="spectral",
            severity="moderate",
            title=f"{result.track_name} mein Low Frequency (Sub-Bass) zyada hai",
            why_explanation=(
                f"Sub-bass (20-60 Hz) region, bass region (60-250 Hz) se "
                f"{result.sub_to_bass_ratio_db} dB zyada energetic hai. Bahut "
                "zyada sub-bass mix ko 'boomy' banata hai — speakers/systems "
                "jo sub-bass achhe se reproduce nahi karte (phone, laptop, "
                "chhote speakers) us par mix kamzor sunayi de sakta hai, aur "
                "jo achhe se reproduce karte hain (club system) wahan woh "
                "muddy/uncontrolled lag sakta hai."
            ),
            how_to_fix=(
                "30-50 Hz range mein high-pass filter ya gentle EQ cut lagayein "
                "(zyadatar musical content 60 Hz se upar hota hai; usse neeche "
                "sirf sub-bass 'rumble' hota hai jo control mein rakhna zaroori "
                "hai). Ek multiband compressor bhi sirf sub-bass region ko tame "
                "karne ke liye use kiya ja sakta hai."
            ),
            professional_tip=(
                "Professional mastering engineers apna mix alag-alag systems "
                "par check karte hain — studio monitors, car speakers, phone, "
                "earbuds — kyunki sub-bass ka experience system ke hisaab se "
                "bahut alag hota hai."
            ),
            measured_values={"sub_to_bass_ratio_db": result.sub_to_bass_ratio_db},
        )
    else:  # thin
        return Finding(
            id="bass_thin",
            category="spectral",
            severity="moderate",
            title=f"{result.track_name} mein Low-End Foundation kamzor hai",
            why_explanation=(
                f"Bass region energy hai lekin sub-bass region bass se "
                f"{abs(result.sub_to_bass_ratio_db)} dB kam hai — mix mein "
                "'weight' ya foundation ki kami mehsoos hoti hai, khaaskar "
                "bade sound systems par."
            ),
            how_to_fix=(
                "Bass instrument mein 40-80 Hz range mein gentle boost try "
                "karein, ya ek sub-harmonic synthesizer plugin (jo missing low "
                "octave generate karta hai) use karein. Kick drum ki sub "
                "frequency bhi is foundation ko support kar sakti hai."
            ),
            professional_tip=(
                "Boost karne se pehle check karein ki playback system khud "
                "sub-bass reproduce kar bhi sakta hai ya nahi — laptop "
                "speakers par test karte hue bass boost karna galat decisions "
                "de sakta hai."
            ),
            measured_values={"sub_to_bass_ratio_db": result.sub_to_bass_ratio_db},
        )


def rule_vocal_presence(vocal_presence_result: dict, vocal_track_name: str) -> Optional[Finding]:
    status = vocal_presence_result["status"]
    if status == "balanced":
        return None
    score = vocal_presence_result["presence_score"]
    if status in ("buried", "recessed"):
        severity = "severe" if status == "buried" else "moderate"
        return Finding(
            id="vocal_presence_low",
            category="balance",
            severity=severity,
            title=f"{vocal_track_name} peeche ja rahi hai (mix mein dabi hui)",
            why_explanation=(
                f"Vocal ki presence score {score}/100 hai. Vocal intelligibility "
                "range (1-5 kHz) mein iski energy, baaki mix ke muqable kam hai — "
                "listener ko lyrics samajhne mein mehnat karni padegi, ya vocal "
                "background instruments ke peeche 'dab' jaati hai."
            ),
            how_to_fix=(
                "Vocal ka level 1-2 dB badhayein, ya 2-5 kHz range mein presence "
                "boost EQ lagayein. Agar level badhane ke baad bhi problem rahe, "
                "to competing instruments (jaise rhythm guitar, keys) ko usi "
                "range mein thoda carve/cut karein — sabko loud karne se sabki "
                "presence kam hoti hai."
            ),
            professional_tip=(
                "Vocal ko forward rakhne ka sabse asaan tareeka hamesha level "
                "badhana nahi — balki competing instruments ke liye 'space "
                "banana' hai. Isse mix zyada balanced aur professional sunayi "
                "deta hai, sirf vocal loud karne se."
            ),
            measured_values={"presence_score": score},
        )
    else:  # forward
        return Finding(
            id="vocal_presence_high",
            category="balance",
            severity="mild",
            title=f"{vocal_track_name} zyada aage aa rahi hai",
            why_explanation=(
                f"Vocal ki presence score {score}/100 hai, jo expected range se "
                "zyada hai — vocal baaki instruments ke muqable itni dominant "
                "hai ki mix asantulit (unbalanced) lag sakta hai, khaaskar agar "
                "genre mein instruments ka bhi important role ho."
            ),
            how_to_fix=(
                "Vocal ka level 1-2 dB kam karein, ya background instruments ka "
                "level thoda badhayein taaki balance behtar ho."
            ),
            professional_tip=(
                "Yeh genre-dependent hota hai — pop/vocal-driven music mein "
                "forward vocal sahi ho sakti hai, lekin band-driven genres "
                "(rock, jazz) mein zyada balanced approach behtar sunayi deta hai."
            ),
            measured_values={"presence_score": score},
        )


def rule_master_loudness_target(result, platform: str) -> Optional[Finding]:
    target = MASTERING_LUFS_TARGETS.get(platform)
    if target is None:
        return None
    diff = result.integrated_lufs - target
    if abs(diff) < 1.0:
        return None
    severity = "mild" if abs(diff) < 3.0 else "moderate"
    direction = "zyada loud" if diff > 0 else "kam loud"
    return Finding(
        id="master_loudness_target",
        category="loudness",
        severity=severity,
        title=f"Master, {platform.replace('_', ' ').title()} ke target se {direction} hai",
        why_explanation=(
            f"Master ki Integrated Loudness {result.integrated_lufs} LUFS hai, "
            f"jabki {platform} ka standard target {target} LUFS hai (farak: "
            f"{round(diff, 1)} LU). Zyadatar streaming platforms tracks ko apne "
            "target LUFS tak automatically 'normalize' (loudness-match) karte "
            "hain — agar aapka master target se zyada loud hai, to platform use "
            "turn down kar dega, jisse dynamic range/limiting ka fayda ulta "
            "khatam ho jaata hai."
        ),
        how_to_fix=(
            f"Master ka overall gain/limiter drive adjust karein taaki Integrated "
            f"LUFS {target} LUFS ke aas-paas aaye (±1 LU). True Peak ko hamesha "
            f"-1 dBTP se neeche rakhein isi process mein."
        ),
        professional_tip=(
            "'Loudness war' se bachna hi behtar strategy hai — platform "
            "normalization ke daur mein, extra loud master ka koi fayda nahi "
            "hota, balki dynamic range/punch kho jaata hai jo actually behtar "
            "sunayi de sakta tha."
        ),
        measured_values={"integrated_lufs": result.integrated_lufs, "target_lufs": target},
    )


# ---------------------------------------------------------------------------
# Rule registry — Phase 4 (Auto-Fix) isi list ka reuse karega taaki
# "kaunsi problems fix karni hain" aur "kaise fix karni hain" ek hi
# jagah define ho, do baar nahi.
# ---------------------------------------------------------------------------

TRACK_LEVEL_RULES: list[Callable] = [
    rule_clipping,
    rule_true_peak_headroom,
    rule_compression_amount,
    rule_mud,
    rule_harshness,
    rule_sibilance,
    rule_stereo_mono_compat,
    rule_bass_balance,
]
