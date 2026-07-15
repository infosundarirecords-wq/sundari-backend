"""
routes_analysis.py
===================
API routes for Phase 1: audio upload + analysis.

Endpoints:
  POST /api/v1/analysis/track          -> analyze a single uploaded track
  POST /api/v1/analysis/masking        -> compare two tracks for frequency masking
  POST /api/v1/analysis/vocal-presence -> compare a vocal stem against the full mix
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.analysis.loader import load_audio, UnsupportedFormatError
from app.analysis.engine import AnalysisEngine
from app.models.schemas import (
    TrackAnalysisResponse, MaskingComparisonResponse, MaskingConflictItem,
    VocalPresenceResponse,
)

router = APIRouter(prefix="/analysis", tags=["Analysis"])
engine = AnalysisEngine()


def _save_upload_to_temp(upload: UploadFile) -> str:
    ext = os.path.splitext(upload.filename or "")[1].lower()
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return tmp_path


@router.post("/track", response_model=TrackAnalysisResponse)
async def analyze_track(file: UploadFile = File(...)):
    tmp_path = _save_upload_to_temp(file)
    try:
        loaded = load_audio(tmp_path)
        result = engine.analyze_track(
            loaded.samples, loaded.sample_rate,
            track_name=file.filename or "Untitled",
        )
        return result.to_dict()
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/masking", response_model=MaskingComparisonResponse)
async def compare_masking(
    track_a: UploadFile = File(...), track_b: UploadFile = File(...),
):
    path_a = _save_upload_to_temp(track_a)
    path_b = _save_upload_to_temp(track_b)
    try:
        loaded_a = load_audio(path_a)
        loaded_b = load_audio(path_b)
        if loaded_a.sample_rate != loaded_b.sample_rate:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Sample rate mismatch: {track_a.filename} is "
                    f"{loaded_a.sample_rate}Hz, {track_b.filename} is "
                    f"{loaded_b.sample_rate}Hz. Both tracks must share the "
                    f"same sample rate for a valid comparison."
                ),
            )
        conflicts = engine.compare_masking(
            loaded_a.samples, loaded_b.samples, loaded_a.sample_rate,
        )
        return MaskingComparisonResponse(
            track_a_name=track_a.filename or "Track A",
            track_b_name=track_b.filename or "Track B",
            conflicts=[MaskingConflictItem(**c) for c in conflicts],
        )
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for p in (path_a, path_b):
            if os.path.exists(p):
                os.remove(p)


@router.post("/vocal-presence", response_model=VocalPresenceResponse)
async def vocal_presence(
    vocal: UploadFile = File(...), full_mix: UploadFile = File(...),
):
    path_vocal = _save_upload_to_temp(vocal)
    path_mix = _save_upload_to_temp(full_mix)
    try:
        loaded_vocal = load_audio(path_vocal)
        loaded_mix = load_audio(path_mix)
        result = engine.analyze_vocal_in_mix(
            loaded_vocal.samples, loaded_mix.samples, loaded_vocal.sample_rate,
        )
        return VocalPresenceResponse(**result)
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for p in (path_vocal, path_mix):
            if os.path.exists(p):
                os.remove(p)
