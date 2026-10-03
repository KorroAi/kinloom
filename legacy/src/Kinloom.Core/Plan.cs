using System.Collections.Generic;

namespace Kinloom.Core
{
    /// <summary>Who an agent is, in words. Read by brains to stay in character; the rules ignore it.</summary>
    public sealed class Profile
    {
        public string Role { get; set; } = "";
        public string Bio { get; set; } = "";
        public string Traits { get; set; } = "";
        public string Style { get; set; } = "";
        public List<string> Goals { get; set; } = new List<string>();
        public List<string> Secrets { get; set; } = new List<string>();
    }

    /// <summary>The verbs a plan step can use. Deed-type verbs go through the pack, so witnesses see them.</summary>
    public static class Verbs
    {
        public const string Goto = "goto";     // target: place
        public const string Work = "work";     // target: place
        public const string Rest = "rest";     // target: place (usually home)
        public const string Talk = "talk";     // target: agent; journals a "meet" for brains to turn into a conversation
        public const string Give = "give";     // target: agent, item: owned by the actor
        public const string Steal = "steal";   // item: owned by someone else; target: its owner (optional)
        public const string Attack = "attack"; // target: agent

        public static readonly string[] All = { Goto, Work, Rest, Talk, Give, Steal, Attack };

        public static bool TargetsPlace(string verb) => verb == Goto || verb == Work || verb == Rest;

        public static bool IsKnown(string verb) => System.Array.IndexOf(All, verb) >= 0;
    }

    public sealed class PlanStep
    {
        public PlanStep(int hour, int minute, string verb, string? targetId, string? itemId = null, string? note = null)
        {
            Hour = hour;
            Minute = minute;
            Verb = verb;
            TargetId = targetId;
            ItemId = itemId;
            Note = note;
        }

        public int Hour { get; }
        public int Minute { get; }
        public string Verb { get; }
        public string? TargetId { get; }
        public string? ItemId { get; }
        public string? Note { get; }
        /// <summary>The step's action happened (or failed); movement-only steps are never "done", they just hold until the next step.</summary>
        public bool Done { get; set; }

        public int MinuteOfDay => Hour * 60 + Minute;

        public override string ToString() =>
            $"{Hour:00}:{Minute:00} {Verb}" + (TargetId != null ? $" {TargetId}" : "") + (ItemId != null ? $" ({ItemId})" : "")
            + (string.IsNullOrEmpty(Note) ? "" : $" — {Note}");
    }

    /// <summary>A day's plan: steps sorted by time. The active step is the last one whose time has come.</summary>
    public sealed class Plan
    {
        public Plan(string intention, int day, IEnumerable<PlanStep> steps, int? causeEntryId = null, int? untilMinute = null)
        {
            UntilMinute = untilMinute;
            Intention = intention;
            Day = day;
            CauseEntryId = causeEntryId;
            Steps = System.Linq.Enumerable.ToList(System.Linq.Enumerable.OrderBy(steps, s => s.MinuteOfDay)); // stable: same-time steps keep their order
        }

        public string Intention { get; }
        /// <summary>Day number the plan is for (0 = any day, used by tests and hand-written plans).</summary>
        public int Day { get; }
        public int? CauseEntryId { get; }
        /// <summary>For fixed plans (story beats): minute of day when the plan lets go. Null = until the end of the day.</summary>
        public int? UntilMinute { get; }

        /// <summary>True between the first step's time and UntilMinute.</summary>
        public bool InWindow(int minuteOfDay) =>
            Steps.Count > 0 && minuteOfDay >= Steps[0].MinuteOfDay && minuteOfDay < (UntilMinute ?? 24 * 60);
        public List<PlanStep> Steps { get; }

        /// <summary>Steps run in order once their time has come: an action step stays active until done;
        /// a movement step stays active until the next step is due. Null when every due step is done.</summary>
        public PlanStep? ActiveStep(int minuteOfDay)
        {
            for (int i = 0; i < Steps.Count; i++)
            {
                var step = Steps[i];
                if (step.MinuteOfDay > minuteOfDay) break;
                if (Verbs.TargetsPlace(step.Verb))
                {
                    bool nextDue = i + 1 < Steps.Count && Steps[i + 1].MinuteOfDay <= minuteOfDay;
                    if (!nextDue) return step;
                }
                else if (!step.Done) return step;
            }
            return null;
        }
    }
}
