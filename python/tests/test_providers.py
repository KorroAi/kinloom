import time

import pytest

from conftest import openai_reply
from kinloom.providers import Anthropic, OpenAICompatible, Scripted, detect


def test_openai_compatible_sends_json_mode_and_reads_usage(http):
    http.answer(body=openai_reply('{"a": 1}', prompt=100, completion=5, cached=60))
    p = OpenAICompatible(http.url, "key", "deepseek-flash", deepseek=True)
    r = p.complete("You are a test.", "Hello", json_mode=True)
    assert r.ok and r.text == '{"a": 1}'
    assert (r.input_tokens, r.cached_tokens, r.output_tokens) == (100, 60, 5)
    req = http.requests[0]
    assert req["path"] == "/chat/completions"
    assert req["headers"]["authorization"] == "Bearer key"
    assert req["body"]["response_format"] == {"type": "json_object"}
    assert req["body"]["thinking"] == {"type": "disabled"}
    prompt = req["body"]["messages"][0]["content"] + req["body"]["messages"][1]["content"]
    assert "json" in prompt.lower()


def test_transient_errors_are_retried_once(http):
    http.answer(503, {"error": "busy"}).answer(200, openai_reply("ok"))
    r = OpenAICompatible(http.url, "k", "m").complete("s", "u")
    assert r.ok and len(http.requests) == 2


def test_bad_requests_are_not_retried(http):
    http.answer(400, {"error": "bad"})
    r = OpenAICompatible(http.url, "k", "m").complete("s", "u")
    assert not r.ok and "400" in r.error and len(http.requests) == 1


def test_a_slow_server_times_out(http):
    def slow(_):
        time.sleep(2)
        return openai_reply("late")
    http.answer(200, slow)
    start = time.time()
    r = OpenAICompatible(http.url, "k", "m").complete("s", "u", timeout=0.5)
    assert not r.ok and "timed out" in r.error
    assert time.time() - start < 1.8


def test_empty_or_odd_answers_are_failures_not_crashes(http):
    http.answer(200, {"choices": []})
    assert not OpenAICompatible(http.url, "k", "m").complete("s", "u").ok
    http.answers.clear()
    http.answer(200, "not json at all")
    assert not OpenAICompatible(http.url, "k", "m").complete("s", "u").ok


def test_streaming_delivers_text_pieces(http):
    chunks = ['{"choices":[{"delta":{"content":"You are "}}]}', '{"choices":[{"delta":{"content":"P3."}}]}',
              '{"choices":[],"usage":{"prompt_tokens":20,"completion_tokens":4}}']
    body = "".join("data: %s\n\n" % c for c in chunks) + "data: [DONE]\n\n"
    http.answer(200, body, {"Content-Type": "text/event-stream"})
    pieces = []
    r = OpenAICompatible(http.url, "k", "m").complete("s", "u", on_text=pieces.append)
    assert r.ok and r.text == "You are P3." and pieces == ["You are ", "P3."]
    assert r.output_tokens == 4
    assert http.requests[0]["body"]["stream"] is True


def test_anthropic_caches_the_system_prompt(http):
    http.answer(200, {"content": [{"type": "text", "text": '{"a":1}'}], "stop_reason": "end_turn",
                      "usage": {"input_tokens": 30, "output_tokens": 4, "cache_read_input_tokens": 20}})
    r = Anthropic("k", "claude-haiku-4-5", base_url=http.url).complete("Stable system.", "u", json_mode=True)
    assert r.ok and r.text == '{"a":1}'
    assert r.input_tokens == 50 and r.cached_tokens == 20
    req = http.requests[0]
    assert req["path"] == "/v1/messages"
    assert req["headers"]["x-api-key"] == "k"
    assert req["body"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["body"]["model"] == "claude-haiku-4-5"


def test_anthropic_refusal_is_a_failure(http):
    http.answer(200, {"content": [], "stop_reason": "refusal", "usage": {}})
    assert not Anthropic("k", "m", base_url=http.url).complete("s", "u").ok


def test_scripted_provider():
    p = Scripted(lambda kind, system, user: "hi" if "Hello" in user else None)
    assert p.complete("s", "Hello").text == "hi"
    assert not p.complete("s", "Bye").ok


def test_detection_order():
    assert detect({}, probe_ollama=False) is None
    p = detect({"DEEPSEEK_API_KEY": "d"}, probe_ollama=False)
    assert p.model == "deepseek-flash" and "deepseek" in p.name
    p = detect({"ANTHROPIC_API_KEY": "a"}, probe_ollama=False)
    assert isinstance(p, Anthropic) and p.model == "claude-haiku-4-5"
    assert detect({"OPENAI_API_KEY": "o"}, probe_ollama=False) is None  # no model is ever guessed for OpenAI
    p = detect({"OPENAI_API_KEY": "o", "KINLOOM_MODEL": "gpt-x"}, probe_ollama=False)
    assert p.model == "gpt-x"
    p = detect({"KINLOOM_BASE_URL": "http://x/v1", "KINLOOM_MODEL": "m", "DEEPSEEK_API_KEY": "d"}, probe_ollama=False)
    assert p.base_url == "http://x/v1" and p.model == "m"
    assert detect({"OPENROUTER_API_KEY": "r"}, probe_ollama=False) is None  # no model is ever guessed for OpenRouter
    p = detect({"OPENROUTER_API_KEY": "r", "KINLOOM_MODEL": "vendor/model"}, probe_ollama=False)
    assert p.base_url == "https://openrouter.ai/api/v1" and p.model == "vendor/model" and p.name == "openrouter"
    p = detect({"DEEPSEEK_API_KEY": "d", "OPENROUTER_API_KEY": "r", "KINLOOM_MODEL": "vendor/model"}, probe_ollama=False)
    assert p.name == "openrouter"          # an OpenRouter model name wins over another provider's key
    assert detect({"DEEPSEEK_API_KEY": "d", "OPENROUTER_API_KEY": "r"}, probe_ollama=False).name == "deepseek"


@pytest.mark.ollama
def test_ollama_is_found_when_running(http):
    http.answer(200, {"models": [{"name": "llama3.2:3b"}, {"name": "qwen2.5:7b"}]})
    p = detect({}, probe_ollama=True, ollama_url=http.url)
    assert p is not None and p.model == "llama3.2:3b" and p.base_url == http.url + "/v1"


def test_kinloom_offline_forces_offline_mode_even_with_keys():
    from kinloom import config
    env = {"KINLOOM_OFFLINE": "1", "DEEPSEEK_API_KEY": "k", "ANTHROPIC_API_KEY": "k"}
    assert detect(env, probe_ollama=False) is None
    assert config.provider({"provider": "deepseek"}, env) is None


def test_an_explicit_endpoint_in_the_environment_wins_over_kinloom_json():
    from kinloom import config
    env = {"KINLOOM_BASE_URL": "http://127.0.0.1:9/v1", "KINLOOM_MODEL": "m", "DEEPSEEK_API_KEY": "k"}
    p = config.provider({"provider": "deepseek", "model": "deepseek-flash"}, env)
    assert p.name == "custom" and p.model == "m"
    p = config.provider({"provider": "deepseek"}, {"DEEPSEEK_API_KEY": "k", "DEEPSEEK_BASE_URL": "http://127.0.0.1:8"})
    assert "127.0.0.1:8" in p.base_url


def test_newer_models_that_refuse_max_tokens_and_temperature_are_adapted_to_once(http):
    refuse = lambda param: {"error": {"message": "Unsupported parameter: '%s' is not supported with this model." % param}}
    http.answer(400, refuse("max_tokens")).answer(400, refuse("temperature")).answer(200, openai_reply("hi"))
    p = OpenAICompatible(http.url, "k", "gpt-x", name="openai")
    r = p.complete("sys", "user", timeout=5)
    assert r.ok and r.text == "hi"
    last = http.requests[-1]["body"]
    assert "max_completion_tokens" in last and "max_tokens" not in last and "temperature" not in last
    before = len(http.requests)
    assert p.complete("sys", "user", timeout=5).ok
    assert len(http.requests) == before + 1          # learned: no more refused calls


def test_an_endless_answer_is_cut_off(http, monkeypatch):
    import kinloom.providers as pr
    monkeypatch.setattr(pr, "MAX_ANSWER", 1000)
    http.answer(200, openai_reply("x" * 5000))
    r = OpenAICompatible(http.url, "k", "m").complete("s", "u", timeout=5)
    assert not r.ok and "too large" in r.error


def test_openrouter_turns_reasoning_off_and_learns_when_refused(http):
    http.answer(body=openai_reply("hi")).answer(400, {"error": {"message": "reasoning is not supported for this model"}}) \
        .answer(body=openai_reply("hi"))
    p = OpenAICompatible(http.url, "k", "vendor/model", name="openrouter")
    assert p.complete("s", "u").ok
    assert http.requests[0]["body"]["reasoning"] == {"enabled": False}      # game calls need speed, not reasoning
    assert p.complete("s", "u").ok
    assert "reasoning" not in http.requests[2]["body"]


def test_calls_reuse_one_connection_to_the_provider(http):
    http.answer(body=openai_reply("a"))
    p = OpenAICompatible(http.url, "k", "m")
    for _ in range(3):
        assert p.complete("s", "u").ok
    assert len({r["peer"] for r in http.requests}) == 1          # no new TCP (and TLS) handshake per call


def test_a_connection_closed_by_the_server_is_replaced_silently(http):
    http.answer(body=openai_reply("a"), headers={"Connection": "close"}).answer(body=openai_reply("b"))
    p = OpenAICompatible(http.url, "k", "m")
    assert p.complete("s", "u").text == "a"
    assert p.complete("s", "u").text == "b"
