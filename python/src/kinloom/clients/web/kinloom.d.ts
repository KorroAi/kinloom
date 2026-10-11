export type Example = string | number | boolean | Example[] | {
    [key: string]: Example;
};
export type Facts = Record<string, unknown>;
export interface CharacterOptions {
    /** Offline lines per event ("*" for any), with {fact} placeholders, or { event: { when: "what is happening, in words",
     * lines: [...] } } (the model reads `when`). */
    lines?: Record<string, string[] | {
        when?: string;
        lines: string[];
    }> | string[];
    /** Offline chat reply (or several, said in turn). */
    offline?: string | string[];
    /** Prepare lines now: ["overtake"] or { overtake: ["who", "whom"] }. */
    events?: string[] | Record<string, string[]>;
    /** Tools the character may use: { boost: { seconds: [0.5, 2] } }, names of the game's tools (Kinloom.tools):
     * ["open_door"], both (["open_door", { boost: {...} }]), or "all". */
    tools?: Record<string, Record<string, Example>> | Array<string | Record<string, Record<string, Example>>> | "all";
    /** Words per line / reply (default 14 / 25). */
    maxWords?: number;
    /** A text box's size in characters: the model's text never goes past it (whole sentences, else cut on a word). */
    maxChars?: number;
    /** Seconds between fresh decisions / actions. */
    every?: number;
    /** The language they write in; "auto": a conversation answers in the speaker's language. */
    language?: string;
    /** A soul: a sentence the model turns once into a full inner life (card, saved), or a card written by the game
     * ({summary, voice, backstory, values, fears, desires, secrets, goals, quirks, likes, dislikes, mood}). */
    soul?: string | boolean | Record<string, string | string[]>;
    /** { tool: feeling }: while talking, that tool is only used for speakers they feel at least this for (-1..1). */
    trust?: Record<string, number>;
    /** false: never make up names of people, places, events or numbers. */
    invent?: boolean;
    /** How they sound when they speak ("low, tired, warm"), or { id: a voice of the voice provider }. */
    voice?: string | {
        id: string;
        describe?: string;
    };
    /** A group (faction, team, village) for reputation. */
    group?: string;
}
export interface Action {
    tool: string;
    args: Record<string, any>;
}
/** A picture the model looks at: a Blob, canvas.toDataURL(), an ArrayBuffer, a typed array or base64. */
export type Picture = Blob | ArrayBuffer | ArrayBufferView | string;
/** The game's own rules for an answer: null, "" or true accept it; a reason (text) or false refuses it. */
export type Check = (answer: any) => string | boolean | null | undefined;
/** The game's rules for an action: (tool, args) -> "" or why it is refused. */
export type ActCheck = (tool: string, args: Record<string, any>) => string | boolean | null | undefined;
/** What a game's check returned, as why it refuses ("" when it accepts): null, "" or true accept; false refuses. */
export declare function reason(verdict: unknown): string;
/** What a character remembers when the game refused one of its actions (act's check). */
export declare function refusedNote(tool: string, args: unknown, why: string): string;
/** The elements of the first JSON list in a text that arrives in pieces (a list, or a list value of the top object:
 * {"items": [...]}), each one as soon as it is complete. feed(piece) returns the texts of the new elements. */
export declare class Items {
    private buf;
    private i;
    private stack;
    private str;
    private esc;
    private level;
    private start;
    private done;
    feed(piece: string): string[];
    private static emit;
}
export interface Prepared {
    ready: boolean;
    waiting: number;
    online: boolean;
}
/** A sense: [lo, hi] a number, true a flag, ["calm", "angry"] one of these. */
export type SenseExample = [number, number] | boolean | string[];
/** A mind rule for one action: ["hp low", "dist below 12"] or { score, when, args }. */
export type MindRule = string | string[] | {
    score?: number;
    when?: string | string[];
    args?: Record<string, Example>;
};
export interface MindOptions {
    senses: Record<string, SenseExample>;
    actions: Record<string, Record<string, Example>>;
    /** The offline mind: { retreat: ["hp low"], charge: { score: 0.5, when: ["dist below 15"], args: { speed: "dist high" } } }. */
    rules?: Record<string, MindRule> | null;
    /** Temperaments in a crowd (each unit keeps one). */
    variants?: number;
    /** Seconds between learning steps when you call reward (0: never). */
    learn?: number;
}
export interface Thought {
    action: string | null;
    args: Record<string, any>;
    variant: number;
}
export interface EventOptions {
    by?: string;
    seenBy?: string[];
    tag?: string;
    impact?: number;
}
export interface Shared {
    from: string;
    to: string;
    text: string;
    tag: string | null;
}
/** A compiled rule: [sense, op, p1, p2] (arguments add lo, hi, whole). */
type Rule = [string, string, any, number, ...any[]];
interface Program {
    [action: string]: {
        score: number;
        when: Rule[];
        args: Record<string, any>;
    };
}
export interface CompiledMind {
    name: string;
    version: number;
    order: string[];
    stick: number;
    variants: Program[];
    ids: number[] | null;
}
type Reply = Record<string, any>;
/** How a Kinloom is made. Native (the SDK calls the model): provider / offline / brain. Relay: url (+ token). */
export interface KinloomOptions {
    /** A relay: `kinloom serve` (or any server speaking /v1). Default http://127.0.0.1:7717 when no provider is given. */
    url?: string;
    /** One per player, match or save. With a relay token and no session given, one id per install (kept in
     * localStorage in a browser) instead of "default", which every player would share. */
    session?: string;
    /** The relay's player token (kinloom serve --token / --player-token). */
    token?: string;
    timeoutMs?: number;
    /** The model, called from this process: { url, key, model } (OpenAI-compatible), { kind: "anthropic", key, model },
     * a list of them (a dead key hands over to the next), "auto" (Node, Deno, Bun: the keys in the environment), a
     * function (kind, system, user) => answer (tests), or { script: {task: answer} }. */
    provider?: ProviderOption;
    /** No model at all: every call answers at once from your lines, replies and examples. */
    offline?: boolean;
    /** A cheaper model for what players do not wait for: { background: "a-model-id" } (same endpoint and key) or a provider
     * spec; { chat: ... } for conversations. */
    models?: Record<string, string | ProviderOption> | null;
    /** "everyone" | "teen" | "mature": characters and content stay within it (a rule in every prompt). */
    rating?: "everyone" | "teen" | "mature" | null;
    /** Speech and transcription: { url, key, speakModel, listenModel } (OpenAI-compatible), or "auto". */
    voice?: VoiceSpec | OpenAIVoice | "auto" | null;
    /** Where memory is kept: "path/file.json" (Node, Deno, Bun), "localStorage:key" (browsers), or {load, save}. */
    memory?: string | MemoryStore | null;
    /** kinloom.json's settings as an object (characters, lore, tools, language, calls_per_minute, prices,
     * banned_words, max_cost_per_hour...), or the path of the file (Node). */
    config?: Record<string, any> | string | null;
    language?: string;
    callsPerMinute?: number;
    /** Dollars per million tokens {input, cached_input, output, source}: costs in stats() and the cost caps. */
    prices?: Record<string, any>;
    /** text => false blocks a model's text (the offline answer is used). */
    contentFilter?: (text: string) => boolean;
    /** Seconds a model call may take. */
    callTimeout?: number;
    /** Share one brain between sessions (players): new Kinloom({ brain: kl.brain, session: "p2" }). */
    brain?: Brain;
}
export declare class Kinloom {
    url: string;
    session: string;
    token: string;
    timeoutMs: number;
    /** The native brain (null in relay mode). */
    brain: Brain | null;
    /** Optional: called with every line said. */
    onSaid: ((character: string, text: string) => void) | null;
    private chars;
    private declaring;
    private decisions;
    private actions;
    private sources;
    private lastDo;
    private decideRefused;
    private decideOk;
    private remarkTurns;
    private downUntil;
    private failures;
    private limitedUntil;
    private warned;
    private minds;
    private units;
    private rewards;
    private rewardAt;
    private flushing;
    private gameTools;
    /** Native when provider, offline or brain is given; else a relay at url (default: a local `kinloom serve`). */
    constructor(options?: KinloomOptions);
    /** Another player's or match's view: the same model and budget, separate memory, banks and decisions. */
    withSession(session: string): Kinloom;
    /** True when a model answers (native: a provider is set). */
    get online(): boolean;
    /** Calls, failures, tokens, offline answers, cost (with prices), average latency (native). */
    stats(): Record<string, any> | null;
    /** What Kinloom did lately: calls, lines, replies, refusals, "empty" answers (native). */
    journal(n?: number): Record<string, any>[];
    /** listener(entry) for everything Kinloom does (native). Returns the listener, for off(). */
    on(listener: (entry: Record<string, any>) => void): (entry: Record<string, any>) => void;
    off(listener: (entry: Record<string, any>) => void): void;
    /** Saves memory now and stops background work (native). */
    close(): void;
    character(name: string, personality?: string, options?: CharacterOptions): this;
    /** A line in character with the real facts filled in (instant when prepared lines exist). fresh: a line the model
     * writes now (slower); maxChars: the size of the box it goes in this time. */
    say(name: string, event: string, facts?: Facts, { fresh, maxChars }?: {
        fresh?: boolean;
        maxChars?: number;
    }): Promise<string>;
    /** Where name's last line or reply came from: "model" (written now), "prepared" (written earlier by the model),
     * "offline" (your own lines and replies), or "" before the first one. */
    source(name: string): string;
    /** A conversation reply in character, grounded in the facts, their memory, mood and what they feel for the speaker.
     * message "": the speaker came up to them, they speak first. onPiece(text): the reply as it is written (streaming).
     * What they decide to do while talking comes out of act(name, {}, false), at once.
     * image: a picture with the message (a Blob, canvas.toDataURL(), an ArrayBuffer, base64), for a model that sees. */
    chat(name: string, message: string, facts?: Facts, speaker?: string, onPiece?: ((text: string) => void) | null, image?: Picture | null, { check }?: {
        check?: Check | null;
    }): Promise<string>;
    private chatOnce;
    /** A short line from someone in the crowd about what just happened (no character to declare), ~1 s.
     * who: who says it ("an old fisherman"); offline: your own lines ({fact} placeholders), said in turn without a model. */
    remark(about: string, { who, facts, offline, maxChars }?: {
        who?: string;
        facts?: Facts;
        offline?: string | string[] | null;
        maxChars?: number;
    }): Promise<string>;
    /** Who the character is and feels: {card, mood: {word, level}, bonds: {speaker: {talks, feeling}}, memories,
     * conversation (with speaker)}. null when the server is not running. */
    /** World facts every character takes as true and never contradicts (one per item). Returns how many were kept
     * (0 when the server is not running). */
    lore(lines: string[]): Promise<number>;
    soul(name: string, speaker?: string): Promise<Reply | null>;
    /** What the player could say now to name, for games without a keyboard: one reply per example, in its order, each
     * keeping that example's intent, written for this moment ("Ask about her past" -> "So, the king's sword?"). The
     * examples are the offline answer, so index i always means the same choice. */
    suggest(name: string, examples: string[], speaker?: string, facts?: Facts, { check }?: {
        check?: Check | null;
    }): Promise<string[]>;
    /** What the game decides happens in name's next reply ("admit you were in the office at 12:30"): the model says it
     * in the character's voice, even a secret of their card. Used by the next chat only; "" takes it back. */
    steer(name: string, text: string): Promise<void>;
    /** A short exchange between two characters (one model call), remembered by both: [{who, text}] ([] offline). */
    converse(a: string, b: string, about?: string, turns?: number): Promise<{
        who: string;
        text: string;
    }[]>;
    /** A snapshot for a debug overlay: each character's mood, feelings, last words, memories and waiting actions, each
     * mind's generation; null when a relay cannot be reached. */
    inspect(): Promise<Reply | null>;
    /** Everything Kinloom knows about this session (memories, feelings, bonds, moods, conversations, lore, learned minds)
     * as one text for the game's own save slot ("" when a relay cannot be reached). */
    save(): Promise<string>;
    /** Puts back what save() gave (this session's state is replaced). */
    load(data: string): Promise<boolean>;
    private stream;
    /** Instant: the latest decision shaped like `choices` (refreshed in the background): an object of choices gives an
     * object, a list of options gives one of them. */
    decide<T extends Record<string, Example> | Example[]>(name: string, situation: Facts, choices: T, { check }?: {
        check?: Check | null;
    }): T extends Example[] ? any : Record<keyof T, any>;
    private decided;
    /** Instant: tool calls chosen since the last call (on their own, or while talking), as [{tool, args}].
     * think false: only what they decided while talking (no model call of their own). */
    act(name: string, situation?: Facts, think?: boolean, { check }?: {
        check?: ActCheck | null;
    }): Action[];
    /** How often decide/act ask: at once in native mode (the brain keeps its own pace); through a relay, a quarter of
     * the character's `every` (8 s by default: every 2 s), never more than 4 times a second. */
    private pollMs;
    private actionsOf;
    /** Content shaped like the example (which is also the offline answer). count > 0 gives a list; instant: from a ready
     * pool; image: a picture the model looks at (a Blob, a data: URL, an ArrayBuffer, base64).
     * check(answer): the game's own rules. null, "" or true accept the answer; a reason (text) or false refuses it: the
     * model hears the reason once, then the offline answer is used (with count/instant, refused items are replaced).
     * offline: the game's own offline answer, shaped like the example (one item of it with count). each(item): every
     * item of a list answer as soon as it is ready (native: as the model writes it), refused items left out. */
    create<T extends Example>(what: string, example: T, { context, count, instant, image, check, offline, each }?: {
        context?: Facts;
        count?: number;
        instant?: boolean;
        image?: Picture | null;
        check?: Check | null;
        offline?: unknown;
        each?: ((item: any) => void) | null;
    }): Promise<any>;
    /** One create request, then the game's check: a list item by item (in native mode as the model writes, each item
     * handed to each() at once), anything else whole (refused: sent back once with its reason). */
    private created;
    /** What the game can do, declared once: {open_door: {door: "north"}, give: {item: "sword"}}. Characters use them by
     * name: character(name, "", { tools: ["open_door"] }) or tools: "all"; act() returns the calls. Returns the names. */
    tools(tools: Record<string, Record<string, Example>>): Promise<string[]>;
    /** For a loading screen: waits (up to timeout seconds) until what Kinloom writes ahead is ready (soul cards, first
     * greetings, line banks): {ready, waiting, online}. Offline: ready at once. */
    prepare(timeout?: number): Promise<Prepared>;
    /** text said aloud in name's voice (null: a narrator voice), or null when no voice can speak (show the text). */
    speak(name: string | null, text: string): Promise<Spoken | null>;
    /** What someone said in a recording (Blob, ArrayBuffer, typed array or base64): the text, "" when nothing. */
    listen(audio: Blob | ArrayBuffer | ArrayBufferView | string, language?: string | null): Promise<string>;
    /** Something happened; the characters named in `about` (or in the text) remember it. options: by (who did it),
     * seenBy (only these witnesses know), tag (for knows), impact (-1..1: how it changes the witnesses' opinion of `by`). */
    event(text: string, about?: string[], { by, seenBy, tag, impact }?: EventOptions): Promise<Reply | null>;
    remember(name: string, note: string): void;
    /** A live snapshot every call can see. */
    state(values: Facts): void;
    /** Declares a mind (see MindOptions). think() runs it locally; the server's model writes variants and learns. */
    mind(name: string, personality: string | undefined, { senses, actions, rules, variants, learn }: MindOptions): this;
    /** Instant, never calls a model: {action, args, variant} for this unit (who: a stable id per unit). */
    think(name: string, senses?: Facts, who?: string): Thought;
    /** How well the unit's last choice went (higher is better). Rewarded minds learn (in `kinloom serve`, key or not).
     * done: the unit's fight, life or round is over (its next rewards start a new story). */
    reward(who: string, value: number, done?: boolean): boolean;
    /** Sends pending rewards now; resolves once everything reported so far is sent. */
    flush(): Promise<void>;
    private flushNow;
    /** How a mind is doing (variants, mean rewards, generations), or null offline. */
    report(name: string): Promise<Reply | null>;
    private refreshMind;
    /** a and b tell each other what they know. Returns [{from, to, text, tag}] ([] offline). */
    meet(a: string, b: string): Promise<Shared[]>;
    /** Rounds of talk inside a group (or among every character). */
    spread(group?: string | null, rounds?: number): Promise<Shared[]>;
    /** Whether name knows about the event tagged `tag` (false offline). */
    knows(name: string, tag: string): Promise<boolean>;
    /** What a thinks of b, -1..1 (0 offline). */
    opinion(a: string, b: string): Promise<number>;
    /** Moves a's opinion of b by change; returns the new opinion (0 offline). */
    feel(a: string, b: string, change: number): Promise<number>;
    /** A group's average opinion of target (0 offline). */
    reputation(target: string, group: string): Promise<number>;
    status(): Promise<Reply>;
    private offlineLine;
    /** Offline answers for a while: 2 s, then 4, 8, at most 10 while the server is still not there. */
    private down;
    private redeclare;
    private fire;
    private post;
    /** Relay: waits (5 s at most) for the declarations of the characters a call names (all of them for prepare, save and
     * inspect, which are about every character), so the server never answers it without their soul and tools. */
    private ready;
    private request;
    /** A relay that said no: told once per verb and status; HTTP 429 (this player is over the relay's rate limit) keeps
     * that verb offline for Retry-After seconds (5 by default), without taking the server for gone. */
    private refusedBy;
    /** The native brain answers what the relay would (the same JSON, verb by verb). */
    private local;
}
/** The offline answer for an example: first option, middle of a range, the example itself. */
/** A spoken line: audio (base64 WAV), url (a data: URL to play), format, seconds, text. */
export interface Spoken {
    audio: string;
    url: string;
    format: string;
    seconds: number;
    text: string;
}
/** A recording as base64, from a Blob, an ArrayBuffer, a typed array, a data: URL or base64 text. */
export declare function toBase64(audio: Blob | ArrayBuffer | ArrayBufferView | string | null | undefined): Promise<string>;
export declare function defaultOf(example: any): any;
/** Replaces {name} placeholders with facts, numbers formatted for people. */
export declare function fill(template: string, facts: Facts): string;
/** FNV-1a 32-bit over UTF-8: which variant a unit gets, identical in every client. */
export declare function fnv1a(text: string): number;
type Kind = ["flag"] | ["range", number, number] | ["options", string[]];
/** "hp low", "dist below 12", "armed", "not armed", "mood is angry" -> [sense, op, p1, p2], or null. */
export declare function parseRule(text: unknown, senses: Record<string, Kind>): Rule | null;
export declare function ruleValue(rule: Rule, senses: Facts): number;
/** The offline mind: the game's rules compiled like the server does (no rules: every action scores 1). */
export declare function compileMind(decl: Record<string, any>): CompiledMind;
/** One decision from a compiled mind. units: who -> last action (hysteresis). */
export declare function runMind(compiled: CompiledMind, senses: Facts, who: string, units: Map<string, string>): Thought;
/** "%.<f>f" % x (Python), sign: "+" for "%+.<f>f". */
export declare function pyFixed(x: number, f: number, sign?: string): string;
/** round(x, n) (Python: the double nearest the correctly rounded decimal, ties to even). */
export declare function pyRound(x: number, n?: number): number;
/** "%g" % x */
export declare function pyG(x: number, precision?: number): string;
/** repr(float) / str(float): the shortest digits, in Python's layout. Whole numbers print as integers (JavaScript
 * cannot tell 2.0 from 2). */
export declare function pyNum(x: number): string;
/** json.dumps(value, ensure_ascii=ascii, sort_keys=sort, default=str): Python's spacing and number spelling. */
export declare function pyDumps(v: unknown, ascii?: boolean, sort?: boolean): string;
/** SHA-1 of UTF-8 text, hex (voices and soul keys: the same in every SDK). */
export declare function sha1(text: string): string;
/** One tidy line: control characters (terminal escapes, NUL...) removed, whitespace collapsed. */
export declare function cleanText(text: unknown): string;
export declare const CUT = "the answer was cut off before its end: write it shorter and complete";
/** True when a model answer stops in the middle of its JSON (the token limit): no complete JSON before that. */
export declare function cutOff(text: unknown): boolean;
/** The first JSON object or array in a model answer, or null. Never throws. */
export declare function findJson(text: unknown, limit?: number): any;
export declare class Shape {
    kind: string;
    example: any;
    info: Record<string, any>;
    constructor(kind: string, example: any, info?: Record<string, any>);
    static of(example: any, depth?: number): Shape;
    default(): any;
    /** [ok, cleaned value, error]. Numbers are clamped into ranges; text is cleaned; object extras are dropped. */
    check(value: any, path?: string): [boolean, any, string | null];
    /** Finds the JSON in a model answer (code fences, chatter around it) and checks it. */
    parse(text: string): [boolean, any, string | null];
    describe(indent?: string): string;
    /** A stable key for caches (same shape, same key). */
    signature(): string;
}
export declare const CARD_EXAMPLE: Record<string, any>;
/** A clean card from anything: known fields only, bounded, never the example's placeholder texts. */
export declare function soulCard(value: any, seed?: string): Record<string, any>;
/** The card as lines for the system prompt. */
export declare function describeCard(c: Record<string, any>): string[];
/** The text up to its last finished sentence ("" when none is finished). */
export declare function wholeSentences(text: string): string;
/** The text up to the end of the sentence that reaches `words` words (chars: a text box's size). */
export declare function capText(text: string, words: number, chars?: number | null): string;
/** At most `chars` characters: the whole sentences that fit, else the first one cut on a word with "…". */
export declare function fitChars(text: string, chars: number | null): string;
/** Streams a reply up to the end of the sentence that reaches `words` words (and, with chars, that fits). */
export declare class Cap {
    words: number;
    chars: number | null;
    shown: string;
    done: boolean;
    text: string;
    pos: number;
    constructor(words: number, chars?: number | null);
    feed(piece: string): string;
    private sentence;
    finish(): string;
}
/** Removes sentences that only narrate the gesture or a habit. [what is said, the first narrated action or ""]. */
export declare function dropNarrated(said: string, gesture: string, habits?: string[]): [string, string];
/** [what is said out loud, the inner part ({} when none)]. */
export declare function splitReply(text: string): [string, Record<string, any>];
/** Holds back the first words of a streamed reply until they are known to be in character. */
export declare class Guard {
    bad: RegExp;
    hold: number;
    text: string;
    shown: number;
    blocked: boolean;
    constructor(bad: RegExp, hold?: number);
    feed(piece: string): string;
    finish(): string;
}
/** Streams only the spoken part. */
export declare class Splitter {
    text: string;
    start: number;
    shown: number;
    done: boolean;
    first: boolean;
    feed(piece: string): string;
    /** [said, inner, the spoken text still to show]. */
    finish(): [string, Record<string, any>, string];
}
/** Drops stage directions (*smiles*, (sighs), [pause]) from a streamed reply, as the finished reply drops them. */
export declare class Unstage {
    buf: string;
    held: string | null;
    pending: string;
    skip: boolean;
    started: boolean;
    private emit;
    feed(piece: string, final?: boolean): string;
    finish(): string;
}
/** Drops what a character keeps saying, sentence by sentence, as the reply streams. */
export declare class Echo {
    before: string[][];
    seen: Set<string>;
    buf: string;
    kept: number;
    dropped: string[];
    short: Map<string, string[]>;
    fresh: number;
    echoed: number;
    early: number;
    constructor(before?: string[]);
    private repeat;
    private pass;
    get stale(): boolean;
    private newStart;
    feed(piece: string): string;
    private freshOne;
    finish(): string;
}
/** The whole-text version of Echo: [what is left, stale]. */
export declare function dropEchoes(text: string, before: string[]): [string, boolean];
/** The secret this text gives away, or null. */
export declare function leaks(text: string, secrets: string[], pub?: string[], share?: number, asked?: string): string | null;
/** The text without the sentences that give a secret away. */
export declare function keepSecrets(text: string, secrets: string[], pub?: string[], asked?: string): string;
/** What a character keeps saying: [phrases, opener]. */
export declare function worn(replies: string[], recent?: number): [string[], string];
/** What changed inside, checked: {mood, intensity, feel, remember, self, gesture, do}. */
export declare function innerOfReply(data: any): Record<string, any>;
/** [word, level] after fading. */
export declare function moodNow(mood: {
    word: string;
    level: number;
    t: number;
} | null | undefined, now: number, baseline: string | null | undefined): [string, number];
/** How strongly a mood is felt, said before it: "very angry", "quite curious", "a little tired". */
export declare function strength(level: number): string;
export declare function ago(seconds: number): string;
/** What a prompt needs to know about a character. */
interface Persona {
    name: string;
    personality: string;
    line_words: number;
    reply_words: number;
    max_chars: number | null;
    invent: boolean;
    tools: Record<string, [Shape | null, string]>;
    trust: Record<string, number>;
}
export declare const prompts: {
    writeIn(language: string): string;
    size(c: Persona): string;
    head(task: string, c: Persona, language: string): string;
    /** obj as JSON in at most `limit` characters. An object too long keeps every key, in its order (the first ones
     * matter most): the last values are shortened first, then replaced by "(cut)". Anything else is cut. */
    clip(obj: unknown, limit?: number): string;
    /** A value made shorter for a context that is too long: long text cut, long lists trimmed, big objects counted. */
    short(v: unknown): unknown;
    /** Someone in the crowd (no declared character) says one line about what just happened. */
    remarkSystem(who: string, language: string, chars?: number | null): string;
    remarkUser(about: string): string;
    feeling(v: number): string;
    context(notes: string[], state: unknown, feelings?: Record<string, number> | null): string;
    factsBlock(facts: Record<string, unknown> | null): string;
    situationBlock(situation: unknown): string;
    contextBlock(context: unknown): string;
    historyBlock(history: [string, string][], limit?: number): string;
    wornBlock(phrases: string[], opener: string): string;
    boxBlock(chars: number | null): string;
    pictureBlock(pictures: number, speaker?: string | null): string;
    messageBlock(speaker: string, message: string): string;
    linesSystem(c: Persona, event: string, placeholders: string[] | null, n: number, language: string, chars?: number | null): string;
    lineSystem(c: Persona, event: string, placeholders: string[], language: string, chars?: number | null): string;
    decideSystem(c: Persona, shape: Shape, language: string): string;
    toolLines(c: Persona, trust: boolean): string[];
    actSystem(c: Persona, language: string): string;
    createSystem(what: string, shape: Shape, language: string): string;
    createManySystem(what: string, shape: Shape, count: number, language: string): string;
    chatSystem(c: Persona, language: string, cardLines?: string[], lore?: string[], task?: string): string;
    deedsSystem(c: Persona): string;
    deedsUser(name: string, speaker: string, message: string, reply: string): string;
    soulSystem(c: Persona, language: string): string;
    soulUser(seed: string, lore?: string[]): string;
    recollectSystem(c: Persona, language: string): string;
    bondBlock(speaker: string, bond: {
        talks: number;
    } | null, since: string, feelingValue: number, known: string[], moodWord: string, moodStrength: string, who?: string, secrets?: boolean, secretTrust?: number): string;
    /** The game refused the last answer (create's check): its reason, once, with the answer it refused. */
    refusedBlock(refused: {
        answer: unknown;
        why: string;
    } | null): string;
    /** What the game decided for this reply (steer): the model makes it happen, in the character's words. */
    steerBlock(steer: string): string;
    repair(error: string): string;
    stayInCharacter(name: string): string;
    sayNew(): string;
    keepSecret(name: string, speaker: string): string;
    numbersRepair(): string;
    senseLine(name: string, kind: SenseKind): string;
    actionLine(name: string, args: Record<string, Shape>): string;
    mindSystem(decl: Declaration, language: string): string;
    mindsUser(decl: Declaration, count: number, rules: unknown): string;
    mindLearnUser(best: unknown, bestMean: number, worst: unknown, worstMean: number, samples: [Record<string, unknown>, string, number][], nBest: number, nWorst: number, evidence?: [number, string, string, number, number][] | null): string;
    impactSystem(language: string): string;
    impactUser(text: string, by: string, people: [string, string, number][]): string;
    ratingLine(rating: string | null): string;
    suggestSystem(c: Persona, n: number, speaker: string): string;
    suggestUser(history: [string, string][], facts: Record<string, unknown> | null, examples: string[]): string;
    who(c: Persona): string;
    converseSystem(a: Persona, b: Persona, turns: number, language: string, lore?: string[]): string;
    converseUser(a: string, ctxA: string, b: string, ctxB: string, about: string): string;
};
/** Where memory is kept between runs: a file (Node, Deno, Bun), localStorage (browsers), or your own. */
/** Where memory lives. aside(): moves an unreadable copy out of the way and says where (optional). */
export interface MemoryStore {
    load(): string | null;
    save(text: string): void;
    aside?(): string | null;
}
export type Note = {
    t: number;
    text: string;
    importance: number;
    [k: string]: any;
};
export declare class Memory {
    store: MemoryStore | null;
    clock: () => number;
    private notesBy;
    private extra;
    private timer;
    private dirty;
    /** What went wrong reading the stored memory, if anything (the brain journals it). */
    problem: string;
    constructor(store?: MemoryStore | null, clock?: () => number);
    /** Loads what can be trusted, entry by entry: one bad note never costs the rest. A store that cannot be read at all
     * is kept aside (memory.json.corrupt-<time> for a file) before anything overwrites it. */
    private read;
    add(session: string, scope: string, text: string, importance?: number, meta?: Record<string, any>): void;
    notes(session: string, scope: string): Note[];
    /** Removes the latest note with exactly this text (a reply the game refused is not remembered). */
    takeBack(session: string, scope: string, text: string): void;
    annotate(session: string, scope: string, eid: string, meta: Record<string, any>): void;
    get(section: string, key: string): any;
    put(section: string, key: string, value: any): void;
    all(session: string, scope: string): string[];
    delete(section: string, key: string): void;
    /** The keys of a section ("session/name" for learned minds). */
    keys(section: string): string[];
    /** {scope: [notes]} of one session (copies): what a save slot keeps. */
    sessionNotes(session: string): Record<string, Note[]>;
    /** The session's notes become these: a save slot loaded. */
    replaceSession(session: string, notes: Record<string, any>): void;
    /** The k most useful notes: 0.45 importance + 0.35 recency + 0.2 overlap with the query. */
    recall(session: string, scopes: string[], query?: string, k?: number, personal?: boolean): string[];
    private changed;
    save(): void;
}
/** Replaces {name} placeholders with facts, numbers formatted for people. */
export declare function fillLine(template: string, facts: Record<string, unknown>): string;
export declare function formatValue(v: unknown): string;
type SenseKind = ["flag"] | ["range", number, number] | ["options", string[]];
/** A small seeded random generator (learning without a model is reproducible per mind). */
export declare class Rand {
    private s;
    constructor(seed: number);
    random(): number;
    uniform(a: number, b: number): number;
    randrange(n: number): number;
    choice<T>(items: T[]): T;
}
export declare class Declaration {
    name: string;
    personality: string;
    senses: Record<string, SenseKind>;
    actions: Record<string, Record<string, Shape>>;
    order: string[];
    variants: number;
    rules: any;
    ruleErrors: string[];
    offline: Record<string, any>;
    constructor(name: string, personality?: string, senses?: unknown, actions?: unknown, rules?: any, variants?: number);
}
/** [compiled rule, null] or [null, reason]. */
export declare function strictRule(text: unknown, senses: Record<string, SenseKind>): [any[] | null, string | null];
/** [clean program with every declared action, errors] or [null, errors]. */
export declare function validateProgram(program: any, decl: Declaration): [Record<string, any> | null, string[]];
export declare class Mind {
    decl: Declaration;
    variants: Record<string, any>[];
    version: number;
    units: Map<string, string>;
    private cache;
    constructor(decl: Declaration, variants?: Record<string, any>[] | null);
    setVariant(index: number, program: Record<string, any>): void;
    setVariants(programs: Record<string, any>[]): void;
    compiled(): any;
    think(senses: any, who?: string | null): {
        action: string;
        args: Record<string, any>;
        variant: number;
    };
    explain(senses: any, who?: string | null): Record<string, any>;
}
/** A small random change (score, threshold, direction, a rule added or dropped, an argument). Always valid. */
export declare function mutate(program: Record<string, any>, decl: Declaration, rnd: Rand): Record<string, any>;
/** Where an action did better or worse than the others: [z, action, rule, advantage, n], strongest first. */
export declare function evidence(decl: Declaration, samples: [any, string, number][], minN?: number, top?: number): [number, string, string, number, number][];
/** A change the data supports, or null. */
export declare function propose(program: Record<string, any>, decl: Declaration, samples: [any, string, number][], rnd: Rand, minZ?: number): Record<string, any> | null;
export interface ModelReply {
    ok: boolean;
    text: string;
    error: string | null;
    input: number;
    cached: number;
    output: number;
    latency: number;
    cut: boolean;
    blind: boolean;
}
/** A picture for a model: its type and base64 data. */
export interface ModelPicture {
    mime: string;
    b64: string;
    bytes: number;
}
export interface CompleteOptions {
    json?: boolean;
    maxTokens?: number;
    temperature?: number;
    timeout?: number;
    onText?: ((piece: string) => void) | null;
    images?: ModelPicture[] | null;
}
/** A model: a provider Kinloom built, or your own object with complete(). */
export interface Provider {
    name: string;
    model: string;
    baseUrl?: string;
    local?: boolean;
    patient?: boolean;
    switched?: string[];
    complete(system: string, user: string, options: CompleteOptions): Promise<ModelReply>;
    warm?(): Promise<void>;
    describe?(): string;
}
/** Any chat-completions endpoint: OpenAI, OpenRouter, DeepSeek, Groq, Gemini, Mistral, Together, xAI, Ollama, LM Studio... */
export declare class OpenAICompatible implements Provider {
    name: string;
    model: string;
    baseUrl: string;
    key: string;
    deepseek: boolean;
    private adapt;
    private effort;
    static EFFORTS: string[];
    static REFUSED: string[];
    static BLIND: string[];
    constructor(baseUrl: string, key: string, model: string, name?: string, deepseek?: boolean);
    get local(): boolean;
    get patient(): boolean;
    describe(): string;
    private body;
    private learn;
    warm(): Promise<void>;
    private headers;
    complete(system: string, user: string, o?: CompleteOptions): Promise<ModelReply>;
    private stream;
}
/** Claude through the Messages API. */
export declare class Anthropic implements Provider {
    name: string;
    model: string;
    baseUrl: string;
    key: string;
    constructor(key: string, model?: string, baseUrl?: string);
    get local(): boolean;
    get patient(): boolean;
    describe(): string;
    complete(system: string, user: string, o?: CompleteOptions): Promise<ModelReply>;
}
/** Tests and replays: fn(kind, system, user) -> text or null (null = a failed call); or a script {task: answer | [answers]}. */
export declare class Scripted implements Provider {
    name: string;
    model: string;
    fn: (kind: string, system: string, user: string) => string | null | Promise<string | null>;
    constructor(fn: ((kind: string, system: string, user: string) => string | null | Promise<string | null>) | Record<string, unknown>, name?: string);
    describe(): string;
    complete(system: string, user: string, o?: CompleteOptions): Promise<ModelReply>;
}
/** Several providers in order: a dead key (401, 402, 403) hands over to the next one for good. */
export declare class Fallback implements Provider {
    current: Provider;
    rest: (() => Provider | null)[];
    switched: string[];
    constructor(first: Provider, rest: (() => Provider | null)[]);
    get name(): string;
    get model(): string;
    get baseUrl(): string;
    get local(): boolean;
    get patient(): boolean;
    describe(): string;
    warm(): Promise<void>;
    complete(system: string, user: string, o?: CompleteOptions): Promise<ModelReply>;
}
/** What the game gives as `provider`: a ready provider, a function or script (tests), "auto", or a description
 * {url, key, model, kind: "openai" | "anthropic", name}. A list: tried in order (dead keys hand over). */
export type ProviderOption = Provider | "auto" | null | ProviderSpec | ProviderSpec[] | ((kind: string, system: string, user: string) => string | null | Promise<string | null>);
export interface ProviderSpec {
    url?: string;
    key?: string;
    model?: string;
    kind?: "openai" | "anthropic" | "deepseek" | "openrouter";
    name?: string;
    script?: Record<string, unknown>;
}
/** The same option for the same seed (voices per character that stay the same). */
export declare function stablePick<T>(options: T[], seed: string): T | null;
export interface VoiceSpec {
    url?: string;
    key?: string;
    speakModel?: string | null;
    listenModel?: string | null;
    voices?: string[];
    name?: string;
}
export declare class OpenAIVoice {
    baseUrl: string;
    key: string;
    speakModel: string | null;
    listenModel: string | null;
    voices: string[];
    name: string;
    constructor(spec: VoiceSpec);
    get canSpeak(): boolean;
    get canListen(): boolean;
    describe(): string;
    private headers;
    speak(text: string, voice: Record<string, any>, timeout?: number): Promise<[Uint8Array | null, string | null]>;
    listen(data: Uint8Array, fmt: string | null, language?: string | null, timeout?: number): Promise<[string | null, string | null]>;
}
/** An error the game made in a call (a wrong type, a missing field): the HTTP server answers 400 with it. */
export declare class KinloomError extends Error {
    status: number;
    constructor(status: number, message: string);
}
export declare function eventKey(event: unknown): string;
interface Act {
    tool: string;
    args: Record<string, any>;
    taken: boolean;
}
/** What say() and chat() give back: the text, where it came from, and (chat) the actions decided in it. */
export interface Said {
    text: string;
    source: "model" | "prepared" | "offline";
    actions: Act[];
}
export declare class Character implements Persona {
    name: string;
    group: string | null;
    personality: string;
    lines: Record<string, string[]>;
    when: Record<string, string>;
    offlines: string[];
    offline: string;
    offlineTurn: number;
    events: Record<string, string[] | null>;
    max_words: number | null;
    line_words: number;
    reply_words: number;
    max_chars: number | null;
    every: number;
    language: string | null;
    toolRefs: string[];
    ownTools: Record<string, [Shape | null, string]>;
    tools: Record<string, [Shape | null, string]>;
    invent: boolean;
    trustWanted: Record<string, number>;
    trust: Record<string, number>;
    warmth: number;
    secret_trust: number;
    warm_up: number;
    card: Record<string, any> | null;
    cardReady: boolean;
    soulKey: string | null;
    voiceId: string | null;
    voice: string;
    constructor(name: unknown, personality?: unknown, lines?: any, offline?: any, events?: any, tools?: any, maxWords?: any, every?: any, language?: any, group?: any, trust?: any, invent?: any, voice?: any, maxChars?: any, warmth?: any, secretTrust?: any, warmUp?: any);
    moment(event: string): string;
}
export interface BrainOptions {
    provider?: ProviderOption;
    memory?: string | MemoryStore | null;
    language?: string | null;
    callsPerMinute?: number | null;
    prices?: Record<string, any> | null;
    callTimeout?: number;
    contentFilter?: ((text: string) => boolean) | null;
    voice?: OpenAIVoice | VoiceSpec | "auto" | null;
    config?: Record<string, any> | string | null;
    /** {chat | background: a model id on the same endpoint, or a provider}: a cheaper model for what players do not wait for. */
    models?: Record<string, string | ProviderOption> | null;
    /** "everyone" | "teen" | "mature": a rule in every prompt. */
    rating?: string | null;
}
export declare class Brain {
    models: Record<string, Provider>;
    rating: string | null;
    provider: Provider | null;
    voice: OpenAIVoice | null;
    language: string;
    voiceLanguage: string | null;
    limit: number;
    prices: Record<string, any> | null;
    banned: RegExp | null;
    contentFilter: ((text: string) => boolean) | null;
    memory: Memory;
    callTimeout: number;
    hedgeAfter: number;
    stallAfter: number;
    innerGrace: number;
    maxCostPerHour: number | null;
    maxCostPerDay: number | null;
    listeners: ((entry: Record<string, any>) => void)[];
    private spent;
    private calls;
    private characters;
    private perSession;
    private declared;
    private gameDeclared;
    private cfgDeclared;
    private banks;
    private decisions;
    private pending;
    private pools;
    private history;
    private stateOf;
    private minds;
    private opinionsBy;
    private moods;
    private gestures;
    private gestureSeen;
    private loreBy;
    private cfgChars;
    private cfgLore;
    private cfgTools;
    private toolSets;
    private blindTold;
    private cardWaiters;
    private greetings;
    private greetingBusy;
    private bonds;
    private clips;
    private lastDecided;
    private remarkTurns;
    private lastUndo;
    private said;
    private switches;
    private rises;
    private steers;
    private replyTimeout;
    private events;
    private spreads;
    private emptyTold;
    private journalEntries;
    private statsOf;
    private busy;
    private running;
    private queue;
    private idleWaiters;
    private voiceCache;
    private closed;
    clock: () => number;
    wall: () => number;
    constructor(o?: BrainOptions);
    private fromConfig;
    private char;
    /** Keeps a character. A full table first lets go of the oldest one the game never declared (made on the fly from a
     * name); a session past its share keeps nothing more. false: not stored (a throwaway). */
    private store;
    log(kind: string, name: string, text: string, detail?: Record<string, any>): void;
    private allow;
    private call;
    /** A call given up on that answered later: its tokens were billed all the same, so they count (and the caps). */
    private late;
    /** The model of a task: conversations and what players wait for use "chat", the rest "background". */
    private providerFor;
    private rated;
    private account;
    private price;
    private race;
    private patient;
    private grace;
    private replyDeadline;
    private pictures;
    private background;
    private pump;
    /** Waits until background work (banks, decisions, pools, cards) is done; false when it timed out. */
    waitIdle(timeout?: number): Promise<boolean>;
    private context;
    character(session: string, name: unknown, spec?: Record<string, any>, fromConfig?: boolean): Character;
    private gameTools;
    private bindTools;
    tools(session: string, tools?: any): string[];
    prepare(session: string, timeout?: number): Promise<Record<string, any>>;
    private giveSoul;
    private prepareGreeting;
    /** World facts every character takes as true (lines: a list or a text, one per line); null reads them. */
    lore(session: string, lines?: any): any;
    private cardLines;
    private mood;
    private bondTable;
    private known;
    private inner;
    private recollect;
    soul(session: string, name: unknown, speaker?: unknown): Record<string, any>;
    say(session: string, name: unknown, event: unknown, facts0?: unknown, fresh?: boolean, maxChars?: unknown): Promise<Said>;
    private tellEmpty;
    private offlineLine;
    private written;
    private lang;
    /** False when any text in the value is blocked by the content filter. */
    allowed(value: unknown): boolean;
    validLine(line0: string, factNames: Set<string> | null, c: Persona): [boolean, string | null];
    private refill;
    decide(session: string, name: unknown, situation0: unknown, choices: any, every?: unknown): any;
    /** onText: the answer's pieces as they come; used(): true when part of it was already used (then no repair). */
    private structured;
    private voiceOf;
    speak(session: string, name: unknown, text0: unknown): Promise<{
        data: Uint8Array;
        seconds: number;
        text: string;
    } | null>;
    listen(session: string, audio: unknown, language?: string | null): Promise<string>;
    act(session: string, name: unknown, situation0?: unknown, think?: boolean): [string, Record<string, any>][];
    private validActions;
    mind(session: string, name: unknown, personality?: unknown, senses?: any, actions?: any, rules?: any, variants?: any, learn?: any): Record<string, any>;
    private compiledOf;
    mindCompiled(session: string, name: unknown): Record<string, any> | null;
    private mindPrograms;
    private writeVariants;
    think(session: string, name: unknown, senses: any, who?: string | null): Record<string, any>;
    explain(session: string, name: unknown, senses: any, who?: string | null): Record<string, any> | null;
    reward(session: string, who: string, value: unknown, mind?: string | null, variant?: number | null, vid?: unknown, action?: string | null, senses?: Record<string, any> | null, done?: boolean): boolean;
    private credit;
    private learnStep;
    private saveMind;
    mindReport(session: string, name: unknown): Record<string, any> | null;
    mindNames(session: string): string[];
    /** [value, "model" or "offline", how many items onItem already got]. offline: the game's own offline answer;
     * refused: {answer, why} the game refused. onItem(item): for a list answer, every item as soon as the model has
     * written it; false when the game refuses it (it is then left out). */
    create(session: string, what0: unknown, example: any, context?: unknown, count?: unknown, instant?: boolean, timeout?: number | null, image?: unknown, offline?: unknown, refused0?: unknown, onItem?: ((item: any) => boolean) | null): Promise<[any, string, number]>;
    /** onText for a list answer: each finished item, valid and allowed, goes to onItem at once (kept when accepted). */
    private streamer;
    private createMany;
    private fromPool;
    /** refused0: {answer, why}, the reply to this same message the game refused: taken back (words, memory of it, its
     * actions) and asked again knowing why; drop: taken back and answered offline (refused twice). */
    chat(session: string, name: unknown, message0: unknown, facts0?: unknown, speaker0?: unknown, stream?: ((piece: string) => void) | null, timeout?: number | null, maxChars?: unknown, image?: unknown, refused0?: unknown, drop?: boolean): Promise<Said>;
    /** The reply the game refused: out of the conversation, the memory and the actions waiting for act(). */
    private takeBack;
    /** A short line said out loud by someone in the crowd (no character to declare) about what just happened.
     * offline: the game's own lines ({fact} placeholders), taken in turn when no model answers. */
    remark(session: string, about0: unknown, who0?: unknown, facts0?: unknown, offline?: unknown, maxChars?: unknown): Promise<Said>;
    /** The remark as said: one short line, the filter passed, no numbers the game did not give; else "". */
    private validRemark;
    /** budget: seconds for everything here (the asking again included). */
    private deeds;
    private nextOffline;
    /** The spoken reply, cleaned; "" when unusable (why gets "filter" or "character"). */
    cleanReply(text0: string, name: string, why?: string[]): string;
    event(session: string, text0: unknown, about?: unknown, importance?: unknown, by0?: unknown, seenBy?: unknown, tag0?: unknown, impact?: unknown): void;
    private estimateImpact;
    private opinionTable;
    /** What the player could say now to name, one reply per example and in its order. Offline: the examples. */
    suggest(session: string, name: unknown, examples: unknown, speaker0?: unknown, facts0?: unknown): Promise<string[]>;
    /** A short exchange between two characters (one model call), remembered by both. Offline: []. */
    converse(session: string, a: unknown, b: unknown, about0?: unknown, turns?: unknown): Promise<Record<string, string>[]>;
    /** Everything a debug overlay shows. */
    inspect(session: string): Record<string, any>;
    /** Everything known about this session, as one JSON text for the game's save slot. */
    saveState(session: string): string;
    /** Puts back what saveState gave (this session's state is replaced). */
    loadState(session: string, text: unknown): boolean;
    /** What a character feels for someone it has no opinion of yet: its warmth (0 for anyone else). */
    private warmthOf;
    opinion(session: string, a: unknown, b: unknown): number;
    /** What the game decides for name's next reply (used once, by the next chat); "" takes it back. */
    steer(session: string, name: unknown, text: unknown): void;
    opinions(session: string, a: unknown): Record<string, number>;
    feel(session: string, a0: unknown, b0: unknown, change: unknown): number;
    reputation(session: string, target: unknown, group: unknown): number;
    knowledge(session: string, name0: unknown, tag?: string | null): Record<string, any>[];
    meet(session: string, a0: unknown, b0: unknown, k?: unknown): Record<string, any>[];
    spread(session: string, group?: unknown, rounds?: unknown): Record<string, any>[];
    remember(session: string, name: unknown, note: unknown, importance?: unknown): void;
    setState(session: string, state: unknown): void;
    /** Journals, once per name and label, that the model reads only the start of something too long. */
    clipNote(name: string, label: string, value: unknown, limit?: number, text?: boolean): void;
    characterList(session: string): Character[];
    isDeclared(session: string, name: unknown): boolean;
    stats(): Record<string, any>;
    get online(): boolean;
    status(): Record<string, any>;
    private status0;
    journal(n?: number): Record<string, any>[];
    close(): void;
    handle(verb: string, body: Record<string, any>, session?: string): Promise<Record<string, any>>;
    /** chat() with the reply streamed: pieces as they are written, then what the server's "done" event carries. */
    chatStream(session: string, body: Record<string, any>, onPiece: (piece: string) => void): Promise<Record<string, any>>;
    private feelings;
    private replyExtra;
}
/** Runs one vector of python/conformance/vectors.json: the output the Python reference would give. */
export declare function vector(fn: string, args: any[]): any;
export {};
