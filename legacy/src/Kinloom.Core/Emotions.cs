namespace Kinloom.Core
{
    public sealed class Emotions
    {
        public float Fear { get; private set; }
        public float Anger { get; private set; }

        public void AddFear(float amount) => Fear = Personality.Clamp01(Fear + amount);
        public void AddAnger(float amount) => Anger = Personality.Clamp01(Anger + amount);

        public void Decay(float factor)
        {
            Fear *= factor;
            Anger *= factor;
        }
    }
}
