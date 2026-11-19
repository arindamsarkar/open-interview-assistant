const seeds = new Map();
chrome.runtime.onMessage.addListener((msg, sender, send) => {
  if (!sender.url?.startsWith(chrome.runtime.getURL(""))) return;
  if (msg.type === "seed") {
    seeds.set(msg.id, msg.selected);
    setTimeout(() => seeds.delete(msg.id), 30000);
    send(true);
  } else if (msg.type === "take") {
    send(seeds.get(msg.id) || "");
    seeds.delete(msg.id);
  }
});

chrome.runtime.onConnect.addListener(port => {
  if (port.name !== "practice" || port.sender.id !== chrome.runtime.id) return;
  const controller = new AbortController();
  port.onDisconnect.addListener(() => controller.abort());
  port.onMessage.addListener(async msg => {
    try {
      const res = await fetch("http://127.0.0.1:11434/api/chat", {
        method: "POST", signal: controller.signal, headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
          model: msg.image ? "gemma3:4b" : msg.model, stream: true, keep_alive: "15m",
          messages: [{role:"system",content:msg.mode === "recap" ? "Write concise meeting notes in the requested language. Ground the summary in the supplied notes and discussion. Mark missing information clearly." : "Coach interview practice. Answer briefly in the requested language. Ground personal claims in the provided background."},
                     ...msg.history, {role:"user",...(msg.image ? {images:[msg.image]} : {}),content:JSON.stringify({role:msg.role,background:msg.cv,meeting_notes:msg.notes,language:msg.language || "match the question",question:msg.question})}]
        })
      });
      if (!res.ok) {
        if (res.status === 403) throw Error("Allow this extension in Ollama. Set OLLAMA_ORIGINS to chrome-extension://" + chrome.runtime.id + " and restart Ollama.");
        if (res.status === 404) throw Error("Model missing. Run ollama pull " + (msg.image ? "gemma3:4b" : msg.model));
        throw Error("Ollama returned HTTP " + res.status);
      }
      let buffer = "";
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      while (true) {
        const {done,value} = await reader.read();
        buffer += value || "";
        const lines = buffer.split("\n");
        buffer = lines.pop();
        if (done && buffer) lines.push(buffer);
        for (const line of lines.filter(Boolean)) {
          const part = JSON.parse(line);
          if (part.error) throw Error(part.error);
          if (part.message?.content) port.postMessage({token:part.message.content});
          if (part.done) {port.postMessage({done:true}); return;}
        }
        if (done) throw Error("Ollama closed the stream early.");
      }
    } catch (e) {
      if (!controller.signal.aborted) port.postMessage({error:e.message});
    }
  });
});
