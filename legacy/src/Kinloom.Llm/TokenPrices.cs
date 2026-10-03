namespace Kinloom.Llm
{
    /// <summary>Prices per million tokens, as published by the provider.</summary>
    public sealed class TokenPrices
    {
        public TokenPrices(double input, double cachedInput, double output)
        {
            Input = input;
            CachedInput = cachedInput;
            Output = output;
        }

        public double Input { get; }
        public double CachedInput { get; }
        public double Output { get; }

        public double CostOf(long input, long cached, long output) =>
            ((input - cached) * Input + cached * CachedInput + output * Output) / 1_000_000d;
    }
}
