"""
routes_mix.py
=============

Phase 8 (Website) ke liye naya endpoint: Decision Engine se AI decisions
lekar unhe turant actual audio par render bhi karta hai, taaki website
"Analyze & Mix" ke baad ek sach mein mixed+mastered WAV file bhi de sake
— sirf text report nahi.

POST /api/v1/mix/render
  Input: same as /api/v1/decision/project (files + roles form fields)
  Output: JSON {
    "decision": <ProjectMixDecision>,
    "audio_base64": "<final mixed+mastered WAV, base64>",
    "sample_rate": int
  }

Note: yeh endpoint CPU-heavy hai (audio DSP, ho sakta hai 10-60 second
lage project size ke hisaab se) — cloud server par kaam ki wajah se
timeout settings zyada rakhein (reverse proxy / uvicorn dono mein).
"""
from __future__ import annotations

import base64
import gc
import io
import os
import shutil
import tempfile

import numpy as np
import soundfile as sf
from fastapi import APIRouter, UploadFile, File, HTTPException, Form

from app.analysis.loader import load_audio, UnsupportedFormatError
from app.analysis.engine import AnalysisEngine
from app.analysis.musical_features import (
    detect_bpm, detect_musical_key, extract_descriptive_features,
)
from app.reporting.report_generator import generate_track_report
from app.decision_engine.engine import DecisionEngine, DecisionEngineError
from app.core.config import get_settings
from app.core.config_to_providers import build_provider_configs
from app.rendering.renderer import render_project

router = APIRouter(prefix="/mix", tags=["Mix Render (Website)"])

analysis_engine = AnalysisEngine()

def save_upload_to_temp(upload: UploadFile) -> str:
    ext = os.path.splitext(upload.filename or "")[1].lower()
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return tmp_path

@router.post("/render")
async def render_mix(
    files: list[UploadFile] = File(...),
    roles: str = Form(..., description="Comma-separated roles, files ke order mein"),
    instruction: str = Form(None),
):
    role_list = [r.strip() for r in roles.split(",")]
    if len(role_list) != len(files):
        raise HTTPException(
            status_code=400,
            detail=f"{len(files)} files diye gaye lekin {len(role_list)} roles — dono ki ginti barabar honi chahiye.",
        )

    settings = get_settings()
    provider_configs = build_provider_configs(settings)
    if not provider_configs:
        raise HTTPException(
            status_code=500,
            detail=(
                "Koi bhi AI provider configured nahi hai. .env mein kam se kam "
                "ek API key set karein (ANTHROPIC_API_KEY / OPENAI_API_KEY / "
                "GEMINI_API_KEY), ya Local LLM (Ollama) chalayein."
            ),
        )

    tmp_paths = []
    try:
        track_analyses = []
        loaded_list = []

        for file, role in zip(files, role_list):
            tmp_path = save_upload_to_temp(file)
            tmp_paths.append(tmp_path)
            loaded = load_audio(tmp_path)
            loaded_list.append((loaded, file.filename or "Untitled"))

            result = analysis_engine.analyze_track(
                loaded.samples, loaded.sample_rate, track_name=file.filename or "Untitled",
            )
            report = generate_track_report(result, role=role)
            track_analyses.append((result, report, role))

        masking_conflicts = []
        for i in range(len(loaded_list)):
            for j in range(i + 1, len(loaded_list)):
                a, b = loaded_list[i][0], loaded_list[j][0]
                if a.sample_rate != b.sample_rate:
                    continue
                conflicts = analysis_engine.compare_masking(a.samples, b.samples, a.sample_rate)
                if conflicts:
                    masking_conflicts.append({
                        "track_a": loaded_list[i][1], "track_b": loaded_list[j][1],
                        "conflicts": conflicts,
                    })

        descriptive_features = None
        if loaded_list:
            first_loaded = loaded_list[0][0]
            mono_mix_result = track_analyses[0][0]
            tempo = detect_bpm(first_loaded.samples, first_loaded.sample_rate)
            key = detect_musical_key(first_loaded.samples, first_loaded.sample_rate)
            features = extract_descriptive_features(
                first_loaded.samples, first_loaded.sample_rate, tempo, key,
                mono_mix_result.dr_value,
            )
            descriptive_features = {
                "tempo_bpm": features.tempo_bpm, "tempo_confidence": tempo.confidence,
                "key": features.key, "key_confidence": key.confidence,
                "spectral_brightness_hz": features.spectral_brightness_hz,
                "dynamic_range_db": features.dynamic_range_db,
                "rhythmic_density": features.rhythmic_density,
                "note": "Genre/Mood qualitative interpretation hai, exact measurement nahi.",
            }

        engine = DecisionEngine(provider_configs)
        # NOTE: current DecisionEngine.decide() signature (engine.py) abhi
        # user_instruction accept nahi karta. Free-text instruction ("vocal
        # upfront rahe" jaisa) is Phase mein pass-through nahi ho raha —
        # future improvement: context_builder.py mein add karna hoga.
        decision = await engine.decide(
            track_analyses=track_analyses,
            masking_conflicts=masking_conflicts,
            descriptive_features=descriptive_features,
        )
        decision_dict = decision.model_dump()

        # Sample rate mismatch check — abhi simplest approach: sabse pehli track ki
        # sample rate ko common maana jaata hai; agar koi track alag hai to error.
        common_sr = loaded_list[0][0].sample_rate
        for loaded, name in loaded_list:
            if loaded.sample_rate != common_sr:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"'{name}' ki sample rate ({loaded.sample_rate}Hz) baaki tracks "
                        f"({common_sr}Hz) se match nahi karti. Sab tracks same sample "
                        f"rate par export karein aur dobara try karein."
                    ),
                )

        # role bhi pass karte hain (loaded_list aur track_analyses same order
        # mein bane the upar wale loop mein) taaki renderer.py lead_vocal ke
        # liye automatic presence/reverb/delay ambience laga sake.
        render_tracks = [
            (loaded.samples, name, role)
            for (loaded, name), (_, _, role) in zip(loaded_list, track_analyses)
        ]
        final_mix = render_project(render_tracks, decision_dict, common_sr)

        # Peak-memory ko kam karne ke liye: render ho jaane ke baad raw
        # track arrays (jo ab nahi chahiye) turant free kar dete hain,
        # aur Python ko turant garbage-collect karne ke liye kehte hain —
        # Render free-tier ki 512MB RAM limit mein fit hona zaroori hai.
        del render_tracks, loaded_list
        gc.collect()

        buf = io.BytesIO()
        sf.write(buf, final_mix.T, common_sr, format="WAV", subtype="PCM_24")
        buf.seek(0)
        audio_b64 = base64.b64encode(buf.read()).decode("ascii")

        del final_mix, buf
        gc.collect()

        return {
            "decision": decision_dict,
            "audio_base64": audio_b64,
            "sample_rate": common_sr,
        }

    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DecisionEngineError as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        for p in tmp_paths:
            if os.path.exists(p):
                os.remove(p)
