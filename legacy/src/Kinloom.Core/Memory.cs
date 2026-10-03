namespace Kinloom.Core
{
    /// <summary>What an agent believes happened. Not necessarily the truth (rumors lose confidence).</summary>
    public sealed class Memory
    {
        public Memory(string kind, string actorId, string? targetId, string? itemId, int deedTick,
            bool firsthand, string? sourceId, float confidence, float valence, bool isCrime, int entryId, bool isLie = false)
        {
            Kind = kind;
            ActorId = actorId;
            TargetId = targetId;
            ItemId = itemId;
            DeedTick = deedTick;
            Firsthand = firsthand;
            SourceId = sourceId;
            Confidence = confidence;
            Valence = valence;
            IsCrime = isCrime;
            EntryId = entryId;
            IsLie = isLie;
        }

        public string Kind { get; }
        public string ActorId { get; }
        public string? TargetId { get; }
        public string? ItemId { get; }
        public int DeedTick { get; }
        public bool Firsthand { get; }
        public string? SourceId { get; }
        public float Confidence { get; }
        public float Valence { get; }
        public bool IsCrime { get; }
        public int EntryId { get; }
        /// <summary>Truth flag for tools and the journal: the agent holding the memory does not know it is a lie.</summary>
        public bool IsLie { get; }

        /// <summary>Identifies the real-world deed, whoever remembers it.</summary>
        public string Key => $"{Kind}|{ActorId}|{TargetId}|{DeedTick}";

        public float Salience => System.Math.Abs(Valence) * Confidence + (IsCrime ? 0.2f : 0f);

        public Memory Retold(string sourceId, float confidenceFactor, int entryId) =>
            new Memory(Kind, ActorId, TargetId, ItemId, DeedTick, false, sourceId,
                Confidence * confidenceFactor, Valence, IsCrime, entryId, IsLie);
    }
}
