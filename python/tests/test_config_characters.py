"""Characters, lore and souls declared in kinloom.json: the game only calls them (every engine, no declaration code),
and edits are picked up while the game runs."""
import json
import os
import time

from kinloom import Kinloom
from test_brain import model


def write(folder, data):
    with open(os.path.join(folder, "kinloom.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_characters_from_the_config_answer_without_being_declared(tmp_path):
    write(tmp_path, {"lore": ["The village is Ashford."],
                     "characters": {"Mira": {"soul": {"summary": "a gruff smith"}, "offline": "Busy.",
                                             "tools": {"give": {"item": "sword"}}, "trust": {"give": 0.3}}}})
    p = model(chat="Hm.")
    kl = Kinloom(provider=p, memory_path=None, folder=str(tmp_path))
    assert kl.chat("Mira", "hi") == "Hm."
    system = [c for c in p.calls if c[0] == "chat"][-1][1]
    assert "a gruff smith" in system and "The village is Ashford." in system and "give" in system
    assert kl.brain.is_declared("default", "Mira")
    off = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    assert off.chat("Mira", "hi") == "Busy." and off.lore() == ["The village is Ashford."]


def test_every_session_gets_the_config_characters(tmp_path):
    write(tmp_path, {"characters": {"Mira": {"personality": "a smith", "offline": "Busy."}}})
    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    assert kl.session("player-2").chat("Mira", "hi") == "Busy."


def test_edits_to_the_config_are_picked_up_while_running(tmp_path):
    write(tmp_path, {"characters": {"Mira": {"personality": "a smith", "offline": "Busy."}}})
    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    kl.brain.config_every = 0.0
    assert kl.chat("Mira", "hi") == "Busy."
    time.sleep(0.02)
    write(tmp_path, {"characters": {"Mira": {"personality": "a smith", "offline": "Closed today."}}})
    os.utime(os.path.join(tmp_path, "kinloom.json"), (time.time() + 5, time.time() + 5))
    assert kl.chat("Mira", "hi") == "Closed today."


def test_a_character_declared_by_the_game_wins_over_the_config(tmp_path):
    write(tmp_path, {"characters": {"Mira": {"offline": "From the config."}}})
    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    kl.character("Mira", offline="From the game.")
    assert kl.chat("Mira", "hi") == "From the game."


def test_bad_character_entries_are_skipped_not_fatal(tmp_path):
    write(tmp_path, {"characters": {"Mira": "not an object", "Bram": {"offline": "Morning!", "unknown_key": 1,
                                                                        "max_words": "lots"}}})
    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    assert kl.chat("Bram", "hi") == "Morning!"
    assert kl.chat("Mira", "hi") == ""


def test_config_characters_are_ready_before_the_first_meeting(tmp_path):
    write(tmp_path, {"characters": {"Mira": {"soul": "a gruff smith"}}})
    p = model(soul={"summary": "a gruff smith"}, greet="You. Buying?", chat="Hm.")
    kl = Kinloom(provider=p, memory_path=None, folder=str(tmp_path))
    kl.wait_idle(5)                                           # card and greeting prepared at start
    assert kl.chat("Mira", "", speaker="Ana") == "You. Buying?"


def test_players_share_cards_and_greetings_instead_of_paying_for_each(tmp_path):
    write(tmp_path, {"characters": {"Mira": {"soul": "a gruff smith"}}})
    p = model(soul={"summary": "a gruff smith"}, greet=["Welcome, one.", "Welcome, two.", "Welcome, three."], chat="Hm.")
    kl = Kinloom(provider=p, memory_path=None, folder=str(tmp_path))
    kl.wait_idle(5)
    first = kl.session("player-1").chat("Mira", "", speaker="Ana")
    kl.wait_idle(5)
    second = kl.session("player-2").chat("Mira", "", speaker="Bob")
    kl.wait_idle(5)
    assert (first, second) == ("Welcome, one.", "Welcome, two.")
    assert len([c for c in p.calls if c[0] == "soul"]) == 1          # one card for every player
    assert len([c for c in p.calls if c[0] == "chat"]) == 0
