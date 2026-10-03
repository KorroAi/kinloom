using System.Text.Json;
using System.Text.Json.Nodes;

namespace Kinloom.Cli.Mcp;

/// <summary>A Model Context Protocol server over stdio (newline-delimited JSON-RPC 2.0), so the developer's coding agent can
/// scan the game, validate declarations, simulate roles, attack guardrails, attach to the running game and estimate cost.</summary>
internal sealed class McpServer
{
    public static readonly string[] Versions = { "2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25" };
    private readonly McpTools _tools;

    public McpServer(Func<string, string?> env) { _tools = new McpTools(env); }

    public async Task RunStdio(TextReader input, TextWriter output, CancellationToken ct)
    {
        string? line;
        while (!ct.IsCancellationRequested && (line = await input.ReadLineAsync(ct)) != null)
        {
            if (line.Trim().Length == 0) continue;
            string? response = await Handle(line);
            if (response == null) continue;
            await output.WriteLineAsync(response);
            await output.FlushAsync(ct);
        }
    }

    public async Task<string?> Handle(string line)
    {
        JsonObject request;
        try { request = JsonNode.Parse(line) as JsonObject ?? throw new JsonException("not an object"); }
        catch (JsonException e) { return Error(null, -32700, "parse error: " + e.Message); }
        var id = request["id"]?.DeepClone();
        string method = request["method"]?.GetValue<string>() ?? "";
        var p = request["params"] as JsonObject ?? new JsonObject();
        if (id == null) return null; // notifications (initialized, cancelled...) need no answer

        switch (method)
        {
            case "initialize":
            {
                string asked = p["protocolVersion"]?.GetValue<string>() ?? "";
                string version = Versions.Contains(asked) ? asked : Versions[^1];
                return Result(id, new JsonObject
                {
                    ["protocolVersion"] = version,
                    ["capabilities"] = new JsonObject { ["tools"] = new JsonObject { ["listChanged"] = false } },
                    ["serverInfo"] = new JsonObject { ["name"] = "kinloom", ["version"] = typeof(McpServer).Assembly.GetName().Version?.ToString(3) ?? "0" },
                    ["instructions"] = "Kinloom puts AI into any game. Start with scan_project, write kinloom/*.json manifests (see kinloom/docs/reference.md), then validate, simulate_role, attack_guardrails and run_tests. attach reads a running game.",
                });
            }
            case "ping":
                return Result(id, new JsonObject());
            case "tools/list":
                return Result(id, new JsonObject { ["tools"] = McpTools.List() });
            case "tools/call":
            {
                string name = p["name"]?.GetValue<string>() ?? "";
                var args = p["arguments"] as JsonObject ?? new JsonObject();
                if (!McpTools.Names.Contains(name)) return Error(id, -32602, $"unknown tool '{name}'");
                (string text, bool isError) outcome;
                try { outcome = await _tools.Call(name, args); }
                catch (Exception e) when (!(e is OutOfMemoryException)) { outcome = ($"{name} failed: {e.GetType().Name}: {e.Message}", true); }
                return Result(id, new JsonObject
                {
                    ["content"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = outcome.text }),
                    ["isError"] = outcome.isError,
                });
            }
            default:
                return Error(id, -32601, $"unknown method '{method}'");
        }
    }

    private static string Result(JsonNode? id, JsonObject result) =>
        new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["result"] = result }.ToJsonString();

    private static string Error(JsonNode? id, int code, string message) =>
        new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["error"] = new JsonObject { ["code"] = code, ["message"] = message } }.ToJsonString();
}
