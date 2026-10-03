namespace Kinloom.Core
{
    /// <summary>Seeded xorshift32: identical sequence on every runtime (Unity, .NET).</summary>
    public sealed class DeterministicRandom
    {
        private uint _state;

        public DeterministicRandom(int seed)
        {
            _state = (uint)seed;
            if (_state == 0) _state = 0x9E3779B9u;
        }

        public uint NextUInt()
        {
            uint x = _state;
            x ^= x << 13;
            x ^= x >> 17;
            x ^= x << 5;
            _state = x;
            return x;
        }

        public float NextFloat() => (NextUInt() >> 8) * (1f / 16777216f);

        public bool Chance(float probability) => NextFloat() < probability;
    }
}
