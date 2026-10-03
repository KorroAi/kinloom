// Types for kinloom.js (the Kinloom client for JavaScript and TypeScript games).

export type EffectKind = "set" | "invoke" | "create" | "destroy" | "say" | "media" | "validate";

export interface Effect {
  id: number;
  kind: EffectKind;
  /** Target thing id (for create: the id the new thing will have). */
  thing: string;
  /** Param (set), function (invoke), type (create), media kind (media), generator (validate). */
  member: string | null;
  /** set: {value}; invoke: named args; create: {args, name?}; say: {to?}; media: {path, format, prompt}; validate: {value}. */
  args: Record<string, any>;
  /** Who proposed it: role:<id>, behavior:<id>, generator:<id>. */
  source: string;
  /** say: the line to show or speak. */
  text: string | null;
  time: number;
}

export type EffectOutcome =
  | void
  | boolean
  | string
  | { status: "ok" | "failed" | "refused"; reason?: string; value?: unknown };

export type EffectHandler = (effect: Effect) => EffectOutcome | Promise<EffectOutcome>;

export interface ManifestError { path: string; message: string; }
export interface AskResult { reply: string | null; usedFallback: boolean; error: string | null; effects: Effect[]; }
export interface GenerateResult { ok: boolean; value: unknown; usedFallback: boolean; errors: string[]; }
export interface MediaResult { ok: boolean; path: string | null; format: string | null; error: string | null; cached: boolean; }

export declare class KinloomError extends Error {
  code?: number;
}

export declare class Kinloom {
  static connect(url?: string, options?: { WebSocket?: any; timeoutMs?: number }): Promise<Kinloom>;
  handle(kind: EffectKind | "generated", handler: EffectHandler): this;
  onEffect(handler: EffectHandler): this;
  declare(manifest: object | string, source?: string): Promise<ManifestError[]>;
  update(thing: string, props: Record<string, unknown>): void;
  event(type: string, data?: Record<string, unknown>, options?: { perceivedBy?: string[]; time?: number; importance?: number }): void;
  frame(time: number): void;
  tick(time: number): Promise<Effect[]>;
  ask(role: string, input: string, from?: string): Promise<AskResult>;
  generate(generator: string, context?: Record<string, unknown>): Promise<GenerateResult>;
  media(kind: string, prompt: string, spec?: Record<string, unknown>): Promise<MediaResult>;
  bind(thing: string): void;
  unbind(thing: string): void;
  remove(thing: string): Promise<boolean>;
  save(): Promise<string>;
  load(state: string): Promise<unknown>;
  stats(): Promise<Record<string, unknown>>;
  snapshot(): Promise<Record<string, unknown>>;
  setMission(role: string, mission: string): Promise<unknown>;
  resolve(id: number, status?: "ok" | "failed" | "refused", reason?: string, value?: unknown): void;
  close(): void;
}
