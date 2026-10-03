using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Kinloom.Llm;
using Kinloom.Core;

namespace Kinloom.Brain
{
    /// <summary>First half of a player line: what does the traveller DO with these words? (pay, hand over, threaten, strike, insult,
    /// accuse, ask someone along). The Arbiter checks each act against the real world and performs it; the NPC then answers
    /// knowing what truly happened — including a bluff with money the traveller does not have.</summary>
    public sealed class IntentJob : CognitionJob
    {
        private readonly string _text;
        private readonly int _ticket;

        public IntentJob(string npcId, string text, int ticket) : base("intent", "intent|" + npcId + "|" + ticket, 0, npcId, null)
        {
            _text = text;
            _ticket = ticket;
        }

        internal override LlmRequest? Build(Brain brain)
        {
            var w = brain.World;
            var npc = w.GetAgent(AgentId!);
            var near = w.Agents.Where(x => x.Present && !x.IsPlayer).Select(x => $"[{x.Id}] {x.Name}");
            var user = new StringBuilder()
                .Append($"In a game, the player (the traveller) says this to {npc.Name} [{npc.Id}]: \"{_text.Replace('"', '\'')}\"\n")
                .Append("People in the world: ").Append(string.Join(", ", near)).Append('\n')
                .Append("Items: ").Append(string.Join(", ", w.Items.Select(i => $"[{i.Id}] {i.Name}"))).Append("\n\n")
                .Append("List only the actions the traveller PERFORMS with these words right now (not promises, not questions, not hypotheticals). ")
                .Append("Most messages perform none. Any language.\n")
                .Append("JSON schema: {\"actions\": [ {\"type\": \"give_gold\", \"amount\": number} | {\"type\": \"give_item\", \"item\": id} | {\"type\": \"attack\"} | ")
                .Append("{\"type\": \"threaten\"} | {\"type\": \"insult\"} | {\"type\": \"accuse\", \"person\": id} | {\"type\": \"ask_follow\"} ]}");
            return new LlmRequest(Task, "You extract game actions from a player's message. Answer with one JSON object.", user.ToString(), 150, 0f);
        }

        internal override bool Apply(Brain brain, JsonElement root)
        {
            var facts = new List<string>();
            foreach (var act in Json.Arr(root, "actions").Take(3))
                Perform(brain, Json.Str(act, "type") ?? "", act, facts);
            brain.Enqueue(new DialogueJob(AgentId!, _text, _ticket, facts));
            return true;
        }

        internal override void Fallback(Brain brain)
        {
            // Without a model: the common case, paying, still works in English and French.
            var facts = new List<string>();
            var m = Regex.Match(_text, @"(?i)\b(?:give|gives|giving|donne|donnes|voici|voilà|take|prends)\b[^\d]{0,20}(\d+)\s*(?:gold|coins?|pi[eè]ces?|or|ryo)");
            if (m.Success)
            {
                using var doc = JsonDocument.Parse($"{{\"amount\": {m.Groups[1].Value}}}");
                Perform(brain, "give_gold", doc.RootElement, facts);
            }
            brain.Enqueue(new DialogueJob(AgentId!, _text, _ticket, facts));
        }

        private void Perform(Brain brain, string type, JsonElement act, List<string> facts)
        {
            var w = brain.World;
            var npc = w.GetAgent(AgentId!);
            var hero = brain.PlayerId != null ? w.FindAgent(brain.PlayerId) : null;
            if (hero == null) return;
            switch (type)
            {
                case "give_gold":
                    int amount = (int)(Json.Num(act, "amount") ?? 0);
                    if (amount <= 0) break;
                    if (hero.Gold < amount)
                    {
                        facts.Add($"The traveller claimed to give you {amount} gold but did not: the traveller only has {hero.Gold}. No coin changed hands.");
                        brain.Reject(hero.Id, Task, $"give_gold: the traveller has only {hero.Gold} gold", null);
                        break;
                    }
                    hero.Gold -= amount;
                    npc.Gold += amount;
                    if (w.Pack.HasDeed("pay")) Actions.PerformDeed(w, hero, "pay", npc.Id, null);
                    else w.Journal.Add(w.Tick, "deed", hero.Id, $"{hero.Name} pay -> {npc.Name} ({amount} gold)", null, npc.Id);
                    facts.Add($"The traveller gave you {amount} gold (you now have {npc.Gold}).");
                    brain.Emit("gold", hero.Id, npc.Id, amount.ToString(CultureInfo.InvariantCulture));
                    break;
                case "give_item":
                    string? itemId = Ids.Item(w, Json.Str(act, "item")) ?? Json.Str(act, "item");
                    var item = w.FindItem(itemId);
                    if (item == null || item.OwnerId != hero.Id)
                    {
                        facts.Add($"The traveller pretended to give you {(item?.Name ?? Json.Str(act, "item") ?? "something")} but does not have it.");
                        break;
                    }
                    Actions.Give(w, hero, npc, item.Id);
                    facts.Add($"The traveller handed you the {item.Name}.");
                    break;
                case "attack":
                    Combat.Attack(w, hero, npc, w.Tuning.AttackDamage);
                    facts.Add("The traveller just struck you!");
                    brain.Emit("strike", hero.Id, npc.Id, "");
                    break;
                case "threaten":
                    if (w.Pack.HasDeed("draw_weapon")) Actions.PerformDeed(w, hero, "draw_weapon", npc.Id, null);
                    facts.Add("The traveller threatened you, hand on the blade.");
                    break;
                case "insult":
                    if (w.Pack.HasDeed("insult")) Actions.PerformDeed(w, hero, "insult", npc.Id, null);
                    facts.Add("The traveller insulted you.");
                    break;
                case "accuse":
                    string? accused = Ids.Agent(w, Json.Str(act, "person"));
                    if (accused == null || accused == hero.Id) break;
                    bool solved = w.Quests.Accuse(w, hero.Id, npc.Id, accused);
                    facts.Add($"The traveller accuses {w.NameOf(accused)}" + (solved ? " — and it is the truth: you asked for exactly this, and now you know." : "."));
                    break;
                case "ask_follow":
                    facts.Add("The traveller asks you to come along (use the follow action if you agree).");
                    break;
            }
        }
    }
}
