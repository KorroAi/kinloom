namespace Kinloom.Core
{
    public sealed class Stimulus
    {
        public Stimulus(DeedDefinition deed, string actorId, string? targetId, string? itemId, Vec2 position, int tick)
        {
            Deed = deed;
            ActorId = actorId;
            TargetId = targetId;
            ItemId = itemId;
            Position = position;
            Tick = tick;
        }

        public DeedDefinition Deed { get; }
        public string ActorId { get; }
        public string? TargetId { get; }
        public string? ItemId { get; }
        public Vec2 Position { get; }
        public int Tick { get; }
    }
}
