using System.Globalization;
using System.Text.Json.Nodes;

namespace Kinloom
{
    /// <summary>Reads any JSON number as a double. <c>GetValue&lt;double&gt;()</c> only works on parsed JSON or values created from a
    /// double; numbers created in code from int, long, float... (engine adapters do this) need this helper.</summary>
    public static class JsonNumber
    {
        public static double ToDouble(JsonNode node)
        {
            if (node is JsonValue v)
            {
                if (v.TryGetValue(out double d)) return d;
                if (v.TryGetValue(out long l)) return l;
                if (v.TryGetValue(out int i)) return i;
                if (v.TryGetValue(out float f)) return f;
                if (v.TryGetValue(out decimal m)) return (double)m;
            }
            return double.Parse(node.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture);
        }
    }
}
