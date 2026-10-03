using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Kinloom.Schema;

namespace Kinloom
{
    public enum ProposalKind { Set, Invoke, Create, Destroy, Say, Behavior, Remember, Generate, Media }

    /// <summary>Something a role, a behavior or a generator wants to happen. Nothing reaches the game before the Arbiter allows it.</summary>
    public sealed class Proposal
    {
        public Proposal(ProposalKind kind, string source) { Kind = kind; Source = source; }

        public ProposalKind Kind { get; }
        /// <summary>Who proposes: <c>role:&lt;id&gt;</c>, <c>behavior:&lt;id&gt;</c>...</summary>
        public string Source { get; }
        /// <summary>Target thing id, or <c>self</c>.</summary>
        public string? Thing { get; set; }
        /// <summary>Param, function, type (create), generator id, media kind.</summary>
        public string? Member { get; set; }
        public JsonObject Args { get; set; } = new JsonObject();
        public string? Text { get; set; }
        /// <summary>Say: who it is addressed to (optional).</summary>
        public string? To { get; set; }
        public BehaviorDecl? Behavior { get; set; }
        /// <summary>The thing the proposer inhabits (what <c>self</c> means), if any.</summary>
        public string? Self { get; set; }
    }

    public sealed class Verdict
    {
        private Verdict(bool allowed, string reason, Effect? effect) { Allowed = allowed; Reason = reason; Effect = effect; }
        public bool Allowed { get; }
        public string Reason { get; }
        /// <summary>The normalized effect to enqueue, for kinds that act on the game.</summary>
        public Effect? Effect { get; }

        internal static Verdict Allow(Effect? effect = null) => new Verdict(true, "ok", effect);
        internal static Verdict Refuse(string reason) => new Verdict(false, reason, null);
    }

    /// <summary>Validates every proposal against the proposer's permissions and the rules the game declared:
    /// targets exist, members exist, values fit their specs, cooldowns and creation limits hold. Refusals are journaled.</summary>
    public sealed class Arbiter
    {
        public const int MaxSayLength = 600;
        public const int MaxNoteLength = 500;
        private readonly KinloomSession _s;

        internal Arbiter(KinloomSession session) { _s = session; }

        /// <param name="journal">False to skip journaling a refusal (repeated refusals of the same behavior rule).</param>
        public Verdict Check(Proposal p, IReadOnlyList<Permission> can, bool journal = true)
        {
            Verdict v;
            try { v = Decide(p, can); }
            catch (Exception e) { v = Verdict.Refuse("invalid proposal: " + e.Message); }
            if (!v.Allowed && journal)
            {
                _s.Stats.Refusals++;
                _s.Log("refused", p.Source, $"{Describe(p)} refused: {v.Reason}");
            }
            return v;
        }

        /// <summary>A spoken line as players will see it: control characters (terminal escapes, NUL...) removed, except line breaks.</summary>
        internal static string Clean(string? text)
        {
            if (string.IsNullOrEmpty(text)) return "";
            var sb = new System.Text.StringBuilder(text!.Length);
            foreach (char c in text) if (!char.IsControl(c) || c == '\n') sb.Append(c);
            return sb.ToString().Trim();
        }

        private static string Describe(Proposal p) => p.Kind switch
        {
            ProposalKind.Set => $"set {p.Thing}.{p.Member}",
            ProposalKind.Invoke => $"{p.Thing}.{p.Member}()",
            ProposalKind.Create => $"create {p.Member}",
            ProposalKind.Destroy => $"destroy {p.Thing}",
            ProposalKind.Say => "say",
            ProposalKind.Behavior => $"behavior {p.Behavior?.Id}",
            ProposalKind.Generate => $"generate {p.Member}",
            ProposalKind.Media => $"media {p.Member}",
            _ => p.Kind.ToString().ToLowerInvariant(),
        };

        private Verdict Decide(Proposal p, IReadOnlyList<Permission> can)
        {
            switch (p.Kind)
            {
                case ProposalKind.Set: return CheckSet(p, can);
                case ProposalKind.Invoke: return CheckInvoke(p, can);
                case ProposalKind.Create: return CheckCreate(p, can);
                case ProposalKind.Destroy: return CheckDestroy(p, can);
                case ProposalKind.Say:
                {
                    if (!can.Any(c => c.Verb == Verb.Say)) return Verdict.Refuse("saying things is not allowed for this role");
                    string text = Clean(p.Text);
                    if (text.Length == 0) return Verdict.Refuse("nothing to say");
                    if (text.Length > MaxSayLength) return Verdict.Refuse($"a line must be at most {MaxSayLength} characters");
                    string speaker = p.Self ?? Manifest.WorldId;
                    var args = new JsonObject();
                    if (!string.IsNullOrWhiteSpace(p.To)) args["to"] = p.To;
                    return Verdict.Allow(new Effect(EffectKind.Say, speaker, null, args, p.Source, text));
                }
                case ProposalKind.Remember:
                    if (!can.Any(c => c.Verb == Verb.Remember)) return Verdict.Refuse("remembering is not allowed for this role");
                    if (string.IsNullOrWhiteSpace(p.Text)) return Verdict.Refuse("nothing to remember");
                    return p.Text!.Trim().Length > MaxNoteLength ? Verdict.Refuse($"a note must be at most {MaxNoteLength} characters") : Verdict.Allow();
                case ProposalKind.Behavior:
                {
                    if (p.Behavior == null) return Verdict.Refuse("no behavior given");
                    var errors = CheckBehavior(p.Behavior, can, p.Self, p.Source);
                    return errors.Count == 0 ? Verdict.Allow() : Verdict.Refuse(string.Join("; ", errors));
                }
                case ProposalKind.Generate:
                    if (!can.Any(c => c.Verb == Verb.Generate && (c.Target == "*" || c.Target == p.Member))) return Verdict.Refuse($"generating '{p.Member}' is not allowed for this role");
                    return _s.Declared.Generators.Any(g => g.Id == p.Member) ? Verdict.Allow() : Verdict.Refuse($"unknown generator '{p.Member}'");
                case ProposalKind.Media:
                    if (!can.Any(c => c.Verb == Verb.Media && (c.Target == "*" || c.Target == p.Member))) return Verdict.Refuse($"requesting '{p.Member}' media is not allowed for this role");
                    string? badPrompt = Media.MediaPort.CheckPrompt(p.Text);
                    return badPrompt != null ? Verdict.Refuse(badPrompt) : Verdict.Allow();
                default:
                    return Verdict.Refuse("unknown proposal");
            }
        }

        /// <summary>Resolves <c>self</c> and checks the thing exists (and is bound when required).</summary>
        private Thing? Target(Proposal p, out string? problem)
        {
            problem = null;
            string? id = p.Thing == "self" ? p.Self : p.Thing;
            if (string.IsNullOrEmpty(id)) { problem = p.Thing == "self" ? "'self' means nothing here: this role does not inhabit a thing" : "no target thing given"; return null; }
            var thing = _s.Things.Find(id);
            if (thing == null) { problem = $"unknown thing '{id}'{Manifest.Suggest(id!, _s.Things.All.Select(t => t.Id))}"; return null; }
            if (_s.Options.RequireBind && !thing.Bound) { problem = $"'{id}' is not bound to anything in the game right now"; return null; }
            return thing;
        }

        private static bool TargetMatches(string target, Thing thing, string? self) =>
            target == "*"
            || (target == "self" && self != null && thing.Id == self)
            || target == thing.Id
            || target == thing.Type.Name
            || (target.StartsWith("tag:", StringComparison.Ordinal) && thing.Tags.Contains(target.Substring(4)));

        private static bool Permits(IReadOnlyList<Permission> can, Verb verb, Thing thing, string? member, string? self) =>
            can.Any(c => c.Verb == verb && c.Target != null && TargetMatches(c.Target, thing, self) && (c.Member == null || c.Member == "*" || c.Member == member));

        private Verdict CheckSet(Proposal p, IReadOnlyList<Permission> can)
        {
            var thing = Target(p, out var problem);
            if (thing == null) return Verdict.Refuse(problem!);
            string member = p.Member ?? "";
            var spec = thing.Type.Params.Find(member) ?? (thing.Type.Open ? FieldSpec.AnyValue : null);
            if (spec == null)
                return Verdict.Refuse(thing.Type.Properties.Find(member) != null
                    ? $"'{member}' is a read-only property of {thing.Type.Name}; only params can be set"
                    : $"'{member}' is not a param of {thing.Type.Name}{Manifest.Suggest(member, thing.Type.Params.Names)}");
            if (!Permits(can, Verb.Set, thing, member, p.Self)) return Verdict.Refuse($"setting {thing.Id}.{member} is not allowed for this role");
            if (!p.Args.ContainsKey("value")) return Verdict.Refuse("no value given");
            var value = p.Args["value"];
            string? invalid = spec.Validate(value, member);
            if (invalid != null) return Verdict.Refuse(invalid);
            return Verdict.Allow(new Effect(EffectKind.Set, thing.Id, member, new JsonObject { ["value"] = value?.DeepClone() }, p.Source));
        }

        private Verdict CheckInvoke(Proposal p, IReadOnlyList<Permission> can)
        {
            var thing = Target(p, out var problem);
            if (thing == null) return Verdict.Refuse(problem!);
            string member = p.Member ?? "";
            if (!thing.Type.Functions.TryGetValue(member, out var fn))
                return Verdict.Refuse($"'{member}' is not a function of {thing.Type.Name}{Manifest.Suggest(member, thing.Type.Functions.Keys)}");
            if (!Permits(can, Verb.Invoke, thing, member, p.Self)) return Verdict.Refuse($"calling {thing.Id}.{member} is not allowed for this role");
            var args = CheckArgs(fn.Args, p.Args, member, out var argProblem);
            if (args == null) return Verdict.Refuse(argProblem!);
            if (fn.Cooldown > 0 && thing.LastCall.TryGetValue(member, out var last) && _s.Now - last < fn.Cooldown)
                return Verdict.Refuse($"{member} is cooling down ({fn.Cooldown - (_s.Now - last):0.0} s left)");
            thing.LastCall[member] = _s.Now;
            return Verdict.Allow(new Effect(EffectKind.Invoke, thing.Id, member, args, p.Source));
        }

        /// <summary>Validated copy of the args with defaults filled; null when something is wrong.</summary>
        private static JsonObject? CheckArgs(FieldSet specs, JsonObject given, string context, out string? problem)
        {
            problem = null;
            foreach (var key in given.Select(k => k.Key))
                if (specs.Find(key) == null) { problem = $"{context} has no argument '{key}'" + (specs.Count > 0 ? $" (expected {string.Join(", ", specs.Names)})" : " (it takes none)"); return null; }
            var args = new JsonObject();
            foreach (var f in specs)
            {
                JsonNode? value;
                if (given.ContainsKey(f.Name)) value = given[f.Name]?.DeepClone();
                else if (f.Spec.Default != null) value = f.Spec.Default.DeepClone();
                else { problem = $"{context} needs the argument '{f.Name}' ({f.Spec.Describe()})"; return null; }
                string? invalid = f.Spec.Validate(value, f.Name);
                if (invalid != null) { problem = invalid; return null; }
                args[f.Name] = value;
            }
            return args;
        }

        private Verdict CheckCreate(Proposal p, IReadOnlyList<Permission> can)
        {
            string typeName = p.Member ?? "";
            if (!_s.Declared.Types.TryGetValue(typeName, out var type)) return Verdict.Refuse($"unknown type '{typeName}'{Manifest.Suggest(typeName, _s.Declared.Types.Keys)}");
            if (type.Creatable == null) return Verdict.Refuse($"'{typeName}' cannot be created");
            if (!can.Any(c => c.Verb == Verb.Create && (c.Target == "*" || c.Target == typeName))) return Verdict.Refuse($"creating {typeName} is not allowed for this role");
            var args = CheckArgs(type.Creatable.Args, p.Args, "create " + typeName, out var problem);
            if (args == null) return Verdict.Refuse(problem!);
            int live = _s.CreatedCount(typeName);
            if (type.Creatable.Max.HasValue && live >= type.Creatable.Max.Value)
                return Verdict.Refuse($"at most {type.Creatable.Max.Value} {typeName} may exist from Kinloom at once ({live} now)");
            string id = _s.NextCreatedId(typeName);
            var effectArgs = new JsonObject { ["args"] = args };
            if (!string.IsNullOrWhiteSpace(p.Text)) effectArgs["name"] = p.Text;
            return Verdict.Allow(new Effect(EffectKind.Create, id, typeName, effectArgs, p.Source));
        }

        private Verdict CheckDestroy(Proposal p, IReadOnlyList<Permission> can)
        {
            var thing = Target(p, out var problem);
            if (thing == null) return Verdict.Refuse(problem!);
            if (thing.Id == Manifest.WorldId) return Verdict.Refuse("the world cannot be destroyed");
            bool own = thing.CreatedBy == p.Source && can.Any(c => c.Verb == Verb.Destroy && c.Target == "own");
            if (!own && !Permits(can, Verb.Destroy, thing, null, p.Self))
                return Verdict.Refuse(thing.CreatedBy == null
                    ? $"destroying {thing.Id} is not allowed for this role (it belongs to the game)"
                    : $"destroying {thing.Id} is not allowed for this role");
            return Verdict.Allow(new Effect(EffectKind.Destroy, thing.Id, null, null, p.Source));
        }

        /// <summary>Static check of a behavior a role wants to install: ownership and every lever its rules use.</summary>
        public IReadOnlyList<string> CheckBehavior(BehaviorDecl b, IReadOnlyList<Permission> can, string? self, string source)
        {
            var errors = new List<string>();
            var owner = b.Owner == null || b.Owner == "self" ? (self != null ? _s.Things.Find(self) : null) : _s.Things.Find(b.Owner);
            if (owner == null) { errors.Add(b.Owner == null ? "a behavior needs an owner thing" : $"unknown owner '{b.Owner}'"); return errors; }
            if (!can.Any(c => c.Verb == Verb.Behavior && c.Target != null && TargetMatches(c.Target, owner, self)))
                errors.Add($"installing behaviors on {owner.Id} is not allowed for this role");
            var parseErrors = new List<ManifestError>();
            Expressions.ExprCheck.Behavior(b, "behavior " + b.Id, parseErrors);
            errors.AddRange(parseErrors.Select(e => e.ToString()));
            foreach (var rule in b.Rules)
                foreach (var act in rule.Do)
                {
                    if (act.Set != null && !LeverAllowed(act.Set, Verb.Set, owner, can, self, errors)) continue;
                    if (act.Invoke != null) LeverAllowed(act.Invoke, Verb.Invoke, owner, can, self, errors);
                    if (act.Wake != null && _s.Declared.Roles.All(r => r.Id != act.Wake)) errors.Add($"unknown role '{act.Wake}'");
                }
            return errors;
        }

        private bool LeverAllowed(string reference, Verb verb, Thing owner, IReadOnlyList<Permission> can, string? self, List<string> errors)
        {
            int dot = reference.LastIndexOf('.');
            if (dot <= 0) { errors.Add($"'{reference}' must look like target.member"); return false; }
            string target = reference.Substring(0, dot), member = reference.Substring(dot + 1);
            var thing = target == "self" ? owner : _s.Things.Find(target);
            if (thing == null) { errors.Add($"unknown thing '{target}'"); return false; }
            bool exists = verb == Verb.Set ? thing.Type.Params.Find(member) != null || thing.Type.Open : thing.Type.Functions.ContainsKey(member);
            if (!exists) { errors.Add($"'{member}' is not a {(verb == Verb.Set ? "param" : "function")} of {thing.Type.Name}"); return false; }
            if (!Permits(can, verb, thing, member, self)) { errors.Add($"{(verb == Verb.Set ? "setting" : "calling")} {thing.Id}.{member} is not allowed for this role"); return false; }
            return true;
        }
    }
}
