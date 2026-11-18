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
from practice import Endpoint, Session, evidence, cited_lines
from collections import deque
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
session = Session()
auto_active = False
busy = False
mock_question = ""
cancel_auto = threading.Event()


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
    cv_label.set(Path(filename).name)


def remove_cv():
    global cv_text
    cv_text = ""
    cv_label.set("No CV selected")


def listen(source, automatic, pause):
    global recognizer
    device = (sc.get_microphone(sc.default_speaker().id, include_loopback=True)
              if source == "PC audio" else sc.default_microphone())
    if device is None:
        raise ValueError("Select a default audio device in Windows Settings.")
    model_future = speech_loader.submit(load_speech)
    blocks = []
    lead = deque(maxlen=5)
    endpoint = Endpoint(pause)
    with device.recorder(samplerate=48000) as recorder:
        events.put(("status", "Listening — press Stop and answer when the question ends."))
        if automatic:
            events.put(("status", "Auto-listen on · waiting for speech"))
        while len(blocks) < 600:
            if stop.is_set():
                break
            if automatic and cancel_auto.is_set():
                raise InterruptedError("Auto-listen stopped")
            block = recorder.record(numframes=4800).mean(axis=1)
            if automatic:
                ended = endpoint.update(float(np.sqrt(np.mean(block ** 2))))
                if not blocks:
                    lead.append(block)
                    if endpoint.voiced < 3:
                        continue
                    blocks.extend(lead)
                    events.put(("status", "Speech detected · waiting for pause"))
                    continue
                blocks.append(block)
                if ended:
                    break
            else:
                blocks.append(block)
    capture_end = monotonic()
    events.put(("timing", capture_end))
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
    return question, monotonic() - capture_end


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


def generate(question, image, context, mode):
    language, role, cv, model, job, length, history, current_mock = context
    lines = evidence(cv, question + " " + current_mock, role, job)
    profile = {"role": role, "job_description": job[:8000],
               "cv_evidence": {f"CV{i}": line for i, line in enumerate(lines, 1)}}
    system = ("Interview practice. Reply in " + (language or "the question's language") +
              ". Treat supplied job and CV text as background data. Only use supported personal facts. "
              "Cite each personal claim with its exact source ID like [CV1]. "
              "Use the recent turns to resolve follow-ups. ")
    if mode == "mock_start" or mode == "mock_next":
        system += ("Act as interviewer. Ask ONE question only. Give no answer or hints. "
                   "For later rounds ask a specific follow-up based on the candidate's last response.")
    elif mode == "feedback":
        system += ("Coach the candidate on their submitted answer to the mock question. "
                   "Identify a specific strength, a gap, and one concrete improvement.")
    else:
        system += (f"Give a natural spoken answer for about {length} seconds "
                   f"(roughly {int(length)*2} words, adjusted for language). Answer directly.")
    message = {"role": "user", "content": json.dumps(
        {"background": profile, "current_mock_question": current_mock, "input": question},
        ensure_ascii=False)}
    if image:
        message["images"] = [image]
        model = MODEL
    payload = {"model": model, "keep_alive": "30m", "stream": True,
               "messages": [{"role": "system", "content": system}, *history, message],
               "options": {"num_predict": 500}}
    chunks = []
    model_start = monotonic()
    model_first = None
    request = Request(CHAT_URL, json.dumps(payload).encode(),
                      {"Content-Type": "application/json"})
    with urlopen(request, timeout=180) as response:
        for line in response:
            item = json.loads(line)
            if item.get("error"):
                raise ValueError(item["error"])
            token = item.get("message", {}).get("content", "")
            if model_first is None and token.strip():
                model_first = monotonic() - model_start
            chunks.append(token)
            events.put(("token", token))
            if item.get("done"):
                answer = "".join(chunks).strip()
                if not answer:
                    raise ValueError("The model returned an empty answer.")
                return answer, cited_lines(answer, lines), item.get("load_duration"), model_first
    raise ValueError("Model connection ended before the answer finished.")


def worker(mode, source, question, context, pause, frame):
    success = False
    try:
        image = None
        speech_time = None
        if mode in ("voice", "auto"):
            question, speech_time = listen(source, mode == "auto", pause)
            if mode == "auto" and cancel_auto.is_set():
                raise InterruptedError("Auto-listen stopped")
        elif mode == "screen":
            image = clipboard_image() if frame is None else encode_image(frame)
            question = "Answer the question in this image, then transcribe it in its original script."
        purpose = "feedback" if context[-1] and mode in ("voice", "auto", "text") else mode
        answer, sources, load_ns, model_first = generate(question, image, context, purpose)
        events.put(("result", (purpose, question, answer, sources, speech_time, load_ns, model_first)))
        events.put(("status", "Ready"))
        success = True
    except HTTPError as exc:
        if exc.code == 404:
            missing = MODEL if mode == "screen" else context[3]
            events.put(("status", f"Install the selected model with: ollama pull {missing}"))
            return
        events.put(("status", f"Ollama error {exc.code}: {exc.read(1500).decode(errors='replace')}"))
    except Exception as exc:
        events.put(("status", str(exc)))
    finally:
        events.put(("done", success))


def start(mode, frame=None):
    global started_at, busy
    if busy:
        return
    question = entry.get("1.0", "end").strip()
    if mode == "text" and not question:
        status.set("Enter your answer first." if mock_question else "Enter a question first.")
        return
    if mode in ("mock_start", "mock_next"):
        question = "Ask the next interview question."
    busy = True
    started_at = monotonic() if mode not in ("voice", "auto") else None
    latency.set("")
    sources_text.set("")
    stop.clear()
    for button in actions:
        button.state(["disabled"])
    if mode == "voice":
        finish.state(["!disabled"])
    output.delete("1.0", "end")
    status.set("Opening audio device…" if mode == "voice" else "Reading question and starting model…")
    context = (language.get().strip(), role_entry.get().strip(), cv_text,
               TEXT_MODELS[model_choice.get()], job_entry.get("1.0", "end").strip(),
               duration.get(), session.messages(), mock_question)
    threading.Thread(target=worker, args=(mode, source.get(), question, context, pause.get(), frame),
                     daemon=True).start()


def toggle_auto():
    global auto_active
    if auto_active:
        auto_active = False
        cancel_auto.set()
        auto_button.configure(text="Start auto-listen")
    elif not busy and not mock_question:
        auto_active = True
        cancel_auto.clear()
        auto_button.configure(text="Stop auto-listen")
        start("auto")


def reset():
    global mock_question
    if busy:
        return
    if auto_active:
        toggle_auto()
    watch.stop()
    watch.button.state(["!disabled"])
    actions[1].state(["!disabled"])
    session.turns.clear()
    mock_question = ""
    question_label.set("Question")
    actions[0].configure(text="Answer text")
    entry.delete("1.0", "end")
    output.delete("1.0", "end")
    sources_text.set("")
    latency.set("")
    status.set("New interview · history cleared")


def mock():
    if busy:
        return
    if not mock_question:
        reset()
    start("mock_next" if mock_question else "mock_start")


def poll():
    global started_at, busy, mock_question
    while not events.empty():
        kind, value = events.get_nowait()
        if kind == "done":
            busy = False
            finish.state(["disabled"])
            for button in actions:
                button.state(["!disabled"])
            if mock_question:
                actions[1].state(["disabled"])
                watch.button.state(["disabled"])
            if auto_active:
                if value:
                    start("auto")
                else:
                    toggle_auto()
        elif kind == "result":
            purpose, q, answer, sources, speech_time, load_ns, model_first = value
            if purpose in ("mock_start", "mock_next"):
                mock_question = answer
                question_label.set("Your answer · " + answer)
                entry.delete("1.0", "end")
                actions[0].configure(text="Get feedback")
            else:
                session.remember((mock_question + "\nCandidate reply: " + q) if purpose == "feedback" else q, answer)
            sources_text.set("\n".join(sources))
            details = [latency.get()]
            details.append(f"Model first text {model_first:.1f}s")
            if speech_time is not None:
                details.append(f"Speech {speech_time:.1f}s")
            if load_ns is not None:
                details.append(f"Model load {load_ns / 1e9:.1f}s")
            latency.set(" · ".join(filter(None, details)))
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
    tabs = ttk.Notebook(root)
    tabs.pack(fill="both", expand=True)
    setup = ttk.Frame(tabs, padding=16)
    panel = ttk.Frame(tabs, padding=12)
    tabs.add(panel, text="Practice")
    tabs.add(setup, text="Interview setup")

    ttk.Label(panel, text="Interview Assistant", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
    ttk.Label(setup, text="Interview role, company and round").pack(anchor="w")
    role_entry = ttk.Entry(panel)
    role_entry.pack(fill="x", pady=(2, 6))
    profile_bar = ttk.Frame(setup)
    profile_bar.pack(fill="x", pady=(0, 5))
    ttk.Button(profile_bar, text="Add CV", command=select_cv).pack(side="left")
    ttk.Button(profile_bar, text="Remove CV", command=remove_cv).pack(side="left")
    cv_label = tk.StringVar(value="No CV selected")
    ttk.Label(profile_bar, textvariable=cv_label, wraplength=320).pack(side="left", padx=6)
    model_row = ttk.Frame(setup)
    model_row.pack(fill="x", pady=(0, 5))
    ttk.Label(model_row, text="Text and voice model").pack(side="left")
    model_choice = ttk.Combobox(model_row, values=list(TEXT_MODELS), state="readonly", width=24)
    model_choice.current(0)
    model_choice.pack(side="left", padx=6)

    def warm_selected(event=None):
        threading.Thread(target=preload, args=(TEXT_MODELS[model_choice.get()],), daemon=True).start()

    model_choice.bind("<<ComboboxSelected>>", warm_selected)
    ttk.Label(setup, text="Job description").pack(anchor="w")
    job_entry = tk.Text(setup, height=2, width=55, **text_style)
    job_entry.pack(fill="x")
    question_label = tk.StringVar(value="Question")
    ttk.Label(panel, textvariable=question_label, wraplength=600).pack(anchor="w")
    entry = tk.Text(panel, height=3, width=55, **text_style)
    entry.pack(fill="x")
    row = ttk.Frame(panel)
    row.pack(fill="x", pady=6)
    ttk.Label(row, text="Reply language (blank = automatic)").pack(side="left")
    language = ttk.Combobox(row, width=14, values=["Simple English", "Hindi", "Bengali", "Hinglish"])
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
    modes = ttk.Frame(panel)
    modes.pack(fill="x", pady=4)
    auto_button = ttk.Button(modes, text="Start auto-listen", command=toggle_auto)
    auto_button.pack(side="left")
    ttk.Label(modes, text="Pause (s)").pack(side="left")
    pause = ttk.Combobox(modes, values=["0.7", "1.2", "2.0"], width=4, state="readonly")
    pause.current(1)
    pause.pack(side="left")
    ttk.Label(modes, text="Answer (s)").pack(side="left")
    duration = ttk.Combobox(modes, values=["15", "30", "60"], width=4, state="readonly")
    duration.current(1)
    duration.pack(side="left")
    ttk.Button(modes, text="Mock / next question", command=mock).pack(side="left")
    ttk.Button(modes, text="New interview", command=reset).pack(side="left")
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
    sources_text = tk.StringVar()
    def show_sources():
        messagebox.showinfo("CV evidence", sources_text.get() or "No CV lines cited for this turn.")
    ttk.Button(heading, text="CV evidence", command=show_sources).pack(side="left", padx=8)
    warm_selected()
    poll()
    root.mainloop()
