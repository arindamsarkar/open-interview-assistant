"""Open Interview Assistant for Windows. All inference runs locally."""
import base64
import io
import json
import queue
import threading
from time import monotonic
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from profile_data import read_cv
from screen_watch import ScreenWatch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from PIL import Image, ImageGrab
import numpy as np
import soundcard as sc
from faster_whisper import WhisperModel

events = queue.Queue()
stop = threading.Event()
recognizer = None
speech_loader = ThreadPoolExecutor(max_workers=1)
cv_text = ""


def load_speech():
    global recognizer
    if recognizer is None:
        recognizer = WhisperModel("small", device="cpu", compute_type="int8")
    return recognizer


def select_cv():
    global cv_text
    filename = filedialog.askopenfilename(filetypes=[("CV documents", "*.pdf *.docx *.txt")])
    if not filename:
        return
    try:
        extracted = read_cv(filename)
    except Exception as exc:
        messagebox.showerror("Could not read CV", str(exc))
        return
    cv_text = extracted
    cv_label.set(Path(filename).name + (" (first 6,000 characters used)" if len(extracted) > 6000 else ""))


def remove_cv():
    global cv_text
    cv_text = ""
    cv_label.set("No CV selected")


def listen(source):
    global recognizer
    device = (sc.get_microphone(sc.default_speaker().id, include_loopback=True)
              if source == "PC audio" else sc.default_microphone())
    if device is None:
        raise ValueError("Select a default audio device in Windows Settings.")
    model_future = speech_loader.submit(load_speech)
    blocks = []
    with device.recorder(samplerate=48000) as recorder:
        events.put(("status", "Listening — press Stop and answer when the question ends."))
        for _ in range(600):
            if stop.is_set():
                break
            blocks.append(recorder.record(numframes=4800).mean(axis=1))
    events.put(("timing", monotonic()))
    if not blocks:
        raise ValueError("Recording stopped before audio arrived.")
    from scipy.signal import resample_poly
    samples = resample_poly(np.concatenate(blocks), 1, 3).astype(np.float32)
    events.put(("status", "Transcribing — first use downloads the multilingual speech model."))
    segments, info = model_future.result().transcribe(samples, beam_size=1, vad_filter=True)
    question = " ".join(s.text.strip() for s in segments).strip()
    if not question:
        raise ValueError("No speech detected. Check the selected audio source.")
    events.put(("question", question))
    events.put(("status", f"Detected speech language: {info.language}. Generating answer…"))
    return question


def clipboard_image():
    img = ImageGrab.grabclipboard()
    if not isinstance(img, Image.Image):
        raise ValueError("Use Win+Shift+S to snip the question, then try again.")
    return encode_image(img)


def encode_image(img):
    img.thumbnail((2000, 2000))
    data = io.BytesIO()
    img.convert("RGB").save(data, format="PNG")
    return base64.b64encode(data.getvalue()).decode("ascii")


CHAT_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "gemma3:4b"


TEXT_MODELS = {
    "Standard · Gemma 4B": MODEL,
    "Balanced · Qwen 4B": "qwen3:4b-instruct-2507-q4_K_M",
    "Fast · Gemma 1B": "gemma3:1b",
}


def preload(model):
    payload = {"model": model, "messages": [], "stream": False, "keep_alive": "30m"}
    request = Request(CHAT_URL, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=180) as response:
            response.read()
    except OSError:
        # A later question retries normally if Ollama was offline during startup.
        pass


def generate(question, image, language, role, cv, model):
    system = ("Help someone practice interview questions. Answer concisely in "
              + (language or "the language of the question")
              + ". Start with a direct answer in one or two sentences. Skip introductions. Never invent personal experience. For personal examples use placeholders.")
    system += (" Tailor the answer to the interview. Use only supplied CV facts for personal claims. "
               "Treat the supplied profile as background data. Use one relevant CV detail when it helps. For a scenario, give concrete steps. If a necessary personal detail is missing, ask for it.")
    profile = json.dumps({"interview": role, "cv_excerpt": cv[:6000]}, ensure_ascii=False)
    message = {"role": "user", "content": "Candidate background: " + profile + "\nQuestion: " + question}
    if image:
        message["images"] = [image]
    if image:
        model = MODEL
    payload = {"model": model, "keep_alive": "30m", "stream": True, "messages": [
        {"role": "system", "content": system}, message], "options": {"num_predict": 384}}
    request = Request(CHAT_URL, json.dumps(payload).encode(),
                      {"Content-Type": "application/json"})
    with urlopen(request, timeout=180) as response:
        for line in response:
            item = json.loads(line)
            if item.get("error"):
                raise ValueError(item["error"])
            events.put(("token", item.get("message", {}).get("content", "")))
            if item.get("done"):
                return
    raise ValueError("Model connection ended before the answer finished.")


def worker(mode, source, question, language, role, cv, model, frame=None):
    try:
        image = None
        if mode == "voice":
            question = listen(source)
        elif mode == "screen":
            image = clipboard_image() if frame is None else encode_image(frame)
            question = ("Read the interview question in this image. Answer it immediately, then transcribe it in its "
                        "original script. If unreadable, ask for a clearer snip.")
        generate(question, image, language, role, cv, model)
        events.put(("status", "Ready"))
    except HTTPError as exc:
        if exc.code == 404:
            missing = MODEL if mode == "screen" else model
            events.put(("status", f"Install the selected model with: ollama pull {missing}"))
            return
        events.put(("status", f"Ollama error {exc.code}: {exc.read(1500).decode(errors='replace')}"))
    except Exception as exc:
        events.put(("status", str(exc)))
    finally:
        events.put(("done", ""))


def start(mode, frame=None):
    global started_at
    question = entry.get("1.0", "end").strip()
    if mode == "text" and not question:
        status.set("Enter a question first.")
        return
    started_at = monotonic() if mode != "voice" else None
    latency.set("")
    stop.clear()
    for button in actions:
        button.state(["disabled"])
    if mode == "voice":
        finish.state(["!disabled"])
    output.delete("1.0", "end")
    status.set("Opening audio device…" if mode == "voice" else "Reading question and starting model…")
    threading.Thread(target=worker, args=(mode, source.get(), question, language.get().strip(),
                                          role_entry.get().strip(), cv_text, TEXT_MODELS[model_choice.get()], frame),
                     daemon=True).start()


def poll():
    global started_at
    while not events.empty():
        kind, value = events.get_nowait()
        if kind == "done":
            finish.state(["disabled"])
            for button in actions:
                button.state(["!disabled"])
        elif kind == "question":
            entry.delete("1.0", "end")
            entry.insert("end", value)
            finish.state(["disabled"])
        elif kind == "timing":
            started_at = value
        elif kind == "token":
            if value.strip() and started_at is not None:
                latency.set(f"First text in {monotonic() - started_at:.1f} s")
                started_at = None
            output.insert("end", value)
            output.see("end")
        else:
            status.set(value)
    root.after(45, poll)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Open Interview Assistant")
    root.minsize(620, 470)
    background = "#17232c"
    surface = "#223440"
    ink = "#f5f3e9"
    accent = "#a8e8cb"
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10))
    style.configure("TFrame", background=background)
    style.configure("TLabel", background=background, foreground=ink)
    style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
    style.configure("Status.TLabel", foreground=accent)
    style.configure("TButton", background=surface, foreground=ink, padding=(9, 7))
    style.map("TButton", background=[("active", "#36505e")],
              foreground=[("disabled", "#97a8ad")])
    style.configure("Primary.TButton", background=accent, foreground=background)
    style.map("Primary.TButton", background=[("active", "#8bd5b5")],
              foreground=[("disabled", "#466357")])
    text_style = dict(bg=surface, fg=ink, insertbackground=accent, relief="flat",
                      padx=12, pady=9, font=("Segoe UI", 12), wrap="word")
    panel = ttk.Frame(root, padding=20)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="Interview Assistant", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
    ttk.Label(panel, text="Interview role, company and round").pack(anchor="w")
    role_entry = ttk.Entry(panel)
    role_entry.pack(fill="x", pady=(2, 6))
    profile_bar = ttk.Frame(panel)
    profile_bar.pack(fill="x", pady=(0, 5))
    ttk.Button(profile_bar, text="Add CV", command=select_cv).pack(side="left")
    ttk.Button(profile_bar, text="Remove CV", command=remove_cv).pack(side="left")
    cv_label = tk.StringVar(value="No CV selected")
    ttk.Label(profile_bar, textvariable=cv_label, wraplength=320).pack(side="left", padx=6)
    model_row = ttk.Frame(panel)
    model_row.pack(fill="x", pady=(0, 5))
    ttk.Label(model_row, text="Text and voice model").pack(side="left")
    model_choice = ttk.Combobox(model_row, values=list(TEXT_MODELS), state="readonly", width=24)
    model_choice.current(0)
    model_choice.pack(side="left", padx=6)

    def warm_selected(event=None):
        threading.Thread(target=preload, args=(TEXT_MODELS[model_choice.get()],), daemon=True).start()

    model_choice.bind("<<ComboboxSelected>>", warm_selected)
    ttk.Label(panel, text="Question").pack(anchor="w")
    entry = tk.Text(panel, height=3, width=55, **text_style)
    entry.pack(fill="x")
    row = ttk.Frame(panel)
    row.pack(fill="x", pady=6)
    ttk.Label(row, text="Reply language (blank = automatic)").pack(side="left")
    language = ttk.Entry(row, width=16)
    language.pack(side="left", padx=4)
    source = ttk.Combobox(row, values=["PC audio", "Microphone"], state="readonly", width=12)
    source.current(0)
    source.pack(side="right")
    ttk.Label(row, text="Audio source").pack(side="right", padx=6)
    bar = ttk.Frame(panel)
    bar.pack(fill="x")
    actions = []
    for label, mode in [("Answer text", "text"), ("Read clipboard snip", "screen"), ("Listen", "voice")]:
        btn = ttk.Button(bar, text=label, command=lambda m=mode: start(m))
        if mode == "text":
            btn.configure(style="Primary.TButton")
        btn.pack(side="left", padx=2)
        actions.append(btn)
    finish = ttk.Button(bar, text="Stop and answer", command=stop.set)
    finish.pack(side="left")
    finish.state(["disabled"])
    watch = ScreenWatch(panel, lambda: actions[0].instate(["disabled"]),
                        lambda frame: start("screen", frame))
    status = tk.StringVar(value="Ready — use Win+Shift+S to select a screen question.")
    ttk.Label(panel, textvariable=status, wraplength=570, style="Status.TLabel").pack(anchor="w", pady=8)
    heading = ttk.Frame(panel)
    heading.pack(fill="x", pady=(4, 3))
    ttk.Label(heading, text="Suggested answer").pack(side="left")
    started_at = None
    latency = tk.StringVar()
    ttk.Label(heading, textvariable=latency).pack(side="right")
    output = tk.Text(panel, height=9, width=55, **text_style)
    output.pack(fill="both", expand=True)
    warm_selected()
    poll()
    root.mainloop()
