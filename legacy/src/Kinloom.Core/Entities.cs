using System.Collections.Generic;

namespace Kinloom.Core
{
    public class Entity
    {
        public Entity(string id, string name, Vec2 position, IEnumerable<string>? tags = null)
        {
            Id = id;
            Name = name;
            Position = position;
            if (tags != null)
                foreach (var tag in tags) Tags.Add(tag);
        }

        public string Id { get; }
        public string Name { get; }
        public HashSet<string> Tags { get; } = new HashSet<string>();
        public Vec2 Position { get; set; }

        public bool Has(string tag) => Tags.Contains(tag);
    }

    public sealed class Place : Entity
    {
        public Place(string id, string name, Vec2 center, float radius, IEnumerable<string>? tags = null)
            : base(id, name, center, tags)
        {
            Radius = radius;
        }

        public float Radius { get; }

        public bool Contains(Vec2 point) => Position.DistanceTo(point) <= Radius;
    }

    public sealed class Item : Entity
    {
        public Item(string id, string name, Vec2 position, float value, string? ownerId, IEnumerable<string>? tags = null)
            : base(id, name, position, tags)
        {
            Value = value;
            OwnerId = ownerId;
            RightfulOwnerId = ownerId;
        }

        public float Value { get; }
        public string? OwnerId { get; set; }
        /// <summary>Who it belongs to by right (common knowledge). OwnerId is who holds it now (only witnesses know).</summary>
        public string? RightfulOwnerId { get; set; }
    }
}
