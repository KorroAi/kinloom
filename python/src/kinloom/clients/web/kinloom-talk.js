// A dialogue box for any web game: the player talks with a character that has a soul. No dependencies.
//
//   import { Kinloom } from "./kinloom.js";
//   import { talkBox } from "./kinloom-talk.js";
//   const kl = new Kinloom();
//   kl.character("Mira", "", { soul: "a gruff blacksmith who secretly sold the king's sword", offline: "Busy.",
//                              tools: { give: { item: "sword" } } });
//   const box = talkBox(kl, "Mira", { speaker: "Ana", onAction: (tool, args) => game.run(tool, args) });
//   box.open();                     // she speaks first; box.send("hello"), box.close()
//
// Replies stream in as they are written. What the character decides while talking (validated against its tools)
// arrives in onAction. voice: true says each sentence aloud as soon as it is written, in the character's voice from
// `kinloom serve` (a voice key there), else with the browser's own voices (free, no key); a microphone button (hold to
// talk) sends what the player says, understood by the server's voice or the browser's recognition.

const CSS = `
.kl-talk { position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%); width: min(640px, calc(100vw - 32px));
  max-height: 46vh; display: none; flex-direction: column; background: rgba(15,17,23,.92); color: #e6e8ef;
  border: 1px solid #2c3242; border-radius: 12px; font: 15px/1.45 system-ui, sans-serif; z-index: 2147483000;
  box-shadow: 0 10px 40px rgba(0,0,0,.45); }
.kl-talk.kl-open { display: flex; }
.kl-talk header { display: flex; align-items: center; gap: 10px; padding: 9px 14px; border-bottom: 1px solid #2c3242; }
.kl-talk header b { flex: 1; } .kl-talk .kl-mood { font-size: 12px; opacity: .65; }
.kl-talk header button { background: none; border: 0; color: inherit; font-size: 18px; cursor: pointer; opacity: .7; }
.kl-talk .kl-log { overflow: auto; padding: 10px 14px; display: flex; flex-direction: column; gap: 8px; min-height: 60px; }
.kl-talk .kl-me { align-self: flex-end; background: #3a4ea8; padding: 6px 11px; border-radius: 12px; max-width: 80%; }
.kl-talk .kl-them { align-self: flex-start; background: #232839; padding: 6px 11px; border-radius: 12px; max-width: 85%; white-space: pre-wrap; }
.kl-talk .kl-gesture { align-self: flex-start; font-style: italic; opacity: .6; font-size: 13px; margin-top: -4px; }
.kl-talk form { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #2c3242; }
.kl-talk input { flex: 1; background: #0f1117; color: inherit; border: 1px solid #2c3242; border-radius: 8px; padding: 8px 10px; font: inherit; }
.kl-talk form button { background: #7c9cff; color: #fff; border: 0; border-radius: 8px; padding: 8px 14px; font: inherit; font-weight: 600; cursor: pointer; }
.kl-talk form .kl-mic { background: #232839; padding: 8px 11px; } .kl-talk form .kl-mic.kl-on { background: #d0473f; }
`;

const SENTENCE = /[.!?\u2026]+["'\u201d\u2019)\]]*\s+/g;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

/** options: speaker (the player's name), parent (element), voice (read replies aloud), lang ("en", "fr"...),
 * speakFirst (on open), facts (function returning the facts of the moment), onAction(tool, args), onReply(text),
 * onGesture(text): the visible thing the character does while speaking ("points at the door"), for your animations. */
export function talkBox(kl, name, { speaker = "player", parent = document.body, voice = false, lang = "", speakFirst = true,
                                    facts = () => ({}), onAction = null, onReply = null, onGesture = null,
                                    mic = voice } = {}) {
  if (!document.getElementById("kl-talk-css")) {
    const style = el("style");
    style.id = "kl-talk-css";
    style.textContent = CSS;
    document.head.appendChild(style);
  }
  const root = el("div", "kl-talk");
  const head = el("header");
  const mood = el("span", "kl-mood");
  const x = el("button", "", "×");
  x.type = "button";
  x.title = "Close";
  head.append(el("b", "", name), mood, x);
  const log = el("div", "kl-log");
  const form = el("form");
  const input = el("input");
  input.placeholder = "Say something…";
  const send = el("button", "", "Send");
  const micButton = el("button", "kl-mic", "\u{1F3A4}");
  micButton.type = "button";
  micButton.title = "Hold to talk";
  const canRecord = mic && typeof navigator !== "undefined" && navigator.mediaDevices && typeof MediaRecorder !== "undefined";
  form.append(input, ...(canRecord ? [micButton] : []), send);
  root.append(head, log, form);
  parent.appendChild(root);
  let busy = false;

  // ---- voice: sentences are sent to the voice as they are written and played in order ----
  const code = (lang || (typeof navigator !== "undefined" && navigator.language) || "en").toLowerCase().slice(0, 2);
  let lines = [];            // promises of {url} (the server's voice) or {text} (the browser's), in order
  let playing = false;
  let current = null;

  function browserSay(text) {
    return new Promise((done) => {
      if (typeof speechSynthesis === "undefined") return done();
      const u = new SpeechSynthesisUtterance(text);
      const score = (v) => (/natural|neural/i.test(v.name) ? 4 : 0) + (/online/i.test(v.name) ? 2 : 0) + (/google/i.test(v.name) ? 1 : 0);
      const voices = speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(code)).sort((a, b) => score(b) - score(a));
      if (voices.length) u.voice = voices[0];
      u.lang = code;
      u.onend = u.onerror = () => done();
      speechSynthesis.speak(u);
    });
  }

  async function playNext() {
    if (playing) return;
    playing = true;
    while (lines.length) {
      const line = await lines.shift();
      if (!root.classList.contains("kl-open")) break;
      if (line.url) {
        await new Promise((done) => {
          current = new Audio(line.url);
          current.onended = current.onerror = () => done();
          current.play().catch(() => done());
        });
        current = null;
      } else if (line.text) {
        await browserSay(line.text);
      }
    }
    playing = false;
  }

  function speak(text) {
    text = (text || "").trim();
    if (!voice || !text) return;
    lines.push(kl.speak(name, text).then((a) => (a ? { url: a.url } : { text }), () => ({ text })));
    playNext();
  }

  function stopSpeaking() {
    lines = [];
    if (current) current.pause();
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  }

  // ---- microphone: hold the button (or the key) to talk ----
  let recorder = null;
  let chunks = [];
  let recognition = null;
  let recognized = "";

  async function startRecording() {
    if (recorder || busy) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        recorder = null;
        micButton.classList.remove("kl-on");
        input.placeholder = "…";
        let text = blob.size > 2000 ? await kl.listen(blob, lang || null) : "";
        if (!text && recognition) {                     // the server heard nothing: the browser's own recognition
          await new Promise((r) => setTimeout(r, 400));
          text = recognized;
        }
        input.placeholder = "Say something…";
        if (text) say(text);
      };
      recorder.start();
      micButton.classList.add("kl-on");
      input.placeholder = "Listening…";
      const Recognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
      recognized = "";
      if (Recognition) {
        recognition = new Recognition();
        recognition.lang = lang || navigator.language || "en";
        recognition.onresult = (e) => { recognized = Array.from(e.results).map((r) => r[0].transcript).join(" ").trim(); };
        recognition.onerror = () => {};
        try { recognition.start(); } catch (e) { recognition = null; }
      }
    } catch (e) {
      recorder = null;
      micButton.title = "No microphone";
    }
  }

  function stopRecording() {
    if (recognition) { try { recognition.stop(); } catch (e) { /* already stopped */ } }
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }

  micButton.addEventListener("pointerdown", (e) => { e.preventDefault(); stopSpeaking(); startRecording(); });
  micButton.addEventListener("pointerup", stopRecording);
  micButton.addEventListener("pointerleave", stopRecording);

  async function say(message) {
    if (busy) return "";
    busy = true;
    send.disabled = true;
    if (message) log.appendChild(el("div", "kl-me", message));
    const bubble = log.appendChild(el("div", "kl-them", "…"));
    let shown = "";
    let spoken = 0;                                     // characters of the reply already sent to the voice
    const reply = await kl.chat(name, message, facts() || {}, speaker, (piece) => {
      shown += piece;
      bubble.textContent = shown;
      log.scrollTop = log.scrollHeight;
      let end = 0;
      for (const m of shown.matchAll(SENTENCE)) if (m.index + m[0].length > spoken) end = m.index + m[0].length;
      if (end) { speak(shown.slice(spoken, end)); spoken = end; }
    });
    bubble.textContent = reply || shown || "…";
    log.scrollTop = log.scrollHeight;
    if (reply && reply.startsWith(shown.slice(0, spoken))) speak(reply.slice(spoken));
    else if (reply && !spoken) speak(reply);
    // act() is instant: it returns what arrived and asks the server again, so a few polls collect the decisions.
    const collect = () => { for (const a of kl.act(name, {}, false)) if (onAction) onAction(a.tool, a.args || {}); };
    collect();
    for (const ms of [300, 800, 1600]) setTimeout(collect, ms);
    const soul = await kl.soul(name, speaker);
    mood.textContent = soul && soul.mood ? soul.mood.word : "";
    if (soul && soul.gesture) {
      log.appendChild(el("div", "kl-gesture", "— " + soul.gesture));
      log.scrollTop = log.scrollHeight;
      if (onGesture) onGesture(soul.gesture);
    }
    busy = false;
    send.disabled = false;
    input.focus();
    if (onReply) onReply(reply);
    return reply;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    input.value = "";
    if (text) say(text);
  });
  x.addEventListener("click", () => box.close());
  root.addEventListener("keydown", (e) => { if (e.key === "Escape") box.close(); e.stopPropagation(); });

  const box = {
    el: root,
    get isOpen() { return root.classList.contains("kl-open"); },
    open() {
      root.classList.add("kl-open");
      input.focus();
      if (speakFirst && !log.childElementCount) say("");
    },
    close() {
      root.classList.remove("kl-open");
      stopRecording();
      stopSpeaking();
    },
    send: say,
    /** Speaks any text in the character's voice (queued after what is being said). */
    speak,
    /** Push-to-talk from your own key or button: startListening() on press, stopListening() on release. */
    startListening: startRecording,
    stopListening: stopRecording,
  };
  return box;
}
