using System.IO;
using System.Text.RegularExpressions;
using Kinloom.Cli;
using Kinloom.Schema;

namespace Kinloom.Cli.Tests;

public class KitTests
{
    private static string Root()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "Kinloom.slnx"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("repo root");
    }

    public static IEnumerable<object[]> ManifestBlocks()
    {
        string kit = Path.Combine(Root(), "kit");
        foreach (var file in Directory.GetFiles(kit, "*.md", SearchOption.AllDirectories).Concat(new[] { Path.Combine(Root(), "llms.txt") }))
        {
            int n = 0;
            foreach (Match m in Regex.Matches(File.ReadAllText(file), "```json kinloom\\r?\\n(.*?)```", RegexOptions.Singleline))
                yield return new object[] { Path.GetRelativePath(Root(), file) + "#" + ++n, m.Groups[1].Value };
        }
    }

    [Theory]
    [MemberData(nameof(ManifestBlocks))]
    public void Every_manifest_example_in_the_kit_is_valid(string where, string json)
    {
        var errors = new List<ManifestError>();
        var d = Manifest.Parse(json, where, errors);
        if (errors.Count == 0) Manifest.Check(d, errors);
        Assert.True(errors.Count == 0, where + ":\n" + string.Join("\n", errors));
    }

    [Fact]
    public void The_kit_has_every_recipe_and_reference()
    {
        Assert.True(ManifestBlocks().Count() >= 7, "expected one manifest example in the reference and in each of the six recipes");
        foreach (var recipe in new[] { "character", "director", "generator", "narrator", "analyst", "interface" })
            Assert.True(File.Exists(Path.Combine(Root(), "kit", "docs", "recipes", recipe + ".md")), recipe);
    }

    [Fact]
    public void Init_copies_the_whole_kit()
    {
        using var p = new TempProject();
        p.Write("main.py", "x = 1");
        Init.Run(p.Dir, null, _ => null);
        foreach (var f in new[] { "kinloom/docs/reference.md", "kinloom/docs/integration-checklist.md", "kinloom/docs/protocol.md",
                     "kinloom/docs/recipes/character.md", "kinloom/docs/recipes/director.md", "kinloom/docs/recipes/generator.md",
                     "kinloom/docs/recipes/narrator.md", "kinloom/docs/recipes/analyst.md", "kinloom/docs/recipes/interface.md" })
            Assert.True(p.Exists(f), f + " missing");
        Assert.Contains("kinloom", p.Read(".claude/skills/kinloom-integrate/SKILL.md"));
        Assert.StartsWith("---", p.Read(".claude/skills/kinloom-integrate/SKILL.md"));
        Assert.Contains("AGENTS.md", p.Read("CLAUDE.md"));
    }
}
