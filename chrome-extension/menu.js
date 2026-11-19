async function launch(separate) {
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (separate) {
      let selected = "";
      try {
        const [item] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: () => String(getSelection()).slice(0, 8000)});
        selected = item.result;
      } catch { /* Restricted tabs still support typed practice in a separate window. */ }
      const id = crypto.randomUUID();
      await chrome.runtime.sendMessage({type: "seed", id, selected});
      await chrome.windows.create({type: "popup", url: chrome.runtime.getURL("panel.html#" + id), width: 440, height: 550});
    } else {
      await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ["panel.js"]});
    }
    window.close();
  } catch (error) {
    document.querySelector("#status").textContent = "Could not open here. Try a normal webpage or the separate window. " + error.message;
  }
}
document.querySelector("#overlay").onclick = () => launch(false);
document.querySelector("#window").onclick = () => launch(true);
