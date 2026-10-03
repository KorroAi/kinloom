using System.Reflection;

namespace Kinloom.Cli;

/// <summary>Files embedded in the executable: the agent kit (<c>kit/</c>), the Godot addon (<c>godot/</c>) and the runtime DLLs (<c>lib/</c>).</summary>
internal static class Kit
{
    private static readonly Assembly Self = typeof(Kit).Assembly;

    /// <summary>Every resource under a prefix, as (path relative to the prefix, bytes). Backslashes from MSBuild are normalized.</summary>
    public static IEnumerable<(string path, byte[] data)> Files(string prefix)
    {
        foreach (var name in Self.GetManifestResourceNames())
        {
            string normalized = name.Replace('\\', '/');
            if (!normalized.StartsWith(prefix + "/", StringComparison.Ordinal)) continue;
            yield return (normalized.Substring(prefix.Length + 1), Bytes(name));
        }
    }

    public static string? Text(string path)
    {
        var name = Self.GetManifestResourceNames().FirstOrDefault(n => n.Replace('\\', '/') == path);
        return name == null ? null : System.Text.Encoding.UTF8.GetString(Bytes(name)).TrimStart('﻿');
    }

    private static byte[] Bytes(string name)
    {
        using var stream = Self.GetManifestResourceStream(name)!;
        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        return memory.ToArray();
    }
}
