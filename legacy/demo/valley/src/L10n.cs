using System.Text.RegularExpressions;
using Godot;
using Kinloom.Core;

namespace Valley;

/// <summary>English/French for the game layer. NPC words come from the Brain in the chosen language;
/// this covers the UI and the rule-level journal lines (which Core writes in English).</summary>
public static class L10n
{
    public static bool French { get; set; }
    public static string BrainLanguage => French ? "French" : "English";

    public static bool DefaultFrench()
    {
        string? env = System.Environment.GetEnvironmentVariable("KINLOOM_LANGUAGE");
        if (!string.IsNullOrEmpty(env)) return env.StartsWith("fr", StringComparison.OrdinalIgnoreCase);
        return OS.GetLocaleLanguage() == "fr";
    }

    private static readonly Dictionary<string, string> Fr = new()
    {
        ["WASD/ZQSD move · E talk · R take · Space strike · Shift dash · H heal · Tab minds · Q quests · C chronicle · T time · F11 window"] =
            "ZQSD/WASD bouger · E parler · R prendre · Espace frapper · Maj esquive · H soin · Tab esprits · Q requêtes · C chronique · T temps · F11 fenêtre",
        ["THE VALLEY"] = "LA VALLÉE",
        ["A KINLOOM BRAIN DEMO"] = "UNE DÉMO KINLOOM BRAIN",
        ["ASAGIRI VALLEY"] = "LA VALLÉE D'ASAGIRI",
        ["Its people think, talk, scheme and remember. What will they say about you?"] = "Ses habitants pensent, parlent, complotent et se souviennent. Que diront-ils de toi ?",
        ["Press Enter to begin"] = "Appuie sur Entrée pour commencer",
        ["L: language — English"] = "L : langue — français",
        ["Three days in the valley. Talk, help, steal, fight: every villager will remember, and tell the others."] =
            "Trois jours dans la vallée. Parle, aide, vole, combats : chaque villageois s'en souviendra, et le racontera.",
        ["Minds powered by {0} through Kinloom Brain"] = "Esprits animés par {0} via Kinloom Brain",
        ["No API key found: villagers run on Kinloom rules only"] = "Aucune clé API : les villageois suivent seulement les règles Kinloom",
        ["mind: {0}"] = "esprits : {0}",
        ["mind: rules only (set DEEPSEEK_API_KEY)"] = "esprits : règles seules (définis DEEPSEEK_API_KEY)",
        ["Say anything… (Enter to speak, Esc to leave)"] = "Dis ce que tu veux… (Entrée pour parler, Échap pour partir)",
        ["Day {0}"] = "Jour {0}",
        ["Autumn in Asagiri. The rice tax is due, and the lantern festival is near."] = "L'automne à Asagiri. L'impôt du riz est dû, et la fête des lanternes approche.",
        ["You arrive in Asagiri by the forest road. The villagers don't know you yet — but they will notice everything you do."] =
            "Tu arrives à Asagiri par la route de la forêt. Les villageois ne te connaissent pas encore — mais ils remarqueront tout ce que tu fais.",
        ["Nobody close enough to talk to."] = "Personne d'assez proche pour parler.",
        ["Time flows x{0}"] = "Le temps s'écoule x{0}",
        ["Nothing within reach to take."] = "Rien à portée de main.",
        ["You take the {0}… and {1} saw you."] = "Tu prends : {0}… et {1} t'ont vu.",
        ["You take the {0}. Nobody seems to have noticed… this time."] = "Tu prends : {0}. Personne ne semble l'avoir remarqué… cette fois.",
        ["1 person"] = "1 personne",
        ["{0} people"] = "{0} personnes",
        ["Knocked out"] = "Assommé",
        ["Everything goes dark…"] = "Tout devient noir…",
        ["You wake up in Sen's hut. Someone carried you here."] = "Tu te réveilles dans la hutte de Sen. Quelqu'un t'a porté jusqu'ici.",
        ["{0} looks at you. ({1} towards you.)"] = "{0} te regarde. ({1})",
        ["What's the news?"] = "Quoi de neuf ?",
        ["Can I help you?"] = "Je peux t'aider ?",
        ["Tell me about yourself."] = "Parle-moi de toi.",
        ["Accept request"] = "Accepter la requête",
        ["Buy (refused)"] = "Acheter (refusé)",
        ["Buy ({0} g)"] = "Acheter ({0} or)",
        ["Give 5 g"] = "Donner 5 or",
        ["Give {0}"] = "Donner : {0}",
        ["You:"] = "Toi :",
        ["Request accepted"] = "Requête acceptée",
        ["({0} refuses to serve you.)"] = "({0} refuse de te servir.)",
        ["You can't afford it ({0} g)."] = "Tu n'as pas de quoi payer ({0} or).",
        ["(you pay {0} g{1} and feel better)"] = "(tu paies {0} or{1} et tu te sens mieux)",
        [", more than the usual price"] = ", plus que le prix habituel",
        ["You give 5 gold to {0}."] = "Tu donnes 5 pièces d'or à {0}.",
        ["You hand the {0} to {1}."] = "Tu remets {0} à {1}.",
        ["MIND"] = "ESPRIT",
        ["INTENTION"] = "INTENTION",
        ["NOW"] = "EN CE MOMENT",
        ["WANTS"] = "VEUT",
        ["THOUGHTS"] = "PENSÉES",
        ["KNOWS"] = "SAIT",
        ["FEELINGS"] = "SENTIMENTS",
        ["WHY?"] = "POURQUOI ?",
        ["(causal chain of the latest decision)"] = "(chaîne causale de la dernière décision)",
        ["following the usual routine"] = "suit sa routine habituelle",
        ["(reflex)"] = "(réflexe)",
        ["Dead."] = "Mort.",
        ["saw it"] = "l'a vu",
        ["heard from {0}"] = "entendu de {0}",
        ["← a lie"] = "← un mensonge",
        ["You"] = "Toi",
        ["Requests"] = "Requêtes",
        ["Nobody has asked you for anything yet. Talk to people; their troubles are real."] = "Personne ne t'a encore rien demandé. Parle aux gens : leurs soucis sont réels.",
        ["reward {0} g"] = "récompense {0} or",
        ["No chronicle yet: the storyteller writes one each night."] = "Pas encore de chronique : le conteur en écrit une chaque nuit.",
        ["THE CHRONICLE OF ASAGIRI"] = "LA CHRONIQUE D'ASAGIRI",
        ["Enter to continue"] = "Entrée pour continuer",
        ["THE LEGEND OF THE TRAVELLER"] = "LA LÉGENDE DU VOYAGEUR",
        ["Trusted by:"] = "Apprécié de :",
        ["Resented by:"] = "Détesté de :",
        ["no one"] = "personne",
        ["Requests fulfilled: {0}   ·   Crimes remembered by villagers: {1}"] = "Requêtes accomplies : {0}   ·   Crimes dont les villageois se souviennent : {1}",
        ["Enter to live another story"] = "Entrée pour vivre une autre histoire",
        ["The last night"] = "La dernière nuit",
        ["Your time in Asagiri is over. The valley decides how it will remember you…"] = "Ton séjour à Asagiri s'achève. La vallée décide comment elle se souviendra de toi…",
        ["{0} mind(s) thinking…"] = "{0} esprit(s) pensent…",
        ["time x{0}"] = "temps x{0}",
        ["Lantern Festival"] = "Fête des lanternes",
        ["A Storm Rolls In"] = "Une tempête approche",
        ["Bandit Raid!"] = "Raid de bandits !",
        ["A Stranger Arrives"] = "Un étranger arrive",
        ["Sickness"] = "Maladie",
        ["Request fulfilled"] = "Requête accomplie",
        ["needs your help:"] = "a besoin de ton aide :",
        ["(talk to them)"] = "(va lui parler)",
        ["thinks:"] = "pense :",
        ["Word spreads"] = "La rumeur court",
        ["(a lie)"] = "(un mensonge)",
        ["A lie is told."] = "Un mensonge est dit.",
        ["Kinloom arbiter blocked {0}: {1}"] = "L'arbitre Kinloom a bloqué {0} : {1}",
        ["{0} emerges from the forest."] = "{0} surgit de la forêt.",
        ["A stranger arrives: {0}."] = "Un étranger arrive : {0}.",
        ["You defeat {0} and recover {1} gold."] = "Tu terrasses {0} et récupères {1} pièces d'or.",
        ["steals"] = "vole",
        ["from"] = "à",
        ["you"] = "toi",
        ["♥ trust"] = "♥ confiance",
        ["✖ trust"] = "✖ confiance",
        ["Event over: {0}"] = "Fin de l'événement : {0}",
        ["Carrying: {0}"] = "Sac : {0}",
        ["You find a {0}."] = "Tu trouves : {0}.",
        ["Nothing to heal with. Buy food, or ask Sen the healer."] = "Rien pour te soigner. Achète à manger, ou va voir Sen.",
        ["You use the {0} (+{1} health)."] = "Tu utilises : {0} (+{1} vie).",
        ["{0} seizes your arm: \"You are under arrest.\""] = "{0} te saisit le bras : « Tu es en état d'arrestation. »",
        ["Pay the fine ({0} g)"] = "Payer l'amende ({0} or)",
        ["Go to jail (6 hours)"] = "Aller en cellule (6 heures)",
        ["Resist"] = "Résister",
        ["Not enough gold for the fine."] = "Pas assez d'or pour l'amende.",
        ["You pay the fine. The village will remember, but you walk free."] = "Tu paies l'amende. Le village s'en souviendra, mais tu es libre.",
        ["Six hours later…"] = "Six heures plus tard…",
        ["The cell door creaks open. The village has had time to talk."] = "La porte de la cellule grince. Le village a eu le temps de parler.",
        ["You pull free and draw steel. Everyone saw."] = "Tu te dégages et tu dégaines. Tout le monde a vu.",
        ["Hero of the valley"] = "Héros de la vallée",
        ["Well liked"] = "Apprécié",
        ["A stranger"] = "Inconnu",
        ["Suspect"] = "Suspect",
        ["Outcast"] = "Paria",
        ["Reputation"] = "Réputation",
        ["{0} people need help — look for the red ! and talk to them (E)."] = "{0} personnes ont besoin d'aide — cherche le ! rouge et parle-leur (E).",
        ["Explore, talk, and see what the valley needs."] = "Explore, parle, et découvre ce dont la vallée a besoin.",
        ["Bring the {0} to {1} (talk, then Give)."] = "Rapporte {0} à {1} (parle-lui, puis Donner).",
        ["Find the {0} for {1}."] = "Trouve {0} pour {1}.",
        ["Deliver the {0} to {1}."] = "Livre {0} à {1}.",
        ["Defeat {0} ({1}'s request)."] = "Vaincs {0} (requête de {1}).",
        ["Find out who did it, then tell {0} (write it)."] = "Découvre le coupable, puis dis-le à {0} (écris-le).",
        ["Win {0} back for {1}."] = "Réconcilie {0} avec {1}.",
        ["Keep {0} alive ({1})."] = "Garde {0} en vie ({1}).",
        ["Teach {0} a lesson ({1})."] = "Donne une leçon à {0} ({1}).",
        ["You pick up the {0}."] = "Tu ramasses : {0}.",
        ["dodged"] = "esquivé",
        ["You recover the {0}. Its owner will want it back."] = "Tu récupères : {0}. Son propriétaire voudra le retrouver.",
        // roles (neutral French: activities rather than gendered job nouns)
        ["Mira's ten-year-old niece"] = "enfant de la famille de Mira, dix ans",
        ["a drifter who lives by the river"] = "vit au bord de la rivière, sans attaches",
        ["a travelling silk merchant"] = "vend de la soie de ville en ville",
        ["a wandering ronin"] = "rōnin sans maître",
        ["bandit leader"] = "chef de la bande",
        ["bandit"] = "membre de la bande",
        ["captain of the guard"] = "capitaine de la garde",
        ["keeper of the tea house"] = "tient le salon de thé",
        ["rice farmer"] = "cultive le riz",
        ["the baker"] = "tient la boulangerie",
        ["the blacksmith"] = "tient la forge",
        ["the old healer"] = "soigne le village depuis trois générations",
        ["the shrine monk"] = "garde le sanctuaire",
        ["the village headman"] = "chef du village",
        ["young guard"] = "jeune recrue de la garde",
    };

    public static string T(string en) => French && Fr.TryGetValue(en, out var fr) ? fr : en;

    public static string T(string en, params object[] args) => string.Format(T(en), args);

    public static string Opinion(float o) => !French ? PromptWord(o) :
        o <= -0.6f ? "déteste" : o <= -0.3f ? "n'aime pas" : o <= -0.1f ? "se méfie" : o < 0.1f ? "neutre" : o < 0.3f ? "apprécie" : o < 0.6f ? "fait confiance" : "adore";

    private static string PromptWord(float o) => Kinloom.Brain.PromptBuilder.OpinionWord(o);

    public static string Deed(string kind) => !French ? kind : kind switch
    {
        "steal" => "vole",
        "attack" => "attaque",
        "kill" => "tue",
        "defend" => "défend le village contre",
        "give" => "donne à",
        "pay" => "paie",
        "help" => "aide",
        "insult" => "insulte",
        "draw_weapon" => "dégaine son arme",
        _ => kind,
    };

    public static string QuestKind(string kind) => !French ? kind.Replace('_', ' ') : kind switch
    {
        QuestKinds.RetrieveItem => "récupérer un objet",
        QuestKinds.DeliverItem => "livrer un objet",
        QuestKinds.Punish => "punir",
        QuestKinds.Persuade => "réconcilier",
        QuestKinds.Protect => "protéger",
        QuestKinds.Accuse => "démasquer",
        QuestKinds.Slay => "vaincre",
        _ => kind,
    };

    public static string Status(QuestStatus s) => !French ? s.ToString().ToUpperInvariant() : s switch
    {
        QuestStatus.Offered => "PROPOSÉE",
        QuestStatus.Active => "EN COURS",
        QuestStatus.Completed => "ACCOMPLIE",
        _ => "ÉCHOUÉE",
    };

    public static string EventName(string kind) => !French ? kind.Replace('_', ' ') : kind switch
    {
        WorldEvents.Festival => "fête",
        WorldEvents.Storm => "tempête",
        WorldEvents.BanditRaid => "raid de bandits",
        WorldEvents.StrangerArrives => "étranger",
        WorldEvents.Illness => "maladie",
        _ => kind,
    };

    /// <summary>A memory as a sentence ("Tob vole Rice sack à Mira").</summary>
    public static string Describe(World w, Memory m)
    {
        if (!French) return Knowledge.Describe(w, m);
        string actor = w.NameOf(m.ActorId), target = m.TargetId != null ? w.NameOf(m.TargetId) : "", item = m.ItemId != null ? w.NameOf(m.ItemId) : "";
        return m.Kind switch
        {
            "steal" => $"{actor} vole {(item.Length > 0 ? item : "quelque chose")}{(target.Length > 0 ? " à " + target : "")}",
            "give" => $"{actor} donne {(item.Length > 0 ? item + " " : "")}à {target}",
            _ => $"{actor} {Deed(m.Kind)} {target}{(item.Length > 0 ? $" ({item})" : "")}".TrimEnd(),
        };
    }

    private static readonly Regex Told = new(@"^(?<a>.+?) (?<how>tells|lies to) (?<b>.+?): (?<x>\S+) (?<deed>\w+)(?: -> (?<t>[^(]+?))?(?: \((?<item>.+)\))?$", RegexOptions.Compiled);
    private static readonly Regex Died = new(@"^(?<x>.+?) dies, struck down by (?<y>.+)$", RegexOptions.Compiled);
    private static readonly Regex Confronts = new(@"^(?<g>.+?) confronts (?<t>.+?) about (?<what>.+)$", RegexOptions.Compiled);
    private static readonly Regex Returned = new(@"^(?<i>.+?) returned to (?<o>.+)$", RegexOptions.Compiled);
    private static readonly Regex Refuses = new(@"^(?<t>.+?) refuses to serve (?<b>.+?) \(", RegexOptions.Compiled);
    private static readonly Regex Talked = new(@"^(?<a>.+?) and (?<b>.+?): (?<s>.+)$", RegexOptions.Compiled);
    private static readonly Regex Fulfilled = new(@"^(?<h>.+?) fulfilled (?<g>.+?)'s request \((?<k>\S+) (?<t>.+?)\), paid (?<n>\d+)$", RegexOptions.Compiled);
    private static readonly Regex Saw = new(@"^(?<w>.+?) saw: (?<x>\S+) (?<deed>\w+)(?: -> (?<t>[^(]+?))?(?: \((?<item>.+)\))?$", RegexOptions.Compiled);
    private static readonly Regex OpinionOf = new(@"^(?<h>.+?)'s opinion of (?<o>.+?): (?<v>\S+ -> \S+)(?<why>.*)$", RegexOptions.Compiled);
    private static readonly Regex Decides = new(@"^(?<a>.+?) decides to (?<what>\w+) \((?<rest>.*)\)$", RegexOptions.Compiled);

    public const string PlayerName = "Traveller";

    /// <summary>What the player did, told about them in the past tense ("tu as volé la soie à Daichi").</summary>
    private static string YouDid(string deed, string t, string item) => deed switch
    {
        "steal" => $"tu as volé {(item.Length > 0 ? item : "quelque chose")}{(t.Length > 0 ? " à " + t : "")}",
        "attack" => $"tu as attaqué {t}",
        "kill" => $"tu as tué {t}",
        "defend" => $"tu as défendu le village contre {t}",
        "give" => $"tu as donné {(item.Length > 0 ? item + " " : "quelque chose ")}à {t}",
        "pay" => $"tu as payé {t}",
        "help" => $"tu as aidé {t}",
        "insult" => $"tu as insulté {t}",
        "draw_weapon" => "tu as dégainé ton arme",
        _ => $"tu as fait ceci : {deed} {t}",
    };

    private static string DeedNoun(string deed) => deed switch
    {
        "steal" => "un vol", "attack" => "une agression", "kill" => "un meurtre", "insult" => "une insulte", "draw_weapon" => "une arme dégainée", _ => deed,
    };

    private static string DeedSentence(string x, string deed, string t, string item) => x == PlayerName ? YouDid(deed, t, item) : deed == "steal"
        ? $"{x} vole {(item.Length > 0 ? item : "quelque chose")}{(t.Length > 0 ? " à " + t : "")}"
        : $"{x} {Deed(deed)} {t}{(item.Length > 0 ? $" ({item})" : "")}".TrimEnd();

    /// <summary>Rule-level journal lines are written in English by Core; show them in French when asked.</summary>
    public static string Journal(string text)
    {
        if (!French) return text;
        var m = Told.Match(text);
        if (m.Success)
        {
            string deed = m.Groups["deed"].Value, x = m.Groups["x"].Value, t = m.Groups["t"].Value.Trim(), item = m.Groups["item"].Value;
            string what = DeedSentence(x, deed, t, item);
            string a = m.Groups["a"].Value, b = m.Groups["b"].Value == PlayerName ? "toi" : m.Groups["b"].Value;
            if (x == PlayerName) return m.Groups["how"].Value == "tells" ? $"{a} raconte à {b} que {what}" : $"{a} fait croire à {b} que {what}";
            return m.Groups["how"].Value == "tells" ? $"{a} raconte à {b} : {what}" : $"{a} ment à {b} : {what}";
        }
        if ((m = Died.Match(text)).Success) return $"{m.Groups["x"].Value} meurt sous les coups de {m.Groups["y"].Value}";
        if ((m = Confronts.Match(text)).Success)
            return m.Groups["t"].Value == PlayerName
                ? $"{m.Groups["g"].Value} t'interpelle pour {DeedNoun(m.Groups["what"].Value)}"
                : $"{m.Groups["g"].Value} interpelle {m.Groups["t"].Value} pour {DeedNoun(m.Groups["what"].Value)}";
        if ((m = Returned.Match(text)).Success) return $"{m.Groups["i"].Value} rendu à {m.Groups["o"].Value}";
        if ((m = Refuses.Match(text)).Success) return $"{m.Groups["t"].Value} refuse de servir {m.Groups["b"].Value}";
        if (text.StartsWith("Quest done: "))
        {
            var f = Fulfilled.Match(text.Substring(12));
            return f.Success
                ? $"Requête accomplie : {(f.Groups["h"].Value == PlayerName ? "tu as aidé" : f.Groups["h"].Value + " a aidé")} {f.Groups["g"].Value} ({QuestKind(f.Groups["k"].Value)} · {f.Groups["t"].Value}) — {f.Groups["n"].Value} or"
                : "Requête accomplie : " + text.Substring(12);
        }
        if (text.StartsWith("Quest failed")) return "Requête échouée " + text.Substring(12);
        if ((m = Saw.Match(text)).Success)
            return $"{m.Groups["w"].Value} a vu : {DeedSentence(m.Groups["x"].Value, m.Groups["deed"].Value, m.Groups["t"].Value.Trim(), m.Groups["item"].Value)}";
        if ((m = OpinionOf.Match(text)).Success) return $"Opinion de {m.Groups["h"].Value} sur {m.Groups["o"].Value} : {m.Groups["v"].Value}{m.Groups["why"].Value}";
        if ((m = Decides.Match(text)).Success)
        {
            string what = m.Groups["what"].Value switch { "flee" => "fuir", "confront" => "interpeller", "report" => "prévenir la garde", "scold" => "faire des reproches", _ => m.Groups["what"].Value };
            return $"{m.Groups["a"].Value} décide de {what} ({m.Groups["rest"].Value.Replace("fear", "peur").Replace("bravery", "courage").Replace("opinion of", "opinion de")})";
        }
        foreach (var (en, fr) in new[] { (" plans: ", " prévoit : "), (" thinks: ", " pense : "), (" commits to: ", " s'engage à : "), (" meets ", " rencontre "), (" to Traveller: ", " au voyageur : "), (" is grateful ", " exprime sa gratitude "), (" approves ", " approuve ") })
            if (text.Contains(en)) return text.Replace(en, fr);
        if ((m = Talked.Match(text)).Success) return $"{m.Groups["a"].Value} et {m.Groups["b"].Value} : {m.Groups["s"].Value}";
        return text;
    }
}
