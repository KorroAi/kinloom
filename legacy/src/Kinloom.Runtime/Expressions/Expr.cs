using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;

namespace Kinloom.Expressions
{
    /// <summary>Where expression paths come from (things, events, the world...).</summary>
    public interface IExprScope
    {
        /// <summary>The value at a path like <c>self.health</c> or <c>player.pos.x</c>; <see cref="Value.Null"/> when unknown.</summary>
        Value Resolve(IReadOnlyList<string> path);
        double Now { get; }
    }

    public sealed class ExprException : Exception
    {
        public ExprException(string message, int column) : base($"column {column}: {message}") { Column = column; Reason = message; }
        public int Column { get; }
        public string Reason { get; }
    }

    /// <summary>A small, sandboxed expression language: literals, paths, arithmetic, comparisons, logic, ternary and a fixed
    /// function list. No loops, no assignment, no side effects. Evaluation never throws: unknown paths are null,
    /// arithmetic with null is null, comparisons with null are false, division by zero is 0.</summary>
    public sealed class Expr
    {
        private readonly Node _root;
        private Expr(string source, Node root, List<IReadOnlyList<string>> paths)
        {
            Source = source;
            _root = root;
            Paths = paths;
        }

        public string Source { get; }
        public IReadOnlyList<IReadOnlyList<string>> Paths { get; }

        public static readonly IReadOnlyDictionary<string, (int min, int max)> Functions = new Dictionary<string, (int, int)>
        {
            ["min"] = (1, 16), ["max"] = (1, 16), ["clamp"] = (3, 3), ["lerp"] = (3, 3), ["abs"] = (1, 1), ["sign"] = (1, 1),
            ["floor"] = (1, 1), ["ceil"] = (1, 1), ["round"] = (1, 1), ["sqrt"] = (1, 1), ["dist"] = (2, 4), ["len"] = (1, 1),
            ["sin"] = (1, 1), ["cos"] = (1, 1), ["tan"] = (1, 1), ["atan2"] = (2, 2), ["pow"] = (2, 2), ["pi"] = (0, 0),
            ["rand"] = (0, 2), ["now"] = (0, 0), ["since"] = (1, 1), ["contains"] = (2, 2), ["exists"] = (1, 1),
        };

        /// <summary>Longest expression accepted (a model could otherwise send megabytes).</summary>
        public const int MaxLength = 2000;
        /// <summary>Deepest nesting accepted: parsing and evaluation recurse, and a stack overflow would kill the game.</summary>
        public const int MaxDepth = 40;

        public static Expr Parse(string source)
        {
            if (source != null && source.Length > MaxLength)
                throw new ExprException($"expression too long ({source.Length} characters, at most {MaxLength})", 1);
            var parser = new Parser(source ?? "");
            var root = parser.ParseAll();
            return new Expr(source ?? "", root, parser.Paths);
        }

        public Value Eval(IExprScope scope, Random rng) => _root.Eval(new Ctx(scope, rng));

        public override string ToString() => Source;

        // ---- evaluation ----

        private readonly struct Ctx
        {
            public Ctx(IExprScope scope, Random rng) { Scope = scope; Rng = rng; }
            public IExprScope Scope { get; }
            public Random Rng { get; }
        }

        private abstract class Node { public abstract Value Eval(Ctx c); }

        private sealed class Literal : Node
        {
            private readonly Value _v;
            public Literal(Value v) { _v = v; }
            public override Value Eval(Ctx c) => _v;
        }

        private sealed class PathNode : Node
        {
            private readonly string[] _path;
            public PathNode(string[] path) { _path = path; }
            public override Value Eval(Ctx c) => c.Scope.Resolve(_path);
        }

        private sealed class ListNode : Node
        {
            private readonly Node[] _items;
            private readonly Value? _constant;
            public ListNode(Node[] items)
            {
                _items = items;
                if (items.All(i => i is Literal)) _constant = Value.OfList(items.Select(i => i.Eval(default)).ToArray());
            }
            public override Value Eval(Ctx c)
            {
                if (_constant.HasValue) return _constant.Value;
                var values = new Value[_items.Length];
                for (int i = 0; i < values.Length; i++) values[i] = _items[i].Eval(c);
                return Value.OfList(values);
            }
        }

        private sealed class Member : Node
        {
            private readonly Node _target; private readonly string _name;
            public Member(Node target, string name) { _target = target; _name = name; }
            public override Value Eval(Ctx c) => _target.Eval(c).Get(_name);
        }

        private sealed class Index : Node
        {
            private readonly Node _target; private readonly Node _index;
            public Index(Node target, Node index) { _target = target; _index = index; }
            public override Value Eval(Ctx c)
            {
                var i = _index.Eval(c);
                return _target.Eval(c).Get(i.Kind == ValueKind.Number ? ((int)i.Number).ToString(CultureInfo.InvariantCulture) : i.String);
            }
        }

        private sealed class Unary : Node
        {
            private readonly char _op; private readonly Node _x;
            public Unary(char op, Node x) { _op = op; _x = x; }
            public override Value Eval(Ctx c)
            {
                var v = _x.Eval(c);
                if (_op == '!') return Value.Of(!v.Truthy);
                if (v.Kind == ValueKind.Number) return Value.Of(-v.Number);
                if (v.Kind == ValueKind.Vector) return Value.OfVector(v.Vector.Select(d => -d).ToArray());
                return Value.Null;
            }
        }

        private sealed class Logic : Node
        {
            private readonly bool _and; private readonly Node _a, _b;
            public Logic(bool and, Node a, Node b) { _and = and; _a = a; _b = b; }
            public override Value Eval(Ctx c)
            {
                bool a = _a.Eval(c).Truthy;
                if (_and) return Value.Of(a && _b.Eval(c).Truthy);
                return Value.Of(a || _b.Eval(c).Truthy);
            }
        }

        private sealed class Ternary : Node
        {
            private readonly Node _cond, _a, _b;
            public Ternary(Node cond, Node a, Node b) { _cond = cond; _a = a; _b = b; }
            public override Value Eval(Ctx c) => _cond.Eval(c).Truthy ? _a.Eval(c) : _b.Eval(c);
        }

        private sealed class Binary : Node
        {
            private readonly string _op; private readonly Node _a, _b;
            public Binary(string op, Node a, Node b) { _op = op; _a = a; _b = b; }

            public override Value Eval(Ctx c)
            {
                var a = _a.Eval(c);
                var b = _b.Eval(c);
                switch (_op)
                {
                    case "==": return Value.Of(a.SameAs(b));
                    case "!=": return Value.Of(!a.SameAs(b));
                    case "<": case "<=": case ">": case ">=":
                    {
                        int? cmp = null;
                        if (IsNum(a) && IsNum(b)) cmp = a.Number.CompareTo(b.Number);
                        else if (a.Kind == ValueKind.String && b.Kind == ValueKind.String) cmp = string.CompareOrdinal(a.String, b.String);
                        if (cmp == null) return Value.False;
                        return Value.Of(_op == "<" ? cmp < 0 : _op == "<=" ? cmp <= 0 : _op == ">" ? cmp > 0 : cmp >= 0);
                    }
                    case "+":
                        if (a.Kind == ValueKind.String || b.Kind == ValueKind.String)
                            return a.Kind == ValueKind.Null || b.Kind == ValueKind.Null ? Value.Null : Value.Of(a.String + b.String);
                        return Arith(a, b, '+');
                    case "-": return Arith(a, b, '-');
                    case "*": return Arith(a, b, '*');
                    case "/": return Arith(a, b, '/');
                    case "%": return Arith(a, b, '%');
                    default: return Value.Null;
                }
            }

            private static bool IsNum(Value v) => v.Kind == ValueKind.Number;

            private static double Op(char op, double x, double y) => op switch
            {
                '+' => x + y,
                '-' => x - y,
                '*' => x * y,
                '/' => y == 0 ? 0 : x / y,
                _ => y == 0 ? 0 : x % y,
            };

            /// <summary>Numbers and vectors (component-wise, or with a scalar). No delegates: this runs every frame.</summary>
            private static Value Arith(Value a, Value b, char op)
            {
                if (IsNum(a) && IsNum(b)) return Value.Of(Op(op, a.Number, b.Number));
                if (a.Kind == ValueKind.Vector && b.Kind == ValueKind.Vector && a.Vector.Length == b.Vector.Length)
                {
                    var x = a.Vector; var y = b.Vector; var r = new double[x.Length];
                    for (int i = 0; i < r.Length; i++) r[i] = Op(op, x[i], y[i]);
                    return Value.OfVector(r);
                }
                if (a.Kind == ValueKind.Vector && IsNum(b))
                {
                    var x = a.Vector; var r = new double[x.Length];
                    for (int i = 0; i < r.Length; i++) r[i] = Op(op, x[i], b.Number);
                    return Value.OfVector(r);
                }
                if (IsNum(a) && b.Kind == ValueKind.Vector)
                {
                    var y = b.Vector; var r = new double[y.Length];
                    for (int i = 0; i < r.Length; i++) r[i] = Op(op, a.Number, y[i]);
                    return Value.OfVector(r);
                }
                return Value.Null;
            }
        }

        private sealed class Call : Node
        {
            private readonly string _name; private readonly Node[] _args;
            /// <summary>Argument buffer reused across evaluations (behaviors evaluate every frame; this keeps them allocation-free).
            /// Taken with an exchange, so concurrent evaluations of the same expression just allocate their own.</summary>
            private Value[]? _buffer;
            public Call(string name, Node[] args) { _name = name; _args = args; }

            public override Value Eval(Ctx c)
            {
                if (_name == "exists") return Value.Of(_args[0].Eval(c).Kind != ValueKind.Null);
                if (_name == "now") return Value.Of(c.Scope.Now);
                if (_name == "pi") return Value.Of(Math.PI);
                var v = System.Threading.Interlocked.Exchange(ref _buffer, null) ?? new Value[_args.Length];
                try { return Apply(c, v); }
                finally
                {
                    Array.Clear(v, 0, v.Length);
                    _buffer = v;
                }
            }

            private Value Apply(Ctx c, Value[] v)
            {
                bool allNum = true;
                for (int i = 0; i < v.Length; i++)
                {
                    v[i] = _args[i].Eval(c);
                    if (v[i].Kind != ValueKind.Number) allNum = false;
                }
                double N(int i) => v[i].Number;
                bool AllNum() => allNum;
                switch (_name)
                {
                    case "min":
                    case "max":
                    {
                        bool min = _name == "min", any = false;
                        double best = 0;
                        void Consider(double d)
                        {
                            if (!any || (min ? d < best : d > best)) best = d;
                            any = true;
                        }
                        if (v.Length == 1 && v[0].Kind == ValueKind.Vector) foreach (var d in v[0].Vector) Consider(d);
                        else if (v.Length == 1 && v[0].Kind == ValueKind.List) { foreach (var x in v[0].Items()) if (x.Kind == ValueKind.Number) Consider(x.Number); }
                        else foreach (var x in v) if (x.Kind == ValueKind.Number) Consider(x.Number);
                        return any ? Value.Of(best) : Value.Null;
                    }
                    case "clamp": return AllNum() ? Value.Of(Math.Max(N(1), Math.Min(N(2), N(0)))) : Value.Null;
                    case "lerp": return AllNum() ? Value.Of(N(0) + (N(1) - N(0)) * N(2)) : Value.Null;
                    case "abs": return AllNum() ? Value.Of(Math.Abs(N(0))) : Value.Null;
                    case "sign": return AllNum() ? Value.Of(Math.Sign(N(0))) : Value.Null;
                    case "floor": return AllNum() ? Value.Of(Math.Floor(N(0))) : Value.Null;
                    case "ceil": return AllNum() ? Value.Of(Math.Ceiling(N(0))) : Value.Null;
                    case "round": return AllNum() ? Value.Of(Math.Round(N(0), MidpointRounding.AwayFromZero)) : Value.Null;
                    case "sqrt": return AllNum() ? Value.Of(N(0) <= 0 ? 0 : Math.Sqrt(N(0))) : Value.Null;
                    case "sin": return AllNum() ? Value.Of(Math.Sin(N(0))) : Value.Null;
                    case "cos": return AllNum() ? Value.Of(Math.Cos(N(0))) : Value.Null;
                    case "tan": return AllNum() ? Value.Of(Math.Tan(N(0))) : Value.Null;
                    case "atan2": return AllNum() ? Value.Of(Math.Atan2(N(0), N(1))) : Value.Null;
                    case "pow": return AllNum() ? Value.Of(Math.Pow(N(0), N(1))) : Value.Null;
                    case "pi": return Value.Of(Math.PI);
                    case "dist":
                    {
                        if (v.Length == 4) return AllNum() ? Value.Of(Math.Sqrt((N(2) - N(0)) * (N(2) - N(0)) + (N(3) - N(1)) * (N(3) - N(1)))) : Value.Null;
                        if (AllNum()) return Value.Of(Math.Abs(N(0) - N(1)));
                        if (v[0].Kind != ValueKind.Vector || v[1].Kind != ValueKind.Vector) return Value.Null;
                        var a = v[0].Vector; var b = v[1].Vector;
                        double sum = 0;
                        for (int i = 0; i < Math.Min(a.Length, b.Length); i++) sum += (a[i] - b[i]) * (a[i] - b[i]);
                        return Value.Of(Math.Sqrt(sum));
                    }
                    case "len": return v[0].Kind == ValueKind.Null ? Value.Null : Value.Of(v[0].Count);
                    case "rand":
                    {
                        double r = c.Rng.NextDouble();
                        return v.Length == 2 && AllNum() ? Value.Of(N(0) + (N(1) - N(0)) * r) : Value.Of(r);
                    }
                    case "since": return AllNum() ? Value.Of(c.Scope.Now - N(0)) : Value.Null;
                    case "contains":
                    {
                        if (v[0].Kind == ValueKind.String) return Value.Of(v[1].Kind != ValueKind.Null && v[0].String.IndexOf(v[1].String, StringComparison.Ordinal) >= 0);
                        var needle = v[1];
                        return Value.Of(v[0].Items().Any(x => x.SameAs(needle)));
                    }
                    default: return Value.Null;
                }
            }
        }

        // ---- parsing ----

        private enum Tok { Number, String, Ident, Op, LParen, RParen, LBracket, RBracket, Comma, Dot, Question, Colon, End }

        private readonly struct Token
        {
            public Token(Tok kind, string text, int column) { Kind = kind; Text = text; Column = column; }
            public Tok Kind { get; }
            public string Text { get; }
            public int Column { get; }
        }

        private sealed class Parser
        {
            private readonly List<Token> _tokens;
            private int _pos;
            private int _depth;

            private void Enter()
            {
                if (++_depth > MaxDepth) throw new ExprException($"expression too deeply nested (more than {MaxDepth} levels)", Peek.Column);
            }
            public List<IReadOnlyList<string>> Paths { get; } = new List<IReadOnlyList<string>>();

            public Parser(string source) { _tokens = Lex(source); }

            private Token Peek => _tokens[_pos];
            private Token Next() => _tokens[_pos++];
            private bool IsOp(string op) => Peek.Kind == Tok.Op && Peek.Text == op;

            private Token Expect(Tok kind, string what)
            {
                if (Peek.Kind != kind) throw new ExprException($"expected {what} but found {Describe(Peek)}", Peek.Column);
                return Next();
            }

            private static string Describe(Token t) => t.Kind == Tok.End ? "the end" : $"'{t.Text}'";

            public Node ParseAll()
            {
                if (Peek.Kind == Tok.End) throw new ExprException("empty expression", 1);
                var node = ParseTernary();
                if (Peek.Kind != Tok.End) throw new ExprException($"unexpected {Describe(Peek)}", Peek.Column);
                return node;
            }

            private Node ParseTernary()
            {
                Enter();
                try
                {
                    var cond = ParseOr();
                    if (Peek.Kind != Tok.Question) return cond;
                    Next();
                    var a = ParseTernary();
                    Expect(Tok.Colon, "':'");
                    var b = ParseTernary();
                    return new Ternary(cond, a, b);
                }
                finally { _depth--; }
            }

            private Node ParseOr()
            {
                var left = ParseAnd();
                while (IsOp("||")) { Next(); left = new Logic(false, left, ParseAnd()); }
                return left;
            }

            private Node ParseAnd()
            {
                var left = ParseEquality();
                while (IsOp("&&")) { Next(); left = new Logic(true, left, ParseEquality()); }
                return left;
            }

            private Node ParseEquality()
            {
                var left = ParseComparison();
                while (IsOp("==") || IsOp("!=")) { string op = Next().Text; left = new Binary(op, left, ParseComparison()); }
                return left;
            }

            private Node ParseComparison()
            {
                var left = ParseAdditive();
                while (IsOp("<") || IsOp("<=") || IsOp(">") || IsOp(">=")) { string op = Next().Text; left = new Binary(op, left, ParseAdditive()); }
                return left;
            }

            private Node ParseAdditive()
            {
                var left = ParseMultiplicative();
                while (IsOp("+") || IsOp("-")) { string op = Next().Text; left = new Binary(op, left, ParseMultiplicative()); }
                return left;
            }

            private Node ParseMultiplicative()
            {
                var left = ParseUnary();
                while (IsOp("*") || IsOp("/") || IsOp("%")) { string op = Next().Text; left = new Binary(op, left, ParseUnary()); }
                return left;
            }

            private Node ParseUnary()
            {
                Enter();
                try
                {
                    if (IsOp("!")) { Next(); return new Unary('!', ParseUnary()); }
                    if (IsOp("-")) { Next(); return new Unary('-', ParseUnary()); }
                    return ParsePostfix(ParsePrimary());
                }
                finally { _depth--; }
            }

            private Node ParsePostfix(Node node)
            {
                while (true)
                {
                    if (Peek.Kind == Tok.Dot) { Next(); node = new Member(node, Expect(Tok.Ident, "a name after '.'").Text); }
                    else if (Peek.Kind == Tok.LBracket) { Next(); var index = ParseTernary(); Expect(Tok.RBracket, "']'"); node = new Index(node, index); }
                    else return node;
                }
            }

            private Node ParsePrimary()
            {
                var t = Peek;
                switch (t.Kind)
                {
                    case Tok.Number:
                        Next();
                        return new Literal(Value.Of(double.Parse(t.Text, CultureInfo.InvariantCulture)));
                    case Tok.String:
                        Next();
                        return new Literal(Value.Of(t.Text));
                    case Tok.LParen:
                    {
                        Next();
                        var inner = ParseTernary();
                        Expect(Tok.RParen, "')'");
                        return inner;
                    }
                    case Tok.LBracket:
                    {
                        Next();
                        var items = new List<Node>();
                        if (Peek.Kind != Tok.RBracket)
                            do { items.Add(ParseTernary()); } while (Peek.Kind == Tok.Comma && Next().Kind == Tok.Comma);
                        Expect(Tok.RBracket, "']'");
                        return new ListNode(items.ToArray());
                    }
                    case Tok.Ident:
                    {
                        Next();
                        if (t.Text == "true") return new Literal(Value.True);
                        if (t.Text == "false") return new Literal(Value.False);
                        if (t.Text == "null") return new Literal(Value.Null);
                        if (Peek.Kind == Tok.LParen) return ParseCall(t);
                        // Gather a static path: a.b.c and a[0] with literal indexes.
                        var path = new List<string> { t.Text };
                        while (true)
                        {
                            if (Peek.Kind == Tok.Dot && _tokens[_pos + 1].Kind == Tok.Ident) { Next(); path.Add(Next().Text); }
                            else if (Peek.Kind == Tok.LBracket && (_tokens[_pos + 1].Kind == Tok.Number || _tokens[_pos + 1].Kind == Tok.String) && _tokens[_pos + 2].Kind == Tok.RBracket)
                            {
                                Next(); path.Add(Next().Text); Next();
                            }
                            else break;
                        }
                        Paths.Add(path);
                        return new PathNode(path.ToArray());
                    }
                    default:
                        throw new ExprException($"unexpected {Describe(t)}", t.Column);
                }
            }

            private Node ParseCall(Token name)
            {
                if (!Functions.TryGetValue(name.Text, out var arity))
                    throw new ExprException($"unknown function '{name.Text}' (available: {string.Join(", ", Functions.Keys)})", name.Column);
                Expect(Tok.LParen, "'('");
                var args = new List<Node>();
                if (Peek.Kind != Tok.RParen)
                    do { args.Add(ParseTernary()); } while (Peek.Kind == Tok.Comma && Next().Kind == Tok.Comma);
                Expect(Tok.RParen, "')'");
                if (args.Count < arity.min || args.Count > arity.max || (name.Text == "rand" && args.Count == 1) || (name.Text == "dist" && args.Count == 3))
                    throw new ExprException($"{name.Text}() takes {(arity.min == arity.max ? arity.min.ToString(CultureInfo.InvariantCulture) : name.Text == "rand" ? "0 or 2" : name.Text == "dist" ? "2 (points) or 4 (x1, y1, x2, y2)" : arity.min + " or more")} arguments", name.Column);
                return new Call(name.Text, args.ToArray());
            }

            private static List<Token> Lex(string s)
            {
                var tokens = new List<Token>();
                int i = 0;
                while (i < s.Length)
                {
                    char ch = s[i];
                    int col = i + 1;
                    if (char.IsWhiteSpace(ch)) { i++; continue; }
                    if (char.IsDigit(ch) || (ch == '.' && i + 1 < s.Length && char.IsDigit(s[i + 1])))
                    {
                        int start = i;
                        while (i < s.Length && (char.IsDigit(s[i]) || s[i] == '.')) i++;
                        if (i < s.Length && (s[i] == 'e' || s[i] == 'E'))
                        {
                            i++;
                            if (i < s.Length && (s[i] == '+' || s[i] == '-')) i++;
                            while (i < s.Length && char.IsDigit(s[i])) i++;
                        }
                        string text = s.Substring(start, i - start);
                        if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out _)) throw new ExprException($"bad number '{text}'", col);
                        tokens.Add(new Token(Tok.Number, text, col));
                        continue;
                    }
                    if (char.IsLetter(ch) || ch == '_')
                    {
                        int start = i;
                        while (i < s.Length && (char.IsLetterOrDigit(s[i]) || s[i] == '_')) i++;
                        tokens.Add(new Token(Tok.Ident, s.Substring(start, i - start), col));
                        continue;
                    }
                    if (ch == '`')
                    {
                        int end = s.IndexOf('`', i + 1);
                        if (end < 0) throw new ExprException("unclosed `", col);
                        tokens.Add(new Token(Tok.Ident, s.Substring(i + 1, end - i - 1), col));
                        i = end + 1;
                        continue;
                    }
                    if (ch == '"' || ch == '\'')
                    {
                        var sb = new StringBuilder();
                        i++;
                        while (i < s.Length && s[i] != ch)
                        {
                            if (s[i] == '\\' && i + 1 < s.Length) { i++; sb.Append(s[i] == 'n' ? '\n' : s[i]); }
                            else sb.Append(s[i]);
                            i++;
                        }
                        if (i >= s.Length) throw new ExprException("unclosed string", col);
                        i++;
                        tokens.Add(new Token(Tok.String, sb.ToString(), col));
                        continue;
                    }
                    string two = i + 1 < s.Length ? s.Substring(i, 2) : "";
                    if (two == "&&" || two == "||" || two == "==" || two == "!=" || two == "<=" || two == ">=")
                    {
                        tokens.Add(new Token(Tok.Op, two, col));
                        i += 2;
                        continue;
                    }
                    Tok? single = ch switch
                    {
                        '(' => Tok.LParen, ')' => Tok.RParen, '[' => Tok.LBracket, ']' => Tok.RBracket, ',' => Tok.Comma,
                        '.' => Tok.Dot, '?' => Tok.Question, ':' => Tok.Colon,
                        '+' => Tok.Op, '-' => Tok.Op, '*' => Tok.Op, '/' => Tok.Op, '%' => Tok.Op, '<' => Tok.Op, '>' => Tok.Op, '!' => Tok.Op,
                        _ => (Tok?)null,
                    };
                    if (single == null) throw new ExprException($"unexpected character '{ch}'", col);
                    tokens.Add(new Token(single.Value, ch.ToString(), col));
                    i++;
                }
                tokens.Add(new Token(Tok.End, "", s.Length + 1));
                tokens.Add(new Token(Tok.End, "", s.Length + 1));
                tokens.Add(new Token(Tok.End, "", s.Length + 1));
                return tokens;
            }
        }
    }
}
