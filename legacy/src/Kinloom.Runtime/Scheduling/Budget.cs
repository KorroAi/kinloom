using System;
using System.Collections.Generic;
using System.Linq;

namespace Kinloom.Scheduling
{
    /// <summary>Sliding-window limits on model calls (per role and global, per real minute) and spend (per real hour).</summary>
    internal sealed class Budget
    {
        private readonly Func<double> _clock;
        private readonly Queue<double> _global = new Queue<double>();
        private readonly Dictionary<string, Queue<double>> _perSource = new Dictionary<string, Queue<double>>();
        private readonly Queue<(double time, double cost)> _spend = new Queue<(double, double)>();

        public Budget(Func<double> clock) { _clock = clock; }

        /// <summary>Null when a call may start now, otherwise the reason it may not.</summary>
        public string? Deny(string source, int? perMinute, int globalPerMinute, double? maxCostPerHour)
        {
            double now = _clock();
            Trim(_global, now, 60);
            if (_global.Count >= globalPerMinute) return $"global limit of {globalPerMinute} calls per minute reached";
            if (perMinute.HasValue)
            {
                var q = Window(source);
                Trim(q, now, 60);
                if (q.Count >= perMinute.Value) return $"{source} limit of {perMinute.Value} calls per minute reached";
            }
            if (maxCostPerHour.HasValue)
            {
                while (_spend.Count > 0 && now - _spend.Peek().time > 3600) _spend.Dequeue();
                double spent = _spend.Sum(x => x.cost);
                if (spent >= maxCostPerHour.Value) return $"spending limit of {maxCostPerHour.Value} per hour reached";
            }
            return null;
        }

        public void RecordCall(string source)
        {
            double now = _clock();
            _global.Enqueue(now);
            Window(source).Enqueue(now);
        }

        public void RecordCost(double cost) => _spend.Enqueue((_clock(), cost));

        private Queue<double> Window(string source)
        {
            if (!_perSource.TryGetValue(source, out var q)) _perSource[source] = q = new Queue<double>();
            return q;
        }

        private static void Trim(Queue<double> q, double now, double seconds)
        {
            while (q.Count > 0 && now - q.Peek() >= seconds) q.Dequeue();
        }
    }
}
