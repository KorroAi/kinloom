using System.Text.RegularExpressions;
using Kinloom.Core;

namespace Kinloom.Game;

/// <summary>Turns technical journal entries into short story lines for the player ("Berta runs to tell the guard.").
/// Unknown formats fall back to the raw text, so nothing is ever hidden.</summary>
public static class Narrator
{
    public static string Short(string name)
    {
        var parts = name.Split(' ');
        return parts.Length > 1 && parts[0] is "The" or "Old" or "Captain" ? parts[1] : parts[0];
    }

    public static string Narrate(JournalEntry e, World world, Agent player)
    {
        string names = string.Join("|", world.Agents.Select(a => a.Name).Append("?").OrderByDescending(n => n.Length).Select(Regex.Escape));
        string items = string.Join("|", world.Items.Select(i => i.Name).OrderByDescending(n => n.Length).Select(Regex.Escape));
        string N = $"(?:{names})";
        string I = items.Length > 0 ? $"(?:{items})" : "(?!)";
        string Who(string name) => name == player.Name ? "you" : Short(name);

        Match m;
        switch (e.Kind)
        {
            case "deed":
                m = Regex.Match(e.Text, $"^(?<a>{N}) (?<k>\\w+)(?: -> (?<t>{N}))?(?: \\((?<i>{I})\\))?$");
                if (!m.Success) break;
                string target = m.Groups["t"].Success ? Who(m.Groups["t"].Value) : "";
                if (m.Groups["a"].Value != player.Name) return $"{Who(m.Groups["a"].Value)} does something: {m.Groups["k"].Value}.";
                return m.Groups["k"].Value switch
                {
                    "steal" when m.Groups["i"].Success => target.Length > 0 ? $"You steal the {m.Groups["i"].Value} from {target}." : $"You take the {m.Groups["i"].Value}.",
                    "draw_weapon" => "You draw your weapon.",
                    "help" => $"You help {target}.",
                    "pay" => $"You pay {target}.",
                    var k => $"You {k.Replace('_', ' ')} {target}".TrimEnd() + ".",
                };

            case "witness":
                m = Regex.Match(e.Text, $"^(?<w>{N}) saw: (?<a>{N}) (?<k>\\w+)(?: -> (?<t>{N}))?(?: \\((?<i>{I})\\))?$");
                if (!m.Success) break;
                string doer = Who(m.Groups["a"].Value), onWhom = m.Groups["t"].Success ? Who(m.Groups["t"].Value) : "";
                string what = m.Groups["k"].Value switch
                {
                    "steal" when m.Groups["i"].Success => $"steal the {m.Groups["i"].Value}",
                    "draw_weapon" => "draw a weapon",
                    "help" => $"help {onWhom}",
                    "pay" => $"pay {onWhom}",
                    var k => k.Replace('_', ' '),
                };
                return $"{Who(m.Groups["w"].Value)} saw {doer} {what}.";

            case "opinion":
                m = Regex.Match(e.Text, $"^(?<a>{N})'s opinion of (?<o>{N}): (?<from>[-+]?[\\d.]+) -> (?<to>[-+]?[\\d.]+)$");
                if (!m.Success) break;
                bool warmer = float.Parse(m.Groups["to"].Value, System.Globalization.CultureInfo.InvariantCulture) > float.Parse(m.Groups["from"].Value, System.Globalization.CultureInfo.InvariantCulture);
                return $"{Who(m.Groups["a"].Value)} now likes {Who(m.Groups["o"].Value)} {(warmer ? "more" : "less")} ({m.Groups["to"].Value}).";

            case "reaction":
                m = Regex.Match(e.Text, $"^(?<a>{N}) decides to (?<c>\\w+) \\(");
                if (m.Success)
                {
                    string a = Who(m.Groups["a"].Value);
                    return m.Groups["c"].Value switch
                    {
                        "flee" => $"{a} runs away in fear.",
                        "report" => $"{a} runs to tell the guard.",
                        "confront" => $"{a} comes after you.",
                        "scold" => $"{a} glares at you.",
                        var c => $"{a} decides to {c}.",
                    };
                }
                m = Regex.Match(e.Text, $"^(?<a>{N}) (?<v>is grateful|approves) \\(");
                if (m.Success) return $"{Who(m.Groups["a"].Value)} {m.Groups["v"].Value}.";
                m = Regex.Match(e.Text, $"^(?<g>{N}) recognizes (?<o>{N}) \\((?:saw it|heard from (?<s>{N})): \\w+\\)$");
                if (m.Success)
                    return m.Groups["s"].Success
                        ? $"{Who(m.Groups["g"].Value)} recognizes {Who(m.Groups["o"].Value)}, thanks to {Who(m.Groups["s"].Value)}."
                        : $"{Who(m.Groups["g"].Value)} recognizes {Who(m.Groups["o"].Value)}.";
                break;

            case "rumor":
                m = Regex.Match(e.Text, $"^(?<s>{N}) tells (?<l>{N}): (?<a>{N}) (?<k>\\w+)(?: -> (?<t>{N}))?$");
                if (m.Success) return Gossip(m.Groups["s"].Value, m.Groups["l"].Value, m.Groups["a"].Value, m.Groups["k"].Value, m.Groups["t"].Success ? m.Groups["t"].Value : null, Who, player);
                break;

            case "report":
                m = Regex.Match(e.Text, $"^(?<s>{N}) reports to (?<l>{N}): (?<a>{N}) (?<k>\\w+)$");
                if (m.Success) return Gossip(m.Groups["s"].Value, m.Groups["l"].Value, m.Groups["a"].Value, m.Groups["k"].Value, m.Groups["s"].Value, Who, player);
                break;

            case "consequence":
                m = Regex.Match(e.Text, $"^(?<g>{N}) confronts (?<o>{N}) about (?<k>[\\w ]+)$");
                if (m.Success)
                {
                    string about = m.Groups["k"].Value switch { "steal" => "the theft", "draw_weapon" => "your weapon", _ => "what you did" };
                    return $"{Who(m.Groups["g"].Value)} confronts {Who(m.Groups["o"].Value)} about {about}.";
                }
                m = Regex.Match(e.Text, $"^(?<i>{I}) returned to (?<o>{N})$");
                if (m.Success) return $"The {m.Groups["i"].Value} goes back to {Who(m.Groups["o"].Value)}.";
                m = Regex.Match(e.Text, $"^(?<t>{N}) sells to (?<b>{N}) for (?<p>[\\d.]+) \\(base (?<base>[\\d.]+),");
                if (m.Success)
                {
                    string price = m.Groups["p"].Value, usual = m.Groups["base"].Value;
                    string note = price == usual ? "" : $" (usually {usual})";
                    return $"{Who(m.Groups["t"].Value)} sells to {Who(m.Groups["b"].Value)} for {price}{note}.";
                }
                m = Regex.Match(e.Text, $"^(?<t>{N}) refuses to serve (?<b>{N})");
                if (m.Success) return $"{Who(m.Groups["t"].Value)} refuses to serve {Who(m.Groups["b"].Value)}.";
                break;
        }
        return e.Text.Replace(player.Name, "you");
    }

    private static string Gossip(string speaker, string listener, string actor, string kind, string? target, Func<string, string> who, Agent player)
    {
        string s = who(speaker), l = who(listener);
        string subject = actor == player.Name ? "you" : who(actor);
        bool aboutPlayer = subject == "you";
        return kind switch
        {
            "steal" when aboutPlayer && (target == null || target == speaker) => $"{s} tells {l} you're a thief.",
            "steal" when aboutPlayer => $"{s} tells {l} you robbed {who(target!)}.",
            "draw_weapon" when aboutPlayer => $"{s} tells {l} you drew a weapon in the village.",
            "help" when aboutPlayer => target == null || target == speaker ? $"{s} tells {l} you're kind." : $"{s} tells {l} you helped {who(target)}.",
            "pay" when aboutPlayer => target == null || target == speaker ? $"{s} tells {l} you paid your debt." : $"{s} tells {l} you paid {who(target)} back.",
            _ => $"{s} tells {l} about {subject} ({kind.Replace('_', ' ')}).",
        };
    }
}
