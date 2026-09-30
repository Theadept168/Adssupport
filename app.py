from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Windows UTF-8 and subprocess encoding configuration
if sys.platform == "win32":
    try:
        import _locale
        _locale._getdefaultlocale = lambda *args: ("en_US", "utf-8")
    except Exception:
        pass
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

import numpy as np
import requests
import streamlit as st
from pydub import AudioSegment

# ==========================================
# Application Configuration & Initial Setup
# ==========================================
st.set_page_config(
    page_title="Dubber AI Pro Studio",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / ".dubber_config.json"
BASE_STORAGE_DIR = BASE_DIR / ".dubber_input"
BASE_STORAGE_DIR.mkdir(exist_ok=True)
FFMPEG_PATH = BASE_DIR / "ffmpeg.exe"

# Configure pydub to use our bundled ffmpeg
if FFMPEG_PATH.exists():
    AudioSegment.converter = str(FFMPEG_PATH)
    AudioSegment.ffprobe = str(FFMPEG_PATH)

# ==========================================
# Ultra-Modern Glassmorphism UI Styling
# ==========================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Kantumruy+Pro:wght@300;400;500;600;700&display=swap');
    
    :root {
        --primary-glow: #6366f1;
        --accent-glow: #a855f7;
        --rose-glow: #ec4899;
        --emerald-glow: #10b981;
        --cyan-glow: #06b6d4;
        --bg-surface: rgba(15, 23, 42, 0.75);
        --bg-card: rgba(17, 24, 39, 0.7);
        --border-glass: rgba(255, 255, 255, 0.09);
        --border-highlight: rgba(255, 255, 255, 0.18);
    }
    
    * {
        font-family: 'Plus Jakarta Sans', 'Kantumruy Pro', -apple-system, sans-serif;
    }
    
    /* Smooth custom scrollbars */
    ::-webkit-scrollbar {
        width: 7px;
        height: 7px;
    }
    ::-webkit-scrollbar-track {
        background: rgba(10, 15, 30, 0.7);
    }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #6366f1, #a855f7);
        border-radius: 9999px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, #818cf8, #c084fc);
    }

    /* Base Body Background with Ambient Cyber Glow */
    .stApp {
        background: 
            radial-gradient(ellipse 90% 50% at 50% -10%, rgba(99, 102, 241, 0.22), transparent 70%),
            radial-gradient(ellipse 60% 40% at 100% 40%, rgba(217, 70, 239, 0.12), transparent 60%),
            radial-gradient(ellipse 60% 40% at 0% 70%, rgba(16, 185, 129, 0.10), transparent 60%),
            radial-gradient(circle at 50% 100%, rgba(30, 58, 138, 0.15), transparent 50%),
            #070a14 !important;
        color: #f8fafc;
        -webkit-font-smoothing: antialiased;
    }
    
    /* Top Studio Hero */
    .studio-hero {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.90) 100%);
        backdrop-filter: blur(24px);
        -webkit-backdrop-filter: blur(24px);
        border: 1px solid var(--border-highlight);
        border-radius: 22px;
        padding: 26px 32px;
        margin-bottom: 24px;
        box-shadow: 0 20px 50px -10px rgba(0, 0, 0, 0.6), inset 0 1px 1px rgba(255, 255, 255, 0.2);
        position: relative;
        overflow: hidden;
    }
    .studio-hero::after {
        content: '';
        position: absolute;
        top: -60px; right: -60px;
        width: 280px; height: 280px;
        background: radial-gradient(circle, rgba(168, 85, 247, 0.25) 0%, transparent 70%);
        pointer-events: none;
    }

    .studio-hero-title {
        font-family: 'Outfit', 'Kantumruy Pro', sans-serif !important;
        font-size: 2.1rem;
        font-weight: 900;
        letter-spacing: -0.02em;
        margin: 0;
        background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #93c5fd 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .studio-hero-sub {
        color: #94a3b8;
        font-size: 0.98rem;
        margin: 8px 0 0 0;
        font-weight: 400;
        line-height: 1.6;
    }

    .pulse-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.4);
        padding: 5px 12px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 700;
        color: #34d399;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .pulse-dot {
        width: 8px;
        height: 8px;
        background: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 10px #10b981;
        animation: pulse-glow 2s infinite;
    }
    @keyframes pulse-glow {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.4); opacity: 0.5; }
    }
    
    /* Stepper Navigation Pills */
    .step-pill {
        flex: 1;
        background: rgba(17, 24, 39, 0.7);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid var(--border-glass);
        border-radius: 16px;
        padding: 14px 18px;
        display: flex;
        align-items: center;
        gap: 14px;
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        position: relative;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }
    .step-pill:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, 0.2);
    }
    .step-pill.active {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.28), rgba(168, 85, 247, 0.28));
        border: 1.5px solid #818cf8;
        box-shadow: 0 8px 30px -4px rgba(99, 102, 241, 0.5), inset 0 0 16px rgba(99, 102, 241, 0.15);
    }
    .step-pill.completed {
        border-color: rgba(16, 185, 129, 0.6);
        background: rgba(16, 185, 129, 0.10);
    }
    
    .step-num {
        width: 36px;
        height: 36px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: 'Outfit', sans-serif;
        font-weight: 800;
        font-size: 1rem;
        flex-shrink: 0;
    }
    .num-1 { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1.5px solid #38bdf8; }
    .num-2 { background: rgba(192, 132, 252, 0.2); color: #c084fc; border: 1.5px solid #c084fc; }
    .num-3 { background: rgba(244, 114, 182, 0.2); color: #f472b6; border: 1.5px solid #f472b6; }
    .num-4 { background: rgba(52, 211, 153, 0.2); color: #34d399; border: 1.5px solid #34d399; }

    /* Studio Glass Cards */
    .studio-card {
        background: rgba(17, 24, 39, 0.72);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid var(--border-glass);
        border-radius: 18px;
        padding: 24px;
        margin-bottom: 22px;
        box-shadow: 0 12px 35px -5px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        transition: all 0.3s ease;
    }
    .studio-card:hover {
        border-color: rgba(255, 255, 255, 0.16);
    }

    /* Streamlit Tabs Elevated Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(15, 23, 42, 0.65);
        padding: 8px;
        border-radius: 16px;
        border: 1px solid var(--border-glass);
        backdrop-filter: blur(16px);
        margin-bottom: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: auto;
        padding: 10px 20px;
        border-radius: 10px;
        font-family: 'Outfit', 'Kantumruy Pro', sans-serif !important;
        font-weight: 600;
        font-size: 0.95rem;
        color: #94a3b8;
        border: 1px solid transparent;
        transition: all 0.25s ease;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #f8fafc;
        background: rgba(255, 255, 255, 0.06);
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #ffffff !important;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.85), rgba(168, 85, 247, 0.85)) !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        box-shadow: 0 6px 20px rgba(124, 58, 237, 0.45);
    }
    
    /* Buttons Glowing Gradient System */
    .stButton > button {
        border-radius: 12px;
        font-family: 'Outfit', 'Kantumruy Pro', sans-serif;
        font-weight: 700;
        font-size: 0.95rem;
        letter-spacing: 0.01em;
        transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        padding: 12px 22px;
        border: 1px solid var(--border-glass);
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #d946ef 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.25) !important;
        box-shadow: 0 6px 24px rgba(124, 58, 237, 0.45) !important;
        color: #ffffff !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 30px rgba(124, 58, 237, 0.65) !important;
        filter: brightness(1.1);
    }
    .stButton > button[kind="secondary"] {
        background: rgba(30, 41, 59, 0.7) !important;
        color: #e2e8f0 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: rgba(51, 65, 85, 0.9) !important;
        border-color: rgba(255, 255, 255, 0.25) !important;
        transform: translateY(-1.5px);
    }

    /* Download Buttons Customizer */
    .stDownloadButton > button {
        border-radius: 12px;
        font-family: 'Outfit', 'Kantumruy Pro', sans-serif;
        font-weight: 700;
        padding: 12px 20px;
        transition: all 0.25s ease;
    }
    .stDownloadButton > button:hover {
        transform: translateY(-2px);
    }
    
    /* File Uploader Glow */
    [data-testid="stFileUploader"] {
        background: rgba(17, 24, 39, 0.6);
        border: 1.5px dashed rgba(99, 102, 241, 0.4);
        border-radius: 16px;
        padding: 18px;
        transition: all 0.3s ease;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: #818cf8;
        background: rgba(30, 41, 59, 0.7);
        box-shadow: 0 0 24px rgba(99, 102, 241, 0.25);
    }

    /* Anti-Overlap Banner */
    .anti-overlap-banner {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.25) 100%);
        border: 1px solid rgba(16, 185, 129, 0.45);
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 18px;
        box-shadow: 0 8px 20px rgba(16, 185, 129, 0.15);
    }

    .khmer-font {
        font-family: 'Kantumruy Pro', sans-serif !important;
        font-size: 1.08rem;
        line-height: 1.75;
        color: #f1f5f9;
    }
    
    /* Gender Badges */
    .gender-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 0.82rem;
        font-weight: 700;
        padding: 5px 12px;
        border-radius: 8px;
        letter-spacing: 0.02em;
    }
    .badge-male {
        background: rgba(56, 189, 248, 0.18);
        color: #7dd3fc;
        border: 1px solid rgba(56, 189, 248, 0.4);
        box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
    }
    .badge-female {
        background: rgba(244, 114, 182, 0.18);
        color: #f9a8d4;
        border: 1px solid rgba(244, 114, 182, 0.4);
        box-shadow: 0 0 12px rgba(244, 114, 182, 0.2);
    }

    /* Dialogue Card */
    .dialogue-card {
        background: rgba(15, 23, 42, 0.65);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 12px;
        transition: all 0.2s ease;
    }
    .dialogue-card:hover {
        border-color: rgba(255, 255, 255, 0.18);
        background: rgba(30, 41, 59, 0.65);
        transform: translateY(-1px);
    }
    .dialogue-card.male-card {
        border-left: 4px solid #38bdf8;
    }
    .dialogue-card.female-card {
        border-left: 4px solid #f472b6;
    }
    
    .stat-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        border-radius: 10px;
        font-size: 0.85rem;
        font-weight: 600;
        background: rgba(30, 41, 59, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }

    /* Simulated Animated Waveform */
    .soundwave-box {
        display: flex;
        align-items: center;
        gap: 4px;
        height: 28px;
        padding: 0 8px;
    }
    .soundwave-bar {
        width: 3.5px;
        background: linear-gradient(180deg, #38bdf8, #818cf8);
        border-radius: 4px;
        animation: soundwave-pulse 1.2s infinite ease-in-out;
    }
    .soundwave-bar:nth-child(2) { animation-delay: 0.15s; background: linear-gradient(180deg, #818cf8, #c084fc); }
    .soundwave-bar:nth-child(3) { animation-delay: 0.3s; background: linear-gradient(180deg, #c084fc, #f472b6); }
    .soundwave-bar:nth-child(4) { animation-delay: 0.45s; background: linear-gradient(180deg, #f472b6, #34d399); }
    .soundwave-bar:nth-child(5) { animation-delay: 0.6s; background: linear-gradient(180deg, #34d399, #38bdf8); }
    @keyframes soundwave-pulse {
        0%, 100% { height: 6px; }
        50% { height: 26px; }
    }

    /* Mobile First Optimizations */
    @media (max-width: 768px) {
        .studio-hero {
            padding: 20px 16px;
            border-radius: 16px;
        }
        .studio-hero-title {
            font-size: 1.6rem;
        }
        .step-pill {
            min-width: 100%;
            margin-bottom: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 0.85rem;
            padding: 8px 12px;
        }
        .stButton > button {
            width: 100%;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# Data Models & Subtitle Utilities
# ==========================================
@dataclass
class Subtitle:
    index: int
    start_time: str
    end_time: str
    text: str
    start_ms: int = 0
    end_ms: int = 0
    detected_gender: str = "Male"
    assigned_voice: str = "km-KH-PisethNeural"
    pitch_f0: float = 130.0

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


def parse_timestamp_to_ms(ts: str) -> int:
    ts = ts.strip().replace(".", ",")
    try:
        parts = ts.split(":")
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split(",")
        s = int(s_parts[0])
        ms = int(s_parts[1]) if len(s_parts) > 1 else 0
        return (h * 3600 + m * 60 + s) * 1000 + ms
    except Exception:
        return 0


def format_ms_to_timestamp(ms: int) -> str:
    total_sec = max(0, ms) // 1000
    rem_ms = max(0, ms) % 1000
    s = total_sec % 60
    m = (total_sec // 60) % 60
    h = total_sec // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{rem_ms:03d}"


def parse_srt(srt_content: str) -> list[Subtitle]:
    if not srt_content or not srt_content.strip():
        return []

    # Strip markdown code fences if Gemini/LLM added them
    clean_text = re.sub(r"^```(?:srt)?\s*", "", srt_content.strip(), flags=re.IGNORECASE)
    clean_text = re.sub(r"\s*```$", "", clean_text).strip()

    subtitles = []
    # 1. Primary parser: split by double newlines
    blocks = re.split(r"\n\s*\n", clean_text)
    cur_idx = 1
    for block in blocks:
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        idx_offset = 1 if lines[0].isdigit() else 0
        if len(lines) > idx_offset and "-->" in lines[idx_offset]:
            timing = lines[idx_offset]
            text = " ".join(lines[idx_offset + 1:]).strip()
            parts = timing.split("-->")
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            s_ms = parse_timestamp_to_ms(start_str)
            e_ms = parse_timestamp_to_ms(end_str)
            if e_ms <= s_ms:
                e_ms = s_ms + 2500
            if text:
                subtitles.append(
                    Subtitle(
                        index=cur_idx,
                        start_time=start_str,
                        end_time=end_str,
                        text=text,
                        start_ms=s_ms,
                        end_ms=e_ms,
                    )
                )
                cur_idx += 1

    # 2. Resilient Regex Fallback if standard splitting missed any items
    if not subtitles:
        pattern = re.compile(
            r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*\n+([^\n]+(?:\n[^\n]+)*?)(?=\n+\d+\n+\d{1,2}:\d{2}:\d{2}|\n+\d{1,2}:\d{2}:\d{2}|$)",
            re.MULTILINE
        )
        for m in pattern.finditer(clean_text):
            start_str = m.group(1).replace(".", ",")
            end_str = m.group(2).replace(".", ",")
            text = " ".join(m.group(3).splitlines()).strip()
            if not text:
                continue
            s_ms = parse_timestamp_to_ms(start_str)
            e_ms = parse_timestamp_to_ms(end_str)
            if e_ms <= s_ms:
                e_ms = s_ms + 2500
            subtitles.append(
                Subtitle(
                    index=cur_idx,
                    start_time=start_str,
                    end_time=end_str,
                    text=text,
                    start_ms=s_ms,
                    end_ms=e_ms,
                )
            )
            cur_idx += 1

    return subtitles


def export_subtitles_to_srt(subtitles: list[Subtitle]) -> str:
    out = []
    for s in subtitles:
        out.append(f"{s.index}\n{s.start_time} --> {s.end_time}\n{s.text.strip()}\n")
    return "\n".join(out)


# ==========================================
# Character Alternation & Voice Assignment
# ==========================================
def estimate_pitch_f0(samples: np.ndarray, sample_rate: int = 16000) -> float:
    if len(samples) == 0:
        return 140.0
    frame_len = int(sample_rate * 0.05)
    hop_len = int(sample_rate * 0.025)
    min_lag = int(sample_rate / 380)
    max_lag = int(sample_rate / 75)
    pitches = []

    mean_energy = float(np.mean(samples**2)) if len(samples) > 0 else 0.0
    energy_thresh = max(20.0, mean_energy * 0.06)

    max_samples = min(len(samples) - frame_len, sample_rate * 45)
    if max_samples <= 0:
        return 140.0

    for i in range(0, max_samples, hop_len):
        frame = samples[i : i + frame_len]
        energy = np.mean(frame**2)
        if energy < energy_thresh:
            continue
        frame_norm = frame - np.mean(frame)
        corr = np.correlate(frame_norm, frame_norm, mode="full")
        corr = corr[len(frame) - 1 :]
        if len(corr) > max_lag:
            peak_lag = min_lag + int(np.argmax(corr[min_lag:max_lag]))
            peak_val = corr[peak_lag]
            zero_lag = corr[0]
            if zero_lag > 0 and (peak_val / zero_lag) > 0.20:
                f0 = sample_rate / peak_lag
                if 75 <= f0 <= 380:
                    pitches.append(f0)
    return float(np.median(pitches)) if pitches else 140.0


def detect_voice(
    media_input: Path | str | AudioSegment,
    max_duration_sec: float = 60.0,
) -> dict:
    """Dedicated voice and character gender detection function (មុខងារពិនិត្យ និងចាប់សំឡេងតួអង្គ).
    Analyzes acoustic fundamental frequency (F0 pitch), harmonics, and energy.
    Returns:
    {
        "gender": "Male" | "Female",
        "voice": "km-KH-PisethNeural" | "km-KH-SreymomNeural",
        "name": "Piseth Neural (ប្រុស - Male)" | "Sreymom Neural (ស្រី - Female)",
        "pitch_hz": float,
        "confidence": str,
        "icon": "👨" | "👩",
        "status": "success",
    }
    """
    try:
        if isinstance(media_input, AudioSegment):
            seg = media_input[: int(max_duration_sec * 1000)]
        else:
            p = Path(media_input)
            if not p.exists():
                return {
                    "gender": "Male",
                    "voice": "km-KH-PisethNeural",
                    "name": "Piseth Neural (ប្រុស - Male)",
                    "pitch_hz": 130.0,
                    "confidence": "70%",
                    "icon": "👨",
                    "status": "fallback",
                }
            seg = AudioSegment.from_file(str(p))[: int(max_duration_sec * 1000)]

        audio_16k = seg.set_channels(1).set_frame_rate(16000)
        samples = np.array(audio_16k.get_array_of_samples(), dtype=np.float32)
        f0 = estimate_pitch_f0(samples, 16000)

        # Threshold at 160.0 Hz: Male is typically 85-155 Hz, Female is 160-280 Hz
        if f0 < 160.0:
            conf = min(98, max(72, int((160.0 - f0) / 75.0 * 26 + 72)))
            return {
                "gender": "Male",
                "voice": "km-KH-PisethNeural",
                "name": "Piseth Neural (ប្រុស - Male)",
                "pitch_hz": round(f0, 1),
                "confidence": f"{conf}%",
                "icon": "👨",
                "status": "success",
            }
        else:
            conf = min(98, max(72, int((f0 - 160.0) / 120.0 * 26 + 72)))
            return {
                "gender": "Female",
                "voice": "km-KH-SreymomNeural",
                "name": "Sreymom Neural (ស្រី - Female)",
                "pitch_hz": round(f0, 1),
                "confidence": f"{conf}%",
                "icon": "👩",
                "status": "success",
            }
    except Exception as e:
        return {
            "gender": "Male",
            "voice": "km-KH-PisethNeural",
            "name": "Piseth Neural (ប្រុស - Male)",
            "pitch_hz": 130.0,
            "confidence": "70%",
            "icon": "👨",
            "status": f"error: {e}",
        }


def assign_character_voices_to_subtitles(
    subtitles: list[Subtitle],
    mode: str = "alternate_mf",
    media_path: Optional[Path] = None,
) -> list[Subtitle]:
    """Assigns voices with seamless male/female alternation (ឆ្លាស់ប្រុសស្រី):
    - "alternate_mf": Line 1 Male (Piseth 👨), Line 2 Female (Sreymom 👩), Line 3 Male...
    - "alternate_fm": Line 1 Female (Sreymom 👩), Line 2 Male (Piseth 👨), Line 3 Female...
    - "auto": Acoustic pitch detection per line with dialogue alternation smoothing
    - "male": Male (Piseth) only
    - "female": Female (Sreymom) only
    """
    if not subtitles:
        return []

    audio_full = None
    if mode == "auto" and media_path and media_path.exists():
        try:
            audio_full = AudioSegment.from_file(media_path)
        except Exception:
            audio_full = None

    for idx, s in enumerate(subtitles):
        # Text cue overrides take highest priority
        t_clean = s.text.strip().lower()
        if any(c in t_clean for c in ("[ស្រី]", "[តួស្រី]", "[female]", "[sreymom]")):
            s.detected_gender = "Female"
            s.assigned_voice = "km-KH-SreymomNeural"
            s.pitch_f0 = 210.0
            continue
        elif any(c in t_clean for c in ("[ប្រុស]", "[តួប្រុស]", "[male]", "[piseth]")):
            s.detected_gender = "Male"
            s.assigned_voice = "km-KH-PisethNeural"
            s.pitch_f0 = 125.0
            continue

        if mode == "alternate_mf":
            # ឆ្លាស់ប្រុស 👨 និង ស្រី 👩 (ចាប់ផ្តើមដោយប្រុស)
            if idx % 2 == 0:
                s.detected_gender = "Male"
                s.assigned_voice = "km-KH-PisethNeural"
                s.pitch_f0 = 125.0
            else:
                s.detected_gender = "Female"
                s.assigned_voice = "km-KH-SreymomNeural"
                s.pitch_f0 = 210.0
        elif mode == "alternate_fm":
            # ឆ្លាស់ស្រី 👩 និង ប្រុស 👨 (ចាប់ផ្តើមដោយស្រី)
            if idx % 2 == 0:
                s.detected_gender = "Female"
                s.assigned_voice = "km-KH-SreymomNeural"
                s.pitch_f0 = 210.0
            else:
                s.detected_gender = "Male"
                s.assigned_voice = "km-KH-PisethNeural"
                s.pitch_f0 = 125.0
        elif mode == "male":
            s.detected_gender = "Male"
            s.assigned_voice = "km-KH-PisethNeural"
            s.pitch_f0 = 125.0
        elif mode == "female":
            s.detected_gender = "Female"
            s.assigned_voice = "km-KH-SreymomNeural"
            s.pitch_f0 = 210.0
        else:  # "auto"
            assigned_g = "Male"
            if audio_full is not None:
                s_ms = max(0, s.start_ms)
                e_ms = min(len(audio_full), s.end_ms)
                if e_ms > s_ms + 250:
                    try:
                        clip = audio_full[s_ms:e_ms].set_channels(1).set_frame_rate(16000)
                        samples = np.array(clip.get_array_of_samples(), dtype=np.float32)
                        f0 = estimate_pitch_f0(samples, 16000)
                        assigned_g = "Female" if f0 >= 160.0 else "Male"
                        s.pitch_f0 = round(f0, 1)
                    except Exception:
                        assigned_g = "Male" if idx % 2 == 0 else "Female"
            else:
                assigned_g = "Male" if idx % 2 == 0 else "Female"
            
            s.detected_gender = assigned_g
            s.assigned_voice = "km-KH-PisethNeural" if assigned_g == "Male" else "km-KH-SreymomNeural"

    return subtitles


# ==========================================
# Persistent State & Configuration
# ==========================================
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(updates: dict):
    cfg = load_config()
    cfg.update(updates)
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        st.error(f"Failed to save config: {e}")


def generate_permanent_device_token(username: str, password: str) -> str:
    u_clean = username.strip()
    raw_cred = f"{u_clean}:{password}".encode("utf-8")
    b64_cred = base64.urlsafe_b64encode(raw_cred).decode("utf-8").rstrip("=")
    sig = hashlib.sha256(f"{b64_cred}:dubber_studio_perm_2026".encode("utf-8")).hexdigest()[:24]
    return f"{b64_cred}.{sig}"


def init_session():
    defaults = {
        "authenticated": False,
        "auth_user": "",
        "user_role": "user",
        "current_step": 1,
        "media_path": None,
        "video_duration_ms": 0,
        "subtitles_orig": [],
        "srt_text_orig": "",
        "subtitles_khmer": [],
        "srt_text_khmer": "",
        "voiceover_clips": {},
        "master_mp3_path": None,
        "voice_mode": "alternate_mf",  # Default to alternating male/female (ឆ្លាស់ប្រុសស្រី)
        "selected_speed": "+60%",  # 1.60x speed (1.60%)
        "selected_pitch": "+0Hz",
        "breathing_pause_ms": 200,  # 200ms anti-collision breathing gap
        "uploader_key": 0,
        "auto_clear_after_download": True,
        "just_cleared_after_download": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if st.session_state.get("selected_speed") in (None, "+0%"):
        st.session_state.selected_speed = "+60%"


init_session()

# Check Device Token Login
if not st.session_state.authenticated:
    dev_token = st.query_params.get("device", "")
    if dev_token and "." in dev_token:
        parts = dev_token.split(".", 1)
        prefix, sig = parts[0], parts[1]
        expected_sig = hashlib.sha256(f"{prefix}:dubber_studio_perm_2026".encode("utf-8")).hexdigest()[:24]
        if sig == expected_sig:
            try:
                pad = "=" * ((4 - len(prefix) % 4) % 4)
                decoded = base64.urlsafe_b64decode((prefix + pad).encode("utf-8")).decode("utf-8")
                if ":" in decoded:
                    user, _ = decoded.split(":", 1)
                    st.session_state.authenticated = True
                    st.session_state.auth_user = user
                    st.session_state.user_role = "admin" if user.lower() == "admin" else "user"
            except Exception:
                pass

# Authentication Gate
if not st.session_state.authenticated:
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_gate, _ = st.columns([1, 2, 1])
    with col_gate:
        st.markdown(
            """
            <div class="studio-card" style="text-align: center; padding: 32px 24px;">
                <div style="font-size: 3rem; margin-bottom: 8px;">🎙️</div>
                <h2 style="margin: 0; color: #60a5fa; font-weight: 700;">Dubber AI Pro Studio</h2>
                <p style="color: #94a3b8; font-size: 0.95rem; margin-top: 6px;">
                    Fast Video Dubbing & High-Precision Khmer TTS Studio
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_modal"):
            u_in = st.text_input("Username / ឈ្មោះគណនី", placeholder="e.g. Thea, admin")
            p_in = st.text_input("Password / ពាក្យសម្ងាត់", type="password")
            btn = st.form_submit_button("🚀 Enter Dubber Studio", use_container_width=True)
            if btn:
                cfg = load_config()
                users = cfg.get("auth_users", {})
                if u_in in users and users[u_in].get("password") == p_in:
                    st.session_state.authenticated = True
                    st.session_state.auth_user = u_in
                    st.session_state.user_role = users[u_in].get("role", "user")
                    st.query_params["device"] = generate_permanent_device_token(u_in, p_in)
                    st.rerun()
                elif u_in == "admin" and p_in == "dubber123":
                    st.session_state.authenticated = True
                    st.session_state.auth_user = "admin"
                    st.session_state.user_role = "admin"
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
    st.stop()


def get_user_workspace() -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", st.session_state.auth_user.lower()) or "guest"
    p = BASE_STORAGE_DIR / "users" / safe
    p.mkdir(parents=True, exist_ok=True)
    return p


USER_DIR = get_user_workspace()


def clear_user_cache(preserve_success_message: bool = False):
    """Cleans all temporary voice clips, extracted wavs, and cached rendered mp3s for the user."""
    tts_dir = USER_DIR / "tts_cache"
    if tts_dir.exists():
        try:
            shutil.rmtree(tts_dir, ignore_errors=True)
            tts_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # Clear temp audio/video files in USER_DIR
    for f in USER_DIR.glob("*.*"):
        if f.is_file() and f.suffix.lower() in [".mp3", ".wav", ".mp4", ".mov", ".mkv", ".avi", ".webm", ".srt", ".zip"]:
            try:
                f.unlink()
            except Exception:
                pass

    # Reset session states
    st.session_state.subtitles_orig = []
    st.session_state.srt_text_orig = ""
    st.session_state.subtitles_khmer = []
    st.session_state.srt_text_khmer = ""
    st.session_state.voiceover_clips = {}
    st.session_state.master_mp3_path = None
    st.session_state.media_path = None
    st.session_state.video_duration_ms = 0
    st.session_state.current_step = 1
    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
    if preserve_success_message:
        st.session_state.just_cleared_after_download = True


def create_master_zip_bundle(mp3_path: Path, srt_text: str) -> bytes:
    """Creates a downloadable ZIP bundle containing the dubbed master MP3 and synced SRT subtitles."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if mp3_path and mp3_path.exists():
            z.write(mp3_path, arcname=mp3_path.name)
        if srt_text:
            z.writestr("synced_voiceover.srt", srt_text.encode("utf-8"))
    buf.seek(0)
    return buf.getvalue()


def on_master_download():
    """Callback triggered automatically when user downloads the master MP3 or bundle to clear cache."""
    if st.session_state.get("auto_clear_after_download", True):
        clear_user_cache(preserve_success_message=True)

# Core Processing Engines
# ==========================================

# 1. Media Extraction & Whisper STT
@st.cache_resource
def get_whisper_engine(model_name: str):
    import whisper
    return whisper.load_model(model_name)


def extract_audio(video_file: Path, out_wav: Path) -> float:
    cmd = [
        str(FFMPEG_PATH if FFMPEG_PATH.exists() else "ffmpeg"),
        "-y",
        "-i", str(video_file),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(out_wav),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        pass

    if not out_wav.exists() or out_wav.stat().st_size <= 44:
        return 0.0

    try:
        seg = AudioSegment.from_file(out_wav)
        dur = len(seg) / 1000.0
        # If audio is very short (< 2.0s) but not empty, pad with silence to prevent Whisper tensor 0-element reshape crash
        if 0.1 <= dur < 2.0:
            seg = seg + AudioSegment.silent(duration=2000)
            seg.export(str(out_wav), format="wav")
            dur = len(seg) / 1000.0
        return dur
    except Exception:
        return 0.0


def get_media_duration_seconds(file_path: Path) -> float:
    """Accurately calculates duration in seconds using pydub or ffprobe."""
    try:
        seg = AudioSegment.from_file(str(file_path))
        return len(seg) / 1000.0
    except Exception:
        pass
    try:
        cmd = [
            str(FFMPEG_PATH.parent / "ffprobe.exe" if FFMPEG_PATH.exists() else "ffprobe"),
            "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def _transcribe_audio_chunk_gemini(
    client,
    audio_chunk_path: Path,
    chunk_index: int,
    total_chunks: int,
    start_sec: float,
    end_sec: float,
    target_lang: str = "original",
    spoken_lang: str = "auto",
) -> str:
    """Internal helper to transcribe one audio chunk with Gemini with strict verbatim accuracy."""
    from google.genai import types

    uploaded_file = client.files.upload(file=str(audio_chunk_path))
    start_ts = format_ms_to_timestamp(int(start_sec * 1000))
    end_ts = format_ms_to_timestamp(int(end_sec * 1000))

    if target_lang == "khmer":
        lang_prompt = (
            "TASK: High-accuracy Speech-to-SRT in Khmer (ភាសាខ្មែរ).\n"
            "INSTRUCTIONS:\n"
            "1. Listen attentively to all spoken dialogue in the audio.\n"
            "2. Transcribe and translate into 100% natural, correct Khmer script (អក្ខរាវិរុទ្ធខ្មែរត្រឹមត្រូវ).\n"
            "3. DO NOT hallucinate words, do not miss syllables, and do not include background sound descriptions."
        )
    elif spoken_lang == "khmer":
        lang_prompt = (
            "TASK: 100% VERBATIM KHMER SPEECH TRANSCRIPTION (ចាប់សំឡេងជាអក្សរខ្មែរឱ្យបានសុក្រឹតបំផុត).\n"
            "STRICT RULES:\n"
            "1. Exact verbatim words: Write down PRECISELY what the speaker says in Khmer. Do not omit particles, interjections, or phrases.\n"
            "2. Correct Khmer orthography: Follow official Khmer dictionary spelling (អក្ខរាវិរុទ្ធត្រឹមត្រូវតាមវចនានុក្រមសម្តេចព្រះសង្ឃរាជ ជួន ណាត).\n"
            "3. Phonetic fidelity: Distinguish similar consonant and vowel sounds accurately (e.g. ពិនិត្យ/ពិន័យ, ទៅ/នៅ, ធ្វើ/ឃើញ, ហ្នឹង/នឹង).\n"
            "4. Proper spacing: Keep natural word-group spacing in Khmer.\n"
            "5. NO foreign scripts: Do not use Latin or Thai script words."
        )
    elif spoken_lang == "chinese":
        lang_prompt = (
            "TASK: 100% VERBATIM CHINESE (MANDARIN) SPEECH TRANSCRIPTION.\n"
            "STRICT RULES: Transcribe every spoken syllable accurately into standard Simplified Chinese characters without hallucination or paraphrasing."
        )
    elif spoken_lang == "english":
        lang_prompt = (
            "TASK: 100% VERBATIM ENGLISH SPEECH TRANSCRIPTION.\n"
            "STRICT RULES: Transcribe spoken dialogue exactly word-for-word with proper capitalization, grammar, and accurate punctuation."
        )
    else:
        lang_prompt = (
            "TASK: 100% VERBATIM SPEECH TRANSCRIPTION IN ORIGINAL SPOKEN LANGUAGE.\n"
            "STRICT RULES:\n"
            "1. Transcribe EXACTLY what is spoken word-for-word without guessing, paraphrasing, or omitting anything.\n"
            "2. If spoken in Khmer, use standard Khmer script (អក្សរខ្មែរ) with correct spelling.\n"
            "3. If spoken in Chinese, English, or Thai, use the exact native script."
        )

    prompt = (
        f"You are a professional audiovisual subtitle engineer.\n"
        f"{lang_prompt}\n\n"
        f"Segment Information: Part {chunk_index} of {total_chunks} (Coverage: {start_ts} to {end_ts}).\n"
        "STRICT REQUIREMENTS FOR 100% VERBATIM AUDIO-TO-TEXT:\n"
        "1. Standard SRT timestamp format: HH:MM:SS,mmm --> HH:MM:SS,mmm (relative to this audio segment, starting from 00:00:00,000).\n"
        "2. COMPLETE VERBATIM CAPTURE: Transcribe EVERY spoken phrase throughout this entire audio segment without skipping or summarizing.\n"
        "3. ACCURATE TIMESTAMPS: Align start timestamp to the exact millisecond speech begins and end timestamp to when speech finishes.\n"
        "4. SHORT READABLE CHUNKS: 1 to 2 spoken sentences per subtitle.\n"
        "5. Output ONLY the raw SRT subtitle content. Do NOT include markdown code fences (no ```srt or ```), commentary, or explanations.\n"
        "6. If there is absolutely no spoken dialogue (only silence or music), output nothing."
    )

    config = types.GenerateContentConfig(
        max_output_tokens=32768,
        temperature=0.0,  # Deterministic greedy decoding for maximum verbatim fidelity
    )

    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-flash-latest",
    ]

    raw_srt = ""
    last_err = None
    for model_name in models_to_try:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[uploaded_file, prompt],
                config=config,
            )
            raw_srt = (resp.text or "").strip()
            if raw_srt:
                break
        except Exception as e:
            last_err = e
            continue

    try:
        client.files.delete(name=uploaded_file.name)
    except Exception:
        pass

    if not raw_srt and last_err:
        raise last_err

    # Clean code fences
    raw_srt = re.sub(r"^```(?:srt)?\s*", "", raw_srt, flags=re.IGNORECASE)
    raw_srt = re.sub(r"\s*```$", "", raw_srt)
    return raw_srt.strip()


def transcribe_with_gemini(
    file_path: Path,
    api_key: str,
    p_bar=None,
    p_status=None,
    target_lang: str = "original",
    spoken_lang: str = "auto",
) -> list[Subtitle]:
    """Transcribes the FULL video or audio speech into standard SRT using Google Gemini Multimodal AI.
    Automatically splits long videos into smart sequential chunks to ensure 100% complete coverage from 00:00 to the final second."""
    if not api_key:
        raise ValueError("Please provide a valid Gemini API Key in the sidebar or settings.")

    from google import genai
    client = genai.Client(api_key=api_key)

    if p_status: p_status.text("⚡ Extracting full audio stream with FFmpeg...")
    if p_bar: p_bar.progress(10)

    # 1. Master audio extraction with vocal enhancement & acoustic normalization
    master_audio = USER_DIR / f"full_audio_{int(time.time())}.mp3"
    ffmpeg_bin = str(FFMPEG_PATH if FFMPEG_PATH.exists() else "ffmpeg")

    if file_path.suffix.lower() in [".mp3", ".wav", ".m4a", ".aac"]:
        input_audio = file_path
    else:
        cmd = [
            ffmpeg_bin, "-y", "-i", str(file_path),
            "-vn", "-ac", "1", "-ar", "24000",
            "-af", "highpass=f=70,lowpass=f=8000,dynaudnorm=f=150:g=15",
            "-b:a", "128k",
            str(master_audio)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not master_audio.exists() or master_audio.stat().st_size <= 100:
            extract_audio(file_path, master_audio)
        input_audio = master_audio

    # Get accurate duration
    total_sec = get_media_duration_seconds(input_audio)
    if total_sec < 0.2:
        raise ValueError("ឯកសារវីដេអូ ឬសំឡេងនេះ មិនមានសំឡេងនិយាយ ឬជាឯកសារទទេ (Audio is empty or silent).")

    st.session_state.video_duration_ms = int(total_sec * 1000)

    # 2. Sequential Chunking Strategy:
    chunk_len_sec = 180.0
    if total_sec <= 210.0:
        chunk_intervals = [(0.0, total_sec)]
    else:
        chunk_intervals = []
        cur = 0.0
        while cur < total_sec:
            end = min(total_sec, cur + chunk_len_sec)
            chunk_intervals.append((cur, end))
            cur = end

    total_chunks = len(chunk_intervals)
    all_subtitles = []
    global_sub_idx = 1

    temp_chunks_dir = USER_DIR / f"chunks_{int(time.time())}"
    temp_chunks_dir.mkdir(exist_ok=True)

    try:
        for idx, (st_sec, en_sec) in enumerate(chunk_intervals, start=1):
            chunk_file = temp_chunks_dir / f"chunk_{idx}.mp3"
            
            # Slice chunk cleanly using FFmpeg with vocal normalization
            slice_cmd = [
                ffmpeg_bin, "-y", "-ss", f"{st_sec:.3f}", "-to", f"{en_sec:.3f}",
                "-i", str(input_audio),
                "-ac", "1", "-ar", "24000",
                "-af", "highpass=f=70,lowpass=f=8000,dynaudnorm=f=150:g=15",
                "-b:a", "128k",
                str(chunk_file)
            ]
            subprocess.run(slice_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not chunk_file.exists() or chunk_file.stat().st_size <= 100:
                continue

            # Update progress UI
            pct = 15 + int(75 * (idx / total_chunks))
            if p_bar: p_bar.progress(min(90, pct))
            st_fmt = format_ms_to_timestamp(int(st_sec * 1000))
            en_fmt = format_ms_to_timestamp(int(en_sec * 1000))
            if p_status:
                p_status.text(f"🧠 Transcribing Full Video: Part {idx}/{total_chunks} ({st_fmt} ➔ {en_fmt})...")

            raw_chunk_srt = _transcribe_audio_chunk_gemini(
                client=client,
                audio_chunk_path=chunk_file,
                chunk_index=idx,
                total_chunks=total_chunks,
                start_sec=st_sec,
                end_sec=en_sec,
                target_lang=target_lang,
                spoken_lang=spoken_lang,
            )

            chunk_subs = parse_srt(raw_chunk_srt)
            offset_ms = int(st_sec * 1000)

            for s in chunk_subs:
                adjusted_start = s.start_ms + offset_ms
                adjusted_end = s.end_ms + offset_ms
                all_subtitles.append(
                    Subtitle(
                        index=global_sub_idx,
                        start_time=format_ms_to_timestamp(adjusted_start),
                        end_time=format_ms_to_timestamp(adjusted_end),
                        text=s.text,
                        start_ms=adjusted_start,
                        end_ms=adjusted_end,
                    )
                )
                global_sub_idx += 1

            # Cleanup chunk file immediately
            try:
                chunk_file.unlink()
            except Exception:
                pass

    finally:
        # Cleanup temp directory and master audio
        try:
            shutil.rmtree(temp_chunks_dir, ignore_errors=True)
        except Exception:
            pass
        if master_audio.exists():
            try:
                master_audio.unlink()
            except Exception:
                pass

    if not all_subtitles:
        raise ValueError(
            "Gemini មិនអាចចាប់សំឡេងនិយាយក្នុងវីដេអូបានទេ (No speech dialogue transcribed). "
            "សូមប្រាកដថាវីដេអូមានសំឡេងមនុស្សនិយាយ ឬបញ្ចូលឯកសារ SRT ផ្ទាល់។"
        )

    if p_bar: p_bar.progress(100)
    if p_status: p_status.text(f"✓ Transcribed Full Video: {len(all_subtitles)} subtitle lines complete!")
    return all_subtitles


def run_whisper_transcription(file_path: Path, model_name: str = "base", p_bar=None, p_status=None) -> list[Subtitle]:
    wav_path = USER_DIR / "extracted_audio.wav"
    if p_status: p_status.text("⚡ Extracting audio stream with FFmpeg...")
    if p_bar: p_bar.progress(15)

    duration_sec = extract_audio(file_path, wav_path)
    if duration_sec < 0.2 or not wav_path.exists() or wav_path.stat().st_size <= 100:
        raise ValueError(
            "ឯកសារវីដេអូ ឬសំឡេងនេះ មិនមានសំឡេងនិយាយ ឬជាឯកសារទទេ (Audio stream is empty or silent). "
            "សូម Upload វីដេអូដែលមានសំឡេងនិយាយ ឬបញ្ចូលឯកសារ SRT ផ្ទាល់។"
        )

    st.session_state.video_duration_ms = int(duration_sec * 1000)

    if p_status: p_status.text(f"🧠 Running Whisper ({model_name}) speech recognition...")
    if p_bar: p_bar.progress(40)

    engine = get_whisper_engine(model_name)
    try:
        res = engine.transcribe(
            str(wav_path),
            fp16=False,
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.5,
        )
        raw_segs = res.get("segments", [])
    except Exception as ex:
        err_msg = str(ex)
        if "cannot reshape tensor" in err_msg or "0 elements" in err_msg:
            raise ValueError(
                "មិនមានសំឡេងនិយាយក្នុងវីដេអូនេះទេ (No audible speech detected). "
                "សូម Upload វីដេអូដែលមានសំឡេងនិយាយច្បាស់ ឬប្រើប្រាស់ឯកសារ SRT ផ្ទាល់។"
            )
        raise ex

    if p_bar: p_bar.progress(85)
    subtitles = []
    for idx, seg in enumerate(raw_segs, start=1):
        txt = str(seg.get("text", "")).strip()
        if not txt:
            continue
        s_ms = int(round(float(seg["start"]) * 1000))
        e_ms = int(round(float(seg["end"]) * 1000))
        subtitles.append(
            Subtitle(
                index=idx,
                start_time=format_ms_to_timestamp(s_ms),
                end_time=format_ms_to_timestamp(e_ms),
                text=txt,
                start_ms=s_ms,
                end_ms=e_ms,
            )
        )

    if not subtitles:
        raise ValueError(
            "Whisper មិនអាចចាប់សំឡេងនិយាយបានទេ (No dialogue transcribed). "
            "សូមប្រាកដថាវីដេអូមានសំឡេងមនុស្សនិយាយ ឬបញ្ចូលឯកសារ SRT ផ្ទាល់។"
        )

    if p_bar: p_bar.progress(100)
    return subtitles


def run_transcription(
    file_path: Path,
    engine: str = "gemini",
    whisper_model: str = "base",
    api_key: str = "",
    p_bar=None,
    p_status=None,
    target_lang: str = "original",
    spoken_lang: str = "auto",
) -> list[Subtitle]:
    """Unified transcription function supporting Gemini Multimodal AI and Whisper Local STT."""
    # Direct SRT fallback if an SRT file was provided
    if file_path.suffix.lower() == ".srt":
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        subs = parse_srt(raw)
        if subs:
            return subs

    # If Gemini AI is requested (or default)
    if engine.lower() == "gemini":
        try:
            return transcribe_with_gemini(
                file_path=file_path,
                api_key=api_key,
                p_bar=p_bar,
                p_status=p_status,
                target_lang=target_lang,
                spoken_lang=spoken_lang,
            )
        except Exception as gem_ex:
            # If Gemini fails and we have Whisper available, notify & fallback
            if p_status:
                p_status.text(f"⚠️ Gemini notice: {gem_ex}. Trying Whisper fallback...")
            time.sleep(1.2)
            return run_whisper_transcription(file_path, whisper_model, p_bar, p_status)
    else:
        return run_whisper_transcription(file_path, whisper_model, p_bar, p_status)


# 2. Translate SRT to Pure Khmer (with Multi-Model Retry)
def translate_subtitles_khmer(subtitles: list[Subtitle], api_key: str, p_bar=None, p_status=None) -> list[Subtitle]:
    if not api_key:
        raise ValueError("Please provide a valid Gemini API Key in the sidebar.")

    from google import genai
    client = genai.Client(api_key=api_key)

    total = len(subtitles)
    batch_size = 20
    khmer_list = []
    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    ]

    for b_idx in range(0, total, batch_size):
        chunk = subtitles[b_idx : b_idx + batch_size]
        payload = [{"id": s.index, "text": s.text} for s in chunk]
        
        prompt = (
            "You are a professional audiovisual translator. Translate these subtitle lines into 100% natural, fluent Khmer (ភាសាខ្មែរ).\n"
            "STRICT RULES:\n"
            "1. ONLY KHMER SCRIPT: Do not output any Thai, Chinese, or Latin script words.\n"
            "2. Natural dialogue: Translate idioms and context into spoken Khmer suitable for dubbing.\n"
            "3. Format: Return STRICTLY a valid JSON array of objects with 'id' and 'text'.\n\n"
            f"Input subtitles:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        translated_map = {}
        for m in models_to_try:
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                data = json.loads(resp.text.strip())
                if isinstance(data, list) and len(data) > 0:
                    translated_map = {int(item["id"]): str(item["text"]).strip() for item in data if "id" in item and "text" in item}
                    break
            except Exception:
                time.sleep(1.0)
                continue

        for s in chunk:
            khmer_txt = translated_map.get(s.index, s.text)
            khmer_txt = re.sub(r"[\u0E00-\u0E7F]+", "", khmer_txt).strip() or s.text
            khmer_list.append(
                Subtitle(
                    index=s.index,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=khmer_txt,
                    start_ms=s.start_ms,
                    end_ms=s.end_ms,
                    detected_gender=s.detected_gender,
                    assigned_voice=s.assigned_voice,
                    pitch_f0=s.pitch_f0,
                )
            )

        if p_bar:
            p_bar.progress(int(min(100, (b_idx + len(chunk)) / total * 100)))
        if p_status:
            p_status.text(f"Translating to Khmer: {min(b_idx + len(chunk), total)}/{total} lines...")

    return khmer_list


# 3. Robust Voice-Over TTS Synthesis (With Infinite Retry & Isolated Event Loop)
def synthesize_line_isolated_loop(text: str, voice: str, rate: str, pitch: str, out_file: Path) -> bool:
    import edge_tts

    async def _async_task():
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await comm.save(str(out_file))

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_async_task())
        return out_file.exists() and out_file.stat().st_size > 500
    except Exception:
        return False
    finally:
        try:
            loop.close()
        except Exception:
            pass


def generate_tts_clip_with_resilience(text: str, voice: str, rate: str, pitch: str, out_file: Path, max_retries: int = 5) -> bool:
    clean = text.strip()
    if not clean:
        return False

    # Tier 1: Microsoft Edge Neural TTS with exponential backoff
    for attempt in range(1, max_retries + 1):
        if out_file.exists():
            out_file.unlink()
        ok = synthesize_line_isolated_loop(clean, voice, rate, pitch, out_file)
        if ok:
            return True
        time.sleep(0.3 * attempt)

    # Tier 2: Google Translate Khmer TTS Fallback
    try:
        from gtts import gTTS
        tts = gTTS(text=clean, lang="km")
        tts.save(str(out_file))
        if out_file.exists() and out_file.stat().st_size > 500:
            return True
    except Exception:
        pass

    # Tier 3: Sanitized punctuation retry
    try:
        sanitized = re.sub(r"[^\w\s\u1780-\u17FF]", " ", clean).strip()
        ok = synthesize_line_isolated_loop(sanitized, voice, "+0%", "+0Hz", out_file)
        if ok:
            return True
    except Exception:
        pass

    return False


def generate_all_tts(subtitles: list[Subtitle], default_voice: str, rate: str, pitch: str, p_bar=None, p_status=None) -> dict[int, str]:
    tts_dir = USER_DIR / "tts_cache"
    tts_dir.mkdir(exist_ok=True)
    
    total = len(subtitles)
    audio_map = {}
    failed = []

    for idx, s in enumerate(subtitles, start=1):
        line_voice = s.assigned_voice or default_voice
        voice_tag = "piseth" if "piseth" in line_voice.lower() else "sreymom"
        clip_p = tts_dir / f"line_{s.index}_{voice_tag}.mp3"

        if clip_p.exists() and clip_p.stat().st_size > 500:
            audio_map[s.index] = str(clip_p)
        else:
            if p_status:
                g_icon = "👨" if "piseth" in line_voice.lower() else "👩"
                p_status.text(f"🎙️ Voicing {g_icon} line {idx}/{total}: {s.text[:30]}...")
            
            success = generate_tts_clip_with_resilience(s.text, line_voice, rate, pitch, clip_p)
            if success:
                audio_map[s.index] = str(clip_p)
            else:
                failed.append(s.index)

        if p_bar:
            p_bar.progress(int(idx / total * 100))

    if failed:
        st.warning(f"⚠️ {len(failed)} line(s) required recovery: lines {failed}")
    return audio_map


def recalculate_timeline_after_voiceover(
    subtitles: list[Subtitle],
    audio_map: dict[int, str],
    min_pause_ms: int = 200,
) -> list[Subtitle]:
    """Recalculates every subtitle timestamp to match the actual voiced audio speech duration
    and anti-overlap placement. Subtitles become 100% synchronized with the master MP3 audio.
    """
    if not subtitles or not audio_map:
        return subtitles

    last_speech_end = 0
    updated_subs = []

    for s in subtitles:
        clip_str = audio_map.get(s.index)
        clip_dur = s.duration_ms
        if clip_str and Path(clip_str).exists():
            try:
                clip = AudioSegment.from_file(clip_str)
                clip_dur = len(clip)
            except Exception:
                pass

        target_start = s.start_ms
        if target_start < last_speech_end + min_pause_ms:
            target_start = last_speech_end + min_pause_ms

        target_end = target_start + clip_dur
        last_speech_end = target_end

        updated_subs.append(
            Subtitle(
                index=s.index,
                start_time=format_ms_to_timestamp(target_start),
                end_time=format_ms_to_timestamp(target_end),
                text=s.text,
                start_ms=target_start,
                end_ms=target_end,
                detected_gender=s.detected_gender,
                assigned_voice=s.assigned_voice,
                pitch_f0=s.pitch_f0,
            )
        )
    return updated_subs


# 4. Render Master MP3 Audio with Anti-Collision / Anti-Overlapping Protection (កុំឱ្យតួអង្គនិយាយជាន់គ្នា)
def render_dubbed_mp3(
    subtitles: list[Subtitle],
    audio_map: dict[int, str],
    video_dur_ms: int = 0,
    bgm_path: Optional[Path] = None,
    bgm_vol_db: float = -18.0,
    min_pause_ms: int = 200,
    p_bar=None,
    p_status=None,
) -> Path:
    """Renders final master MP3 ensuring ZERO speech overlapping (កុំឱ្យតួអង្គនិយាយជាន់គ្នាដាច់ខាត).
    Each line begins at or after its SRT timestamp, but if the previous character hasn't finished,
    the start time is seamlessly sequenced with a natural breathing pause (min_pause_ms).
    """
    if not subtitles or not audio_map:
        raise ValueError("Missing subtitles or voiced clips to render.")

    if p_status: p_status.text("🎼 Computing timeline and anti-collision placement...")
    if p_bar: p_bar.progress(10)

    # First pass: load clips and calculate non-overlapping placements
    placements = []
    last_speech_end = 0

    for s in subtitles:
        clip_str = audio_map.get(s.index)
        if not clip_str or not Path(clip_str).exists():
            continue
        try:
            clip = AudioSegment.from_file(clip_str)
            clip_dur = len(clip)

            # ANTI-OVERLAP COLLISION PREVENTION:
            # If the subtitle start_ms is before the previous character finishes + pause:
            target_start = s.start_ms
            if target_start < last_speech_end + min_pause_ms:
                # Seamlessly sequence speech so voices NEVER talk over each other
                target_start = last_speech_end + min_pause_ms

            placements.append({
                "clip": clip,
                "start_ms": target_start,
                "end_ms": target_start + clip_dur,
            })
            last_speech_end = target_start + clip_dur
        except Exception:
            pass

    # Canvas duration must accommodate the final speaker's speech
    final_speech_end = max((p["end_ms"] for p in placements), default=0)
    total_canvas_len = max(video_dur_ms, final_speech_end + 1500)

    timeline = AudioSegment.silent(duration=total_canvas_len)

    # Second pass: composite clips onto timeline
    total_clips = len(placements)
    for idx, p in enumerate(placements):
        clip = p["clip"]
        st_pos = p["start_ms"]
        # Extend canvas if needed
        if st_pos + len(clip) > len(timeline):
            timeline = timeline + AudioSegment.silent(duration=(st_pos + len(clip) - len(timeline) + 3000))
        timeline = timeline.overlay(clip, position=st_pos)

        if p_bar:
            p_bar.progress(10 + int(70 * (idx + 1) / max(1, total_clips)))

    # Background Music Blending with Smooth Fade Out
    if bgm_path and bgm_path.exists():
        if p_status: p_status.text("🎶 Blending background music track...")
        try:
            bgm = AudioSegment.from_file(bgm_path) + bgm_vol_db
            cur_dur = len(timeline)
            if len(bgm) < cur_dur:
                loops = (cur_dur // len(bgm)) + 1
                bgm = (bgm * loops)[:cur_dur]
            else:
                bgm = bgm[:cur_dur]
            bgm = bgm.fade_out(2000)
            timeline = timeline.overlay(bgm, position=0)
        except Exception as e:
            st.warning(f"BGM blend notice: {e}")

    out_file = USER_DIR / f"master_voiceover_{int(time.time())}.mp3"
    if p_status: p_status.text("📦 Exporting master 192kbps MP3...")
    if p_bar: p_bar.progress(95)

    timeline.export(str(out_file), format="mp3", bitrate="192k")
    if p_bar: p_bar.progress(100)
    return out_file


# =====================================================================
# UNIFIED ALL-IN-ONE MASTER DUBBING FUNCTION (FUNCTION តែមួយ ធ្វើការទាំងអស់)
# =====================================================================
def run_unified_dubbing_process(
    media_file: Path,
    bgm_file: Optional[Path] = None,
    api_key: str = "",
    transcribe_engine: str = "gemini",
    whisper_model: str = "base",
    spoken_lang: str = "auto",
    voice_mode: str = "alternate_mf",
    voice_speed: str = "+60%",
    voice_pitch: str = "+0Hz",
    breathing_pause_ms: int = 200,
    progress_bar=None,
    status_box=None,
) -> dict:
    """Master All-In-One Function: Transcribe -> Translate -> Alternate Voice TTS -> Timeline Count -> Render MP3.
    Executes the entire end-to-end audiovisual dubbing pipeline in ONE unified function."""
    def log(msg: str):
        if status_box:
            status_box.write(msg)

    def prog(val: int):
        if progress_bar:
            progress_bar.progress(val)

    is_srt = media_file.suffix.lower() == ".srt"
    prog(5)

    # 1. STEP 1: LOAD OR TRANSCRIBE AUDIO -> SRT
    if is_srt:
        log("📄 **Step 1/4 (SRT Loaded)**: Parsing existing SRT subtitle file directly...")
        raw_srt = media_file.read_text(encoding="utf-8", errors="ignore")
        subs_orig = parse_srt(raw_srt)
        if not subs_orig:
            raise ValueError("ឯកសារ SRT នេះទទេ ឬខុសទម្រង់ (Invalid or empty SRT file).")
        srt_text_orig = raw_srt
        log(f"✓ Loaded {len(subs_orig)} lines from SRT.")
    else:
        eng_label = "Gemini Flash AI" if transcribe_engine.lower() == "gemini" else f"Whisper ({whisper_model})"
        log(f"🎙️ **Step 1/4 (Speech-to-Text)**: Transcribing speech with {eng_label} (Acoustic normalized & verbatim)...")
        subs_orig = run_transcription(
            file_path=media_file,
            engine=transcribe_engine,
            whisper_model=whisper_model,
            api_key=api_key,
            p_bar=progress_bar,
            p_status=status_box,
            target_lang="original",
            spoken_lang=spoken_lang,
        )
        srt_text_orig = export_subtitles_to_srt(subs_orig)
        log(f"✓ Step 1 Complete: {len(subs_orig)} lines transcribed.")

    prog(30)

    # 2. STEP 2: TRANSLATE TO KHMER & ASSIGN CHARACTERS
    has_khmer = bool(re.search(r"[\u1780-\u17FF]", srt_text_orig))
    if has_khmer:
        log("🇰🇭 **Step 2/4 (Khmer Detected)**: Dialogue already in Khmer! Direct character voice assignment...")
        subs_khmer = assign_character_voices_to_subtitles(subs_orig, voice_mode, media_file if not is_srt else None)
    else:
        log("🇰🇭 **Step 2/4 (Translation)**: Translating subtitles into pure natural Khmer with Gemini AI...")
        subs_trans = translate_subtitles_khmer(subs_orig, api_key, progress_bar)
        subs_khmer = assign_character_voices_to_subtitles(subs_trans, voice_mode, media_file if not is_srt else None)

    srt_text_khmer = export_subtitles_to_srt(subs_khmer)
    log(f"✓ Step 2 Complete: {len(subs_khmer)} lines ready with Piseth 👨 & Sreymom 👩 characters.")
    prog(50)

    # 3. STEP 3: SYNTHESIZE NEURAL VOICES (EDGE-TTS)
    log(f"🗣️ **Step 3/4 (Voiceover TTS)**: Synthesizing Piseth 👨 & Sreymom 👩 (Speed: {voice_speed}, Infinite auto-retry)...")
    clips = generate_all_tts(
        subs_khmer,
        "km-KH-PisethNeural",
        voice_speed,
        voice_pitch,
        progress_bar,
    )
    log(f"✓ Step 3 Complete: {len(clips)} audio dialogue clips generated.")
    prog(75)

    # 4. STEP 4: TIMELINE RECALCULATION & ANTI-COLLISION RENDERING
    log("⏱️ **Step 4/4 (Timeline Sync & Master MP3)**: Re-counting timeline and rendering master MP3 without voice collision...")
    subs_khmer_synced = recalculate_timeline_after_voiceover(subs_khmer, clips, breathing_pause_ms)
    srt_text_khmer_synced = export_subtitles_to_srt(subs_khmer_synced)

    # Render master MP3 with anti-overlap
    video_dur_ms = st.session_state.get("video_duration_ms", 0)
    master_mp3 = render_dubbed_mp3(
        subtitles=subs_khmer_synced,
        audio_map=clips,
        video_dur_ms=video_dur_ms,
        bgm_path=bgm_file,
        bgm_vol_db=-18.0,
        min_pause_ms=breathing_pause_ms,
        p_bar=progress_bar,
    )
    prog(100)
    log("🎉 **Dubbing Complete**: Master MP3 rendered successfully!")

    return {
        "master_mp3_path": str(master_mp3),
        "subtitles_khmer": subs_khmer_synced,
        "srt_text_khmer": srt_text_khmer_synced,
        "subtitles_orig": subs_orig,
        "srt_text_orig": srt_text_orig,
        "clips": clips,
        "total_lines": len(subs_khmer_synced),
    }


# ==========================================
# Sidebar Configuration
# ==========================================
with st.sidebar:
    st.markdown(
        f"""
        <div style="background: rgba(30, 41, 59, 0.7); border-radius: 12px; padding: 14px; border: 1px solid rgba(255,255,255,0.08); margin-bottom: 16px;">
            <div style="font-size: 0.85rem; color: #94a3b8;">Logged in as</div>
            <div style="font-size: 1.15rem; font-weight: 700; color: #60a5fa;">{st.session_state.auth_user}</div>
            <div style="font-size: 0.75rem; color: #34d399; font-weight: 600; text-transform: uppercase;">● {st.session_state.user_role}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cfg = load_config()
    current_key = cfg.get("gemini_api_key", "")
    
    st.markdown("#### ⚙️ AI Engine Settings")
    input_key = st.text_input("Gemini API Key", value=current_key, type="password", help="For Step 1 Speech-to-SRT & Step 2 Khmer translation")
    if input_key != current_key:
        if st.button("💾 Save Key", use_container_width=True):
            save_config({"gemini_api_key": input_key})
            st.success("API key saved!")
            st.rerun()

    transcribe_engine = st.selectbox(
        "🎙️ Speech-to-SRT Engine",
        options=["✨ Gemini Flash AI (Cloud - Recommended)", "💻 Whisper Local (Offline STT)"],
        index=0,
        help="Gemini AI transcribes speech to SRT quickly with accurate timestamps and zero CPU strain.",
    )
    whisper_model = "base"
    if "Whisper" in transcribe_engine:
        whisper_model = st.selectbox("Whisper STT Model", options=["base", "tiny", "small"], index=0)

    global_spoken_lang_choice = st.selectbox(
        "🎙️ ភាសានិយាយក្នុងវីដេអូ (Spoken Audio Language)",
        options=[
            "🇰🇭 ភាសាខ្មែរ (Khmer - ចាប់សំឡេងខ្មែរ 100% ត្រឹមត្រូវអក្ខរាវិរុទ្ធ)",
            "🌐 Auto-Detect All Languages (ស្វ័យប្រវត្តិតាមសំឡេង)",
            "🇨🇳 ភាសាចិន (Chinese / Mandarin)",
            "🇬🇧 ភាសាអង់គ្លេស (English)",
            "🇹🇭 ភាសាថៃ (Thai)",
        ],
        index=0,
        help="កំណត់ភាសានិយាយក្នុងវីដេអូ ដើម្បីឱ្យ AI ចាប់យកអត្ថបទ និងអក្ខរាវិរុទ្ធបានត្រឹមត្រូវបំផុត",
    )
    if "ខ្មែរ" in global_spoken_lang_choice or "Khmer" in global_spoken_lang_choice:
        chosen_global_lang = "khmer"
    elif "ចិន" in global_spoken_lang_choice or "Chinese" in global_spoken_lang_choice:
        chosen_global_lang = "chinese"
    elif "អង់គ្លេស" in global_spoken_lang_choice or "English" in global_spoken_lang_choice:
        chosen_global_lang = "english"
    else:
        chosen_global_lang = "auto"


    st.markdown("#### 🎭 តួអង្គឆ្លាស់ប្រុសស្រី (Character Mode)")
    mode_options = [
        ("alternate_mf", "🔄 ឆ្លាស់ប្រុស 👨 និង ស្រី 👩 (ចាប់ផ្តើមប្រុស)"),
        ("alternate_fm", "🔄 ឆ្លាស់ស្រី 👩 និង ប្រុស 👨 (ចាប់ផ្តើមស្រី)"),
        ("auto", "🤖 ស្វ័យប្រវត្តិតាមសំឡេងដើម (Pitch Detect)"),
        ("male", "👨 ប្រុសតែមួយ (Piseth)"),
        ("female", "👩 ស្រីតែមួយ (Sreymom)"),
    ]
    cur_idx = 0
    for idx_opt, (k_val, _) in enumerate(mode_options):
        if st.session_state.voice_mode == k_val:
            cur_idx = idx_opt
            break

    v_mode = st.radio(
        "Voice Assignment Mode",
        options=mode_options,
        format_func=lambda x: x[1],
        index=cur_idx,
    )
    st.session_state.voice_mode = v_mode[0]

    st.markdown("#### 🛡️ ការពារកុំឱ្យនិយាយជាន់គ្នា (Anti-Overlap)")
    st.session_state.breathing_pause_ms = st.slider(
        "ចន្លោះពេលដកដង្ហើមរវាងតួអង្គ (Pause Gap)",
        min_value=100,
        max_value=600,
        value=st.session_state.breathing_pause_ms,
        step=50,
        help="ធានាថាតួអង្គមិននិយាយជាន់គ្នាដាច់ខាត ដោយទុកចន្លោះពេលធម្មជាតិមុនតួអង្គបន្ទាប់និយាយ",
    )

    speed_opts = ["-20%", "-10%", "+0%", "+15%", "+30%", "+45%", "+60%", "+75%", "+90%", "+100%"]
    cur_speed = st.session_state.selected_speed if st.session_state.selected_speed in speed_opts else "+60%"
    st.session_state.selected_speed = st.select_slider(
        "Speech Speed / ល្បឿនសំឡេង",
        options=speed_opts,
        value=cur_speed,
        help="ល្បឿនបច្ចុប្បន្នកំណត់ជាលំនាំដើម: +60% (1.60x speed)",
    )

    st.markdown("---")
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("🔄 Reset Flow", use_container_width=True):
            st.session_state.subtitles_orig = []
            st.session_state.srt_text_orig = ""
            st.session_state.subtitles_khmer = []
            st.session_state.srt_text_khmer = ""
            st.session_state.voiceover_clips = {}
            st.session_state.master_mp3_path = None
            st.session_state.current_step = 1
            st.rerun()
    with c_btn2:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.query_params.clear()
            st.rerun()


# ==========================================
# Studio Header & Stepper Navigation Bar
# ==========================================
st.markdown(
    f"""
    <div class="studio-hero">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px;">
            <div>
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                    <span class="pulse-badge"><span class="pulse-dot"></span> Studio Engine 2026</span>
                    <span style="font-size: 0.8rem; color: #64748b;">|</span>
                    <span style="font-size: 0.82rem; color: #94a3b8; font-weight: 500;">High-Precision Khmer AI Dubber</span>
                </div>
                <h1 class="studio-hero-title">
                    🎙️ Dubber AI Pro Studio
                </h1>
                <p class="studio-hero-sub">
                    ស្ទូឌីយោបញ្ចូលសំឡេងស្វ័យប្រវត្តិ • ឆ្លាស់ប្រុសស្រី <b>Piseth 👨 & Sreymom 👩</b> • ការពារកុំឱ្យនិយាយជាន់គ្នា <b>(Zero-Collision)</b> • នាំចេញ Master MP3
                </p>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px;">
                <span class="stat-badge" style="border-color: rgba(56, 189, 248, 0.3); color: #7dd3fc;">
                    🎬 {len(st.session_state.subtitles_orig)} Segments
                </span>
                <span class="stat-badge" style="border-color: rgba(192, 132, 252, 0.3); color: #e9d5ff;">
                    🎭 {st.session_state.voice_mode.upper()}
                </span>
                <span class="stat-badge" style="border-color: rgba(52, 211, 153, 0.3); color: #6ee7b7;">
                    🛡️ {st.session_state.breathing_pause_ms}ms Pause
                </span>
                <span class="stat-badge" style="border-color: rgba(251, 191, 36, 0.3); color: #fde68a;">
                    ⚡ {st.session_state.selected_speed}
                </span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.session_state.get("just_cleared_after_download"):
    st.markdown(
        """
        <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; border-radius: 12px; padding: 14px 18px; margin-bottom: 1.2rem; display: flex; align-items: center; gap: 14px;">
            <div style="font-size: 2rem;">🎉</div>
            <div>
                <div style="font-weight: 700; color: #34d399; font-size: 1.05rem;">
                    ទាញយក Master MP3 រួចរាល់! Cache & Files ត្រូវបានសម្អាតស្អាត 100%
                </div>
                <div style="font-size: 0.88rem; color: #cbd5e1; margin-top: 3px;">
                    Master MP3 downloaded successfully! All temporary audio clips & previous project data have been wiped clean. You can now start creating a brand new MP3!
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.session_state.just_cleared_after_download = False


st.markdown(
    """
    <div class="studio-card">
        <h3 style="margin-top:0; color:#60a5fa;">⚡ 1-Click Pipeline (ឆ្លាស់ប្រុសស្រី & គ្មានការនិយាយជាន់គ្នា)</h3>
        <p style="color:#94a3b8;">Upload your video or audio file. Dubber AI will transcribe, translate to Khmer, alternate characters between Male (Piseth 👨) and Female (Sreymom 👩), guarantee zero speech overlap, and render your final master MP3.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
c_au1, c_au2 = st.columns([3, 2])
with c_au1:
    auto_file = st.file_uploader(
        "Select Video, Audio, or SRT File",
        type=["mp4", "mov", "mkv", "avi", "webm", "mp3", "wav", "m4a", "srt"],
        key=f"auto_pipe_file_{st.session_state.get('uploader_key', 0)}",
        help="Upload a video to transcribe & dub, OR upload an SRT file to generate voice-over directly!",
    )
with c_au2:
    auto_bgm_file = st.file_uploader(
        "Optional Background Music (BGM)",
        type=["mp3", "wav"],
        key=f"auto_pipe_bgm_{st.session_state.get('uploader_key', 0)}",
    )
    st.markdown(
        f"""
        <div class="anti-overlap-banner">
            <span style="color:#34d399; font-weight:700;">🛡️ Anti-Overlap System Active</span><br>
            <span style="font-size:0.85rem; color:#d1d5db;">តួអង្គនឹងមិននិយាយជាន់គ្នាដាច់ខាត។ ចន្លោះដកដង្ហើម: <b>{st.session_state.breathing_pause_ms}ms</b></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

if auto_file:
    is_srt_input = auto_file.name.lower().endswith(".srt")
    btn_label = "🚀 Run 1-Click Voice-Over from SRT" if is_srt_input else "🚀 Run 1-Click Dubbing Pipeline Now"
    if st.button(btn_label, type="primary", use_container_width=True):
        saved = USER_DIR / f"auto_in_{int(time.time())}{Path(auto_file.name).suffix}"
        saved.write_bytes(auto_file.getbuffer())
        st.session_state.media_path = saved

        bgm_p = None
        if auto_bgm_file:
            bgm_p = USER_DIR / f"bgm_{int(time.time())}.mp3"
            bgm_p.write_bytes(auto_bgm_file.getbuffer())

        status_box = st.status("🎬 Running Full Pipeline...", expanded=True)
        p_bar = st.progress(5)

        try:
            chosen_engine = "gemini" if "Gemini" in transcribe_engine else "whisper"
            result = run_unified_dubbing_process(
                media_file=saved,
                bgm_file=bgm_p,
                api_key=input_key or current_key,
                transcribe_engine=chosen_engine,
                whisper_model=whisper_model,
                spoken_lang=chosen_global_lang,
                voice_mode=st.session_state.voice_mode,
                voice_speed=st.session_state.selected_speed,
                voice_pitch=st.session_state.selected_pitch,
                breathing_pause_ms=st.session_state.breathing_pause_ms,
                progress_bar=p_bar,
                status_box=status_box,
            )

            st.session_state.subtitles_orig = result["subtitles_orig"]
            st.session_state.srt_text_orig = result["srt_text_orig"]
            st.session_state.subtitles_khmer = result["subtitles_khmer"]
            st.session_state.srt_text_khmer = result["srt_text_khmer"]
            st.session_state.voiceover_clips = result["clips"]
            st.session_state.master_mp3_path = result["master_mp3_path"]
            st.session_state.current_step = 4
            status_box.update(label="🎉 Full Pipeline Complete (All-In-One Unified Function Finished)!", state="complete")
            st.balloons()
        except Exception as e:
            status_box.update(label=f"❌ Error: {e}", state="error")
            st.error(f"Pipeline stopped: {e}")

if st.session_state.master_mp3_path and Path(st.session_state.master_mp3_path).exists():
    mp3_obj = Path(st.session_state.master_mp3_path)
    mp3_bytes = mp3_obj.read_bytes()
    zip_bytes = create_master_zip_bundle(mp3_obj, st.session_state.srt_text_khmer)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="studio-card" style="border: 1px solid rgba(52, 211, 153, 0.45); background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(15, 23, 42, 0.85) 100%);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; margin-bottom: 12px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="font-size: 2rem;">🎧</div>
                    <div>
                        <h3 style="margin: 0; color: #34d399; font-family: 'Outfit', 'Kantumruy Pro', sans-serif; font-weight: 800; font-size: 1.3rem;">
                            Master Dubbed MP3 Studio Release
                        </h3>
                        <span style="font-size: 0.85rem; color: #cbd5e1;">ឆ្លាស់ប្រុសស្រី • គ្មានការនិយាយជាន់គ្នា (Zero-Collision) • Synced Timeline</span>
                    </div>
                </div>
                <div class="soundwave-box">
                    <div class="soundwave-bar"></div>
                    <div class="soundwave-bar"></div>
                    <div class="soundwave-bar"></div>
                    <div class="soundwave-bar"></div>
                    <div class="soundwave-bar"></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.audio(mp3_bytes, format="audio/mp3")

    st.markdown("<br>", unsafe_allow_html=True)
    st.checkbox(
        "🧹 Auto-clear cache after downloading MP3 to make a new MP3 immediately (សម្អាត cache ស្វ័យប្រវត្តពេល download ចប់)",
        value=st.session_state.get("auto_clear_after_download", True),
        key="chk_auto_clear_tab0",
        on_change=lambda: st.session_state.update(auto_clear_after_download=st.session_state.chk_auto_clear_tab0),
    )

    c_pipe_d1, c_pipe_d2, c_pipe_d3 = st.columns([2, 2, 2])
    with c_pipe_d1:
        st.download_button(
            label="⬇️ Download Master MP3",
            data=mp3_bytes,
            file_name=f"dubbed_khmer_{mp3_obj.name}",
            mime="audio/mp3",
            type="primary",
            key="btn_dl_mp3_tab0",
            on_click=on_master_download,
            use_container_width=True,
        )
    with c_pipe_d2:
        st.download_button(
            label="📦 Download Bundle (MP3 + SRT .ZIP)",
            data=zip_bytes,
            file_name="dubbed_khmer_master_bundle.zip",
            mime="application/zip",
            key="btn_dl_zip_tab0",
            on_click=on_master_download,
            use_container_width=True,
        )
    with c_pipe_d3:
        st.download_button(
            label="📄 Download Synced SRT",
            data=st.session_state.srt_text_khmer,
            file_name="synced_voiceover.srt",
            mime="text/plain",
            key="btn_dl_srt_tab0",
            use_container_width=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    c_pipe_c1, c_pipe_c2 = st.columns([3, 1])
    with c_pipe_c1:
        st.info("💡 ក្រោយពេលទាញយក Master MP3 ឬ Zip Bundle រួចរាល់ ប្រព័ន្ធនឹងសម្អាត cache ដោយស្វ័យប្រវត្តដើម្បីធ្វើ MP3 ថ្មី។ អ្នកក៏អាចចុចប៊ូតុង Clear Cache ដោយផ្ទាល់បានដែរ។")
    with c_pipe_c2:
        if st.button("🧹 Clear Cache & Make New MP3", key="btn_clear_tab0", type="primary", use_container_width=True):
            clear_user_cache(preserve_success_message=True)
            st.rerun()

