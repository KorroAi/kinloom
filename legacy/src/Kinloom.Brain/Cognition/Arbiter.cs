using System.Globalization;
using System.Text.Json;
using Kinloom.Core;

namespace Kinloom.Brain
{
    /// <summary>The safety layer between a model's proposals and the world. Nothing a model says changes the world
    /// unless it passes these rules; everything refused is journaled with the reason.</summary>
    public static class Arbiter
    {
        public const float AttackAngerThreshold = 0.4f;
        public const float AttackOpinionThreshold = -0.5f;

        /// <summary>Turns a proposed plan step into a legal one, or explains why not.</summary>
        public static PlanStep? Step(World world, Agent actor, JsonElement e, out string error, string? defaultTime = null)
        {
            error = "";
            string verb = (Json.Str(e, "verb") ?? "").ToLowerInvariant();
            string? rawTarget = Json.Str(e, "target");
            string? itemId = Ids.Item(world, Json.Str(e, "item")) ?? Json.Str(e, "item");
            string? note = Json.Str(e, "note");
            int? minute = Json.MinuteOfDay(Json.Str(e, "time") ?? defaultTime);
            if (minute == null) { error = $"unreadable time '{Json.Str(e, "time")}'"; return null; }
            if (!Verbs.IsKnown(verb)) { error = $"unknown verb '{verb}'"; return null; }

            string? targetId = (Verbs.TargetsPlace(verb) ? Ids.Place(world, rawTarget) : Ids.Agent(world, rawTarget)) ?? rawTarget;
            if (Verbs.TargetsPlace(verb))
            {
                if (world.FindPlace(targetId) == null) { error = $"{verb}: unknown place '{targetId}'"; return null; }
                return new PlanStep(minute.Value / 60, minute.Value % 60, verb, targetId, null, note);
            }

            if (verb == Verbs.Steal)
            {
                var item = world.FindItem(itemId);
                if (item == null) { error = $"steal: unknown item '{itemId}'"; return null; }
                if (item.OwnerId == actor.Id) { error = $"steal: {actor.Name} already owns {item.Name}"; return null; }
                return new PlanStep(minute.Value / 60, minute.Value % 60, verb, item.OwnerId, item.Id, note);
            }

            var target = world.FindAgent(targetId);
            if (target == null || !target.Active) { error = $"{verb}: '{targetId}' is not someone present"; return null; }
            if (target.Id == actor.Id) { error = $"{verb}: cannot target oneself"; return null; }
            if (verb == Verbs.Give)
            {
                var item = world.FindItem(itemId);
                if (item == null || item.OwnerId != actor.Id) { error = $"give: {actor.Name} does not own '{itemId}'"; return null; }
            }
            if (verb == Verbs.Attack && !MayAttack(actor, target)) { error = $"attack: {actor.Name} is not angry enough to attack {target.Name}"; return null; }
            return new PlanStep(minute.Value / 60, minute.Value % 60, verb, target.Id, verb == Verbs.Give ? itemId : null, note);
        }

        /// <summary>Violence needs a reason the rules can see: rage, hatred, or a raider.</summary>
        public static bool MayAttack(Agent actor, Agent target) =>
            actor.Mind.Emotions.Anger >= AttackAngerThreshold
            || actor.Mind.OpinionOf(target.Id) <= AttackOpinionThreshold
            || target.Has(WorldEvents.HostileTag);

        public static float Clamp(float value, float max) => value < -max ? -max : (value > max ? max : value);

        /// <summary>A model-proposed change of heart, clamped and journaled so Why() can explain it.</summary>
        public static int? ShiftOpinion(World world, Agent holder, string aboutId, float delta, float max, string? why, int? cause)
        {
            aboutId = Ids.Agent(world, aboutId) ?? aboutId;
            if (world.FindAgent(aboutId) == null || aboutId == holder.Id) return null;
            delta = Clamp(delta, max);
            if (System.Math.Abs(delta) < 0.001f) return null;
            float before = holder.Mind.OpinionOf(aboutId);
            holder.Mind.ShiftOpinion(aboutId, delta);
            float after = holder.Mind.OpinionOf(aboutId);
            int entry = world.Journal.Add(world.Tick, "opinion", holder.Id,
                string.Format(CultureInfo.InvariantCulture, "{0}'s opinion of {1}: {2:+0.00;-0.00;0.00} -> {3:+0.00;-0.00;0.00}{4}",
                    holder.Name, world.NameOf(aboutId), before, after, string.IsNullOrEmpty(why) ? "" : $" ({why})"), cause, aboutId);
            holder.Mind.SetOpinionCause(aboutId, entry);
            return entry;
        }
    }
}
