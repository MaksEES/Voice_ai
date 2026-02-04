import sys

print(f"Python version: {sys.version}")

modules = ['webview', 'psutil', 'pyttsx3', 'speech_recognition', 'pyaudio', 'google.generativeai', 'google.genai']

for m in modules:
    try:
        if '.' in m:
            __import__(m)
        else:
            __import__(m)
        print(f"[OK] {m}")
    except ImportError:
        print(f"[MISSING] {m}")
    except Exception as e:
        print(f"[ERROR] {m}: {e}")
