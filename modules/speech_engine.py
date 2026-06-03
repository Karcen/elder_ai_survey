# -*- coding: utf-8 -*-
"""
speech_engine.py · 语音播报与识别

设计目标：**任何依赖缺失都能优雅降级**，绝不阻断老人答题。

播报 TTS：
    离线 pyttsx3（首选）；缺失则降级为「静默 + 文字提示」。
识别 ASR：
    离线 vosk + SpeechRecognition；缺失则识别功能不可用（返回 None）。
    联网模式下可由 ai_engine 走 Whisper（此处保留接口）。

所有播报在后台线程进行，不阻塞 GUI 主线程。
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("speech_engine")

BASE_DIR = Path(__file__).resolve().parent.parent


class SpeechEngine:
    """语音引擎：封装 TTS 播报与（可选）ASR 识别，缺依赖自动降级。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        sp = self.config.get("speech", {})
        self.enabled: bool = sp.get("enabled", True)
        self.rate: int = int(sp.get("tts_rate", 150))
        self.volume: float = float(sp.get("tts_volume", 1.0))
        self.vosk_model_path = BASE_DIR / sp.get("vosk_model_path", "models/vosk-model-small-cn")

        self._tts_lock = threading.Lock()
        self._speaking = threading.Event()
        self.tts_available = self._probe_tts()
        self.asr_available = self._probe_asr()

        log.info("语音引擎初始化：TTS=%s ASR=%s",
                 "可用" if self.tts_available else "降级(静默)",
                 "可用" if self.asr_available else "不可用")

    # ---------------- 能力探测 ----------------
    def _probe_tts(self) -> bool:
        if not self.enabled:
            return False
        try:
            import pyttsx3  # noqa: F401
            return True
        except Exception as exc:  # noqa: BLE001  任何导入/驱动问题都降级
            log.warning("pyttsx3 不可用，语音播报降级为静默：%s", exc)
            return False

    def _probe_asr(self) -> bool:
        if not self.enabled:
            return False
        try:
            import vosk  # noqa: F401
            import speech_recognition  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            log.info("vosk/SpeechRecognition 不可用，语音识别关闭：%s", exc)
            return False
        if not self.vosk_model_path.exists():
            log.info("未找到 vosk 模型：%s，语音识别关闭。", self.vosk_model_path)
            return False
        return True

    # ---------------- TTS 播报 ----------------
    def speak(self, text: str, on_done: Optional[Callable[[], None]] = None,
              block: bool = False) -> None:
        """朗读文本。默认后台线程异步播报，不阻塞界面。

        Args:
            text: 要朗读的文字
            on_done: 播报结束回调（在工作线程中调用）
            block: 是否同步阻塞直到播报完成（主要用于测试）
        """
        if not text:
            if on_done:
                on_done()
            return
        if not self.tts_available:
            log.debug("[静默播报] %s", text)
            if on_done:
                on_done()
            return

        def _run() -> None:
            with self._tts_lock:
                self._speaking.set()
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", self.rate)
                    engine.setProperty("volume", self.volume)
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
                except Exception as exc:  # noqa: BLE001
                    log.warning("TTS 播报失败（降级静默）：%s", exc)
                finally:
                    self._speaking.clear()
                    if on_done:
                        on_done()

        if block:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> None:
        """尽力停止当前播报（pyttsx3 在多线程下能力有限）。"""
        try:
            if self.tts_available:
                import pyttsx3
                pyttsx3.init().stop()
        except Exception:  # noqa: BLE001
            pass

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    # ---------------- ASR 识别（可选） ----------------
    def listen(self, timeout: int = 5) -> Optional[str]:
        """离线识别一段语音，返回文本；不可用或失败返回 None。"""
        if not self.asr_available:
            log.info("语音识别不可用。")
            return None
        try:
            import json
            import queue
            import sounddevice as sd  # 可能未安装
            import vosk

            model = vosk.Model(str(self.vosk_model_path))
            q: "queue.Queue" = queue.Queue()

            def _cb(indata, frames, time_, status):  # noqa: ANN001
                q.put(bytes(indata))

            rec = vosk.KaldiRecognizer(model, 16000)
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype="int16",
                                   channels=1, callback=_cb):
                import time as _t
                start = _t.time()
                while _t.time() - start < timeout:
                    data = q.get()
                    if rec.AcceptWaveform(data):
                        text = json.loads(rec.Result()).get("text", "")
                        if text:
                            return text.replace(" ", "")
            return json.loads(rec.FinalResult()).get("text", "").replace(" ", "") or None
        except Exception as exc:  # noqa: BLE001
            log.warning("语音识别失败：%s", exc)
            return None


# 便捷单例
_default_engine: Optional[SpeechEngine] = None


def get_engine(config: Optional[Dict[str, Any]] = None) -> SpeechEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = SpeechEngine(config)
    return _default_engine
