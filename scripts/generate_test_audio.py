from __future__ import annotations

import argparse
import asyncio
import base64
from pathlib import Path
import sys
import wave

import edge_tts
import imageio_ffmpeg
import numpy as np
from pydub import AudioSegment
import requests
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import load_config


SPEECH_URL = "https://api.openai.com/v1/audio/speech"


CASES = {
    "short": "呃，我們下週一，啊不對，下週三要開會，請 TPE 團隊同步 BIOS 狀態。",
    "medium": "那個，我今天想先確認三件事。第一，Firmware 的 NPI 進度要更新；第二，QA 要在週五前回報；第三，我們下週一，啊不對，下週三要跟 BJ 團隊開會。",
    "long": "呃，這段是 SpeedyType 的長句測試。我們原本打算下週一發 BIOS 測試版，啊不對，應該是下週三發 Firmware 測試版。請 TPE 團隊先確認 USB 和 Thunderbolt 的相容性，然後 QA 在 NPI 會議前整理 API 測試結果，最後 BJ 團隊協助確認使用者回饋。",
}


def write_16k_mono_wav(source_wav: Path, target_wav: Path) -> float:
    audio, sample_rate = sf.read(source_wav, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    target_rate = 16000
    if sample_rate != target_rate:
        old_x = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
        new_len = int(round(len(mono) * target_rate / sample_rate))
        new_x = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
        mono = np.interp(new_x, old_x, mono).astype("float32")
    sf.write(target_wav, mono, target_rate, subtype="PCM_16")
    with wave.open(str(target_wav), "rb") as wav_file:
        return wav_file.getnframes() / float(wav_file.getframerate())


async def synthesize_edge_tts(text: str, output_mp3: Path) -> None:
    communicate = edge_tts.Communicate(
        text,
        voice="zh-TW-HsiaoChenNeural",
        rate="-5%",
    )
    await communicate.save(str(output_mp3))


def convert_mp3_to_wav(source_mp3: Path, target_wav: Path) -> None:
    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    audio = AudioSegment.from_file(source_mp3, format="mp3")
    audio.export(target_wav, format="wav")


def write_pcm_wav(filename: Path, pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> None:
    with wave.open(str(filename), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(rate)
        wav_file.writeframes(pcm)


def synthesize_gemini_tts(text: str, target_wav: Path, api_key: str) -> None:
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": f"Say clearly in Mandarin Chinese at a natural dictation pace: {text}"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": "Kore",
                        }
                    }
                },
            },
            "model": "gemini-3.1-flash-tts-preview",
        },
        timeout=120,
    )
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Gemini TTS API error status={response.status_code}, body:\n{response.text}")
    payload = response.json()
    try:
        encoded = payload["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Gemini TTS response format unexpected:\n{payload}") from exc
    write_pcm_wav(target_wav, base64.b64decode(encoded))


def synthesize_minimax_tts(text: str, target_wav: Path, api_key: str) -> None:
    response = requests.post(
        "https://api.minimax.io/v1/t2a_v2",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "speech-2.8-turbo",
            "text": text,
            "stream": False,
            "language_boost": "Chinese",
            "output_format": "hex",
            "voice_setting": {"voice_id": "Chinese (Mandarin)_Reliable_Executive"},
        },
        timeout=120,
    )
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"MiniMax TTS API error status={response.status_code}, body:\n{response.text}")
    payload = response.json()
    if payload.get("base_resp", {}).get("status_code") != 0:
        raise RuntimeError(f"MiniMax TTS API returned non-zero status:\n{payload}")
    hex_audio = payload["data"]["audio"]
    target_wav.write_bytes(bytes.fromhex(hex_audio))


def synthesize_case(name: str, text: str, output_dir: Path, openai_api_key: str, gemini_api_key: str, minimax_api_key: str) -> tuple[Path, float, str]:
    raw_path = output_dir / f"{name}_raw.wav"
    edge_mp3_path = output_dir / f"{name}_edge.mp3"
    final_path = output_dir / f"{name}_16k.wav"
    response = requests.post(
        SPEECH_URL,
        headers={"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini-tts",
            "voice": "coral",
            "input": text,
            "instructions": "Speak clearly in Mandarin Chinese at a natural dictation pace.",
            "response_format": "wav",
        },
        timeout=120,
    )
    source = "openai-gpt-4o-mini-tts"
    if 200 <= response.status_code < 300:
        raw_path.write_bytes(response.content)
    else:
        print(f"OpenAI TTS failed status={response.status_code}; falling back to Gemini TTS. Body:\n{response.text}")
        try:
            synthesize_gemini_tts(text, raw_path, gemini_api_key)
            source = "gemini-3.1-flash-tts-preview"
        except Exception as gemini_exc:
            print(f"Gemini TTS failed; falling back to MiniMax TTS. Error:\n{gemini_exc}")
            try:
                synthesize_minimax_tts(text, raw_path, minimax_api_key)
                source = "minimax-speech-2.8-turbo"
            except Exception as minimax_exc:
                print(f"MiniMax TTS failed; falling back to Edge TTS. Error:\n{minimax_exc}")
                asyncio.run(synthesize_edge_tts(text, edge_mp3_path))
                convert_mp3_to_wav(edge_mp3_path, raw_path)
                source = "edge-tts-zh-TW-HsiaoChenNeural"
    duration = write_16k_mono_wav(raw_path, final_path)
    return final_path, duration, source


def synthesize_minimax_variant(name: str, text: str, output_dir: Path, minimax_api_key: str) -> tuple[Path, float, str]:
    raw_path = output_dir / f"{name}_minimax_raw.wav"
    final_path = output_dir / f"{name}_minimax_16k.wav"
    synthesize_minimax_tts(text, raw_path, minimax_api_key)
    duration = write_16k_mono_wav(raw_path, final_path)
    return final_path, duration, "minimax-speech-2.8-turbo"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--output-dir", default="test_audio")
    args = parser.parse_args()

    config = load_config(args.env)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in CASES.items():
        path, duration, source = synthesize_case(name, text, output_dir, config.openai_api_key, config.gemini_api_key, config.minimax_api_key)
        print(f"{name}: {path} duration={duration:.3f}s source={source} text={text}")
        if config.minimax_api_key:
            mm_path, mm_duration, mm_source = synthesize_minimax_variant(name, text, output_dir, config.minimax_api_key)
            print(f"{name}: {mm_path} duration={mm_duration:.3f}s source={mm_source} text={text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
