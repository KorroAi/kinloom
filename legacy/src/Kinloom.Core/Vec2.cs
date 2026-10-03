namespace Kinloom.Core
{
    public readonly struct Vec2
    {
        public readonly float X;
        public readonly float Y;

        public Vec2(float x, float y)
        {
            X = x;
            Y = y;
        }

        public float DistanceTo(Vec2 other)
        {
            float dx = other.X - X, dy = other.Y - Y;
            return (float)System.Math.Sqrt(dx * dx + dy * dy);
        }

        public Vec2 MoveTowards(Vec2 target, float maxStep)
        {
            float d = DistanceTo(target);
            if (d <= maxStep || d == 0f) return target;
            float t = maxStep / d;
            return new Vec2(X + (target.X - X) * t, Y + (target.Y - Y) * t);
        }

        public Vec2 Offset(float dx, float dy) => new Vec2(X + dx, Y + dy);

        public override string ToString() => System.FormattableString.Invariant($"({X:0.#}, {Y:0.#})");
    }
}
