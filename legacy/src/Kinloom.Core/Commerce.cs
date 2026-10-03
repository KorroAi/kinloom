namespace Kinloom.Core
{
    public sealed class TradeResult
    {
        public TradeResult(bool refused, float price, int entryId)
        {
            Refused = refused;
            Price = price;
            EntryId = entryId;
        }

        public bool Refused { get; }
        public float Price { get; }
        public int EntryId { get; }
    }

    /// <summary>Consequence module: prices and service depend on what the trader believes about the buyer.</summary>
    public static class Commerce
    {
        public const float RefuseBelow = -0.6f;

        public static float PriceFor(Agent trader, Agent buyer, float basePrice) =>
            basePrice * (1f - 0.5f * trader.Mind.OpinionOf(buyer.Id));

        public static bool WillTrade(Agent trader, Agent buyer) => trader.Mind.OpinionOf(buyer.Id) > RefuseBelow;

        public static TradeResult Trade(World world, Agent buyer, Agent trader, float basePrice)
        {
            float opinion = trader.Mind.OpinionOf(buyer.Id);
            int? cause = trader.Mind.OpinionCause(buyer.Id);

            if (!WillTrade(trader, buyer))
            {
                trader.Say(world.Pack.Bark("refuse", world.Random), world.Tick);
                int refused = world.Journal.Add(world.Tick, "consequence", trader.Id,
                    System.FormattableString.Invariant($"{trader.Name} refuses to serve {buyer.Name} (opinion {opinion:+0.00;-0.00;0.00})"), cause);
                return new TradeResult(true, 0f, refused);
            }

            float price = PriceFor(trader, buyer, basePrice);
            trader.Say(world.Pack.Bark(price > basePrice ? "overcharge" : "serve", world.Random), world.Tick);
            int entry = world.Journal.Add(world.Tick, "consequence", trader.Id,
                System.FormattableString.Invariant($"{trader.Name} sells to {buyer.Name} for {price:0.0} (base {basePrice:0.0}, opinion {opinion:+0.00;-0.00;0.00})"), cause);
            return new TradeResult(false, price, entry);
        }
    }
}
