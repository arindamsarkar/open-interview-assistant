(async () => {
  if (globalThis.practicePanel?.isConnected) return;
  const standalone = location.protocol === "chrome-extension:";
  const selected = standalone ? await chrome.runtime.sendMessage({type:"take", id:location.hash.slice(1)}) : String(getSelection());
  const host = document.createElement("div");
  globalThis.practicePanel = host;
  if (!standalone) host.style.cssText = "all:initial!important;position:fixed!important;right:12px!important;bottom:12px!important;width:min(380px,96vw)!important;z-index:2147483647!important";
  document.documentElement.append(host);
  const ui = host.attachShadow({mode:"closed"});
  ui.innerHTML = `<style>
    *{box-sizing:border-box}section{font:14px/1.45 system-ui;color:#f5faf8;background:#14262c;padding:16px;border:1px solid #57877c;border-radius:12px;max-height:95vh;overflow:auto}
    header{display:flex;justify-content:space-between;align-items:center}h1{font-size:18px;margin:0}label,details,p{display:block;margin:9px 0}
    textarea,input,select,button{font:inherit}textarea,input,select{width:100%;padding:6px;background:#223640;color:white;border:1px solid #65817e;border-radius:5px}
    button{cursor:pointer;padding:5px 10px;border:0;border-radius:5px}#ask{background:#a8e8cb}output{display:block;white-space:pre-wrap}small{color:#bfdbd1}
    </style><section><header><h1>Interview Assistant</h1><button id="close" aria-label="Close panel">Close</button></header>
    <details><summary>Interview setup</summary><label>Role and company<input id="role"></label><label>Relevant CV notes<textarea id="cv"></textarea></label>
    <label>Reply language<input id="language" placeholder="Match question"></label><label>Model<select id="model"><option>gemma3:4b</option><option>gemma3:1b</option><option>qwen3:4b-instruct-2507-q4_K_M</option></select></label></details>
    <label>Practice question<textarea id="question" rows="3"></textarea></label><button id="ask">Get answer</button> <button id="pick">Use selected text</button>
    <p><small id="status" role="status">Ready</small></p><output id="answer"></output></section>`;
  const el = id => ui.getElementById(id);
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
  el("close").onclick = () => {port?.disconnect(); host.remove(); if (standalone) window.close();};
  el("ask").onclick = () => {
    const question = el("question").value.trim();
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
          history.push({role:"user",content:question},{role:"assistant",content:el("answer").textContent});
          if (history.length > 8) history.splice(0,2);
        }
        el("status").textContent = msg.error || "Ready"; port=null; el("ask").disabled=false; channel.disconnect();
      }
    });
    channel.postMessage({question,history,role:el("role").value,cv:el("cv").value.slice(0,6000),language:el("language").value,model:el("model").value});
  };
})();
