import pyttsx3
import os
import time
from openwakeword.custom_verifier_model import train_custom_verifier

def generate():
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    for voice in voices:
        if "russian" in voice.name.lower() or "ru" in voice.name.lower():
            engine.setProperty('voice', voice.id)
            break

    positive_clips = []
    
    # Сгенерируем 5 аудиофайлов со словом "Макс" с разной скоростью речи для разнообразия
    for i in range(5):
        engine.setProperty('rate', 130 + i * 10)
        filename = f"maks_pos_{i}.wav"
        engine.save_to_file("макс", filename)
        positive_clips.append(filename)
        
    engine.runAndWait()
    
    # Дадим файловый системе время сохранить файлы
    time.sleep(1)

    print("Training openWakeWord model for 'Max'...")
    try:
        train_custom_verifier(positive_clips, None, "maks.onnx", "alexa")
        print("Success! Model maks.onnx created.")
    except Exception as e:
        print(f"Error during training: {e}")
        
    for f in positive_clips:
        if os.path.exists(f):
            os.remove(f)

if __name__ == "__main__":
    generate()
