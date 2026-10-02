"""Suite-wide test configuration."""
import os

# Never load the real TTS stack inside pytest. InboundRouter._speak would pull
# sherpa-onnx/onnxruntime into the test process, and that DLL combination
# crashed the interpreter (Windows access violation) partway through the full
# run. Voice behaviour itself is covered by mocked tests in test_voice_*.
os.environ.setdefault("GENESIS_COMPANION_MUTE", "1")
