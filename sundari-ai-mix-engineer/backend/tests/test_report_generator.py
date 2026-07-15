"""
test_report_generator.py
=========================
Phase 2 (AI Mix Report + Learning Mode) ke liye synthetic-signal validated
tests. Har test yeh verify karta hai ki specific numeric condition sahi
finding trigger kare (aur galat condition mein trigger na kare).

Run with:
    cd backend && pytest tests/test_report_generator.py -v
"""

import numpy as np
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.analysis.engine import AnalysisEngine
from app.reporting.report_generator import (
    generate_track_report, generate_masking_report, add_vocal_presence_finding,
)

SR = 44100
DURATION = 4.0


def sine(freq, amp=1.0, duration=DURATION, sr=SR):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return amp * np.sin(2 * np.pi * freq * t)


@pytest.fixture
def engine():
    return AnalysisEngine()


def test_muddy_vocal_gets_mud_finding(engine):
    t = np.linspace(0, DURATION, int(SR * DURATION), endpoint=False)
    np.random.seed(2)
    muddy = 0.6 * np.sin(2 * np.pi * 350 * t) + 0.05 * np.random.randn(len(t))
    result = engine.analyze_track(np.stack([muddy, muddy]), SR, "Lead Vocal")
    report = generate_track_report(result, role="lead_vocal")
    ids = [f.id for f in report.findings]
    assert "mud" in ids


def test_clean_balanced_signal_gets_no_severe_findings(engine):
    # Ek moderate-crest-factor signal jo lead_vocal ke target range (6-11dB)
    # ke andar aaye aur koi spectral imbalance na ho.
    t = np.linspace(0, DURATION, int(SR * DURATION), endpoint=False)
    np.random.seed(3)
    signal_ = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.02 * np.random.randn(len(t))
    result = engine.analyze_track(np.stack([signal_, signal_]), SR, "Clean Vocal")
    report = generate_track_report(result, role="lead_vocal")
    severe_findings = [f for f in report.findings if f.severity == "severe"]
    assert len(severe_findings) == 0


def test_clipped_track_gets_clipping_finding(engine):
    t = np.linspace(0, DURATION, int(SR * DURATION), endpoint=False)
    raw = 3.0 * np.sin(2 * np.pi * 1000 * t)
    clipped = np.clip(raw, -1.0, 1.0)
    result = engine.analyze_track(np.stack([clipped, clipped]), SR, "Guitar")
    report = generate_track_report(result, role="guitar")
    ids = [f.id for f in report.findings]
    assert "clipping" in ids
    assert report.overall_status == "critical"


def test_out_of_phase_track_gets_mono_compatibility_finding(engine):
    mono = sine(1000, 0.5)
    result = engine.analyze_track(np.stack([mono, -mono]), SR, "Wide Synth")
    report = generate_track_report(result, role="generic")
    ids = [f.id for f in report.findings]
    assert "mono_compatibility" in ids


def test_kick_bass_masking_report_generated(engine):
    kick = sine(85, 0.5)
    bass = sine(88, 0.5)
    conflicts = engine.compare_masking(
        np.stack([kick, kick]), np.stack([bass, bass]), SR,
    )
    report = generate_masking_report("Kick", "Bass", conflicts)
    assert report is not None
    assert "bass" in report.conflicting_bands


def test_no_masking_when_frequencies_far_apart(engine):
    kick = sine(60, 0.5)
    hihat = sine(9000, 0.5)
    conflicts = engine.compare_masking(
        np.stack([kick, kick]), np.stack([hihat, hihat]), SR,
    )
    report = generate_masking_report("Kick", "Hi-Hat", conflicts)
    assert report is None


def test_master_over_target_lufs_flagged(engine):
    t = np.linspace(0, DURATION, int(SR * DURATION), endpoint=False)
    loud = 0.95 * np.sin(2 * np.pi * 1000 * t)
    result = engine.analyze_track(np.stack([loud, loud]), SR, "Master")
    report = generate_track_report(result, role="master", platform_target="spotify")
    ids = [f.id for f in report.findings]
    assert "master_loudness_target" in ids


def test_findings_sorted_severe_first(engine):
    t = np.linspace(0, DURATION, int(SR * DURATION), endpoint=False)
    raw = 3.0 * np.sin(2 * np.pi * 1000 * t)  # will clip -> severe
    clipped = np.clip(raw, -1.0, 1.0)
    result = engine.analyze_track(np.stack([clipped, clipped]), SR, "Master")
    report = generate_track_report(result, role="master", platform_target="spotify")
    severities = [f.severity for f in report.findings]
    severity_rank = {"info": 0, "mild": 1, "moderate": 2, "severe": 3}
    ranks = [severity_rank[s] for s in severities]
    assert ranks == sorted(ranks, reverse=True)


def test_vocal_presence_merged_into_report(engine):
    t = np.linspace(0, DURATION, int(SR * DURATION), endpoint=False)
    # Vocal jiski presence-band energy mix se kaafi kam hai (buried)
    vocal = 0.05 * np.sin(2 * np.pi * 1500 * t)
    mix = 0.5 * np.sin(2 * np.pi * 1500 * t) + 0.3 * np.sin(2 * np.pi * 800 * t)

    vocal_result = engine.analyze_track(np.stack([vocal, vocal]), SR, "Lead Vocal")
    base_report = generate_track_report(vocal_result, role="lead_vocal")

    presence = engine.analyze_vocal_in_mix(
        np.stack([vocal, vocal]), np.stack([mix, mix]), SR,
    )
    final_report = add_vocal_presence_finding(base_report, presence)

    ids = [f.id for f in final_report.findings]
    assert "vocal_presence_low" in ids
