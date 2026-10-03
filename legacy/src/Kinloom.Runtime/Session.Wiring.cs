using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Kinloom.Behaviors;
using Kinloom.Generators;
using Kinloom.Llm;
using Kinloom.Media;
using Kinloom.Roles;
using Kinloom.Scheduling;
using Kinloom.Schema;

namespace Kinloom
{
    /// <summary>Connects the subsystems (behaviors, roles, memory...) to the session's lifecycle hooks.</summary>
    public sealed partial class KinloomSession
    {
        private BehaviorEngine _behaviors = null!;
        private RoleEngine _roles = null!;
        private GeneratorRunner _generators = null!;
        private Budget _budget = null!;

        partial void InitSubsystems()
        {
            var watch = Stopwatch.StartNew();
            _budget = new Budget(Options.Clock ?? (() => watch.Elapsed.TotalSeconds));
            _behaviors = new BehaviorEngine(this);
            _roles = new RoleEngine(this, _budget);
            _generators = new GeneratorRunner(this, _budget);
            Media = new MediaPort(Options.MediaCache ?? System.IO.Path.Combine(System.IO.Path.GetTempPath(), "kinloom-media"));
        }

        partial void OnDeclared(Declarations d)
        {
            // Behaviors named as a role's fallback wait for that fallback; the others run from the start.
            var fallbacks = new HashSet<string>(Declared.Roles.Select(r => r.Fallback?.Behavior).Where(x => x != null)!);
            foreach (var b in d.Behaviors.Where(b => !fallbacks.Contains(b.Id))) _behaviors.Install(b, "game", null, null);
            _roles.Declare(d.Roles);
        }

        partial void OnThingRemoved(string id)
        {
            _behaviors.RemoveOwnedBy(id);
        }

        partial void OnEvent(GameEvent e)
        {
            _roles.OnEvent(e);
        }

        partial void OnPump()
        {
            _roles.Step();
            _generators.Step();
            _behaviors.Step();
        }

        /// <summary>Installs (or replaces, for the same source) instant rules. <paramref name="can"/> null means trusted (the game);
        /// otherwise every lever the rules use must be allowed. Returns the reasons it was refused, if any.</summary>
        public IReadOnlyList<string> InstallBehavior(BehaviorDecl behavior, string source, IReadOnlyList<Permission>? can, string? self = null)
        {
            lock (_gate) return _behaviors.Install(behavior, source, can, self);
        }

        public bool RemoveBehavior(string id)
        {
            lock (_gate)
            {
                bool removed = _behaviors.Remove(id);
                if (removed) Log("behavior", "session", $"removed behavior {id}");
                return removed;
            }
        }

        /// <summary>Removes the behaviors roles installed and their fallback instincts (all roles, or one), keeping the game's
        /// own. Call it when a round, level or race restarts so reflexes do not carry over. Returns how many were removed.</summary>
        public int ClearInstalledBehaviors(string? roleId = null)
        {
            lock (_gate)
            {
                var ids = _behaviors.All
                    .Where(b => BehaviorEngine.RoleOf(b.Source) is string role && (roleId == null || role == roleId))
                    .Select(b => b.Decl.Id).ToList();
                foreach (var id in ids) _behaviors.Remove(id);
                if (ids.Count > 0) Log("behavior", "session", $"cleared {ids.Count} installed behaviors{(roleId != null ? " of " + roleId : "")}");
                return ids.Count;
            }
        }

        /// <summary>Installed behaviors: declaration, who installed it, owner thing.</summary>
        public IReadOnlyList<(BehaviorDecl behavior, string source, string owner)> Behaviors
        {
            get { lock (_gate) return _behaviors.All.Select(b => (b.Decl, b.Source, b.OwnerId)).ToList(); }
        }

        private JsonObject SaveRoleState() => _roles.Save();

        private void LoadRoleState(JsonObject? state, double timeShift) => _roles.Load(state);

        /// <summary>Asks a role to think as soon as its budget allows.</summary>
        internal void RequestWake(string roleId, string reason) => _roles.Wake(roleId, reason);

        /// <summary>Makes a role think now (subject to its budget), e.g. when the game reaches a story beat.</summary>
        public void Wake(string roleId, string reason = "The game asked you to act now.")
        {
            lock (_gate) _roles.Wake(roleId, reason);
        }

        /// <summary>Talks to a role (a player typing or speaking, another system asking). The reply arrives after the model answers
        /// and the game keeps pumping; over budget or without a model, the role's fallback answers.</summary>
        public Task<AskResult> Ask(string roleId, string input, string? from = null)
        {
            lock (_gate) return _roles.Ask(roleId, input, from);
        }

        /// <summary>True while a model call (role or generator) is running or an answer is waiting for the next pump.</summary>
        public bool HasRoleWork { get { lock (_gate) return _roles.Busy || _generators.Busy; } }

        /// <summary>Runs a generator. The result arrives after the model answers and the game keeps pumping
        /// (with <c>gameValidate</c>, after the game resolved the Validate effect).</summary>
        public Task<GenerateResult> Generate(string generatorId, JsonObject? context = null, string? source = null)
        {
            lock (_gate) return _generators.Generate(generatorId, context, source);
        }

        public IReadOnlyList<string> RoleIds { get { lock (_gate) return _roles.Roles.Select(r => r.Id).ToList(); } }

        /// <summary>Replaces a role's mission at run time (the inspector's live edit).</summary>
        public bool SetMission(string roleId, string mission)
        {
            lock (_gate)
            {
                var role = _roles.Find(roleId);
                if (role == null || string.IsNullOrWhiteSpace(mission)) return false;
                role.Mission = mission;
                Log("note", "session", $"mission of {roleId} changed");
                return true;
            }
        }

        public string? MissionOf(string roleId) { lock (_gate) return _roles.Find(roleId)?.Mission; }

        internal IReadOnlyList<Permission>? RolePermissions(string roleId) => _roles.Find(roleId)?.Can;

        /// <summary>The exact prompt and tools a role would get now, without calling any model (simulation, debugging).</summary>
        public (string system, string user, IReadOnlyList<string> tools)? PreviewPrompt(string roleId, string? askInput = null, string? from = null, string reason = "Preview.")
        {
            lock (_gate)
            {
                var role = _roles.Find(roleId);
                if (role == null) return null;
                var trigger = askInput != null ? new Trigger("ask") { AskInput = askInput, From = from } : new Trigger(reason);
                return (RolePrompt.System(this, role), RolePrompt.User(this, role, trigger), RoleTools.For(role.Can, role.Decl.Inhabits != null).Select(t => t.Name).ToList());
            }
        }

        internal void CountCall(string source, LlmResponse response, Budget budget)
        {
            Stats.Calls++;
            if (!response.Ok) Stats.Failures++;
            Stats.InputTokens += response.InputTokens;
            Stats.CachedInputTokens += response.CachedInputTokens;
            Stats.OutputTokens += response.OutputTokens;
            Stats.LatencyMs += response.LatencyMs;
            Stats.CallsBySource[source] = Stats.CallsBySource.TryGetValue(source, out var n) ? n + 1 : 1;
            if (Options.Prices != null)
            {
                double cost = Options.Prices.CostOf(response.InputTokens, response.CachedInputTokens, response.OutputTokens);
                Stats.Cost = (Stats.Cost ?? 0) + cost;
                budget.RecordCost(cost);
            }
        }

        internal void StartGeneration(string generatorId, JsonObject context, string source) => _generators.Generate(generatorId, context, source);

        /// <summary>The developer's media tools (Kinloom ships none). Register providers here or declare them in kinloom.json.</summary>
        public MediaPort Media { get; private set; } = null!;

        /// <summary>Asks the registered media tools for an asset; journals the outcome.</summary>
        public async Task<MediaResult> RequestMedia(MediaRequest request, string? source = null)
        {
            string who = source ?? "game";
            Log("call", who, $"media {request.Kind}: {request.Prompt}");
            var result = await Media.Request(request).ConfigureAwait(false);
            if (result.Ok) Log("media", who, $"{request.Kind} ready: {result.Path}{(result.Cached ? " (cached)" : "")}");
            else Log("error", who, $"media {request.Kind} failed: {result.Error}");
            return result;
        }

        internal void StartMedia(string kind, string prompt, JsonObject spec, string source, string? thing)
        {
            var request = new MediaRequest(kind, prompt, spec);
            _ = RequestMedia(request, source).ContinueWith(t =>
            {
                if (t.Status != TaskStatus.RanToCompletion || !t.Result.Ok) return;
                EnqueueEffect(new Effect(EffectKind.Media, thing ?? Manifest.WorldId, kind,
                    new JsonObject { ["path"] = t.Result.Path, ["format"] = t.Result.Format, ["prompt"] = prompt }, source), null);
            }, TaskScheduler.Default);
        }
    }
}
