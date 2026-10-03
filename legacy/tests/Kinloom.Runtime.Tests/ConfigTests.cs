using System.IO;
using Kinloom.Config;

namespace Kinloom.Runtime.Tests;

public class ConfigTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "kinloom-config-" + Guid.NewGuid().ToString("N"));

    public ConfigTests() { Directory.CreateDirectory(Path.Combine(_dir, "kinloom")); }
    public void Dispose() { try { Directory.Delete(_dir, true); } catch (IOException) { } }

    private void Write(string json) => File.WriteAllText(Path.Combine(_dir, "kinloom.json"), json);
    private static Func<string, string?> Env(params (string k, string v)[] vars) => k => vars.FirstOrDefault(x => x.k == k).v;

    [Fact]
    public void A_missing_file_gives_defaults()
    {
        var c = KinloomConfig.Load(_dir);
        Assert.Equal("kinloom", c.Manifest);
        Assert.Equal(7717, c.ServePort);
        Assert.Equal(7718, c.DebugPort);
        Assert.Null(c.Prices);
    }

    [Fact]
    public void Without_the_key_there_are_no_clients_and_the_problem_names_the_variable_only()
    {
        Write("""{"provider":{"kind":"deepseek","keyEnv":"MY_SECRET_KEY","fast":"deepseek-flash"}}""");
        var c = KinloomConfig.Load(_dir);
        var clients = c.CreateClients(Env());
        Assert.Null(clients.Fast);
        Assert.Null(clients.Deep);
        Assert.Contains("MY_SECRET_KEY", clients.Problem);
    }

    [Fact]
    public void With_the_key_both_tiers_get_a_client()
    {
        Write("""{"provider":{"kind":"openai","keyEnv":"OPENAI_API_KEY","fast":"small-model","deep":"big-model"}}""");
        var clients = KinloomConfig.Load(_dir).CreateClients(Env(("OPENAI_API_KEY", "sk-test")));
        Assert.Equal("small-model", clients.Fast!.Name);
        Assert.Equal("big-model", clients.Deep!.Name);
        Assert.Null(clients.Problem);
    }

    [Fact]
    public void A_provider_without_models_is_a_problem_not_a_guess()
    {
        Write("""{"provider":{"kind":"openai","keyEnv":"OPENAI_API_KEY"}}""");
        var clients = KinloomConfig.Load(_dir).CreateClients(Env(("OPENAI_API_KEY", "sk-test")));
        Assert.Null(clients.Fast);
        Assert.Contains("provider.fast", clients.Problem);
    }

    [Fact]
    public void A_scripted_provider_reads_its_script_relative_to_the_project()
    {
        File.WriteAllText(Path.Combine(_dir, "kinloom", "script.json"), """{"*":["{}"]}""");
        Write("""{"provider":{"kind":"scripted","script":"kinloom/script.json"}}""");
        var clients = KinloomConfig.Load(_dir).CreateClients(Env());
        Assert.Equal("scripted", clients.Fast!.Name);
    }

    [Fact]
    public void The_environment_can_override_the_provider()
    {
        File.WriteAllText(Path.Combine(_dir, "s.json"), """{"*":["{}"]}""");
        Write("""{"provider":{"kind":"deepseek","fast":"deepseek-flash"}}""");
        var clients = KinloomConfig.Load(_dir).CreateClients(Env(("KINLOOM_PROVIDER", "scripted"), ("KINLOOM_SCRIPT", Path.Combine(_dir, "s.json"))));
        Assert.Equal("scripted", clients.Fast!.Name);
    }

    [Fact]
    public void Prices_need_all_three_numbers()
    {
        Write("""{"prices":{"input":0.3,"output":1.2}}""");
        Assert.Null(KinloomConfig.Load(_dir).Prices);
        Write("""{"prices":{"input":0.3,"cachedInput":0.03,"output":1.2,"source":"provider pricing page, 2026-09-27"}}""");
        Assert.Equal(1.2, KinloomConfig.Load(_dir).Prices!.Output);
    }

    [Fact]
    public void Broken_json_fails_with_the_file_name()
    {
        Write("{ nope");
        var e = Assert.Throws<InvalidOperationException>(() => KinloomConfig.Load(_dir));
        Assert.Contains("kinloom.json", e.Message);
    }

    [Fact]
    public void A_session_is_built_from_the_project()
    {
        File.WriteAllText(Path.Combine(_dir, "kinloom", "game.json"), TestData.Trucks);
        Write("""{"language":"French","media":{"image":{"command":"gen {prompt} {out}","format":"png"}},"budget":{"maxCallsPerMinute":12}}""");
        var session = KinloomConfig.Load(_dir).CreateSession(_dir, Env(), out var errors);
        Assert.Empty(errors);
        Assert.NotNull(session.Things.Find("truck_2"));
        Assert.Equal("French", session.Options.Language);
        Assert.Equal(12, session.Options.MaxCallsPerMinute);
        Assert.Contains("image", session.Media.Kinds);
    }
}
