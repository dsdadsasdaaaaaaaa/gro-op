"""Exercises the advisor plumbing (context building, structured-output handling, applying tasks /
photo requests / clamped target changes) with a stubbed Claude client. No network."""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from grow_brain.advisor import Advisor, AdvisorError
from grow_brain.controller import Controller
from grow_brain.ha import HAClient
from grow_brain.models import BriefOut, ChatOut, LogAdviceOut, PhotoAnalysisOut
from grow_brain.notify import Notifier
from grow_brain.store import Store


class FakeParse:
    def __init__(self):
        self.calls = []
        self.next = None

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        model = kwargs["output_format"]
        out = self.next or model.model_validate(DEFAULTS[model])
        return SimpleNamespace(stop_reason="end_turn", parsed_output=out, content=[],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


DEFAULTS = {
    BriefOut: {"headline": "Day 5 – fine", "summary": "All good.", "concerns": [], "actions": ["Water tomorrow"],
               "per_plant": [{"plant_id": 1, "headline": "Levi: fine", "summary": "Keep going."}, {"plant_id": 2, "headline": "Dad: fine", "summary": "Same."}],
               "target_changes": [{"field": "humidity_max", "to": 40, "reason": "test clamp"}],
               "photo_requests": [{"plant_id": 2, "title": "Top of canopy", "instructions": "From above, light off, flash on", "reason": "check"}],
               "tasks": [{"plant_id": 1, "title": "Water 1 L", "detail": "pH 6.3", "due": None, "priority": "normal"}]},
    LogAdviceOut: {"summary": "pH a bit high", "steps": ["Use pH 6.2 water next"], "urgency": "attention", "tasks_done": [1],
                   "target_changes": [], "photo_requests": [], "tasks": [{"title": "Water 1 L", "detail": "dupe", "due": None, "priority": "normal"}]},
    PhotoAnalysisOut: {"summary": "Healthy", "health_score": 9, "findings": [{"title": "ok", "severity": "info", "detail": "fine"}],
                       "actions": [], "target_changes": [], "photo_requests": [], "tasks": []},
    ChatOut: {"reply": "Sure.", "target_changes": [], "photo_requests": [], "tasks": [{"title": "Buy pH down", "detail": "", "due": None, "priority": "high"}]},
}


@pytest.fixture
async def env(tmp_path: Path):
    store = Store(tmp_path / "t.sqlite")
    await store.open()
    ha = HAClient("http://127.0.0.1:1", "x")
    notifier = Notifier(ha, store)
    controller = Controller(store, ha, "UTC", notifier)
    await store.set_kv("grow_profile", {"stage": "veg", "start_date": "2026-09-01", "stage_started": "2026-09-10"})
    await store.set_device("temperature_sensor", "sensor.t")
    await store.set_device("light", "switch.l")
    await store.add_plant(name="Levi's plant", owner="Levi", start_date="2026-09-19", notify_service="notify.levi")
    await store.add_plant(name="Dad's plant", owner="Dad", start_date="2026-09-19", notify_service="notify.dad")
    adv = Advisor(store, controller, "sk-test", "claude-opus-5", notifier, tmp_path)
    fake = FakeParse()
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=fake)))
    client.with_options = lambda **k: (fake.options.append(k), client)[1]
    fake.options = []
    adv.client = client
    yield store, adv, fake
    await store.close()
    await ha.close()


async def test_brief_applies_and_clamps(env):
    store, adv, fake = env
    brief = await adv.daily_brief()
    assert brief["headline"] == "Day 5 – fine"
    assert len(brief["tasks"]) == 1 and len(brief["photo_requests"]) == 1
    # humidity_max asked 40 from 65 → clamped to a 5-point nudge → 60
    ch = brief["target_changes"][0]
    assert ch["from"] == 65.0 and ch["to"] == 60.0 and ch["applied"] is True
    t, _, _ = await adv.controller.effective_targets()
    assert t.humidity_max == 60.0 and t.source == "advisor"
    assert (await store.latest_brief())["headline"] == "Day 5 – fine"
    assert [pb["name"] for pb in brief["per_plant"]] == ["Levi's plant", "Dad's plant"]
    prs = await store.photo_requests("open")
    assert len(prs) == 1 and prs[0]["plant_id"] == 2 and brief["tasks"][0]["plant_id"] == 1
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5" and call["fallbacks"] == "default"
    assert "plant_id=2" in call["messages"][-1]["content"] and "Dad" in call["messages"][-1]["content"]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Liberty Haze" in call["messages"][-1]["content"]
    assert "NO (not connected yet)" in call["messages"][-1]["content"]  # exhaust not ducted is surfaced


async def test_log_advice_dedupes_tasks(env):
    store, adv, fake = env
    await adv.daily_brief()
    entry = await store.add_log_entry("ph", 6.8, "pH", "runoff", None, plant_id=2)
    advice = await adv.advise_on_log(entry)
    assert "Dad just logged for plant_id=2" in fake.calls[-1]["messages"][-1]["content"]
    assert advice["urgency"] == "attention"
    assert advice["tasks_done"] == [1]  # advisor closed the brief's task #1 itself
    assert (await store.get_task(1))["status"] == "done"
    # "Water 1 L" is open for plant 1; the same title for plant 2 is a different task and is created for plant 2
    assert advice["tasks"] and advice["tasks"][0]["plant_id"] == 2
    assert (await store.get_log_entry(entry["id"]))["advice_summary"] == "pH a bit high"


async def test_photo_analysis_marks_request_done(env, tmp_path):
    store, adv, fake = env
    pr = await store.add_photo_request("Top", "From above", "check")
    img = tmp_path / "p.jpg"
    Image.new("RGB", (50, 50), (0, 128, 0)).save(img, "JPEG")
    pid = await store.add_photo(pr["id"], None, str(img))
    a = await adv.analyse_photo(pid, img, "image/jpeg", pr, "note")
    assert a["health_score"] == 9
    assert (await store.get_photo_request(pr["id"]))["status"] == "done"
    content = fake.calls[0]["messages"][-1]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"


async def test_chat_keeps_history_and_adds_task(env):
    store, adv, fake = env
    r = await adv.chat("remind me to buy pH down")
    assert "Buy pH down" in r["reply"]
    r2 = await adv.chat("thanks")
    hist = fake.calls[1]["messages"]
    assert hist[0]["role"] == "user" and hist[1]["role"] == "assistant" and hist[-1]["role"] == "user"
    assert len(await store.chat_history()) == 4


async def test_refusal_surfaces_cleanly(env):
    store, adv, fake = env

    async def refuse(**kwargs):
        return SimpleNamespace(stop_reason="refusal", parsed_output=None, content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=0))

    adv.client.beta.messages.parse = refuse
    with pytest.raises(AdvisorError):
        await adv.chat("hi")


async def test_no_key_means_disabled(env):
    store, adv, fake = env
    adv.client = None
    assert not adv.enabled
    with pytest.raises(AdvisorError):
        await adv.daily_brief()



def test_task_dedupe_catches_rewordings_but_not_different_jobs():
    from grow_brain.advisor import _similar, _words
    assert _similar(_words("Dim the LED to ~30 %"), _words("Dim the LED to about 40%"))
    assert _similar(_words("Put a clear dome over Levi's cup"), _words("Dome over the cup"))
    assert not _similar(_words("Check the towel"), _words("Check the cup"))
    assert not _similar(_words("Refill the humidifier tank"), _words("Level the LED panel"))



async def test_second_nudge_the_same_day_is_capped(env):
    store, adv, fake = env
    await adv.daily_brief()                   # humidity_max 65 → 60 (the full 5-point daily budget)
    await adv.daily_brief()                   # asks for 40 again: nothing left today
    t, _, _ = await adv.controller.effective_targets()
    assert t.humidity_max == 60.0


async def test_fahrenheit_slip_and_system_tasks_and_budget(env):
    store, adv, fake = env
    await store.set_kv("settings", {"units": "f"})
    fake.next = BriefOut.model_validate({**DEFAULTS[BriefOut], "target_changes": [{"field": "temp_max_c", "to": 80.0, "reason": "°F slip"}]})
    brief = await adv.daily_brief()
    ch = brief["target_changes"][0]
    assert ch["to"] < ch["from"] + 0.01 or abs(ch["to"] - 26.7) < 1.5     # 80 °F read as 26.7 °C, never "raise to 32 °C"
    # the advisor can't tick off the app's own refill task
    task = await store.add_task("Refill the humidifier tank", "x", None, "high", "system")
    fake.next = LogAdviceOut.model_validate({**DEFAULTS[LogAdviceOut], "tasks_done": [task["id"]]})
    await adv.advise_on_log(await store.add_log_entry("note", None, None, None, "hi", 1))
    assert (await store.get_task(task["id"]))["status"] == "open"
    # a spent budget stops calls with a plain message
    await store.set_kv("settings", {"advisor_budget_usd": 0.01})
    await store.add_usage("brief", "claude-opus-5", 1, 0, 0, 1, 1.0)
    fake.next = None
    with pytest.raises(AdvisorError, match="budget"):
        await adv.daily_brief()


async def test_interactive_calls_fail_fast_and_cost_is_recorded_on_cutoff(env):
    store, adv, fake = env
    await adv.chat("hello", 1)
    assert fake.options and fake.options[-1]["max_retries"] == 0
    orig = fake.__call__

    async def cut(**kwargs):
        fake.calls.append(kwargs)
        return SimpleNamespace(stop_reason="max_tokens", parsed_output=None, content=[], model="claude-opus-5",
                               usage=SimpleNamespace(input_tokens=100, output_tokens=16000, cache_read_input_tokens=0))
    adv.client.beta.messages.parse = cut
    before = (await store.usage_summary("2000-01-01"))["calls"]
    with pytest.raises(AdvisorError, match="cut off"):
        await adv.chat("long question", 1)
    assert (await store.usage_summary("2000-01-01"))["calls"] == before + 1


def test_sdk_accepts_the_arguments_the_advisor_sends():
    """Catch a renamed SDK argument in CI instead of in the growers' tent."""
    import inspect
    import anthropic
    client = anthropic.AsyncAnthropic(api_key="x")
    sig = inspect.signature(client.beta.messages.parse)
    params = sig.parameters
    for name in ("model", "max_tokens", "system", "messages", "output_format", "output_config", "betas"):
        assert name in params, name
    assert "fallbacks" in params or any(p.kind == p.VAR_KEYWORD for p in params.values())
    assert hasattr(client, "with_options")
