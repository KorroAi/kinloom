using System;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using Kinloom.Llm;

namespace Kinloom.Roles
{
    /// <summary>One model call with a hard time limit. The token asks the client to stop; a client that ignores it is
    /// abandoned anyway, so a role or generator can never stay stuck on a call that never returns.</summary>
    internal static class ModelCall
    {
        public static async Task<LlmResponse> Run(ILlmClient client, LlmRequest request, double seconds)
        {
            var limit = TimeSpan.FromSeconds(Math.Max(0.05, seconds));
            using var cts = new CancellationTokenSource(limit);
            Task<LlmResponse> call;
            try { call = client.CompleteAsync(request, cts.Token); }
            catch (Exception e) { return LlmResponse.Failure(e.GetType().Name + ": " + e.Message); }
            var finished = await Task.WhenAny(call, Task.Delay(limit + TimeSpan.FromMilliseconds(250))).ConfigureAwait(false);
            if (finished != call || call.IsCanceled)
            {
                _ = call.ContinueWith(t => _ = t.Exception, TaskContinuationOptions.OnlyOnFaulted);
                return LlmResponse.Failure("timed out after " + seconds.ToString("0.#", CultureInfo.InvariantCulture) + " s", (long)limit.TotalMilliseconds);
            }
            try { return await call.ConfigureAwait(false); }
            catch (OperationCanceledException) { return LlmResponse.Failure("timed out after " + seconds.ToString("0.#", CultureInfo.InvariantCulture) + " s", (long)limit.TotalMilliseconds); }
            catch (Exception e) { return LlmResponse.Failure(e.GetType().Name + ": " + e.Message); }
        }
    }
}
