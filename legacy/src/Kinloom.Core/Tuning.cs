namespace Kinloom.Core
{
    public sealed class Tuning
    {
        public float SightRadius { get; set; } = 10f;
        public float TalkRadius { get; set; } = 3f;
        public float ReachDistance { get; set; } = 2f;
        public float RumorBaseChance { get; set; } = 0.15f;
        public float RumorConfidenceFactor { get; set; } = 0.8f;
        public float ReportConfidence { get; set; } = 0.9f;
        public float MinRumorConfidence { get; set; } = 0.3f;
        public float MinCrimeConfidence { get; set; } = 0.5f;
        public float VictimWeight { get; set; } = 0.8f;
        public float WitnessWeight { get; set; } = 0.4f;
        public int FleeTicks { get; set; } = 2 * World.TicksPerHour;
        public int PursuitTicks { get; set; } = 2 * World.TicksPerHour;
        public float EmotionDecay { get; set; } = 0.97f;
        public float OpinionDrift { get; set; } = 0.0005f;
        public int AttackDamage { get; set; } = 3;
        /// <summary>Guards who catch the player for a crime journal an "arrest" (hosts turn it into fines or jail). Off by default.</summary>
        public bool Arrests { get; set; }
        /// <summary>Villagers at home between 00:00 and 05:00 are asleep and perceive nothing. Off by default.</summary>
        public bool Sleep { get; set; }
    }
}
