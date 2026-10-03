// Kinloom client for JavaScript and TypeScript games: browser (Phaser, Three.js, Babylon, PixiJS...), Node 22+, Deno, Bun.
// No dependencies. Talks JSON-RPC to `kinloom serve` (docs/protocol.md). Types: kinloom.d.ts.
//
//   import { Kinloom } from "./kinloom.js";
//   const kl = await Kinloom.connect();                     // ws://localhost:7717/ws
//   kl.handle("say", e => showSubtitle(e.thing, e.text));    // return nothing = ok, a string = refused (the AI learns why)
//   kl.handle("set", e => { game[e.thing][e.member] = e.args.value; });
//   await kl.declare(manifest);
//   // every frame:
//   kl.update("player", { health: player.health });
//   kl.frame(gameTimeSeconds);                               // effects arrive and are applied by your handlers
//   const { reply } = await kl.ask("dispatcher", "Where is the depot?", "player");

const DEFAULT_URL = "ws://localhost:7717/ws";

export class KinloomError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "KinloomError";
    this.code = code;
  }
}

export class Kinloom {
  /** Opens a connection. `options.WebSocket` replaces the global WebSocket (older Node: `ws` package). */
  static connect(url = DEFAULT_URL, options = {}) {
    const WS = options.WebSocket ?? globalThis.WebSocket;
    if (!WS) throw new KinloomError("no WebSocket implementation: pass options.WebSocket (for example from the 'ws' package)");
    return new Promise((resolve, reject) => {
      const ws = new WS(url);
      ws.onopen = () => resolve(new Kinloom(ws, options));
      ws.onerror = (e) => reject(new KinloomError(`cannot connect to ${url}: ${e?.message ?? "is kinloom serve running?"}`));
    });
  }

  constructor(ws, options = {}) {
    this._ws = ws;
    this._nextId = 1;
    this._pending = new Map();
    this._handlers = new Map();
    this._fallbackHandler = null;
    this._timeoutMs = options.timeoutMs ?? 60000;
    this._closed = false;
    ws.onmessage = (m) => this._receive(typeof m.data === "string" ? m.data : String(m.data));
    ws.onclose = () => {
      this._closed = true;
      for (const p of this._pending.values()) p.reject(new KinloomError("connection closed"));
      this._pending.clear();
    };
    ws.onerror = null;
  }

  /** Handles one kind of effect: set, invoke, create, destroy, say, media, validate (or "generated" for generator results).
   * The handler returns nothing or true (ok), false (failed), a string (refused, with that reason), or
   * {status, reason, value}; it may be async. */
  handle(kind, handler) {
    this._handlers.set(kind, handler);
    return this;
  }

  /** Handles every effect kind without its own handler. */
  onEffect(handler) {
    this._fallbackHandler = handler;
    return this;
  }

  // ---------- methods ----------

  async declare(manifest, source) {
    const r = await this._request("declare", { manifest, ...(source ? { source } : {}) });
    return r.errors ?? [];
  }

  update(thing, props) { this._notify("update", { thing, props }); }

  event(type, data = {}, { perceivedBy, time, importance } = {}) {
    this._notify("event", { type, data, ...(perceivedBy ? { perceivedBy } : {}), ...(time != null ? { time } : {}), ...(importance != null ? { importance } : {}) });
  }

  /** Fire-and-forget tick for game loops: effects come back as notifications and go to your handlers. */
  frame(time) { this._notify("tick", { time }); }

  /** Tick and wait: applies the returned effects with your handlers and returns them. */
  async tick(time) {
    const r = await this._request("tick", { time });
    const effects = r.effects ?? [];
    await Promise.all(effects.map((e) => this._apply(e)));
    return effects;
  }

  ask(role, input, from) { return this._request("ask", { role, input, ...(from ? { from } : {}) }); }
  generate(generator, context = {}) { return this._request("generate", { generator, context }); }
  media(kind, prompt, spec = {}) { return this._request("media", { kind, prompt, spec }); }
  bind(thing) { this._notify("bind", { thing }); }
  unbind(thing) { this._notify("unbind", { thing }); }
  async remove(thing) { return (await this._request("remove", { thing })).removed; }
  async save() { return (await this._request("save", {})).state; }
  load(state) { return this._request("load", { state }); }
  stats() { return this._request("stats", {}); }
  snapshot() { return this._request("snapshot", {}); }
  setMission(role, mission) { return this._request("setMission", { role, mission }); }

  /** Resolves an effect yourself (only needed when a handler returned a Promise you settle elsewhere). */
  resolve(id, status = "ok", reason, value) {
    this._notify("resolve", { id, status, ...(reason != null ? { reason } : {}), ...(value !== undefined ? { value } : {}) });
  }

  close() { this._ws.close(); }

  // ---------- internals ----------

  _send(message) {
    if (this._closed) throw new KinloomError("connection closed");
    this._ws.send(JSON.stringify({ jsonrpc: "2.0", ...message }));
  }

  _notify(method, params) { this._send({ method, params }); }

  _request(method, params) {
    const id = this._nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._pending.delete(id);
        reject(new KinloomError(`${method} timed out after ${this._timeoutMs} ms`));
      }, this._timeoutMs);
      this._pending.set(id, {
        resolve: (v) => { clearTimeout(timer); resolve(v); },
        reject: (e) => { clearTimeout(timer); reject(e); },
      });
      try { this._send({ id, method, params }); } catch (e) { this._pending.get(id)?.reject(e); this._pending.delete(id); }
    });
  }

  _receive(text) {
    let msg;
    try { msg = JSON.parse(text); } catch { return; }
    if (msg.id != null && this._pending.has(msg.id)) {
      const p = this._pending.get(msg.id);
      this._pending.delete(msg.id);
      if (msg.error) p.reject(new KinloomError(msg.error.message, msg.error.code));
      else p.resolve(msg.result ?? {});
      return;
    }
    if (msg.method === "effects") for (const e of msg.params?.items ?? []) this._apply(e);
  }

  async _apply(effect) {
    const isGenerated = effect.kind === "invoke" && effect.thing === "world" && effect.member === "generated";
    const handler = (isGenerated && this._handlers.get("generated")) || this._handlers.get(effect.kind) || this._fallbackHandler;
    let result;
    if (!handler) {
      // World facts live in Kinloom; anything else needs a handler so the AI learns it was not applied.
      result = effect.thing === "world" && effect.kind !== "say" ? { status: "ok" } : { status: "failed", reason: `the game has no handler for ${effect.kind} effects` };
    } else {
      try { result = toResult(await handler(effect)); }
      catch (e) { result = { status: "failed", reason: String(e?.message ?? e) }; }
    }
    if (!this._closed) this.resolve(effect.id, result.status, result.reason, result.value);
  }
}

function toResult(r) {
  if (r === undefined || r === null || r === true) return { status: "ok" };
  if (r === false) return { status: "failed" };
  if (typeof r === "string") return { status: "refused", reason: r };
  if (typeof r === "object" && r.status) return r;
  return { status: "ok" };
}
