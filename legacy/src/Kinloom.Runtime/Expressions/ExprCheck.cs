using System.Collections.Generic;
using Kinloom.Schema;

namespace Kinloom.Expressions
{
    /// <summary>Reports the syntax errors of every expression in a manifest, located by path.</summary>
    internal static class ExprCheck
    {
        public static void Check(Declarations d, List<ManifestError> errors)
        {
            for (int i = 0; i < d.Roles.Count; i++)
                for (int w = 0; w < d.Roles[i].Wake.Count; w++)
                {
                    One(d.Roles[i].Wake[w].When, $"roles[{i}].wake[{w}].when", errors);
                    One(d.Roles[i].Wake[w].Where, $"roles[{i}].wake[{w}].where", errors);
                }
            for (int i = 0; i < d.Behaviors.Count; i++) Behavior(d.Behaviors[i], $"behaviors[{i}]", errors);
            for (int i = 0; i < d.Generators.Count; i++)
                for (int c = 0; c < d.Generators[i].Constraints.Count; c++)
                    One(d.Generators[i].Constraints[c], $"generators[{i}].constraints[{c}]", errors);
        }

        public static void Behavior(BehaviorDecl b, string path, List<ManifestError> errors)
        {
            for (int r = 0; r < b.Rules.Count; r++)
            {
                var rule = b.Rules[r];
                string rp = $"{path}.rules[{r}]";
                One(rule.When, rp + ".when", errors);
                for (int a = 0; a < rule.Do.Count; a++)
                {
                    var act = rule.Do[a];
                    string ap = $"{rp}.do[{a}]";
                    One(act.To, ap + ".to", errors);
                    foreach (var arg in act.Args) One(arg.Value, $"{ap}.args.{arg.Key}", errors);
                    foreach (var datum in act.Data) One(datum.Value, $"{ap}.data.{datum.Key}", errors);
                }
            }
        }

        private static void One(string? source, string path, List<ManifestError> errors)
        {
            if (source == null) return;
            try { Expr.Parse(source); }
            catch (ExprException e) { errors.Add(new ManifestError(path, $"{e.Message} in \"{source}\"")); }
        }
    }
}
