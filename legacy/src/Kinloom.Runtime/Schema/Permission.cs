using System;

namespace Kinloom.Schema
{
    public enum Verb { Set, Invoke, Create, Destroy, Say, Behavior, Generate, Media, Remember }

    /// <summary>One entry of a role's <c>can</c> list.
    /// Grammar: <c>set:&lt;target&gt;.&lt;param&gt;</c>, <c>invoke:&lt;target&gt;.&lt;function&gt;</c>, <c>create:&lt;Type&gt;</c>,
    /// <c>destroy:own</c> | <c>destroy:&lt;target&gt;</c>, <c>behavior:&lt;target&gt;</c>, <c>generate:&lt;id&gt;</c>, <c>media:&lt;kind&gt;</c>, <c>say</c>, <c>remember</c>.
    /// A target is <c>self</c>, a thing id, a type name, <c>tag:&lt;tag&gt;</c> or <c>*</c>; members and ids may be <c>*</c>.</summary>
    public sealed class Permission
    {
        private Permission(Verb verb, string? target, string? member, string source)
        {
            Verb = verb;
            Target = target;
            Member = member;
            Source = source;
        }

        public Verb Verb { get; }
        public string? Target { get; }
        public string? Member { get; }
        public string Source { get; }

        public override string ToString() => Source;

        /// <summary>Null with <paramref name="error"/> set when the text does not follow the grammar.</summary>
        public static Permission? TryParse(string text, out string? error)
        {
            error = null;
            string s = text.Trim();
            if (s == "say") return new Permission(Verb.Say, null, null, s);
            if (s == "remember") return new Permission(Verb.Remember, null, null, s);
            int colon = s.IndexOf(':');
            if (colon <= 0 || colon == s.Length - 1)
            {
                error = $"'{text}' is not a permission (expected e.g. set:self.speed, invoke:hud.show, create:Enemy, say)";
                return null;
            }
            string verb = s.Substring(0, colon), rest = s.Substring(colon + 1);
            switch (verb)
            {
                case "set":
                case "invoke":
                {
                    int dot = rest.LastIndexOf('.');
                    if (dot <= 0 || dot == rest.Length - 1)
                    {
                        error = $"'{text}' needs a target and a member, like {verb}:self.{(verb == "set" ? "speed" : "jump")}";
                        return null;
                    }
                    return new Permission(verb == "set" ? Verb.Set : Verb.Invoke, rest.Substring(0, dot), rest.Substring(dot + 1), s);
                }
                case "create": return new Permission(Verb.Create, rest, null, s);
                case "destroy": return new Permission(Verb.Destroy, rest, null, s);
                case "behavior": return new Permission(Verb.Behavior, rest, null, s);
                case "generate": return new Permission(Verb.Generate, rest, null, s);
                case "media": return new Permission(Verb.Media, rest, null, s);
                default:
                    error = $"unknown permission verb '{verb}' (expected set, invoke, create, destroy, behavior, generate, media, say or remember)";
                    return null;
            }
        }

        public static Permission Parse(string text) =>
            TryParse(text, out var error) ?? throw new FormatException(error);
    }
}
