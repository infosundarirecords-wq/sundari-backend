"""
routes_report.py
=================
Phase 2 API: AI Mix Report + Learning Mode.

Endpoints:
  POST /api/v1/report/track              -> ek track ka full teaching-style report
  POST /api/v1/report/masking             -> do tracks ke beech clash/masking report
  POST /api/v1/report/vocal-in-mix        -> vocal presence report (vocal + full mix)

`track_role` query param se yeh decide hota hai kaunse rules apply honge
(lead_vocal, backing_vocal, kick, snare, bass, guitar, keys, master, generic).
Master role ke liye `platform` bhi diya ja sakta hai
(spotify | youtube | apple_music | club | broadcast).
"""

from __future__ import annotations

import os
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional

from app.analysis.loader import load_audio, UnsupportedFormatError
from app.analysis.engine import AnalysisEngine
from app.reporting.report_generator import (
    generate_track_report, generate_masking_report, add_vocal_presence_finding,
)
from app.reporting.knowledge_base import TRACK_ROLES, MASTERING_LUFS_TARGETS
from app.models.schemas import (
    TrackReportResponse, MaskingReportResponse, FindingItem,
)

router = APIRouter(prefix="/report", tags=["AI Mix Report"])
engine = AnalysisEngine()


def _save_upload_to_temp(upload: UploadFile) -> str:
    ext = os.path.splitext(upload.filename or "")[1].lower()
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return tmp_path


def _validate_role(role: str):
    if role not in TRACK_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid track_role '{role}'. Valid options: {list(TRACK_ROLES)}",
        )


def _validate_platform(platform: Optional[str]):
    if platform is not None and platform not in MASTERING_LUFS_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform '{platform}'. Valid options: {list(MASTERING_LUFS_TARGETS)}",
        )


@router.post("/track", response_model=TrackReportResponse)
async def report_track(
    file: UploadFile = File(...),
    track_role: str = Form("generic"),
    platform: Optional[str] = Form(None),
):
    _validate_role(track_role)
    _validate_platform(platform)

    tmp_path = _save_upload_to_temp(file)
    try:
        loaded = load_audio(tmp_path)
        result = engine.analyze_track(
            loaded.samples, loaded.sample_rate,
            track_name=file.filename or "Untitled",
        )
        report = generate_track_report(result, role=track_role, platform_target=platform)
        return TrackReportResponse(
            track_name=report.track_name,
            track_role=report.track_role,
            overall_status=report.overall_status,
            findings=[FindingItem(**vars(f)) for f in report.findings],
            summary_line=report.summary_line,
        )
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/masking", response_model=MaskingReportResponse)
async def report_masking(
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
                    f"Sample rate mismatch: {track_a.filename} "
                    f"({loaded_a.sample_rate}Hz) vs {track_b.filename} "
                    f"({loaded_b.sample_rate}Hz)."
                ),
            )
        conflicts = engine.compare_masking(
            loaded_a.samples, loaded_b.samples, loaded_a.sample_rate,
        )
        report = generate_masking_report(
            track_a.filename or "Track A", track_b.filename or "Track B", conflicts,
        )
        if report is None:
            return MaskingReportResponse(
                track_a=track_a.filename or "Track A",
                track_b=track_b.filename or "Track B",
                title="Koi masking conflict nahi mila",
                why_explanation="In dono tracks ke beech koi significant frequency overlap detect nahi hui.",
                how_to_fix="Kisi badlaav ki zaroorat nahi.",
                professional_tip="Yeh accha sign hai — dono tracks apni-apni frequency space mein clear hain.",
                conflicting_bands=[],
            )
        return MaskingReportResponse(
            track_a=report.track_a, track_b=report.track_b, title=report.title,
            why_explanation=report.why_explanation, how_to_fix=report.how_to_fix,
            professional_tip=report.professional_tip,
            conflicting_bands=report.conflicting_bands,
        )
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for p in (path_a, path_b):
            if os.path.exists(p):
                os.remove(p)


@router.post("/vocal-in-mix", response_model=TrackReportResponse)
async def report_vocal_in_mix(
    vocal: UploadFile = File(...), full_mix: UploadFile = File(...),
):
    path_vocal = _save_upload_to_temp(vocal)
    path_mix = _save_upload_to_temp(full_mix)
    try:
        loaded_vocal = load_audio(path_vocal)
        loaded_mix = load_audio(path_mix)

        vocal_result = engine.analyze_track(
            loaded_vocal.samples, loaded_vocal.sample_rate,
            track_name=vocal.filename or "Vocal",
        )
        base_report = generate_track_report(vocal_result, role="lead_vocal")

        presence = engine.analyze_vocal_in_mix(
            loaded_vocal.samples, loaded_mix.samples, loaded_vocal.sample_rate,
        )
        final_report = add_vocal_presence_finding(base_report, presence)

        return TrackReportResponse(
            track_name=final_report.track_name,
            track_role=final_report.track_role,
            overall_status=final_report.overall_status,
            findings=[FindingItem(**vars(f)) for f in final_report.findings],
            summary_line=final_report.summary_line,
        )
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for p in (path_vocal, path_mix):
            if os.path.exists(p):
                os.remove(p)
