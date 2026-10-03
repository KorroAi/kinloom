using System.Collections.Generic;

namespace Kinloom.Core
{
    public enum QuestStatus { Offered, Active, Completed, Failed }

    public static class QuestKinds
    {
        public const string RetrieveItem = "retrieve_item"; // item must end up owned by the giver
        public const string DeliverItem = "deliver_item";   // item must end up owned by the target
        public const string Punish = "punish";              // the hero must hurt the target
        public const string Persuade = "persuade";          // the target's opinion of the giver must reach PersuadeThreshold
        public const string Protect = "protect";            // the target must be alive at the deadline
        public const string Accuse = "accuse";              // name the true culprit (the target) to the giver
        public const string Slay = "slay";                  // the target (a raider, a beast) must be dead

        public static readonly string[] All = { RetrieveItem, DeliverItem, Punish, Persuade, Protect, Accuse, Slay };

        public static bool IsKnown(string? kind) => kind != null && System.Array.IndexOf(All, kind) >= 0;
    }

    /// <summary>A mission born from the world (usually proposed by a brain). Completion is checked by rules, never by a model.</summary>
    public sealed class Quest
    {
        internal Quest(string id, string giverId, string kind, string targetId, string? itemId, int reward, string reason, int offeredTick, int? deadlineTick, int entryId)
        {
            Id = id;
            GiverId = giverId;
            Kind = kind;
            TargetId = targetId;
            ItemId = itemId;
            Reward = reward;
            Reason = reason;
            OfferedTick = offeredTick;
            DeadlineTick = deadlineTick;
            EntryId = entryId;
        }

        public string Id { get; }
        public string GiverId { get; }
        public string Kind { get; }
        public string TargetId { get; }
        public string? ItemId { get; }
        public int Reward { get; }
        public string Reason { get; }
        public int OfferedTick { get; }
        public int? DeadlineTick { get; }
        public int EntryId { get; }
        public QuestStatus Status { get; internal set; } = QuestStatus.Offered;
        public string? HeroId { get; internal set; }
        /// <summary>An item the giver hands over on success (if they still own it).</summary>
        public string? RewardItemId { get; set; }
        public int AcceptedTick { get; internal set; }
    }

    public sealed class QuestBook
    {
        public const float PersuadeThreshold = 0.3f;
        public const float CompletionGratitude = 0.4f;
        public const float FailureDisappointment = 0.2f;

        private readonly List<Quest> _quests = new List<Quest>();
        private readonly List<(int Tick, string Giver, string Kind, string Target, string? Item, int Reward, string Reason, int? DeadlineHours, string? RewardItem)> _scheduled
            = new List<(int, string, string, string, string?, int, string, int?, string?)>();

        /// <summary>An authored quest that appears at a given time (a story beat): offered by rules, checked by rules.</summary>
        public void ScheduleOffer(int tick, string giverId, string kind, string targetId, string? itemId, int reward, string reason, int? deadlineHours, string? rewardItemId = null) =>
            _scheduled.Add((tick, giverId, kind, targetId, itemId, reward, reason, deadlineHours, rewardItemId));

        public IReadOnlyList<Quest> All => _quests;

        public Quest? Find(string? id)
        {
            foreach (var q in _quests) if (q.Id == id) return q;
            return null;
        }

        public Quest Offer(World world, string giverId, string kind, string targetId, string? itemId, int reward, string reason, int? deadlineTick, int? causeId = null) =>
            TryOffer(world, giverId, kind, targetId, itemId, reward, reason, deadlineTick, out var error, causeId)
            ?? throw new System.ArgumentException(error);

        public Quest? TryOffer(World world, string giverId, string kind, string targetId, string? itemId, int reward, string reason,
            int? deadlineTick, out string error, int? causeId = null)
        {
            error = "";
            var giver = world.FindAgent(giverId);
            if (giver == null) { error = $"unknown giver '{giverId}'"; return null; }
            if (!QuestKinds.IsKnown(kind)) { error = $"unknown quest kind '{kind}' (use {string.Join(", ", QuestKinds.All)})"; return null; }
            if (world.FindAgent(targetId) == null) { error = $"unknown target '{targetId}'"; return null; }
            bool needsItem = kind == QuestKinds.RetrieveItem || kind == QuestKinds.DeliverItem;
            if (needsItem && world.FindItem(itemId) == null) { error = $"quest '{kind}' needs a known item (got '{itemId}')"; return null; }
            if (kind == QuestKinds.Protect && deadlineTick == null) { error = "a protect quest needs a deadline"; return null; }
            if (reward < 0) { error = "reward cannot be negative"; return null; }
            foreach (var q in _quests)
                if (q.GiverId == giverId && q.Kind == kind && q.TargetId == targetId && q.ItemId == itemId
                    && (q.Status == QuestStatus.Offered || q.Status == QuestStatus.Active))
                { error = "the same quest is already open"; return null; }

            string id = $"q{_quests.Count + 1}";
            int entry = world.Journal.Add(world.Tick, "quest", giverId,
                $"{giver.Name} offers a quest ({kind} {world.NameOf(targetId)}" + (itemId != null ? $", {world.NameOf(itemId)}" : "") + $", reward {reward}): {reason}",
                causeId, targetId);
            var quest = new Quest(id, giverId, kind, targetId, itemId, reward, reason, world.Tick, deadlineTick, entry);
            _quests.Add(quest);
            return quest;
        }

        public bool Accept(World world, string questId, string heroId)
        {
            var q = Find(questId);
            var hero = world.FindAgent(heroId);
            if (q == null || hero == null || q.Status != QuestStatus.Offered) return false;
            q.Status = QuestStatus.Active;
            q.HeroId = heroId;
            q.AcceptedTick = world.Tick;
            world.Journal.Add(world.Tick, "quest", heroId, $"{hero.Name} accepts {world.NameOf(q.GiverId)}'s quest: {q.Reason}", q.EntryId, q.GiverId);
            return true;
        }

        /// <summary>Rules decide success and failure every tick.</summary>
        public void Check(World world)
        {
            for (int i = _scheduled.Count - 1; i >= 0; i--)
            {
                var s = _scheduled[i];
                if (world.Tick < s.Tick) continue;
                _scheduled.RemoveAt(i);
                var giver = world.FindAgent(s.Giver);
                if (giver == null || !giver.IsAlive) continue;
                var q = TryOffer(world, s.Giver, s.Kind, s.Target, s.Item, s.Reward, s.Reason,
                    s.DeadlineHours.HasValue ? world.Tick + s.DeadlineHours.Value * World.TicksPerHour : (int?)null, out _);
                if (q != null) q.RewardItemId = s.RewardItem;
            }
            foreach (var q in _quests)
            {
                if (q.Status != QuestStatus.Active) continue;
                var giver = world.FindAgent(q.GiverId)!;
                var target = world.FindAgent(q.TargetId)!;
                bool expired = q.DeadlineTick.HasValue && world.Tick >= q.DeadlineTick.Value;

                if (!giver.IsAlive) { Fail(world, q, $"{giver.Name} is dead"); continue; }
                switch (q.Kind)
                {
                    case QuestKinds.RetrieveItem:
                        if (world.FindItem(q.ItemId)?.OwnerId == q.GiverId) Complete(world, q);
                        else if (expired) Fail(world, q, "too late");
                        break;
                    case QuestKinds.DeliverItem:
                        if (world.FindItem(q.ItemId)?.OwnerId == q.TargetId) Complete(world, q);
                        else if (expired) Fail(world, q, "too late");
                        break;
                    case QuestKinds.Punish:
                        if (world.Fights.HasHurt(q.HeroId!, q.TargetId, q.AcceptedTick)) Complete(world, q);
                        else if (expired) Fail(world, q, "too late");
                        break;
                    case QuestKinds.Persuade:
                        if (target.Mind.OpinionOf(q.GiverId) >= PersuadeThreshold) Complete(world, q);
                        else if (expired) Fail(world, q, "too late");
                        break;
                    case QuestKinds.Protect:
                        if (!target.IsAlive) Fail(world, q, $"{target.Name} died");
                        else if (expired) Complete(world, q);
                        break;
                    case QuestKinds.Slay:
                        if (!target.IsAlive) Complete(world, q);
                        else if (expired) Fail(world, q, "too late");
                        break;
                    case QuestKinds.Accuse:
                        if (expired) Fail(world, q, "too late");
                        break;
                }
            }
        }

        /// <summary>The hero names a culprit to the giver. True if it answers an open accusation quest correctly;
        /// a wrong name costs trust with the giver and, more, with the accused.</summary>
        public bool Accuse(World world, string heroId, string giverId, string accusedId)
        {
            Quest? quest = null;
            foreach (var q in _quests)
                if (q.Kind == QuestKinds.Accuse && q.GiverId == giverId && q.HeroId == heroId && q.Status == QuestStatus.Active) quest = q;
            var giver = world.FindAgent(giverId);
            var accused = world.FindAgent(accusedId);
            if (quest == null || giver == null || accused == null) return false;
            if (accusedId == quest.TargetId)
            {
                Complete(world, quest);
                giver.Mind.ShiftOpinion(accusedId, -0.4f);
                return true;
            }
            int entry = world.Journal.Add(world.Tick, "quest", heroId, $"False accusation: {world.NameOf(heroId)} blames {accused.Name} before {giver.Name}", quest.EntryId, accusedId);
            giver.Mind.ShiftOpinion(heroId, -0.1f);
            giver.Mind.SetOpinionCause(heroId, entry);
            accused.Mind.ShiftOpinion(heroId, -0.3f);
            accused.Mind.SetOpinionCause(heroId, entry);
            return false;
        }

        private static void Complete(World world, Quest q)
        {
            var giver = world.GetAgent(q.GiverId);
            var hero = world.GetAgent(q.HeroId!);
            int paid = System.Math.Min(q.Reward, giver.Gold);
            giver.Gold -= paid;
            hero.Gold += paid;
            var reward = world.FindItem(q.RewardItemId);
            if (reward != null && reward.OwnerId == giver.Id) reward.OwnerId = hero.Id;
            q.Status = QuestStatus.Completed;
            int entry = world.Journal.Add(world.Tick, "quest", q.GiverId,
                $"Quest done: {hero.Name} fulfilled {giver.Name}'s request ({q.Kind} {world.NameOf(q.TargetId)}), paid {paid}", q.EntryId, hero.Id);
            giver.Mind.ShiftOpinion(hero.Id, CompletionGratitude);
            giver.Mind.SetOpinionCause(hero.Id, entry);
        }

        private static void Fail(World world, Quest q, string why)
        {
            var giver = world.GetAgent(q.GiverId);
            q.Status = QuestStatus.Failed;
            int entry = world.Journal.Add(world.Tick, "quest", q.GiverId,
                $"Quest failed ({why}): {giver.Name}'s request ({q.Kind} {world.NameOf(q.TargetId)})", q.EntryId, q.HeroId);
            if (q.HeroId != null && giver.IsAlive)
            {
                giver.Mind.ShiftOpinion(q.HeroId, -FailureDisappointment);
                giver.Mind.SetOpinionCause(q.HeroId, entry);
            }
        }
    }
}
