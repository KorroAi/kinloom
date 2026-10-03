namespace Kinloom.Core
{
    public enum IntentKind { Routine, Flee, Approach, Report }

    public sealed class Intent
    {
        public Intent(IntentKind kind, string? targetId, string? memoryKey, int untilTick, int? causeEntryId)
        {
            Kind = kind;
            TargetId = targetId;
            MemoryKey = memoryKey;
            UntilTick = untilTick;
            CauseEntryId = causeEntryId;
        }

        public IntentKind Kind { get; }
        public string? TargetId { get; }
        public string? MemoryKey { get; }
        public int UntilTick { get; }
        public int? CauseEntryId { get; }

        public static Intent Routine() => new Intent(IntentKind.Routine, null, null, int.MaxValue, null);

        public override string ToString() => TargetId == null ? Kind.ToString() : $"{Kind} {TargetId}";
    }
}
