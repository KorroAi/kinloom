using System.Collections.Generic;
using System.Text.Json.Nodes;
using Kinloom.Expressions;

namespace Kinloom.Behaviors
{
    /// <summary>Expression scope over the session: <c>self</c> (the owner), any thing id, <c>world</c>, and <c>event</c> when one is being handled.
    /// <c>event.type</c>, <c>event.time</c>, <c>event.source</c> and each data field (<c>event.who</c>, also <c>event.data.who</c>).</summary>
    internal sealed class ThingScope : IExprScope
    {
        private readonly KinloomSession _s;
        private Thing? _self;
        private Value _event;

        public ThingScope(KinloomSession session) { _s = session; }

        public double Now => _s.Now;

        public ThingScope With(Thing? self, GameEvent? e = null)
        {
            _self = self;
            _event = e == null ? Value.Null : EventValue(e);
            return this;
        }

        internal static Value EventValue(GameEvent e)
        {
            var o = new JsonObject();
            foreach (var p in e.Data) o[p.Key] = p.Value?.DeepClone();
            o["type"] = e.Type;
            o["time"] = e.Time;
            o["importance"] = e.Importance;
            o["source"] = e.Source;
            o["data"] = e.Data.DeepClone();
            return Value.From(o);
        }

        public Value Resolve(IReadOnlyList<string> path)
        {
            string root = path[0];
            if (root == "event") return _event.Navigate(path, 1);
            var thing = root == "self" ? _self : _s.Things.Find(root);
            if (thing == null) return Value.Null;
            if (path.Count == 1) return thing.AsValue();
            return thing.Get(path[1]).Navigate(path, 2);
        }
    }
}
