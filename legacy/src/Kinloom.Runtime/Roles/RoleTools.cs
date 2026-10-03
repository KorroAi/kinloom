using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Kinloom.Llm;
using Kinloom.Schema;

namespace Kinloom.Roles
{
    /// <summary>The generic tools a role can call. They are the same for every game; the prompt lists which things,
    /// params and functions each one may touch. Only tools the role's permissions allow are offered.</summary>
    internal static class RoleTools
    {
        private static JsonObject Schema(string json) => JsonNode.Parse(json)!.AsObject();

        private static readonly Dictionary<string, (Verb verb, LlmTool tool)> All = new Dictionary<string, (Verb, LlmTool)>
        {
            ["set_param"] = (Verb.Set, new LlmTool("set_param", "Change a param of a thing (see the allowed params and their ranges).",
                Schema(@"{""type"":""object"",""properties"":{""thing"":{""type"":""string"",""description"":""thing id, or self""},""param"":{""type"":""string""},""value"":{""description"":""new value within the allowed range""}},""required"":[""thing"",""param"",""value""]}"))),
            ["invoke"] = (Verb.Invoke, new LlmTool("invoke", "Call a function of a thing with its arguments.",
                Schema(@"{""type"":""object"",""properties"":{""thing"":{""type"":""string"",""description"":""thing id, or self""},""function"":{""type"":""string""},""args"":{""type"":""object"",""description"":""named arguments""}},""required"":[""thing"",""function""]}"))),
            ["create"] = (Verb.Create, new LlmTool("create", "Create a new thing of an allowed type.",
                Schema(@"{""type"":""object"",""properties"":{""type"":{""type"":""string""},""args"":{""type"":""object""},""name"":{""type"":""string"",""description"":""optional display name""}},""required"":[""type""]}"))),
            ["destroy"] = (Verb.Destroy, new LlmTool("destroy", "Remove a thing you are allowed to remove.",
                Schema(@"{""type"":""object"",""properties"":{""thing"":{""type"":""string""}},""required"":[""thing""]}"))),
            ["say"] = (Verb.Say, new LlmTool("say", "Say a line out loud in the game (players see or hear it).",
                Schema(@"{""type"":""object"",""properties"":{""text"":{""type"":""string"",""maxLength"":600},""to"":{""type"":""string"",""description"":""optional: who you address""}},""required"":[""text""]}"))),
            ["set_behavior"] = (Verb.Behavior, new LlmTool("set_behavior", "Install or replace instant rules that run every frame without you.",
                Schema(@"{""type"":""object"",""properties"":{""id"":{""type"":""string""},""owner"":{""type"":""string"",""description"":""thing id the rules belong to (default: self)""},""rules"":{""type"":""array"",""items"":{""type"":""object"",""properties"":{""when"":{""type"":""string""},""do"":{""type"":""array"",""items"":{""type"":""object""}},""cooldown"":{""type"":""number""}},""required"":[""when"",""do""]}}},""required"":[""id"",""rules""]}"))),
            ["remove_behavior"] = (Verb.Behavior, new LlmTool("remove_behavior", "Remove a behavior you installed earlier.",
                Schema(@"{""type"":""object"",""properties"":{""id"":{""type"":""string""}},""required"":[""id""]}"))),
            ["remember"] = (Verb.Remember, new LlmTool("remember", "Keep a note in your long-term memory.",
                Schema(@"{""type"":""object"",""properties"":{""text"":{""type"":""string""},""importance"":{""type"":""number"",""minimum"":0,""maximum"":1}},""required"":[""text""]}"))),
            ["generate"] = (Verb.Generate, new LlmTool("generate", "Ask for structured content from an allowed generator; the game receives the result.",
                Schema(@"{""type"":""object"",""properties"":{""generator"":{""type"":""string""},""brief"":{""type"":""string"",""description"":""what you want, in a sentence or two""}},""required"":[""generator"",""brief""]}"))),
            ["request_media"] = (Verb.Media, new LlmTool("request_media", "Ask the game's media tools for an asset (image, sound, voice, 3D model...).",
                Schema(@"{""type"":""object"",""properties"":{""kind"":{""type"":""string""},""prompt"":{""type"":""string""},""spec"":{""type"":""object"",""description"":""format, size, voice... as the game expects""}},""required"":[""kind"",""prompt""]}"))),
        };

        public static IReadOnlyCollection<string> Names => All.Keys;

        /// <summary>The tools a role may call. For a role without a body, schemas never mention <c>self</c>.</summary>
        public static List<LlmTool> For(IReadOnlyList<Permission> can, bool hasSelf = true) =>
            All.Values.Where(t => can.Any(c => c.Verb == t.verb)).Select(t => hasSelf ? t.tool : WithoutSelf(t.tool)).ToList();

        private static LlmTool WithoutSelf(LlmTool tool)
        {
            string json = tool.Parameters.ToJsonString()
                .Replace("thing id, or self", "thing id")
                .Replace("thing id the rules belong to (default: self)", "thing id the rules belong to (required)");
            return new LlmTool(tool.Name, tool.Description, JsonNode.Parse(json)!.AsObject());
        }

        public static bool Allowed(string tool, IReadOnlyList<Permission> can) =>
            All.TryGetValue(tool, out var t) && can.Any(c => c.Verb == t.verb);
    }
}
