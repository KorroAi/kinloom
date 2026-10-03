using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Kinloom.Schema;

namespace Kinloom
{
    /// <summary>The runtime. The game declares things and roles, pushes updates and events, calls <see cref="Pump(double)"/>
    /// every frame (or tick) and applies the effects it returns, then reports each outcome with <see cref="Resolve"/>.
    /// All public members are thread-safe; model calls run in the background and are applied during Pump.</summary>
    public sealed partial class KinloomSession
    {
        private readonly object _gate = new object();
        private readonly List<Effect> _ready = new List<Effect>();
        private readonly Dictionary<long, Outstanding> _outstanding = new Dictionary<long, Outstanding>();
        private readonly Dictionary<long, Action<EffectResult>?> _callbacks = new Dictionary<long, Action<EffectResult>?>();
        private readonly List<GameEvent> _events = new List<GameEvent>();
        private readonly HashSet<string> _reported = new HashSet<string>();
        private long _nextEffect;
        private int _nextCreated;
        private readonly Dictionary<string, double> _lastJournaled = new Dictionary<string, double>();
        private readonly HashSet<long> _quiet = new HashSet<long>();

        private sealed class Outstanding
        {
            public Outstanding(Effect effect) { Effect = effect; }
            public Effect Effect { get; }
        }

        public KinloomSession(SessionOptions? options = null)
        {
            Options = options ?? new SessionOptions();
            Journal = new Journal(Options.JournalCapacity);
            Random = new Random(Options.Seed);
            Arbiter = new Arbiter(this);
            Things.Add(ThingDecl.Create(Manifest.WorldId, Manifest.WorldTypeName, "World"), Manifest.WorldType, null).Bound = true;
            InitSubsystems();
        }

        partial void InitSubsystems();

        public SessionOptions Options { get; }
        public Registry Things { get; } = new Registry();
        public Journal Journal { get; }
        public RuntimeStats Stats { get; } = new RuntimeStats();
        public Arbiter Arbiter { get; }
        public Declarations Declared { get; } = new Declarations();
        internal Random Random { get; }
        /// <summary>Current game time in seconds (only moves forward).</summary>
        public double Now { get; private set; }
        /// <summary>The last 200 events, oldest first.</summary>
        public IReadOnlyList<GameEvent> RecentEvents { get { lock (_gate) return _events.ToList(); } }
        public int OutstandingEffects { get { lock (_gate) return _outstanding.Count; } }

        // ---------------- declarations ----------------

        /// <summary>Adds types, things, events, roles, behaviors and generators. Nothing is applied when there are errors.</summary>
        public IReadOnlyList<ManifestError> Declare(string json, string source = "declare")
        {
            var errors = new List<ManifestError>();
            var d = Manifest.Parse(json, source, errors);
            return errors.Count > 0 ? errors : Declare(d);
        }

        public IReadOnlyList<ManifestError> Declare(Declarations d)
        {
            if (d.Types.Count == 0 && d.Events.Count == 0 && d.Roles.Count == 0 && d.Behaviors.Count == 0 && d.Generators.Count == 0)
                return DeclareThings(d);
            lock (_gate)
            {
                var errors = new List<ManifestError>();
                var merged = new Declarations();
                merged.Merge(Declared, errors);
                merged.Merge(d, errors);
                if (errors.Count == 0) Manifest.Check(merged, errors);
                if (errors.Count > 0) return errors;

                Declared.Merge(d, errors);
                foreach (var thing in d.Things) Things.Add(thing, Declared.Types[thing.Type], null);
                OnDeclared(d);
                Log("note", "session", $"declared {d.Types.Count} types, {d.Things.Count} things, {d.Roles.Count} roles, {d.Behaviors.Count} behaviors, {d.Generators.Count} generators");
                return errors;
            }
        }

        partial void OnDeclared(Declarations d);

        /// <summary>Fast path for things appearing at run time (spawned enemies, pickups...): only the new things are
        /// checked, with the same rules and messages as a full manifest check, so spawning stays O(1) per thing.</summary>
        private IReadOnlyList<ManifestError> DeclareThings(Declarations d)
        {
            lock (_gate)
            {
                var errors = new List<ManifestError>();
                var batch = new HashSet<string>(StringComparer.Ordinal);
                for (int i = 0; i < d.Things.Count; i++)
                {
                    var t = d.Things[i];
                    Manifest.CheckThing(t, $"things[{i}]", Declared.Types, errors);
                    if (t.Id.Length > 0 && (Things.Find(t.Id) != null || !batch.Add(t.Id)))
                        errors.Add(new ManifestError("things", $"thing '{t.Id}' is declared twice ({(Things.Find(t.Id) != null ? "already declared" : t.Source)} and {t.Source})"));
                }
                if (errors.Count > 0) return errors;
                foreach (var t in d.Things)
                {
                    Declared.Things.Add(t);
                    Things.Add(t, Declared.Types[t.Type], null);
                }
                if (d.Things.Count > 0) Log("note", "session", d.Things.Count == 1 ? $"declared thing {d.Things[0].Id}" : $"declared {d.Things.Count} things");
                return errors;
            }
        }

        /// <summary>Removes a thing (the game destroyed it). Pending effects on it are dropped at the next pump.</summary>
        public bool RemoveThing(string id)
        {
            lock (_gate)
            {
                if (id == Manifest.WorldId) return false;
                bool removed = Things.Remove(id);
                if (removed)
                {
                    Declared.Things.RemoveAll(t => t.Id == id);
                    OnThingRemoved(id);
                }
                return removed;
            }
        }

        partial void OnThingRemoved(string id);

        public void Bind(string thingId) { lock (_gate) { var t = Things.Find(thingId); if (t != null) t.Bound = true; } }
        public void Unbind(string thingId) { lock (_gate) { var t = Things.Find(thingId); if (t != null) t.Bound = false; } }

        // ---------------- state from the game ----------------

        public void Tick(double gameTime)
        {
            lock (_gate) if (gameTime > Now) Now = gameTime;
        }

        /// <summary>New values for a thing's properties (and params, when the game changed them itself).</summary>
        public void Update(string thingId, JsonObject props)
        {
            lock (_gate)
            {
                var thing = Things.Find(thingId);
                if (thing == null) { ReportOnce("unknown-thing:" + thingId, $"update for unknown thing '{thingId}' ignored (declare it first)"); return; }
                foreach (var p in props)
                {
                    if (thing.Type.Params.Find(p.Key) != null) thing.Set(thing.Params, p.Key, p.Value);
                    else if (thing.Type.Properties.Find(p.Key) != null || thing.Type.Open) thing.Set(thing.Properties, p.Key, p.Value);
                    else ReportOnce($"unknown-prop:{thingId}.{p.Key}", $"'{p.Key}' is not a property of {thing.Type.Name}; update for {thingId}.{p.Key} ignored");
                }
            }
        }

        public void Emit(GameEvent e)
        {
            lock (_gate)
            {
                if (double.IsNaN(e.Time)) e.Time = Now;
                if (double.IsNaN(e.Importance)) e.Importance = Declared.Events.TryGetValue(e.Type, out var decl) ? decl.Importance : 0.5;
                _events.Add(e);
                if (_events.Count > 200) _events.RemoveAt(0);
                Log("event", e.Source ?? "game", e.Describe(), e.Data.DeepClone());
                OnEvent(e);
            }
        }

        partial void OnEvent(GameEvent e);

        // ---------------- effects ----------------

        internal Effect EnqueueEffect(Effect effect, Action<EffectResult>? onResolved)
        {
            lock (_gate)
            {
                effect.Id = ++_nextEffect;
                effect.Created = Now;
                if (effect.Kind == EffectKind.Set && effect.Member != null && Things.Find(effect.Thing) is Thing target)
                    target.Pending[effect.Member] = (effect.Id, effect.Args["value"]?.DeepClone());
                _ready.Add(effect);
                _callbacks[effect.Id] = onResolved;
                return effect;
            }
        }

        /// <summary>Advances time, runs instant behaviors and finished model work, and returns the effects to apply now.</summary>
        public IReadOnlyList<Effect> Pump(double gameTime)
        {
            lock (_gate)
            {
                Tick(gameTime);
                OnPump();
                ExpireOutstanding();
                if (_ready.Count == 0) return Array.Empty<Effect>();
                var batch = new List<Effect>(_ready.Count);
                foreach (var e in _ready)
                {
                    var target = Things.Find(e.Thing);
                    bool creates = e.Kind == EffectKind.Create;
                    string? problem = creates ? null
                        : target == null ? $"'{e.Thing}' no longer exists"
                        : Options.RequireBind && !target.Bound ? $"'{e.Thing}' is not bound to anything in the game"
                        : null;
                    if (problem != null)
                    {
                        Log("dropped", e.Source, $"{e} dropped: {problem}");
                        Complete(e, EffectResult.Failed(problem));
                        continue;
                    }
                    _outstanding[e.Id] = new Outstanding(e);
                    batch.Add(e);
                    Stats.Effects++;
                    if (Journaled(e)) Log("effect", e.Source, e.ToString(), e.ToJson());
                }
                _ready.Clear();
                return batch;
            }
        }

        partial void OnPump();

        /// <summary>Pumps and applies every effect through <paramref name="handler"/>; returns how many were applied.</summary>
        public int Pump(double gameTime, IEffectHandler handler)
        {
            var batch = Pump(gameTime);
            foreach (var e in batch)
            {
                EffectResult result;
                try { result = handler.Apply(e); }
                catch (Exception ex) { result = EffectResult.Failed(ex.GetType().Name + ": " + ex.Message); }
                Resolve(e.Id, result);
            }
            return batch.Count;
        }

        /// <summary>The game's outcome for an effect. Unknown or already-resolved ids are ignored.</summary>
        public void Resolve(long effectId, EffectResult result)
        {
            lock (_gate)
            {
                if (!_outstanding.TryGetValue(effectId, out var o)) return;
                _outstanding.Remove(effectId);
                var e = o.Effect;
                if (result.Status == ResolveStatus.Ok) ApplyConfirmed(e);
                if (result.Status != ResolveStatus.Ok || !_quiet.Contains(e.Id))
                    Log(result.Status == ResolveStatus.Ok ? "resolved" : "refused", e.Source,
                    $"{e} → {result}", new JsonObject { ["effect"] = e.Id, ["status"] = result.Status.ToString().ToLowerInvariant(), ["reason"] = result.Reason });
                Complete(e, result);
            }
        }

        private void ApplyConfirmed(Effect e)
        {
            var thing = Things.Find(e.Thing);
            switch (e.Kind)
            {
                case EffectKind.Set:
                    if (thing != null && e.Member != null) thing.Set(thing.Params, e.Member, e.Args["value"]);
                    break;
                case EffectKind.Invoke:
                    if (thing != null && e.Member != null) thing.LastCall[e.Member] = Now;
                    break;
                case EffectKind.Create:
                    if (thing == null && e.Member != null && Declared.Types.TryGetValue(e.Member, out var type))
                    {
                        var decl = ThingDecl.Create(e.Thing, e.Member, e.Args["name"]?.ToString());
                        Declared.Things.Add(decl);
                        var created = Things.Add(decl, type, e.Source);
                        created.Bound = true;
                        if (e.Args["args"] is JsonObject initial)
                            foreach (var p in initial) created.Set(created.Properties, p.Key, p.Value);
                    }
                    break;
                case EffectKind.Destroy:
                    RemoveThing(e.Thing);
                    break;
            }
        }

        /// <summary>Behaviors may steer a param every frame; the journal keeps one line per param every 2 game seconds
        /// (the effects themselves are all applied). Everything else is journaled.</summary>
        private bool Journaled(Effect e)
        {
            if (e.Kind != EffectKind.Set || !e.Source.StartsWith("behavior:", System.StringComparison.Ordinal)) return true;
            string key = e.Source + "|" + e.Thing + "." + e.Member;
            if (_lastJournaled.TryGetValue(key, out var last) && Now - last < 2) { _quiet.Add(e.Id); return false; }
            _lastJournaled[key] = Now;
            return true;
        }

        private void Complete(Effect e, EffectResult result)
        {
            _quiet.Remove(e.Id);
            if (e.Kind == EffectKind.Set && e.Member != null && Things.Find(e.Thing) is Thing t
                && t.Pending.TryGetValue(e.Member, out var pending) && pending.effect == e.Id)
                t.Pending.Remove(e.Member);
            if (_callbacks.TryGetValue(e.Id, out var callback))
            {
                _callbacks.Remove(e.Id);
                try { callback?.Invoke(result); }
                catch (Exception ex) { Log("error", e.Source, "effect callback failed: " + ex.Message); }
            }
        }

        private void ExpireOutstanding()
        {
            if (_outstanding.Count == 0) return;
            foreach (var o in _outstanding.Values.Where(o => Now - o.Effect.Created > Options.EffectTimeout).ToList())
            {
                _outstanding.Remove(o.Effect.Id);
                Log("dropped", o.Effect.Source, $"{o.Effect} expired: the game never resolved it");
                Complete(o.Effect, EffectResult.Failed("timeout"));
            }
        }

        /// <summary>Live things of a type created by Kinloom, plus creations not yet confirmed.</summary>
        internal int CreatedCount(string type)
        {
            lock (_gate)
                return Things.All.Count(t => t.CreatedBy != null && t.Type.Name == type)
                    + _ready.Concat(_outstanding.Values.Select(o => o.Effect)).Count(e => e.Kind == EffectKind.Create && e.Member == type);
        }

        internal string NextCreatedId(string type)
        {
            lock (_gate)
            {
                string prefix = type.ToLowerInvariant();
                while (true)
                {
                    string id = prefix + "_k" + (++_nextCreated);
                    if (Things.Find(id) == null) return id;
                }
            }
        }

        // ---------------- journal helpers ----------------

        internal void Log(string kind, string source, string text, JsonNode? data = null) =>
            Journal.Add(new JournalEntry(Now, kind, source, text, data));

        private void ReportOnce(string key, string text)
        {
            // Bounded: a game spamming updates for thousands of unknown ids must not grow this forever.
            if (_reported.Count < 1000 && _reported.Add(key)) Log("error", "game", text);
        }
    }
}
