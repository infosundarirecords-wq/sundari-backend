"""
report_generator.py
====================
Phase 2 orchestrator: Phase 1 ke TrackAnalysisResult (aur agar available ho
to masking/vocal-presence results) ko leta hai, knowledge_base.py ke rules
chalata hai, aur ek complete MixReport banata hai — severity ke hisaab se
sorted (severe pehle), taaki user ko sabse zaroori problem sabse pehle
dikhe.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from app.reporting.knowledge_base import (
    Finding, TRACK_LEVEL_RULES, rule_vocal_presence,
    rule_master_loudness_target, _severity_rank,
)


@dataclass
class TrackReport:
    track_name: str
    track_role: str
    overall_status: str  # "excellent" | "good" | "needs_attention" | "critical"
    findings: list        # list[Finding]
    summary_line: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _overall_status_from_findings(findings: list) -> str:
    if not findings:
        return "excellent"
    max_sev = max(_severity_rank(f.severity) for f in findings)
    if max_sev >= 3:
        return "critical"
    if max_sev == 2:
        return "needs_attention"
    return "good"


def _build_summary_line(track_name: str, findings: list) -> str:
    if not findings:
        return f"{track_name} theek lag rahi hai — koi badi samasya nahi mili."
    titles = [f.title for f in sorted(findings, key=lambda f: -_severity_rank(f.severity))]
    top = titles[:2]
    if len(titles) > 2:
        return f"{track_name}: {'; '.join(top)}, aur {len(titles) - 2} aur cheezein."
    return f"{track_name}: {'; '.join(top)}."


def generate_track_report(
    result, role: str = "generic",
    platform_target: Optional[str] = None,
) -> TrackReport:
    """
    `result` -> app.analysis.engine.TrackAnalysisResult (Phase 1)
    `role`   -> "lead_vocal" | "backing_vocal" | "kick" | "snare" | "bass" |
                "guitar" | "keys" | "master" | "generic"
    `platform_target` -> agar role == "master", to "spotify"/"youtube"/
                          "apple_music"/"club"/"broadcast" mein se koi ek
    """
    findings: list = []

    for rule_fn in TRACK_LEVEL_RULES:
        finding = rule_fn(result, role)
        if finding is not None:
            findings.append(finding)

    if role == "master" and platform_target:
        f = rule_master_loudness_target(result, platform_target)
        if f is not None:
            findings.append(f)

    findings.sort(key=lambda f: -_severity_rank(f.severity))

    return TrackReport(
        track_name=result.track_name,
        track_role=role,
        overall_status=_overall_status_from_findings(findings),
        findings=findings,
        summary_line=_build_summary_line(result.track_name, findings),
    )


def add_vocal_presence_finding(track_report: TrackReport, vocal_presence_result: dict) -> TrackReport:
    """
    Vocal presence check ek alag audio pair (vocal stem + full mix) maangta
    hai, isliye yeh generate_track_report() ke andar automatically nahi
    chalta — API layer isse explicitly call karta hai jab dono files
    available hon, aur result ko existing track report mein merge kar
    deta hai.
    """
    f = rule_vocal_presence(vocal_presence_result, track_report.track_name)
    if f is not None:
        track_report.findings.append(f)
        track_report.findings.sort(key=lambda f: -_severity_rank(f.severity))
        track_report.overall_status = _overall_status_from_findings(track_report.findings)
        track_report.summary_line = _build_summary_line(
            track_report.track_name, track_report.findings,
        )
    return track_report


@dataclass
class MaskingFinding:
    track_a: str
    track_b: str
    title: str
    why_explanation: str
    how_to_fix: str
    professional_tip: str
    conflicting_bands: list


def generate_masking_report(track_a_name: str, track_b_name: str, conflicts: list) -> Optional[MaskingFinding]:
    """
    `conflicts` -> app.analysis.engine.AnalysisEngine.compare_masking() ka
    output (list of dicts: band, track_a_db, track_b_db, level_gap_db,
    severity).

    Yeh spec ke Kick vs Bass example ko generalize karta hai: koi bhi do
    tracks jo same frequency band mein "clash" kar rahe hon.
    """
    if not conflicts:
        return None

    band_names_hindi = {
        "sub_bass": "Sub-Bass (20-60 Hz)",
        "bass": "Bass (60-250 Hz)",
        "low_mid": "Low-Mid (250-500 Hz)",
        "mid": "Mid (500-2000 Hz)",
        "upper_mid": "Upper-Mid (2-4 kHz)",
        "presence": "Presence (4-6 kHz)",
        "brilliance": "Brilliance (6-20 kHz)",
    }
    band_list = [band_names_hindi.get(c["band"], c["band"]) for c in conflicts]

    return MaskingFinding(
        track_a=track_a_name,
        track_b=track_b_name,
        title=f"{track_a_name} aur {track_b_name} Clash kar rahe hain",
        why_explanation=(
            f"Dono tracks ka energy level in frequency bands mein bahut close hai: "
            f"{', '.join(band_list)}. Isse 'frequency masking' hoti hai — jab do "
            "sounds same frequency range mein compete karte hain, to dimaag dono "
            "ko alag-alag clearly sun nahi paata; ek doosre ko dabaa deta hai ya "
            "dono milkar ek 'muddy' block ban jaate hain."
        ),
        how_to_fix=(
            "In dono tracks mein se ek ko us conflicting band mein thoda cut "
            "karein (complementary EQ) — usually jo track us range mein "
            "'ownership' deserve karti hai use rehne dein (jaise bass ka fundamental "
            "note range), aur doosri track (jaise kick) ko wahan carve karein. "
            "Kick/Bass ke liye classic trick: kick ko ek narrow frequency (jaise "
            "60-80 Hz) 'apni' rakhne dein, aur bass ko us exact range mein "
            "sidechain compression ya EQ cut se thoda niche karein."
        ),
        professional_tip=(
            "Kick-Bass clash mixing ki sabse common problem hai. Professional "
            "engineers aksar complementary EQ curves banate hain — jahan ek "
            "track boost hoti hai, doosri usi jagah cut hoti hai — taaki dono ko "
            "apni-apni clear 'jagah' mil sake, bina overall low-end energy khoye."
        ),
        conflicting_bands=[c["band"] for c in conflicts],
    )
