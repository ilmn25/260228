"""Speech‑to‑text CLI integration using Whisper.

This module provides automatic voice streaming with continuous speech detection.
When activated, it automatically:
- Listens to your microphone continuously
- Detects when you start speaking (voice activity detection)
- Records until you stop speaking (1.5s silence)
- Auto-transcribes and sends to the agent
- Returns to listening for your next speech

The listener runs continuously from ``main.py`` and only forwards
transcriptions while runtime speech input is enabled. Initial state can be
set with ``ENABLE_SPEECH_ON_START``.
"""

from __future__ import annotations
import asyncio
import os
import tempfile
import wave
import numpy as np
from typing import Awaitable, Callable

from bridge import AgentBridge
from skills.runtime_state import get_speech_enabled


def detect_speech_in_audio(audio_data: bytes, threshold: float = 500.0) -> bool:
    """Detect if audio contains speech using energy-based VAD.
    
    Args:
        audio_data: Raw audio bytes (16-bit PCM)
        threshold: Energy threshold for speech detection
        
    Returns:
        True if speech is detected, False otherwise
    """
    # Convert bytes to numpy array
    audio_array = np.frombuffer(audio_data, dtype=np.int16)
    
    # Calculate RMS energy
    energy = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
    
    return energy > threshold


async def stream_from_microphone(
    bridge: AgentBridge,
    model,
    send: Callable[[str], Awaitable[None]],
    sample_rate: int = 16000,
    chunk_duration: float = 0.5,
    silence_duration: float = 1.5,
    energy_threshold: float = 500.0
) -> None:
    """Stream audio from microphone with automatic speech detection.
    
    Continuously listens to microphone, detects speech, and transcribes automatically.
    
    Args:
        bridge: AgentBridge instance for sending transcriptions
        model: Loaded Whisper model
        sample_rate: Audio sample rate in Hz
        chunk_duration: Duration of each audio chunk in seconds
        silence_duration: Duration of silence before stopping recording
        energy_threshold: Energy threshold for speech detection
    """
    try:
        import pyaudio
    except ImportError:
        raise RuntimeError(
            "PyAudio required for microphone streaming.\n"
            "Install: pip install pyaudio"
        )
    
    CHUNK = int(sample_rate * chunk_duration)
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    
    p = pyaudio.PyAudio()
    
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=sample_rate,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print("\n🎧 Stream mode active - listening for speech...")
    print("   Speak naturally, pauses will auto-trigger transcription when enabled")
    print("   Press Ctrl+C to stop streaming\n")
    
    recording = False
    frames = []
    silence_chunks = 0
    max_silence_chunks = int(silence_duration / chunk_duration)
    last_enabled_state: bool | None = None
    
    try:
        while True:
            speech_enabled = get_speech_enabled(default_enabled=False)
            if speech_enabled != last_enabled_state:
                status = "enabled" if speech_enabled else "disabled"
                print(f"🔈 Speech input {status}")
                if not speech_enabled:
                    recording = False
                    frames = []
                    silence_chunks = 0
                last_enabled_state = speech_enabled

            data = await asyncio.to_thread(
                lambda: stream.read(CHUNK, exception_on_overflow=False)
            )

            if not speech_enabled:
                continue
            
            # Detect if current chunk contains speech
            has_speech = detect_speech_in_audio(data, energy_threshold)
            
            if has_speech:
                if not recording:
                    print("🎤 Speech detected, recording...")
                    recording = True
                    frames = []
                
                frames.append(data)
                silence_chunks = 0
            elif recording:
                frames.append(data)
                silence_chunks += 1
                
                # If silence detected for long enough, process the recording
                if silence_chunks >= max_silence_chunks:
                    print("⏹️  Silence detected, transcribing...")
                    recording = False
                    silence_chunks = 0
                    
                    # Save and transcribe
                    if frames:
                        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                        temp_path = temp_file.name
                        temp_file.close()
                        
                        wf = wave.open(temp_path, 'wb')
                        wf.setnchannels(CHANNELS)
                        wf.setsampwidth(p.get_sample_size(FORMAT))
                        wf.setframerate(sample_rate)
                        wf.writeframes(b''.join(frames))
                        wf.close()
                        
                        try:
                            result = await asyncio.to_thread(model.transcribe, temp_path)
                            transcription = result.get("text", "").strip()
                            
                            if transcription:
                                print(f"📝 Transcribed: {transcription}\n")
                                await bridge.process_prompt(transcription, send)
                            else:
                                print("   (no speech detected)\n")
                        except FileNotFoundError as err:
                            print(f"❌ Error: ffmpeg not found!")
                            print("   Install ffmpeg to use speech transcription.")
                            print("   Run: winget install ffmpeg\n")
                        except Exception as err:
                            print(f"❌ Error transcribing: {err}\n")
                        finally:
                            try:
                                os.unlink(temp_path)
                            except:
                                pass
                        
                        frames = []
                        print("🎧 Listening...")
    
    except KeyboardInterrupt:
        print("\n⏹️  Streaming stopped")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


async def run_speech_cli(bridge: AgentBridge | None = None) -> None:
    """Automatically start continuous voice streaming mode.

    ``bridge`` may be provided when running alongside another integration;
    otherwise a fresh bridge is created. The function continuously listens
    for speech and auto-transcribes until interrupted with Ctrl+C.
    """
    try:
        import whisper
        if not hasattr(whisper, "load_model"):
            raise ImportError("wrong whisper package installed")
    except Exception as exc:
        raise RuntimeError(
            "OpenAI whisper required for speech mode.\n"
            "Install: pip install openai-whisper\n"
            f"Error: {exc}"
        )

    # Check for ffmpeg
    import shutil
    if not shutil.which("ffmpeg"):
        print("\n⚠️  WARNING: ffmpeg not found!")
        print("Whisper requires ffmpeg to process audio files.")
        print("\nInstall ffmpeg:")
        print("  1. Download from: https://ffmpeg.org/download.html")
        print("  2. Or use: winget install ffmpeg")
        print("  3. Or use: choco install ffmpeg")
        print("\nAfter installing, restart your terminal.\n")

    print("Loading Whisper model...")
    model = whisper.load_model("base")

    if bridge is None:
        from prompts.system import SPEECH_INPUT_PROMPT
        bridge = AgentBridge(extra_system_prompt=SPEECH_INPUT_PROMPT)

    await bridge.start()

    async def _cli_send(message: str) -> None:  # noqa: D401
        print(message)

    # Automatically start streaming mode
    try:
        await stream_from_microphone(bridge, model, _cli_send)
    except Exception as err:
        print(f"Error in streaming mode: {err}")
        print("Tip: Install pyaudio with: pip install pyaudio")

    await bridge.close()
