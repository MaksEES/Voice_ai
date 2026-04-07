# AI ChatBot

A chatbot application that uses the Google Gemini API for natural language processing.

## Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/MaksEES/Voice_ai.git
    cd Voice_ai
    ```

2.  **Install Dependencies:**
    ```bash
    pip install pywebview google-genai psutil python-dotenv pyttsx3 speechrecognition pyaudio faster-whisper
    ```

3.  **Environment Variables:**
    Create a `.env` file in the root directory and add your Google Gemini and ElevenLabs API key:
    ```env
    API_KEY="your_api_key_here"
    Voice_API_KEY="your_elevenlabs_api_key_here"
    ```

5.  **Run the application:**
    ```bash
    python backend/app.py
    ```