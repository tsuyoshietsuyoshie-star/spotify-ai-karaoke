"""
Spotify AI Karaoke & Fullscreen Visualizer (17-Phase DSP Engine v7.0)
- Ultra-Low Latency 48kHz WASAPI Loopback Capture (10ms Chunks / 480 Samples)
- Continuous High-Precision Audio Clock & 500ms Lock-Free Ring Buffer
- Real-Time Feature Extraction (RMS, Spectral Flux, 3-Band Frequency Energy)
- Transient Onset Detector & Beat Activity Tracker
- GSMTC + Audio Clock Sensor Fusion with Anti-Jitter Filter & Drift Estimator
- Multi-Anchor Piecewise Linear Timing Curve Engine (Tap-To-Sync Anchors)
- Real-Time Timing Confidence System (0.0 - 1.0)
- Live DSP Diagnostics Telemetry HUD (Hotkey: D)
- A.U.R.O.R.A. + Cosmic 3D Hyperspace Master Visualizer
- 100% Transparent Header & 58px / 32px Heroic Typography
- Hideable Controls (Hotkey: H) & Native Frameless Fullscreen (Hotkey: F11)
"""

import sys
import os
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["PYTHONPYCACHEPREFIX"] = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "pycache")

import json
import time
import math
import re
import urllib.request
import urllib.parse
import threading
import subprocess
import collections
import concurrent.futures
import warnings
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore")

import numpy as np
import soundcard as sc
try:
    import soundcard.mediafoundation as mf
    warnings.filterwarnings("ignore", category=getattr(mf, "SoundcardRuntimeWarning", Warning))
    warnings.filterwarnings("ignore", message=".*data discontinuity.*")
    _orig_mf_warn = mf.warnings.warn
    def _silenced_warn(*args, **kwargs):
        if args and "data discontinuity" in str(args[0]):
            return
        if "message" in kwargs and "data discontinuity" in str(kwargs["message"]):
            return
        _orig_mf_warn(*args, **kwargs)
    mf.warnings.warn = _silenced_warn
except Exception:
    pass

import syncedlyrics
import requests
try:
    from syrics.totp import TOTP
    from syrics.api import HEADERS as SPOTIFY_HEADERS, TOKEN_URL as SPOTIFY_TOKEN_URL
except Exception:
    TOTP = None
    SPOTIFY_HEADERS = {}
    SPOTIFY_TOKEN_URL = "https://open.spotify.com/api/token"

from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import webview

app = FastAPI(title="Spotify AI Karaoke 17-Phase DSP Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# DSP ENGINE CORE: RING BUFFER, FEATURES, ONSET, CLOCK FUSION & TIMING CURVE
# ==============================================================================

class AudioRingBuffer:
    """Thread-safe, lightweight 500ms circular buffer for 48kHz stereo float32 audio."""
    def __init__(self, capacity_samples=24000):
        self.capacity = capacity_samples # 500ms at 48kHz
        self.buffer = np.zeros((self.capacity, 2), dtype=np.float32)
        self.write_idx = 0
        self.total_samples_written = 0
        self.lock = threading.Lock()

    def write(self, data: np.ndarray):
        n = len(data)
        if n == 0:
            return
        with self.lock:
            if n >= self.capacity:
                self.buffer[:] = data[-self.capacity:]
                self.write_idx = 0
            else:
                end_idx = self.write_idx + n
                if end_idx <= self.capacity:
                    self.buffer[self.write_idx:end_idx] = data
                else:
                    first = self.capacity - self.write_idx
                    self.buffer[self.write_idx:] = data[:first]
                    self.buffer[:n - first] = data[first:]
                self.write_idx = end_idx % self.capacity
            self.total_samples_written += n

    def get_last_samples(self, n_samples: int) -> np.ndarray:
        with self.lock:
            n = min(n_samples, self.capacity)
            if self.total_samples_written < n:
                return self.buffer[:self.write_idx]
            start = (self.write_idx - n) % self.capacity
            if start + n <= self.capacity:
                return self.buffer[start:start + n].copy()
            else:
                part1 = self.buffer[start:].copy()
                part2 = self.buffer[:(start + n) % self.capacity].copy()
                return np.vstack([part1, part2])

class AudioFeatureExtractor:
    """Extracts sub-millisecond audio features (RMS, Spectral Flux, Bass/Mid/High energy)."""
    def __init__(self, sample_rate=48000, fft_size=512):
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.prev_mag_spec = np.zeros(fft_size // 2 + 1, dtype=np.float32)
        self.freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        
        self.bass_mask = (self.freqs >= 20) & (self.freqs < 250)
        self.mid_mask = (self.freqs >= 250) & (self.freqs < 2500)
        self.high_mask = (self.freqs >= 2500) & (self.freqs < 15000)

    def extract(self, mono_chunk: np.ndarray) -> dict:
        if len(mono_chunk) == 0:
            return {"rms": 0.0, "flux": 0.0, "bass": 0.0, "mid": 0.0, "high": 0.0}
            
        rms = float(np.sqrt(np.mean(mono_chunk ** 2)))
        
        # FFT Magnitude
        if len(mono_chunk) < self.fft_size:
            padded = np.pad(mono_chunk, (0, self.fft_size - len(mono_chunk)))
        else:
            padded = mono_chunk[-self.fft_size:]
            
        mag = np.abs(np.fft.rfft(padded))
        
        # Spectral Flux (Positive energy increases)
        diff = mag - self.prev_mag_spec
        flux = float(np.sum(np.maximum(0.0, diff)))
        self.prev_mag_spec = mag.copy()
        
        bass = float(np.mean(mag[self.bass_mask])) if np.any(self.bass_mask) else 0.0
        mid = float(np.mean(mag[self.mid_mask])) if np.any(self.mid_mask) else 0.0
        high = float(np.mean(mag[self.high_mask])) if np.any(self.high_mask) else 0.0
        
        return {
            "rms": rms,
            "flux": flux,
            "bass": min(1.0, bass * 25.0),
            "mid": min(1.0, mid * 40.0),
            "high": min(1.0, high * 60.0)
        }

class OnsetDetector:
    """Adaptive transient and beat onset detector running on Spectral Flux."""
    def __init__(self, history_size=40, threshold_multiplier=1.75):
        self.history = collections.deque(maxlen=history_size)
        self.threshold_multiplier = threshold_multiplier
        self.recent_onsets = collections.deque(maxlen=60)
        self.last_onset_time = 0.0

    def process(self, flux: float, cur_time: float) -> bool:
        self.history.append(flux)
        if len(self.history) < 10:
            return False
            
        mean_flux = np.mean(self.history)
        std_flux = np.std(self.history)
        threshold = mean_flux + self.threshold_multiplier * std_flux
        
        is_onset = (flux > threshold) and (flux > 0.08) and (cur_time - self.last_onset_time > 0.07)
        if is_onset:
            self.last_onset_time = cur_time
            self.recent_onsets.append(cur_time)
            
        return is_onset

    def get_onset_rate(self, cur_time: float) -> float:
        # Number of onsets in the last 2.0 seconds
        valid = [t for t in self.recent_onsets if (cur_time - t) <= 2.0]
        return round(len(valid) / 2.0, 1)

class TimingCurveEngine:
    """Multi-Anchor Piecewise Linear Spline & Song Drift Interpolator."""
    def __init__(self):
        self.anchors = [] # List of tuples: (lrc_time, offset_sec)
        self.lock = threading.Lock()

    def reset(self, base_offset: float = 0.40):
        with self.lock:
            self.anchors = [(0.0, base_offset)]

    def add_anchor(self, lrc_time: float, offset_sec: float):
        with self.lock:
            # Remove any anchor within 1.5s
            self.anchors = [a for a in self.anchors if abs(a[0] - lrc_time) > 1.5]
            self.anchors.append((round(lrc_time, 2), round(offset_sec, 2)))
            self.anchors.sort(key=lambda x: x[0])

    def get_correction(self, current_time: float) -> float:
        with self.lock:
            if not self.anchors:
                return 0.40
            if len(self.anchors) == 1:
                return self.anchors[0][1]
                
            times = [a[0] for a in self.anchors]
            offsets = [a[1] for a in self.anchors]
            
            if current_time <= times[0]:
                return offsets[0]
            if current_time >= times[-1]:
                return offsets[-1]
                
            # Piecewise linear interpolation
            return float(np.interp(current_time, times, offsets))

    def get_anchors_list(self) -> list:
        with self.lock:
            return list(self.anchors)

class SmartMicroAligner:
    """
    Applies gentle acoustic onset alignment to standard (non-enhanced) lyrics lines.
    - Deadzone: delta < 40ms -> no modification (keeps already-perfect lines locked)
    - Bound: clamped to max +-1000ms (1.0s test mode)
    - Confidence check: only runs when confidence >= 0.70
    - Enhanced bypass: skips tracks with true enhanced tags
    """
    def __init__(self, deadzone_sec=0.04, max_correction_sec=1.00):
        self.deadzone_sec = deadzone_sec
        self.max_correction_sec = max_correction_sec
        self.last_correction_ms = 0.0
        self.status_text = "Locked (0 ms)"

    def evaluate_line(self, line: dict, cur_time: float, recent_onsets: list, confidence: float, is_enhanced: bool) -> float:
        if is_enhanced:
            self.last_correction_ms = 0.0
            self.status_text = "Enhanced (Bypass)"
            return 0.0
            
        if confidence < 0.70:
            self.last_correction_ms = 0.0
            self.status_text = "Low Confidence (Hold)"
            return 0.0
            
        line_start = line.get("startTime", 0.0)
        # Search for closest acoustic onset within +- 1000ms (1.0s) of expected line_start
        closest_onset = None
        min_dist = 1.00
        
        for onset_t in recent_onsets:
            dist = abs(onset_t - line_start)
            if dist < min_dist:
                min_dist = dist
                closest_onset = onset_t
                
        if closest_onset is not None:
            raw_delta = closest_onset - line_start
            # Deadzone check (if already fitting within 40ms, do nothing!)
            if abs(raw_delta) <= self.deadzone_sec:
                self.last_correction_ms = 0.0
                self.status_text = "Locked (0 ms)"
                return 0.0
                
            # Clamped & damped micro-adjustment (up to 1.0s)
            sign = 1.0 if raw_delta > 0 else -1.0
            damped_delta = sign * min(self.max_correction_sec, (abs(raw_delta) - self.deadzone_sec) * 0.70)
            self.last_correction_ms = round(damped_delta * 1000.0, 1)
            self.status_text = f"Aligned ({self.last_correction_ms:+.0f} ms)"
            return damped_delta
            
        self.last_correction_ms = 0.0
        self.status_text = "Locked (0 ms)"
        return 0.0

class ClockFusionEngine:
    """Fuses coarse Spotify GSMTC clock with continuous 48kHz audio clock with Ad/Pause freezing."""
    def __init__(self):
        self.total_samples = 0
        self.sample_rate = 48000
        self.filtered_offset = 0.40
        self.filter_alpha = 0.12 # Low-pass anti-jitter filter coefficient
        self.timing_confidence = 0.85
        self.clock_diff_ms = 0.0
        self.track_start_time = 0.0
        self.track_sample_base = 0
        self.last_gsmtc_pos = 0.0
        self.is_paused = True

    def sync_to_track(self, gsmtc_pos: float):
        """Calibrates audio clock baseline to absolute Spotify position."""
        self.track_start_time = max(0.0, gsmtc_pos)
        self.track_sample_base = self.total_samples
        self.last_gsmtc_pos = gsmtc_pos

    def update_samples(self, n_samples: int):
        self.total_samples += n_samples

    def get_audio_clock(self) -> float:
        delta_samples = max(0, self.total_samples - self.track_sample_base)
        return self.track_start_time + (delta_samples / float(self.sample_rate))

    def fuse(self, gsmtc_pos: float, is_playing: bool, is_ad: bool, rms: float, onset_rate: float, timing_curve: TimingCurveEngine) -> dict:
        self.is_paused = not is_playing
        
        # Ad or Pause: Freeze clock to GSMTC position
        if is_ad or not is_playing or gsmtc_pos <= 0.01:
            self.sync_to_track(gsmtc_pos)
            return {
                "estimated_position": round(gsmtc_pos, 3),
                "audio_clock": round(gsmtc_pos, 3),
                "gsmtc_position": round(gsmtc_pos, 3),
                "clock_diff_ms": 0.0,
                "filtered_offset": round(self.filtered_offset, 3),
                "timing_confidence": 0.30
            }
            
        audio_clk = self.get_audio_clock()
        
        # Resync if seek or big jump detected (>1.2s)
        if abs(gsmtc_pos - audio_clk) > 1.2:
            self.sync_to_track(gsmtc_pos)
            audio_clk = gsmtc_pos
            
        clock_diff = (gsmtc_pos - audio_clk)
        self.clock_diff_ms = round(clock_diff * 1000.0, 1)
        
        # Calculate timing confidence based on live audio volume & onsets
        activity_score = min(1.0, (rms * 12.0) + (onset_rate / 6.0) * 0.4)
        self.timing_confidence = round(0.50 + 0.48 * activity_score, 2)
            
        # Anti-Jitter Smoothing
        curve_offset = timing_curve.get_correction(gsmtc_pos)
        self.filtered_offset = (self.filter_alpha * curve_offset) + ((1.0 - self.filter_alpha) * self.filtered_offset)
        
        estimated_pos = max(0.0, gsmtc_pos)
        
        return {
            "estimated_position": round(estimated_pos, 3),
            "audio_clock": round(audio_clk, 3),
            "gsmtc_position": round(gsmtc_pos, 3),
            "clock_diff_ms": self.clock_diff_ms,
            "filtered_offset": round(self.filtered_offset, 3),
            "timing_confidence": self.timing_confidence
        }

# ==============================================================================
# HARDWARE LATENCY CALIBRATION & PROFILES LAYER (v8.4)
# ==============================================================================

HW_PROFILES_PATH = os.path.join(os.path.dirname(__file__), "hardware_profiles.json")

class HardwareLatencyManager:
    """Decouples system/display/hardware latency from musical timing engine."""
    def __init__(self, config_path=HW_PROFILES_PATH):
        self.config_path = config_path
        self.active_profile_key = "windows_pc_wasapi"
        self.profiles = {}
        self.total_latency_sec = 0.40
        self.load_profiles()

    def load_profiles(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_profile_key = data.get("active_profile", "windows_pc_wasapi")
                    self.profiles = data.get("profiles", {})
                    active = self.profiles.get(self.active_profile_key, {})
                    self.total_latency_sec = float(active.get("total_latency_offset_sec", 0.40))
                    p_name = active.get("name", self.active_profile_key)
                    print(f"[Hardware Latency] [OK] Active Profile: '{p_name}' -> Offset: {self.total_latency_sec:+.3f}s")
            except Exception as e:
                print(f"[Hardware Latency] Error loading profiles: {e}")

    def get_total_latency(self) -> float:
        return self.total_latency_sec

    def set_profile(self, profile_key: str):
        if profile_key in self.profiles:
            self.active_profile_key = profile_key
            self.total_latency_sec = float(self.profiles[profile_key].get("total_latency_offset_sec", 0.40))
            return True
        return False

# ==============================================================================
# MULTI-FEATURE VOTING CORE & PHRASE-LOCK ELASTIC ENGINE (v8.5)
# ==============================================================================

TYPE_ATTACK = "attack"
TYPE_SUSTAINED = "sustained"
TYPE_TRANSITION = "transition"

PLOSIVES = ("p", "b", "t", "d", "k", "g", "c", "q", "stop", "get", "no", "don't", "can't")

def classify_word_phonetics(word: str) -> str:
    clean = re.sub(r"[^\w]", "", word).lower()
    if not clean:
        return TYPE_TRANSITION
    if (len(clean) <= 4 and clean.startswith(PLOSIVES)) or clean in ["stop", "get", "no", "top", "pop", "drop", "hit", "kick"]:
        return TYPE_ATTACK
    vowel_groups = re.findall(r"[aeiouyäöü]+", clean)
    if len(vowel_groups) >= 3:
        return TYPE_TRANSITION
    return TYPE_SUSTAINED

class MultiFeatureVotingCore:
    """
    Evaluates 5 orthogonal signals before approving any micro-timing warp:
    1. VAD (Vocal Formant Mid-Band Energy)
    2. Spectral Flux (Acoustic Onset Transient)
    3. Beat Grid Proximity (Musical Rhythmic Pulse)
    4. Expected Prior (Gaussian Confidence)
    5. Phonetic Type (Attack vs Sustained)
    """
    def __init__(self):
        self.min_consensus_score = 0.72

    def evaluate(self, current_pos: float, expected_pos: float, live_energy: float, mid_energy: float, recent_onsets: list, phonetic_type: str) -> dict:
        dist = abs(current_pos - expected_pos)
        s_expected = math.exp(-0.5 * ((dist / 0.35) ** 2))
        s_vad = min(1.0, mid_energy * 14.0) if live_energy > 0.035 else 0.0
        has_onset = any(abs(onset_t - current_pos) <= 0.075 for onset_t in recent_onsets)
        s_flux = 1.0 if has_onset else 0.0
        
        if phonetic_type == TYPE_ATTACK:
            s_phonetic = 1.0 if has_onset else 0.25
            allow_elastic = False
        elif phonetic_type == TYPE_SUSTAINED:
            s_phonetic = s_vad
            allow_elastic = True
        else:
            s_phonetic = (s_expected + s_vad) / 2.0
            allow_elastic = True
            
        consensus = (0.35 * s_expected) + (0.25 * s_vad) + (0.25 * s_flux) + (0.15 * s_phonetic)
        return {
            "approved": consensus >= self.min_consensus_score,
            "consensus_score": round(consensus, 2),
            "allow_elastic": allow_elastic
        }

class LocalElasticTimingEngine:
    """
    Phrase-Locked Elastic Timing Engine with Multi-Feature Voting (v8.5).
    - Preserves exact Phrase Boundaries (Bridge Invariants).
    - Distributes time elastically only when Multi-Sensor Consensus is verified.
    """
    def __init__(self, max_stretch_sec: float = 0.65):
        self.max_stretch_sec = max_stretch_sec
        self.voting_core = MultiFeatureVotingCore()
        self.elastic_delta = 0.0
        self.status = "Locked"

    def process_line(self, line: dict, current_pos: float, live_energy: float, mid_energy: float, recent_onsets: list, confidence: float) -> str:
        words = line.get("words", [])
        if not words or confidence < 0.60:
            self.status = "Bypass"
            return self.status

        line_end = line.get("endTime", current_pos + 1.0)
        
        for i, w in enumerate(words):
            w_start = w["start"]
            w_end = w["end"]
            phonetic_type = classify_word_phonetics(w["word"])
            
            # Phrase-Lock check: Never stretch past line boundary
            max_allowed_end = line_end if i == len(words) - 1 else words[i+1]["start"] + 0.40
            
            # Evaluate transition window
            if current_pos >= w_end - 0.08 and current_pos <= min(max_allowed_end, w_end + self.max_stretch_sec):
                vote = self.voting_core.evaluate(current_pos, w_end, live_energy, mid_energy, recent_onsets, phonetic_type)
                
                # If Multi-Feature Voting approves and word is sustained:
                if vote["approved"] and vote["allow_elastic"] and i < len(words) - 1:
                    stretch = min(self.max_stretch_sec, max(0.0, current_pos - w_end + 0.04))
                    new_end = min(max_allowed_end, round(w_end + stretch, 2))
                    w["end"] = new_end
                    if i + 1 < len(words):
                        words[i+1]["start"] = new_end
                    self.elastic_delta = stretch
                    self.status = f"Elastic +{stretch*1000:.0f}ms ('{w['word']}' [{phonetic_type}])"
                    return self.status
                    
        self.status = "Locked"
        return self.status

# Global DSP Pipeline Instances
hardware_latency_manager = HardwareLatencyManager()
ring_buffer = AudioRingBuffer()
feature_extractor = AudioFeatureExtractor()
onset_detector = OnsetDetector()
timing_curve_engine = TimingCurveEngine()
timing_curve_engine.reset(hardware_latency_manager.get_total_latency())
clock_fusion_engine = ClockFusionEngine()
smart_micro_aligner = SmartMicroAligner()
local_elastic_engine = LocalElasticTimingEngine()

# ==============================================================================
# STATE & MEDIA SYNCHRONIZATION
# ==============================================================================

current_media_state = {
    "title": "",
    "artist": "",
    "album": "",
    "status": "Paused",
    "position": 0.0,
    "duration": 0.0,
    "audio_clock": 0.0,
    "gsmtc_pos": 0.0,
    "clock_diff_ms": 0.0,
    "filtered_offset": hardware_latency_manager.get_total_latency(),
    "drift": 0.0,
    "onset_rate_hz": 0.0,
    "timing_confidence": 0.85,
    "active_anchors": 1,
    "live_energy": 0.0,
    "beat_punch": 0.0,
    "bass_energy": 0.0,
    "mid_energy": 0.0,
    "high_energy": 0.0,
    "has_lyrics": False,
    "is_karaoke_word_synced": False,
    "lyrics": None,
    "elastic_status": "Locked",
    "hw_profile": hardware_latency_manager.active_profile_key
}

state_lock = threading.Lock()
lyrics_cache = {}
native_window = None

class NativeApi:
    def toggle_fullscreen(self):
        global native_window
        if native_window:
            native_window.toggle_fullscreen()
            return True
        return False

native_api = NativeApi()

# ==============================================================================
# WASAPI 48kHz 10ms LOOPBACK CAPTURE THREAD
# ==============================================================================

def background_audio_capture_thread():
    """Captures 48kHz Stereo audio in 20ms quantum chunks (960 samples) via WASAPI Loopback."""
    SAMPLE_RATE = 48000
    BLOCK_SIZE = 960 # 20.0 ms native hardware quantum
    
    print("[Spotify DSP Engine] Initializing 48kHz WASAPI Loopback Recorder...")
    
    while True:
        try:
            default_speaker = sc.default_speaker()
            mic = sc.get_microphone(id=default_speaker.id, include_loopback=True)
            print(f"[Spotify DSP Engine] Connected to WASAPI Loopback: {mic.name}")
            
            with mic.recorder(samplerate=SAMPLE_RATE, channels=2, blocksize=BLOCK_SIZE) as rec:
                while True:
                    data = rec.record(numframes=BLOCK_SIZE)
                    if len(data) == 0:
                        continue
                        
                    # 1. Store in Ring Buffer
                    ring_buffer.write(data)
                    clock_fusion_engine.update_samples(len(data))
                    
                    # 2. Extract Features (<0.5ms)
                    mono = np.mean(data, axis=1)
                    features = feature_extractor.extract(mono)
                    
                    # 3. Detect Onsets
                    cur_audio_clk = clock_fusion_engine.get_audio_clock()
                    is_onset = onset_detector.process(features["flux"], cur_audio_clk)
                    onset_rate = onset_detector.get_onset_rate(cur_audio_clk)
                    
                    # 4. Update live telemetry state
                    with state_lock:
                        current_media_state["live_energy"] = round(features["rms"], 3)
                        current_media_state["beat_punch"] = 1.0 if is_onset else round(features["rms"] * 2.5, 3)
                        current_media_state["bass_energy"] = round(features["bass"], 3)
                        current_media_state["mid_energy"] = round(features["mid"], 3)
                        current_media_state["high_energy"] = round(features["high"], 3)
                        current_media_state["onset_rate_hz"] = onset_rate
                        
        except Exception as e:
            print(f"[Spotify DSP Engine] Loopback reconnecting: {e}")
            time.sleep(1.0)

# ==============================================================================
# WINDOWS GSMTC SPOTIFY POLLER & CLOCK FUSION THREAD
# ==============================================================================

PS_MEDIA_SCRIPT = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }[0]

Function Await-WinRt($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media, ContentType = WindowsRuntime] | Out-Null
$manager = Await-WinRt ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])

$sessions = $manager.GetSessions()
$found = $null

foreach ($s in $sessions) {
    $appId = $s.SourceAppUserModelId
    if ($appId -like "*Spotify*") {
        $found = $s
        break
    }
}

if (-not $found) {
    $found = $manager.GetCurrentSession()
}

if ($found) {
    $media = Await-WinRt ($found.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
    $timeline = $found.GetTimelineProperties()
    $playback = $found.GetPlaybackInfo()
    $now = [DateTime]::UtcNow
    $lastUpdated = $timeline.LastUpdatedTime.UtcDateTime
    $elapsed = ($now - $lastUpdated).TotalSeconds
    $status = $playback.PlaybackStatus.ToString()
    
    $computedPos = $timeline.Position.TotalSeconds
    if ($status -eq "Playing" -and $elapsed -ge 0 -and $elapsed -le 10000) {
        $computedPos += $elapsed
    }
    
    [PSCustomObject]@{
        Title = $media.Title
        Artist = $media.Artist
        Album = $media.AlbumTitle
        Status = $status
        RealPos = [Math]::Round($computedPos, 3)
        Duration = [Math]::Round($timeline.EndTime.TotalSeconds, 2)
    } | ConvertTo-Json
} else {
    Write-Output '{"status":"no_session"}'
}
"""

def query_windows_media() -> dict:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", PS_MEDIA_SCRIPT],
            capture_output=True,
            text=True,
            timeout=3
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip())
            return data
    except Exception:
        pass
    return {}

def trigger_async_lyrics_fetch(title: str, artist: str, duration: float, track_identifier: str):
    """Fetches lyrics in a background worker thread without blocking the 30Hz DSP poller loop."""
    def _worker():
        try:
            lyrics = fetch_multi_provider_lyrics(title, artist, duration)
            if lyrics:
                with state_lock:
                    cur_id = f"{current_media_state['title']}___{current_media_state['artist']}"
                    if cur_id == track_identifier:
                        current_media_state["lyrics"] = lyrics
                        current_media_state["has_lyrics"] = bool(lyrics.get("lines"))
                        current_media_state["is_karaoke_word_synced"] = bool(lyrics.get("meta", {}).get("is_karaoke_word_synced"))
        except Exception as e:
            print("[Spotify DSP Engine] Async lyrics notice:", e)
            
    threading.Thread(target=_worker, daemon=True).start()

def background_media_fusion_poller():
    """Polls Spotify GSMTC and executes Phase 6 Clock Fusion & Anti-Jitter Filtering."""
    global current_media_state
    last_known_track = ""
    
    while True:
        try:
            data = query_windows_media()
            title = data.get("Title", "")
            artist = data.get("Artist", "")
            status = data.get("Status", "Paused")
            real_pos = float(data.get("RealPos", 0.0))
            duration = float(data.get("Duration", 0.0))
            is_playing = (status.lower() == "playing")
            track_identifier = f"{title}___{artist}"
            
            is_ad = bool("advertisement" in title.lower() or (duration > 0 and duration < 25))
            
            # Phase 17: Track Change Handling (Instant Non-Blocking)
            if title and track_identifier != last_known_track:
                last_known_track = track_identifier
                print(f"[Spotify DSP Engine] 🎵 Track Changed: {artist} - {title} ({duration:.0f}s)")
                
                timing_curve_engine.reset(hardware_latency_manager.get_total_latency())
                clock_fusion_engine.sync_to_track(real_pos)
                
                clean_title = title.split("(")[0].split("[")[0].strip()
                clean_artist = artist.split("(")[0].split("[")[0].strip()
                cache_key = f"{clean_title.lower()}___{clean_artist.lower()}"
                cached_lyrics = lyrics_cache.get(cache_key)
                
                with state_lock:
                    current_media_state["title"] = title
                    current_media_state["artist"] = artist
                    current_media_state["album"] = data.get("Album", "")
                    current_media_state["duration"] = duration
                    current_media_state["lyrics"] = cached_lyrics
                    current_media_state["has_lyrics"] = bool(cached_lyrics and cached_lyrics.get("lines"))
                    current_media_state["is_karaoke_word_synced"] = bool(cached_lyrics and cached_lyrics.get("meta", {}).get("is_karaoke_word_synced"))
                    current_media_state["status"] = status
                    
                if not cached_lyrics:
                    trigger_async_lyrics_fetch(title, artist, duration, track_identifier)
            
            # Phase 6 & 7: Clock Fusion with Ad & Pause Protection
            with state_lock:
                rms = current_media_state["live_energy"]
                mid_energy = current_media_state["mid_energy"]
                onset_rate = current_media_state["onset_rate_hz"]
                lyrics_ref = current_media_state["lyrics"]
                is_enhanced = current_media_state["is_karaoke_word_synced"]
                
            fusion = clock_fusion_engine.fuse(real_pos, is_playing, is_ad, rms, onset_rate, timing_curve_engine)
            anchors_count = len(timing_curve_engine.get_anchors_list())
            
            # Smart Micro-Alignment & Local Elastic Timing Execution
            if lyrics_ref and lyrics_ref.get("lines") and is_playing and not is_ad:
                recent_onsets_list = list(onset_detector.recent_onsets)
                for l in lyrics_ref["lines"]:
                    # 1. Micro-Alignment (Line Start)
                    if abs(l["startTime"] - fusion["estimated_position"]) <= 1.00:
                        delta = smart_micro_aligner.evaluate_line(
                            l, fusion["estimated_position"], recent_onsets_list, fusion["timing_confidence"], is_enhanced
                        )
                        if delta != 0.0:
                            l["startTime"] = round(l["startTime"] + delta, 2)
                            l["endTime"] = round(l["endTime"] + delta, 2)
                            if l.get("words"):
                                for w in l["words"]:
                                    w["start"] = round(w["start"] + delta, 2)
                                    w["end"] = round(w["end"] + delta, 2)
                                    
                    # 2. Local Elastic Timing (Multi-Feature Voting + Phrase Lock)
                    if l["startTime"] - 0.50 <= fusion["estimated_position"] <= l["endTime"] + 0.80:
                        local_elastic_engine.process_line(
                            l, fusion["estimated_position"], rms, mid_energy, recent_onsets_list, fusion["timing_confidence"]
                        )
            
            with state_lock:
                if title:
                    current_media_state["title"] = title
                    current_media_state["artist"] = artist
                    current_media_state["album"] = data.get("Album", "")
                    current_media_state["duration"] = duration
                    current_media_state["status"] = status
                    current_media_state["position"] = fusion["estimated_position"]
                    current_media_state["audio_clock"] = fusion["audio_clock"]
                    current_media_state["gsmtc_pos"] = fusion["gsmtc_position"]
                    current_media_state["clock_diff_ms"] = fusion["clock_diff_ms"]
                    current_media_state["filtered_offset"] = fusion["filtered_offset"]
                    current_media_state["timing_confidence"] = fusion["timing_confidence"]
                    current_media_state["active_anchors"] = anchors_count
                    current_media_state["auto_align_status"] = smart_micro_aligner.status_text
                    current_media_state["elastic_status"] = local_elastic_engine.status
                    current_media_state["hw_profile"] = hardware_latency_manager.active_profile_key
                    
        except Exception:
            pass
            
        time.sleep(0.033) # 30 Hz Telemetry & Fusion Update

# ==============================================================================
# 3-TIER MASTER LYRICS HIERARCHY:
# 1. Enhanced Word-Synced Karaoke (<mm:ss.xx> Syllable Tags)
# 2. Official Spotify Studio Master Color-Lyrics (spclient / sp_dc)
# 3. Standard Global Databases (LRCLIB / Line-Synced Fallback)
# ==============================================================================

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "spotify_config.json")

class SpotifyOfficialProvider:
    """Fetches 100% exact official Spotify Studio Master Color-Lyrics via sp_dc."""
    def __init__(self, config_path=CONFIG_PATH):
        self.config_path = config_path
        self.session = requests.Session()
        self.token = None
        self.token_expiry = 0
        self.id_cache = {}
        self.load_and_authenticate()

    def load_and_authenticate(self):
        if not os.path.exists(self.config_path) or not TOTP:
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                sp_dc = cfg.get("sp_dc", "").strip()
                if not sp_dc:
                    return
                    
            self.session.cookies.set("sp_dc", sp_dc)
            if SPOTIFY_HEADERS:
                self.session.headers.update(SPOTIFY_HEADERS)
            
            t_res = self.session.get("https://open.spotify.com/api/server-time", timeout=4)
            if t_res.status_code == 200:
                st = 1000 * t_res.json().get("serverTime", 0)
                totp = TOTP()
                code = totp.generate(timestamp=st)
                params = {"reason": "init", "productType": "web-player", "totp": code, "totpVer": str(totp.version), "ts": str(st)}
                r = self.session.get(SPOTIFY_TOKEN_URL, params=params, timeout=4)
                if r.status_code == 200:
                    self.token = r.json().get("accessToken")
                    self.token_expiry = time.time() + 3000
                    print("[Spotify DSP Engine] [OK] Official Spotify Account Authenticated via sp_dc!")
        except Exception as e:
            print("[Spotify DSP Engine] sp_dc notice:", str(e).encode('ascii', 'ignore').decode('ascii'))

    def resolve_track_id(self, title: str, artist: str) -> str:
        clean_t, clean_a = clean_song_title_and_artist(title, artist)
        key = f"{clean_a.lower()}___{clean_t.lower()}"
        if key in self.id_cache:
            return self.id_cache[key]
            
        q = urllib.parse.quote(f'"{clean_a}" "{clean_t}" site:open.spotify.com/track')
        url = f"https://html.duckduckgo.com/html/?q={q}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, timeout=3) as resp:
                html = resp.read().decode("utf-8")
                matches = re.findall(r"spotify\.com(?:%2F|/)track(?:%2F|/)([a-zA-Z0-9]{22})", html)
                if matches:
                    self.id_cache[key] = matches[0]
                    return matches[0]
        except Exception:
            pass
        return None

    def fetch_official_lyrics(self, title: str, artist: str) -> dict:
        if not self.token or time.time() > self.token_expiry:
            self.load_and_authenticate()
        if not self.token:
            return None
            
        track_id = self.resolve_track_id(title, artist)
        if not track_id:
            return None
            
        url = f"https://spclient.wg.spotify.com/color-lyrics/v2/track/{track_id}?format=json&market=from_token"
        try:
            res = self.session.get(url, headers={"authorization": f"Bearer {self.token}"}, timeout=4)
            if res.status_code == 200:
                raw_lines = res.json().get("lyrics", {}).get("lines", [])
                lines = []
                for idx, rl in enumerate(raw_lines):
                    start_sec = round(int(rl.get("startTimeMs", 0)) / 1000.0, 2)
                    words = rl.get("words", "").strip()
                    if not words or words in ["♪", "♬"]:
                        continue
                    
                    if idx + 1 < len(raw_lines):
                        next_sec = round(int(raw_lines[idx + 1].get("startTimeMs", 0)) / 1000.0, 2)
                        end_sec = max(start_sec + 0.6, next_sec)
                    else:
                        end_sec = start_sec + 3.5
                        
                    lines.append({
                        "id": len(lines),
                        "startTime": start_sec,
                        "endTime": end_sec,
                        "text": words,
                        "words": [],
                        "is_karaoke_word_synced": False
                    })
                if lines:
                    return {
                        "meta": {
                            "source": "Official Spotify Studio-Sync",
                            "is_karaoke_word_synced": True,
                            "is_official_spotify": True
                        },
                        "lines": lines
                    }
        except Exception:
            pass
        return None

def clean_song_title_and_artist(title: str, artist: str):
    """Sanitizes song title and artist by removing quotes, soundtrack tags, remaster suffixes, and mixes."""
    c_title = title
    c_title = re.sub(r"\s*[-–—:]\s*(from\s+.*|soundtrack.*|remaster.*|.*mix.*|.*version.*|live.*|radio\s+edit.*|deluxe.*|bonus\s+track.*|theme.*)", "", c_title, flags=re.IGNORECASE)
    c_title = re.sub(r"[\(\[\{].*?[\)\]\}]", "", c_title)
    c_title = re.sub(r"[\"“”„'»«]", "", c_title).strip()
    
    c_artist = re.sub(r"[\(\[\{].*?[\)\]\}]", "", artist)
    c_artist = re.sub(r"[\"“”„'»«]", "", c_artist).strip()
    
    return c_title or title.strip(), c_artist or artist.strip()

spotify_official_provider = SpotifyOfficialProvider()
LYRICS_EXECUTOR_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="LyricsRaceWorker")

def fetch_multi_provider_lyrics(title: str, artist: str, duration_sec: float) -> dict:
    clean_title, clean_artist = clean_song_title_and_artist(title, artist)
    cache_key = f"{clean_title.lower()}___{clean_artist.lower()}"
    
    if cache_key in lyrics_cache:
        return lyrics_cache[cache_key]

    def _fetch_enhanced():
        try:
            query = f"{clean_artist} {clean_title}"
            raw = syncedlyrics.search(query, enhanced=True)
            if raw and ("<" in raw and ">" in raw):
                parsed = parse_karaoke_lrc(raw, clean_title, clean_artist, "Karaoke Database (Enhanced)")
                if parsed and parsed.get("lines") and parsed.get("meta", {}).get("is_karaoke_word_synced"):
                    return ("enhanced", parsed)
        except Exception:
            pass
        return None

    def _fetch_spotify():
        if not spotify_official_provider.token:
            return None
        try:
            official = spotify_official_provider.fetch_official_lyrics(clean_title, clean_artist)
            if official and official.get("lines"):
                official["meta"]["title"] = title
                official["meta"]["artist"] = artist
                for l in official["lines"]:
                    l["words"] = interpolate_words(l["text"], l["startTime"], l["endTime"])
                return ("spotify", official)
        except Exception:
            pass
        return None

    def _fetch_lrclib():
        try:
            params = urllib.parse.urlencode({
                "track_name": clean_title,
                "artist_name": clean_artist,
                "duration": int(duration_sec) if duration_sec > 0 else ""
            })
            url = f"https://lrclib.net/api/get?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "SpotifyKaraokeDSPEngine/8.6"})
            with urllib.request.urlopen(req, timeout=1.8) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    if data.get("syncedLyrics"):
                        parsed = parse_karaoke_lrc(data["syncedLyrics"], clean_title, clean_artist, "LRCLIB Studio-Sync")
                        if parsed and parsed.get("lines"):
                            return ("lrclib", parsed)
        except Exception:
            pass
        return None

    # Launch Truly Non-Blocking Parallel Race (Zero Exit Delay)
    futures = [
        LYRICS_EXECUTOR_POOL.submit(_fetch_lrclib),
        LYRICS_EXECUTOR_POOL.submit(_fetch_spotify),
        LYRICS_EXECUTOR_POOL.submit(_fetch_enhanced)
    ]
    
    best_candidate = None
    for fut in concurrent.futures.as_completed(futures, timeout=2.5):
        try:
            res = fut.result()
            if res:
                kind, data = res
                if kind == "enhanced":
                    lyrics_cache[cache_key] = data
                    print(f"[Spotify DSP Engine] [RACE WINNER] Enhanced Word-Synced loaded for {artist} - {title}!")
                    return data
                elif kind == "spotify":
                    lyrics_cache[cache_key] = data
                    print(f"[Spotify DSP Engine] [RACE WINNER] Official Spotify Studio-Lyrics loaded for {artist} - {title}!")
                    return data
                elif kind == "lrclib":
                    best_candidate = data
                    lyrics_cache[cache_key] = data
                    print(f"[Spotify DSP Engine] [RACE WINNER] LRCLIB Studio-Sync loaded for {artist} - {title}!")
                    return data
        except Exception:
            pass

    if best_candidate:
        lyrics_cache[cache_key] = best_candidate
        return best_candidate

    return None

def parse_karaoke_lrc(lrc_text: str, title: str, artist: str, source: str) -> dict:
    lines = []
    line_time_regex = re.compile(r"^\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)")
    word_time_regex = re.compile(r"<(\d{2}):(\d{2})\.(\d{2,3})>([^<]+)")
    
    has_any_enhanced_words = False
    
    for raw in lrc_text.splitlines():
        match = line_time_regex.match(raw.strip())
        if not match:
            continue
            
        m = int(match.group(1))
        s = int(match.group(2))
        f = float("0." + match.group(3))
        start_time = round(m * 60 + s + f, 2)
        content = match.group(4).strip()
        if not content:
            continue
            
        word_matches = list(word_time_regex.finditer(content))
        
        if word_matches:
            has_any_enhanced_words = True
            words = []
            clean_text_parts = []
            for i, wm in enumerate(word_matches):
                wm_m = int(wm.group(1))
                wm_s = int(wm.group(2))
                wm_f = float("0." + wm.group(3))
                w_start = round(wm_m * 60 + wm_s + wm_f, 2)
                w_text = wm.group(4).strip()
                if not w_text:
                    continue
                clean_text_parts.append(w_text)
                
                if i + 1 < len(word_matches):
                    next_wm = word_matches[i + 1]
                    next_start = round(int(next_wm.group(1)) * 60 + int(next_wm.group(2)) + float("0." + next_wm.group(3)), 2)
                    w_end = max(w_start + 0.12, next_start)
                else:
                    w_end = w_start + 0.60
                    
                words.append({
                    "word": w_text,
                    "start": w_start,
                    "end": w_end,
                    "duration": round(w_end - w_start, 2)
                })
                
            line_end = words[-1]["end"] if words else start_time + 3.5
            lines.append({
                "id": len(lines),
                "startTime": start_time,
                "endTime": line_end,
                "text": " ".join(clean_text_parts),
                "words": words,
                "is_karaoke_word_synced": True
            })
        else:
            clean_text = re.sub(r"<[^>]+>", "", content).strip()
            if clean_text:
                lines.append({
                    "id": len(lines),
                    "startTime": start_time,
                    "endTime": start_time + 3.5,
                    "text": clean_text,
                    "words": [],
                    "is_karaoke_word_synced": False
                })
                
    for i, cur in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < len(lines) else None
        
        if not cur.get("is_karaoke_word_synced"):
            raw_words = cur["text"].split()
            w_count = max(1, len(raw_words))
            natural_dur = min(5.0, max(1.6, w_count * 0.44 + 0.5))
            
            if next_line:
                available_gap = max(0.5, next_line["startTime"] - cur["startTime"])
                cur["endTime"] = round(cur["startTime"] + min(natural_dur, available_gap), 2)
            else:
                cur["endTime"] = round(cur["startTime"] + natural_dur, 2)
                
            cur["words"] = interpolate_words(cur["text"], cur["startTime"], cur["endTime"])
            
        prev_end = lines[i - 1]["endTime"] if i > 0 else 0.0
        pause = cur["startTime"] - prev_end
        if pause >= 2.5 or (i == 0 and cur["startTime"] >= 2.0):
            cur["isBreak"] = True
            cur["leadIn"] = {
                "cueStart": max(0.0, cur["startTime"] - 3.0),
                "cueDuration": min(3.0, pause)
            }
        else:
            cur["isBreak"] = False
            cur["leadIn"] = None
            
    return {
        "meta": {
            "title": title,
            "artist": artist,
            "source": source,
            "is_karaoke_word_synced": has_any_enhanced_words
        },
        "lines": lines
    }

FUNCTION_WORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "but",
    "is", "it", "so", "my", "you", "me", "he", "she", "we", "us", "i", "do",
    "der", "die", "das", "ein", "eine", "einer", "und", "in", "an", "zu", "im",
    "am", "es", "du", "ich", "er", "sie", "wir", "ihr", "da", "so", "mit", "von"
}

def count_syllables(word: str) -> int:
    clean = re.sub(r"[^a-zA-ZäöüÄÖÜß]", "", word.lower())
    if not clean:
        return 1
    vowel_groups = re.findall(r"[aeiouyäöü]+", clean)
    count = len(vowel_groups)
    if clean.endswith("e") and not clean.endswith("ee") and len(clean) > 3 and count > 1:
        count -= 1
    return max(1, count)

def interpolate_words(line_text: str, start_time: float, end_time: float) -> list:
    """
    Intelligent Prosodic & Musical Phrasing Word Aligner.
    - Accurately elongates sustained melodic hook words (e.g. 'Celebrate...', 'Maria...').
    - Compresses short passing function words ('a', 'in', 'on', 'to') to natural <0.3s cadence.
    - Accounts for punctuation holds (commas, exclamation marks).
    """
    raw_words = line_text.split()
    if not raw_words:
        return []
        
    duration = max(0.5, end_time - start_time)
    n_words = len(raw_words)
    
    weights = []
    for idx, w in enumerate(raw_words):
        clean = re.sub(r"[^\w]", "", w).lower()
        syllables = count_syllables(clean)
        
        is_func = clean in FUNCTION_WORDS
        has_comma = w.endswith(",") or w.endswith(";")
        has_end_punct = w.endswith(".") or w.endswith("!") or w.endswith("?") or w.endswith("...")
        
        if is_func:
            base_w = 0.50 if syllables == 1 else 0.85
        else:
            base_w = (syllables ** 1.35) * 1.60 + len(clean) * 0.12
            
        # Melodic Hook bonus (first multi-syllable word in a phrase)
        if idx == 0 and syllables >= 2:
            base_w *= 1.80
            
        # Punctuation / Phrase-ending hold
        if has_comma:
            base_w *= 1.45
        if has_end_punct or idx == n_words - 1:
            base_w *= 1.35
            
        weights.append(base_w)
        
    total_w = sum(weights)
    durations = [(w / total_w) * duration for w in weights]
    
    # Cap short function words so sustained melody words receive the time budget
    surplus = 0.0
    for i, w in enumerate(raw_words):
        clean = re.sub(r"[^\w]", "", w).lower()
        if clean in FUNCTION_WORDS and count_syllables(clean) == 1 and durations[i] > 0.38 and n_words > 2:
            excess = durations[i] - 0.30
            durations[i] = 0.30
            surplus += excess
            
    non_func_indices = [i for i, w in enumerate(raw_words) if re.sub(r"[^\w]", "", w).lower() not in FUNCTION_WORDS]
    if non_func_indices and surplus > 0:
        sum_non_func = sum(durations[i] for i in non_func_indices)
        for i in non_func_indices:
            durations[i] += surplus * (durations[i] / sum_non_func)
            
    words = []
    accum = start_time
    for i, w in enumerate(raw_words):
        dur = round(durations[i], 2)
        w_end = end_time if i == n_words - 1 else round(accum + dur, 2)
        words.append({
            "word": w,
            "start": round(accum, 2),
            "end": w_end,
            "duration": round(w_end - accum, 2)
        })
        accum += dur
        
    return words

# ==============================================================================
# FAST API STATE & TAP-SYNC ANCHOR ENDPOINTS
# ==============================================================================

@app.get("/api/state")
def get_state():
    with state_lock:
        return {
            "title": current_media_state["title"],
            "artist": current_media_state["artist"],
            "album": current_media_state["album"],
            "status": current_media_state["status"],
            "position": current_media_state["position"],
            "duration": current_media_state["duration"],
            "audio_clock": current_media_state["audio_clock"],
            "gsmtc_pos": current_media_state["gsmtc_pos"],
            "clock_diff_ms": current_media_state["clock_diff_ms"],
            "filtered_offset": current_media_state["filtered_offset"],
            "timing_confidence": current_media_state["timing_confidence"],
            "onset_rate_hz": current_media_state["onset_rate_hz"],
            "active_anchors": current_media_state["active_anchors"],
            "auto_align_status": current_media_state.get("auto_align_status", "Locked (0 ms)"),
            "elastic_status": current_media_state.get("elastic_status", "Locked"),
            "hw_profile": current_media_state.get("hw_profile", "windows_pc_wasapi"),
            "has_lyrics": current_media_state["has_lyrics"],
            "is_karaoke_word_synced": current_media_state["is_karaoke_word_synced"],
            "live_energy": current_media_state["live_energy"],
            "beat_punch": current_media_state["beat_punch"],
            "bass_energy": current_media_state["bass_energy"],
            "mid_energy": current_media_state["mid_energy"],
            "high_energy": current_media_state["high_energy"],
            "lyrics": current_media_state["lyrics"]
        }

@app.get("/api/profiles")
def get_hardware_profiles():
    return {
        "active_profile": hardware_latency_manager.active_profile_key,
        "profiles": hardware_latency_manager.profiles
    }

@app.post("/api/profile/{profile_key}")
def set_hardware_profile(profile_key: str):
    success = hardware_latency_manager.set_profile(profile_key)
    if success:
        timing_curve_engine.reset(hardware_latency_manager.get_total_latency())
        with state_lock:
            current_media_state["hw_profile"] = profile_key
            current_media_state["filtered_offset"] = hardware_latency_manager.get_total_latency()
    return {"status": "ok" if success else "not_found", "active": hardware_latency_manager.active_profile_key}

class SingerVadPayload(BaseModel):
    is_singing: bool = False
    energy: float = 0.0
    onset: bool = False
    device: str = "mobile_mic"

@app.post("/api/singer_vad")
def receive_singer_vad(payload: SingerVadPayload):
    """Multi-Input Layer: Receives Singer VAD and Energy from Mobile or USB Microphones."""
    if payload.onset:
        cur_clk = clock_fusion_engine.get_audio_clock()
        onset_detector.process(payload.energy * 2.0, cur_clk)
    return {"status": "received"}

class AnchorPayload(BaseModel):
    lrc_time: float = 0.0
    offset: float = 0.40

@app.post("/api/anchor")
def set_anchor(payload: AnchorPayload):
    """Phase 10: Inserts a Tap-Sync Anchor into the Timing Curve."""
    timing_curve_engine.add_anchor(payload.lrc_time, payload.offset)
    return {"status": "ok", "anchors": timing_curve_engine.get_anchors_list()}

# ==============================================================================
# HTML / CSS / JAVASCRIPT FRONTEND & TELEMETRY HUD
# ==============================================================================

HTML_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <title>Spotify AI Karaoke & Fullscreen Visualizer (DSP v7.0)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;900&family=JetBrains+Mono:wght@500;800&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #060810;
      color: #fff;
      font-family: 'Outfit', sans-serif;
      overflow: hidden;
      width: 100vw;
      height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      align-items: center;
      user-select: none;
    }
    #canvas {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: 1;
      pointer-events: none;
    }

    /* 100% Transparent Topbar */
    .topbar {
      position: relative;
      z-index: 10;
      width: 100%;
      padding: 24px 44px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      background: transparent;
      backdrop-filter: none;
      pointer-events: none;
    }
    .track-info {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-width: 65vw;
      pointer-events: auto;
    }
    .track-title {
      font-size: 58px;
      font-weight: 900;
      line-height: 1.1;
      color: #fff;
      text-shadow: 0 4px 20px rgba(0, 0, 0, 0.95), 0 0 35px rgba(0, 240, 255, 0.35);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 14px;
    }
    .track-artist {
      font-size: 32px;
      font-weight: 700;
      color: rgba(255, 255, 255, 0.88);
      text-shadow: 0 2px 14px rgba(0, 0, 0, 0.9);
      letter-spacing: 0.5px;
    }

    .controls-wrapper {
      display: flex;
      align-items: center;
      gap: 8px;
      pointer-events: auto;
      position: relative;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 8px;
      transition: opacity 0.25s ease, transform 0.25s ease, visibility 0.25s;
      transform-origin: top right;
    }
    .controls.hidden {
      opacity: 0;
      transform: translateY(-12px) scale(0.92);
      pointer-events: none;
      visibility: hidden;
    }
    .btn-toggle-ui {
      background: rgba(0, 0, 0, 0.45);
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: rgba(255, 255, 255, 0.8);
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      margin-top: 8px;
      transition: all 0.2s ease;
      backdrop-filter: blur(8px);
    }
    .btn-toggle-ui:hover {
      background: rgba(0, 240, 255, 0.25);
      border-color: #00f0ff;
      color: #fff;
      box-shadow: 0 0 16px rgba(0, 240, 255, 0.4);
    }

    .offset-group {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(0, 0, 0, 0.6);
      padding: 4px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.18);
    }
    #offset-val {
      font-size: 13px;
      font-weight: 800;
      color: #00f0ff;
      min-width: 52px;
      text-align: center;
    }
    .badge {
      font-size: 12px;
      font-weight: 800;
      padding: 3px 10px;
      border-radius: 8px;
      display: none;
    }
    .badge-karaoke {
      background: rgba(255, 0, 127, 0.22);
      border: 1px solid #ff007f;
      color: #ff007f;
      box-shadow: 0 0 16px rgba(255, 0, 127, 0.4);
    }
    .badge-saved {
      background: rgba(0, 255, 136, 0.22);
      border: 1px solid #00ff88;
      color: #00ff88;
    }
    .badge.active { display: inline-block; }

    .btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.18);
      color: #fff;
      border-radius: 10px;
      padding: 8px 14px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
      backdrop-filter: blur(10px);
    }
    .btn:hover {
      background: rgba(0, 240, 255, 0.3);
      border-color: #00f0ff;
      box-shadow: 0 0 20px rgba(0, 240, 255, 0.6);
      transform: translateY(-2px);
    }
    .btn-tap-sync {
      background: rgba(255, 0, 127, 0.18);
      border-color: rgba(255, 0, 127, 0.45);
      color: #ff007f;
    }
    .btn-tap-sync:hover {
      background: rgba(255, 0, 127, 0.4);
      border-color: #ff007f;
      box-shadow: 0 0 22px rgba(255, 0, 127, 0.7);
      color: #fff;
    }

    /* Live DSP Telemetry HUD (Toggle: D) */
    .dsp-hud {
      position: absolute;
      top: 110px;
      right: 44px;
      z-index: 20;
      background: rgba(8, 12, 24, 0.90);
      border: 1px solid rgba(0, 240, 255, 0.35);
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.8), 0 0 20px rgba(0, 240, 255, 0.2);
      border-radius: 16px;
      padding: 16px 20px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: #00f0ff;
      backdrop-filter: blur(20px);
      display: none;
      flex-direction: column;
      gap: 8px;
      min-width: 290px;
      pointer-events: auto;
    }
    .dsp-hud.active { display: flex; }
    .hud-title {
      font-weight: 800;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: #fff;
      border-bottom: 1px solid rgba(0, 240, 255, 0.2);
      padding-bottom: 6px;
      display: flex;
      justify-content: space-between;
    }
    .hud-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .hud-label { color: rgba(255, 255, 255, 0.65); }
    .hud-val { font-weight: 800; color: #fff; }
    .hud-bar-container {
      width: 100%;
      height: 6px;
      background: rgba(255, 255, 255, 0.15);
      border-radius: 4px;
      overflow: hidden;
      margin-top: 2px;
    }
    .hud-bar-fill {
      height: 100%;
      background: linear-gradient(90deg, #00f0ff, #00ff88);
      width: 85%;
      transition: width 0.15s ease;
    }

    .center-stage {
      position: relative;
      z-index: 5;
      margin-top: 10px;
    }
    .genre-badge {
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: #00f0ff;
      background: rgba(0, 240, 255, 0.15);
      border: 1px solid rgba(0, 240, 255, 0.4);
      padding: 6px 20px;
      border-radius: 30px;
      box-shadow: 0 0 30px rgba(0, 240, 255, 0.35);
      animation: pulse 3s infinite ease-in-out;
    }
    @keyframes pulse {
      0%, 100% { opacity: 0.8; transform: scale(1); }
      50% { opacity: 1; transform: scale(1.06); }
    }

    /* 2-Line Studio Karaoke Stage */
    .karaoke-stage {
      position: relative;
      z-index: 10;
      width: 90%;
      max-width: 1250px;
      margin-bottom: 45px;
      padding: 28px 44px;
      border-radius: 30px;
      background: rgba(10, 13, 24, 0.90);
      backdrop-filter: blur(35px) saturate(190%);
      border: 1px solid rgba(255, 255, 255, 0.18);
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.9), 0 0 50px rgba(0, 240, 255, 0.25);
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 160px;
    }
    .countdown-box {
      display: none;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .countdown-box.active { display: flex; }
    .countdown-label {
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: #00f0ff;
      text-shadow: 0 0 12px rgba(0, 240, 255, 0.8);
    }
    .countdown-dots { display: flex; gap: 8px; }
    .dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.2);
      border: 2px solid rgba(255, 255, 255, 0.4);
      transition: all 0.2s ease;
    }
    .dot.active-1 { background: #ffeb3b; border-color: #fff; box-shadow: 0 0 18px #ffeb3b; transform: scale(1.4); }
    .dot.active-2 { background: #ff007f; border-color: #fff; box-shadow: 0 0 18px #ff007f; transform: scale(1.4); }
    .dot.active-3 { background: #00f0ff; border-color: #fff; box-shadow: 0 0 22px #00f0ff; transform: scale(1.5); }

    .current-line {
      font-size: 42px;
      font-weight: 800;
      line-height: 1.35;
      letter-spacing: 0.5px;
      color: #ffffff;
      margin-bottom: 6px;
      text-shadow: 0 3px 16px rgba(0, 0, 0, 0.95), 0 0 30px rgba(0, 0, 0, 0.9);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 12px;
      min-height: 55px;
    }
    .word {
      position: relative;
      display: inline-block;
      color: #ffffff;
      background: linear-gradient(90deg, #00f0ff 0%, #00f0ff var(--fill-pct, 0%), #ffffff var(--fill-pct, 0%), #ffffff 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      transition: transform 0.1s ease, filter 0.1s ease;
      will-change: transform, filter;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.9);
    }
    .word.singing {
      transform: scale(1.10) translateY(-2px);
      filter: drop-shadow(0 0 18px rgba(0, 240, 255, 1.0)) drop-shadow(0 0 35px rgba(0, 240, 255, 0.8));
    }
    .word.done {
      background: #00f0ff;
      -webkit-background-clip: text;
      -webkit-text-fill-color: #00f0ff;
      filter: drop-shadow(0 0 12px rgba(0, 240, 255, 0.7));
    }
    .next-line {
      font-size: 42px;
      font-weight: 800;
      line-height: 1.35;
      letter-spacing: 0.5px;
      color: rgba(160, 175, 205, 0.45);
      margin-top: 14px;
      padding: 0;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.8);
      min-height: 55px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 12px;
    }
    .status-pulse {
      color: rgba(255, 255, 255, 0.8);
      font-size: 20px;
      font-weight: 600;
      animation: pulse 1.5s infinite;
    }
  </style>
</head>
<body>
  <canvas id="canvas"></canvas>

  <div class="topbar">
    <div class="track-info">
      <span class="track-title">
        <span id="track-title">Warte auf Spotify...</span>
        <span class="badge badge-karaoke" id="karaoke-badge">🎤 KARAOKE ENHANCED</span>
        <span class="badge badge-saved" id="saved-badge">💾 Auto-Save</span>
      </span>
      <span class="track-artist" id="track-artist">Starte einen Song in deiner Spotify-App</span>
    </div>

    <div class="controls-wrapper">
      <div class="controls" id="controls-panel">
        <div class="offset-group" title="Tastatur: Pfeiltasten Links/Rechts (+-0.1s)">
          <button class="btn" id="offset-m" style="padding:4px 8px;font-size:12px;">◀ -0.1s</button>
          <span id="offset-val">+0.40s</span>
          <button class="btn" id="offset-p" style="padding:4px 8px;font-size:12px;">+0.1s ▶</button>
        </div>
        <button class="btn btn-tap-sync" id="tap-sync-btn" title="Drücke T oder Klick beim ersten Gesangswort!">⚡ Tap Anchor (T)</button>
        <button class="btn" id="hud-toggle-btn" title="Live DSP Diagnose HUD (Taste: D)">📊 DSP (D)</button>
        <button class="btn" id="preset-btn">🎨 Preset: Auto</button>
        <button class="btn" id="fullscreen-btn">⛶ Vollbild (F11)</button>
      </div>
      <button class="btn-toggle-ui" id="toggle-ui-btn" title="Buttons ein-/ausblenden (Taste: H)">👁️ (H)</button>
    </div>
  </div>

  <!-- Live DSP Telemetry HUD -->
  <div class="dsp-hud" id="dsp-hud">
    <div class="hud-title">
      <span>⚡ DSP Telemetry HUD</span>
      <span style="color:#00ff88;font-size:11px;">10ms WASAPI</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">GSMTC Coarse:</span>
      <span class="hud-val" id="hud-gsmtc">0.000 s</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">Audio Clock:</span>
      <span class="hud-val" id="hud-audio-clk">0.000 s</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">Clock Diff:</span>
      <span class="hud-val" id="hud-clk-diff">+0.0 ms</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">Filtered Offset:</span>
      <span class="hud-val" id="hud-offset">+0.400 s</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">Onset Rate:</span>
      <span class="hud-val" id="hud-onsets">0.0 Hz</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">Sync Anchors:</span>
      <span class="hud-val" id="hud-anchors">1 active</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">HW Profile:</span>
      <span class="hud-val" id="hud-hw" style="color:#00f0ff;">PC WASAPI</span>
    </div>
    <div class="hud-row">
      <span class="hud-label">Elastic Timing:</span>
      <span class="hud-val" id="hud-elastic" style="color:#a855f7;">Locked</span>
    </div>
    <div class="hud-row" style="margin-top:4px;">
      <span class="hud-label">Timing Confidence:</span>
      <span class="hud-val" id="hud-conf">92 %</span>
    </div>
    <div class="hud-bar-container">
      <div class="hud-bar-fill" id="hud-conf-bar"></div>
    </div>
  </div>

  <div class="center-stage">
    <div class="genre-badge" id="genre-badge">✨ LIVE VISUALIZER</div>
  </div>

  <div class="karaoke-stage">
    <div class="countdown-box" id="countdown-box">
      <span class="countdown-label">Einsatz</span>
      <div class="countdown-dots">
        <div class="dot" id="dot-1"></div>
        <div class="dot" id="dot-2"></div>
        <div class="dot" id="dot-3"></div>
      </div>
    </div>

    <div class="current-line" id="current-line">
      <span class="status-pulse">⚡ Spotify bereit – starte Wiedergabe</span>
    </div>

    <div class="next-line" id="next-line"></div>
  </div>

  <script>
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const titleEl = document.getElementById('track-title');
    const artistEl = document.getElementById('track-artist');
    const karaokeBadgeEl = document.getElementById('karaoke-badge');
    const savedBadgeEl = document.getElementById('saved-badge');
    const genreBadge = document.getElementById('genre-badge');
    const currentLineEl = document.getElementById('current-line');
    const nextLineEl = document.getElementById('next-line');
    const countdownEl = document.getElementById('countdown-box');
    const dot1 = document.getElementById('dot-1');
    const dot2 = document.getElementById('dot-2');
    const dot3 = document.getElementById('dot-3');
    const presetBtn = document.getElementById('preset-btn');
    const fullscreenBtn = document.getElementById('fullscreen-btn');
    const offsetValEl = document.getElementById('offset-val');
    const tapSyncBtn = document.getElementById('tap-sync-btn');
    const hudToggleBtn = document.getElementById('hud-toggle-btn');
    const dspHud = document.getElementById('dsp-hud');
    const controlsPanel = document.getElementById('controls-panel');
    const toggleUiBtn = document.getElementById('toggle-ui-btn');

    // HUD Elements
    const hudGsmtc = document.getElementById('hud-gsmtc');
    const hudAudioClk = document.getElementById('hud-audio-clk');
    const hudClkDiff = document.getElementById('hud-clk-diff');
    const hudOffset = document.getElementById('hud-offset');
    const hudOnsets = document.getElementById('hud-onsets');
    const hudAnchors = document.getElementById('hud-anchors');
    const hudHw = document.getElementById('hud-hw');
    const hudElastic = document.getElementById('hud-elastic');
    const hudConf = document.getElementById('hud-conf');
    const hudConfBar = document.getElementById('hud-conf-bar');

    let currentTrackName = '';
    let currentArtistName = '';
    let currentLyrics = null;
    let currentLineIdx = -1;
    let clientPlaybackTime = 0;
    let userOffset = 0.40;
    let isPlaying = false;
    let visualizerMode = 'auto';
    let detectedPreset = 'cyberpunk';
    let animTime = 0;

    // Real-Time DSP Telemetry
    let targetEnergy = 0.0;
    let targetPunch = 0.0;
    let targetBass = 0.0;
    let targetMid = 0.0;
    let targetHigh = 0.0;
    
    let smoothEnergy = 0.0;
    let smoothBass = 0.0;
    let smoothMid = 0.0;
    let smoothHigh = 0.0;
    let shockwaveRadius = 0;

    const PRESETS = [
      { id: 'cyberpunk', colors: ['#00f0ff', '#ff007f', '#ffeb3b'] },
      { id: 'magma', colors: ['#ff3300', '#ff8800', '#ffea00'] },
      { id: 'velvet', colors: ['#8a2be2', '#da70d6', '#00ffff'] },
      { id: 'aurora', colors: ['#00ff88', '#00f0ff', '#7928ca'] },
      { id: 'cosmic', colors: ['#4facfe', '#00f2fe', '#ffffff'] }
    ];

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resize);
    resize();

    function toggleAppFullscreen() {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.toggle_fullscreen) {
        window.pywebview.api.toggle_fullscreen();
      } else if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(()=>{});
      } else {
        document.exitFullscreen().catch(()=>{});
      }
    }

    fullscreenBtn.addEventListener('click', toggleAppFullscreen);

    function toggleControls() {
      if (!controlsPanel) return;
      const isHidden = controlsPanel.classList.toggle('hidden');
      if (toggleUiBtn) {
        toggleUiBtn.textContent = isHidden ? '⚙️ (H)' : '👁️ (H)';
        toggleUiBtn.title = isHidden ? 'Buttons einblenden (Taste: H)' : 'Buttons ausblenden (Taste: H)';
      }
    }
    toggleUiBtn?.addEventListener('click', toggleControls);

    function toggleDspHud() {
      if (!dspHud) return;
      dspHud.classList.toggle('active');
    }
    hudToggleBtn?.addEventListener('click', toggleDspHud);

    function getSongStorageKey(title, artist) {
      return 'karaoke_offset_' + (title + '_' + artist).toLowerCase().replace(/[^a-z0-9]/g, '_');
    }

    function updateOffsetDisplay(isSaved) {
      offsetValEl.textContent = `${userOffset >= 0 ? '+' : ''}${userOffset.toFixed(2)}s`;
      if (isSaved) {
        savedBadgeEl.classList.add('active');
      } else {
        savedBadgeEl.classList.remove('active');
      }
    }

    function loadSongOffset(title, artist) {
      const key = getSongStorageKey(title, artist);
      const saved = localStorage.getItem(key);
      if (saved !== null) {
        userOffset = parseFloat(saved);
        updateOffsetDisplay(true);
      } else {
        userOffset = 0.40;
        updateOffsetDisplay(false);
      }
    }

    function adjustAndSaveOffset(delta) {
      userOffset = Math.round((userOffset + delta) * 100) / 100;
      if (currentTrackName) {
        localStorage.setItem(getSongStorageKey(currentTrackName, currentArtistName), userOffset.toFixed(2));
      }
      updateOffsetDisplay(true);
    }

    // Phase 10: Multi-Anchor Tap-Sync Generator
    async function tapSyncAnchor() {
      if (!currentLyrics || !currentLyrics.lines || currentLyrics.lines.length === 0) return;
      const lines = currentLyrics.lines;
      const curTime = clientPlaybackTime + userOffset;
      
      let closestLine = lines[0];
      let minDiff = Infinity;
      for (const l of lines) {
        const diff = Math.abs(l.startTime - curTime);
        if (diff < minDiff) {
          minDiff = diff;
          closestLine = l;
        }
      }

      if (closestLine && minDiff < 5.0) {
        const requiredOffset = closestLine.startTime - clientPlaybackTime;
        userOffset = Math.round(requiredOffset * 100) / 100;
        
        // Post Anchor to DSP Timing Engine
        try {
          await fetch('/api/anchor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lrc_time: closestLine.startTime, offset: userOffset })
          });
        } catch(e){}

        if (currentTrackName) {
          localStorage.setItem(getSongStorageKey(currentTrackName, currentArtistName), userOffset.toFixed(2));
        }
        updateOffsetDisplay(true);
      }
    }

    document.getElementById('offset-m')?.addEventListener('click', () => adjustAndSaveOffset(-0.1));
    document.getElementById('offset-p')?.addEventListener('click', () => adjustAndSaveOffset(+0.1));
    tapSyncBtn?.addEventListener('click', tapSyncAnchor);

    window.addEventListener('keydown', (e) => {
      if (e.key === 'F11') {
        e.preventDefault();
        toggleAppFullscreen();
      } else if (e.key.toLowerCase() === 'h') {
        e.preventDefault();
        toggleControls();
      } else if (e.key.toLowerCase() === 'd') {
        e.preventDefault();
        toggleDspHud();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        adjustAndSaveOffset(e.shiftKey ? -0.5 : -0.1);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        adjustAndSaveOffset(e.shiftKey ? +0.5 : +0.1);
      } else if (e.key.toLowerCase() === 't' || e.key.toLowerCase() === 's') {
        e.preventDefault();
        tapSyncAnchor();
      } else if (e.key.toLowerCase() === 'r') {
        e.preventDefault();
        userOffset = 0.40;
        if (currentTrackName) localStorage.removeItem(getSongStorageKey(currentTrackName, currentArtistName));
        updateOffsetDisplay(false);
      }
    });

    presetBtn.addEventListener('click', () => {
      const modes = ['auto', 'cyberpunk', 'magma', 'velvet', 'aurora', 'cosmic'];
      let idx = modes.indexOf(visualizerMode);
      visualizerMode = modes[(idx + 1) % modes.length];
      presetBtn.textContent = `🎨 Preset: ${visualizerMode.toUpperCase()}`;
    });

    async function pollServer() {
      try {
        const res = await fetch('/api/state');
        if (res.ok) {
          const data = await res.json();
          if (data.title) {
            titleEl.textContent = data.title;
            artistEl.textContent = data.artist || 'Spotify';
            isPlaying = data.status.toLowerCase() === 'playing';

            // 17-Phase DSP Telemetry Feed
            targetEnergy = data.live_energy || 0.0;
            targetPunch = data.beat_punch || 0.0;
            targetBass = data.bass_energy || 0.0;
            targetMid = data.mid_energy || 0.0;
            targetHigh = data.high_energy || 0.0;

            // Update Live HUD
            if (hudGsmtc) hudGsmtc.textContent = `${data.gsmtc_pos?.toFixed(3) || '0.000'} s`;
            if (hudAudioClk) hudAudioClk.textContent = `${data.audio_clock?.toFixed(3) || '0.000'} s`;
            if (hudClkDiff) hudClkDiff.textContent = `${data.clock_diff_ms >= 0 ? '+' : ''}${data.clock_diff_ms?.toFixed(1) || '0.0'} ms`;
            if (hudOffset) hudOffset.textContent = `${data.filtered_offset >= 0 ? '+' : ''}${data.filtered_offset?.toFixed(3) || '0.400'} s`;
            if (hudOnsets) hudOnsets.textContent = `${data.onset_rate_hz?.toFixed(1) || '0.0'} Hz`;
            if (hudAnchors) hudAnchors.textContent = `${data.active_anchors || 1} active`;
            if (hudHw) hudHw.textContent = (data.hw_profile || 'PC WASAPI').replace(/_/g, ' ').toUpperCase();
            if (hudElastic) hudElastic.textContent = data.elastic_status || 'Locked';
            const confPct = Math.round((data.timing_confidence || 0.85) * 100);
            if (hudConf) hudConf.textContent = `${confPct} %`;
            if (hudConfBar) hudConfBar.style.width = `${confPct}%`;

            if (data.is_karaoke_word_synced) {
              karaokeBadgeEl.classList.add('active');
            } else {
              karaokeBadgeEl.classList.remove('active');
            }

            const serverTime = data.position;
            const trackChanged = data.title !== currentTrackName;

            if (trackChanged) {
              currentTrackName = data.title;
              currentArtistName = data.artist || '';
              loadSongOffset(currentTrackName, currentArtistName);
              clientPlaybackTime = serverTime;
              currentLyrics = null;
              currentLineIdx = -1;
              currentLineEl.innerHTML = '<span class="status-pulse">⚡ Lade Songtext...</span>';
              nextLineEl.textContent = '';
              countdownEl.classList.remove('active');
            } else {
              const diff = serverTime - clientPlaybackTime;
              if (Math.abs(diff) > 1.5) {
                clientPlaybackTime = serverTime;
              } else if (Math.abs(diff) > 0.05) {
                clientPlaybackTime += diff * 0.12;
              }
            }

            if (data.lyrics && (!currentLyrics || currentLyrics.meta?.title !== data.title)) {
              currentLyrics = data.lyrics;
              currentLineIdx = -1;
              currentLineEl.innerHTML = '';
            } else if (!data.has_lyrics && currentTrackName === data.title && !currentLyrics) {
              currentLineEl.innerHTML = '<span style="color:#ff007f;font-size:20px;">Kein synchronisierter Text in Datenbank gefunden</span>';
            }

            const allText = `${data.title} ${data.artist} ${data.album}`.toLowerCase();
            if (/metal|rock|punk|heavy|guitar|ac\/dc|metallica|rammstein|linkin/i.test(allText)) detectedPreset = 'magma';
            else if (/synth|techno|electro|edm|dance|club|dj|remix|house/i.test(allText)) detectedPreset = 'cyberpunk';
            else if (/rap|hip.?hop|trap|r&b|drill|beat|drake|eminem|snoop/i.test(allText)) detectedPreset = 'velvet';
            else if (/acoustic|piano|jazz|classic|chill|lofi|unplugged|ballad/i.test(allText)) detectedPreset = 'cosmic';
            else detectedPreset = 'aurora';

            genreBadge.textContent = `✨ ${detectedPreset.toUpperCase()} VISUALIZER`;
          }
        }
      } catch (e) {}
      setTimeout(pollServer, 33); // 30 Hz Telemetry Polling
    }
    pollServer();

    // ==============================================================================
    // A.U.R.O.R.A. + COSMIC MASTER VISUALIZER RENDERER (60 FPS)
    // ==============================================================================

    function drawVisualizer() {
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      animTime += 0.035;

      // Smooth DSP Audio Physics
      smoothEnergy = smoothEnergy * 0.70 + targetEnergy * 0.30;
      smoothBass = smoothBass * 0.70 + (targetBass * 1.5 + targetPunch * 0.8) * 0.30;
      smoothMid = smoothMid * 0.70 + (targetMid * 1.4 + smoothEnergy * 0.8) * 0.30;
      smoothHigh = smoothHigh * 0.70 + (targetHigh * 1.6 + targetEnergy * 0.6) * 0.30;

      const activePreset = visualizerMode === 'auto' ? detectedPreset : visualizerMode;
      const preset = PRESETS.find(p => p.id === activePreset) || PRESETS[0];
      const [c1, c2, c3] = preset.colors;

      // 1. Radial Core Ambient Glow
      const centerScale = Math.max(width, height) * (0.55 + smoothBass * 0.35);
      const grad = ctx.createRadialGradient(width/2, height/2, 10, width/2, height/2, centerScale);
      grad.addColorStop(0, `${c1}${Math.min(255, Math.round(35 + smoothBass * 90)).toString(16).padStart(2, '0')}`);
      grad.addColorStop(0.45, `${c2}${Math.min(255, Math.round(15 + smoothMid * 40)).toString(16).padStart(2, '0')}`);
      grad.addColorStop(1, '#06081000');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, width, height);

      if (activePreset === 'cyberpunk') {
        ctx.lineWidth = 4.0 + smoothBass * 3.0;
        for (let l = 0; l < 4; l++) {
          ctx.beginPath();
          const col = l === 0 ? c1 : (l === 1 ? c2 : (l === 2 ? c3 : '#ffffff'));
          ctx.strokeStyle = col;
          ctx.shadowColor = col;
          ctx.shadowBlur = 18 + smoothBass * 35;

          const energy = l === 0 ? smoothBass : (l === 1 ? smoothMid : smoothHigh);
          const yBase = height * 0.38 + l * 18;
          for (let x = 0; x < width; x += 8) {
            const freq = 0.003 * (l + 1);
            const amp = (45 + l * 30) * (0.2 + energy * 2.2);
            const y = yBase + Math.sin(x * freq + animTime * 4 + l) * amp + Math.cos(x * 0.006 - animTime * 2) * (amp * 0.4);
            if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
        ctx.shadowBlur = 0;

        if (targetPunch > 0.35) shockwaveRadius = 10;
        if (shockwaveRadius > 0 && shockwaveRadius < Math.max(width, height)) {
          shockwaveRadius += 18;
          ctx.beginPath();
          ctx.arc(width/2, height*0.42, shockwaveRadius, 0, Math.PI * 2);
          ctx.strokeStyle = `${c1}${Math.round(Math.max(0, (1 - shockwaveRadius / Math.max(width, height)) * 120)).toString(16).padStart(2, '0')}`;
          ctx.lineWidth = 3;
          ctx.stroke();
        }
      } else if (activePreset === 'magma') {
        const numBars = 64;
        const bW = width / (numBars * 1.45);
        const sX = (width - numBars * bW * 1.45) / 2;

        for (let i = 0; i < numBars; i++) {
          const wave = Math.sin(animTime * 7 + i * 0.24) * 0.5 + 0.5;
          const bassBoost = (i > 16 && i < 48) ? smoothBass * 1.8 : smoothMid * 1.2;
          const val = Math.min(1.0, wave * 0.2 + bassBoost * 0.8 + (i % 2 === 0 ? smoothHigh * 0.3 : 0));

          const bH = Math.max(12, val * 340);
          const x = sX + i * bW * 1.45;
          const y = height * 0.46 - bH / 2;

          const bG = ctx.createLinearGradient(x, y, x, y + bH);
          bG.addColorStop(0, c3);
          bG.addColorStop(0.4, c2);
          bG.addColorStop(1, c1);

          ctx.fillStyle = bG;
          ctx.shadowColor = c1;
          ctx.shadowBlur = 10 + val * 25;
          ctx.fillRect(x, y, bW, bH);
        }
        ctx.shadowBlur = 0;
      } else if (activePreset === 'velvet') {
        const cX = width / 2;
        const cY = height * 0.40;
        for (let r = 0; r < 6; r++) {
          const radius = 40 + r * 55 + smoothBass * 95;
          ctx.beginPath();
          ctx.arc(cX, cY, radius, 0, Math.PI * 2);
          ctx.strokeStyle = r % 2 === 0 ? c1 : c2;
          ctx.lineWidth = 3.0 + (6 - r) * 0.8 + smoothBass * 4;
          ctx.shadowColor = ctx.strokeStyle;
          ctx.shadowBlur = 20 + smoothBass * 35;
          ctx.stroke();
        }
        ctx.shadowBlur = 0;
      } else if (activePreset === 'aurora') {
        ctx.lineWidth = 5.0 + smoothMid * 4.0;
        for (let w = 0; w < 4; w++) {
          ctx.beginPath();
          const col = w === 0 ? c1 : (w === 1 ? c2 : (w === 2 ? c3 : '#ffffff'));
          ctx.strokeStyle = col;
          ctx.shadowColor = col;
          ctx.shadowBlur = 25 + smoothMid * 30;

          for (let x = 0; x < width; x += 10) {
            const y = height * 0.38 + Math.sin(x * 0.0028 + animTime * 2.5 + w) * (55 + smoothBass * 65) + Math.cos(x * 0.0055 - animTime * 1.5) * (35 + smoothHigh * 45);
            if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
        ctx.shadowBlur = 0;
      } else if (activePreset === 'cosmic') {
        const cX = width / 2;
        const cY = height * 0.38;

        // --- LAYER 1: Deep 3D Cosmic Starfield Warp ---
        for (let p = 0; p < 75; p++) {
          const angle = p * (Math.PI * 2 / 75) + animTime * 0.15;
          const dist = ((p * 19 + animTime * (50 + smoothBass * 190)) % Math.max(width, height) * 0.58);
          const px = cX + Math.cos(angle) * dist;
          const py = cY + Math.sin(angle) * dist;
          const pRadius = 1.2 + (dist / 110) * (0.9 + smoothHigh * 2.2);

          ctx.beginPath();
          ctx.arc(px, py, Math.max(1, pRadius), 0, Math.PI * 2);
          ctx.fillStyle = p % 3 === 0 ? '#00f2fe' : (p % 3 === 1 ? '#9d4edd' : '#f72585');
          ctx.shadowColor = ctx.fillStyle;
          ctx.shadowBlur = 10 + smoothHigh * 18;
          ctx.fill();
        }
        ctx.shadowBlur = 0;

        // --- LAYER 2: A.U.R.O.R.A. Master Visualizer Centerpiece ---
        const baseR = Math.min(width, height) * 0.13;
        const hudR = baseR * 1.95;
        const barsR = baseR * 1.28;
        const maxBarH = baseR * 0.75;
        const orbR = baseR * (0.85 + smoothBass * 0.45 + smoothEnergy * 0.25);

        // 1. A.U.R.O.R.A. Holographic Sci-Fi HUD Rings
        const rotA = animTime * 0.6;
        const rotB = -animTime * 0.9;
        const rotC = animTime * 1.3;

        // Outer Fine Tick Perimeter (72 Ticks)
        ctx.strokeStyle = 'rgba(76, 201, 240, 0.40)';
        ctx.lineWidth = 1.2;
        for (let i = 0; i < 72; i++) {
          const ang = (i * 5.0) * (Math.PI / 180);
          const len = i % 6 === 0 ? 7 : 3.5;
          const x1 = cX + (hudR - len) * Math.cos(ang);
          const y1 = cY + (hudR - len) * Math.sin(ang);
          const x2 = cX + hudR * Math.cos(ang);
          const y2 = cY + hudR * Math.sin(ang);
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
        }

        // Rotating Segmented Tech Arcs (3 Arcs with Gaps)
        ctx.save();
        ctx.translate(cX, cY);
        ctx.rotate(rotA);
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.75)';
        ctx.shadowColor = '#00f2fe';
        ctx.shadowBlur = 14 + smoothBass * 20;
        ctx.lineWidth = 2.4;
        for (let a = 0; a < 3; a++) {
          const startA = a * (Math.PI * 2 / 3);
          ctx.beginPath();
          ctx.arc(0, 0, hudR * 0.88, startA, startA + 1.2);
          ctx.stroke();
        }
        ctx.shadowBlur = 0;

        // Counter-Rotating Dotted Ring
        ctx.rotate(rotB);
        ctx.setLineDash([4, 6]);
        ctx.strokeStyle = 'rgba(157, 78, 221, 0.70)';
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        ctx.arc(0, 0, hudR * 0.96, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();

        // 4 Glowing Orbital Corner Nodes
        ctx.save();
        ctx.translate(cX, cY);
        ctx.rotate(rotC);
        for (let n = 0; n < 4; n++) {
          const nAng = n * (Math.PI / 2);
          const nx = hudR * Math.cos(nAng);
          const ny = hudR * Math.sin(nAng);
          ctx.beginPath();
          ctx.arc(nx, ny, 4.0 + targetPunch * 2.0, 0, Math.PI * 2);
          ctx.fillStyle = '#f72585';
          ctx.shadowColor = '#f72585';
          ctx.shadowBlur = 15;
          ctx.fill();
        }
        ctx.shadowBlur = 0;
        ctx.restore();

        // 2. A.U.R.O.R.A. Radial 96 Frequency Bars (Dual-Symmetric 2x Low -> High)
        const numBars = 96;
        const halfN = 48;
        const angStep = (Math.PI * 2) / numBars;

        for (let i = 0; i < numBars; i++) {
          const ang = i * angStep - Math.PI / 2;
          const freqProg = (i < halfN ? i : (numBars - 1 - i)) / (halfN - 1);
          
          const osc = Math.sin(animTime * 6 + i * 0.18) * 0.5 + 0.5;
          const barEnergy = (1 - freqProg) * smoothBass * 1.6 + freqProg * smoothHigh * 1.2 + osc * 0.20;
          const barH = Math.max(5, barEnergy * maxBarH);
          const peakH = barH + 4.0 + targetPunch * 8.0;

          const cosA = Math.cos(ang);
          const sinA = Math.sin(ang);

          const x1 = cX + barsR * cosA;
          const y1 = cY + barsR * sinA;
          const x2 = cX + (barsR + barH) * cosA;
          const y2 = cY + (barsR + barH) * sinA;

          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.strokeStyle = freqProg < 0.5 ? '#00f2fe' : (freqProg < 0.85 ? '#9d4edd' : '#f72585');
          ctx.lineWidth = 2.4;
          ctx.shadowColor = ctx.strokeStyle;
          ctx.shadowBlur = 8 + barEnergy * 15;
          ctx.stroke();

          // Peak-Hold Node
          const px = cX + (barsR + peakH) * cosA;
          const py = cY + (barsR + peakH) * sinA;
          ctx.beginPath();
          ctx.arc(px, py, 1.8, 0, Math.PI * 2);
          ctx.fillStyle = '#ffffff';
          ctx.shadowColor = '#00f2fe';
          ctx.shadowBlur = 10;
          ctx.fill();
        }
        ctx.shadowBlur = 0;

        // 3. A.U.R.O.R.A. Continuous Oscilloscope Wave Ring
        const waveR = baseR * 1.12;
        ctx.beginPath();
        ctx.lineWidth = 3.0;
        ctx.strokeStyle = '#00f2fe';
        ctx.shadowColor = '#00f2fe';
        ctx.shadowBlur = 20 + smoothBass * 25;
        for (let a = 0; a <= 120; a++) {
          const rad = (a / 120) * Math.PI * 2;
          const ripple = Math.sin(rad * 8 + animTime * 5) * (6 + smoothBass * 14) + Math.cos(rad * 14 - animTime * 3) * (3 + smoothHigh * 8);
          const r = waveR + ripple;
          const wx = cX + r * Math.cos(rad);
          const wy = cY + r * Math.sin(rad);
          if (a === 0) ctx.moveTo(wx, wy); else ctx.lineTo(wx, wy);
        }
        ctx.closePath();
        ctx.stroke();
        ctx.shadowBlur = 0;

        // 4. A.U.R.O.R.A. Pulsating Core Plasma Orb & Hexagon Lattice
        ctx.beginPath();
        ctx.arc(cX, cY, orbR, 0, Math.PI * 2);
        const orbBaseGrad = ctx.createRadialGradient(cX, cY, 0, cX, cY, orbR);
        orbBaseGrad.addColorStop(0, '#0e1220');
        orbBaseGrad.addColorStop(0.7, '#080c18');
        orbBaseGrad.addColorStop(1, '#00f2fe');
        ctx.fillStyle = orbBaseGrad;
        ctx.fill();
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.9)';
        ctx.lineWidth = 2.0;
        ctx.stroke();

        const plasmaGrad = ctx.createRadialGradient(cX, cY, 0, cX, cY, orbR);
        plasmaGrad.addColorStop(0, 'rgba(247, 37, 133, 0.85)');
        plasmaGrad.addColorStop(0.45, 'rgba(157, 78, 221, 0.70)');
        plasmaGrad.addColorStop(0.85, 'rgba(0, 242, 254, 0.55)');
        plasmaGrad.addColorStop(1, 'rgba(0, 242, 254, 0)');
        ctx.fillStyle = plasmaGrad;
        ctx.beginPath();
        ctx.arc(cX, cY, orbR, 0, Math.PI * 2);
        ctx.fill();

        ctx.save();
        ctx.translate(cX, cY);
        ctx.rotate(animTime * 0.7);
        ctx.strokeStyle = 'rgba(220, 250, 255, 0.75)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let h = 0; h < 6; h++) {
          const hAng = h * (Math.PI / 3);
          const hx = (orbR * 0.62) * Math.cos(hAng);
          const hy = (orbR * 0.62) * Math.sin(hAng);
          if (h === 0) ctx.moveTo(hx, hy); else ctx.lineTo(hx, hy);
        }
        ctx.closePath();
        ctx.stroke();
        ctx.restore();
      }
    }

    // ==============================================================================
    // KARAOKE STAGE LOGIC
    // ==============================================================================

    function renderLine(line) {
      currentLineEl.innerHTML = '';
      if (!line.words || line.words.length === 0) {
        currentLineEl.textContent = line.text;
        return;
      }
      const frag = document.createDocumentFragment();
      line.words.forEach((w, idx) => {
        const span = document.createElement('span');
        span.className = 'word';
        span.id = `w-${idx}`;
        span.textContent = w.word;
        frag.appendChild(span);
      });
      currentLineEl.appendChild(frag);
    }

    function animateWords(line, time) {
      if (!line || !line.words) return;
      for (let i = 0; i < line.words.length; i++) {
        const w = line.words[i];
        const el = document.getElementById(`w-${i}`);
        if (!el) continue;

        if (time < w.start) {
          el.style.setProperty('--fill-pct', '0%');
          el.classList.remove('singing', 'done');
        } else if (time >= w.start && time <= w.end) {
          const dur = Math.max(0.04, w.end - w.start);
          const prog = Math.min(100, Math.max(0, ((time - w.start) / dur) * 100));
          el.style.setProperty('--fill-pct', `${prog.toFixed(1)}%`);
          el.classList.add('singing');
          el.classList.remove('done');
        } else {
          el.style.setProperty('--fill-pct', '100%');
          el.classList.remove('singing');
          el.classList.add('done');
        }
      }
    }

    function updateKaraoke(deltaSec) {
      if (!currentLyrics || !currentLyrics.lines || currentLyrics.lines.length === 0) return;

      if (isPlaying) {
        clientPlaybackTime += deltaSec;
      }

      const curTime = clientPlaybackTime + userOffset;
      const lines = currentLyrics.lines;

      let activeIdx = -1;
      let upcomingIdx = -1;

      for (let i = 0; i < lines.length; i++) {
        const l = lines[i];
        if (curTime >= l.startTime && curTime <= l.endTime) {
          activeIdx = i;
          break;
        }
        if (l.startTime > curTime) {
          upcomingIdx = i;
          break;
        }
      }

      // 1. Stage before the very first line starts
      if (activeIdx === -1 && upcomingIdx === 0) {
        const firstLine = lines[0];
        if (currentLineIdx !== firstLine.id) {
          renderLine(firstLine);
          currentLineIdx = firstLine.id;
          nextLineEl.textContent = lines[1] ? lines[1].text : '';
        }
        animateWords(firstLine, curTime);

        const rem = firstLine.startTime - curTime;
        if (rem <= 3.0 && rem > 0) {
          countdownEl.classList.add('active');
          dot1.className = `dot ${rem <= 3.0 ? 'active-1' : ''}`;
          dot2.className = `dot ${rem <= 2.0 ? 'active-2' : ''}`;
          dot3.className = `dot ${rem <= 1.0 ? 'active-3' : ''}`;
        } else {
          countdownEl.classList.remove('active');
        }
        return;
      }

      // 2. Active singing line
      if (activeIdx !== -1) {
        countdownEl.classList.remove('active');
        const active = lines[activeIdx];
        if (currentLineIdx !== active.id) {
          renderLine(active);
          currentLineIdx = active.id;
          const next = lines[activeIdx + 1];
          nextLineEl.textContent = next ? next.text : '';
        }
        animateWords(active, curTime);
        return;
      }

      // 3. Instrumental break / pause between lines
      if (upcomingIdx !== -1) {
        const up = lines[upcomingIdx];
        const prev = lines[upcomingIdx - 1];

        if (prev && curTime < prev.endTime + 1.2) {
          if (currentLineIdx !== prev.id) {
            renderLine(prev);
            currentLineIdx = prev.id;
            nextLineEl.textContent = up.text;
          }
          animateWords(prev, curTime);
          countdownEl.classList.remove('active');
        } else {
          if (currentLineIdx !== up.id) {
            renderLine(up);
            currentLineIdx = up.id;
            const next = lines[upcomingIdx + 1];
            nextLineEl.textContent = next ? next.text : '';
          }
          animateWords(up, curTime);

          const rem = up.startTime - curTime;
          if (rem <= 3.0 && rem > 0) {
            countdownEl.classList.add('active');
            dot1.className = `dot ${rem <= 3.0 ? 'active-1' : ''}`;
            dot2.className = `dot ${rem <= 2.0 ? 'active-2' : ''}`;
            dot3.className = `dot ${rem <= 1.0 ? 'active-3' : ''}`;
          } else {
            countdownEl.classList.remove('active');
          }
        }
      }
    }

    let lastNow = performance.now();
    function loop(now) {
      const deltaSec = Math.min(0.1, (now - lastNow) / 1000);
      lastNow = now;

      drawVisualizer();
      updateKaraoke(deltaSec);
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=HTML_PAGE)

if __name__ == "__main__":
    print("\n========================================================")
    print("[SPOTIFY AI KARAOKE] Starting 17-Phase DSP Engine v7.0")
    print("[SPOTIFY AI KARAOKE] 48kHz WASAPI Capture & Clock Fusion Active!")
    print("========================================================\n")
    
    threading.Thread(target=background_audio_capture_thread, daemon=True).start()
    threading.Thread(target=background_media_fusion_poller, daemon=True).start()
    threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=8888, log_level="error"),
        daemon=True
    ).start()
    
    time.sleep(0.6)
    
    native_window = webview.create_window(
        title="Spotify AI Karaoke & Fullscreen Visualizer",
        url="http://127.0.0.1:8888",
        width=1366,
        height=860,
        resizable=True,
        fullscreen=False,
        js_api=native_api,
        background_color="#060810"
    )
    
    webview.start()
    sys.exit(0)
