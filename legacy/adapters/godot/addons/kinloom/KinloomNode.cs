#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Godot;
using Kinloom;
using Kinloom.Config;
using Kinloom.GodotAdapter;
using Kinloom.Protocol;
using Kinloom.Schema;

/// <summary>The Kinloom autoload. Reads kinloom.json and kinloom/*.json at startup, binds game nodes (GDScript or C#) to declared
/// things through Godot's own reflection, pumps the runtime every frame and applies effects on the main thread.
/// Every method below is callable from GDScript (all arguments required) and C#.</summary>
public partial class KinloomNode : Node
{
    [Signal] public delegate void SaidEventHandler(string role, string thing, string text, string to);
    [Signal] public delegate void RepliedEventHandler(string role, string text);
    [Signal] public delegate void GeneratedEventHandler(string generator, string json);
    [Signal] public delegate void MediaReadyEventHandler(string kind, string path, string prompt, string thing);
    [Signal] public delegate void CreateRequestedEventHandler(string type, string id, global::Godot.Collections.Dictionary args);
    [Signal] public delegate void ValidateRequestedEventHandler(long id, string generator, string json);

    private readonly Dictionary<string, Node> _nodes = new Dictionary<string, Node>();
    private readonly HashSet<string> _created = new HashSet<string>();
    private readonly HashSet<string> _spawned = new HashSet<string>();
    private readonly Dictionary<string, string> _lastSent = new Dictionary<string, string>();
    private readonly Dictionary<string, HashSet<string>> _propertyNames = new Dictionary<string, HashSet<string>>();
    private double _clock, _sinceUpdate;
    private WsServer? _debug;

    /// <summary>The runtime itself, for C# code that wants the full API.</summary>
    public KinloomSession Session { get; private set; } = new KinloomSession();

    /// <summary>How many times per second bound nodes' properties are read.</summary>
    [Export] public double UpdateHz { get; set; } = 10;

    public override void _Ready()
    {
        string dir = ProjectSettings.GlobalizePath("res://");
        KinloomConfig config;
        try { config = KinloomConfig.Load(dir); }
        catch (InvalidOperationException e) { GD.PushError("[kinloom] " + e.Message); config = new KinloomConfig { ProjectDir = dir }; }
        var options = config.ToOptions(dir);
        options.RequireBind = true; // effects only reach things that are bound to a live node
        Session = new KinloomSession(options);
        config.RegisterMedia(Session.Media, dir);
        var problem = config.CreateClients(null, dir).Problem;
        if (problem != null) GD.Print("[kinloom] " + problem);

        var errors = new List<ManifestError>();
        var declared = Manifest.LoadDirectory(config.ManifestDir(dir), errors);
        if (errors.Count == 0) errors.AddRange(Session.Declare(declared));
        foreach (var e in errors) GD.PushError("[kinloom] manifest: " + e);
        GD.Print($"[kinloom] {Session.Declared.Things.Count} things, {Session.Declared.Roles.Count} roles from {config.ManifestDir(dir)}");

        Session.Journal.Added += entry =>
        {
            if (entry.Kind == "error" || entry.Kind == "refused" && entry.Source.StartsWith("behavior:", StringComparison.Ordinal))
                GD.Print("[kinloom] " + entry);
        };

        if (OS.IsDebugBuild() && config.DebugPort > 0)
        {
            try
            {
                _debug = WsServer.ForSession(config.DebugPort, Session);
                _debug.Start();
                GD.Print($"[kinloom] inspector: http://localhost:{config.DebugPort}/ (kinloom inspect)");
            }
            catch (Exception e) { GD.Print($"[kinloom] debug port {config.DebugPort} unavailable: {e.Message}"); _debug = null; }
        }
    }

    public override void _ExitTree()
    {
        _debug?.Dispose();
        _debug = null;
    }

    public override void _Process(double delta)
    {
        _clock += delta;
        _sinceUpdate += delta;
        if (_sinceUpdate >= 1.0 / Math.Max(1, UpdateHz))
        {
            _sinceUpdate = 0;
            PushState();
        }
        foreach (var effect in Session.Pump(_clock))
        {
            EffectResult result;
            try { result = Apply(effect); }
            catch (Exception e) { result = EffectResult.Failed(e.GetType().Name + ": " + e.Message); }
            if (result != null!) Session.Resolve(effect.Id, result);
        }
    }

    // ---------------- binding ----------------

    /// <summary>Links a declared thing to a node. Properties are read by name (or from a <c>_kinloom_state()</c> Dictionary),
    /// params written with set, functions called with callv.</summary>
    public void Bind(string id, Node node)
    {
        if (Session.Things.Find(id) == null) { GD.PushError($"[kinloom] Bind: '{id}' is not declared in kinloom/*.json (use Spawned to declare it now)"); return; }
        _nodes[id] = node;
        Session.Bind(id);
        PushState(id, node);
    }

    public void Unbind(string id)
    {
        _nodes.Remove(id);
        Session.Unbind(id);
    }

    /// <summary>Declares and binds a thing the game created itself (an enemy spawned by the game, a new vehicle...).</summary>
    public void Spawned(string id, string type, Node node)
    {
        if (Session.Things.Find(id) == null)
        {
            var decl = new JsonObject { ["things"] = new JsonArray(new JsonObject { ["id"] = id, ["type"] = type, ["name"] = node.Name.ToString() }) };
            var errors = Session.Declare(decl.ToJsonString(), "Spawned");
            if (errors.Count > 0) { GD.PushError("[kinloom] Spawned: " + string.Join("; ", errors)); return; }
            _spawned.Add(id);
        }
        Bind(id, node);
    }

    /// <summary>The game removed a thing.</summary>
    public void Despawned(string id)
    {
        _nodes.Remove(id);
        _created.Remove(id);
        _spawned.Remove(id);
        Session.RemoveThing(id);
    }

    // ---------------- events and facts ----------------

    public void EmitEvent(string type, global::Godot.Collections.Dictionary data) =>
        Session.Emit(new GameEvent(type, GodotValues.ToJsonObject(data)));

    public void EmitEventSeenBy(string type, global::Godot.Collections.Dictionary data, global::Godot.Collections.Array perceivedBy) =>
        Session.Emit(new GameEvent(type, GodotValues.ToJsonObject(data), perceivedBy.Select(x => x.AsString()).ToArray()));

    /// <summary>A global fact on the built-in <c>world</c> thing, visible to roles that see <c>world</c>.</summary>
    public void SetFact(string key, Variant value) =>
        Session.Update(Manifest.WorldId, new JsonObject { [key] = GodotValues.ToJson(value) });

    // ---------------- talking, generating, waking ----------------

    /// <summary>Talks to a role; the answer arrives with the Replied signal.</summary>
    public void Ask(string role, string text, string from)
    {
        Session.Ask(role, text, from).ContinueWith(t =>
        {
            string reply = t.Status == System.Threading.Tasks.TaskStatus.RanToCompletion ? t.Result.Reply ?? "" : "";
            Callable.From(() => EmitSignal(SignalName.Replied, role, reply)).CallDeferred();
        });
    }

    /// <summary>Runs a generator; the validated value (JSON) arrives with the Generated signal ("" when it failed without fallback).</summary>
    public void Generate(string generator, global::Godot.Collections.Dictionary context)
    {
        Session.Generate(generator, GodotValues.ToJsonObject(context)).ContinueWith(t =>
        {
            string json = t.Status == System.Threading.Tasks.TaskStatus.RanToCompletion && t.Result.Ok ? t.Result.Value?.ToJsonString() ?? "null" : "";
            Callable.From(() => EmitSignal(SignalName.Generated, generator, json)).CallDeferred();
        });
    }

    public void Wake(string role) => Session.Wake(role);

    /// <summary>Removes the behaviors roles installed (and their fallback instincts); "" for every role. Call it when a race,
    /// round or level restarts so reflexes do not carry over. Returns how many were removed.</summary>
    public int ClearRoleBehaviors(string role) => Session.ClearInstalledBehaviors(string.IsNullOrEmpty(role) ? null : role);

    /// <summary>Removes one installed behavior by id.</summary>
    public bool RemoveBehavior(string id) => Session.RemoveBehavior(id);

    /// <summary>Ids of the installed behaviors, as "id|source|owner" (debugging, housekeeping).</summary>
    public string[] BehaviorList() => Session.Behaviors.Select(b => $"{b.behavior.Id}|{b.source}|{b.owner}").ToArray();

    /// <summary>Answers a ValidateRequested signal.</summary>
    public void ResolveValidation(long id, bool ok, string reason) =>
        Session.Resolve(id, ok ? EffectResult.Ok() : EffectResult.Refused(string.IsNullOrWhiteSpace(reason) ? "refused by the game" : reason));

    // ---------------- persistence and debugging ----------------

    public string SaveState() => Session.Save();

    public void LoadState(string state)
    {
        try { Session.Load(state); }
        catch (InvalidOperationException e) { GD.PushError("[kinloom] " + e.Message); }
    }

    /// <summary>Adds declarations at run time; returns the errors (empty when accepted).</summary>
    public string Declare(string json) => string.Join("\n", Session.Declare(json, "Declare"));

    /// <summary>Calls, failures, fallbacks, refusals, tokens and cost (null without declared prices), as JSON.</summary>
    public string StatsJson() => Wire.Stats(Session.Stats).ToJsonString();

    /// <summary>The last journal lines (debugging without the inspector).</summary>
    public string JournalText(int count) => string.Join("\n", Session.Journal.Recent(count).Select(j => j.ToString()));

    /// <summary>One-line state of a thing as Kinloom sees it (debugging).</summary>
    public string DescribeThing(string id) => Session.Things.Find(id)?.Describe() ?? $"no thing '{id}'";

    // ---------------- internals ----------------

    private void PushState()
    {
        foreach (var pair in _nodes.ToList())
        {
            if (!IsInstanceValid(pair.Value) || pair.Value.IsQueuedForDeletion())
            {
                // A freed node: things that appeared at run time go away; things from the manifest stay declared, only unbound,
                // so the game can bind a new node later (a level reloads, the player returns from a menu).
                if (_spawned.Contains(pair.Key) || _created.Contains(pair.Key)) Despawned(pair.Key);
                else Unbind(pair.Key);
                continue;
            }
            PushState(pair.Key, pair.Value);
        }
    }

    private void PushState(string id, Node node)
    {
        var thing = Session.Things.Find(id);
        if (thing == null) return;
        var props = new JsonObject();
        if (node.HasMethod("_kinloom_state"))
        {
            var state = node.Call("_kinloom_state");
            if (state.VariantType == Variant.Type.Dictionary) props = GodotValues.ToJsonObject(state.AsGodotDictionary());
        }
        else
        {
            var names = PropertyNames(node);
            foreach (var f in thing.Type.Properties.Concat(thing.Type.Params))
                if (names.Contains(f.Name)) props[f.Name] = GodotValues.ToJson(node.Get(f.Name));
        }
        var changed = new JsonObject();
        foreach (var p in props)
        {
            string key = id + "." + p.Key, text = p.Value?.ToJsonString() ?? "null";
            if (_lastSent.TryGetValue(key, out var last) && last == text) continue;
            _lastSent[key] = text;
            changed[p.Key] = p.Value?.DeepClone();
        }
        if (changed.Count > 0) Session.Update(id, changed);
    }

    /// <summary>Script and native property names of a node, cached per script/class.</summary>
    private HashSet<string> PropertyNames(Node node)
    {
        var script = node.GetScript();
        string key = node.GetClass() + "|" + (script.VariantType == Variant.Type.Object ? (script.AsGodotObject() as Resource)?.ResourcePath : "");
        if (_propertyNames.TryGetValue(key, out var names)) return names;
        names = new HashSet<string>();
        foreach (var entry in node.GetPropertyList()) names.Add(entry["name"].AsString());
        _propertyNames[key] = names;
        return names;
    }

    private EffectResult Apply(Effect e)
    {
        string role = e.Source.StartsWith("role:", StringComparison.Ordinal) ? e.Source.Substring(5) : e.Source;
        switch (e.Kind)
        {
            case EffectKind.Say:
                EmitSignal(SignalName.Said, role, e.Thing, e.Text ?? "", e.Args["to"]?.GetValue<string>() ?? "");
                return EffectResult.Ok();
            case EffectKind.Media:
                EmitSignal(SignalName.MediaReady, e.Member ?? "", e.Args["path"]?.GetValue<string>() ?? "", e.Args["prompt"]?.GetValue<string>() ?? "", e.Thing);
                return EffectResult.Ok();
            case EffectKind.Validate:
                EmitSignal(SignalName.ValidateRequested, e.Id, e.Member ?? "", e.Args["value"]?.ToJsonString() ?? "null");
                return null!; // resolved later by ResolveValidation
            case EffectKind.Create:
                return Create(e);
        }
        if (e.Thing == Manifest.WorldId)
        {
            if (e.Kind == EffectKind.Invoke && e.Member == "generated")
                EmitSignal(SignalName.Generated, e.Args["generator"]?.GetValue<string>() ?? "", e.Args["value"]?.ToJsonString() ?? "null");
            return EffectResult.Ok(); // world facts live in the runtime
        }
        if (!_nodes.TryGetValue(e.Thing, out var node) || !IsInstanceValid(node)) return EffectResult.Failed($"'{e.Thing}' has no live node");
        var thing = Session.Things.Find(e.Thing);
        switch (e.Kind)
        {
            case EffectKind.Set:
            {
                if (!PropertyNames(node).Contains(e.Member!)) return EffectResult.Failed($"node {node.Name} has no property '{e.Member}'");
                node.Set(e.Member!, GodotValues.ToVariant(e.Args["value"], thing?.Type.Params.Find(e.Member!)));
                _lastSent.Remove(e.Thing + "." + e.Member);
                return EffectResult.Ok();
            }
            case EffectKind.Invoke:
            {
                if (!node.HasMethod(e.Member!)) return EffectResult.Failed($"node {node.Name} has no method '{e.Member}'");
                var args = new global::Godot.Collections.Array();
                if (thing != null && thing.Type.Functions.TryGetValue(e.Member!, out var fn))
                    foreach (var a in fn.Args) args.Add(GodotValues.ToVariant(e.Args[a.Name], a.Spec));
                var returned = node.Callv(e.Member!, args);
                // A method may refuse by returning {"refused": "reason"}.
                if (returned.VariantType == Variant.Type.Dictionary && returned.AsGodotDictionary().TryGetValue("refused", out var reason))
                    return EffectResult.Refused(reason.AsString());
                return EffectResult.Ok();
            }
            case EffectKind.Destroy:
                node.QueueFree();
                _nodes.Remove(e.Thing);
                _created.Remove(e.Thing);
                return EffectResult.Ok();
            default:
                return EffectResult.Failed("unsupported effect " + e.Kind);
        }
    }

    private EffectResult Create(Effect e)
    {
        var type = Session.Declared.Types.TryGetValue(e.Member ?? "", out var t) ? t : null;
        var creationArgs = e.Args["args"] as JsonObject ?? new JsonObject();
        var godot = type?.Engine?["godot"] as JsonObject;
        string? scenePath = godot?["scene"]?.GetValue<string>();
        if (scenePath == null)
        {
            var dict = new global::Godot.Collections.Dictionary();
            foreach (var p in creationArgs) dict[p.Key] = GodotValues.ToVariant(p.Value, type?.Creatable?.Args.Find(p.Key));
            EmitSignal(SignalName.CreateRequested, e.Member ?? "", e.Thing, dict);
            return EffectResult.Ok(); // the game spawns it and calls Kinloom.Bind(id, node)
        }
        var scene = GD.Load<PackedScene>(scenePath);
        if (scene == null) return EffectResult.Failed($"cannot load scene {scenePath}");
        var node = scene.Instantiate();
        node.Name = e.Thing;
        var names = PropertyNames(node);
        foreach (var p in creationArgs)
            if (names.Contains(p.Key)) node.Set(p.Key, GodotValues.ToVariant(p.Value, type?.Creatable?.Args.Find(p.Key)));
        string? parentPath = godot?["parent"]?.GetValue<string>();
        Node? parent = parentPath != null ? GetNodeOrNull(parentPath) : GetTree().CurrentScene;
        if (parent == null) { node.QueueFree(); return EffectResult.Failed($"parent {parentPath} not found"); }
        parent.AddChild(node);
        _nodes[e.Thing] = node;
        _created.Add(e.Thing);
        Callable.From(() => { if (Session.Things.Find(e.Thing) != null) Session.Bind(e.Thing); }).CallDeferred();
        return EffectResult.Ok();
    }
}
