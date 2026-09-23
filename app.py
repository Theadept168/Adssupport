import asyncio
import concurrent.futures
import io
import json
import os
import re
import secrets
import subprocess
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
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
    initial_sidebar_state="auto",
)

CONFIG_PATH = Path(".dubber_config.json")
STORAGE_DIR = Path(".dubber_input")
STORAGE_DIR.mkdir(exist_ok=True)

FFMPEG_PATH = Path(__file__).with_name("ffmpeg.exe")
FFMPEG_BIN = str(FFMPEG_PATH.resolve()) if FFMPEG_PATH.exists() else "ffmpeg"
AudioSegment.converter = FFMPEG_BIN
AudioSegment.ffmpeg = FFMPEG_BIN


def load_saved_config() -> dict:
    config = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
    if "auth_users" not in config:
        config["auth_users"] = {"admin": {"password": "dubber123", "role": "admin", "status": "approved"}}
    if "pending_users" not in config:
        config["pending_users"] = {}
    if "device_tokens" not in config:
        config["device_tokens"] = {}
    try:
        if hasattr(st, "secrets") and st.secrets:
            if "GEMINI_API_KEY" in st.secrets:
                config.setdefault("gemini_api_key", st.secrets["GEMINI_API_KEY"])
            if "OPENAI_API_KEY" in st.secrets:
                config.setdefault("openai_api_key", st.secrets["OPENAI_API_KEY"])
            if "ELEVENLABS_API_KEY" in st.secrets:
                config.setdefault("elevenlabs_api_key", st.secrets["ELEVENLABS_API_KEY"])
            if "DUBBER_USER" in st.secrets and "DUBBER_PASSWORD" in st.secrets:
                config["auth_users"][st.secrets["DUBBER_USER"]] = {
                    "password": st.secrets["DUBBER_PASSWORD"],
                    "role": "admin",
                    "status": "approved",
                }
    except Exception:
        pass
    return config


def get_user_password(user_val) -> str:
    if isinstance(user_val, dict):
        return str(user_val.get("password", ""))
    return str(user_val)


def save_saved_config(updates: dict) -> None:
    current = load_saved_config()
    current.update(updates)
    try:
        CONFIG_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def get_client_device_info() -> dict:
    headers = getattr(st.context, "headers", {}) or {}
    ip = getattr(st.context, "ip_address", "") or headers.get("x-forwarded-for", "") or "Local Device"
    ua = headers.get("user-agent", "")
    
    device = "Desktop PC"
    if "iPhone" in ua:
        device = "iPhone (iOS)"
    elif "iPad" in ua:
        device = "iPad (iPadOS)"
    elif "Android" in ua:
        device = "Android Phone"
    elif "Windows" in ua or "Win64" in ua or "Win32" in ua:
        device = "Windows PC"
    elif "Macintosh" in ua or "Mac OS" in ua:
        device = "Mac"
    elif "Linux" in ua:
        device = "Linux"

    browser = "Browser"
    if "Edg" in ua:
        browser = "Edge"
    elif "Chrome" in ua and "Edg" not in ua:
        browser = "Chrome"
    elif "Safari" in ua and "Chrome" not in ua:
        browser = "Safari"
    elif "Firefox" in ua:
        browser = "Firefox"
        
    device_name = f"{device} • {browser}"
    return {
        "device_name": device_name,
        "ip": str(ip),
        "login_time": time.strftime("%Y-%m-%d %H:%M"),
    }


saved_config = load_saved_config()

# Predefined Edge TTS Neural voices
EDGE_VOICES = {
    "🎭 Auto-Detect (Piseth / Sreymom)": "auto_detect",
    "Khmer - Male (Piseth Neural)": "km-KH-PisethNeural",
    "Khmer - Female (Sreymom Neural)": "km-KH-SreymomNeural",
    "English (US) - Female (Jenny Neural)": "en-US-JennyNeural",
    "English (US) - Male (Guy Neural)": "en-US-GuyNeural",
    "Thai - Female (Premwadee Neural)": "th-TH-PremwadeeNeural",
    "Thai - Male (Niwat Neural)": "th-TH-NiwatNeural",
    "Vietnamese - Female (HoaiMy Neural)": "vi-VN-HoaiMyNeural",
    "Vietnamese - Male (NamMinh Neural)": "vi-VN-NamMinhNeural",
    "Chinese - Female (Xiaoxiao Neural)": "zh-CN-XiaoxiaoNeural",
    "Japanese - Female (Nanami Neural)": "ja-JP-NanamiNeural",
    "French - Female (Denise Neural)": "fr-FR-DeniseNeural",
}

VOICE_BUTTON_OPTIONS = [
    "🎭 Auto (Piseth 👨 / Sreymom 👩)",
    "👨 Piseth (ប្រុស / Boy)",
    "👩 Sreymom (ស្រី / Girl)",
]
VOICE_BUTTON_MAP = {
    "🎭 Auto (Piseth 👨 / Sreymom 👩)": "auto_detect",
    "👨 Piseth (ប្រុស / Boy)": "km-KH-PisethNeural",
    "👩 Sreymom (ស្រី / Girl)": "km-KH-SreymomNeural",
}


def estimate_pitch_f0(samples: np.ndarray, sample_rate: int = 16000) -> float:
    if len(samples) == 0:
        return 140.0
    frame_len = int(sample_rate * 0.05)  # 50ms window = 800 samples
    hop_len = int(sample_rate * 0.025)   # 25ms step = 400 samples
    min_lag = int(sample_rate / 350)     # ~350 Hz max human speech F0 (~45 samples)
    max_lag = int(sample_rate / 75)      # ~75 Hz min human speech F0 (~213 samples)
    pitches = []

    # Adaptive energy threshold to detect voiced frames even on quiet speech
    mean_energy = float(np.mean(samples**2)) if len(samples) > 0 else 0.0
    energy_thresh = max(25.0, mean_energy * 0.08)

    max_samples = min(len(samples) - frame_len, sample_rate * 45)
    if max_samples <= 0:
        return 140.0

    for i in range(0, max_samples, hop_len):
        frame = samples[i:i + frame_len]
        energy = np.mean(frame**2)
        if energy < energy_thresh:
            continue
        frame_norm = frame - np.mean(frame)
        corr = np.correlate(frame_norm, frame_norm, mode='full')
        corr = corr[len(frame) - 1:]
        if len(corr) > max_lag:
            peak_lag = min_lag + int(np.argmax(corr[min_lag:max_lag]))
            peak_val = corr[peak_lag]
            zero_lag = corr[0]
            if zero_lag > 0 and (peak_val / zero_lag) > 0.22:  # Voiced frame threshold
                f0 = sample_rate / peak_lag
                if 75 <= f0 <= 350:
                    pitches.append(f0)
    return float(np.median(pitches)) if pitches else 140.0


def detect_voice_piseth_sreymom(media_path: str = None, audio_segment: AudioSegment = None) -> dict:
    try:
        if audio_segment is None:
            if not media_path or not Path(media_path).exists():
                return {
                    "voice": "km-KH-PisethNeural",
                    "gender": "Male",
                    "name": "Piseth Neural (Male)",
                    "pitch": 130.0,
                    "icon": "👨",
                }
            audio_segment = AudioSegment.from_file(media_path)
            # For whole media file, inspect first 60 seconds
            inspect_clip = audio_segment[:60000]
        else:
            inspect_clip = audio_segment

        # Normalize to 16kHz mono for pitch estimation
        audio_16k = inspect_clip.set_channels(1).set_frame_rate(16000)
        samples = np.array(audio_16k.get_array_of_samples(), dtype=np.float32)
        f0 = estimate_pitch_f0(samples, 16000)

        # Male fundamental frequency typically 85-155 Hz, Female 165-255 Hz
        if f0 < 165.0:
            return {
                "voice": "km-KH-PisethNeural",
                "gender": "Male",
                "name": "Piseth Neural (Male)",
                "pitch": round(f0, 1),
                "icon": "👨",
            }
        else:
            return {
                "voice": "km-KH-SreymomNeural",
                "gender": "Female",
                "name": "Sreymom Neural (Female)",
                "pitch": round(f0, 1),
                "icon": "👩",
            }
    except Exception:
        return {
            "voice": "km-KH-PisethNeural",
            "gender": "Male",
            "name": "Piseth Neural (Male)",
            "pitch": 130.0,
            "icon": "👨",
        }


# ==========================================
# Subtitle Data Model & Parsing Functions
# ==========================================
@dataclass
class Subtitle:
    index: int
    start: int  # milliseconds
    end: int    # milliseconds
    text: str
    voice: str = ""  # Specific voice override for multi-speaker dubbing


TIME_RE = re.compile(
    r"(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})[,\.](?P<millis>\d{3})"
)


def parse_timestamp(value: str) -> int:
    match = TIME_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: '{value}'")
    parts = {key: int(number) for key, number in match.groupdict().items()}
    return ((parts["hours"] * 60 + parts["minutes"]) * 60 + parts["seconds"]) * 1000 + parts["millis"]


def format_timestamp(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_srt(content: str) -> list[Subtitle]:
    subtitles = []
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        time_line_idx = 1 if "-->" in lines[1] else (0 if "-->" in lines[0] else -1)
        if time_line_idx == -1:
            continue
        start_value, end_value = [part.strip() for part in lines[time_line_idx].split("-->", 1)]
        raw_text = "\n".join(lines[time_line_idx + 1:]).strip()
        idx = int(lines[0].strip()) if time_line_idx == 1 and lines[0].strip().isdigit() else len(subtitles) + 1
        subtitles.append(Subtitle(idx, parse_timestamp(start_value), parse_timestamp(end_value), raw_text))
    if not subtitles:
        raise ValueError("No valid subtitle blocks were detected.")
    return subtitles


def render_srt(subtitles: list[Subtitle]) -> str:
    return "\n\n".join(
        f"{position}\n{format_timestamp(item.start)} --> {format_timestamp(item.end)}\n{item.text}"
        for position, item in enumerate(subtitles, 1)
    ) + "\n"


def classify_all_segments_piseth_sreymom(
    subtitles: list[Subtitle],
    media_path: str = None,
    audio_full: AudioSegment = None,
) -> dict[int, dict]:
    """
    Analyzes each subtitle segment's audio to detect whether the character speaking
    is Male (Piseth) or Female (Sreymom).
    Returns dict mapping: subtitle.index -> {
        "voice": "km-KH-PisethNeural" or "km-KH-SreymomNeural",
        "gender": "Male" | "Female",
        "name": "Piseth Neural (Male)" | "Sreymom Neural (Female)",
        "icon": "👨" | "👩",
        "pitch": f0
    }
    """
    if not subtitles:
        return {}

    if audio_full is None:
        if not media_path or not Path(media_path).exists():
            return {}
        try:
            audio_full = AudioSegment.from_file(media_path)
        except Exception:
            return {}

    # Global fallback if a segment is too short or quiet
    global_info = detect_voice_piseth_sreymom(audio_segment=audio_full[:60000])
    fallback_info = global_info if global_info else {
        "voice": "km-KH-PisethNeural",
        "gender": "Male",
        "name": "Piseth Neural (Male)",
        "pitch": 130.0,
        "icon": "👨",
    }

    results = {}
    for sub in subtitles:
        start_ms = max(0, sub.start)
        end_ms = min(len(audio_full), sub.end)
        clip_len = end_ms - start_ms
        if clip_len >= 180:
            clip = audio_full[start_ms:end_ms]
            info = detect_voice_piseth_sreymom(audio_segment=clip)
            results[sub.index] = info
        else:
            results[sub.index] = fallback_info

    return results


# ==========================================
# Async Task Runner Helper
# ==========================================
def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


# ==========================================
# AI Transcription & Translation Backends
# ==========================================
def generate_with_gemini_retry(client, model_name: str, contents, config):
    model_names = [model_name]
    fallback_candidates = [
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
    ]
    for c in fallback_candidates:
        if c not in model_names:
            model_names.append(c)

    last_error = None
    for candidate in model_names[:6]:
        for attempt in range(2):
            try:
                return client.models.generate_content(model=candidate, contents=contents, config=config), candidate
            except Exception as error:
                last_error = error
                is_transient = any(m in str(error).upper() for m in ("503", "UNAVAILABLE", "HIGH DEMAND", "RESOURCE_EXHAUSTED", "429"))
                if not is_transient:
                    break
                if attempt < 1:
                    time.sleep(1.5)
    raise RuntimeError(f"All Gemini models exhausted. Last error: {last_error}")


def translate_subtitles_with_gemini(subtitles: list[Subtitle], source_language: str, api_key: str, model_name: str) -> list[Subtitle]:
    if not api_key:
        raise ValueError("Please provide a Gemini API key in the sidebar.")
    from google import genai

    client = genai.Client(api_key=api_key)
    payload = [{"id": position, "text": item.text} for position, item in enumerate(subtitles)]
    source_description = "the detected source language" if source_language.strip().lower() == "auto" else source_language
    prompt = (
        f"Translate these subtitle lines from {source_description} to Khmer. "
        "Return strictly a JSON array of objects, each with numeric 'id' and one translated 'text' field. "
        "Preserve exact meaning, names, punctuation, natural tone, and line order. Do not add markdown or commentary.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    response, used_model = generate_with_gemini_retry(
        client,
        model_name,
        prompt,
        {"response_mime_type": "application/json", "temperature": 0.2},
    )
    if used_model != model_name:
        st.info(f"Switched model: used **{used_model}** for translation.")
    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```json\s*|^```\s*|```$", "", raw_text, flags=re.MULTILINE).strip()
    translated_payload = json.loads(raw_text)
    if not isinstance(translated_payload, list) or len(translated_payload) != len(subtitles):
        raise ValueError(f"Expected {len(subtitles)} translated lines, but received {len(translated_payload)}.")
    translations = {int(item["id"]): str(item["text"]).strip() for item in translated_payload}
    return [Subtitle(item.index, item.start, item.end, translations[position]) for position, item in enumerate(subtitles)]


def translate_subtitles_with_openai(subtitles: list[Subtitle], source_language: str, api_key: str) -> list[Subtitle]:
    if not api_key:
        raise ValueError("Please provide an OpenAI API key in the sidebar.")
    import httpx
    from openai import OpenAI

    client = OpenAI(api_key=api_key, http_client=httpx.Client())
    source_description = "the detected source language" if source_language.strip().lower() == "auto" else source_language
    payload = [{"id": position, "text": item.text} for position, item in enumerate(subtitles)]
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"Translate subtitle lines from {source_description} to Khmer. Return JSON with a 'translations' array of objects having numeric 'id' and 'text'. Maintain exact order, names, and tone.",
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    result = json.loads(response.choices[0].message.content)
    translated_payload = result.get("translations", [])
    if len(translated_payload) != len(subtitles):
        raise ValueError(f"Expected {len(subtitles)} lines, got {len(translated_payload)}.")
    translations = {int(item["id"]): str(item["text"]).strip() for item in translated_payload}
    return [Subtitle(item.index, item.start, item.end, translations[position]) for position, item in enumerate(subtitles)]


def run_auto_translation(subtitles: list[Subtitle], source_language: str, gemini_key: str, openai_key: str, model_name: str) -> list[Subtitle]:
    g_model = model_name if model_name.startswith("gemini-") else "gemini-3.5-flash"
    try:
        if gemini_key:
            return translate_subtitles_with_gemini(subtitles, source_language, gemini_key, g_model)
        elif openai_key:
            return translate_subtitles_with_openai(subtitles, source_language, openai_key)
        else:
            raise ValueError("No API key configured for auto-translation. Enter a Gemini or OpenAI API key in the sidebar.")
    except Exception as gemini_err:
        if openai_key:
            st.info("Gemini was busy, automatically switched to OpenAI GPT-4o Mini.")
            return translate_subtitles_with_openai(subtitles, source_language, openai_key)
        raise gemini_err


def transcribe_with_openai(media_path: Path, api_key: str) -> str:
    if not api_key:
        raise ValueError("OpenAI API key is required for OpenAI transcription.")
    import httpx
    from openai import OpenAI

    client = OpenAI(api_key=api_key, http_client=httpx.Client())
    with media_path.open("rb") as media_file:
        response = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=media_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    segments = getattr(response, "segments", None) or []
    if not segments:
        raise ValueError("OpenAI returned no speech segments.")
    return render_srt([
        Subtitle(index, round(segment.start * 1000), round(segment.end * 1000), segment.text.strip())
        for index, segment in enumerate(segments, 1)
        if segment.text.strip()
    ])


def transcribe_media(uploaded_file, model_name: str, api_key: str) -> str:
    input_suffix = Path(uploaded_file.name).suffix.lower()
    if input_suffix not in {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv"}:
        input_suffix = ".mp4"
    media_path = STORAGE_DIR / f"uploaded_media{input_suffix}"
    media_path.write_bytes(uploaded_file.getvalue())

    st.session_state.uploaded_media_path = str(media_path.resolve())
    st.session_state.is_video = input_suffix in {".mp4", ".mov", ".webm", ".mkv"}

    upload_file_path = media_path
    if st.session_state.is_video:
        audio_extract_path = STORAGE_DIR / "temp_transcribe_audio.mp3"
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(media_path),
            "-vn", "-acodec", "libmp3lame", "-b:a", "64k", "-ar", "16000",
            str(audio_extract_path),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if audio_extract_path.exists() and audio_extract_path.stat().st_size > 0:
                upload_file_path = audio_extract_path
        except Exception:
            upload_file_path = media_path

    if model_name == "openai-gpt-4o-mini-transcribe":
        return transcribe_with_openai(upload_file_path, api_key)

    if model_name.startswith("gemini-"):
        if not api_key:
            raise ValueError("Enter a Gemini API key in the sidebar for Gemini transcription.")
        from google import genai

        client = genai.Client(api_key=api_key)
        media = client.files.upload(file=str(upload_file_path))

        # Wait for file processing if needed
        max_wait = 15
        while hasattr(media, "state") and media.state and media.state.name == "PROCESSING" and max_wait > 0:
            time.sleep(1)
            media = client.files.get(name=media.name)
            max_wait -= 1

        candidate_models = [model_name]
        for alt in ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.6-flash"]:
            if alt not in candidate_models:
                candidate_models.append(alt)

        prompt = (
            "Automatically detect the spoken language and transcribe this media. "
            "Return strictly a JSON array of objects with numeric 'start' and 'end' times in seconds and a 'text' field. "
            "Split speech into natural, readable subtitle segments. Preserve original language. "
            "Do not add markdown backticks or commentary."
        )

        response = None
        last_error = None
        used_model = model_name
        for candidate in candidate_models:
            for attempt in range(2):
                try:
                    response = client.models.generate_content(
                        model=candidate,
                        contents=[media, prompt],
                        config={"response_mime_type": "application/json", "temperature": 0.1},
                    )
                    used_model = candidate
                    break
                except Exception as error:
                    last_error = error
                    is_transient = any(m in str(error).upper() for m in ("503", "UNAVAILABLE", "HIGH DEMAND", "RESOURCE_EXHAUSTED", "429"))
                    if not is_transient:
                        break
                    if attempt < 1:
                        time.sleep(1.5)
            if response and getattr(response, "text", "").strip():
                break

        if not response or not getattr(response, "text", "").strip():
            # Graceful automated fallback to local Whisper if all Gemini models hit quota or fail
            st.warning("⚠️ Gemini quota temporarily reached. Automatically completing transcription with local Whisper...")
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(str(upload_file_path), fp16=False)
            subtitles = [
                Subtitle(index, round(segment["start"] * 1000), round(segment["end"] * 1000), segment["text"].strip())
                for index, segment in enumerate(result["segments"], 1)
                if segment["text"].strip()
            ]
            if not subtitles:
                raise ValueError("No speech segments detected in media.")
            return render_srt(subtitles)

        if used_model != model_name:
            st.info(f"Switched model: used **{used_model}** for transcription.")

        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```json\s*|^```\s*|```$", "", raw_text, flags=re.MULTILINE).strip()
        try:
            parsed = json.loads(raw_text)
            segments = parsed if isinstance(parsed, list) else parsed.get("segments", parsed.get("subtitles", []))
            subtitles = [
                Subtitle(index, round(float(segment["start"]) * 1000), round(float(segment["end"]) * 1000), str(segment["text"]).strip())
                for index, segment in enumerate(segments, 1)
                if str(segment.get("text", "")).strip()
            ]
        except Exception:
            subtitles = []

        if not subtitles:
            # Fallback to local whisper if json parsing failed
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(str(upload_file_path), fp16=False)
            subtitles = [
                Subtitle(index, round(segment["start"] * 1000), round(segment["end"] * 1000), segment["text"].strip())
                for index, segment in enumerate(result["segments"], 1)
                if segment["text"].strip()
            ]

        if not subtitles:
            raise ValueError("No speech segments detected in media.")
        return render_srt(subtitles)

    import whisper

    model = whisper.load_model(model_name)
    result = model.transcribe(str(upload_file_path), fp16=False)
    subtitles = [
        Subtitle(index, round(segment["start"] * 1000), round(segment["end"] * 1000), segment["text"].strip())
        for index, segment in enumerate(result["segments"], 1)
        if segment["text"].strip()
    ]
    return render_srt(subtitles)


# ==========================================
# High-Quality TTS Synthesis Engine
# ==========================================
def synthesize_single_line(text: str, engine: str, voice: str, speed: float, elevenlabs_key: str = "") -> bytes:
    cleaned_text = text.replace("\n", " ").strip()
    # Remove bracketed and parenthesized sound cues (e.g. [Music], [Applause], (laughter))
    cleaned_text = re.sub(r"\[.*?\]|\(.*?\)", "", cleaned_text).strip()

    # If text is empty or contains no pronounceable letters/digits across any script (e.g. "...", "---", "?!?")
    if not cleaned_text or not re.search(r"[\w\u1780-\u17ff]", cleaned_text):
        return AudioSegment.silent(duration=400).export(io.BytesIO(), format="wav").getvalue()

    if voice == "auto_detect" or not voice:
        detected = st.session_state.get("detected_voice_info", {})
        voice = detected.get("voice", "km-KH-PisethNeural")

    if engine == "Microsoft Edge Neural":
        import edge_tts

        speed_diff = int(round((speed - 1.0) * 100))
        rate_str = f"{speed_diff:+d}%"
        edge_voice = voice if (voice and "Neural" in voice) else "km-KH-PisethNeural"

        async def _speak(text_to_speak, rate_val):
            communicate = edge_tts.Communicate(text=text_to_speak, voice=edge_voice, rate=rate_val)
            stream = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    stream.write(chunk["data"])
            return stream.getvalue()

        mp3_bytes = b""
        try:
            mp3_bytes = run_async(_speak(cleaned_text, rate_str))
        except Exception:
            # If rate or parameters caused an issue, retry with standard rate +0%
            if rate_str != "+0%":
                try:
                    mp3_bytes = run_async(_speak(cleaned_text, "+0%"))
                except Exception:
                    pass

        # If Edge TTS failed (e.g. temporary Microsoft server glitch or NoAudioReceived), fallback to gTTS
        if not mp3_bytes:
            try:
                from gTTS import gTTS
                speech_file = io.BytesIO()
                lang = "km" if ("km" in edge_voice.lower() or any(0x1780 <= ord(c) <= 0x17FF for c in cleaned_text)) else "en"
                gTTS(text=cleaned_text, lang=lang).write_to_fp(speech_file)
                mp3_bytes = speech_file.getvalue()
            except Exception:
                pass

        # If even fallback failed, return silent audio segment rather than crashing the pipeline
        if not mp3_bytes:
            return AudioSegment.silent(duration=500).export(io.BytesIO(), format="wav").getvalue()

        try:
            decoded = subprocess.run(
                [FFMPEG_BIN, "-loglevel", "error", "-i", "pipe:0", "-f", "wav", "pipe:1"],
                input=mp3_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout
            return decoded
        except Exception:
            return AudioSegment.silent(duration=500).export(io.BytesIO(), format="wav").getvalue()

    elif engine == "ElevenLabs API":
        if not elevenlabs_key:
            raise ValueError("ElevenLabs API key is required.")
        voice_id = voice if voice and voice != "auto_detect" else "21m00Tcm4TlvDq8ikWAM"  # Default Rachel
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": elevenlabs_key,
        }
        data = {
            "text": cleaned_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        try:
            res = requests.post(url, json=data, headers=headers, timeout=30)
            res.raise_for_status()
            decoded = subprocess.run(
                [FFMPEG_BIN, "-loglevel", "error", "-i", "pipe:0", "-f", "wav", "pipe:1"],
                input=res.content,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout
            return decoded
        except Exception:
            return AudioSegment.silent(duration=500).export(io.BytesIO(), format="wav").getvalue()

    else:
        # Fallback to gTTS
        try:
            from gTTS import gTTS

            speech_file = io.BytesIO()
            gTTS(text=cleaned_text, lang=voice if len(voice) <= 5 else "km").write_to_fp(speech_file)
            decoded = subprocess.run(
                [FFMPEG_BIN, "-loglevel", "error", "-i", "pipe:0", "-f", "wav", "pipe:1"],
                input=speech_file.getvalue(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout
            speech = AudioSegment.from_file(io.BytesIO(decoded), format="wav")
            if speed != 1.0:
                speech = speech.speedup(playback_speed=speed, chunk_size=50, crossfade=10)
            out = io.BytesIO()
            speech.export(out, format="wav")
            return out.getvalue()
        except Exception:
            return AudioSegment.silent(duration=500).export(io.BytesIO(), format="wav").getvalue()


def synthesize_full_audio(subtitles: list[Subtitle], engine: str, voice: str, speed: float, elevenlabs_key: str = "", progress_callback=None) -> bytes:
    output = AudioSegment.silent(duration=0)
    total = len(subtitles)

    # Preload media audio for character voice detection when auto_detect is chosen
    media_audio = None
    if voice == "auto_detect" and st.session_state.get("uploaded_media_path"):
        media_p = Path(st.session_state.uploaded_media_path)
        if media_p.exists():
            try:
                media_audio = AudioSegment.from_file(str(media_p))
            except Exception:
                media_audio = None

    for i, item in enumerate(subtitles):
        target_start = item.start
        if len(output) < target_start:
            output += AudioSegment.silent(duration=target_start - len(output))

        # Check line-specific voice or fallback to character auto-detection (Piseth / Sreymom)
        line_voice = st.session_state.get("subtitle_voices", {}).get(item.index) or getattr(item, "voice", "")
        if not line_voice:
            if voice == "auto_detect":
                # Per-character voice detection dynamically from media audio clip
                if media_audio is not None and (item.end - item.start) >= 180:
                    try:
                        clip = media_audio[max(0, item.start):min(len(media_audio), item.end)]
                        seg_det = detect_voice_piseth_sreymom(audio_segment=clip)
                        line_voice = seg_det.get("voice", "km-KH-PisethNeural")
                        st.session_state.setdefault("subtitle_voices", {})[item.index] = line_voice
                    except Exception:
                        line_voice = ""
                if not line_voice:
                    detected = st.session_state.get("detected_voice_info", {})
                    line_voice = detected.get("voice", "km-KH-PisethNeural")
            else:
                line_voice = voice

        try:
            wav_bytes = synthesize_single_line(item.text, engine, line_voice, speed, elevenlabs_key)
            clip = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
            output += clip
        except Exception:
            line_duration = max(300, (item.end - item.start)) if item.end > item.start else 500
            output += AudioSegment.silent(duration=line_duration)

        if progress_callback:
            line_tag = "👨 Piseth" if "Piseth" in line_voice else ("👩 Sreymom" if "Sreymom" in line_voice else line_voice)
            try:
                progress_callback(i + 1, total, line_tag)
            except TypeError:
                progress_callback(i + 1, total)

    wav_file = io.BytesIO()
    output.export(wav_file, format="wav")
    final_bytes = wav_file.getvalue()

    # Save to disk for video multiplexing
    dubbed_audio_path = STORAGE_DIR / "dubbed_voiceover.wav"
    dubbed_audio_path.write_bytes(final_bytes)
    st.session_state.dubbed_audio_path = str(dubbed_audio_path.resolve())

    return final_bytes


# ==========================================
# Video Studio & Subtitle Burning Engine
# ==========================================
def video_has_audio(video_file: str) -> bool:
    try:
        res = subprocess.run([FFMPEG_BIN, "-i", video_file], capture_output=True, text=True)
        return "Audio:" in res.stderr
    except Exception:
        return True


def process_video_dubbing(
    video_path: str,
    audio_path: str = None,
    srt_path: str = None,
    audio_mode: str = "replace",  # 'replace', 'mix', 'keep' (backward compatibility)
    orig_volume: float = 0.0,     # backward compatibility
    dub_volume: float = 1.0,      # volume of dubbed voice-over (1.0 = normal)
    burn_subtitles: bool = False, # default False (do not burn subtitles on video)
    enable_bg_music: bool = False, # Turn ON to extract & keep video background music
    bg_music_vol: float = 0.20,   # Volume of background music (0.05 to 0.80)
    enable_orig_voice: bool = False, # Turn ON to keep original speaker/actor voice (documentary style)
    orig_voice_vol: float = 0.15, # Volume of original voice (0.05 to 0.60)
) -> str:
    out_video_path = STORAGE_DIR / "dubbed_output.mp4"
    if out_video_path.exists():
        try:
            out_video_path.unlink()
        except Exception:
            pass

    cmd = [FFMPEG_BIN, "-y", "-i", video_path]
    has_audio_track = audio_path and Path(audio_path).exists()
    has_source_audio = video_has_audio(video_path)

    if has_audio_track and dub_volume > 0:
        cmd.extend(["-i", audio_path])

    # Backward compatibility with legacy orig_volume if flags not set
    if not enable_bg_music and not enable_orig_voice and orig_volume > 0.0:
        enable_bg_music = True
        bg_music_vol = orig_volume

    # Normalize volume inputs (supports 0-100 percentage or 0.0-1.0 float)
    norm_bg_vol = (float(bg_music_vol) / 100.0) if float(bg_music_vol) > 1.0 else float(bg_music_vol)
    norm_orig_vol = (float(orig_voice_vol) / 100.0) if float(orig_voice_vol) > 1.0 else float(orig_voice_vol)
    norm_dub_vol = (float(dub_volume) / 100.0) if float(dub_volume) > 1.5 else float(dub_volume)

    # Video filters (subtitles) - ONLY if burn_subtitles is True
    video_filters = []
    if burn_subtitles and srt_path and Path(srt_path).exists():
        escaped_srt = Path(srt_path).resolve().as_posix().replace(":", r"\:")
        video_filters.append(
            f"subtitles='{escaped_srt}':force_style='Fontname=Leelawadee UI,FontSize=16,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=4,MarginV=25,Outline=1'"
        )

    filter_complex = []
    if video_filters:
        filter_complex.append(f"[0:v:0]{','.join(video_filters)}[vout]")
        video_map = "[vout]"
    else:
        video_map = "0:v:0"

    audio_map = None
    has_dub = has_audio_track and norm_dub_vol > 0

    if has_dub:
        # TTS Voice-Over track is available as [1:a:0]
        if not has_source_audio or (not enable_bg_music and not enable_orig_voice) or (norm_bg_vol <= 0 and norm_orig_vol <= 0):
            # 100% clean dubbed voice-over (original audio muted)
            filter_complex.append(f"[1:a:0]volume={norm_dub_vol:.2f}[dubout]")
            audio_map = "[dubout]"
        elif enable_bg_music and not enable_orig_voice:
            # Background Music ON, Original Voice OFF:
            # Suppress center vocal dialogue from video audio, isolate stereo music
            filter_complex.append(
                f"[0:a:0]stereotools=mlev=0.015625:slev=1.2,volume={norm_bg_vol:.2f}[bg];"
                f"[1:a:0]volume={norm_dub_vol:.2f}[dub];"
                f"[bg][dub]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            audio_map = "[aout]"
        elif enable_orig_voice and not enable_bg_music:
            # Original Voice ON, Background Music OFF:
            # Retain original actor dialogue softly behind voice-over
            filter_complex.append(
                f"[0:a:0]stereotools=mlev=1.2:slev=0.15,volume={norm_orig_vol:.2f}[orig];"
                f"[1:a:0]volume={norm_dub_vol:.2f}[dub];"
                f"[orig][dub]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            audio_map = "[aout]"
        else:
            # Both Background Music & Original Voice ON:
            # Full original track mixed at ducked level behind voice-over
            mix_vol = max(norm_bg_vol, norm_orig_vol)
            filter_complex.append(
                f"[0:a:0]volume={mix_vol:.2f}[orig];"
                f"[1:a:0]volume={norm_dub_vol:.2f}[dub];"
                f"[orig][dub]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            audio_map = "[aout]"
    else:
        # No dubbed voice-over (or dub_volume == 0)
        if not has_source_audio or (not enable_bg_music and not enable_orig_voice) or (norm_bg_vol <= 0 and norm_orig_vol <= 0):
            audio_map = None
        elif enable_bg_music and not enable_orig_voice:
            filter_complex.append(f"[0:a:0]stereotools=mlev=0.015625:slev=1.2,volume={norm_bg_vol:.2f}[bgout]")
            audio_map = "[bgout]"
        elif enable_orig_voice and not enable_bg_music:
            filter_complex.append(f"[0:a:0]stereotools=mlev=1.2:slev=0.15,volume={norm_orig_vol:.2f}[origout]")
            audio_map = "[origout]"
        else:
            mix_vol = max(norm_bg_vol, norm_orig_vol)
            filter_complex.append(f"[0:a:0]volume={mix_vol:.2f}[origout]")
            audio_map = "[origout]"

    if filter_complex:
        cmd.extend(["-filter_complex", ";".join(filter_complex)])
        cmd.extend(["-map", video_map])
        if audio_map:
            cmd.extend(["-map", audio_map])
        else:
            cmd.extend(["-an"])
    else:
        cmd.extend(["-map", video_map])
        if audio_map:
            cmd.extend(["-map", audio_map])
        else:
            cmd.extend(["-an"])

    cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_video_path.resolve()),
    ])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{proc.stderr}")

    return str(out_video_path.resolve())


# ==========================================
# UI Styling & Modern Theme
# ==========================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kantumruy+Pro:ital,wght@0,300..700;1,300..700&family=Outfit:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
    
    :root {
        --primary: #059669;
        --primary-hover: #10b981;
        --accent: #f97316;
        --bg-main: #0a0f1d;
        --card-bg: rgba(23, 32, 54, 0.7);
        --border-color: rgba(255, 255, 255, 0.08);
        --text-primary: #f8fafc;
        --text-secondary: #94a3b8;
        --font-sans: 'Plus Jakarta Sans', 'Kantumruy Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        --font-khmer: 'Kantumruy Pro', 'Leelawadee UI', 'Khmer OS Battambang', 'Segoe UI', sans-serif;
    }
    
    .stApp {
        background: radial-gradient(circle at 90% 10%, rgba(16, 185, 129, 0.08) 0%, transparent 40%),
                    radial-gradient(circle at 10% 90%, rgba(249, 115, 22, 0.06) 0%, transparent 40%),
                    #0f172a;
        color: var(--text-primary);
        font-family: var(--font-sans);
    }

    /* Khmer Script Line-Height and Typography Support */
    p, div, span, label, input, textarea, button, [data-baseweb="tab"] {
        font-family: var(--font-sans);
        line-height: 1.65;
    }

    textarea, input {
        font-family: var(--font-khmer) !important;
        line-height: 1.7 !important;
    }

    .khmer-text {
        font-family: var(--font-khmer) !important;
        line-height: 1.7 !important;
    }
    
    h1, h2, h3, h4 {
        font-family: 'Outfit', var(--font-khmer), sans-serif;
        font-weight: 700;
        letter-spacing: -0.02em;
        line-height: 1.3;
    }
    
    .hero-container {
        padding: 1.6rem 1.8rem;
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        backdrop-filter: blur(12px);
        margin-bottom: 1.5rem;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
    }
    
    .badge-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        margin-bottom: 0.6rem;
    }
    
    .hero-title {
        font-size: clamp(1.8rem, 4vw, 2.75rem);
        margin: 0 0 0.4rem 0;
        background: linear-gradient(135deg, #ffffff 30%, #94a3b8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .hero-subtitle {
        color: var(--text-secondary);
        font-size: 0.95rem;
        margin: 0;
        line-height: 1.5;
    }
    
    .metric-card {
        background: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        text-align: center;
    }
    
    .metric-value {
        font-family: 'Outfit', sans-serif;
        font-size: 1.45rem;
        font-weight: 700;
        color: #38bdf8;
    }
    
    .metric-label {
        font-size: 0.78rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .srt-box {
        background: #090d16;
        color: #34d399;
        border: 1px solid rgba(52, 211, 153, 0.2);
        border-radius: 10px;
        padding: 0.9rem;
        font-family: var(--font-khmer), 'JetBrains Mono', Consolas, monospace;
        font-size: 0.88rem;
        line-height: 1.7;
        max-height: 300px;
        overflow-y: auto;
        white-space: pre-wrap;
        -webkit-overflow-scrolling: touch;
    }
    
    .tab-header {
        border-left: 4px solid var(--accent);
        padding-left: 1rem;
        margin-bottom: 1.3rem;
    }

    /* Touch-Friendly Buttons (Min 44px) */
    button[kind="primary"], button[kind="secondary"], .stButton > button {
        min-height: 44px !important;
        padding: 0.55rem 1.1rem !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
        transition: all 0.15s ease-in-out !important;
    }
    .stButton > button:active {
        transform: scale(0.98);
    }

    /* Modern Responsive Pills & Segmented Voice Buttons */
    div[data-testid="stPills"], div[data-testid="stSegmentedControl"] {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 6px !important;
        margin: 4px 0 6px 0 !important;
    }
    div[data-testid="stPills"] button, div[data-testid="stSegmentedControl"] button {
        min-height: 42px !important;
        padding: 0.45rem 1rem !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        background: rgba(30, 41, 59, 0.75) !important;
        color: #e2e8f0 !important;
        transition: all 0.15s ease-in-out !important;
    }
    div[data-testid="stPills"] button:hover, div[data-testid="stSegmentedControl"] button:hover {
        border-color: rgba(56, 189, 248, 0.4) !important;
        background: rgba(30, 41, 59, 0.95) !important;
    }
    div[data-testid="stPills"] button[aria-selected="true"], div[data-testid="stSegmentedControl"] button[aria-selected="true"] {
        background: linear-gradient(135deg, #0284c7 0%, #38bdf8 100%) !important;
        color: #ffffff !important;
        border-color: #38bdf8 !important;
        box-shadow: 0 2px 10px rgba(56, 189, 248, 0.35) !important;
        font-weight: 700 !important;
    }

    /* Mobile Responsive Tab Navigation */
    div[data-baseweb="tab-list"] {
        gap: 6px !important;
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
        scrollbar-width: thin;
        padding-bottom: 4px !important;
        -webkit-overflow-scrolling: touch;
    }
    div[data-baseweb="tab-list"]::-webkit-scrollbar {
        height: 3px;
    }
    div[data-baseweb="tab-list"]::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.15);
        border-radius: 3px;
    }
    button[data-baseweb="tab"] {
        padding: 0.55rem 0.95rem !important;
        border-radius: 8px 8px 0 0 !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
    }

    /* Mobile Subtitle Card Editor Components */
    .mobile-card-editor {
        background: linear-gradient(135deg, rgba(23, 32, 54, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(56, 189, 248, 0.22);
        border-radius: 14px;
        padding: 1.1rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 20px -4px rgba(0, 0, 0, 0.35);
    }
    .badge-time {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.82rem;
        font-family: 'JetBrains Mono', monospace;
        background: rgba(56, 189, 248, 0.12);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.25);
    }
    .source-preview {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.9rem;
        color: #cbd5e1;
        margin: 0.5rem 0 0.8rem 0;
        line-height: 1.55;
    }
    
    @media (max-width: 768px) {
        .hero-container {
            padding: 1.1rem 1.1rem !important;
            margin-bottom: 1.1rem !important;
            border-radius: 12px !important;
        }
        .hero-title {
            font-size: 1.55rem !important;
        }
        .hero-subtitle {
            font-size: 0.82rem !important;
            line-height: 1.4 !important;
        }
        .tab-header {
            margin-bottom: 1rem !important;
        }
        .tab-header h3 {
            font-size: 1.18rem !important;
        }
        .metric-value {
            font-size: 1.25rem !important;
        }
        .metric-card {
            padding: 0.7rem 0.85rem !important;
        }
    }

    /* Login Screen Glassmorphic Theme */
    .login-container-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.98) 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 24px;
        padding: 2.2rem 2rem;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6), 0 0 30px rgba(16, 185, 129, 0.12);
        backdrop-filter: blur(20px);
        margin: 1.5rem auto 1.5rem auto;
        text-align: center;
    }
    .login-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 5px 14px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        background: rgba(16, 185, 129, 0.16);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.35);
        margin-bottom: 0.8rem;
    }
    .login-title-text {
        font-size: 1.75rem;
        font-weight: 700;
        margin: 0 0 0.4rem 0;
        background: linear-gradient(135deg, #ffffff 40%, #94a3b8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .login-desc-text {
        color: #94a3b8;
        font-size: 0.92rem;
        margin: 0 0 0.5rem 0;
        line-height: 1.5;
    }
    .login-credential-box {
        background: rgba(16, 185, 129, 0.08);
        border: 1px dashed rgba(16, 185, 129, 0.3);
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 0.84rem;
        color: #a7f3d0;
        margin-top: 1.2rem;
        line-height: 1.6;
        text-align: left;
    }
    .login-credential-box code {
        background: rgba(0, 0, 0, 0.4);
        padding: 2px 6px;
        border-radius: 4px;
        color: #6ee7b7;
        font-weight: 600;
    }

    /* Customer Account Management & KPI Count Styling */
    .kpi-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
        margin-bottom: 1.5rem;
    }
    .kpi-card {
        background: linear-gradient(135deg, rgba(23, 32, 54, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid var(--border-color);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        text-align: center;
        box-shadow: 0 4px 15px -3px rgba(0, 0, 0, 0.3);
        transition: transform 0.15s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
    }
    .kpi-card.pending {
        border-color: rgba(245, 158, 11, 0.4);
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(15, 23, 42, 0.95) 100%);
    }
    .kpi-card.approved {
        border-color: rgba(16, 185, 129, 0.4);
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(15, 23, 42, 0.95) 100%);
    }
    .kpi-card.total {
        border-color: rgba(56, 189, 248, 0.4);
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.1) 0%, rgba(15, 23, 42, 0.95) 100%);
    }
    .kpi-card.admin {
        border-color: rgba(168, 85, 247, 0.4);
        background: linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(15, 23, 42, 0.95) 100%);
    }
    .kpi-value {
        font-family: 'Outfit', sans-serif;
        font-size: 1.85rem;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: 0.2rem;
    }
    .kpi-label {
        font-size: 0.78rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
    }

    .customer-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.85) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 0.9rem;
        transition: all 0.15s ease;
    }
    .customer-card.is-pending {
        border-left: 4px solid #f59e0b;
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.06) 0%, rgba(15, 23, 42, 0.85) 100%);
    }
    .customer-card.is-approved {
        border-left: 4px solid #10b981;
    }
    .customer-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 0.6rem;
    }
    .customer-avatar {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 1.05rem;
        margin-right: 8px;
    }
    .customer-title-block {
        display: flex;
        align-items: center;
    }
    .customer-uname {
        font-size: 1.05rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .badge-status {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        text-transform: uppercase;
    }
    .badge-status.pending {
        background: rgba(245, 158, 11, 0.18);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }
    .badge-status.approved {
        background: rgba(16, 185, 129, 0.18);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .badge-status.admin {
        background: rgba(168, 85, 247, 0.18);
        color: #c084fc;
        border: 1px solid rgba(168, 85, 247, 0.4);
    }
    .customer-info-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 8px;
        font-size: 0.85rem;
        color: #94a3b8;
        margin-bottom: 0.8rem;
    }
    .customer-info-item span {
        color: #f1f5f9;
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# Authentication & User Gate
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_user" not in st.session_state:
    st.session_state.auth_user = ""
if "current_device" not in st.session_state:
    st.session_state.current_device = ""

# Auto-Login with Saved Device Token
if not st.session_state.authenticated:
    device_token = st.query_params.get("device", "")
    saved_tokens = saved_config.get("device_tokens", {})
    if device_token and device_token in saved_tokens:
        tok_data = saved_tokens[device_token]
        tok_user = tok_data.get("user", "")
        auth_users = saved_config.get("auth_users", {})
        if tok_user in auth_users or tok_user == "admin":
            st.session_state.authenticated = True
            st.session_state.auth_user = tok_user
            st.session_state.current_device = tok_data.get("device_name", "Saved Device")


def complete_user_login(username: str, remember: bool):
    dev_info = get_client_device_info()
    auth_users = saved_config.get("auth_users", {})
    if username in auth_users:
        if isinstance(auth_users[username], dict):
            auth_users[username]["last_device"] = dev_info
            auth_users[username]["last_login"] = time.strftime("%Y-%m-%d %H:%M")
        else:
            auth_users[username] = {
                "password": auth_users[username],
                "role": "admin" if username == "admin" else "user",
                "status": "approved",
                "last_device": dev_info,
                "last_login": time.strftime("%Y-%m-%d %H:%M"),
            }
    elif username == "admin":
        auth_users["admin"] = {
            "password": "dubber123",
            "role": "admin",
            "status": "approved",
            "last_device": dev_info,
            "last_login": time.strftime("%Y-%m-%d %H:%M"),
        }

    updates = {"auth_users": auth_users}
    if remember:
        token = secrets.token_hex(16)
        dev_tokens = saved_config.get("device_tokens", {})
        dev_tokens[token] = {
            "user": username,
            **dev_info
        }
        updates["device_tokens"] = dev_tokens
        st.query_params["device"] = token

    save_saved_config(updates)
    st.session_state.authenticated = True
    st.session_state.auth_user = username
    st.session_state.current_device = dev_info.get("device_name", "Saved Device")
    st.toast(f"Welcome back, {username}! Device saved 📱", icon="🎉")
    st.rerun()


if not st.session_state.authenticated:
    _, col_login, _ = st.columns([1, 1.4, 1])
    with col_login:
        st.markdown(
            """
            <div class="login-container-card">
                <div class="login-badge">🔒 Studio Access Portal</div>
                <div style="font-size: 2.8rem; margin: 0.2rem 0 0.4rem 0;">🎙️</div>
                <h2 class="login-title-text">Dubber AI Pro Studio</h2>
                <p class="login-desc-text">Sign in to your account or register for new studio access.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_login, tab_signup = st.tabs(["🔑 Sign In", "✨ Create Account"])

        with tab_login:
            with st.form(key="dubber_login_form"):
                login_username = st.text_input("Username", key="inp_user", placeholder="Enter your username").strip()
                login_password = st.text_input("Password", type="password", key="inp_pass", placeholder="Enter your password").strip()
                save_device = st.checkbox("📱 Save this device (stay signed in on this phone/PC)", value=True, help="Remembers this device so you don't have to enter your password again.")
                btn_submit_login = st.form_submit_button("🚀 Sign In to Studio", type="primary", use_container_width=True)

                if btn_submit_login:
                    if not login_username or not login_password:
                        st.error("Please enter both username and password.")
                    else:
                        auth_users = saved_config.get("auth_users", {})
                        pending_users = saved_config.get("pending_users", {})

                        if login_username in pending_users:
                            st.warning("⏳ **Account Pending Approval**: Your registration has been submitted and is currently awaiting administrator review. Please check back soon.")
                        elif login_username in auth_users:
                            expected_pw = get_user_password(auth_users[login_username])
                            if login_password == expected_pw:
                                complete_user_login(login_username, save_device)
                            else:
                                st.error("❌ Incorrect password. Please try again.")
                        elif login_username == "admin" and login_password in ("dubber123", "admin123"):
                            complete_user_login("admin", save_device)
                        else:
                            st.error("❌ Invalid username or password. If you don't have an account, click 'Create Account' above.")

        with tab_signup:
            with st.form(key="dubber_signup_form"):
                st.markdown("<p style='font-size:0.86rem; color:#94a3b8; margin-bottom:0.8rem;'>Submit your details below. New customer accounts are reviewed and activated by the administrator.</p>", unsafe_allow_html=True)
                signup_user = st.text_input("Desired Username", key="reg_user", placeholder="e.g. video_editor99").strip()
                signup_name = st.text_input("Full Name or Note (Optional)", key="reg_name", placeholder="e.g. Video Editor / Studio Name").strip()
                signup_contact = st.text_input("Phone Number / Telegram / Email (Optional)", key="reg_contact", placeholder="e.g. 012 345 678 or @telegram").strip()
                signup_pass = st.text_input("Password", type="password", key="reg_pass", placeholder="Minimum 4 characters").strip()
                signup_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm", placeholder="Re-enter password").strip()
                btn_submit_signup = st.form_submit_button("📝 Register Customer Account", type="primary", use_container_width=True)

                if btn_submit_signup:
                    auth_users = saved_config.get("auth_users", {})
                    pending_users = saved_config.get("pending_users", {})

                    if not signup_user or not signup_pass:
                        st.error("Please fill in both username and password.")
                    elif len(signup_user) < 3:
                        st.error("Username must be at least 3 characters.")
                    elif not re.match(r"^[a-zA-Z0-9_\-\.]+$", signup_user):
                        st.error("Username may only contain letters, numbers, hyphens, and underscores.")
                    elif len(signup_pass) < 4:
                        st.error("Password must be at least 4 characters.")
                    elif signup_pass != signup_confirm:
                        st.error("Passwords do not match.")
                    elif signup_user in auth_users or signup_user == "admin":
                        st.error(f"The username '{signup_user}' is already taken. Please choose another username.")
                    elif signup_user in pending_users:
                        st.warning(f"Registration for '{signup_user}' is already pending administrator approval.")
                    else:
                        pending_users[signup_user] = {
                            "password": signup_pass,
                            "name": signup_name or signup_user,
                            "contact": signup_contact or "N/A",
                            "created_at": time.strftime("%Y-%m-%d %H:%M"),
                            "status": "pending",
                        }
                        save_saved_config({"pending_users": pending_users})
                        st.success("✅ **Registration Submitted Successfully!**")
                        st.info("⏳ Your account is now **waiting for administrator approval**. Once approved, you will be able to sign in.")
    st.stop()

# ==========================================
# Authenticated App Banner
# ==========================================
st.markdown(
    """
    <div class="hero-container">
        <div class="badge-pill">🎙️ AI Localization Studio & Video Dubber</div>
        <h1 class="hero-title">Dubber AI Pro Studio</h1>
        <p class="hero-subtitle">Automatic Speech Transcription • Khmer Translation • Microsoft Neural TTS • Video Hardsubs & Dubbing</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# Session State Initialization
# ==========================================
if "source_srt" not in st.session_state:
    st.session_state.source_srt = ""
if "khmer_srt" not in st.session_state:
    st.session_state.khmer_srt = ""
if "uploaded_media_path" not in st.session_state:
    st.session_state.uploaded_media_path = ""
if "is_video" not in st.session_state:
    st.session_state.is_video = False
if "dubbed_audio_bytes" not in st.session_state:
    st.session_state.dubbed_audio_bytes = None
if "dubbed_audio_path" not in st.session_state:
    st.session_state.dubbed_audio_path = ""
if "output_video_path" not in st.session_state:
    st.session_state.output_video_path = ""
if "enable_bg_music" not in st.session_state:
    st.session_state.enable_bg_music = False
if "bg_music_vol" not in st.session_state:
    st.session_state.bg_music_vol = 20
elif isinstance(st.session_state.bg_music_vol, float) and st.session_state.bg_music_vol <= 1.0:
    st.session_state.bg_music_vol = int(round(st.session_state.bg_music_vol * 100))

if "enable_orig_voice" not in st.session_state:
    st.session_state.enable_orig_voice = False
if "orig_voice_vol" not in st.session_state:
    st.session_state.orig_voice_vol = 15
elif isinstance(st.session_state.orig_voice_vol, float) and st.session_state.orig_voice_vol <= 1.0:
    st.session_state.orig_voice_vol = int(round(st.session_state.orig_voice_vol * 100))

if "dub_voice_vol" not in st.session_state:
    st.session_state.dub_voice_vol = 100
elif isinstance(st.session_state.dub_voice_vol, float) and st.session_state.dub_voice_vol <= 1.5:
    st.session_state.dub_voice_vol = int(round(st.session_state.dub_voice_vol * 100))

if "burn_subtitles_pref" not in st.session_state:
    st.session_state.burn_subtitles_pref = False
if "detected_voice_info" not in st.session_state:
    st.session_state.detected_voice_info = None
if "subtitle_voices" not in st.session_state:
    st.session_state.subtitle_voices = {}
if "chosen_voice" not in st.session_state:
    st.session_state.chosen_voice = "auto_detect"
if "voice_btn_selection" not in st.session_state or st.session_state.voice_btn_selection not in VOICE_BUTTON_OPTIONS:
    st.session_state.voice_btn_selection = "🎭 Auto (Piseth 👨 / Sreymom 👩)"
if "voice_gender_counts" not in st.session_state:
    st.session_state.voice_gender_counts = {"male": 0, "female": 0}

# ==========================================
# Sidebar: Settings & Configuration
# ==========================================
with st.sidebar:
    curr_u = st.session_state.get('auth_user', 'admin')
    curr_dev = st.session_state.get('current_device', '')
    if not curr_dev:
        curr_dev = get_client_device_info().get('device_name', 'Current Device')

    st.markdown(
        f"""
        <div style="background: rgba(30, 41, 59, 0.85); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; padding: 11px 14px; margin-bottom: 0.8rem;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                <div style="font-size: 0.95rem; font-weight: 700; color: #34d399;">👤 {escape(curr_u)}</div>
                <span style="background: rgba(16, 185, 129, 0.18); color: #34d399; font-size: 0.68rem; font-weight: 700; padding: 2px 7px; border-radius: 999px; border: 1px solid rgba(16, 185, 129, 0.3);">SAVED DEVICE</span>
            </div>
            <div style="font-size: 0.76rem; color: #94a3b8;">📱 {escape(curr_dev)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("🚪 Log Out & Remove Device", key="btn_logout", use_container_width=True):
        dev_param = st.query_params.get("device", "")
        cfg = load_saved_config()
        dev_tokens = cfg.get("device_tokens", {})
        if dev_param in dev_tokens:
            del dev_tokens[dev_param]
            save_saved_config({"device_tokens": dev_tokens})
        st.query_params.clear()
        st.session_state.authenticated = False
        st.session_state.auth_user = ""
        st.session_state.current_device = ""
        st.toast("Logged out and device disconnected.")
        st.rerun()

    st.markdown("---")
    st.markdown("### ⚙️ Pipeline Configuration")
    
    pipeline_model = st.selectbox(
        "Speech Transcription Model",
        [
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "openai-gpt-4o-mini-transcribe",
            "base",
            "small",
            "medium",
        ],
        help="Gemini and OpenAI models run via cloud API. Whisper ('base', 'small', 'medium') runs 100% locally on CPU/GPU without quota limits.",
    )
    
    source_language = st.text_input(
        "Source Media Language",
        value="auto",
        help="Language code of the original audio (e.g., 'auto', 'en', 'zh', 'th', 'ja').",
    )

    st.markdown("---")
    st.markdown("### 🔑 API Keys")
    
    def_gemini = os.getenv("GEMINI_API_KEY", saved_config.get("gemini_api_key", ""))
    gemini_key = st.text_input("Gemini API Key", value=def_gemini, type="password", help="Get free key at ai.google.dev")
    
    def_openai = os.getenv("OPENAI_API_KEY", saved_config.get("openai_api_key", ""))
    openai_key = st.text_input("OpenAI API Key", value=def_openai, type="password", help="platform.openai.com")

    def_eleven = os.getenv("ELEVENLABS_API_KEY", saved_config.get("elevenlabs_api_key", ""))
    eleven_key = st.text_input("ElevenLabs API Key (Optional)", value=def_eleven, type="password", help="api.elevenlabs.io")

    if st.button("💾 Save Keys to Disk", use_container_width=True):
        save_saved_config({
            "gemini_api_key": gemini_key.strip(),
            "openai_api_key": openai_key.strip(),
            "elevenlabs_api_key": eleven_key.strip(),
        })
        st.success("API keys safely saved to .dubber_config.json")

    with st.expander("🔐 Change Password"):
        new_pw = st.text_input("New Password", type="password", key="inp_new_pw")
        confirm_pw = st.text_input("Confirm Password", type="password", key="inp_confirm_pw")
        if st.button("Update Password", key="btn_update_pw", use_container_width=True):
            if not new_pw:
                st.error("Password cannot be empty.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            else:
                users = saved_config.get("auth_users", {"admin": "dubber123"})
                curr_user = st.session_state.get("auth_user", "admin")
                users[curr_user] = new_pw
                save_saved_config({"auth_users": users})
                st.success("✅ Password updated! Use your new password next time you log in.")

    if st.session_state.get("auth_user", "") == "admin":
        auth_users = saved_config.get("auth_users", {})
        pending_users = saved_config.get("pending_users", {})
        num_pending = len(pending_users)

        pending_label = f"👥 User Approvals ({num_pending})" if num_pending > 0 else "👥 User Approvals"
        with st.expander(pending_label, expanded=(num_pending > 0)):
            if num_pending > 0:
                st.markdown(
                    f"<span style='background:rgba(239,68,68,0.2); color:#fca5a5; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:999px;'>⚠️ {num_pending} Waiting for Approval</span>",
                    unsafe_allow_html=True,
                )
                st.write("")
                for p_user, p_info in list(pending_users.items()):
                    p_pw = get_user_password(p_info)
                    p_name = p_info.get("name", p_user) if isinstance(p_info, dict) else p_user
                    p_date = p_info.get("created_at", "") if isinstance(p_info, dict) else ""

                    st.markdown(
                        f"""
                        <div style="background:rgba(30,41,59,0.7); border:1px solid rgba(255,255,255,0.08); border-radius:10px; padding:10px; margin-bottom:8px;">
                            <div style="font-weight:700; color:#34d399;">👤 {escape(p_user)}</div>
                            <div style="font-size:0.8rem; color:#94a3b8;">Note: {escape(p_name)}</div>
                            <div style="font-size:0.74rem; color:#64748b;">Registered: {escape(p_date)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    col_app, col_rej = st.columns(2)
                    with col_app:
                        if st.button("✅ Approve", key=f"app_{p_user}", use_container_width=True):
                            auth_users[p_user] = {
                                "password": p_pw,
                                "name": p_name,
                                "role": "user",
                                "status": "approved",
                                "approved_at": time.strftime("%Y-%m-%d %H:%M"),
                            }
                            del pending_users[p_user]
                            save_saved_config({"auth_users": auth_users, "pending_users": pending_users})
                            st.toast(f"✅ Approved user: {p_user}!", icon="🎉")
                            st.rerun()
                    with col_rej:
                        if st.button("❌ Reject", key=f"rej_{p_user}", use_container_width=True):
                            del pending_users[p_user]
                            save_saved_config({"pending_users": pending_users})
                            st.toast(f"Rejected registration for {p_user}.", icon="🗑️")
                            st.rerun()
                    st.markdown("---")
            else:
                st.info("✅ No pending registrations.")

            st.markdown("**Approved Accounts:**")
            for a_user, a_info in list(auth_users.items()):
                is_adm = (a_user == "admin" or (isinstance(a_info, dict) and a_info.get("role") == "admin"))
                col_u, col_del = st.columns([3, 1])
                with col_u:
                    st.markdown(f"• `{a_user}` {'*(Admin)*' if is_adm else '*(User)*'}")
                with col_del:
                    if not is_adm:
                        if st.button("🗑️", key=f"del_u_{a_user}", help=f"Remove user {a_user}"):
                            del auth_users[a_user]
                            save_saved_config({"auth_users": auth_users})
                            st.toast(f"Removed user {a_user}.")
                            st.rerun()

    st.markdown("---")
    st.markdown("### 🔊 Voice-Over Engine")
    
    tts_engine = st.selectbox(
        "TTS Engine",
        ["Microsoft Edge Neural", "Google gTTS", "ElevenLabs API"],
        help="Microsoft Edge Neural provides realistic studio voices with native Khmer support for free with no key required!",
    )
    
    if tts_engine == "Microsoft Edge Neural":
        st.markdown("**Voice Selection (1-Click Buttons):**")
        cur_sb_v = st.session_state.get("voice_btn_selection", "🎭 Auto (Piseth 👨 / Sreymom 👩)")
        if cur_sb_v not in VOICE_BUTTON_OPTIONS:
            cur_sb_v = "🎭 Auto (Piseth 👨 / Sreymom 👩)"

        sb_voice_choice = st.pills(
            "Speaker Voice",
            options=VOICE_BUTTON_OPTIONS,
            default=cur_sb_v,
            key="sb_voice_pills",
            label_visibility="collapsed",
        )
        if sb_voice_choice:
            st.session_state.voice_btn_selection = sb_voice_choice
            st.session_state.chosen_voice = VOICE_BUTTON_MAP[sb_voice_choice]
            chosen_voice = st.session_state.chosen_voice
        else:
            chosen_voice = st.session_state.get("chosen_voice", "auto_detect")

        if chosen_voice == "auto_detect":
            vg = st.session_state.get("voice_gender_counts", {})
            m_c = vg.get("male", 0)
            f_c = vg.get("female", 0)
            if m_c or f_c:
                st.caption(f"🎭 Auto-Detected: **{m_c} 👨 Piseth (ប្រុស)** • **{f_c} 👩 Sreymom (ស្រី)**")
            else:
                det_sb = st.session_state.get("detected_voice_info")
                if det_sb:
                    st.caption(f"🎯 Default: **{det_sb.get('icon', '🎙️')} {det_sb.get('name', 'Piseth Neural')}** ({det_sb.get('pitch', 130)} Hz)")
                else:
                    st.caption("🎯 Auto-Detect: ចាប់សម្លេងតួអង្គប្រុស (Piseth 👨) ឬ ស្រី (Sreymom 👩)")
        elif chosen_voice == "km-KH-PisethNeural":
            st.caption("👨 Selected: **Piseth Neural** (Khmer Male / ប្រុស)")
        elif chosen_voice == "km-KH-SreymomNeural":
            st.caption("👩 Selected: **Sreymom Neural** (Khmer Female / ស្រី)")

        with st.expander("🌐 More International Voices"):
            more_voices = [k for k in EDGE_VOICES.keys() if k not in VOICE_BUTTON_OPTIONS]
            more_selection = st.selectbox("Other Languages", more_voices, index=0, key="sb_other_voices")
            if st.button("Apply Voice", key="btn_apply_other_voice", use_container_width=True):
                chosen_voice = EDGE_VOICES[more_selection]
                st.session_state.chosen_voice = chosen_voice
                st.session_state.voice_btn_selection = more_selection
                st.rerun()
    elif tts_engine == "ElevenLabs API":
        chosen_voice = st.text_input("ElevenLabs Voice ID", value="21m00Tcm4TlvDq8ikWAM", help="e.g. Rachel, Adam")
    else:
        chosen_voice = st.selectbox("gTTS Voice Language", ["km", "en", "th", "vi", "zh-CN"], index=0)

    voice_speed = st.slider("Speech Rate / Speed", min_value=0.75, max_value=1.50, value=1.00, step=0.05)

    st.markdown("---")
    st.markdown("### 🎬 Video Dubbing & Audio Settings")
    burn_subs_pref = st.checkbox(
        "Burn Subtitles on Video",
        value=st.session_state.get("burn_subtitles_pref", False),
        help="Turn OFF (default) so video has NO subtitles on screen. Turn ON only if you want hardcoded subtitles.",
        key="sb_burn_subs",
    )
    st.session_state.burn_subtitles_pref = burn_subs_pref

    st.markdown("##### 🎛️ Audio Controls (Music & Voice)")
    sb_enable_bg_music = st.toggle(
        "🎵 Background Music",
        value=st.session_state.get("enable_bg_music", False),
        key="sb_enable_bg_music",
        help="Turn ON to extract and keep video background music playing behind the dubbed voice. Turn OFF for clean voice-over.",
    )
    if sb_enable_bg_music:
        sb_bg_music_vol = st.slider(
            "Music Volume",
            min_value=0,
            max_value=100,
            value=int(st.session_state.get("bg_music_vol", 20)),
            step=1,
            format="%d%%",
            key="sb_bg_music_vol",
        )
        st.session_state.bg_music_vol = sb_bg_music_vol
    else:
        sb_bg_music_vol = 0
    st.session_state.enable_bg_music = sb_enable_bg_music

    sb_enable_orig_voice = st.toggle(
        "🗣️ Original Voice",
        value=st.session_state.get("enable_orig_voice", False),
        key="sb_enable_orig_voice",
        help="Turn ON to keep original actor/speaker voice softly playing in background (documentary style). Turn OFF to mute original voice.",
    )
    if sb_enable_orig_voice:
        sb_orig_voice_vol = st.slider(
            "Original Voice Volume",
            min_value=0,
            max_value=100,
            value=int(st.session_state.get("orig_voice_vol", 15)),
            step=1,
            format="%d%%",
            key="sb_orig_voice_vol",
        )
        st.session_state.orig_voice_vol = sb_orig_voice_vol
    else:
        sb_orig_voice_vol = 0
    st.session_state.enable_orig_voice = sb_enable_orig_voice

    dub_vol_pref = st.slider(
        "Dubbed Voice-Over Volume",
        min_value=0,
        max_value=150,
        value=int(st.session_state.get("dub_voice_vol", 100)),
        step=5,
        format="%d%%",
        key="sb_dub_vol",
    )
    st.session_state.dub_voice_vol = dub_vol_pref

    orig_vol_pref = max(sb_bg_music_vol, sb_orig_voice_vol) if (sb_enable_bg_music or sb_enable_orig_voice) else 0.0
    st.caption("Engine: FFmpeg (bundled) • Edge Neural TTS • Whisper • Gemini")

# ==========================================
# Main Studio Tabs
# ==========================================
is_admin_user = st.session_state.get("auth_user", "") == "admin"
pending_dict = saved_config.get("pending_users", {})
num_pending = len(pending_dict)

if is_admin_user:
    cust_tab_title = f"05 👥 Customers ({num_pending})" if num_pending > 0 else "05 👥 Customers"
    tab_transcribe, tab_translate, tab_editor_voice, tab_video, tab_customers = st.tabs([
        "01 🎙️ Transcribe",
        "02 🌐 Translate",
        "03 ✏️ Voice & Edit",
        "04 🎬 Video Studio",
        cust_tab_title,
    ])
else:
    tab_transcribe, tab_translate, tab_editor_voice, tab_video = st.tabs([
        "01 🎙️ Transcribe",
        "02 🌐 Translate",
        "03 ✏️ Voice & Edit",
        "04 🎬 Video Studio",
    ])
    tab_customers = None

# ----------------------------------------------------
# TAB 01: Transcribe Media
# ----------------------------------------------------
with tab_transcribe:
    st.markdown(
        """
        <div class="tab-header">
            <h3>Step 1: Automatic Speech-to-Text Transcription</h3>
            <p style="color: #94a3b8; margin: 0;">Upload any video or audio file to generate millimeter-accurate timestamped subtitles.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    col1, col2 = st.columns([1.2, 1], gap="medium")
    
    with col1:
        uploaded_media = st.file_uploader(
            "Upload Audio or Video",
            type=["mp3", "wav", "m4a", "mp4", "mov", "webm", "mkv"],
            help="Supports standard video and audio formats up to 500MB.",
        )
        if uploaded_media:
            input_suffix = Path(uploaded_media.name).suffix.lower()
            if input_suffix not in {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv"}:
                input_suffix = ".mp4"
            save_media_path = STORAGE_DIR / f"uploaded_media{input_suffix}"
            if (
                st.session_state.uploaded_media_path != str(save_media_path.resolve())
                or not save_media_path.exists()
                or save_media_path.stat().st_size != uploaded_media.size
            ):
                save_media_path.write_bytes(uploaded_media.getvalue())
                st.session_state.uploaded_media_path = str(save_media_path.resolve())
                st.session_state.is_video = input_suffix in {".mp4", ".mov", ".webm", ".mkv"}
                st.session_state.detected_voice_info = detect_voice_piseth_sreymom(str(save_media_path.resolve()))

        existing_srt_file = st.file_uploader(
            "Or import an existing SRT subtitle file",
            type=["srt"],
            key="existing_srt_uploader",
        )

        if st.session_state.get("uploaded_media_path") and Path(st.session_state.uploaded_media_path).exists():
            det_v = st.session_state.get("detected_voice_info")
            if not det_v:
                det_v = detect_voice_piseth_sreymom(st.session_state.uploaded_media_path)
                st.session_state.detected_voice_info = det_v
            
            det_c1, det_c2 = st.columns([3, 1])
            with det_c1:
                st.markdown(
                    f"""
                    <div style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 10px; padding: 8px 12px; margin: 4px 0 10px 0;">
                        <span style="font-size: 0.8rem; color: #94a3b8; font-weight: 600;">🎙️ Auto-Detected Voice:</span>
                        <strong style="color: #38bdf8; font-size: 0.92rem; margin-left: 6px;">{det_v.get('icon', '🎙️')} {det_v.get('name', 'Piseth Neural (Male)')}</strong>
                        <span style="font-size: 0.75rem; color: #cbd5e1; margin-left: 6px;">(Pitch: {det_v.get('pitch', 130)} Hz)</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with det_c2:
                if st.button("🔍 Re-detect", key="t1_redetect_voice", help="Re-scan media audio pitch", use_container_width=True):
                    st.session_state.detected_voice_info = detect_voice_piseth_sreymom(st.session_state.uploaded_media_path)
                    st.rerun()
        auto_translate = st.checkbox(
            "⚡ Auto-translate to Khmer immediately when transcription is done",
            value=True,
            help="Automatically translate subtitles to natural Khmer as soon as transcription finishes.",
        )
        auto_voiceover = st.checkbox(
            "🎙️ Auto-generate Voice-Over TTS after translation",
            value=True,
            help=f"Full pipeline: Transcribes -> Auto-translates to Khmer -> Auto-synthesizes voice-over ({tts_engine}).",
        )
        if auto_voiceover:
            st.markdown(
                """
                <div style="background: rgba(30, 41, 59, 0.75); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 10px 14px; margin: 6px 0 8px 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-wrap: wrap; gap: 4px;">
                        <span style="font-weight: 700; color: #f8fafc; font-size: 0.90rem;">🎙️ Select Voice: Auto, Piseth, or Sreymom</span>
                        <span style="font-size: 0.70rem; color: #38bdf8; background: rgba(56, 189, 248, 0.15); padding: 2px 7px; border-radius: 6px; font-weight: 600;">1-Click Buttons</span>
                    </div>
                    <p style="font-size: 0.74rem; color: #94a3b8; margin: 0 0 8px 0;">Tap to select whether to auto-detect speaker pitch (Boy/Girl) or force Piseth or Sreymom.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            t1_cur_voice = st.session_state.get("voice_btn_selection", "🎭 Auto (Piseth 👨 / Sreymom 👩)")
            if t1_cur_voice not in VOICE_BUTTON_OPTIONS:
                t1_cur_voice = "🎭 Auto (Piseth 👨 / Sreymom 👩)"

            t1_voice_choice = st.pills(
                "Voice-Over Speaker",
                options=VOICE_BUTTON_OPTIONS,
                default=t1_cur_voice,
                key="t1_voice_pills",
                label_visibility="collapsed",
            )
            if t1_voice_choice:
                st.session_state.voice_btn_selection = t1_voice_choice
                st.session_state.chosen_voice = VOICE_BUTTON_MAP[t1_voice_choice]

            active_t1_voice = st.session_state.get("chosen_voice", "auto_detect")
            if active_t1_voice == "auto_detect":
                vg = st.session_state.get("voice_gender_counts", {})
                m_c = vg.get("male", 0)
                f_c = vg.get("female", 0)
                if m_c or f_c:
                    st.caption(f"🎭 Auto Character Detection: **{m_c} 👨 Piseth (ប្រុស)** • **{f_c} 👩 Sreymom (ស្រី)**")
                else:
                    det = st.session_state.get("detected_voice_info")
                    if det:
                        st.caption(f"🎯 Default: **{det.get('icon', '🎙️')} {det.get('name', 'Piseth Neural')}** ({det.get('pitch', 130)} Hz)")
                    else:
                        st.caption("🎭 ចាប់សម្លេងតួអង្គស្វ័យប្រវត្តិ (Boy/Male <165Hz ➔ Piseth, Girl/Female ≥165Hz ➔ Sreymom)")
            elif active_t1_voice == "km-KH-PisethNeural":
                st.caption("👨 Active Voice: **Piseth Neural** (Khmer Male Voice / ប្រុស)")
            elif active_t1_voice == "km-KH-SreymomNeural":
                st.caption("👩 Active Voice: **Sreymom Neural** (Khmer Female Voice / ស្រី)")
        auto_video_dub = st.checkbox(
            "🎬 Auto-send to Video Studio & render dubbed video when done",
            value=True,
            help="If a video was uploaded, automatically sends everything to Video Studio and renders hardsubbed MP4 video.",
        )
        
        # Audio Mix Controls (Background Music & Original Voice)
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.65); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 12px 14px; margin: 10px 0 14px 0;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                    <span style="font-weight: 700; font-size: 0.92rem; color: #f8fafc;">🎛️ Audio Controls (Music & Original Voice)</span>
                    <span style="font-size: 0.72rem; color: #38bdf8; background: rgba(56, 189, 248, 0.15); padding: 2px 8px; border-radius: 6px; font-weight: 600;">Dubbing Mix</span>
                </div>
                <p style="font-size: 0.75rem; color: #94a3b8; margin: 0 0 6px 0;">Toggle background music and original dialogue ON or OFF for the rendered video.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_t1_m, col_t1_v = st.columns(2)
        with col_t1_m:
            t1_enable_bg_music = st.toggle(
                "🎵 Background Music",
                value=st.session_state.get("enable_bg_music", False),
                key="t1_enable_bg_music",
                help="Turn ON to extract and keep video background music playing behind the dubbed voice. Turn OFF for clean voice-over.",
            )
            if t1_enable_bg_music:
                t1_bg_music_vol = st.slider(
                    "Music Volume",
                    min_value=0,
                    max_value=100,
                    value=int(st.session_state.get("bg_music_vol", 20)),
                    step=1,
                    format="%d%%",
                    key="t1_bg_music_vol",
                )
                st.session_state.bg_music_vol = t1_bg_music_vol
            else:
                t1_bg_music_vol = 0
            st.session_state.enable_bg_music = t1_enable_bg_music

        with col_t1_v:
            t1_enable_orig_voice = st.toggle(
                "🗣️ Original Voice",
                value=st.session_state.get("enable_orig_voice", False),
                key="t1_enable_orig_voice",
                help="Turn ON to keep original actor/speaker voice softly playing in background (documentary style). Turn OFF to mute original voice.",
            )
            if t1_enable_orig_voice:
                t1_orig_voice_vol = st.slider(
                    "Original Voice Volume",
                    min_value=0,
                    max_value=100,
                    value=int(st.session_state.get("orig_voice_vol", 15)),
                    step=1,
                    format="%d%%",
                    key="t1_orig_voice_vol",
                )
                st.session_state.orig_voice_vol = t1_orig_voice_vol
            else:
                t1_orig_voice_vol = 0
            st.session_state.enable_orig_voice = t1_enable_orig_voice

        col_t1_d, col_t1_s = st.columns([1.2, 1])
        with col_t1_d:
            t1_dub_vol = st.slider(
                "🎙️ Dubbed Voice-Over Volume",
                min_value=0,
                max_value=150,
                value=int(st.session_state.get("dub_voice_vol", 100)),
                step=5,
                format="%d%%",
                key="t1_dub_vol",
            )
            st.session_state.dub_voice_vol = t1_dub_vol
        with col_t1_s:
            t1_burn_subs = st.checkbox(
                "Burn Subtitles on Video",
                value=st.session_state.get("burn_subtitles_pref", False),
                key="t1_burn_subs",
                help="Default: OFF (no subtitles on video). Turn ON to hardcode subtitles.",
            )
            st.session_state.burn_subtitles_pref = t1_burn_subs
        
        btn_create = st.button("🚀 Transcribe Media / Parse SRT", type="primary", use_container_width=True)
        if btn_create:
            try:
                subtitles = None
                if existing_srt_file:
                    st.session_state.source_srt = existing_srt_file.getvalue().decode("utf-8-sig")
                    subtitles = parse_srt(st.session_state.source_srt)
                    if st.session_state.get("uploaded_media_path"):
                        seg_voices = classify_all_segments_piseth_sreymom(subtitles, media_path=st.session_state.uploaded_media_path)
                        if seg_voices:
                            st.session_state.subtitle_voices = {idx: v["voice"] for idx, v in seg_voices.items()}
                            st.session_state.subtitle_voice_details = seg_voices
                            m_count = sum(1 for v in seg_voices.values() if v.get("gender") == "Male")
                            f_count = sum(1 for v in seg_voices.values() if v.get("gender") == "Female")
                            st.session_state.voice_gender_counts = {"male": m_count, "female": f_count}
                    st.success(f"Successfully loaded {len(subtitles)} subtitle segments from SRT!")
                elif uploaded_media:
                    with st.spinner(f"Transcribing media using **{pipeline_model}**..."):
                        if pipeline_model.startswith("openai"):
                            transcribe_key = openai_key
                        elif pipeline_model.startswith("gemini"):
                            transcribe_key = gemini_key
                        else:
                            transcribe_key = ""
                        srt_output = transcribe_media(uploaded_media, pipeline_model, transcribe_key)
                        st.session_state.source_srt = srt_output
                        subtitles = parse_srt(srt_output)
                        st.session_state.detected_voice_info = detect_voice_piseth_sreymom(st.session_state.uploaded_media_path)

                        # Automatically classify character gender (Piseth vs Sreymom) for all segments
                        seg_voices = classify_all_segments_piseth_sreymom(subtitles, media_path=st.session_state.uploaded_media_path)
                        if seg_voices:
                            st.session_state.subtitle_voices = {idx: v["voice"] for idx, v in seg_voices.items()}
                            st.session_state.subtitle_voice_details = seg_voices
                            m_count = sum(1 for v in seg_voices.values() if v.get("gender") == "Male")
                            f_count = sum(1 for v in seg_voices.values() if v.get("gender") == "Female")
                            st.session_state.voice_gender_counts = {"male": m_count, "female": f_count}
                            st.success(f"Transcription complete! Extracted {len(subtitles)} segments.")
                            st.info(f"🎭 **ចាប់សម្លេងតួអង្គបានជោគជ័យ**: {m_count} 👨 Piseth (សម្លេងប្រុស) • {f_count} 👩 Sreymom (សម្លេងស្រី)")
                        else:
                            st.success(f"Transcription complete! Extracted {len(subtitles)} segments.")
                else:
                    st.warning("Please upload a media file or SRT to proceed.")

                if subtitles and auto_translate:
                    with st.spinner("🌐 Auto-translating subtitles to Khmer..."):
                        translated_subs = run_auto_translation(subtitles, source_language, gemini_key, openai_key, pipeline_model)
                        st.session_state.khmer_srt = render_srt(translated_subs)
                        st.success(f"✅ Auto-translated {len(translated_subs)} segments to Khmer!")

                    if auto_voiceover:
                        active_voice_t1 = st.session_state.get("chosen_voice", chosen_voice)
                        counts = st.session_state.get("voice_gender_counts", {})
                        m_c = counts.get("male", 0)
                        f_c = counts.get("female", 0)
                        if active_voice_t1 == "auto_detect":
                            disp_v_t1 = f"Auto Detect (👨 Piseth {m_c} / 👩 Sreymom {f_c})" if (m_c or f_c) else "Auto Detect (Piseth / Sreymom)"
                        elif "Piseth" in active_voice_t1:
                            disp_v_t1 = "Piseth Neural (Boy)"
                        elif "Sreymom" in active_voice_t1:
                            disp_v_t1 = "Sreymom Neural (Girl)"
                        else:
                            disp_v_t1 = active_voice_t1

                        with st.spinner(f"🎙️ Auto-synthesizing voice-over with {tts_engine} ({disp_v_t1})..."):
                            audio_bytes = synthesize_full_audio(
                                translated_subs,
                                tts_engine,
                                active_voice_t1,
                                voice_speed,
                                eleven_key,
                            )
                            st.session_state.dubbed_audio_bytes = audio_bytes
                            st.success("🎧 Voice-over track generated automatically! Ready in Player & Video Studio.")

                        if auto_video_dub and st.session_state.is_video and st.session_state.uploaded_media_path and st.session_state.dubbed_audio_path:
                            with st.spinner("🎬 Sending to Video Studio & rendering dubbed video..."):
                                srt_temp = STORAGE_DIR / "burn_subtitles.srt"
                                srt_temp.write_text(st.session_state.khmer_srt, encoding="utf-8")
                                final_v = process_video_dubbing(
                                    video_path=st.session_state.uploaded_media_path,
                                    audio_path=st.session_state.dubbed_audio_path,
                                    srt_path=str(srt_temp.resolve()) if t1_burn_subs else None,
                                    dub_volume=t1_dub_vol,
                                    burn_subtitles=t1_burn_subs,
                                    enable_bg_music=t1_enable_bg_music,
                                    bg_music_vol=t1_bg_music_vol,
                                    enable_orig_voice=t1_enable_orig_voice,
                                    orig_voice_vol=t1_orig_voice_vol,
                                )
                                st.session_state.output_video_path = final_v
                                st.success("🎉 Video Studio production complete! Dubbed video preview is ready below.")
            except Exception as e:
                st.error(f"Error: {e}")

    with col2:
        if st.session_state.source_srt:
            subs = parse_srt(st.session_state.source_srt)
            duration_sec = (subs[-1].end if subs else 0) / 1000
            
            det_v_col2 = st.session_state.get("detected_voice_info")
            if det_v_col2:
                mc1, mc2, mc3 = st.columns(3)
            else:
                mc1, mc2 = st.columns(2)
                mc3 = None

            with mc1:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{len(subs)}</div><div class="metric-label">Segments</div></div>', unsafe_allow_html=True)
            with mc2:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{duration_sec:.1f}s</div><div class="metric-label">Total Duration</div></div>', unsafe_allow_html=True)
            if mc3 and det_v_col2:
                with mc3:
                    st.markdown(f'<div class="metric-card"><div class="metric-value" style="font-size: 1.1rem;">{det_v_col2.get("icon", "🎙️")} {det_v_col2.get("gender", "Male")}</div><div class="metric-label">{det_v_col2.get("name", "Piseth").split()[0]} ({det_v_col2.get("pitch", 130)} Hz)</div></div>', unsafe_allow_html=True)
            
            if st.session_state.output_video_path and Path(st.session_state.output_video_path).exists():
                st.markdown("#### 🎬 Final Dubbed Video (Video Studio)")
                st.video(st.session_state.output_video_path)
                with open(st.session_state.output_video_path, "rb") as vf:
                    v_bytes_t1 = vf.read()
                st.download_button(
                    "📥 Download Dubbed Video (.MP4)",
                    data=v_bytes_t1,
                    file_name="dubbed_studio_output.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    key="dl_video_tab1",
                )

            if st.session_state.dubbed_audio_bytes:
                st.markdown("#### 🎧 Generated Voice-Over Audio")
                st.audio(st.session_state.dubbed_audio_bytes, format="audio/wav")
                st.download_button(
                    "📥 Download Voice-Over (WAV)",
                    data=st.session_state.dubbed_audio_bytes,
                    file_name="dubbed_voiceover.wav",
                    mime="audio/wav",
                    use_container_width=True,
                    key="dl_voiceover_tab1",
                )

            if st.session_state.khmer_srt:
                p_tab1, p_tab2 = st.tabs(["🇰🇭 Khmer Subtitles (Auto-Ready)", "📄 Source Subtitles"])
                with p_tab1:
                    st.markdown(f'<div class="srt-box">{escape(st.session_state.khmer_srt[:3000])}</div>', unsafe_allow_html=True)
                    st.download_button(
                        "📥 Download Khmer SRT",
                        data=st.session_state.khmer_srt,
                        file_name="khmer_subtitles.srt",
                        mime="application/x-subrip",
                        use_container_width=True,
                        key="dl_khmer_srt_tab1_ready",
                    )
                with p_tab2:
                    st.markdown(f'<div class="srt-box">{escape(st.session_state.source_srt[:3000])}</div>', unsafe_allow_html=True)
                    st.download_button(
                        "📥 Download Source SRT",
                        data=st.session_state.source_srt,
                        file_name="source_subtitles.srt",
                        mime="application/x-subrip",
                        use_container_width=True,
                        key="dl_source_srt_tab1_ready",
                    )
            else:
                st.markdown("#### Source Subtitles Preview")
                st.markdown(f'<div class="srt-box">{escape(st.session_state.source_srt[:3000])}</div>', unsafe_allow_html=True)
                st.download_button(
                    "📥 Download Source SRT",
                    data=st.session_state.source_srt,
                    file_name="source_subtitles.srt",
                    mime="application/x-subrip",
                    use_container_width=True,
                    key="dl_source_srt_tab1_only",
                )
        else:
            st.info("Uploaded subtitles and segments will appear here after transcription.")

# ----------------------------------------------------
# TAB 02: Khmer Translation
# ----------------------------------------------------
with tab_translate:
    st.markdown(
        """
        <div class="tab-header">
            <h3>Step 2: Translate Subtitles to Natural Khmer</h3>
            <p style="color: #94a3b8; margin: 0;">Preserves exact start and end timestamps while translating tone, idiom, and context.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    if not st.session_state.source_srt:
        st.info("⚠️ Please complete Step 1 (Transcribe Media) first.")
    else:
        t_col1, t_col2 = st.columns([1.2, 1], gap="medium")
        
        with t_col1:
            trans_mode = st.radio(
                "Translation Engine",
                ["Auto (Gemini with OpenAI Fallback)", "Google Gemini API", "OpenAI (GPT-4o Mini)", "Manual Paste"],
                horizontal=False,
            )
            
            manual_text = ""
            if trans_mode == "Manual Paste":
                manual_text = st.text_area(
                    "Paste Khmer Translation (1 line per subtitle segment)",
                    height=200,
                    placeholder="Enter translated lines matching source subtitle order...",
                )

            auto_voiceover_t2 = st.checkbox(
                "🎙️ Auto-generate Voice-Over TTS immediately when translation is done",
                value=True,
                help=f"Automatically synthesizes full synchronized audio using {tts_engine} ({chosen_voice}) once Khmer subtitles are generated.",
            )
            auto_video_dub_t2 = st.checkbox(
                "🎬 Auto-send to Video Studio & render dubbed video when done",
                value=True,
                help="Automatically sends subtitles and voice-over to Video Studio to render MP4 video.",
            )
            
            btn_translate = st.button("🌐 Translate to Khmer", type="primary", use_container_width=True)
            if btn_translate:
                try:
                    source_subs = parse_srt(st.session_state.source_srt)
                    
                    if trans_mode == "Manual Paste":
                        lines = [ln.strip() for ln in manual_text.splitlines() if ln.strip()]
                        if len(lines) != len(source_subs):
                            raise ValueError(f"Expected {len(source_subs)} lines, but received {len(lines)}.")
                        translated_subs = [Subtitle(s.index, s.start, s.end, ln) for s, ln in zip(source_subs, lines)]
                    elif trans_mode == "Google Gemini API":
                        with st.spinner("Translating with Gemini..."):
                            g_model = pipeline_model if pipeline_model.startswith("gemini-") else "gemini-3.5-flash"
                            translated_subs = translate_subtitles_with_gemini(source_subs, source_language, gemini_key, g_model)
                    elif trans_mode == "OpenAI (GPT-4o Mini)":
                        with st.spinner("Translating with GPT-4o Mini..."):
                            translated_subs = translate_subtitles_with_openai(source_subs, source_language, openai_key)
                    else:  # Auto
                        with st.spinner("Translating via Gemini with automatic fallback..."):
                            translated_subs = run_auto_translation(source_subs, source_language, gemini_key, openai_key, pipeline_model)
                    
                    st.session_state.khmer_srt = render_srt(translated_subs)
                    st.success("Translation complete!")

                    # Ensure character voice classification is populated
                    if not st.session_state.get("subtitle_voices") and st.session_state.get("uploaded_media_path"):
                        seg_v = classify_all_segments_piseth_sreymom(translated_subs, media_path=st.session_state.uploaded_media_path)
                        if seg_v:
                            st.session_state.subtitle_voices = {idx: v["voice"] for idx, v in seg_v.items()}
                            st.session_state.subtitle_voice_details = seg_v
                            m_count = sum(1 for v in seg_v.values() if v.get("gender") == "Male")
                            f_count = sum(1 for v in seg_v.values() if v.get("gender") == "Female")
                            st.session_state.voice_gender_counts = {"male": m_count, "female": f_count}

                    if auto_voiceover_t2:
                        active_v2 = st.session_state.get("chosen_voice", chosen_voice)
                        counts_t2 = st.session_state.get("voice_gender_counts", {})
                        m_t2 = counts_t2.get("male", 0)
                        f_t2 = counts_t2.get("female", 0)
                        if active_v2 == "auto_detect":
                            disp_v2 = f"Auto Detect (👨 Piseth {m_t2} / 👩 Sreymom {f_t2})" if (m_t2 or f_t2) else "Auto Detect (Piseth / Sreymom)"
                        elif "Piseth" in active_v2:
                            disp_v2 = "Piseth Neural (Boy)"
                        elif "Sreymom" in active_v2:
                            disp_v2 = "Sreymom Neural (Girl)"
                        else:
                            disp_v2 = active_v2

                        with st.spinner(f"🎙️ Auto-synthesizing voice-over using {tts_engine} ({disp_v2})..."):
                            audio_bytes = synthesize_full_audio(
                                translated_subs,
                                tts_engine,
                                active_v2,
                                voice_speed,
                                eleven_key,
                            )
                            st.session_state.dubbed_audio_bytes = audio_bytes
                            st.success("✅ Voice-over generated automatically! You can preview it on the right.")

                        if auto_video_dub_t2 and st.session_state.is_video and st.session_state.uploaded_media_path and st.session_state.dubbed_audio_path:
                            with st.spinner("🎬 Sending to Video Studio & rendering dubbed video..."):
                                srt_temp = STORAGE_DIR / "burn_subtitles.srt"
                                srt_temp.write_text(st.session_state.khmer_srt, encoding="utf-8")
                                final_v = process_video_dubbing(
                                    video_path=st.session_state.uploaded_media_path,
                                    audio_path=st.session_state.dubbed_audio_path,
                                    srt_path=str(srt_temp.resolve()) if st.session_state.get("burn_subtitles_pref", False) else None,
                                    dub_volume=float(st.session_state.get("dub_voice_vol", 1.00)),
                                    burn_subtitles=st.session_state.get("burn_subtitles_pref", False),
                                    enable_bg_music=st.session_state.get("enable_bg_music", False),
                                    bg_music_vol=float(st.session_state.get("bg_music_vol", 0.20)),
                                    enable_orig_voice=st.session_state.get("enable_orig_voice", False),
                                    orig_voice_vol=float(st.session_state.get("orig_voice_vol", 0.15)),
                                )
                                st.session_state.output_video_path = final_v
                                st.success("🎉 Video Studio production complete! Dubbed video preview is ready on the right.")
                except Exception as e:
                    st.error(f"Translation Error: {e}")

        with t_col2:
            if st.session_state.output_video_path and Path(st.session_state.output_video_path).exists():
                st.markdown("#### 🎬 Final Dubbed Video (Video Studio)")
                st.video(st.session_state.output_video_path)
                with open(st.session_state.output_video_path, "rb") as vf:
                    v_bytes_t2 = vf.read()
                st.download_button(
                    "📥 Download Dubbed Video (.MP4)",
                    data=v_bytes_t2,
                    file_name="dubbed_studio_output.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    key="dl_video_tab2",
                )

            if st.session_state.dubbed_audio_bytes:
                st.markdown("#### 🎧 Generated Voice-Over Audio")
                st.audio(st.session_state.dubbed_audio_bytes, format="audio/wav")
                st.download_button(
                    "📥 Download Voice-Over (WAV)",
                    data=st.session_state.dubbed_audio_bytes,
                    file_name="dubbed_voiceover.wav",
                    mime="audio/wav",
                    use_container_width=True,
                    key="dl_voiceover_tab2",
                )

            if st.session_state.khmer_srt:
                k_subs = parse_srt(st.session_state.khmer_srt)
                st.markdown(f'<div class="metric-card"><div class="metric-value">{len(k_subs)}</div><div class="metric-label">Khmer Segments Ready</div></div>', unsafe_allow_html=True)
                st.markdown("#### Translated Khmer SRT Preview")
                st.markdown(f'<div class="srt-box">{escape(st.session_state.khmer_srt[:3000])}</div>', unsafe_allow_html=True)
                st.download_button(
                    "📥 Download Khmer SRT",
                    data=st.session_state.khmer_srt,
                    file_name="khmer_subtitles.srt",
                    mime="application/x-subrip",
                    use_container_width=True,
                    key="dl_khmer_srt_tab2",
                )
            else:
                st.info("Translated Khmer subtitles will appear here.")

# ----------------------------------------------------
# TAB 03: Interactive Editor & Voice-over
# ----------------------------------------------------
with tab_editor_voice:
    st.markdown(
        """
        <div class="tab-header">
            <h3>Step 3: Timeline Subtitle Editor & Voice Synthesis</h3>
            <p style="color: #94a3b8; margin: 0;">Review, modify translations, audition individual lines, and generate full synchronized voice-overs.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    active_srt = st.session_state.khmer_srt or st.session_state.source_srt
    if not active_srt:
        st.info("⚠️ Please transcribe or translate subtitles first.")
    else:
        subs_list = parse_srt(active_srt)
        source_subs = parse_srt(st.session_state.source_srt) if st.session_state.source_srt else subs_list

        # Automatically detect character voices if not yet populated
        if not st.session_state.get("subtitle_voices") and st.session_state.get("uploaded_media_path") and Path(st.session_state.uploaded_media_path).exists():
            auto_segs = classify_all_segments_piseth_sreymom(subs_list, media_path=st.session_state.uploaded_media_path)
            if auto_segs:
                st.session_state.subtitle_voices = {idx: v["voice"] for idx, v in auto_segs.items()}
                st.session_state.subtitle_voice_details = auto_segs
                m_c = sum(1 for v in auto_segs.values() if v.get("gender") == "Male")
                f_c = sum(1 for v in auto_segs.values() if v.get("gender") == "Female")
                st.session_state.voice_gender_counts = {"male": m_c, "female": f_c}

        st.markdown("#### 📝 Subtitle Translation & Audio Editor")

        # Speaker Voice Assignment Toolbar
        sub_v_dict = st.session_state.get("subtitle_voices", {})
        m_c = sum(1 for v in sub_v_dict.values() if "Piseth" in v)
        f_c = sum(1 for v in sub_v_dict.values() if "Sreymom" in v)

        st.markdown(
            f"""
            <div style="background: rgba(30, 41, 59, 0.75); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 10px 14px; margin: 10px 0 12px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                    <span style="font-weight: 700; color: #f8fafc; font-size: 0.92rem;">🎭 ការបែងចែកសម្លេងតួអង្គ (Character Voice: Piseth 👨 / Sreymom 👩)</span>
                    <span style="font-size: 0.75rem; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 3px 10px; border-radius: 8px; font-weight: 600;">
                        👨 Piseth: {m_c} ឃ្លា • 👩 Sreymom: {f_c} ឃ្លា
                    </span>
                </div>
                <p style="font-size: 0.76rem; color: #94a3b8; margin: 4px 0 0 0;">ប្រព័ន្ធចាប់សម្លេងតួអង្គស្វ័យប្រវត្តិតាមរយៈកម្រិត Pitch នៃឃ្លានីមួយៗ (សម្លេងប្រុស ➔ Piseth 👨, សម្លេងស្រី ➔ Sreymom 👩)។</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        v_col1, v_col2, v_col3, v_col4 = st.columns([1.3, 1, 1, 0.8], gap="small")
        with v_col1:
            if st.button("🎭 ចាប់សម្លេងឡើងវិញ", type="secondary", use_container_width=True, help="វិភាគរលកសម្លេងសម្រាប់គ្រប់ឃ្លាដើម្បីកំណត់ Piseth (ប្រុស) ឬ Sreymom (ស្រី)"):
                if not st.session_state.uploaded_media_path or not Path(st.session_state.uploaded_media_path).exists():
                    st.warning("No media file available to analyze per-line pitch. Please upload media in Tab 01.")
                else:
                    with st.spinner("កំពុងចាប់សម្លេងតួអង្គគ្រប់ឃ្លាទាំងអស់..."):
                        try:
                            seg_v = classify_all_segments_piseth_sreymom(subs_list, media_path=st.session_state.uploaded_media_path)
                            if seg_v:
                                st.session_state.subtitle_voices = {idx: v["voice"] for idx, v in seg_v.items()}
                                st.session_state.subtitle_voice_details = seg_v
                                m_count = sum(1 for v in seg_v.values() if v.get("gender") == "Male")
                                f_count = sum(1 for v in seg_v.values() if v.get("gender") == "Female")
                                st.session_state.voice_gender_counts = {"male": m_count, "female": f_count}
                                st.success(f"✅ ចាប់សម្លេងតួអង្គបានជោគជ័យ: {m_count} 👨 Piseth (ប្រុស) • {f_count} 👩 Sreymom (ស្រី)")
                                st.rerun()
                        except Exception as err:
                            st.error(f"Voice auto-assignment failed: {err}")
        with v_col2:
            if st.button("👨 All Piseth", use_container_width=True, help="Set all dialogue lines to Piseth Neural (Boy/Male)"):
                st.session_state.subtitle_voices = {sub.index: "km-KH-PisethNeural" for sub in subs_list}
                st.toast("Set all lines to 👨 Piseth Neural!", icon="👨")
                st.rerun()
        with v_col3:
            if st.button("👩 All Sreymom", use_container_width=True, help="Set all dialogue lines to Sreymom Neural (Girl/Female)"):
                st.session_state.subtitle_voices = {sub.index: "km-KH-SreymomNeural" for sub in subs_list}
                st.toast("Set all lines to 👩 Sreymom Neural!", icon="👩")
                st.rerun()
        with v_col4:
            if st.button("🔄 Reset", use_container_width=True, help="Reset all lines to global default"):
                st.session_state.subtitle_voices = {}
                st.toast("Reset all line voices to global default.", icon="🔄")
                st.rerun()

        editor_mode = st.radio(
            "Editor Layout Mode",
            ["📱 Mobile Card Editor", "💻 Desktop Table Editor"],
            horizontal=True,
            help="Mobile Card Editor provides large touch-friendly inputs for phone screens. Desktop Table Editor provides a spreadsheet view.",
        )

        if editor_mode == "📱 Mobile Card Editor":
            total_segs = len(subs_list)
            if "card_seg_idx" not in st.session_state:
                st.session_state.card_seg_idx = 0
            if st.session_state.card_seg_idx >= total_segs:
                st.session_state.card_seg_idx = max(0, total_segs - 1)

            cur_idx = st.session_state.card_seg_idx
            cur_sub = subs_list[cur_idx]
            cur_src = source_subs[cur_idx].text if cur_idx < len(source_subs) else ""

            # Mobile Navigation Toolbar
            nav_col1, nav_col2, nav_col3 = st.columns([1, 2.2, 1], gap="small")
            with nav_col1:
                if st.button("◀ Prev", disabled=(cur_idx == 0), use_container_width=True):
                    st.session_state.card_seg_idx = max(0, cur_idx - 1)
                    st.rerun()
            with nav_col2:
                selected_option = st.selectbox(
                    "Jump to Segment",
                    options=range(total_segs),
                    index=cur_idx,
                    format_func=lambda x: f"Segment #{x+1} of {total_segs}",
                    label_visibility="collapsed",
                    key="mobile_card_seg_select",
                )
                if selected_option != cur_idx:
                    st.session_state.card_seg_idx = selected_option
                    st.rerun()
            with nav_col3:
                if st.button("Next ▶", disabled=(cur_idx >= total_segs - 1), use_container_width=True):
                    st.session_state.card_seg_idx = min(total_segs - 1, cur_idx + 1)
                    st.rerun()

            # Mobile Card Presentation
            start_str = format_timestamp(cur_sub.start)
            end_str = format_timestamp(cur_sub.end)
            dur_sec = (cur_sub.end - cur_sub.start) / 1000

            st.markdown(
                f"""
                <div class="mobile-card-editor">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap; gap: 6px;">
                        <span style="font-weight: 700; color: #38bdf8; font-size: 1rem;">Segment #{cur_idx + 1} of {total_segs}</span>
                        <span class="badge-time">⏱️ {start_str} ➔ {end_str} ({dur_sec:.2f}s)</span>
                    </div>
                    <div style="font-size: 0.78rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em;">Original Source Text</div>
                    <div class="source-preview">{escape(cur_src) if cur_src else '<em style="color:#64748b">No source text</em>'}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Segment Voice Selector
            sub_voices = st.session_state.get("subtitle_voices", {})
            cur_line_voice = sub_voices.get(cur_sub.index, "")
            if not cur_line_voice:
                cur_line_voice = det_v_tab3.get("voice", "km-KH-PisethNeural")

            v_options = {
                "👨 Piseth (ប្រុស / Boy)": "km-KH-PisethNeural",
                "👩 Sreymom (ស្រី / Girl)": "km-KH-SreymomNeural",
            }
            inv_v = {v: k for k, v in v_options.items()}
            cur_label = inv_v.get(cur_line_voice, "👨 Piseth (ប្រុស / Boy)")

            st.caption("Voice for this Segment:")
            chosen_card_voice_label = st.pills(
                "Speaker Voice for Segment",
                options=list(v_options.keys()),
                default=cur_label,
                key=f"card_voice_pills_{cur_idx}",
                label_visibility="collapsed",
            )
            if not chosen_card_voice_label:
                chosen_card_voice_label = cur_label
            chosen_card_voice = v_options[chosen_card_voice_label]

            edited_khmer_text = st.text_area(
                "Dubbed (Khmer) Text",
                value=cur_sub.text,
                key=f"card_text_input_{cur_idx}",
                height=110,
                help="Type or adjust the Khmer translated text. Uses Kantumruy Pro font with high-contrast line height.",
            )

            act_col1, act_col2 = st.columns([1.2, 1], gap="small")
            with act_col1:
                if st.button(f"💾 Save Segment #{cur_idx + 1}", type="primary", use_container_width=True):
                    subs_list[cur_idx].text = edited_khmer_text.strip()
                    st.session_state.setdefault("subtitle_voices", {})[cur_sub.index] = chosen_card_voice
                    st.session_state.khmer_srt = render_srt(subs_list)
                    st.toast(f"✅ Segment #{cur_idx + 1} saved ({chosen_card_voice_label.split()[1]})!", icon="💾")
                    if cur_idx < total_segs - 1:
                        st.session_state.card_seg_idx = cur_idx + 1
                    st.rerun()

            with act_col2:
                if st.button("🔊 Audition Line", use_container_width=True):
                    try:
                        audition_bytes = synthesize_single_line(edited_khmer_text, tts_engine, chosen_card_voice, voice_speed, eleven_key)
                        st.audio(audition_bytes, format="audio/wav")
                        st.caption(f"Line #{cur_idx + 1} synthesized with {tts_engine} ({chosen_card_voice_label})")
                    except Exception as err:
                        st.error(f"Audition failed: {err}")

        else:
            # Desktop Spreadsheet Table View
            st.caption("You can edit the 'Dubbed Text' and 'Speaker Voice' directly in the table below, then click 'Apply Edits'.")

            # Build DataFrame with Voice column
            table_data_desktop = []
            sub_voices = st.session_state.get("subtitle_voices", {})
            for i, sub in enumerate(subs_list):
                src_text = source_subs[i].text if i < len(source_subs) else ""
                assigned_v = sub_voices.get(sub.index, "")
                if not assigned_v:
                    assigned_v = det_v_tab3.get("voice", "km-KH-PisethNeural")
                v_disp = "👩 Sreymom Neural (Female)" if "Sreymom" in assigned_v else "👨 Piseth Neural (Male)"
                table_data_desktop.append({
                    "Index": sub.index,
                    "Start": format_timestamp(sub.start),
                    "End": format_timestamp(sub.end),
                    "Source Text": src_text,
                    "Dubbed Text": sub.text,
                    "Speaker Voice": v_disp,
                })

            df_desktop = pd.DataFrame(table_data_desktop)

            edited_df = st.data_editor(
                df_desktop,
                column_config={
                    "Index": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "Start": st.column_config.TextColumn("Start Time", width="small"),
                    "End": st.column_config.TextColumn("End Time", width="small"),
                    "Source Text": st.column_config.TextColumn("Original Source", disabled=True),
                    "Dubbed Text": st.column_config.TextColumn("Dubbed (Khmer) Text", width="large"),
                    "Speaker Voice": st.column_config.SelectboxColumn(
                        "Speaker Voice",
                        options=["👨 Piseth Neural (Male)", "👩 Sreymom Neural (Female)"],
                        required=True,
                        width="medium",
                    ),
                },
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
            )

            c_apply, c_audition = st.columns([1, 1], gap="medium")
            with c_apply:
                if st.button("💾 Apply Subtitle Edits", use_container_width=True):
                    updated_subtitles = []
                    if "subtitle_voices" not in st.session_state:
                        st.session_state.subtitle_voices = {}
                    for _, row in edited_df.iterrows():
                        sub_id = int(row["Index"])
                        updated_subtitles.append(
                            Subtitle(
                                index=sub_id,
                                start=parse_timestamp(row["Start"]),
                                end=parse_timestamp(row["End"]),
                                text=str(row["Dubbed Text"]).strip(),
                            )
                        )
                        r_voice = str(row.get("Speaker Voice", ""))
                        st.session_state.subtitle_voices[sub_id] = "km-KH-SreymomNeural" if "Sreymom" in r_voice else "km-KH-PisethNeural"
                    st.session_state.khmer_srt = render_srt(updated_subtitles)
                    st.success("Subtitle edits and voice assignments saved successfully!")
                    st.rerun()

            with c_audition:
                audition_idx = st.selectbox(
                    "Audition / Test Single Line Speech",
                    options=range(len(subs_list)),
                    format_func=lambda x: f"Line #{x+1}: {subs_list[x].text[:45]}...",
                )
                if st.button("🔊 Audition Line Now", use_container_width=True):
                    target_text = subs_list[audition_idx].text
                    sub_idx = subs_list[audition_idx].index
                    desktop_line_voice = st.session_state.get("subtitle_voices", {}).get(sub_idx, chosen_voice)
                    try:
                        audition_bytes = synthesize_single_line(target_text, tts_engine, desktop_line_voice, voice_speed, eleven_key)
                        st.audio(audition_bytes, format="audio/wav")
                        st.caption(f"Line #{audition_idx+1} synthesized with {tts_engine} ({desktop_line_voice})")
                    except Exception as err:
                        st.error(f"Audition failed: {err}")

        st.markdown("---")
        st.markdown("#### 🎙️ Synthesize Complete Voice-Over Track")
        disp_v_t3 = chosen_voice
        if chosen_voice == "auto_detect":
            vg = st.session_state.get("voice_gender_counts", {})
            m_t3 = vg.get("male", 0)
            f_t3 = vg.get("female", 0)
            disp_v_t3 = f"Auto Detect (👨 Piseth {m_t3} / 👩 Sreymom {f_t3})" if (m_t3 or f_t3) else "Auto Detect (Piseth / Sreymom)"
        elif "Piseth" in chosen_voice:
            disp_v_t3 = "Piseth Neural (Boy)"
        elif "Sreymom" in chosen_voice:
            disp_v_t3 = "Sreymom Neural (Girl)"

        custom_voice_count = len(st.session_state.get("subtitle_voices", {}))
        voice_note = f"Voice: **{disp_v_t3}**" + (f" ({custom_voice_count} lines assigned)" if custom_voice_count else "")
        st.caption(f"Engine: **{tts_engine}** • {voice_note} • Speed: **{voice_speed}x**")
        
        btn_synth = st.button("⚡ Generate Full Synchronized Voice-Over Track", type="primary", use_container_width=True)
        if btn_synth:
            try:
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                
                def on_progress(current, total, tag=""):
                    progress_bar.progress(current / total)
                    extra = f" ({tag})" if tag else ""
                    status_text.text(f"កំពុងបង្កើតសម្លេងឃ្លាទី {current} នៃ {total}{extra}...")

                audio_bytes = synthesize_full_audio(
                    subs_list,
                    tts_engine,
                    chosen_voice,
                    voice_speed,
                    eleven_key,
                    progress_callback=on_progress,
                )
                st.session_state.dubbed_audio_bytes = audio_bytes
                status_text.text("Synthesis complete!")
                st.success("Full voice-over track generated!")
            except Exception as e:
                st.error(f"Synthesis failed: {e}")

        if st.session_state.dubbed_audio_bytes:
            st.markdown("##### 🎧 Preview Full Audio Track")
            st.audio(st.session_state.dubbed_audio_bytes, format="audio/wav")
            st.download_button(
                "📥 Download Full Voice-Over (WAV)",
                data=st.session_state.dubbed_audio_bytes,
                file_name="dubbed_voiceover.wav",
                mime="audio/wav",
                use_container_width=True,
                key="dl_voiceover_tab3",
            )

# ----------------------------------------------------
# TAB 04: Video Studio & Dubbing
# ----------------------------------------------------
with tab_video:
    st.markdown(
        """
        <div class="tab-header">
            <h3>Step 4: Video Studio — Hardsub Burning & Audio Dubbing</h3>
            <p style="color: #94a3b8; margin: 0;">Export high-definition MP4 videos with burned-in subtitles and dubbed Khmer audio tracks.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    v_col1, v_col2 = st.columns([1.2, 1], gap="medium")
    
    with v_col1:
        # Determine source video
        default_video_path = st.session_state.uploaded_media_path if st.session_state.is_video else ""
        if default_video_path and Path(default_video_path).exists():
            st.success(f"Detected video from Step 1: `{Path(default_video_path).name}`")
            video_to_use = default_video_path
        else:
            custom_video = st.file_uploader("Upload Target Video for Dubbing", type=["mp4", "mov", "webm", "mkv"], key="custom_video_uploader")
            if custom_video:
                save_path = STORAGE_DIR / f"target_video{Path(custom_video.name).suffix}"
                save_path.write_bytes(custom_video.getvalue())
                video_to_use = str(save_path.resolve())
            else:
                video_to_use = ""

        st.markdown("#### 🛠️ Dubbing & Audio Settings")
        
        burn_subs = st.checkbox(
            "Burn Subtitles into Video (Hardsub)",
            value=st.session_state.get("burn_subtitles_pref", False),
            key="t4_burn_subs",
            help="Turn OFF (default) to keep video clean with NO subtitles on screen. Turn ON to hardcode subtitles.",
        )
        st.session_state.burn_subtitles_pref = burn_subs

        if burn_subs:
            subtitle_source = st.radio(
                "Subtitles to Burn",
                ["Khmer Subtitles", "Original Source Subtitles"],
                horizontal=True,
            )
        else:
            subtitle_source = "Khmer Subtitles"
        
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.65); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 12px 14px; margin: 10px 0 14px 0;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                    <span style="font-weight: 700; font-size: 0.92rem; color: #f8fafc;">🎛️ Audio Controls (Music & Original Voice)</span>
                    <span style="font-size: 0.72rem; color: #38bdf8; background: rgba(56, 189, 248, 0.15); padding: 2px 8px; border-radius: 6px; font-weight: 600;">Dubbing Mix</span>
                </div>
                <p style="font-size: 0.75rem; color: #94a3b8; margin: 0 0 6px 0;">Turn ON or OFF background music and original actor dialogue independently.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_t4_m, col_t4_v = st.columns(2)
        with col_t4_m:
            t4_enable_bg_music = st.toggle(
                "🎵 Background Music",
                value=st.session_state.get("enable_bg_music", False),
                key="t4_enable_bg_music",
                help="Turn ON to extract and keep background music playing behind the dubbed voice. Turn OFF for clean voice-over.",
            )
            if t4_enable_bg_music:
                t4_bg_music_vol = st.slider(
                    "Music Volume",
                    min_value=0,
                    max_value=100,
                    value=int(st.session_state.get("bg_music_vol", 20)),
                    step=1,
                    format="%d%%",
                    key="t4_bg_music_vol",
                )
                st.session_state.bg_music_vol = t4_bg_music_vol
            else:
                t4_bg_music_vol = 0
            st.session_state.enable_bg_music = t4_enable_bg_music

        with col_t4_v:
            t4_enable_orig_voice = st.toggle(
                "🗣️ Original Voice",
                value=st.session_state.get("enable_orig_voice", False),
                key="t4_enable_orig_voice",
                help="Turn ON to keep original actor/speaker voice softly playing in background (documentary style). Turn OFF to mute original voice.",
            )
            if t4_enable_orig_voice:
                t4_orig_voice_vol = st.slider(
                    "Original Voice Volume",
                    min_value=0,
                    max_value=100,
                    value=int(st.session_state.get("orig_voice_vol", 15)),
                    step=1,
                    format="%d%%",
                    key="t4_orig_voice_vol",
                )
                st.session_state.orig_voice_vol = t4_orig_voice_vol
            else:
                t4_orig_voice_vol = 0
            st.session_state.enable_orig_voice = t4_enable_orig_voice

        dub_vol_t4 = st.slider(
            "🎙️ Dubbed Voice-Over Volume",
            min_value=0,
            max_value=150,
            value=int(st.session_state.get("dub_voice_vol", 100)),
            step=5,
            format="%d%%",
            key="t4_dub_vol",
            help="Set to 0% if you only want the video's original audio track without voice-over.",
        )
        st.session_state.dub_voice_vol = dub_vol_t4

        btn_render_video = st.button("🎬 Render & Export Final Dubbed Video", type="primary", use_container_width=True)
        if btn_render_video:
            if not video_to_use or not Path(video_to_use).exists():
                st.error("Please provide a valid video file.")
            else:
                # Prepare SRT file
                selected_srt_content = st.session_state.khmer_srt if subtitle_source == "Khmer Subtitles" else st.session_state.source_srt
                if burn_subs and not selected_srt_content:
                    st.error("No subtitles available to burn. Please complete Step 1 or 2.")
                else:
                    srt_temp = STORAGE_DIR / "burn_subtitles.srt"
                    if selected_srt_content:
                        srt_temp.write_text(selected_srt_content, encoding="utf-8")
                    
                    # Prepare audio file
                    audio_for_video = st.session_state.dubbed_audio_path if st.session_state.dubbed_audio_path and Path(st.session_state.dubbed_audio_path).exists() else None
                    if dub_vol_t4 > 0 and not audio_for_video:
                        st.warning("No voice-over audio track found. Please generate audio in Step 3 first, or turn on Background Music / Original Voice.")
                    else:
                        with st.spinner("Processing video with FFmpeg (encoding H.264 & AAC)..."):
                            try:
                                final_video_path = process_video_dubbing(
                                    video_path=video_to_use,
                                    audio_path=audio_for_video,
                                    srt_path=str(srt_temp.resolve()) if burn_subs else None,
                                    dub_volume=dub_vol_t4,
                                    burn_subtitles=burn_subs,
                                    enable_bg_music=t4_enable_bg_music,
                                    bg_music_vol=t4_bg_music_vol,
                                    enable_orig_voice=t4_enable_orig_voice,
                                    orig_voice_vol=t4_orig_voice_vol,
                                )
                                st.session_state.output_video_path = final_video_path
                                st.success("Video rendering complete!")
                            except Exception as video_err:
                                st.error(f"Video rendering failed: {video_err}")

    with v_col2:
        if st.session_state.output_video_path and Path(st.session_state.output_video_path).exists():
            v_size_mb = Path(st.session_state.output_video_path).stat().st_size / (1024 * 1024)
            st.markdown(f'<div class="metric-card"><div class="metric-value">{v_size_mb:.2f} MB</div><div class="metric-label">Dubbed Video Size</div></div>', unsafe_allow_html=True)
            st.markdown("#### 📺 Video Preview")
            st.video(st.session_state.output_video_path)
            
            with open(st.session_state.output_video_path, "rb") as vf:
                video_data = vf.read()
            st.download_button(
                "📥 Download Dubbed Video (.MP4)",
                data=video_data,
                file_name="dubbed_studio_output.mp4",
                mime="video/mp4",
                use_container_width=True,
                key="dl_video_tab4",
            )
        else:
            st.info("The rendered video player and download link will appear here.")

# ----------------------------------------------------
# TAB 05: Customer Registration Management & Count Data
# ----------------------------------------------------
if is_admin_user and tab_customers is not None:
    with tab_customers:
        st.markdown(
            """
            <div class="tab-header">
                <h3>👥 Customer Registration Management & Analytics</h3>
                <p style="color: #94a3b8; margin: 0;">Review and approve customer registrations, monitor customer count data, and manage studio access.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        cfg_now = load_saved_config()
        all_auth_users = cfg_now.get("auth_users", {})
        all_pending_users = cfg_now.get("pending_users", {})

        total_accounts = len(all_auth_users) + len(all_pending_users)
        cnt_pending = len(all_pending_users)
        cnt_approved = sum(1 for u, info in all_auth_users.items() if not (u == "admin" or (isinstance(info, dict) and info.get("role") == "admin")))
        cnt_admins = sum(1 for u, info in all_auth_users.items() if u == "admin" or (isinstance(info, dict) and info.get("role") == "admin"))

        # Real-Time KPI Metric Cards (Count Data)
        kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)
        with kpi_c1:
            st.markdown(
                f"""
                <div class="kpi-card total">
                    <div class="kpi-value" style="color: #38bdf8;">{total_accounts}</div>
                    <div class="kpi-label">📊 Total Registrations</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with kpi_c2:
            pend_color = "#f59e0b" if cnt_pending > 0 else "#64748b"
            st.markdown(
                f"""
                <div class="kpi-card pending">
                    <div class="kpi-value" style="color: {pend_color};">{cnt_pending}</div>
                    <div class="kpi-label">⏳ Pending Approvals</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with kpi_c3:
            st.markdown(
                f"""
                <div class="kpi-card approved">
                    <div class="kpi-value" style="color: #34d399;">{cnt_approved}</div>
                    <div class="kpi-label">✅ Active Customers</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with kpi_c4:
            st.markdown(
                f"""
                <div class="kpi-card admin">
                    <div class="kpi-value" style="color: #c084fc;">{cnt_admins}</div>
                    <div class="kpi-label">🛡️ Administrators</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if total_accounts > 0:
            pct_active = int(round((cnt_approved + cnt_admins) / total_accounts * 100))
            st.caption(f"Studio Activation Ratio: **{pct_active}%** ({cnt_approved + cnt_admins} active / {total_accounts} registered accounts)")
            st.progress((cnt_approved + cnt_admins) / total_accounts)

        st.markdown("---")

        # Search, Filter and Batch Action Bar
        ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([1.8, 1.2, 1.2], gap="small")
        with ctrl_c1:
            cust_search = st.text_input("🔍 Search Customers", placeholder="Search by username, name, or phone...", key="tab5_search_inp").strip()
        with ctrl_c2:
            filter_opts = ["All Accounts", f"⏳ Pending Approvals ({cnt_pending})", f"✅ Active Customers ({cnt_approved})", "🛡️ Admins"]
            status_filter = st.selectbox("Status Filter", filter_opts, index=0, key="tab5_status_filter")
        with ctrl_c3:
            st.write("")
            if cnt_pending > 0:
                if st.button("⚡ Approve All Pending", type="primary", use_container_width=True, key="tab5_btn_app_all"):
                    for pu, pinfo in list(all_pending_users.items()):
                        ppw = get_user_password(pinfo)
                        pname = pinfo.get("name", pu) if isinstance(pinfo, dict) else pu
                        pcontact = pinfo.get("contact", "N/A") if isinstance(pinfo, dict) else "N/A"
                        pcreated = pinfo.get("created_at", "") if isinstance(pinfo, dict) else ""
                        all_auth_users[pu] = {
                            "password": ppw,
                            "name": pname,
                            "contact": pcontact,
                            "role": "user",
                            "status": "approved",
                            "created_at": pcreated,
                            "approved_at": time.strftime("%Y-%m-%d %H:%M"),
                        }
                        del all_pending_users[pu]
                    save_saved_config({"auth_users": all_auth_users, "pending_users": all_pending_users})
                    st.toast(f"✅ Approved all {cnt_pending} pending customer accounts!", icon="🎉")
                    st.rerun()
            else:
                st.button("⚡ Approve All", disabled=True, use_container_width=True, key="tab5_btn_app_all_dis")

        # ------------------------------------
        # PENDING CUSTOMERS LIST
        # ------------------------------------
        show_pending = ("Pending" in status_filter or "All" in status_filter)
        if show_pending:
            filtered_pending = {}
            for u, info in all_pending_users.items():
                name = info.get("name", u) if isinstance(info, dict) else u
                contact = info.get("contact", "N/A") if isinstance(info, dict) else "N/A"
                if cust_search:
                    q = cust_search.lower()
                    if q not in u.lower() and q not in name.lower() and q not in contact.lower():
                        continue
                filtered_pending[u] = info

            if filtered_pending:
                st.markdown(f"#### ⏳ Pending Customer Approvals ({len(filtered_pending)})")
                for u, info in list(filtered_pending.items()):
                    pw = get_user_password(info)
                    name = info.get("name", u) if isinstance(info, dict) else u
                    contact = info.get("contact", "N/A") if isinstance(info, dict) else "N/A"
                    reg_date = info.get("created_at", "N/A") if isinstance(info, dict) else "N/A"

                    st.markdown(
                        f"""
                        <div class="customer-card is-pending">
                            <div class="customer-header">
                                <div class="customer-title-block">
                                    <div class="customer-avatar">{escape(u[0].upper())}</div>
                                    <div>
                                        <div class="customer-uname">{escape(u)}</div>
                                        <div style="font-size:0.82rem; color:#94a3b8;">{escape(name)}</div>
                                    </div>
                                </div>
                                <span class="badge-status pending">⏳ Awaiting Approval</span>
                            </div>
                            <div class="customer-info-grid">
                                <div class="customer-info-item">📞 Contact: <span>{escape(contact)}</span></div>
                                <div class="customer-info-item">📅 Registered: <span>{escape(reg_date)}</span></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    btn_app_c, btn_rej_c, _ = st.columns([1.2, 1, 2], gap="small")
                    with btn_app_c:
                        if st.button(f"✅ Approve Account", key=f"t5_app_{u}", type="primary", use_container_width=True):
                            all_auth_users[u] = {
                                "password": pw,
                                "name": name,
                                "contact": contact,
                                "role": "user",
                                "status": "approved",
                                "created_at": reg_date,
                                "approved_at": time.strftime("%Y-%m-%d %H:%M"),
                            }
                            if u in all_pending_users:
                                del all_pending_users[u]
                            save_saved_config({"auth_users": all_auth_users, "pending_users": all_pending_users})
                            st.toast(f"✅ Approved customer '{u}'!", icon="🎉")
                            st.rerun()
                    with btn_rej_c:
                        if st.button(f"❌ Reject", key=f"t5_rej_{u}", use_container_width=True):
                            if u in all_pending_users:
                                del all_pending_users[u]
                            save_saved_config({"pending_users": all_pending_users})
                            st.toast(f"Rejected registration for '{u}'.", icon="🗑️")
                            st.rerun()
                    st.write("")
            elif "Pending" in status_filter:
                st.info("✅ No pending registrations match your search.")

        # ------------------------------------
        # ACTIVE APPROVED CUSTOMERS LIST
        # ------------------------------------
        show_approved = ("Active" in status_filter or "Admins" in status_filter or "All" in status_filter)
        if show_approved:
            filtered_approved = {}
            for u, info in all_auth_users.items():
                is_adm = (u == "admin" or (isinstance(info, dict) and info.get("role") == "admin"))
                if "Admins" in status_filter and not is_adm:
                    continue
                if "Active" in status_filter and is_adm:
                    continue
                name = info.get("name", u) if isinstance(info, dict) else u
                contact = info.get("contact", "N/A") if isinstance(info, dict) else "N/A"
                if cust_search:
                    q = cust_search.lower()
                    if q not in u.lower() and q not in name.lower() and q not in contact.lower():
                        continue
                filtered_approved[u] = info

            if filtered_approved:
                st.markdown(f"#### ✅ Active Accounts ({len(filtered_approved)})")
                for u, info in list(filtered_approved.items()):
                    is_adm = (u == "admin" or (isinstance(info, dict) and info.get("role") == "admin"))
                    name = info.get("name", u) if isinstance(info, dict) else u
                    contact = info.get("contact", "N/A") if isinstance(info, dict) else "N/A"
                    reg_date = info.get("created_at", "N/A") if isinstance(info, dict) else "N/A"
                    app_date = info.get("approved_at", "N/A") if isinstance(info, dict) else "N/A"

                    last_dev = info.get("last_device", {}) if isinstance(info, dict) else {}
                    dev_name = last_dev.get("device_name", "Not logged in yet") if isinstance(last_dev, dict) else str(last_dev or "Not logged in yet")
                    dev_ip = last_dev.get("ip", "N/A") if isinstance(last_dev, dict) else "N/A"
                    last_login = info.get("last_login", last_dev.get("login_time", "N/A") if isinstance(last_dev, dict) else "N/A") if isinstance(info, dict) else "N/A"

                    role_badge = '<span class="badge-status admin">🛡️ Admin</span>' if is_adm else '<span class="badge-status approved">✅ Active Customer</span>'
                    avatar_style = 'background:rgba(168,85,247,0.18); color:#c084fc;' if is_adm else 'background:rgba(16,185,129,0.18); color:#34d399;'

                    st.markdown(
                        f"""
                        <div class="customer-card is-approved">
                            <div class="customer-header">
                                <div class="customer-title-block">
                                    <div class="customer-avatar" style="{avatar_style}">{escape(u[0].upper())}</div>
                                    <div>
                                        <div class="customer-uname">{escape(u)}</div>
                                        <div style="font-size:0.82rem; color:#94a3b8;">{escape(name)}</div>
                                    </div>
                                </div>
                                {role_badge}
                            </div>
                            <div class="customer-info-grid">
                                <div class="customer-info-item">📞 Contact: <span>{escape(contact)}</span></div>
                                <div class="customer-info-item">📱 Saved Device: <span style="color:#38bdf8;">{escape(dev_name)}</span></div>
                                <div class="customer-info-item">🌐 IP: <span>{escape(dev_ip)}</span></div>
                                <div class="customer-info-item">🕒 Last Login: <span>{escape(last_login)}</span></div>
                                <div class="customer-info-item">📅 Registered: <span>{escape(reg_date)}</span></div>
                                <div class="customer-info-item">⏱️ Approved: <span>{escape(app_date)}</span></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if not is_adm:
                        c_act1, c_act2, _ = st.columns([1.2, 1, 2], gap="small")
                        with c_act1:
                            with st.popover(f"🔑 Reset Password", use_container_width=True):
                                st.markdown(f"**Reset Password for `{u}`**")
                                p_new = st.text_input("New Password", key=f"t5_rpw_{u}", type="password", placeholder="Min 4 characters")
                                if st.button("Update Password", key=f"t5_btn_rpw_{u}", type="primary", use_container_width=True):
                                    if len(p_new) < 4:
                                        st.error("Password must be at least 4 characters.")
                                    else:
                                        if isinstance(info, dict):
                                            all_auth_users[u]["password"] = p_new
                                        else:
                                            all_auth_users[u] = {"password": p_new, "role": "user", "status": "approved"}
                                        save_saved_config({"auth_users": all_auth_users})
                                        st.toast(f"🔑 Password reset for customer '{u}'!", icon="✅")
                                        st.rerun()
                        with c_act2:
                            if st.button(f"🗑️ Delete Account", key=f"t5_del_{u}", use_container_width=True):
                                del all_auth_users[u]
                                save_saved_config({"auth_users": all_auth_users})
                                st.toast(f"Removed account for '{u}'.", icon="🗑️")
                                st.rerun()
                        st.write("")
            elif "Active" in status_filter:
                st.info("No active accounts match your search.")

        # ------------------------------------
        # EXPORT CUSTOMER REGISTRY
        # ------------------------------------
        st.markdown("---")
        st.markdown("#### 📥 Export Customer Registry Data")
        export_records = []
        for u, info in all_pending_users.items():
            export_records.append({
                "Username": u,
                "Name": info.get("name", u) if isinstance(info, dict) else u,
                "Contact": info.get("contact", "N/A") if isinstance(info, dict) else "N/A",
                "Role": "Customer (Pending)",
                "Status": "Pending Approval",
                "Saved Device": "Pending",
                "Last Login": "N/A",
                "IP Address": "N/A",
                "Registered At": info.get("created_at", "N/A") if isinstance(info, dict) else "N/A",
                "Approved At": "N/A",
            })
        for u, info in all_auth_users.items():
            is_adm = (u == "admin" or (isinstance(info, dict) and info.get("role") == "admin"))
            last_dev = info.get("last_device", {}) if isinstance(info, dict) else {}
            dev_name = last_dev.get("device_name", "Not logged in yet") if isinstance(last_dev, dict) else str(last_dev or "Not logged in yet")
            dev_ip = last_dev.get("ip", "N/A") if isinstance(last_dev, dict) else "N/A"
            last_login = info.get("last_login", last_dev.get("login_time", "N/A") if isinstance(last_dev, dict) else "N/A") if isinstance(info, dict) else "N/A"

            export_records.append({
                "Username": u,
                "Name": info.get("name", u) if isinstance(info, dict) else u,
                "Contact": info.get("contact", "N/A") if isinstance(info, dict) else "N/A",
                "Role": "Administrator" if is_adm else "Customer",
                "Status": "Approved",
                "Saved Device": dev_name,
                "Last Login": last_login,
                "IP Address": dev_ip,
                "Registered At": info.get("created_at", "N/A") if isinstance(info, dict) else "N/A",
                "Approved At": info.get("approved_at", "N/A") if isinstance(info, dict) else "N/A",
            })

        if export_records:
            df_export = pd.DataFrame(export_records)
            csv_data = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Customer Accounts CSV",
                data=csv_data,
                file_name=f"customer_accounts_{time.strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="tab5_download_csv",
            )
