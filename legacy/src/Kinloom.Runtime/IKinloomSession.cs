using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Kinloom.Media;
using Kinloom.Schema;

namespace Kinloom
{
    /// <summary>The contract a game talks to, identical in-process (<see cref="KinloomSession"/>) and over the local
    /// WebSocket service (<see cref="Protocol.RemoteSession"/>). See docs/protocol.md for the wire format.</summary>
    public interface IKinloomSession
    {
        IReadOnlyList<ManifestError> Declare(string json);
        void Update(string thingId, JsonObject props);
        void Emit(GameEvent e);
        /// <summary>Advances game time and returns effects to apply now (over the wire: those received since the last call).</summary>
        IReadOnlyList<Effect> Pump(double gameTime);
        void Resolve(long effectId, EffectResult result);
        Task<AskResult> Ask(string roleId, string input, string? from = null);
        Task<GenerateResult> Generate(string generatorId, JsonObject? context = null, string? source = null);
        Task<MediaResult> RequestMedia(MediaRequest request, string? source = null);
        void Bind(string thingId);
        void Unbind(string thingId);
        bool RemoveThing(string id);
        string Save();
        void Load(string json);
    }

    public sealed partial class KinloomSession : IKinloomSession
    {
        IReadOnlyList<ManifestError> IKinloomSession.Declare(string json) => Declare(json);

        /// <summary>Effects waiting for the next pump.</summary>
        internal int ReadyCount { get { lock (_gate) return _ready.Count; } }
    }
}
