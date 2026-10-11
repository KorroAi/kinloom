// Lantern Row: a tiny .NET game with no AI and no mod API. The proof treats it as a closed game: only its built .dll
// is read (by REA) and patched (by the mod); nothing in the mod refers to this source.
using System;

namespace LanternRow
{
    public class Player
    {
        public string Name = "Ana";
        public int Coins = 12;
    }

    public class Shopkeeper
    {
        int _visits;

        public string Greet(Player p)
        {
            _visits++;
            if (_visits == 1) return "Welcome to Lantern Row, " + p.Name + ". Oil is 3 coins a flask.";
            return p.Coins < 3 ? "No coins, no oil, " + p.Name + "." : "Back again, " + p.Name + "? Still 3 coins.";
        }

        public string Answer(Player p, string question)
        {
            switch (question.Trim().ToLowerInvariant())
            {
                case "price": return "3 coins a flask.";
                case "guard": return "Ask him yourself.";
                default: return "I sell oil, not answers.";
            }
        }
    }

    public class Guard
    {
        static readonly string[] Rounds = { "Move along.", "Keep the lamps lit.", "Curfew at nine." };
        int _round;

        public void Shout(string text)
        {
            Console.WriteLine("Guard: " + text);
        }

        public void Patrol(int hour)
        {
            Shout(hour >= 21 ? "Curfew! Inside, all of you." : Rounds[_round++ % Rounds.Length]);
        }
    }

    public static class Program
    {
        public static void Main(string[] args)
        {
            var ana = new Player();
            var marlo = new Shopkeeper();
            var guard = new Guard();
            Console.WriteLine("Marlo: " + marlo.Greet(ana));
            Console.WriteLine("Ana: What's on the guard's mind tonight?");
            Console.WriteLine("Marlo: " + marlo.Answer(ana, "What's on the guard's mind tonight?"));
            guard.Patrol(20);
            guard.Patrol(21);
            Console.WriteLine("Marlo: " + marlo.Greet(ana));
        }
    }
}
