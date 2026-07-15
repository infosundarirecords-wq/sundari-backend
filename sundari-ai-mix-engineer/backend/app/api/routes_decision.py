"""
routes_decision.py
===================
Phase 4 API: Intelligent Multi-Provider Decision Engine.

POST /api/v1/decision/project — poore project (multiple tracks) ke liye
AI se non-preset, context-aware mixing decisions maangta hai.

Note: is endpoint ko chalane ke liye kam se kam ek provider ki API key
configured honi chahiye (.env mein ANTHROPIC_API_KEY / OPENAI_API_KEY /
GEMINI_API_KEY), ya Local LLM (Ollama) local machine par chal raha ho.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Optional

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

router = APIRouter(prefix="/decision", tags=["Decision Engine"])
analysis_engine = AnalysisEngine()


def _save_upload_to_temp(upload: UploadFile) -> str:
    ext = os.path.splitext(upload.filename or "")[1].lower()
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return tmp_path


@router.post("/project")
async def decide_project(
    files: list[UploadFile] = File(...),
    roles: str = Form(..., description="Comma-separated roles, files ke order mein — e.g. 'lead_vocal,kick,bass'"),
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
        first_loaded = None
        for file, role in zip(files, role_list):
            tmp_path = _save_upload_to_temp(file)
            tmp_paths.append(tmp_path)
            loaded = load_audio(tmp_path)
            if first_loaded is None:
                first_loaded = loaded
            result = analysis_engine.analyze_track(
                loaded.samples, loaded.sample_rate, track_name=file.filename or "Untitled",
            )
            report = generate_track_report(result, role=role)
            track_analyses.append((result, report, role))

        # Masking conflicts har pair ke beech (spec: sabhi tracks ke beech sambandh samjhe)
        masking_conflicts = []
        # Reload samples for masking comparison (simpler + memory-safe for now;
        # ek future optimization: samples ko upar hi cache karna)
        loaded_samples = []
        for path in tmp_paths:
            loaded_samples.append(load_audio(path))

        for i in range(len(loaded_samples)):
            for j in range(i + 1, len(loaded_samples)):
                if loaded_samples[i].sample_rate != loaded_samples[j].sample_rate:
                    continue
                conflicts = analysis_engine.compare_masking(
                    loaded_samples[i].samples, loaded_samples[j].samples,
                    loaded_samples[i].sample_rate,
                )
                if conflicts:
                    masking_conflicts.append({
                        "track_a": files[i].filename, "track_b": files[j].filename,
                        "conflicts": conflicts,
                    })

        # Musical features (BPM/Key genuinely detected; Genre/Mood descriptive-only)
        descriptive_features = None
        if first_loaded is not None:
            mono_mix_result = track_analyses[0][0]
            tempo = detect_bpm(first_loaded.samples, first_loaded.sample_rate)
            key = detect_musical_key(first_loaded.samples, first_loaded.sample_rate)
            features = extract_descriptive_features(
                first_loaded.samples, first_loaded.sample_rate, tempo, key,
                mono_mix_result.dr_value,
            )
            descriptive_features = {
                "tempo_bpm": features.tempo_bpm,
                "tempo_confidence": tempo.confidence,
                "key": features.key,
                "key_confidence": key.confidence,
                "spectral_brightness_hz": features.spectral_brightness_hz,
                "dynamic_range_db": features.dynamic_range_db,
                "rhythmic_density": features.rhythmic_density,
                "note": (
                    "Genre aur Mood objectively measure nahi kiye ja sakte — "
                    "AI in descriptive features ke aadhar par qualitative "
                    "interpretation dega, exact measurement nahi."
                ),
            }

        engine = DecisionEngine(provider_configs)
        decision = await engine.decide(
            track_analyses=track_analyses,
            masking_conflicts=masking_conflicts,
            descriptive_features=descriptive_features,
        )
        return decision.model_dump()

    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DecisionEngineError as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        for p in tmp_paths:
            if os.path.exists(p):
                os.remove(p)
