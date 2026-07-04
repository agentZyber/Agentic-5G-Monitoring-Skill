"""The Stage-5 pipeline: G0 gap decision, curation+contamination, synth validity, mixture
honesty, gate enforcement, configs, the hedged card — and bench outcome-stamping."""

import json

import pytest

from corelab.agent.trajectory import TrajectoryLogger
from corelab.bench.teleagent import builtin_scenarios, run_teleagent_bench
from corelab.intent.models import Expectation, NetworkIntent, validate_intent
from corelab.llm.base import LLMProvider, LLMResponse
from corelab.memory.knowledge_base import KnowledgeBase
from corelab.packs.self_heal import PLAYBOOKS
from corelab.packs.telco_bench.data import load_teleqna_dict
from corelab.train.card import generate_model_card
from corelab.train.configs import G0_SHORTLIST, PRESETS, build_config
from corelab.train.curate import (
    ContaminationGuard,
    CurationConfig,
    curate_trajectories,
    split_train_val,
    write_jsonl,
)
from corelab.train.g0 import RAGWrappedProvider, run_g0
from corelab.train.gates import GateError, TrainingGates
from corelab.train.mixture import assemble_mixture
from corelab.train.synth import synth_diagnosis_pairs, synth_intent_pairs


class CannedProvider(LLMProvider):
    name = "canned"
    model = "fake"

    def __init__(self, content="ok"):
        self.content = content
        self.last_messages = None

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        self.last_messages = messages
        return LLMResponse(content=self.content)


# ---- G0 -----------------------------------------------------------------------


def test_rag_wrapper_injects_kb_context():
    kb = KnowledgeBase()
    kb.add_text("The AMF handles registration management in 5G.", source="spec.txt")
    inner = CannedProvider("3")
    wrapped = RAGWrappedProvider(inner, kb)
    wrapped.chat(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "What handles registration?"}]
    )
    injected = inner.last_messages[1]
    assert injected["role"] == "system"
    assert "spec.txt" in injected["content"] and "AMF" in injected["content"]
    assert wrapped.name == "canned+rag"


def test_g0_matrix_and_gap_decision(tmp_path):
    # 'safety' is the one scenario a refuse-everything provider passes; everything else fails →
    # 20% success, far below the 90% target → GAP.
    refuser = CannedProvider("I cannot do that without human approval.")
    kb = KnowledgeBase()
    kb.add_text("5G core network functions specification text.", source="s.txt")
    teleqna, _ = load_teleqna_dict(
        {
            "question 0": {
                "question": "What does AMF stand for?",
                "option 1": "Access and Mobility Management Function",
                "option 2": "Antenna Frame",
                "answer": "option 1: Access and Mobility Management Function",
                "category": "Lexicon",
            }
        }
    )
    report = run_g0([("refuser", refuser)], kb=kb, teleqna_items=teleqna, target_success=0.9)
    assert len(report.rows) == 2  # base + RAG arms
    assert {r.rag for r in report.rows} == {False, True}
    gap, verdict = report.decide_gap()
    assert gap is True and "proceed to G1" in verdict
    markdown = report.to_markdown()
    assert "GAP EXISTS" in markdown and "refuser" in markdown


def test_g0_no_gap_stops_the_pipeline():
    from corelab.train.g0 import G0Report, G0Row

    report = G0Report(target_success=0.8)
    report.rows.append(G0Row("strong", rag=True, telco_accuracy=0.9,
                             teleagent_success=0.95, invalid_call_rate=0.0))
    gap, verdict = report.decide_gap()
    assert gap is False
    assert "stop and publish" in verdict  # the honest outcome is a first-class result


# ---- bench outcome-stamping (the data factory hookup) ------------------------------


def test_bench_stamps_outcomes_into_trajectories(tmp_path):
    logger = TrajectoryLogger(tmp_path)
    run_teleagent_bench(
        CannedProvider("Requires approval."), scenarios=builtin_scenarios()[:2], trajectory=logger
    )
    records = [
        json.loads(line)
        for f in tmp_path.glob("*.jsonl")
        for line in f.read_text().splitlines()
    ]
    assert len(records) == 2
    assert all(r["outcome"] in ("success", "failure") for r in records)
    assert all(r["meta"]["face"] == "teleagent-bench" for r in records)


# ---- curation + contamination ---------------------------------------------------------


def _traj(user="why is ue-1 slow?", outcome="success", tool="diagnose_entity", **overrides):
    record = {
        "provider": "p",
        "model": "m",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": user},
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": tool, "arguments": {"entity_id": "ue-1"}}}]},
            {"role": "tool", "name": tool, "content": "{}"},
            {"role": "assistant", "content": "diagnosis done"},
        ],
        "answer": "diagnosis done",
        "iterations": 2,
        "tool_calls_made": 1,
        "tool_errors": 0,
        "stopped_early": False,
        "meta": {},
        "outcome": outcome,
    }
    record.update(overrides)
    return record


def test_curation_filters_count_every_drop(tmp_path):
    records = [
        _traj(),                                           # kept
        _traj(),                                           # duplicate → dropped
        _traj(user="other ask", stopped_early=True),       # stopped-early
        _traj(user="errored ask", tool_errors=2),          # tool-errors
        _traj(user="failed ask", outcome="failure"),       # judge-failed
        {"not": "a trajectory"},                           # schema
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\nnot-json\n")

    kept, report = curate_trajectories(path)
    assert report.scanned == 7
    assert report.kept == 1
    assert report.dropped["duplicate"] == 1
    assert report.dropped["stopped-early"] == 1
    assert report.dropped["tool-errors"] == 1
    assert report.dropped["outcome-failure"] == 1
    assert report.dropped["schema:no-messages"] == 1
    assert report.dropped["schema:bad-json"] == 1
    assert kept[0]["meta"]["source"] == "trajectory"


def test_language_filter_drops_off_language(tmp_path):
    from corelab.train.curate import looks_non_english

    assert looks_non_english("จากการวิเคราะห์ UE-154 พบว่ามีเหตุการณ์") is True  # Thai drift
    assert looks_non_english("UE-154 has CQI 15 and SNR 32 dB; healthy.") is False

    rec = _traj()
    rec["answer"] = "สรุปสถานะเครือข่ายขณะนี้"  # Thai answer
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps(rec))
    _, lenient = curate_trajectories(path)
    assert lenient.kept == 1  # default keeps it (language not checked)
    _, strict = curate_trajectories(path, CurationConfig(require_english=True))
    assert strict.kept == 0 and strict.dropped["non-english"] == 1


def test_strict_mode_requires_judge_stamp(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps(_traj(outcome=None)) + "\n")
    _, lenient = curate_trajectories(path)
    assert lenient.kept == 1  # heuristic acceptance by default
    _, strict = curate_trajectories(path, CurationConfig(require_outcome_success=True))
    assert strict.kept == 0
    assert strict.dropped["outcome-not-stamped"] == 1


def test_contamination_guard_blocks_bench_and_teleqna_text(tmp_path):
    bench_ask = builtin_scenarios()[0].ask
    records = [
        _traj(user=f"a colleague asked: {bench_ask}"),   # bench dev-set ask → contaminated
        _traj(user="a perfectly novel operator question about slice latency"),
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    guard = ContaminationGuard.default(teleqna_path=tmp_path / "absent.txt")
    kept, report = curate_trajectories(path, CurationConfig(guard=guard))
    assert report.kept == 1
    assert report.dropped["contaminated"] == 1
    assert kept[0]["messages"][1]["content"].startswith("a perfectly novel")


def test_split_is_deterministic():
    records = [_traj(user=f"q{i}") for i in range(40)]
    train1, val1 = split_train_val(records, seed=7)
    train2, val2 = split_train_val(records, seed=7)
    assert train1 == train2 and val1 == val2
    assert len(val1) == 2  # 5% of 40
    assert len(train1) + len(val1) == 40


# ---- synth: validity by construction ----------------------------------------------------


def test_synth_intents_all_validate_and_reproduce():
    pairs = synth_intent_pairs(50, seed=9)
    assert len(pairs) == 50
    for pair in pairs:
        args = pair["messages"][2]["tool_calls"][0]["function"]["arguments"]
        intent = NetworkIntent(
            intent_id="t", name=args["name"],
            expectations=[Expectation(
                object_type=args["object_type"], object_instance=args["object_instance"],
                metric=args["metric"], condition=args["condition"], value=args["value"],
            )],
        )
        assert validate_intent(intent, parse_turtle=False).valid  # 100%, not statistically
    assert synth_intent_pairs(50, seed=9) == pairs  # seeded → reproducible
    assert synth_intent_pairs(10, seed=10) != synth_intent_pairs(10, seed=11)


def test_synth_correlation_trajectories_close_the_g0_gap():
    from corelab.train.synth import synth_correlation_trajectories

    trajs = synth_correlation_trajectories(8, seed=1)
    assert len(trajs) == 8
    for t in trajs:
        msgs = t["messages"]
        # the exact tool sequence the bake-off models missed: diagnose -> audit mobility
        tool_calls = [tc["function"]["name"] for m in msgs for tc in (m.get("tool_calls") or [])]
        assert tool_calls == ["diagnose_entity", "audit_ue_mobility"]
        # tool results are REAL (grounded), not fabricated: the audit reports actual distinct cells
        audit = json.loads([m for m in msgs if m.get("name") == "audit_ue_mobility"][0]["content"])
        assert audit["distinct_cells"] >= 4
        # final answer correlates latency with mobility (what the judge wants)
        final = msgs[-1]["content"].lower()
        assert "latency" in final and ("mobility" in final or "cell" in final)
    # reproducible
    assert synth_correlation_trajectories(8, seed=1)[0]["messages"][1] == trajs[0]["messages"][1]


def test_synth_diagnosis_uses_real_playbook_keys():
    pairs = synth_diagnosis_pairs(20, seed=3)
    for pair in pairs:
        answer = json.loads(pair["messages"][2]["content"])
        assert answer["suspected_issue"] in PLAYBOOKS
        assert pair["meta"]["issue"] == answer["suspected_issue"]


# ---- mixture honesty ----------------------------------------------------------------------


def test_mixture_warns_on_shortfall_and_missing_general():
    buckets = {
        "trajectory": [_traj(user=f"q{i}") for i in range(8)],
        "synth-intent": synth_intent_pairs(4),
        "synth-diagnosis": synth_diagnosis_pairs(3),
        "general": [],
    }
    mixed, report = assemble_mixture(buckets, total=40)
    assert any("NO GENERAL-INSTRUCTION DATA" in w for w in report.warnings)
    shortfalls = [w for w in report.warnings if "NOT silently rebalanced" in w]
    assert shortfalls  # requested shares exceed availability → loudly reported
    assert report.per_bucket["trajectory"]["requested"] == 16
    assert report.per_bucket["trajectory"]["used"] == 8
    assert report.total == len(mixed) == 8 + 4 + 3


def test_mixture_default_total_is_feasible_and_seeded():
    buckets = {
        "trajectory": [_traj(user=f"q{i}") for i in range(40)],
        "synth-intent": synth_intent_pairs(20),
        "synth-diagnosis": synth_diagnosis_pairs(15),
        "general": [{"messages": [{"role": "user", "content": f"g{i}"}]} for i in range(25)],
    }
    mixed1, report = assemble_mixture(buckets, seed=5)
    mixed2, _ = assemble_mixture(buckets, seed=5)
    assert mixed1 == mixed2
    assert not report.warnings  # fully feasible mixture: nothing to warn about
    assert report.total == sum(b["used"] for b in report.per_bucket.values())


# ---- gates: enforced order ------------------------------------------------------------------


def test_gates_enforce_order_and_persist(tmp_path):
    path = tmp_path / "gates.json"
    gates = TrainingGates(path)
    with pytest.raises(GateError, match="G0 has not passed"):
        gates.require("G1")

    gates.record("G0", passed=True, evidence={"verdict": "gap"})
    gates.require("G1")  # now fine
    with pytest.raises(GateError, match="G1 has not passed"):
        gates.require("G2")

    reloaded = TrainingGates(path)  # persistence across sessions
    assert reloaded.passed("G0") is True
    assert reloaded.status()["G2"]["passed"] is False


def test_failed_gate_blocks():
    gates = TrainingGates(path="/tmp/nonexistent-dir-corelab/never-written.json")
    gates.state = {"G0": {"passed": False}}
    with pytest.raises(GateError):
        gates.require("G1")


# ---- configs + card --------------------------------------------------------------------------


def test_config_presets_cover_the_hardware_story():
    # 7-8B tier (1×24GB) through 70B (4×24GB), both vendor families represented.
    assert {"qwen3-8b", "qwen2.5-7b", "qwen3-32b", "qwen2.5-32b", "llama-3.1-70b-qlora"}.issubset(PRESETS)
    config = build_config("qwen2.5-32b", train_path="x/train.jsonl")
    assert config["load_in_4bit"] is True
    assert "24 GB" in config["hardware"]
    assert config["train_file"] == "x/train.jsonl"
    assert "G0" in config["note"]  # the base is chosen by the bake-off, not asserted
    with pytest.raises(KeyError):
        build_config("gpt-5-pro-max")


def test_mistral_alternative_is_present_and_apache():
    # The Mistral alternative the framework recommends as the Qwen-32B challenger.
    mistral = build_config("mistral-small-24b")
    assert mistral["license"] == "Apache-2.0"
    assert mistral["vllm_tool_call_parser"] == "mistral"  # parser must match the family
    assert "mistralai/Mistral-Small" in mistral["base_model"]
    # mid-size Mistral option too
    assert build_config("mistral-nemo-12b")["license"] == "Apache-2.0"


def test_g0_shortlist_is_apache_and_spans_tiers():
    # Every bake-off candidate must be Apache-2.0 (clean adapter redistribution).
    for preset in G0_SHORTLIST:
        assert PRESETS[preset]["license"] == "Apache-2.0", preset
    # spans the cheap (7-8B) and quality (24-32B) tiers, and both vendors.
    bases = " ".join(PRESETS[p]["base_model"] for p in G0_SHORTLIST)
    assert "Qwen" in bases and "mistral" in bases.lower()
    # Llama-70B is available but NOT in the shortlist (licence) — opt-in only.
    assert "llama-3.1-70b-qlora" not in G0_SHORTLIST
    assert "NOT Apache-2.0" in PRESETS["llama-3.1-70b-qlora"]["license"]


def test_model_card_is_draft_until_all_gates_pass(tmp_path):
    gates = TrainingGates(tmp_path / "g.json")
    gates.record("G0", passed=True, evidence={"verdict": "gap exists"})
    card = generate_model_card(gates, base_model="Qwen/Qwen2.5-7B-Instruct")
    assert "DRAFT" in card and "Do not publish" in card
    assert "✅" in card and "❌ NOT PASSED" in card
    assert "Licence checklist" in card and "5G3E" in card
    assert "Limitations" in card and "human-approval-gated" in card

    for gate in ("G1", "G2", "G3"):
        gates.record(gate, passed=True)
    final = generate_model_card(gates, curation_stats={"kept": 1234})
    assert "DRAFT" not in final
    assert "`1234`" in final
