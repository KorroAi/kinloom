#nullable enable
// KinloomDialogue: a dialogue box with a real character in it, for Unity 2021.3 and later. Add the component to any
// GameObject, write who the character is in one sentence, press Play. No UI package needed (the box is drawn with
// IMGUI); turn "Draw Default Box" off and use the events to show it in your own UI.
//
// The player types, or picks one of the replies you list (rewritten for the moment by the model: games played with a
// gamepad, on mobile or in VR). The character answers in its own voice, with a mood, feelings for the player and
// memories that last. What it decides to do while talking arrives as onAction(tool, argsJson). Without a model it
// answers with its offline line and the game keeps working.
//
// The client: set KinloomDialogue.Client once from code (native mode with your options, or a relay with a token);
// else every box uses a relay at Relay Url (`kinloom serve`, local by default). Never put a model key in a scene.
// With a Relay Token (a shipped game), each install gets its own session id (kept in PlayerPrefs, "kinloom-session"),
// so players never share one memory on the server. Kinloom's warnings go to the Unity console.
using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Events;

namespace Kinloom
{
    [AddComponentMenu("Kinloom/Kinloom Dialogue")]
    public sealed class KinloomDialogue : MonoBehaviour
    {
        [Serializable] public sealed class TextEvent : UnityEvent<string> { }
        /// <summary>tool, args as JSON ({"item": "sword"}).</summary>
        [Serializable] public sealed class ActionEvent : UnityEvent<string, string> { }
        [Serializable] public sealed class ChoicesEvent : UnityEvent<string[]> { }

        /// <summary>The client every KinloomDialogue uses. Set it from code before the boxes start (native mode, a relay
        /// with a token); null: a relay at relayUrl.</summary>
        public static KinloomClient? Client;

        [Header("Character")]
        public string characterName = "Mira";
        [Tooltip("Who they are, in one sentence. The model turns it once into a full inner life (kept in Kinloom's memory).")]
        [TextArea(2, 5)] public string soul = "a widowed blacksmith, gruff and proud, who secretly sold the king's sword";
        [Tooltip("What they say when no model answers.")]
        public string offlineLine = "...";
        [Tooltip("Language of what they say (empty: Kinloom's; \"auto\": the player's).")]
        public string language = "";
        [Tooltip("The player's name: the character remembers each person it talks to.")]
        public string speaker = "player";
        [Tooltip("Tools they may use while talking, as JSON: {\"give\": {\"item\": \"sword\"}, \"follow\": {}}. They arrive as onAction.")]
        [TextArea(1, 4)] public string toolsJson = "";
        [Tooltip("The character speaks first when the box opens.")]
        public bool speakFirst = true;
        [Tooltip("Open when the scene starts (else call Open()).")]
        public bool openOnStart = true;

        [Header("Player")]
        [Tooltip("Show a text field (keyboard games).")]
        public bool typing = true;
        [Tooltip("Replies shown as choices, rewritten for the moment by the model (each keeps its intent); offline they are shown as written.")]
        public string[] replyExamples = new string[0];

        [Header("Connection (when Client is not set from code)")]
        public string relayUrl = "http://127.0.0.1:7717";
        [Tooltip("A player token of your online relay (kinloom serve --token): never a model key.")]
        public string relayToken = "";

        [Header("Look")]
        public bool drawDefaultBox = true;
        public bool typewriter = true;
        [Tooltip("Characters per second for the typewriter.")]
        public float typewriterSpeed = 60f;

        [Header("Events")]
        public TextEvent onReply = new TextEvent();
        public ActionEvent onAction = new ActionEvent();
        [Tooltip("The visible thing the character does while speaking (\"points at the door\"): play an animation.")]
        public TextEvent onGesture = new TextEvent();
        public ChoicesEvent onChoices = new ChoicesEvent();
        public UnityEvent onClosed = new UnityEvent();

        /// <summary>Whether the box is open.</summary>
        public bool IsOpen { get; private set; }
        /// <summary>True while the character is answering.</summary>
        public bool Busy { get; private set; }
        /// <summary>The character's mood word (from its soul), "" until known.</summary>
        public string Mood { get; private set; } = "";
        /// <summary>The replies offered now (the examples, rewritten for the moment).</summary>
        public string[] Choices { get; private set; } = new string[0];

        private readonly List<(string who, string text)> _log = new List<(string who, string text)>();
        private string _typed = "";
        private float _shown;
        private Vector2 _scroll;
        private string _gesture = "";
        private bool _declared;

        private KinloomClient Kl => Client ??= new KinloomClient(relayUrl, SessionFor(relayToken), relayToken);

        /// <summary>A shipped game (a relay token): one session per install, kept in PlayerPrefs. Local play: "default".</summary>
        public static string SessionFor(string token)
        {
            if (string.IsNullOrEmpty(token)) return "default";
            var id = PlayerPrefs.GetString("kinloom-session", "");
            if (id.Length == 0)
            {
                id = "player-" + Guid.NewGuid().ToString("N");
                PlayerPrefs.SetString("kinloom-session", id);
                PlayerPrefs.Save();
            }
            return id;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void RouteWarnings() => KinloomClient.Warn = text => Debug.LogWarning(text);

        private void Start()
        {
            Declare();
            if (openOnStart) Open();
        }

        /// <summary>Declares the character (done at Start; call again after changing its fields from code).</summary>
        public void Declare()
        {
            var options = new Dictionary<string, object> { ["offline"] = offlineLine };
            var card = soul.TrimStart().StartsWith("{") ? Json.Read(soul) as Dictionary<string, object> : null;
            options["soul"] = card != null ? (object)card : (soul.Trim().Length > 0 ? (object)soul : true);
            if (!string.IsNullOrEmpty(language)) options["language"] = language;
            if (toolsJson.Trim().Length > 0)
            {
                if (Json.Read(toolsJson) is Dictionary<string, object> tools) options["tools"] = tools;
                else Debug.LogWarning("[kinloom] " + characterName + ": toolsJson is not a JSON object like {\"give\": {\"item\": \"sword\"}}");
            }
            Kl.Character(characterName, "", options);
            _declared = true;
        }

        /// <summary>Opens the box; the character speaks first when speakFirst is on.</summary>
        public void Open()
        {
            if (!_declared) Declare();
            if (IsOpen) return;
            IsOpen = true;
            if (speakFirst && _log.Count == 0) Send("");
            else RefreshChoices();
        }

        public void Close()
        {
            if (!IsOpen) return;
            IsOpen = false;
            onClosed.Invoke();
        }

        /// <summary>The player says text ("" lets the character speak first).</summary>
        public async void Send(string text)
        {
            if (Busy) return;
            text = (text ?? "").Trim();
            Busy = true;
            if (text.Length > 0) _log.Add((speaker, text));
            _typed = "";
            try
            {
                var reply = await Kl.Chat(characterName, text, null, speaker);
                if (this == null) return;                        // destroyed while the model was writing
                if (reply.Length > 0)
                {
                    _log.Add((characterName, reply));
                    _shown = typewriter ? 0f : reply.Length;
                    _scroll.y = float.MaxValue;
                    onReply.Invoke(reply);
                }
                foreach (var a in Kl.Act(characterName, null, false)) onAction.Invoke(a.Tool, Json.Write(a.Args));
                var s = await Kl.Soul(characterName, speaker);
                if (this == null) return;
                if (s != null)
                {
                    if (s.TryGetValue("mood", out var m) && m is Dictionary<string, object> mood && mood.TryGetValue("word", out var w)) Mood = w as string ?? "";
                    var g = s.TryGetValue("gesture", out var gv) ? gv as string ?? "" : "";
                    if (g.Length > 0 && g != _gesture) onGesture.Invoke(g);
                    _gesture = g;
                }
            }
            catch (Exception e) { Debug.LogException(e); }
            finally { if (this != null) Busy = false; }
            if (this != null) RefreshChoices();
        }

        /// <summary>The player picks choice i (0-based) of Choices.</summary>
        public void Choose(int i)
        {
            if (i >= 0 && i < Choices.Length) Send(Choices[i]);
        }

        private async void RefreshChoices()
        {
            if (replyExamples == null || replyExamples.Length == 0) return;
            try
            {
                var got = await Kl.Suggest(characterName, replyExamples, speaker);
                if (this == null) return;
                Choices = got.ToArray();
                onChoices.Invoke(Choices);
            }
            catch (Exception e) { Debug.LogException(e); }
        }

        private void Update()
        {
            if (_log.Count > 0 && _shown < _log[_log.Count - 1].text.Length) _shown += Time.unscaledDeltaTime * Mathf.Max(1f, typewriterSpeed);
        }

        private void OnGUI()
        {
            if (!drawDefaultBox || !IsOpen) return;
            float w = Mathf.Min(Screen.width - 20, 720), h = Mathf.Min(Screen.height * 0.45f, 300);
            var area = new Rect((Screen.width - w) / 2, Screen.height - h - 10, w, h);
            GUI.Box(area, GUIContent.none);
            GUILayout.BeginArea(new Rect(area.x + 10, area.y + 8, area.width - 20, area.height - 16));
            GUILayout.BeginHorizontal();
            GUILayout.Label("<b>" + Plain(characterName) + "</b>" + (Mood.Length > 0 ? "  <i>(" + Plain(Mood) + ")</i>" : ""), Rich());
            GUILayout.FlexibleSpace();
            if (GUILayout.Button("x", GUILayout.Width(24))) Close();
            GUILayout.EndHorizontal();
            _scroll = GUILayout.BeginScrollView(_scroll);
            var sb = new StringBuilder();
            for (int i = 0; i < _log.Count; i++)
            {
                var (who, said) = _log[i];
                if (i == _log.Count - 1 && who == characterName && _shown < said.Length) said = said.Substring(0, (int)_shown);
                sb.Append(who == characterName ? "<b>" + Plain(who) + ":</b> " : "<color=#9ab>" + Plain(who) + ":</color> ").Append(Plain(said)).Append('\n');
            }
            if (Busy) sb.Append("<i>...</i>");
            GUILayout.Label(sb.ToString(), Rich());
            GUILayout.EndScrollView();
            for (int i = 0; i < Choices.Length; i++)
                if (GUILayout.Button((i + 1) + ". " + Choices[i]) && !Busy) Choose(i);
            if (typing)
            {
                GUILayout.BeginHorizontal();
                GUI.SetNextControlName("kinloom-input");
                _typed = GUILayout.TextField(_typed, 300);
                var enter = Event.current.type == EventType.KeyDown && (Event.current.keyCode == KeyCode.Return || Event.current.keyCode == KeyCode.KeypadEnter)
                            && GUI.GetNameOfFocusedControl() == "kinloom-input";
                if ((GUILayout.Button("Say", GUILayout.Width(60)) || enter) && !Busy && _typed.Trim().Length > 0)
                {
                    Send(_typed);
                    if (enter) Event.current.Use();
                }
                GUILayout.EndHorizontal();
            }
            if (Event.current.type == EventType.KeyDown && !Busy && GUI.GetNameOfFocusedControl() != "kinloom-input")
            {
                int n = Event.current.keyCode - KeyCode.Alpha1;
                if (n >= 0 && n < Choices.Length) { Choose(n); Event.current.Use(); }
                else if (Event.current.keyCode == KeyCode.Escape) { Close(); Event.current.Use(); }
            }
            GUILayout.EndArea();
        }

        // what players and the model write is shown as text, never as markup
        private static string Plain(string s) => s.Replace("<", "<​");

        private static GUIStyle? _rich;
        private static GUIStyle Rich() => _rich ??= new GUIStyle(GUI.skin.label) { richText = true, wordWrap = true };
    }
}
