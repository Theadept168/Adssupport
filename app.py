from __future__ import annotations

import asyncio
import concurrent.futures
import io
import json
import os
import re
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
from pydub import AudioSegment

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

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
BASE_STORAGE_DIR = Path(".dubber_input")
BASE_STORAGE_DIR.mkdir(exist_ok=True)
STORAGE_DIR = BASE_STORAGE_DIR  # fallback reference


def get_user_storage_dir(username: str = None) -> Path:
    if not username:
        try:
            if hasattr(st, "session_state"):
                username = st.session_state.get("auth_user", "")
        except Exception:
            username = ""
    if not username:
        safe_name = "guest"
    else:
        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(username)).strip().lower() or "guest"
    user_dir = BASE_STORAGE_DIR / "users" / safe_name
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

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
    if "admin_contact" not in config:
        config["admin_contact"] = {
            "telegram": "@Adsservice7",
            "phone": "+855 768876797",
            "email": "thea13389@gmail.com",
            "note": "ទាក់ទងមកកាន់ Admin តាម Telegram ឬទូរស័ព្ទ ដើម្បីស្នើសុំបើកគណនី ឬសាកសួរព័ត៌មានបន្ថែម។",
        }
    if "admin_messages" not in config:
        config["admin_messages"] = []
    if "custom_reviews" not in config:
        config["custom_reviews"] = []
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


def get_admin_contact_info() -> dict:
    cfg = load_saved_config()
    return cfg.get("admin_contact", {
        "telegram": "@Adsservice7",
        "phone": "+855 768876797",
        "email": "thea13389@gmail.com",
        "note": "ទាក់ទងមកកាន់ Admin តាម Telegram ឬទូរស័ព្ទ ដើម្បីស្នើសុំបើកគណនី ឬសាកសួរព័ត៌មានបន្ថែម។",
    })


def save_admin_contact_info(info_dict: dict) -> None:
    save_saved_config({"admin_contact": info_dict})


def send_message_to_admin(sender: str, contact: str, message: str) -> bool:
    if not message.strip():
        return False
    cfg = load_saved_config()
    msgs = cfg.get("admin_messages", [])
    new_msg = {
        "id": secrets.token_hex(4),
        "sender": sender.strip() or "Anonymous Customer",
        "contact": contact.strip() or "N/A",
        "message": message.strip(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "unread",
    }
    msgs.append(new_msg)
    save_saved_config({"admin_messages": msgs})
    return True


def render_contact_admin(key_prefix: str = "main", compact: bool = False):
    contact_info = get_admin_contact_info()
    tg = str(contact_info.get("telegram", "")).strip()
    phone = str(contact_info.get("phone", "")).strip()
    email = str(contact_info.get("email", "")).strip()
    note = str(contact_info.get("note", "")).strip()

    tg_clean = tg.lstrip("@")
    tg_url = f"https://t.me/{tg_clean}" if tg_clean and not tg_clean.startswith("http") else tg
    phone_clean = re.sub(r"[^\d+]", "", phone)

    if compact:
        tg_html = f'<div style="margin-top: 4px;">✈️ Telegram: <a href="{escape(tg_url)}" target="_blank" style="color: #38bdf8; font-weight: 600; text-decoration: none;">{escape(tg)}</a></div>' if tg else ''
        phone_html = f'<div style="margin-top: 4px;">📞 Phone: <a href="tel:{escape(phone_clean)}" style="color: #34d399; font-weight: 600; text-decoration: none;">{escape(phone)}</a></div>' if phone else ''
        email_html = f'<div style="margin-top: 4px;">✉️ Email: <a href="mailto:{escape(email)}" style="color: #cbd5e1; text-decoration: none;">{escape(email)}</a></div>' if email else ''
        note_html = f'<p style="font-size: 0.76rem; color: #94a3b8; margin: 0 0 8px 0;">{escape(note)}</p>' if note else ''

        html = f"""<div style="background: rgba(30, 41, 59, 0.75); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 12px; padding: 10px 14px; margin: 8px 0;">
<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
<span style="font-weight: 700; color: #38bdf8; font-size: 0.88rem;">💬 Contact Admin</span>
<span style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 0.68rem; font-weight: 700; padding: 2px 7px; border-radius: 999px;">Support</span>
</div>
{note_html}
<div style="display: flex; flex-direction: column; font-size: 0.82rem;">
{tg_html}
{phone_html}
{email_html}
</div>
</div>"""
        st.markdown(html, unsafe_allow_html=True)
    else:
        tg_card = f"""<a href="{escape(tg_url)}" target="_blank" style="text-decoration: none; display: block;">
<div style="background: rgba(56, 189, 248, 0.14); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 10px; padding: 12px 14px; text-align: center; color: #38bdf8; font-weight: 700; font-size: 0.92rem;">
✈️ Telegram: {escape(tg)}
</div>
</a>""" if tg else ""

        phone_card = f"""<a href="tel:{escape(phone_clean)}" style="text-decoration: none; display: block;">
<div style="background: rgba(16, 185, 129, 0.14); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 10px; padding: 12px 14px; text-align: center; color: #34d399; font-weight: 700; font-size: 0.92rem;">
📞 Phone: {escape(phone)}
</div>
</a>""" if phone else ""

        email_card = f"""<a href="mailto:{escape(email)}" style="text-decoration: none; display: block;">
<div style="background: rgba(249, 115, 22, 0.14); border: 1px solid rgba(249, 115, 22, 0.35); border-radius: 10px; padding: 12px 14px; text-align: center; color: #fb923c; font-weight: 700; font-size: 0.92rem;">
✉️ Email: {escape(email)}
</div>
</a>""" if email else ""

        note_text = escape(note) if note else "សម្រាប់សាកសួរព័ត៌មានបន្ថែម ស្នើសុំបើកគណនី ឬរាយការណ៍បញ្ហា សូមទាក់ទងមកកាន់ Admin តាមមធ្យោបាយខាងក្រោម៖"

        html = f"""<div style="background: rgba(30, 41, 59, 0.75); border: 1px solid rgba(56, 189, 248, 0.28); border-radius: 14px; padding: 16px 18px; margin: 12px 0;">
<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
<div style="font-size: 1.02rem; font-weight: 700; color: #38bdf8;">💬 ទាក់ទងទៅកាន់ Admin (Contact Administrator)</div>
<span style="background: rgba(56, 189, 248, 0.18); color: #38bdf8; font-size: 0.72rem; font-weight: 700; padding: 3px 9px; border-radius: 999px;">Official Support</span>
</div>
<p style="font-size: 0.84rem; color: #cbd5e1; margin: 0 0 12px 0; line-height: 1.5;">{note_text}</p>
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 6px;">
{tg_card}
{phone_card}
{email_card}
</div>
</div>"""
        st.markdown(html, unsafe_allow_html=True)

    with st.expander("✉️ ផ្ញើសារផ្ទាល់ទៅ Admin (Send In-App Message)", expanded=False):
        msg_sender = st.text_input("Your Name / Username", value=st.session_state.get("auth_user", ""), placeholder="Enter your name", key=f"inp_msg_sender_{key_prefix}").strip()
        msg_contact = st.text_input("Your Contact (Phone / Telegram / Email)", placeholder="e.g. @telegram or 012 345 678", key=f"inp_msg_contact_{key_prefix}").strip()
        msg_body = st.text_area("Message / Question (សាររបស់អ្នក)", placeholder="Describe your question or request to Admin...", key=f"inp_msg_body_{key_prefix}").strip()
        btn_send = st.button("📤 ផ្ញើសារទៅ Admin", type="primary", use_container_width=True, key=f"btn_send_admin_{key_prefix}")
        if btn_send:
            if not msg_body:
                st.error("Please enter a message.")
            else:
                send_message_to_admin(msg_sender, msg_contact, msg_body)
                st.success("✅ សាររបស់អ្នកត្រូវបានផ្ញើទៅ Admin រួចរាល់ហើយ! Admin នឹងពិនិត្យមើលក្នុងពេលឆាប់ៗ។")


DEFAULT_CUSTOMER_REVIEWS = [
    {
        "id": "rev_1",
        "name": "សុខា Media (Sokha Media)",
        "role": "Content Creator & YouTuber",
        "rating": 5,
        "avatar": "🎬",
        "date": "មុននេះ ២ ម៉ោង",
        "verified": True,
        "review": "សាកល្បងប្រើ Dubber AI នេះហើយ ភ្ញាក់ផ្អើលតែម្តង! បកប្រែរឿងចិន និងវីដេអូអង់គ្លេសមកខ្មែរបានរលូន សម្លេង Piseth & Sreymom និយាយស៊ីសង្វាក់គ្នាដូចមនុស្សមែនទែន 10/10!",
    },
    {
        "id": "rev_2",
        "name": "Vannak Digital Studio",
        "role": "TikToker & Digital Marketer",
        "rating": 5,
        "avatar": "📱",
        "date": "ម្សិលមិញ",
        "verified": True,
        "review": "មុខងារ Transcribe One Folder ជួយស្រង់ Subtitle និង Dubbing វីដេអូ TikTok ម្ដងមួយ Folder ធំៗចំណេញពេលរាប់ម៉ោង។ ណែនាំឱ្យអ្នកធ្វើ Content ប្រើទាំងអស់គ្នា!",
    },
    {
        "id": "rev_3",
        "name": "ម៉ារីណា Online Shop",
        "role": "E-Commerce Business Owner",
        "rating": 5,
        "avatar": "🛍️",
        "date": "៣ ថ្ងៃមុន",
        "verified": True,
        "review": "កាលពីមុនចំណាយលុយច្រើនជួលគេបញ្ចូលសម្លេងស្ប៉តពាណិជ្ជកម្ម ឥឡូវមាន Studio នេះ ដាក់វីដេអូចូល Render តែ ៣ នាទីបានវីដេអូលក់ទំនិញយ៉ាងឡូយ!",
    },
    {
        "id": "rev_4",
        "name": "Bona Film & Editor",
        "role": "Senior Video Editor",
        "rating": 5,
        "avatar": "✂️",
        "date": "៥ ថ្ងៃមុន",
        "verified": True,
        "review": "Burn Subtitles ខ្មែរស្អាត មិនបែក Font ហើយ Audio Synchronize ត្រូវប្លង់វីដេអូល្អណាស់។ Admin Support រហ័សទាន់ចិត្ត!",
    },
    {
        "id": "rev_5",
        "name": "Dara Tech & Gaming",
        "role": "Video Localization Producer",
        "rating": 5,
        "avatar": "🎮",
        "date": "១ សប្តាហ៍មុន",
        "verified": True,
        "review": "ល្អបំផុតសម្រាប់អ្នកចង់ធ្វើវីដេអូ Re-dubbed ពីភាសាបរទេស។ System ដំណើរការលឿន ងាយស្រួលប្រើសូម្បីតែនៅលើទូរស័ព្ទ!",
    },
    {
        "id": "rev_6",
        "name": "ស្រីពៅ សម្រស់ធម្មជាតិ",
        "role": "KOL & Product Reviewer",
        "rating": 5,
        "avatar": "💄",
        "date": "២ សប្តាហ៍មុន",
        "verified": True,
        "review": "សម្លេងស្រី Sreymom Neural ពិរោះទន់ភ្លន់ខ្លាំង សមស្របនឹងការនិយាយ Review ផលិតផល។ អតិថិជនមើលវីដេអូច្រើនជាងមុន!",
    },
]


def get_customer_reviews() -> list:
    cfg = load_saved_config()
    custom_revs = cfg.get("custom_reviews", [])
    return custom_revs + DEFAULT_CUSTOMER_REVIEWS


def save_customer_review(name: str, role: str, rating: int, review_text: str) -> None:
    cfg = load_saved_config()
    custom_revs = cfg.get("custom_reviews", [])
    new_rev = {
        "id": secrets.token_hex(4),
        "name": name.strip() or "Anonymous Creator",
        "role": role.strip() or "Content Creator",
        "rating": max(1, min(5, int(rating))),
        "avatar": "⭐",
        "date": "ទើបតែបញ្ចូល (Just now)",
        "verified": True,
        "review": review_text.strip(),
    }
    custom_revs.insert(0, new_rev)
    save_saved_config({"custom_reviews": custom_revs})


def render_social_proof_reviews(key_prefix: str = "main", compact: bool = False):
    return


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
    "🎭 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Piseth 👨 + Sreymom 👩)",
    "👨 Piseth តែម្នាក់ឯង (ប្រុស)",
    "👩 Sreymom តែម្នាក់ឯង (ស្រី)",
]
VOICE_BUTTON_MAP = {
    "🎭 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Piseth 👨 + Sreymom 👩)": "auto_detect",
    "🎭 Auto (Piseth 👨 / Sreymom 👩)": "auto_detect",
    "👨 Piseth តែម្នាក់ឯង (ប្រុស)": "km-KH-PisethNeural",
    "👨 Piseth (ប្រុស / Boy)": "km-KH-PisethNeural",
    "👩 Sreymom តែម្នាក់ឯង (ស្រី)": "km-KH-SreymomNeural",
    "👩 Sreymom (ស្រី / Girl)": "km-KH-SreymomNeural",
}


def estimate_pitch_f0(samples: np.ndarray, sample_rate: int = 16000) -> float:
    if len(samples) == 0:
        return 140.0
    frame_len = int(sample_rate * 0.05)  # 50ms window = 800 samples
    hop_len = int(sample_rate * 0.025)   # 25ms step = 400 samples
    min_lag = int(sample_rate / 380)     # ~380 Hz max human speech F0 (~42 samples)
    max_lag = int(sample_rate / 75)      # ~75 Hz min human speech F0 (~213 samples)
    pitches = []

    # Adaptive energy threshold to detect voiced frames even on quiet speech
    mean_energy = float(np.mean(samples**2)) if len(samples) > 0 else 0.0
    energy_thresh = max(20.0, mean_energy * 0.06)

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
            if zero_lag > 0 and (peak_val / zero_lag) > 0.20:  # Voiced frame threshold
                f0 = sample_rate / peak_lag
                if 75 <= f0 <= 380:
                    pitches.append(f0)
    return float(np.median(pitches)) if pitches else 140.0


def detect_voice_piseth_sreymom(media_path: str = None, audio_segment: AudioSegment = None) -> dict:
    try:
        if audio_segment is None:
            if not media_path or not Path(media_path).exists():
                return {
                    "voice": "km-KH-PisethNeural",
                    "gender": "Male",
                    "name": "Piseth Neural (Male / ប្រុស)",
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

        # Male fundamental frequency typically 85-155 Hz, Female 160-280 Hz (boundary at 160.0 Hz)
        if f0 < 160.0:
            return {
                "voice": "km-KH-PisethNeural",
                "gender": "Male",
                "name": "Piseth Neural (Male / ប្រុស)",
                "pitch": round(f0, 1),
                "icon": "👨",
            }
        else:
            return {
                "voice": "km-KH-SreymomNeural",
                "gender": "Female",
                "name": "Sreymom Neural (Female / ស្រី)",
                "pitch": round(f0, 1),
                "icon": "👩",
            }
    except Exception:
        return {
            "voice": "km-KH-PisethNeural",
            "gender": "Male",
            "name": "Piseth Neural (Male / ប្រុស)",
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

    results = {}
    prev_info = None

    if audio_full is None and media_path and Path(media_path).exists():
        try:
            audio_full = AudioSegment.from_file(media_path)
        except Exception:
            audio_full = None

    # Global fallback if a segment is too short or quiet
    global_info = detect_voice_piseth_sreymom(audio_segment=audio_full[:60000]) if audio_full is not None else None
    fallback_info = global_info if global_info else {
        "voice": "km-KH-PisethNeural",
        "gender": "Male",
        "name": "Piseth Neural (Male / ប្រុស)",
        "pitch": 130.0,
        "icon": "👨",
    }

    for sub in subtitles:
        # 1. Text cues override (e.g. [ស្រី], [ប្រុស], [Female], [Male])
        t_clean = sub.text.strip().lower()
        if any(t_clean.startswith(prefix) for prefix in ("[ស្រី]", "[តួស្រី]", "[female]", "[woman]", "[girl]", "[sreymom]")):
            cur_info = {
                "voice": "km-KH-SreymomNeural",
                "gender": "Female",
                "name": "Sreymom Neural (Female / ស្រី)",
                "pitch": 220.0,
                "icon": "👩",
            }
            results[sub.index] = cur_info
            prev_info = cur_info
            continue
        elif any(t_clean.startswith(prefix) for prefix in ("[ប្រុស]", "[តួប្រុស]", "[male]", "[man]", "[boy]", "[piseth]")):
            cur_info = {
                "voice": "km-KH-PisethNeural",
                "gender": "Male",
                "name": "Piseth Neural (Male / ប្រុស)",
                "pitch": 120.0,
                "icon": "👨",
            }
            results[sub.index] = cur_info
            prev_info = cur_info
            continue

        # 2. Acoustic pitch detection from media audio clip
        if audio_full is not None:
            start_ms = max(0, sub.start)
            end_ms = min(len(audio_full), sub.end)
            clip_len = end_ms - start_ms
            if clip_len >= 180:
                clip = audio_full[start_ms:end_ms]
                info = detect_voice_piseth_sreymom(audio_segment=clip)
                results[sub.index] = info
                prev_info = info
            elif prev_info is not None:
                results[sub.index] = prev_info
            else:
                results[sub.index] = fallback_info
        else:
            results[sub.index] = prev_info or fallback_info

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
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
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


THAI_CHAR_PATTERN = re.compile(r"[\u0e00-\u0e7f]")


def has_thai_characters(text: str) -> bool:
    """Check if string contains any Thai Unicode characters."""
    if not text:
        return False
    return bool(THAI_CHAR_PATTERN.search(str(text)))


def strip_or_clean_thai(text: str) -> str:
    """Fallback filter to strip any remaining Thai characters if all LLM passes fail."""
    if not text:
        return ""
    cleaned = THAI_CHAR_PATTERN.sub("", str(text))
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned


def purge_and_enforce_khmer(
    subtitles: list[Subtitle],
    source_language: str = "auto",
    gemini_key: str = "",
    openai_key: str = "",
    model_name: str = "gemini-flash-latest",
) -> list[Subtitle]:
    """
    Scans subtitle segments. If ANY Thai characters (U+0E00-U+0E7F) are detected,
    forces an ultra-strict re-translation of those lines into 100% natural Khmer.
    Strictly forbids and eliminates any Thai characters from the studio output.
    """
    if not subtitles:
        return subtitles

    offending_indices = [idx for idx, item in enumerate(subtitles) if has_thai_characters(item.text)]
    if not offending_indices:
        return subtitles

    payload = [{"id": idx, "text": subtitles[idx].text} for idx in offending_indices]

    retranslated = {}
    force_prompt = (
        "You are an expert audiovisual translator specializing in Khmer (ភាសាខ្មែរ).\n"
        "STRICT MANDATORY RULE - NO THAI LANGUAGE ALLOWED:\n"
        "The following subtitle lines mistakenly contain Thai text (ภาษาไทย) or Thai characters. "
        "You MUST translate EVERY SINGLE WORD completely into 100% natural, fluent Khmer (អក្សរខ្មែរ).\n"
        "1. Absolutely ZERO Thai characters (Unicode range U+0E00 to U+0E7F) are permitted in the output.\n"
        "2. Do NOT output mixed Thai-Khmer. Every Thai phrase, verb, noun, name, and idiom must be translated into Khmer script.\n"
        "3. Output strictly a JSON array of objects with numeric 'id' and 'text'. No commentary or markdown.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    if gemini_key:
        try:
            from google import genai

            client = genai.Client(api_key=gemini_key)
            g_mod = model_name if (model_name and model_name.startswith("gemini-")) else "gemini-flash-latest"
            resp, _ = generate_with_gemini_retry(
                client,
                g_mod,
                force_prompt,
                {"response_mime_type": "application/json", "temperature": 0.1},
            )
            raw = resp.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for obj in parsed:
                    t_text = str(obj.get("text", "")).strip()
                    if t_text and not has_thai_characters(t_text):
                        retranslated[int(obj["id"])] = t_text
        except Exception:
            pass

    still_needed = [idx for idx in offending_indices if idx not in retranslated]
    if still_needed and openai_key:
        try:
            import httpx
            from openai import OpenAI

            client = OpenAI(api_key=openai_key, http_client=httpx.Client())
            oa_payload = [{"id": idx, "text": subtitles[idx].text} for idx in still_needed]
            oa_prompt = (
                "Translate these subtitle lines completely into 100% natural Khmer (ភាសាខ្មែរ). "
                "STRICT BAN: Absolutely NO Thai characters (U+0E00-U+0E7F) allowed in output. "
                "Return JSON with a 'translations' array of objects having numeric 'id' and 'text'."
            )
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": oa_prompt},
                    {"role": "user", "content": json.dumps(oa_payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            oa_res = json.loads(res.choices[0].message.content)
            for item in oa_res.get("translations", []):
                t_text = str(item.get("text", "")).strip()
                if t_text and not has_thai_characters(t_text):
                    retranslated[int(item["id"])] = t_text
        except Exception:
            pass

    cleaned_subs = []
    for idx, item in enumerate(subtitles):
        new_text = retranslated.get(idx, item.text)
        if has_thai_characters(new_text):
            new_text = strip_or_clean_thai(new_text)
            if not new_text:
                new_text = "..."
        cleaned_subs.append(Subtitle(item.index, item.start, item.end, new_text))

    return cleaned_subs


def translate_subtitles_with_gemini(subtitles: list[Subtitle], source_language: str, api_key: str, model_name: str) -> list[Subtitle]:
    if not api_key:
        raise ValueError("Please provide a Gemini API key in the sidebar.")
    from google import genai

    client = genai.Client(api_key=api_key)
    payload = [{"id": position, "text": item.text} for position, item in enumerate(subtitles)]
    source_description = "the detected source language" if source_language.strip().lower() == "auto" else source_language
    prompt = (
        f"You are a professional audiovisual translator. Translate these subtitle lines from {source_description} to 100% natural Khmer (ភាសាខ្មែរ).\n"
        "STRICT MANDATORY RULES:\n"
        "1. ABSOLUTELY NO THAI SCRIPT OR THAI WORDS ALLOWED: You MUST NOT output any Thai characters (Unicode range U+0E00 to U+0E7F) under any circumstances. "
        "Even if the source dialogue or subtitle is in Thai (ภาษาไทย), every single Thai word, phrase, name, and idiom MUST be fully and naturally translated into Khmer script (អក្សរខ្មែរ).\n"
        "2. NO MIXED THAI-KHMER: Do NOT leave any untranslated Thai words. Convert everything completely into Khmer.\n"
        "3. Preserve exact meaning, names, dramatic emotion, line order, and punctuation.\n"
        "4. Return strictly a JSON array of objects, each with numeric 'id' and one translated 'text' field (containing ONLY Khmer script, numbers, and standard punctuation). Do not add markdown or commentary.\n\n"
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
    res_subs = [Subtitle(item.index, item.start, item.end, translations[position]) for position, item in enumerate(subtitles)]
    return purge_and_enforce_khmer(res_subs, source_language=source_language, gemini_key=api_key, model_name=model_name)


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
                "content": (
                    f"Translate subtitle lines from {source_description} to 100% natural Khmer (ភាសាខ្មែរ). "
                    "CRITICAL BAN ON THAI: Under NO circumstance should any Thai characters (U+0E00-U+0E7F) appear in the output. "
                    "If the source is in Thai or contains Thai words, you MUST translate every single Thai word completely into Khmer script (អក្សរខ្មែរ). "
                    "Return JSON with a 'translations' array of objects having numeric 'id' and 'text'. Maintain exact order, names, and tone."
                ),
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
    res_subs = [Subtitle(item.index, item.start, item.end, translations[position]) for position, item in enumerate(subtitles)]
    return purge_and_enforce_khmer(res_subs, source_language=source_language, openai_key=api_key)


def run_auto_translation(subtitles: list[Subtitle], source_language: str, gemini_key: str, openai_key: str, model_name: str) -> list[Subtitle]:
    if not gemini_key or not openai_key:
        _cfg = load_saved_config()
        if not gemini_key:
            gemini_key = _cfg.get("gemini_api_key", "") or os.getenv("GEMINI_API_KEY", "")
        if not openai_key:
            openai_key = _cfg.get("openai_api_key", "") or os.getenv("OPENAI_API_KEY", "")

    g_model = model_name if (model_name and model_name.startswith("gemini-")) else "gemini-flash-latest"
    try:
        if gemini_key:
            res = translate_subtitles_with_gemini(subtitles, source_language, gemini_key, g_model)
        elif openai_key:
            res = translate_subtitles_with_openai(subtitles, source_language, openai_key)
        else:
            raise ValueError("No API key configured for auto-translation. Enter a Gemini or OpenAI API key in the sidebar.")
    except Exception as gemini_err:
        if openai_key:
            st.info("Gemini was busy, automatically switched to OpenAI GPT-4o Mini.")
            res = translate_subtitles_with_openai(subtitles, source_language, openai_key)
        else:
            raise gemini_err

    return purge_and_enforce_khmer(res, source_language=source_language, gemini_key=gemini_key, openai_key=openai_key, model_name=g_model)


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


@st.cache_resource(show_spinner="Loading speech model into RAM...")
def get_whisper_model(model_name: str):
    import whisper

    return whisper.load_model(model_name)


def transcribe_media(uploaded_file, model_name: str, api_key: str, media_save_path: Path = None) -> str:
    user_storage = get_user_storage_dir()
    if isinstance(uploaded_file, (str, Path)):
        media_path = Path(uploaded_file)
        input_suffix = media_path.suffix.lower()
        if not media_path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")
    else:
        input_suffix = Path(uploaded_file.name).suffix.lower()
        if input_suffix not in {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv", ".flv", ".avi", ".wmv", ".m4v"}:
            input_suffix = ".mp4"
        media_path = media_save_path if media_save_path else (user_storage / f"uploaded_media{input_suffix}")
        media_path.write_bytes(uploaded_file.getvalue())

    is_vid = input_suffix in {".mp4", ".mov", ".webm", ".mkv", ".flv", ".avi", ".wmv", ".m4v"}
    try:
        if hasattr(st, "session_state"):
            st.session_state.uploaded_media_path = str(media_path.resolve())
            st.session_state.is_video = is_vid
    except Exception:
        pass

    upload_file_path = media_path
    temp_clean_files = []
    if is_vid:
        audio_extract_path = user_storage / f"temp_audio_{secrets.token_hex(8)}.mp3"
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(media_path),
            "-vn", "-acodec", "libmp3lame", "-b:a", "64k", "-ar", "16000",
            str(audio_extract_path),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if audio_extract_path.exists() and audio_extract_path.stat().st_size > 0:
                upload_file_path = audio_extract_path
                temp_clean_files.append(audio_extract_path)
        except Exception:
            upload_file_path = media_path

    # If upload_file_path still contains non-ASCII characters (e.g. Chinese, Khmer, accented characters),
    # create a temporary clean ASCII copy so Google GenAI / httpx header never crashes with 'ascii' codec can't encode
    if any(ord(c) > 127 for c in upload_file_path.name) or " " in upload_file_path.name:
        import shutil
        safe_ascii_copy = user_storage / f"safe_upload_{secrets.token_hex(8)}{upload_file_path.suffix.lower()}"
        try:
            shutil.copy2(upload_file_path, safe_ascii_copy)
            upload_file_path = safe_ascii_copy
            temp_clean_files.append(safe_ascii_copy)
        except Exception:
            pass

    try:
        if not api_key:
            _cfg = load_saved_config()
            if model_name.startswith("openai"):
                api_key = _cfg.get("openai_api_key", "") or os.getenv("OPENAI_API_KEY", "")
            elif model_name.startswith("gemini"):
                api_key = _cfg.get("gemini_api_key", "") or os.getenv("GEMINI_API_KEY", "")

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
        for alt in ["gemini-flash-latest", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3-flash-preview"]:
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
            model = get_whisper_model("base")
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
            model = get_whisper_model("base")
            result = model.transcribe(str(upload_file_path), fp16=False)
            subtitles = [
                Subtitle(index, round(segment["start"] * 1000), round(segment["end"] * 1000), segment["text"].strip())
                for index, segment in enumerate(result["segments"], 1)
                if segment["text"].strip()
            ]

        if not subtitles:
            raise ValueError("No speech segments detected in media.")
        return render_srt(subtitles)

        model = get_whisper_model(model_name)
        result = model.transcribe(str(upload_file_path), fp16=False)
        subtitles = [
            Subtitle(index, round(segment["start"] * 1000), round(segment["end"] * 1000), segment["text"].strip())
            for index, segment in enumerate(result["segments"], 1)
            if segment["text"].strip()
        ]
        return render_srt(subtitles)

    finally:
        for tmp_c in temp_clean_files:
            try:
                if tmp_c.exists():
                    tmp_c.unlink()
            except Exception:
                pass


# ==========================================
# High-Quality TTS Synthesis Engine
# ==========================================
def synthesize_single_line(text: str, engine: str, voice: str, speed: float, elevenlabs_key: str = "") -> bytes:
    cleaned_text = text.replace("\n", " ").strip()
    # Remove bracketed and parenthesized sound cues (e.g. [Music], [Applause], (laughter))
    cleaned_text = re.sub(r"\[.*?\]|\(.*?\)", "", cleaned_text).strip()
    # Safety: Filter any stray Thai characters so Khmer neural voice doesn't glitch
    if has_thai_characters(cleaned_text):
        cleaned_text = strip_or_clean_thai(cleaned_text)

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


def synthesize_full_audio(
    subtitles: list[Subtitle],
    engine: str,
    voice: str,
    speed: float,
    elevenlabs_key: str = "",
    progress_callback=None,
    media_path: str = None,
    output_audio_path: str = None,
    subtitle_voices_override: dict = None,
) -> bytes:
    output = AudioSegment.silent(duration=0)
    total = len(subtitles)

    # Preload media audio for character voice detection when auto_detect is chosen
    media_audio = None
    target_media = media_path or (st.session_state.get("uploaded_media_path") if hasattr(st, "session_state") else None)
    if voice == "auto_detect" and target_media:
        media_p = Path(target_media)
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
        line_voice = ""
        if subtitle_voices_override and item.index in subtitle_voices_override:
            line_voice = subtitle_voices_override[item.index]
        elif hasattr(st, "session_state"):
            line_voice = st.session_state.get("subtitle_voices", {}).get(item.index) or getattr(item, "voice", "")

        if not line_voice:
            if voice == "auto_detect":
                # Per-character voice detection dynamically from media audio clip
                if media_audio is not None and (item.end - item.start) >= 180:
                    try:
                        clip = media_audio[max(0, item.start):min(len(media_audio), item.end)]
                        seg_det = detect_voice_piseth_sreymom(audio_segment=clip)
                        line_voice = seg_det.get("voice", "km-KH-PisethNeural")
                        if hasattr(st, "session_state"):
                            st.session_state.setdefault("subtitle_voices", {})[item.index] = line_voice
                    except Exception:
                        line_voice = ""
                if not line_voice:
                    detected = st.session_state.get("detected_voice_info", {}) if hasattr(st, "session_state") else {}
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
    if output_audio_path:
        out_audio_p = Path(output_audio_path)
        out_audio_p.parent.mkdir(parents=True, exist_ok=True)
        out_audio_p.write_bytes(final_bytes)
        try:
            if hasattr(st, "session_state"):
                st.session_state.dubbed_audio_path = str(out_audio_p.resolve())
        except Exception:
            pass
    else:
        user_storage = get_user_storage_dir()
        dubbed_audio_path = user_storage / "dubbed_voiceover.wav"
        dubbed_audio_path.write_bytes(final_bytes)
        try:
            if hasattr(st, "session_state"):
                st.session_state.dubbed_audio_path = str(dubbed_audio_path.resolve())
        except Exception:
            pass

    return final_bytes


# ==========================================
# Video Studio & Subtitle Burning Engine
# ==========================================
def video_has_audio(video_file: str) -> bool:
    try:
        res = subprocess.run([FFMPEG_BIN, "-i", video_file], capture_output=True, text=True, encoding="utf-8", errors="replace")
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
    output_video_path: str = None,
) -> str:
    user_storage = get_user_storage_dir()
    if output_video_path:
        out_video_path = Path(output_video_path)
        out_video_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_video_path = user_storage / "dubbed_output.mp4"

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
            f"subtitles='{escaped_srt}':force_style='Fontname=Kantumruy Pro,FontSize=16,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=4,MarginV=25,Outline=1'"
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

    if burn_subtitles:
        cmd.extend([
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-level", "4.1",
            "-preset", "fast",
            "-crf", "23",
        ])
    else:
        cmd.extend(["-c:v", "copy"])

    cmd.extend([
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_video_path.resolve()),
    ])

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{proc.stderr}")

    return str(out_video_path.resolve())


def render_video_preview(video_path: str):
    if not video_path:
        st.info("No video file available to preview.")
        return
    p = Path(video_path)
    if not p.exists() or p.stat().st_size == 0:
        st.info("No valid video file available to preview.")
        return
    try:
        with open(p, "rb") as vf:
            v_data = vf.read()
        st.video(v_data, format="video/mp4")
    except Exception:
        st.video(str(p.resolve()), format="video/mp4")


def transcribe_one_folder(
    folder_path: str | Path = None,
    output_folder: str | Path = None,
    model_name: str = "gemini-flash-latest",
    source_language: str = "auto",
    gemini_key: str = "",
    openai_key: str = "",
    elevenlabs_key: str = "",
    tts_engine: str = "Microsoft Edge Neural",
    voice: str = "auto_detect",
    voice_speed: float = 1.0,
    burn_subtitles: bool = False,
    enable_bg_music: bool = False,
    bg_music_vol: float = 0.20,
    enable_orig_voice: bool = False,
    orig_voice_vol: float = 0.15,
    dub_volume: float = 1.0,
    progress_callback = None,
    file_list: list = None,
    save_only_video: bool = True,
) -> dict:
    """
    Automated Batch Pipeline:
    Transcribes media files in a folder -> Translates subtitles to natural Khmer ->
    Synthesizes Khmer voice-over (Edge-TTS Piseth/Sreymom) -> Auto-renders dubbed video with FFmpeg.

    When save_only_video=True (default), ONLY the finished rendered video (.mp4) is saved.
    Intermediate SRT and MP3/WAV audio files are automatically cleaned up.
    """
    valid_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".m4v", ".mp3", ".wav", ".m4a", ".aac"}
    media_files = []

    if file_list:
        for f in file_list:
            p = Path(f)
            if p.suffix.lower() in valid_exts and p.exists():
                media_files.append(p)
    elif folder_path:
        inp_dir = Path(folder_path)
        if not inp_dir.exists() or not inp_dir.is_dir():
            raise FileNotFoundError(f"Folder does not exist or is not a directory: {folder_path}")
        media_files = sorted([f for f in inp_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts])
    else:
        raise ValueError("Either folder_path or file_list must be provided.")

    if output_folder:
        out_dir = Path(output_folder)
    elif folder_path:
        out_dir = Path(folder_path) / "dubbed_outputs"
    else:
        out_dir = get_user_storage_dir() / "dubbed_batch_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    total_files = len(media_files)
    results = []

    if total_files == 0:
        return {
            "total_files": 0,
            "succeeded": 0,
            "failed": 0,
            "output_folder": str(out_dir.resolve()),
            "results": [],
            "message": "No compatible media files (.mp4, .mov, .mkv, .webm, .mp3, .wav, etc.) found in folder.",
        }

    user_storage = get_user_storage_dir()
    temp_work_dir = user_storage / "temp_batch_work"
    temp_work_dir.mkdir(parents=True, exist_ok=True)

    for i, media_file in enumerate(media_files, 1):
        f_name = media_file.name
        f_stem = media_file.stem
        is_vid = media_file.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".m4v"}
        temp_cleanup_files = []

        item_result = {
            "index": i,
            "filename": f_name,
            "original_path": str(media_file.resolve()),
            "status": "pending",
            "source_srt": None,
            "khmer_srt": None,
            "dubbed_audio": None,
            "output_video": None,
            "error": None,
        }

        def report(step_text: str):
            if progress_callback:
                try:
                    progress_callback(i, total_files, f"[{i}/{total_files}] {f_name}: {step_text}", item_result)
                except Exception:
                    pass

        try:
            # 1. Transcribe speech to text
            t_key = openai_key if model_name.startswith("openai") else (gemini_key if model_name.startswith("gemini") else "")
            if not t_key:
                _cfg = load_saved_config()
                t_key = _cfg.get("openai_api_key" if model_name.startswith("openai") else "gemini_api_key", "") or os.getenv("GEMINI_API_KEY", "")
            source_srt_content = transcribe_media(media_file, model_name=model_name, api_key=t_key)
            src_subs = parse_srt(source_srt_content)
            if not src_subs:
                raise ValueError("No speech segments detected in media.")

            clean_stem = re.sub(r"_dubbed(_[a-f0-9]+)?$", "", f_stem)

            if not save_only_video:
                src_srt_path = out_dir / f"{clean_stem}_source.srt"
                src_srt_path.write_text(source_srt_content, encoding="utf-8")
                item_result["source_srt"] = str(src_srt_path.resolve())

            # 2. Translate subtitles to Khmer
            report(f"🌐 Step 2/4: Translating {len(src_subs)} subtitles into natural Khmer...")
            khmer_subs = run_auto_translation(
                src_subs,
                source_language=source_language,
                gemini_key=gemini_key,
                openai_key=openai_key,
                model_name=model_name,
            )
            khmer_srt_content = render_srt(khmer_subs)

            if not save_only_video:
                khmer_srt_path = out_dir / f"{clean_stem}_khmer.srt"
                khmer_srt_path.write_text(khmer_srt_content, encoding="utf-8")
                item_result["khmer_srt"] = str(khmer_srt_path.resolve())
            else:
                khmer_srt_path = temp_work_dir / f"tmp_srt_{secrets.token_hex(8)}_khmer.srt"
                khmer_srt_path.write_text(khmer_srt_content, encoding="utf-8")
                temp_cleanup_files.append(khmer_srt_path)

            # 3. Voice-Over Synthesis in Khmer
            report(f"🔊 Step 3/4: Generating Khmer Voice-Over ({voice})...")
            subtitle_voices = {}
            if voice == "auto_detect":
                try:
                    seg_voices = classify_all_segments_piseth_sreymom(khmer_subs, media_path=str(media_file.resolve()))
                    if seg_voices:
                        subtitle_voices = {idx: v["voice"] for idx, v in seg_voices.items()}
                except Exception:
                    subtitle_voices = {}

            if not save_only_video or not is_vid:
                dubbed_audio_path = out_dir / (f"{clean_stem}_dubbed.mp3" if not is_vid else f"{clean_stem}_dubbed_audio.wav")
            else:
                dubbed_audio_path = temp_work_dir / f"tmp_audio_{secrets.token_hex(8)}_audio.wav"
                temp_cleanup_files.append(dubbed_audio_path)

            synthesize_full_audio(
                subtitles=khmer_subs,
                engine=tts_engine,
                voice=voice,
                speed=voice_speed,
                elevenlabs_key=elevenlabs_key,
                media_path=str(media_file.resolve()),
                output_audio_path=str(dubbed_audio_path.resolve()),
                subtitle_voices_override=subtitle_voices,
            )
            if not save_only_video or not is_vid:
                item_result["dubbed_audio"] = str(dubbed_audio_path.resolve())

            # 4. Auto Render Dubbed Video
            if is_vid:
                report("🎬 Step 4/4: Auto-rendering dubbed video with FFmpeg...")
                rendered_video_path = out_dir / f"{clean_stem}_dubbed.mp4"
                if rendered_video_path.resolve() == media_file.resolve():
                    rendered_video_path = out_dir / f"{clean_stem}_dubbed_{secrets.token_hex(3)}.mp4"
                process_video_dubbing(
                    video_path=str(media_file.resolve()),
                    audio_path=str(dubbed_audio_path.resolve()),
                    srt_path=str(khmer_srt_path.resolve()) if burn_subtitles else None,
                    dub_volume=dub_volume,
                    burn_subtitles=burn_subtitles,
                    enable_bg_music=enable_bg_music,
                    bg_music_vol=bg_music_vol,
                    enable_orig_voice=enable_orig_voice,
                    orig_voice_vol=orig_voice_vol,
                    output_video_path=str(rendered_video_path.resolve()),
                )
                item_result["output_video"] = str(rendered_video_path.resolve())
            else:
                item_result["output_video"] = str(dubbed_audio_path.resolve())

            # Clean up temporary intermediate files (SRT and Audio)
            for tmp_f in temp_cleanup_files:
                try:
                    if tmp_f.exists():
                        tmp_f.unlink()
                except Exception:
                    pass

            item_result["status"] = "success"
            report("✅ Complete!")

        except Exception as exc:
            # Clean up temporary intermediate files on error as well
            for tmp_f in temp_cleanup_files:
                try:
                    if tmp_f.exists():
                        tmp_f.unlink()
                except Exception:
                    pass
            item_result["status"] = "error"
            item_result["error"] = str(exc)
            report(f"❌ Error: {exc}")

        results.append(item_result)

    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")

    return {
        "total_files": total_files,
        "succeeded": succeeded,
        "failed": failed,
        "output_folder": str(out_dir.resolve()),
        "results": results,
    }


# Function alias for exact user prompt naming
transrcibe_one_folder = transcribe_one_folder


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
if "session_token" not in st.session_state:
    st.session_state.session_token = ""
if "session_lock_alert" not in st.session_state:
    st.session_state.session_lock_alert = ""

# Auto-Login with Saved Device Token
if not st.session_state.authenticated:
    device_token = st.query_params.get("device", "")
    saved_tokens = saved_config.get("device_tokens", {})
    if device_token and device_token in saved_tokens:
        tok_data = saved_tokens[device_token]
        tok_user = tok_data.get("user", "")
        _cfg_check = load_saved_config()
        auth_users = _cfg_check.get("auth_users", {})
        if tok_user in auth_users or tok_user == "admin":
            # Validate that this saved device token's session_token still matches the active one
            _tok_session = tok_data.get("session_token", "")
            _live_session = auth_users.get(tok_user, {}).get("active_session_token", "") if isinstance(auth_users.get(tok_user), dict) else ""
            if _tok_session and _tok_session == _live_session:
                st.session_state.authenticated = True
                st.session_state.auth_user = tok_user
                st.session_state.session_token = _tok_session
                st.session_state.current_device = tok_data.get("device_name", "Saved Device")
            else:
                # Session was taken over by another device — clear stale token
                st.query_params.clear()


def complete_user_login(username: str, remember: bool):
    dev_info = get_client_device_info()
    # Generate a unique session token to enforce single active session
    new_session_token = secrets.token_hex(24)

    _cfg = load_saved_config()
    auth_users = _cfg.get("auth_users", {})
    if username in auth_users:
        if isinstance(auth_users[username], dict):
            auth_users[username]["last_device"] = dev_info
            auth_users[username]["last_login"] = time.strftime("%Y-%m-%d %H:%M")
            auth_users[username]["active_session_token"] = new_session_token
            auth_users[username]["active_device_name"] = dev_info.get("device_name", "")
        else:
            auth_users[username] = {
                "password": auth_users[username],
                "role": "admin" if username == "admin" else "user",
                "status": "approved",
                "last_device": dev_info,
                "last_login": time.strftime("%Y-%m-%d %H:%M"),
                "active_session_token": new_session_token,
                "active_device_name": dev_info.get("device_name", ""),
            }
    elif username == "admin":
        auth_users["admin"] = {
            "password": "dubber123",
            "role": "admin",
            "status": "approved",
            "last_device": dev_info,
            "last_login": time.strftime("%Y-%m-%d %H:%M"),
            "active_session_token": new_session_token,
            "active_device_name": dev_info.get("device_name", ""),
        }

    updates = {"auth_users": auth_users}
    if remember:
        token = secrets.token_hex(16)
        dev_tokens = _cfg.get("device_tokens", {})
        dev_tokens[token] = {
            "user": username,
            "session_token": new_session_token,
            **dev_info
        }
        updates["device_tokens"] = dev_tokens
        st.query_params["device"] = token

    save_saved_config(updates)
    st.session_state.authenticated = True
    st.session_state.auth_user = username
    st.session_state.session_token = new_session_token
    st.session_state.current_device = dev_info.get("device_name", "Saved Device")
    st.session_state.session_lock_alert = ""
    st.toast(f"Welcome back, {username}! 🎉", icon="🎉")
    st.rerun()


if not st.session_state.authenticated:
    # Full widescreen layout: Left side = Studio Showcase, Features & Customer Reviews (Ratings); Right side = Sign In & Sign Up + Quick Admin Contact
    col_showcase, col_auth = st.columns([1.25, 1], gap="large")

    with col_showcase:
        st.markdown(
            """<div style="background: linear-gradient(145deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.95) 100%); border: 1px solid rgba(56, 189, 248, 0.28); border-radius: 20px; padding: 26px 28px; margin-bottom: 16px;">
<div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); padding: 5px 14px; border-radius: 999px; color: #38bdf8; font-size: 0.78rem; font-weight: 700; margin-bottom: 14px;">
🎙️ AI LOCALIZATION & VIDEO DUBBING STUDIO
</div>
<h1 style="font-size: 2.2rem; font-weight: 800; color: #ffffff; margin: 0 0 10px 0; line-height: 1.25;">
Dubber AI <span style="background: linear-gradient(135deg, #38bdf8 0%, #34d399 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Pro Studio</span>
</h1>
<p style="font-size: 0.96rem; color: #cbd5e1; line-height: 1.65; margin: 0 0 18px 0;">
ប្រព័ន្ធ AI ស្វ័យប្រវត្តិកម្រិតខ្ពស់សម្រាប់ទាញយកសំឡេង ស្រង់ Subtitles បកប្រែជាភាសាខ្មែរ និងបញ្ចូលសំឡេងស្វ័យប្រវត្តិ (Whisper AI + Microsoft Edge Neural TTS) បង្កើតវីដេអូ TikTok, Reels, YouTube រហ័ស និងមានគុណភាពខ្ពស់បំផុត!
</p>
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 8px;">
<div style="background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 12px; padding: 12px 14px;">
<div style="font-size: 0.92rem; font-weight: 700; color: #38bdf8;">⚡ 1-Click Folder Dubbing</div>
<div style="font-size: 0.78rem; color: #94a3b8; margin-top: 3px;">បកប្រែ និងបញ្ចូលសម្លេងម្ដងមួយ Folder ស្វ័យប្រវត្តិ មិនបាច់រង់ចាំយូរ</div>
</div>
<div style="background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 12px; padding: 12px 14px;">
<div style="font-size: 0.92rem; font-weight: 700; color: #34d399;">🎭 Dual Voice System</div>
<div style="font-size: 0.78rem; color: #94a3b8; margin-top: 3px;">និយាយប្រុសផងស្រីផងក្នុងវីដេអូតែមួយ (Piseth 👨 + Sreymom 👩)</div>
</div>
<div style="background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 12px; padding: 12px 14px;">
<div style="font-size: 0.92rem; font-weight: 700; color: #fbbf24;">📝 Khmer Hardsub Burner</div>
<div style="font-size: 0.78rem; color: #94a3b8; margin-top: 3px;">បង្កប់ Subtitle ខ្មែរលើវីដេអូច្បាស់ស្អាត Font ខ្មែរត្រឹមត្រូវ</div>
</div>
<div style="background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 12px; padding: 12px 14px;">
<div style="font-size: 0.92rem; font-weight: 700; color: #a78bfa;">📱 Multi-Platform Ready</div>
<div style="font-size: 0.78rem; color: #94a3b8; margin-top: 3px;">ដំណើរការយ៉ាងរលូនទាំងលើទូរស័ព្ទដៃ Smartphone និងកុំព្យូទ័រ PC</div>
</div>
</div>
</div>""",
            unsafe_allow_html=True,
        )

    with col_auth:
        # Show session-lock warning if kicked out by another device
        _lock_msg = st.session_state.get("session_lock_alert", "")
        if _lock_msg:
            st.markdown(
                f"""<div style="background: linear-gradient(135deg, rgba(239,68,68,0.18) 0%, rgba(15,23,42,0.95) 100%);
border: 2px solid rgba(239,68,68,0.55); border-radius: 16px; padding: 18px 20px;
margin-bottom: 1.2rem; text-align: center;">
<div style="font-size: 1.5rem; margin-bottom: 6px;">⚠️</div>
<div style="font-size: 0.95rem; font-weight: 700; color: #f87171; margin-bottom: 6px;">ការព្រមាន / Security Alert</div>
<div style="font-size: 0.87rem; color: #fca5a5; line-height: 1.65;">{_lock_msg}</div>
</div>""",
                unsafe_allow_html=True,
            )
            st.session_state.session_lock_alert = ""

        st.markdown(
            """<div class="login-container-card" style="margin-top: 0; padding: 1.8rem 1.6rem;">
<div class="login-badge">🔒 Studio Access Portal</div>
<div style="font-size: 2.2rem; margin: 0.2rem 0 0.3rem 0;">🎙️</div>
<h2 class="login-title-text" style="font-size: 1.5rem;">ចូលប្រើប្រាស់ Studio</h2>
<p class="login-desc-text" style="font-size: 0.85rem; margin-bottom: 0;">Sign in to your account or register for new studio access.</p>
</div>""",
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
                    _fresh_cfg = load_saved_config()
                    auth_users = _fresh_cfg.get("auth_users", {})
                    pending_users = _fresh_cfg.get("pending_users", {})

                    _valid_login = False
                    if login_username in pending_users:
                        st.warning("⏳ **Account Pending Approval**: Your registration has been submitted and is currently awaiting administrator review. Please check back soon.")
                        render_contact_admin(key_prefix="login_pending", compact=False)
                    elif login_username in auth_users:
                        expected_pw = get_user_password(auth_users[login_username])
                        if login_password == expected_pw:
                            _valid_login = True
                        else:
                            st.error("❌ Incorrect password. Please try again.")
                    elif login_username == "admin" and login_password in ("dubber123", "admin123"):
                        _valid_login = True
                    else:
                        st.error("❌ Invalid username or password. If you don't have an account, click 'Create Account' above.")

                    if _valid_login:
                        complete_user_login(login_username, save_device)

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
                _fresh_cfg2 = load_saved_config()
                auth_users = _fresh_cfg2.get("auth_users", {})
                pending_users = _fresh_cfg2.get("pending_users", {})

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
                    render_contact_admin(key_prefix="reg_already_pending", compact=False)
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
                    st.info("⏳ Your account is now **waiting for administrator approval**. You can contact the admin below to request fast activation:")
                    render_contact_admin(key_prefix="reg_success", compact=False)

        st.markdown("---")
        render_contact_admin(key_prefix="auth_page_footer", compact=False)
    st.stop()

# ==========================================
# Single-Session Verification Gate
# ==========================================
_gate_user = st.session_state.get("auth_user", "")
_gate_token = st.session_state.get("session_token", "")
if _gate_user and _gate_token:
    _gate_cfg = load_saved_config()
    _gate_users = _gate_cfg.get("auth_users", {})
    _live_token = _gate_users.get(_gate_user, {}).get("active_session_token", "") if isinstance(_gate_users.get(_gate_user), dict) else ""
    if _live_token and _live_token != _gate_token:
        # Another device logged in and took over this account
        st.session_state.authenticated = False
        st.session_state.auth_user = ""
        st.session_state.session_token = ""
        st.session_state.current_device = ""
        st.session_state.session_lock_alert = (
            "⚠️ គណនីនេះត្រូវបានចូលប្រើ (Login) នៅលើឧបករណ៍ផ្សេងទៀតរួចហើយ!\n"
            "មួយគណនីអាចប្រើប្រាស់បានតែ ១ ឧបករណ៍ប៉ុណ្ណោះ មិនអាចប្រើដំណាលគ្នាបានទេ។"
        )
        st.query_params.clear()
        st.rerun()

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
# Session State Initialization & Auto-Restore
# ==========================================
_curr_auth_user = st.session_state.get("auth_user", "")
_user_storage_init = get_user_storage_dir(_curr_auth_user)

# When a user logs in or switches, reset session state so videos never collide between accounts
if st.session_state.get("_active_session_user") != _curr_auth_user:
    st.session_state._active_session_user = _curr_auth_user
    st.session_state.source_srt = ""
    st.session_state.khmer_srt = ""
    st.session_state.uploaded_media_path = ""
    st.session_state.is_video = False
    st.session_state.dubbed_audio_bytes = None
    st.session_state.dubbed_audio_path = ""
    st.session_state.output_video_path = ""
    st.session_state.subtitle_voices = {}
    st.session_state.detected_voice_info = None
    st.session_state.batch_dub_results = None
    st.session_state.batch_folder_path = ""
    st.session_state.batch_media_files = []
    st.session_state.batch_target_folder = ""

    # Restore from this user's private storage folder only
    if _curr_auth_user:
        _init_video = _user_storage_init / "dubbed_output.mp4"
        _init_audio = _user_storage_init / "dubbed_voiceover.wav"
        _init_srt = _user_storage_init / "burn_subtitles.srt"
        _init_media = _user_storage_init / "uploaded_media.mp4"
        if not _init_media.exists():
            _init_media = _user_storage_init / "target_video.mp4"

        if _init_srt.exists():
            try:
                st.session_state.khmer_srt = _init_srt.read_text(encoding="utf-8")
            except Exception:
                pass
        if _init_media.exists():
            st.session_state.uploaded_media_path = str(_init_media.resolve())
            st.session_state.is_video = True
        if _init_audio.exists():
            try:
                st.session_state.dubbed_audio_bytes = _init_audio.read_bytes()
                st.session_state.dubbed_audio_path = str(_init_audio.resolve())
            except Exception:
                pass
        if _init_video.exists():
            st.session_state.output_video_path = str(_init_video.resolve())

        _user_batch_in = _user_storage_init / "batch_input"
        if _user_batch_in.exists():
            _found_b = sorted([f for f in _user_batch_in.rglob("*") if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".m4v", ".mp3", ".wav", ".m4a", ".aac"}])
            if _found_b:
                st.session_state.batch_media_files = _found_b
                st.session_state.batch_target_folder = str(_user_batch_in.resolve())

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
if st.session_state.get("voice_btn_selection") not in VOICE_BUTTON_OPTIONS:
    st.session_state.voice_btn_selection = VOICE_BUTTON_OPTIONS[0]
if "sb_voice_pills" in st.session_state and st.session_state.sb_voice_pills not in VOICE_BUTTON_OPTIONS:
    del st.session_state["sb_voice_pills"]
if "t1_voice_pills" in st.session_state and st.session_state.t1_voice_pills not in VOICE_BUTTON_OPTIONS:
    del st.session_state["t1_voice_pills"]
if "voice_gender_counts" not in st.session_state:
    st.session_state.voice_gender_counts = {"male": 0, "female": 0}
if "batch_dub_results" not in st.session_state:
    st.session_state.batch_dub_results = None
if "batch_folder_path" not in st.session_state:
    st.session_state.batch_folder_path = ""

# Auto-classify segment voices if SRT and media are present but voices not yet loaded
if not st.session_state.subtitle_voices and st.session_state.khmer_srt and st.session_state.uploaded_media_path and Path(st.session_state.uploaded_media_path).exists():
    try:
        _loaded_subs = parse_srt(st.session_state.khmer_srt)
        _auto_seg_v = classify_all_segments_piseth_sreymom(_loaded_subs, media_path=st.session_state.uploaded_media_path)
        if _auto_seg_v:
            st.session_state.subtitle_voices = {idx: v["voice"] for idx, v in _auto_seg_v.items()}
            st.session_state.subtitle_voice_details = _auto_seg_v
            _mc = sum(1 for v in _auto_seg_v.values() if v.get("gender") == "Male")
            _fc = sum(1 for v in _auto_seg_v.values() if v.get("gender") == "Female")
            st.session_state.voice_gender_counts = {"male": _mc, "female": _fc}
    except Exception:
        pass

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
        # Clear active_session_token so account is freed for another device
        _logout_user = st.session_state.get("auth_user", "")
        _logout_auth = cfg.get("auth_users", {})
        if _logout_user in _logout_auth and isinstance(_logout_auth[_logout_user], dict):
            _logout_auth[_logout_user]["active_session_token"] = ""
            _logout_auth[_logout_user]["active_device_name"] = ""
        save_saved_config({"device_tokens": dev_tokens, "auth_users": _logout_auth})
        st.query_params.clear()
        st.session_state.authenticated = False
        st.session_state.auth_user = ""
        st.session_state.current_device = ""
        st.session_state.session_token = ""
        st.toast("Logged out and device disconnected.")
        st.rerun()

    st.markdown("---")
    st.markdown("### ⚙️ Pipeline Configuration")
    
    pipeline_model = st.selectbox(
        "Speech Transcription Model",
        [
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3-flash-preview",
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
        st.markdown("**ជ្រើសរើសសម្លេង (Voice Mode):**")
        cur_sb_v = st.session_state.get("voice_btn_selection", "🎭 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Piseth 👨 + Sreymom 👩)")
        if cur_sb_v not in VOICE_BUTTON_OPTIONS:
            cur_sb_v = "🎭 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Piseth 👨 + Sreymom 👩)"

        if "sb_voice_pills" in st.session_state and st.session_state.sb_voice_pills not in VOICE_BUTTON_OPTIONS:
            del st.session_state["sb_voice_pills"]
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
                st.caption(f"🎭 **និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ**: **{m_c} 👨 Piseth** + **{f_c} 👩 Sreymom**")
            else:
                det_sb = st.session_state.get("detected_voice_info")
                if det_sb:
                    st.caption(f"🎯 Default: **{det_sb.get('icon', '🎙️')} {det_sb.get('name', 'Piseth Neural')}** ({det_sb.get('pitch', 130)} Hz)")
                else:
                    st.caption("🎭 ចាប់សម្លេងតួអង្គប្រុស & ស្រី (Piseth 👨 + Sreymom 👩) ក្នុងវិដេអូតែមួយ")
        elif chosen_voice == "km-KH-PisethNeural":
            st.caption("👨 សម្លេងប្រុសតែម្នាក់ឯង: **Piseth Neural** (Khmer Male / ប្រុស)")
        elif chosen_voice == "km-KH-SreymomNeural":
            st.caption("👩 សម្លេងស្រីតែម្នាក់ឯង: **Sreymom Neural** (Khmer Female / ស្រី)")

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
    st.markdown("---")
    render_contact_admin(key_prefix="sidebar_support", compact=True)

# ==========================================
# Main Studio Tabs
# ==========================================
is_admin_user = st.session_state.get("auth_user", "") == "admin"
pending_dict = saved_config.get("pending_users", {})
num_pending = len(pending_dict)
admin_msgs = saved_config.get("admin_messages", [])
num_unread_msgs = sum(1 for m in admin_msgs if m.get("status") == "unread")

if is_admin_user:
    badges = []
    if num_pending > 0:
        badges.append(f"{num_pending} pending")
    if num_unread_msgs > 0:
        badges.append(f"{num_unread_msgs} ✉️")
    badge_str = f" ({', '.join(badges)})" if badges else ""
    cust_tab_title = f"06 👥 Customers{badge_str}"
    tab_transcribe, tab_batch_folder, tab_translate, tab_editor_voice, tab_video, tab_customers = st.tabs([
        "01 🎙️ Transcribe",
        "02 📁 Folder Auto-Dub",
        "03 🌐 Translate",
        "04 ✏️ Voice & Edit",
        "05 🎬 Video Studio",
        cust_tab_title,
    ])
else:
    tab_transcribe, tab_batch_folder, tab_translate, tab_editor_voice, tab_video = st.tabs([
        "01 🎙️ Transcribe",
        "02 📁 Folder Auto-Dub",
        "03 🌐 Translate",
        "04 ✏️ Voice & Edit",
        "05 🎬 Video Studio",
    ])
    tab_customers = None

# Global Video Preview Banner if video is ready
if st.session_state.output_video_path and Path(st.session_state.output_video_path).exists():
    with st.expander("🎬 **ទស្សនាវិដេអូដែលបានបញ្ចូលសម្លេងរួចរាល់ (Click to Watch Dubbed Video Preview)**", expanded=False):
        render_video_preview(st.session_state.output_video_path)
        with open(st.session_state.output_video_path, "rb") as vf_top:
            v_top_bytes = vf_top.read()
        st.download_button(
            "📥 Download Dubbed Video (.MP4)",
            data=v_top_bytes,
            file_name="dubbed_studio_output.mp4",
            mime="video/mp4",
            use_container_width=True,
            key="dl_video_top_banner",
        )

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
            save_media_path = get_user_storage_dir() / f"uploaded_media{input_suffix}"
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
                        <span style="font-weight: 700; color: #f8fafc; font-size: 0.90rem;">🎙️ ជម្រើសសម្លេងតួអង្គ (Voice Mode)</span>
                        <span style="font-size: 0.70rem; color: #38bdf8; background: rgba(56, 189, 248, 0.15); padding: 2px 7px; border-radius: 6px; font-weight: 600;">1-Click</span>
                    </div>
                    <p style="font-size: 0.74rem; color: #94a3b8; margin: 0 0 8px 0;">ជ្រើសរើស <b>និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ</b> (ស្វ័យប្រវត្ត) ឬកំណត់យកតែសម្លេងប្រុស ឬសម្លេងស្រីសុទ្ធ។</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            t1_cur_voice = st.session_state.get("voice_btn_selection", "🎭 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Piseth 👨 + Sreymom 👩)")
            if t1_cur_voice not in VOICE_BUTTON_OPTIONS:
                t1_cur_voice = "🎭 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Piseth 👨 + Sreymom 👩)"

            if "t1_voice_pills" in st.session_state and st.session_state.t1_voice_pills not in VOICE_BUTTON_OPTIONS:
                del st.session_state["t1_voice_pills"]
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
                    st.caption(f"🎭 **និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ**: **{m_c} 👨 Piseth (ប្រុស)** + **{f_c} 👩 Sreymom (ស្រី)**")
                else:
                    det = st.session_state.get("detected_voice_info")
                    if det:
                        st.caption(f"🎯 Default: **{det.get('icon', '🎙️')} {det.get('name', 'Piseth Neural')}** ({det.get('pitch', 130)} Hz)")
                    else:
                        st.caption("🎭 ចាប់សម្លេងតួអង្គស្វ័យប្រវត្តិ (តួប្រុស ➔ Piseth 👨 + តួស្រី ➔ Sreymom 👩 ក្នុងវិដេអូតែមួយ)")
            elif active_t1_voice == "km-KH-PisethNeural":
                st.caption("👨 សម្លេងប្រុសតែម្នាក់ឯង: **Piseth Neural** (Khmer Male Voice / ប្រុស)")
            elif active_t1_voice == "km-KH-SreymomNeural":
                st.caption("👩 សម្លេងស្រីតែម្នាក់ឯង: **Sreymom Neural** (Khmer Female Voice / ស្រី)")
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
                                srt_temp = get_user_storage_dir() / "burn_subtitles.srt"
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
                                st.success("🎉 ដំណើរការផលិតវិដេអូបានចប់សព្វគ្រប់ 100%! (Dubbing Complete!)")
                                st.markdown("#### 🎬 ទស្សនាវិដេអូដែលបានបញ្ចូលសម្លេង (Dubbed Video Preview):")
                                render_video_preview(final_v)
                                with open(final_v, "rb") as vf_col1:
                                    v_done_b1 = vf_col1.read()
                                st.download_button(
                                    "📥 Download Dubbed Video (.MP4)",
                                    data=v_done_b1,
                                    file_name="dubbed_studio_output.mp4",
                                    mime="video/mp4",
                                    use_container_width=True,
                                    key="dl_video_col1_immediate",
                                )
            except Exception as e:
                st.error(f"Error: {e}")

    with col2:
        if st.session_state.output_video_path and Path(st.session_state.output_video_path).exists():
            st.markdown(
                """
                <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 12px; padding: 12px 14px; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span style="font-weight: 700; color: #34d399; font-size: 1rem;">🎬 វិដេអូដែលបានផលិតរួចរាល់ (Dubbed Video Preview)</span>
                        <span style="font-size: 0.72rem; color: #10b981; background: rgba(16, 185, 129, 0.2); padding: 2px 8px; border-radius: 6px; font-weight: 700;">Ready to Watch</span>
                    </div>
                    <div style="font-size: 0.8rem; color: #cbd5e1; margin-top: 4px;">ចុច Play ខាងក្រោមដើម្បីទស្សនាវិដេអូដែលមានសម្លេងតួអង្គប្រុស & ស្រីឆ្លាស់គ្នា!</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_video_preview(st.session_state.output_video_path)
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
                    if has_thai_characters(st.session_state.khmer_srt):
                        st.error("⚠️ **រកឃើញអក្សរថៃក្នុងអត្ថបទ (Thai Language Detected)**: ចុចប៊ូតុងខាងក្រោមដើម្បីប្តូរទៅជាភាសាខ្មែរ 100% ភ្លាមៗ!")
                        if st.button("🇰🇭 ប្តូរអក្សរថៃទាំងអស់ទៅជាភាសាខ្មែរ 100% (Clean All Thai to Khmer)", type="primary", use_container_width=True, key="btn_fix_thai_tab1"):
                            with st.spinner("កំពុងប្តូរអក្សរថៃទៅជាភាសាខ្មែរ 100%..."):
                                cur_subs = parse_srt(st.session_state.khmer_srt)
                                fixed_subs = purge_and_enforce_khmer(cur_subs, gemini_key=gemini_key, openai_key=openai_key, model_name=pipeline_model)
                                st.session_state.khmer_srt = render_srt(fixed_subs)
                                st.toast("✅ បានប្តូរអក្សរថៃទៅជាភាសាខ្មែរ 100% ដោយជោគជ័យ!", icon="🇰🇭")
                                st.rerun()
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

def open_native_folder_picker(initial_dir: str = "") -> str:
    """Opens a native Windows FolderBrowserDialog via PowerShell on Windows."""
    if sys.platform != "win32":
        return ""
    try:
        init_p = str(Path(initial_dir).resolve()).replace("'", "''") if (initial_dir and Path(initial_dir).exists()) else ""
        ps_script = (
            '[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null; '
            '$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; '
            '$dialog.Description = "Dubber AI Studio - ជ្រើសរើស Folder វីដេអូ"; '
            '$dialog.ShowNewFolderButton = $true; '
            + (f"if (Test-Path '{init_p}') {{ $dialog.SelectedPath = '{init_p}' }}; " if init_p else "")
            + '$res = $dialog.ShowDialog(); '
            'if ($res -eq [System.Windows.Forms.DialogResult]::OK) { '
            '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; '
            '[Console]::WriteLine($dialog.SelectedPath); '
            '}'
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if res.returncode == 0:
            for line in reversed(res.stdout.splitlines()):
                line = line.strip()
                if line and Path(line).exists() and Path(line).is_dir():
                    return str(Path(line).resolve())
    except Exception:
        pass
    return ""


# ----------------------------------------------------
# TAB 02: Folder Batch Auto-Dubbing
# ----------------------------------------------------
with tab_batch_folder:
    st.markdown(
        """
        <div class="tab-header">
            <h3>Step 1B: Transcribe One Folder (All-in-One Auto Pipeline)</h3>
            <p style="color: #94a3b8; margin: 0;">
                ដំណើរការស្វ័យប្រវត្តិកម្មផលិតវិដេអូជាបាច់ក្នុង 1 ថត៖ <b>ចម្លងសម្លេង (Transcribe)</b> ➔ <b>បកប្រែភាសាខ្មែរ (Khmer)</b> ➔ <b>បញ្ចូលសម្លេង (Voice-Over)</b> ➔ <b>Auto Render វិដេអូ (.MP4)</b> ស្រេចដោយស្វ័យប្រវត្ត។
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    batch_col1, batch_col2 = st.columns([1.1, 1], gap="medium")

    with batch_col1:
        st.markdown("#### 📂 1. ជ្រើសរើសវីដេអូសម្រាប់ Dubbing (Select Videos)")

        curr_auth_u = st.session_state.get("auth_user", "guest")
        user_storage = get_user_storage_dir(curr_auth_u)
        user_batch_in = user_storage / "batch_input"
        user_batch_out = user_storage / "batch_outputs"
        user_batch_in.mkdir(parents=True, exist_ok=True)
        user_batch_out.mkdir(parents=True, exist_ok=True)

        if "batch_media_files" not in st.session_state:
            st.session_state.batch_media_files = []

        valid_exts = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".m4v", ".mp3", ".wav", ".m4a", ".aac"}

        user_session_folder_key = f"batch_folder_path_{curr_auth_u}"
        def_pc_path = st.session_state.get(user_session_folder_key) or str(user_batch_in.resolve())

        batch_input_mode = st.radio(
            "ជ្រើសរើសវិធីសាស្ត្រជ្រើសរើស Folder (Folder Input Method):",
            [
                "📁 ជ្រើសរើស Folder លើកុំព្យូទ័រ (Folder Path on Computer / Network / Presets)",
                "🌐 ជ្រើសរើស Folder តាម Browser (Browser Folder Picker - All Computers & Laptops)",
            ],
            horizontal=True,
            key="batch_input_mode_selector",
        )

        if "Folder Path on Computer" in batch_input_mode:
            # 1. Native Windows Browse Folder Button & Reset
            c_browse, c_rst = st.columns([1.6, 1])
            with c_browse:
                if st.button("📂 ចុចបើកជ្រើសរើស Folder (Browse Windows Folder)", key="btn_open_win_folder_dialog", type="primary", use_container_width=True):
                    with st.spinner("កំពុងបើកផ្ទាំងជ្រើសរើស Folder (Folder Browser Dialog)..."):
                        picked = open_native_folder_picker(def_pc_path)
                        if picked:
                            st.session_state[user_session_folder_key] = picked
                            st.session_state.batch_target_folder = picked
                            st.session_state.explorer_current_dir = picked
                            st.toast(f"✅ បានជ្រើសរើស Folder: {picked}", icon="📁")
                            st.rerun()
            with c_rst:
                if st.button("🔄 Folder ដើមរបស់ខ្ញុំ", key="btn_pc_reset_default", use_container_width=True):
                    st.session_state[user_session_folder_key] = str(user_batch_in.resolve())
                    st.session_state.batch_target_folder = str(user_batch_in.resolve())
                    st.session_state.explorer_current_dir = str(user_batch_in.resolve())
                    st.rerun()

            # 2. Preset Folder Shortcuts
            st.markdown("<p style='font-size:0.83rem; color:#94a3b8; margin: 4px 0;'>⚡ ផ្លូវកាត់ Folder ពេញនិយម (Quick Shortcuts):</p>", unsafe_allow_html=True)
            sc_cols = st.columns(4)
            with sc_cols[0]:
                vid_dir = Path.home() / "Videos"
                if vid_dir.exists() and st.button("🎥 Videos", key="btn_q_vid", use_container_width=True):
                    st.session_state[user_session_folder_key] = str(vid_dir.resolve())
                    st.session_state.batch_target_folder = str(vid_dir.resolve())
                    st.session_state.explorer_current_dir = str(vid_dir.resolve())
                    st.rerun()
            with sc_cols[1]:
                down_dir = Path.home() / "Downloads"
                if down_dir.exists() and st.button("📥 Downloads", key="btn_q_down", use_container_width=True):
                    st.session_state[user_session_folder_key] = str(down_dir.resolve())
                    st.session_state.batch_target_folder = str(down_dir.resolve())
                    st.session_state.explorer_current_dir = str(down_dir.resolve())
                    st.rerun()
            with sc_cols[2]:
                desk_dir = Path.home() / "Desktop"
                if desk_dir.exists() and st.button("🖥️ Desktop", key="btn_q_desk", use_container_width=True):
                    st.session_state[user_session_folder_key] = str(desk_dir.resolve())
                    st.session_state.batch_target_folder = str(desk_dir.resolve())
                    st.session_state.explorer_current_dir = str(desk_dir.resolve())
                    st.rerun()
            with sc_cols[3]:
                d_drive = Path("D:/")
                if d_drive.exists() and st.button("💾 D: Drive", key="btn_q_d_drive", use_container_width=True):
                    st.session_state[user_session_folder_key] = "D:/"
                    st.session_state.batch_target_folder = "D:/"
                    st.session_state.explorer_current_dir = "D:/"
                    st.rerun()
                elif Path("C:/").exists() and st.button("💾 C: Drive", key="btn_q_c_drive", use_container_width=True):
                    st.session_state[user_session_folder_key] = "C:/"
                    st.session_state.batch_target_folder = "C:/"
                    st.session_state.explorer_current_dir = "C:/"
                    st.rerun()

            # 2B. Hongguo Drama Series Quick Selector
            hongguo_base = Path.home() / "Videos" / "Hongguo"
            if not hongguo_base.exists():
                hongguo_base = Path("D:/Tool Download movie chin/Hongguo")

            if hongguo_base.exists():
                drama_list = sorted([d.name for d in hongguo_base.iterdir() if d.is_dir()])
                if drama_list:
                    st.markdown("<p style='font-size:0.83rem; color:#38bdf8; margin: 6px 0 2px 0;'>🎬 ជ្រើសរើសរឿងចិនពី Hongguo (Hongguo Drama Series):</p>", unsafe_allow_html=True)
                    col_hg1, col_hg2 = st.columns([2, 1])
                    with col_hg1:
                        sel_drama = st.selectbox("រឿងដែលមានស្រាប់:", ["-- ជ្រើសរើសរឿង --"] + drama_list, key="sel_hongguo_drama", label_visibility="collapsed")
                    with col_hg2:
                        if sel_drama != "-- ជ្រើសរើសរឿង --" and st.button("▶️ ជ្រើសរើសរឿងនេះ", key="btn_apply_hongguo_drama", use_container_width=True):
                            drama_p = hongguo_base / sel_drama
                            st.session_state[user_session_folder_key] = str(drama_p.resolve())
                            st.session_state.batch_target_folder = str(drama_p.resolve())
                            st.session_state.explorer_current_dir = str(drama_p.resolve())
                            st.toast(f"✅ បានជ្រើសរើសរឿង: {sel_drama}!", icon="🎬")
                            st.rerun()

            # 3. Interactive In-Browser Visual Folder Tree Explorer
            if "explorer_current_dir" not in st.session_state:
                st.session_state.explorer_current_dir = def_pc_path if (Path(def_pc_path).exists() and Path(def_pc_path).is_dir()) else str(Path.home().resolve())

            exp_curr = Path(st.session_state.explorer_current_dir)
            if not exp_curr.exists() or not exp_curr.is_dir():
                exp_curr = Path.home()
                st.session_state.explorer_current_dir = str(exp_curr.resolve())

            with st.expander("🔍 រុករកមើល Folder (Interactive Folder Browser)", expanded=False):
                st.caption(f"📁 ទីតាំងបច្ចុប្បន្ន: `{exp_curr.resolve()}`")
                c_up, c_sel = st.columns([1, 1.4])
                with c_up:
                    p_up = exp_curr.parent
                    if p_up and p_up != exp_curr and p_up.exists():
                        if st.button("⬆️ ឡើងលើ 1 កម្រិត (Up)", key="btn_nav_up", use_container_width=True):
                            st.session_state.explorer_current_dir = str(p_up.resolve())
                            st.rerun()
                with c_sel:
                    if st.button("🎯 ជ្រើសរើស Folder នេះ", key="btn_nav_sel_curr", type="primary", use_container_width=True):
                        st.session_state[user_session_folder_key] = str(exp_curr.resolve())
                        st.session_state.batch_target_folder = str(exp_curr.resolve())
                        st.toast(f"✅ បានជ្រើសរើស: {exp_curr.name or str(exp_curr.resolve())}", icon="📁")
                        st.rerun()

                try:
                    sub_dirs = sorted([d for d in exp_curr.iterdir() if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("$")])
                    if sub_dirs:
                        cols_per_row = 2
                        for chunk_idx in range(0, min(len(sub_dirs), 30), cols_per_row):
                            c_dirs = st.columns(cols_per_row)
                            for c_i, d_obj in enumerate(sub_dirs[chunk_idx:chunk_idx+cols_per_row]):
                                with c_dirs[c_i]:
                                    try:
                                        v_cnt = sum(1 for vf in d_obj.iterdir() if vf.is_file() and vf.suffix.lower() in valid_exts)
                                        v_badge = f" ({v_cnt} 🎬)" if v_cnt > 0 else ""
                                    except Exception:
                                        v_badge = ""
                                    if st.button(f"📁 {d_obj.name}{v_badge}", key=f"f_nav_{d_obj.name}_{chunk_idx}_{c_i}", use_container_width=True):
                                        st.session_state.explorer_current_dir = str(d_obj.resolve())
                                        st.rerun()
                    else:
                        st.caption("ℹ️ គ្មាន Subfolder នៅក្នុង Folder នេះទេ។")
                except PermissionError:
                    st.warning("⚠️ គ្មានសិទ្ធិបើកមើល Folder នេះទេ។")
                except Exception:
                    pass

            # 4. Direct Manual Folder Path Input
            pc_path_input = st.text_input(
                "📁 ទីតាំង Folder លើកុំព្យូទ័រ (Folder Path):",
                value=def_pc_path,
                key="pc_path_txt_in",
                help="បញ្ចូលផ្លូវ Folder ដូចជា D:/Videos ឬ C:/Users/.../Videos ឬ \\\\192.168.1.5\\Shared",
            )
            clean_p = pc_path_input.strip().strip('"').strip("'") if pc_path_input else ""

            # Smart path normalizer for client username mismatch (e.g. C:\Users\Adsservicevip\Videos\... on server host)
            if clean_p and not Path(clean_p).exists() and ("\\Videos\\" in clean_p or "/Videos/" in clean_p):
                tail_part = re.split(r"[\\/]Videos[\\/]", clean_p, flags=re.IGNORECASE)[-1]
                mapped_local = Path.home() / "Videos" / tail_part
                if mapped_local.exists():
                    clean_p = str(mapped_local.resolve())
                else:
                    srv_mapped = BASE_STORAGE_DIR / tail_part
                    if srv_mapped.exists():
                        clean_p = str(srv_mapped.resolve())

            st.session_state[user_session_folder_key] = clean_p

            if clean_p:
                p_obj = Path(clean_p)
                if p_obj.exists() and p_obj.is_dir():
                    found_p_files = sorted([f for f in p_obj.iterdir() if f.is_file() and f.suffix.lower() in valid_exts])
                    st.session_state.batch_media_files = found_p_files
                    st.session_state.batch_target_folder = clean_p
                    if found_p_files:
                        st.success(f"✓ បានស្កេនឃើញ {len(found_p_files)} វីដេអូក្នុង Folder `{p_obj.name or clean_p}` ស្រេចសម្រាប់ Dubbing!")
                    else:
                        st.info(f"📂 Folder `{p_obj.name or clean_p}` ត្រឹមត្រូវ ប៉ុន្តែមិនទាន់មានឯកសារវីដេអូ (.mp4, .mov, .mkv, ...) ទេ។")
                else:
                    st.warning(f"⚠️ រកមិនឃើញ Folder: `{clean_p}` លើ Server ទេ។")
                    st.markdown(
                        "<div style='font-size:0.83rem; color:#cbd5e1; margin-bottom:8px;'>"
                        "💡 ប្រសិនបើអ្នកកំពុងប្រើប្រាស់ពីកុំព្យូទ័រផ្សេង (Client PC/Laptop/Mac/Phone) សូមជ្រើសរើសជម្រើស <b>'🌐 ជ្រើសរើស Folder តាម Browser'</b> ខាងលើដើម្បីជ្រើសរើស Folder ពីកុំព្យូទ័ររបស់អ្នកផ្ទាល់!"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button("➕ បង្កើត Folder នេះឥឡូវនេះ (Create Folder)", key="btn_make_dir"):
                        try:
                            p_obj.mkdir(parents=True, exist_ok=True)
                            st.success("✓ បានបង្កើត Folder រួចរាល់!")
                            st.session_state.batch_target_folder = clean_p
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

        else:
            # Mode 2: Browser Folder Picker (Universal for ALL Computers & Laptops)
            st.markdown(
                """
                <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 10px; padding: 10px 14px; margin-bottom: 12px;">
                    <div style="color: #60a5fa; font-weight: 700; font-size: 0.9rem; margin-bottom: 3px;">
                        🌐 ជ្រើសរើស Folder ផ្ទាល់ពីកុំព្យូទ័ររបស់អ្នក (Select Folder from ANY Computer)
                    </div>
                    <div style="color: #94a3b8; font-size: 0.8rem;">
                        ដំណើរការលើគ្រប់កុំព្យូទ័រទាំងអស់ (PC, Laptop, Mac, Phone)។ គ្រាន់តែចុច <b>Browse files</b> ដើម្បីជ្រើសរើស Folder វីដេអូ ឬអូសទម្លាក់ (<b>Drag & Drop</b>) Folder ទាំងមូលចូលទីនេះ!
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c_f_mode, c_f_info = st.columns([1.5, 1])
            with c_f_mode:
                is_folder_mode = st.toggle(
                    "📁 របៀបជ្រើសរើស Folder ទាំងមូល (Folder Mode)",
                    value=True,
                    key="batch_folder_mode_toggle",
                    help="បើកមុខងារនេះដើម្បីឲ្យ Browse files បើកផ្ទាំងរើស Folder ទាំងមូល",
                )
            with c_f_info:
                if is_folder_mode:
                    st.caption("✨ រើស Folder ទាំងមូលតែ 1 Click")
                else:
                    st.caption("📄 រើសឯកសារវីដេអូរាយ")

            st.markdown('<div id="folder-batch-uploader-wrapper"></div>', unsafe_allow_html=True)
            if is_folder_mode:
                st.html(
                    """
                    <script>
                    (function() {
                        function attachFolderPickerAttr() {
                            const wrapper = document.getElementById("folder-batch-uploader-wrapper");
                            if (!wrapper) return;
                            const container = wrapper.closest('[data-testid="stVerticalBlock"]') || wrapper.parentElement;
                            if (!container) return;
                            const input = container.querySelector('input[type="file"]');
                            if (input && !input.hasAttribute('webkitdirectory')) {
                                input.setAttribute('webkitdirectory', '');
                                input.setAttribute('directory', '');
                                input.setAttribute('multiple', '');
                            }
                        }
                        attachFolderPickerAttr();
                        const observer = new MutationObserver(attachFolderPickerAttr);
                        observer.observe(document.body, { childList: true, subtree: true });
                    })();
                    </script>
                    """,
                    unsafe_allow_javascript=True,
                )
            else:
                st.html(
                    """
                    <script>
                    (function() {
                        const wrapper = document.getElementById("folder-batch-uploader-wrapper");
                        if (!wrapper) return;
                        const container = wrapper.closest('[data-testid="stVerticalBlock"]') || wrapper.parentElement;
                        if (!container) return;
                        const input = container.querySelector('input[type="file"]');
                        if (input && input.hasAttribute('webkitdirectory')) {
                            input.removeAttribute('webkitdirectory');
                            input.removeAttribute('directory');
                        }
                    })();
                    </script>
                    """,
                    unsafe_allow_javascript=True,
                )

            up_batch = st.file_uploader(
                "📁 ជ្រើសរើស Folder វីដេអូ ឬឯកសារ (Select Folder or Video Files):",
                type=["mp4", "mov", "mkv", "webm", "avi", "flv", "wmv", "mp3", "wav", "m4a"],
                accept_multiple_files=True,
                key="batch_file_uploader_widget",
                help="អាចចុច Browse files ដើម្បីរើស Folder ទាំងមូល ឬ Drag & Drop Folder ចូលទីនេះ",
            )
            if up_batch:
                saved_files = []
                for uf in up_batch:
                    clean_rel = uf.name.replace("\\", "/").lstrip("/")
                    dest = user_batch_in / Path(clean_rel)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(uf.getvalue())
                    saved_files.append(dest)
                st.session_state.batch_media_files = saved_files

                # Detect if a subfolder was chosen (e.g. 小奶宝驾到)
                sub_folder_name = ""
                for sf in saved_files:
                    try:
                        if sf.parent != user_batch_in and sf.parent.is_relative_to(user_batch_in):
                            sub_folder_name = sf.parent.name
                            st.session_state.batch_target_folder = str(sf.parent.resolve())
                            st.session_state[user_session_folder_key] = str(sf.parent.resolve())
                            break
                    except Exception:
                        pass

                if not sub_folder_name:
                    st.session_state.batch_target_folder = str(user_batch_in.resolve())
                    st.session_state[user_session_folder_key] = str(user_batch_in.resolve())
                    f_label = "Folder"
                else:
                    f_label = f"Folder `{sub_folder_name}`"

                st.success(f"✓ បានបញ្ចូល {len(saved_files)} វីដេអូពី {f_label} រួចរាល់ ស្រេចសម្រាប់ Dubbing!")

            existing_in = sorted([f for f in user_batch_in.rglob("*") if f.is_file() and f.suffix.lower() in valid_exts])
            if existing_in:
                col_ex1, col_ex2 = st.columns([1.5, 1])
                with col_ex1:
                    st.caption(f"📁 វីដេអូក្នុង Folder ផ្ទុករបស់អ្នក: **{len(existing_in)} files**")
                with col_ex2:
                    if st.button("🗑️ សម្អាតចោល (Clear Uploads)", key="btn_clear_uploads", use_container_width=True):
                        for f in user_batch_in.rglob("*"):
                            try:
                                if f.is_file():
                                    f.unlink()
                            except Exception:
                                pass
                        for d in sorted([p for p in user_batch_in.rglob("*") if p.is_dir()], reverse=True):
                            try:
                                d.rmdir()
                            except Exception:
                                pass
                        st.session_state.batch_media_files = []
                        st.rerun()

                if not st.session_state.get("batch_media_files"):
                    st.session_state.batch_media_files = existing_in
                    st.session_state.batch_target_folder = str(user_batch_in.resolve())

        # Active selected files
        active_files = [Path(p) for p in st.session_state.get("batch_media_files", []) if Path(p).exists()]
        if active_files:
            st.markdown(
                f"""
                <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 10px 14px; margin: 10px 0;">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span style="color: #34d399; font-weight: 700; font-size: 0.92rem;">✓ បានជ្រើសរើស {len(active_files)} វីដេអូសម្រាប់ Dubbing</span>
                        <span style="font-size: 0.75rem; color: #a7f3d0; background: rgba(16, 185, 129, 0.2); padding: 2px 8px; border-radius: 999px;">Ready</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Smart Output folder path: inside the selected folder / dubbed_outputs or user_batch_out
        target_f = st.session_state.get("batch_target_folder", "")
        if target_f and Path(target_f).exists() and Path(target_f).is_dir() and Path(target_f) != Path.cwd():
            def_out = str((Path(target_f) / "dubbed_outputs").resolve())
        else:
            def_out = str(user_batch_out.resolve())

        batch_out_path = st.text_input(
            "💾 ថតរក្សាទុកលទ្ធផល (Output Folder):",
            value=def_out,
            help=f"Rendered videos will be saved here.",
        )

        st.markdown("#### ⚙️ 2. កំណត់សំឡេង និងការ Mix (Pipeline Settings)")
        
        b_c1, b_c2 = st.columns(2)
        with b_c1:
            batch_voice_opt = st.selectbox(
                "🎙️ Khmer Voice Mode",
                [
                    "🎭 និយាយប្រុសផងស្រីផងស្វ័យប្រវត្ត (Piseth 👨 + Sreymom 👩)",
                    "👨 Piseth Neural (សម្លេងប្រុស)",
                    "👩 Sreymom Neural (សម្លេងស្រី)",
                ],
                help="Auto-detect dynamically switches between Piseth and Sreymom based on character voice pitch.",
            )
            if "Piseth" in batch_voice_opt and "Sreymom" in batch_voice_opt:
                chosen_batch_voice = "auto_detect"
            elif "Piseth" in batch_voice_opt:
                chosen_batch_voice = "km-KH-PisethNeural"
            else:
                chosen_batch_voice = "km-KH-SreymomNeural"

        with b_c2:
            batch_speed = st.slider("⚡ ល្បឿនសម្លេង (Voice Speed)", 0.75, 1.40, 1.0, 0.05, format="%.2fx")

        col_bm_m, col_bm_v = st.columns(2)
        with col_bm_m:
            batch_bg_music = st.toggle("🎵 Background Music", value=st.session_state.get("enable_bg_music", False), key="batch_bg_music")
            if batch_bg_music:
                batch_bg_vol = st.slider("Music Vol", 5, 80, int(st.session_state.get("bg_music_vol", 20)), format="%d%%", key="batch_bg_vol")
            else:
                batch_bg_vol = 0
        with col_bm_v:
            batch_orig_voice = st.toggle("🗣️ Original Voice", value=st.session_state.get("enable_orig_voice", False), key="batch_orig_voice")
            if batch_orig_voice:
                batch_orig_vol = st.slider("Orig Vol", 5, 50, int(st.session_state.get("orig_voice_vol", 15)), format="%d%%", key="batch_orig_vol")
            else:
                batch_orig_vol = 0

        col_bd_v, col_bd_s = st.columns([1.2, 1])
        with col_bd_v:
            batch_dub_vol = st.slider("🎙️ Dubbed Voice Vol", 50, 150, 100, 5, format="%d%%", key="batch_dub_vol")
        with col_bd_s:
            batch_burn_subs = st.checkbox("Burn Subtitles on Video", value=False, key="batch_burn_subs", help="Hardcode Khmer subtitles onto video frame.")

        batch_save_only_video = st.checkbox(
            "💾 រក្សាទុកតែវិដេអូស្រេច (Save ONLY Finished Video - No SRT/MP3)",
            value=True,
            key="batch_save_only_video",
            help="រក្សាទុកតែវិដេអូដែលបានបញ្ចូលសម្លេងរួច (.MP4) ក្នុង Folder លទ្ធផល ដោយមិនរក្សាទុកឯកសារ SRT និង MP3 នោះទេ។",
        )

        start_batch_btn = st.button("🚀 Start Folder Dubbing (Transcribe ➔ Translate ➔ Voice-Over ➔ Render)", type="primary", use_container_width=True)

    with batch_col2:
        st.markdown("#### 📋 3. បញ្ជីឯកសារ និងវឌ្ឍនភាព (Progress & Results)")

        active_files = [Path(p) for p in st.session_state.get("batch_media_files", []) if Path(p).exists()]
        if active_files:
            with st.expander(f"📁 បញ្ជីវីដេអូដែលបានជ្រើសរើស ({len(active_files)} files)", expanded=not bool(st.session_state.batch_dub_results)):
                for idx, mf in enumerate(active_files, 1):
                    sz_mb = mf.stat().st_size / (1024 * 1024)
                    ext_icon = "🎬" if mf.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".m4v"} else "🎧"
                    st.markdown(f"**{idx}.** {ext_icon} `{mf.name}` *({sz_mb:.1f} MB)*")

        if start_batch_btn:
            active_files = [Path(p) for p in st.session_state.get("batch_media_files", []) if Path(p).exists()]
            if not active_files:
                st.error("⚠️ មិនទាន់មានវីដេអូសម្រាប់ Dubbing ទេ។ សូម Upload វីដេអូ ឬជ្រើសរើស Folder ជាមុនសិន។")
            else:
                st.info(f"🚀 កំពុងចាប់ផ្តើមដំណើរការ {len(active_files)} ឯកសារ...")
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                log_box = st.empty()
                logs = []

                def batch_progress_ui(cur_idx, total_cnt, step_msg, item_res=None):
                    frac = max(0.0, min(1.0, (cur_idx - 1) / total_cnt))
                    progress_bar.progress(frac)
                    status_text.markdown(f"**{step_msg}**")
                    logs.append(f"[{time.strftime('%H:%M:%S')}] {step_msg}")
                    log_box.code("\n".join(logs[-10:]), language="bash")

                try:
                    res_summary = transcribe_one_folder(
                        file_list=active_files,
                        output_folder=batch_out_path,
                        model_name=pipeline_model,
                        source_language=source_language,
                        gemini_key=gemini_key,
                        openai_key=openai_key,
                        elevenlabs_key=eleven_key,
                        tts_engine=tts_engine,
                        voice=chosen_batch_voice,
                        voice_speed=batch_speed,
                        burn_subtitles=batch_burn_subs,
                        enable_bg_music=batch_bg_music,
                        bg_music_vol=batch_bg_vol,
                        enable_orig_voice=batch_orig_voice,
                        orig_voice_vol=batch_orig_vol,
                        dub_volume=batch_dub_vol,
                        progress_callback=batch_progress_ui,
                        save_only_video=batch_save_only_video,
                    )
                    progress_bar.progress(1.0)
                    status_text.success(f"🎉 ដំណើរការ Folder បានបញ្ចប់ជោគជ័យ! ({res_summary['succeeded']}/{res_summary['total_files']} files)")
                    st.session_state.batch_dub_results = res_summary
                except Exception as b_err:
                    st.error(f"❌ កំហុសក្នុងដំណើរការ Batch: {b_err}")

        # Render Batch Results if available
        if st.session_state.get("batch_dub_results"):
            b_res = st.session_state.batch_dub_results
            st.markdown("---")
            st.markdown(
                f"""
                <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 12px; padding: 12px 16px; margin: 10px 0 16px 0;">
                    <div style="font-size: 1.05rem; font-weight: 700; color: #34d399; margin-bottom: 4px;">🎉 លទ្ធផលផលិតវិដេអូជាបាច់ (Batch Completed)</div>
                    <div style="font-size: 0.85rem; color: #cbd5e1;">
                        ជោគជ័យ: <b>{b_res.get('succeeded', 0)}</b> / {b_res.get('total_files', 0)} ឯកសារ • ថតរក្សាទុក: <code>{escape(b_res.get('output_folder', ''))}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            succ_vids = [
                item.get("output_video")
                for item in b_res.get("results", [])
                if item.get("status") == "success" and item.get("output_video") and Path(item.get("output_video")).exists()
            ]
            if len(succ_vids) > 1:
                import io, zipfile
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for vp in succ_vids:
                        zf.write(vp, arcname=Path(vp).name)
                zip_buf.seek(0)
                st.download_button(
                    f"📦 Download វីដេអូទាំងអស់ជា ZIP ({len(succ_vids)} Videos)",
                    data=zip_buf.getvalue(),
                    file_name=f"dubbed_batch_{curr_auth_u}_{int(time.time())}.zip",
                    mime="application/zip",
                    key="dl_batch_all_zip",
                    use_container_width=True,
                )

            for item in b_res.get("results", []):
                item_stat = "✅" if item.get("status") == "success" else "❌"
                with st.expander(f"{item_stat} **{item.get('filename')}**", expanded=(item.get("status") == "success")):
                    if item.get("status") == "success":
                        out_v = item.get("output_video")
                        if out_v and Path(out_v).exists() and Path(out_v).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                            render_video_preview(out_v)
                            with open(out_v, "rb") as vf_b:
                                v_bytes = vf_b.read()
                            st.download_button(
                                f"📥 Download Dubbed Video ({Path(out_v).name})",
                                data=v_bytes,
                                file_name=Path(out_v).name,
                                mime="video/mp4",
                                key=f"dl_b_vid_{item['index']}",
                                use_container_width=True,
                            )
                        elif out_v and Path(out_v).exists():
                            with open(out_v, "rb") as af_b:
                                a_bytes = af_b.read()
                            st.download_button(
                                f"📥 Download Media ({Path(out_v).name})",
                                data=a_bytes,
                                file_name=Path(out_v).name,
                                mime="audio/wav",
                                key=f"dl_b_aud_{item['index']}",
                                use_container_width=True,
                            )
                    else:
                        st.error(f"បរាជ័យ: {item.get('error')}")

# ----------------------------------------------------
# TAB 03: Khmer Translation
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
                            g_model = pipeline_model if (pipeline_model and pipeline_model.startswith("gemini-")) else "gemini-flash-latest"
                            translated_subs = translate_subtitles_with_gemini(source_subs, source_language, gemini_key, g_model)
                    elif trans_mode == "OpenAI (GPT-4o Mini)":
                        with st.spinner("Translating with GPT-4o Mini..."):
                            translated_subs = translate_subtitles_with_openai(source_subs, source_language, openai_key)
                    else:  # Auto
                        with st.spinner("Translating via Gemini with automatic fallback..."):
                            translated_subs = run_auto_translation(source_subs, source_language, gemini_key, openai_key, pipeline_model)
                    
                    translated_subs = purge_and_enforce_khmer(translated_subs, source_language=source_language, gemini_key=gemini_key, openai_key=openai_key, model_name=pipeline_model)
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
                                srt_temp = get_user_storage_dir() / "burn_subtitles.srt"
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
                                st.success("🎉 ដំណើរការផលិតវិដេអូបានចប់សព្វគ្រប់ 100%! (Dubbing Complete!)")
                                st.markdown("#### 🎬 ទស្សនាវិដេអូដែលបានបញ្ចូលសម្លេង (Dubbed Video Preview):")
                                render_video_preview(final_v)
                                with open(final_v, "rb") as vf_col2:
                                    v_done_b2 = vf_col2.read()
                                st.download_button(
                                    "📥 Download Dubbed Video (.MP4)",
                                    data=v_done_b2,
                                    file_name="dubbed_studio_output.mp4",
                                    mime="video/mp4",
                                    use_container_width=True,
                                    key="dl_video_t2_immediate",
                                )
                except Exception as e:
                    st.error(f"Translation Error: {e}")

        with t_col2:
            if st.session_state.output_video_path and Path(st.session_state.output_video_path).exists():
                st.markdown(
                    """
                    <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 12px; padding: 12px 14px; margin-bottom: 12px;">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <span style="font-weight: 700; color: #34d399; font-size: 1rem;">🎬 វិដេអូដែលបានផលិតរួចរាល់ (Dubbed Video Preview)</span>
                            <span style="font-size: 0.72rem; color: #10b981; background: rgba(16, 185, 129, 0.2); padding: 2px 8px; border-radius: 6px; font-weight: 700;">Ready to Watch</span>
                        </div>
                        <div style="font-size: 0.8rem; color: #cbd5e1; margin-top: 4px;">ចុច Play ខាងក្រោមដើម្បីទស្សនាវិដេអូដែលមានសម្លេងតួអង្គប្រុស & ស្រីឆ្លាស់គ្នា!</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                render_video_preview(st.session_state.output_video_path)
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
                if has_thai_characters(st.session_state.khmer_srt):
                    st.error("⚠️ **រកឃើញអក្សរថៃក្នុងអត្ថបទ (Thai Language Detected)**: ចុចប៊ូតុងខាងក្រោមដើម្បីប្តូរទៅជាភាសាខ្មែរ 100% ភ្លាមៗ!")
                    if st.button("🇰🇭 ប្តូរអក្សរថៃទាំងអស់ទៅជាភាសាខ្មែរ 100% (Clean All Thai to Khmer)", type="primary", use_container_width=True, key="btn_fix_thai_tab2"):
                        with st.spinner("កំពុងប្តូរអក្សរថៃទៅជាភាសាខ្មែរ 100%..."):
                            cur_subs = parse_srt(st.session_state.khmer_srt)
                            fixed_subs = purge_and_enforce_khmer(cur_subs, gemini_key=gemini_key, openai_key=openai_key, model_name=pipeline_model)
                            st.session_state.khmer_srt = render_srt(fixed_subs)
                            st.toast("✅ បានប្តូរអក្សរថៃទៅជាភាសាខ្មែរ 100% ដោយជោគជ័យ!", icon="🇰🇭")
                            st.rerun()
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

        if has_thai_characters(active_srt):
            st.error("⚠️ **រកឃើញអក្សរថៃក្នុងអត្ថបទ (Thai Characters Detected in Subtitles)**: ចុចប៊ូតុងខាងក្រោមដើម្បីប្តូរទៅជាភាសាខ្មែរ 100% ភ្លាមៗ!")
            if st.button("🇰🇭 ប្តូរអក្សរថៃទាំងអស់ទៅជាភាសាខ្មែរ 100% (Clean All Thai to Khmer)", type="primary", use_container_width=True, key="btn_fix_thai_tab3"):
                with st.spinner("កំពុងប្តូរអក្សរថៃទៅជាភាសាខ្មែរ 100%..."):
                    fixed_subs = purge_and_enforce_khmer(subs_list, gemini_key=gemini_key, openai_key=openai_key, model_name=pipeline_model)
                    st.session_state.khmer_srt = render_srt(fixed_subs)
                    st.toast("✅ បានប្តូរអក្សរថៃទៅជាភាសាខ្មែរ 100% ដោយជោគជ័យ!", icon="🇰🇭")
                    st.rerun()

        # Speaker Voice Assignment Toolbar
        sub_v_dict = st.session_state.get("subtitle_voices", {})
        m_c = sum(1 for v in sub_v_dict.values() if "Piseth" in v)
        f_c = sum(1 for v in sub_v_dict.values() if "Sreymom" in v)

        st.markdown(
            f"""
            <div style="background: rgba(30, 41, 59, 0.75); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 10px 14px; margin: 10px 0 12px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                    <span style="font-weight: 700; color: #f8fafc; font-size: 0.95rem;">🎬 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Multi-Speaker Dialogue)</span>
                    <span style="font-size: 0.8rem; background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 4px 12px; border-radius: 8px; font-weight: 700; border: 1px solid rgba(52, 211, 153, 0.3);">
                        ✨ រួមគ្នាក្នុងវិដេអូតែមួយ: 👨 Piseth ({m_c} ឃ្លា) + 👩 Sreymom ({f_c} ឃ្លា)
                    </span>
                </div>
                <p style="font-size: 0.76rem; color: #94a3b8; margin: 4px 0 0 0;">ឃ្លានីមួយៗត្រូវបានកំណត់សម្លេងតាមតួអង្គ (សម្លេងប្រុស ➔ Piseth 👨, សម្លេងស្រី ➔ Sreymom 👩) ហើយបញ្ចូលគ្នាក្នុងវិដេអូតែមួយ។ អ្នកអាចចុចប្តូរតួអង្គសម្រាប់ឃ្លានីមួយៗខាងក្រោមបានភ្លាមៗ។</p>
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
                "👨 Piseth (ប្រុស)": "km-KH-PisethNeural",
                "👩 Sreymom (ស្រី)": "km-KH-SreymomNeural",
            }
            inv_v = {v: k for k, v in v_options.items()}
            cur_label = inv_v.get(cur_line_voice, "👨 Piseth (ប្រុស)")

            st.caption("តួអង្គនិយាយសម្រាប់ឃ្លានេះ (Speaker Voice):")
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

            # Auto-save immediately when user toggles voice pill
            if cur_sub.index not in sub_voices or sub_voices[cur_sub.index] != chosen_card_voice:
                st.session_state.setdefault("subtitle_voices", {})[cur_sub.index] = chosen_card_voice
                m_c_new = sum(1 for v in st.session_state.subtitle_voices.values() if "Piseth" in v)
                f_c_new = sum(1 for v in st.session_state.subtitle_voices.values() if "Sreymom" in v)
                st.session_state.voice_gender_counts = {"male": m_c_new, "female": f_c_new}

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
                    saved_text = edited_khmer_text.strip()
                    if has_thai_characters(saved_text):
                        st.info("🧹 Converting Thai characters to 100% Khmer...")
                        cleaned_list = purge_and_enforce_khmer(
                            [Subtitle(cur_sub.index, cur_sub.start, cur_sub.end, saved_text)],
                            gemini_key=gemini_key,
                            openai_key=openai_key,
                            model_name=pipeline_model,
                        )
                        saved_text = cleaned_list[0].text
                    subs_list[cur_idx].text = saved_text
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
                    if any(has_thai_characters(sub.text) for sub in updated_subtitles):
                        st.info("🧹 Automatically cleaning and translating detected Thai text into 100% Khmer...")
                        updated_subtitles = purge_and_enforce_khmer(
                            updated_subtitles,
                            gemini_key=gemini_key,
                            openai_key=openai_key,
                            model_name=pipeline_model,
                        )
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
            st.markdown(
                f"""
                <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 12px; padding: 12px 14px; margin: 8px 0 12px 0;">
                    <div style="font-weight: 700; color: #34d399; font-size: 0.95rem;">🎬 និយាយប្រុសផងស្រីផងក្នុងវិដេអូតែមួយ (Multi-Speaker in One Video)</div>
                    <div style="color: #f8fafc; font-size: 0.84rem; margin-top: 4px;">
                        👨 Piseth: <b>{m_t3}</b> ឃ្លា • 👩 Sreymom: <b>{f_t3}</b> ឃ្លា 👉 <b>នឹងបញ្ចូលគ្នាក្នុងសម្លេងតែមួយសម្រាប់វីដេអូ</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            disp_v_t3 = f"និយាយប្រុសផងស្រីផង (👨 Piseth {m_t3} + 👩 Sreymom {f_t3})"
        elif "Piseth" in chosen_voice:
            disp_v_t3 = "Piseth Neural (ប្រុសតែម្នាក់ឯង)"
        elif "Sreymom" in chosen_voice:
            disp_v_t3 = "Sreymom Neural (ស្រីតែម្នាក់ឯង)"

        custom_voice_count = len(st.session_state.get("subtitle_voices", {}))
        voice_note = f"Mode: **{disp_v_t3}**" + (f" ({custom_voice_count} lines assigned)" if custom_voice_count else "")
        st.caption(f"Engine: **{tts_engine}** • {voice_note} • Speed: **{voice_speed}x**")
        
        btn_synth = st.button("⚡ Generate Full Voice-Over Track (និយាយប្រុសផងស្រីផង)", type="primary", use_container_width=True)
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
                save_path = get_user_storage_dir() / f"target_video{Path(custom_video.name).suffix}"
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

        v_counts = st.session_state.get("voice_gender_counts", {})
        m_v = v_counts.get("male", 0)
        f_v = v_counts.get("female", 0)
        st.markdown(
            f"""
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 12px; padding: 12px 14px; margin: 10px 0 14px 0;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                    <span style="font-weight: 700; font-size: 0.92rem; color: #34d399;">🎬 វិដេអូតែមួយនិយាយទាំងប្រុស (Piseth) និងស្រី (Sreymom)</span>
                    <span style="font-size: 0.72rem; color: #10b981; background: rgba(16, 185, 129, 0.2); padding: 2px 8px; border-radius: 6px; font-weight: 700;">Multi-Speaker Video</span>
                </div>
                <p style="font-size: 0.78rem; color: #94a3b8; margin: 0;">
                    {f"👨 Piseth: <b>{m_v}</b> ឃ្លា • 👩 Sreymom: <b>{f_v}</b> ឃ្លា • " if (m_v or f_v) else ""}
                    វិដេអូដែលចេញមកនឹងមានសម្លេងតួអង្គប្រុស & ស្រីឆ្លាស់គ្នាតាមសាច់រឿងក្នុងខ្សែវិដេអូតែមួយគត់។
                </p>
            </div>
            <div style="background: rgba(30, 41, 59, 0.65); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 12px 14px; margin: 0 0 14px 0;">
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
                    srt_temp = get_user_storage_dir() / "burn_subtitles.srt"
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
                                st.success("🎉 ដំណើរការផលិតវិដេអូបានចប់សព្វគ្រប់ 100%! (Dubbing Complete!)")
                                st.markdown("#### 🎬 ទស្សនាវិដេអូដែលបានបញ្ចូលសម្លេង (Dubbed Video Preview):")
                                render_video_preview(final_video_path)
                                with open(final_video_path, "rb") as vf_col4:
                                    video_data_done = vf_col4.read()
                                st.download_button(
                                    "📥 Download Dubbed Video (.MP4)",
                                    data=video_data_done,
                                    file_name="dubbed_studio_output.mp4",
                                    mime="video/mp4",
                                    use_container_width=True,
                                    key="dl_video_t4_immediate",
                                )
                            except Exception as video_err:
                                st.error(f"Video rendering failed: {video_err}")

    with v_col2:
        if st.session_state.output_video_path and Path(st.session_state.output_video_path).exists():
            v_size_mb = Path(st.session_state.output_video_path).stat().st_size / (1024 * 1024)
            st.markdown(
                f"""
                <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 12px; padding: 12px 14px; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span style="font-weight: 700; color: #34d399; font-size: 1rem;">🎬 វិដេអូដែលបានផលិតរួចរាល់ ({v_size_mb:.2f} MB)</span>
                        <span style="font-size: 0.72rem; color: #10b981; background: rgba(16, 185, 129, 0.2); padding: 2px 8px; border-radius: 6px; font-weight: 700;">Ready to Watch</span>
                    </div>
                    <div style="font-size: 0.8rem; color: #cbd5e1; margin-top: 4px;">ចុច Play ខាងក្រោមដើម្បីទស្សនាវិដេអូដែលមានសម្លេងតួអង្គប្រុស & ស្រីឆ្លាស់គ្នា!</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_video_preview(st.session_state.output_video_path)
            
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
                    active_token = info.get("active_session_token", "") if isinstance(info, dict) else ""
                    active_device = info.get("active_device_name", "") if isinstance(info, dict) else ""
                    is_online = bool(active_token)
                    online_badge = (
                        '<span style="background:rgba(16,185,129,0.18);color:#34d399;font-size:0.72rem;font-weight:700;'
                        'padding:2px 9px;border-radius:999px;border:1px solid rgba(16,185,129,0.4);">🟢 Online</span>'
                        if is_online else
                        '<span style="background:rgba(100,116,139,0.18);color:#94a3b8;font-size:0.72rem;font-weight:700;'
                        'padding:2px 9px;border-radius:999px;border:1px solid rgba(100,116,139,0.3);">⚫ Offline</span>'
                    )

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
                                <div style="display:flex;gap:6px;align-items:center;">{online_badge} {role_badge}</div>
                            </div>
                            <div class="customer-info-grid">
                                <div class="customer-info-item">📞 Contact: <span>{escape(contact)}</span></div>
                                <div class="customer-info-item">📱 Active Device: <span style="color:#38bdf8;">{escape(active_device or dev_name)}</span></div>
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
                        c_act1, c_act2, c_act3, _ = st.columns([1.2, 1, 1.2, 1.2], gap="small")
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
                        with c_act3:
                            # Admin force-disconnect / kick session
                            kick_label = "🔌 Kick Session" if is_online else "🔌 No Session"
                            if st.button(kick_label, key=f"t5_kick_{u}", disabled=not is_online, use_container_width=True):
                                if isinstance(all_auth_users.get(u), dict):
                                    all_auth_users[u]["active_session_token"] = ""
                                    all_auth_users[u]["active_device_name"] = ""
                                    save_saved_config({"auth_users": all_auth_users})
                                    st.toast(f"🔌 Session disconnected for '{u}'. They will be logged out on next action.", icon="⚡")
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

        # ------------------------------------
        # ADMIN CONTACT SETTINGS & SUPPORT INBOX
        # ------------------------------------
        st.markdown("---")
        st.markdown("#### ⚙️ កំណត់ព័ត៌មានទំនាក់ទំនង Admin (Admin Contact Settings)")
        st.markdown("<p style='font-size:0.84rem; color:#94a3b8;'>ព័ត៌មាននេះនឹងត្រូវបង្ហាញនៅលើទំព័រ Login/Register និងផ្ទាំងជំនួយសម្រាប់អតិថិជនទាក់ទងមកកាន់ Admin។</p>", unsafe_allow_html=True)

        curr_contact = get_admin_contact_info()
        col_adm_c1, col_adm_c2 = st.columns(2)
        with col_adm_c1:
            inp_tg = st.text_input("✈️ Telegram Username / Link", value=curr_contact.get("telegram", "@Theadept168"), help="e.g. @Theadept168 or https://t.me/Theadept168", key="admin_edit_tg")
            inp_phone = st.text_input("📞 Phone / WhatsApp Number", value=curr_contact.get("phone", "+855 12 345 678"), help="e.g. +855 12 345 678", key="admin_edit_phone")
        with col_adm_c2:
            inp_email = st.text_input("✉️ Email Address", value=curr_contact.get("email", "admin@dubberai.com"), help="e.g. admin@dubberai.com", key="admin_edit_email")
            inp_note = st.text_input("📝 Support Note (Khmer)", value=curr_contact.get("note", "ទាក់ទងមកកាន់ Admin តាម Telegram ឬទូរស័ព្ទ ដើម្បីស្នើសុំបើកគណនី ឬសាកសួរព័ត៌មានបន្ថែម។"), key="admin_edit_note")

        if st.button("💾 Save Admin Contact Settings", key="btn_save_admin_contact", use_container_width=True):
            save_admin_contact_info({
                "telegram": inp_tg.strip(),
                "phone": inp_phone.strip(),
                "email": inp_email.strip(),
                "note": inp_note.strip(),
            })
            st.toast("✅ បានរក្សាទុកព័ត៌មានទំនាក់ទំនង Admin រួចរាល់!", icon="🎉")
            st.rerun()

        # Customer Messages Inbox
        st.markdown("---")
        _fresh_cfg_msg = load_saved_config()
        all_msgs = _fresh_cfg_msg.get("admin_messages", [])
        unread_count = sum(1 for m in all_msgs if m.get("status") == "unread")
        inbox_title = f"#### 📬 ប្រអប់សារពីអតិថិជន (Customer Inquiries) ({unread_count} New)" if unread_count > 0 else "#### 📬 ប្រអប់សារពីអតិថិជន (Customer Inquiries)"
        st.markdown(inbox_title)

        if all_msgs:
            col_inbox_h1, col_inbox_h2 = st.columns([3, 1])
            with col_inbox_h2:
                if st.button("🗑️ Clear Read Messages", key="btn_clear_read_msgs", help="Remove all read inquiries"):
                    remaining = [m for m in all_msgs if m.get("status") == "unread"]
                    save_saved_config({"admin_messages": remaining})
                    st.toast("Cleared read messages.")
                    st.rerun()

            for idx, msg in enumerate(reversed(all_msgs)):
                m_id = msg.get("id", str(idx))
                is_unr = msg.get("status") == "unread"
                border_col = "rgba(56, 189, 248, 0.45)" if is_unr else "rgba(255, 255, 255, 0.08)"
                bg_col = "rgba(56, 189, 248, 0.08)" if is_unr else "rgba(30, 41, 59, 0.6)"
                badge_html = '<span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; font-size: 0.72rem; font-weight: 700; padding: 2px 7px; border-radius: 999px;">NEW</span>' if is_unr else '<span style="color: #64748b; font-size: 0.72rem;">Read</span>'

                st.markdown(
                    f"""
                    <div style="background: {bg_col}; border: 1px solid {border_col}; border-radius: 12px; padding: 12px 14px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <div>
                                <span style="font-weight: 700; color: #f8fafc; font-size: 0.95rem;">👤 {escape(msg.get('sender', 'Customer'))}</span>
                                <span style="color: #94a3b8; font-size: 0.8rem; margin-left: 8px;">📞 {escape(msg.get('contact', 'N/A'))}</span>
                            </div>
                            <div>
                                {badge_html}
                                <span style="font-size: 0.74rem; color: #64748b; margin-left: 8px;">🕒 {escape(msg.get('created_at', ''))}</span>
                            </div>
                        </div>
                        <div style="font-size: 0.88rem; color: #e2e8f0; background: rgba(15, 23, 42, 0.5); border-radius: 8px; padding: 8px 10px; margin-top: 4px; white-space: pre-wrap;">
                            {escape(msg.get('message', ''))}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col_m_act1, col_m_act2, col_m_sp = st.columns([1, 1, 3])
                with col_m_act1:
                    if is_unr:
                        if st.button("✓ Mark as Read", key=f"mark_read_{m_id}_{idx}", use_container_width=True):
                            for m in all_msgs:
                                if m.get("id") == m_id:
                                    m["status"] = "read"
                                    break
                            save_saved_config({"admin_messages": all_msgs})
                            st.rerun()
                with col_m_act2:
                    if st.button("🗑️ Delete", key=f"del_msg_{m_id}_{idx}", use_container_width=True):
                        all_msgs = [m for m in all_msgs if m.get("id") != m_id]
                        save_saved_config({"admin_messages": all_msgs})
                        st.toast("Message deleted.")
                        st.rerun()
        else:
            st.info("✅ មិនទាន់មានសារពីអតិថិជននៅឡើយទេ។ (No customer messages yet)")
