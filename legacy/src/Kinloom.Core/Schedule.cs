using System.Collections.Generic;

namespace Kinloom.Core
{
    public sealed class Schedule
    {
        private readonly List<KeyValuePair<int, string>> _slots = new List<KeyValuePair<int, string>>();

        public Schedule Add(int startHour, string placeId)
        {
            _slots.Add(new KeyValuePair<int, string>(startHour, placeId));
            _slots.Sort((a, b) => a.Key.CompareTo(b.Key));
            return this;
        }

        /// <summary>Place for this hour; before the first slot of the day, the last slot of the previous day applies.</summary>
        public string? PlaceAt(int hour)
        {
            if (_slots.Count == 0) return null;
            string placeId = _slots[_slots.Count - 1].Value;
            foreach (var slot in _slots)
                if (slot.Key <= hour) placeId = slot.Value;
            return placeId;
        }
    }
}
