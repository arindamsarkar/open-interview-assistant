(async () => {
  if (globalThis.practicePanel?.isConnected) return;
  const standalone = location.protocol === "chrome-extension:";
  const selected = standalone ? await chrome.runtime.sendMessage({type:"take", id:location.hash.slice(1)}) : String(getSelection());
  const host = document.createElement("div");
  globalThis.practicePanel = host;
  if (!standalone) host.style.cssText = "all:initial!important;position:fixed!important;left:max(8px,calc(50vw - 213px))!important;top:16px!important;width:min(426px,calc(100vw - 16px))!important;z-index:2147483647!important";
  document.documentElement.append(host);
  const ui = host.attachShadow({mode:"closed"});
  ui.innerHTML = `<style>
    *{box-sizing:border-box}[hidden]{display:none!important}section{color-scheme:dark;font:14px/1.45 system-ui;color:#f6f6fa;background:rgba(28,29,36,.96);border:1px solid #50515d;border-radius:18px;box-shadow:0 8px 32px #0004;max-height:90vh;overflow:auto}
    header,.actions{display:flex;align-items:center;gap:6px}header{padding:8px 10px}h1{flex:1;margin:0;font-size:14px;font-weight:650;letter-spacing:-.2px}
    #grip{color:#aaabb7;cursor:grab;touch-action:none;user-select:none;padding:2px 6px;font-size:18px}
    #body{padding:0 12px 12px}summary{cursor:pointer;color:#c7c7d2}details{border-top:1px solid #454650;padding:9px 2px}label{display:block;margin:6px 0}
    textarea,input,select,button{font:inherit}textarea,input,select{width:100%;padding:8px;background:#202128;color:white;border:1px solid #555662;border-radius:8px}
    textarea{resize:vertical}button{cursor:pointer;padding:5px 9px;color:#f3f3f9;background:#393a44;border:1px solid #565762;border-radius:8px}button:hover{background:#484956}button:focus-visible,summary:focus-visible{outline:2px solid #b3a8ff}button:disabled{opacity:.6}
    #ask{background:#ecebf4;color:#24242d;font-weight:600;margin-left:auto}#status{color:#c3c1d1;font-size:12px}.reply{background:#34353e;border-radius:11px;margin:4px 0 10px;padding:10px 12px}.reply:has(output:empty){display:none}
    output{display:block;white-space:pre-wrap;max-height:34vh;overflow:auto}.actions{flex-wrap:wrap}kbd{font:11px system-ui;opacity:.75}
    </style><section><header><span id="grip" title="Drag to move">⠿</span><h1>Interview Assistant</h1><button id="fold" aria-expanded="true" aria-label="Collapse panel">−</button><button id="close" aria-label="Close panel">×</button></header><div id="body">
    <details><summary>Interview setup</summary><label>Role and company<input id="role"></label><label>Relevant CV notes<textarea id="cv"></textarea></label>
    <label>Reply language<input id="language" placeholder="Match question"></label><label>Model<select id="model"><option>gemma3:4b</option><option>gemma3:1b</option><option>qwen3:4b-instruct-2507-q4_K_M</option></select></label></details>
    <div class="reply"><output id="answer" aria-label="Suggested answer"></output></div>
    <label for="question">Question</label><textarea id="question" rows="2" placeholder="Ask a question or follow up"></textarea>
    <div class="actions"><button id="pick">Use selection</button><button id="ask">Assist <kbd>Ctrl ↵</kbd></button></div>
    <details><summary>Meeting tools</summary>
    <label>Speech language<select id="speechLang"><option value="en-IN">English</option><option value="hi-IN">Hindi</option><option value="bn-IN">Bengali</option></select></label>
    <small>Chrome may send microphone audio to its speech service. Start only with participant permission.</small>
    <div class="actions"><button id="mic">Start mic transcript</button><button id="screen">Ask about screen</button></div>
    <label>Transcript and meeting notes<textarea id="notes" rows="4"></textarea></label>
    <div class="actions"><button id="summary">Recap and next steps</button><button id="export">Export Markdown</button></div>
    </details><small id="status" role="status">Ready</small></div></section>`;
  const el = id => ui.getElementById(id);
  el("fold").onclick = () => {
    const folded = !el("body").hidden;
    el("body").hidden = folded;
    el("fold").textContent = folded ? "+" : "−";
    el("fold").setAttribute("aria-expanded", String(!folded));
    el("fold").setAttribute("aria-label", folded ? "Expand panel" : "Collapse panel");
  };
  el("question").onkeydown = e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !e.isComposing) {
      e.preventDefault(); el("ask").click();
    }
  };
  const grip = el("grip");
  grip.hidden = standalone;
  if (!standalone) {
    let offset;
    grip.onpointerdown = e => {
      if (e.button !== 0) return;
      const box = host.getBoundingClientRect();
      offset = [e.clientX - box.left, e.clientY - box.top];
      grip.setPointerCapture(e.pointerId);
    };
    grip.onpointermove = e => {
      if (!offset) return;
      const box = host.getBoundingClientRect();
      const x = Math.max(0, Math.min(innerWidth - box.width, e.clientX - offset[0]));
      const y = Math.max(0, Math.min(innerHeight - box.height, e.clientY - offset[1]));
      host.style.setProperty("left", x + "px", "important");
      host.style.setProperty("top", y + "px", "important");
    };
    grip.onlostpointercapture = () => { offset = null; };
  }
  el("question").value = (selected || "").slice(0,8000);
  el("pick").hidden = standalone;
  el("pick").onmousedown = e => e.preventDefault();
  el("pick").onclick = () => {
    const text = String(getSelection()).trim();
    if (text) el("question").value = text.slice(0,8000);
    else el("status").textContent = "Select a question on the page first.";
  };
  const history = [];
  let port;
  const log = [];
  let recognition;
  let capturing = false;
  let closed = false;
  el("mic").onclick = () => {
    if (recognition) {recognition.stop(); return;}
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) {el("status").textContent = "Speech recognition unavailable. Type or paste your transcript."; return;}
    const speech = new Speech();
    speech.lang = el("speechLang").value;
    speech.continuous = true;
    speech.onresult = event => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          const line = event.results[i][0].transcript.trim();
          if (line) el("notes").value += (el("notes").value ? "\n" : "") + line;
        }
      }
    };
    speech.onend = () => {recognition = null; el("mic").textContent = "Start mic transcript";};
    speech.onerror = e => {el("status").textContent = "Microphone transcription: " + e.error;};
    try {
      speech.start(); recognition = speech; el("mic").textContent = "Stop mic transcript";
    } catch (error) {el("status").textContent = error.message;}
  };
  el("screen").onclick = async () => {
    if (capturing || port) return;
    capturing = true;
    let stream;
    const video = document.createElement("video");
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({video:true, audio:false});
      if (closed) return;
      video.muted = true; video.srcObject = stream; await video.play();
      const canvas = document.createElement("canvas");
      const ratio = Math.min(1, 1600 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * ratio);
      canvas.height = Math.round(video.videoHeight * ratio);
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      if (!closed) run(el("question").value.trim() || "Read and answer the question on screen.", "screen", canvas.toDataURL("image/png").split(",")[1]);
    } catch (error) {el("status").textContent = "Screen capture: " + error.message;}
    finally {stream?.getTracks().forEach(track => track.stop()); video.srcObject = null; capturing = false;}
  };
  el("export").onclick = () => {
    const parts = ["# Interview session", el("role").value, "## Meeting notes", el("notes").value,
                   ...log.map(turn => "## " + turn.question + "\n\n" + turn.answer)];
    const url = URL.createObjectURL(new Blob([parts.join("\n\n")], {type:"text/markdown"}));
    const link = document.createElement("a"); link.href = url; link.download = "interview-session.md"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  };
  el("close").onclick = () => {
    closed = true; recognition?.abort(); port?.disconnect(); host.remove(); if (standalone) window.close();
  };
  el("ask").onclick = () => run(el("question").value.trim(), "answer");
  el("summary").onclick = () => {
    if (!el("notes").value.trim() && !history.length) {el("status").textContent = "Add notes or complete a turn first.";return;}
    run("Summarize this discussion and list decisions and next steps. Include owners and dates only if stated.", "recap");
  };
  function run(question, mode, image) {
    if (port || closed) return;
    if (!question) {el("status").textContent = "Enter or select a question.";return;}
    const channel = chrome.runtime.connect({name:"practice"});
    port = channel; el("ask").disabled = true;
    el("status").textContent = "Waiting for local Ollama…";
    el("answer").textContent = "";
    channel.onDisconnect.addListener(() => {
      if (port === channel) {port = null; el("ask").disabled=false; el("status").textContent="Connection ended. Check that Ollama is running.";}
    });
    channel.onMessage.addListener(msg => {
      if (msg.token) {el("answer").textContent += msg.token; el("status").textContent="Answering…";}
      if (msg.done || msg.error) {
        if (msg.done) {
          log.push({question,answer:el("answer").textContent});
          history.push({role:"user",content:question},{role:"assistant",content:el("answer").textContent});
          if (history.length > 8) history.splice(0,2);
        }
        el("status").textContent = msg.error || "Ready"; port=null; el("ask").disabled=false; channel.disconnect();
      }
    });
    channel.postMessage({question,history,mode,image,notes:el("notes").value.slice(-16000),role:el("role").value,cv:el("cv").value.slice(0,6000),language:el("language").value,model:el("model").value});
  };
})();
