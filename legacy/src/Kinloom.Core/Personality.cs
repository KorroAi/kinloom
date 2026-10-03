namespace Kinloom.Core
{
    /// <summary>Fixed traits. Never rewritten at runtime (prevents personality drift).</summary>
    public sealed class Personality
    {
        public Personality(float bravery, float sociability, float forgiveness)
        {
            Bravery = Clamp01(bravery);
            Sociability = Clamp01(sociability);
            Forgiveness = Clamp01(forgiveness);
        }

        public float Bravery { get; }
        public float Sociability { get; }
        public float Forgiveness { get; }

        internal static float Clamp01(float v) => v < 0f ? 0f : (v > 1f ? 1f : v);
    }
}
