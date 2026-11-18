# Open Interview Assistant

A Windows 10/11 desktop interview practice assistant. Type a question, snip it from a screen, or listen through the default microphone or PC playback device. Suggested answers appear as the local model generates them.

## Windows setup

1. Install 64-bit Python 3.11 from https://www.python.org/downloads/ with the Windows py launcher enabled.
2. Install and start Ollama from https://ollama.com/download/windows.
3. In PowerShell run `ollama pull gemma3:4b`. This downloads the image and text model. Allow several GB of disk space for the models.
4. Extract the entire ZIP and double-click Start.cmd. The launcher installs Python dependencies in the project folder. The first voice question also downloads the multilingual Whisper small model. Internet access is required for initial setup.

## Use

- **Typed:** enter a question and choose Answer text.
- **Screen:** use Win+Shift+S and drag over one question. Choose Read clipboard snip. The answer includes the model's transcription so you can check it. Crop closely for small print.
- **Voice:** choose PC audio for the default playback device (including headphones), or Microphone for speech in the room. Click Listen, then Stop and answer after the question. Capture stops automatically after one minute. PC audio includes all sound from the default output. Use this during practice or where participants allow assistance and capture.
- **Languages:** leave the reply field blank to match the question, or enter a language name such as Bengali, Hindi or English. Speech detection uses multilingual Whisper. Screen reading and responses use Gemma 3. Coverage differs across the models. Mixed speech, rare scripts and short clips can produce errors.
- **Screen sharing:** share only the interview window in your meeting app when you want a separate private workspace. Full-display sharing can show the assistant. It runs as an ordinary Python desktop application.
- **Performance:** the first response includes model loading time. Short questions and a warmed-up model reduce waiting. Local CPU inference can be slow. For model connection errors, start Ollama and verify the model appears in `ollama list`.

Audio stays in memory. Screen snips use the Windows clipboard and its configured history. Model input goes to Ollama on localhost. Close the app to discard the current session. The MIT license covers this application. Dependencies and model weights carry their respective licenses.

## Interview and CV

Enter the role, company and round. Add a text-based PDF, DOCX or UTF-8 TXT CV.
In Interview setup, paste the job description. Each turn ranks lines from the full CV by word overlap with the question, role and job description and supplies up to five excerpts. Use CV evidence to inspect the exact cited excerpts. Verify that the model interpreted them correctly. Remove CV clears the
selection. The role and CV are held in memory for this session.

## Text and voice models

Standard uses the original Gemma 4B installation. For a balance of speed and
detail, install `ollama pull qwen3:4b-instruct-2507-q4_K_M` and select Balanced.
For the smallest option install `ollama pull gemma3:1b` and select Fast.
Selecting a model starts a background warm-up. Screen questions use Gemma 4B.
Compare the second run of the same question in each mode on your own PC.

## Automatic screen reading

Place the practice questions on the primary display. Click **Auto-read screen**
and drag around the question and choices on the preview. Keep the assistant and
other windows outside that rectangle. After the content settles for two samples,
the assistant submits the visible crop to the local vision model. It processes
one answer at a time and checks the latest visible content when ready again.
Choose **Stop auto-read** to stop new captures. A submitted answer can finish.

## Practice controls

- **Start auto-listen** listens through the selected device, detects speech and submits after the selected pause (0.7, 1.2 or 2 seconds). Listening resumes after the answer finishes. Stop auto-listen ends the loop. A submitted request may finish. Background noise and very quiet speech can affect detection.
- **Follow-ups** use the last four completed turns locally. New interview clears the conversation and exits mock mode while retaining the setup.
- **Timings** show end-to-first-text, capture-end to transcript for voice, model-request to first text, and Ollama's reported model load. Model load is part of model latency; do not add these numbers together.
- **Mock / next question** starts a practice round. Type your reply or record it with Listen, get feedback, then choose Mock / next question for a follow-up.
- **Answer (s)** targets 15, 30 or 60 seconds of spoken content. Choose Simple English, Hindi, Bengali or Hinglish, enter another language, or leave blank to match the question.
