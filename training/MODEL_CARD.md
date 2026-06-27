# zortenet-netops-qwen3-8b-lora

LoRA adapter for **Qwen/Qwen3-8B**, tuned for agentic 5G/6G network operations (tool calling, intent drafting, evidence-grounded diagnosis) with the [ZorteNet toolkit](https://github.com/akiskourtis/Agentic-5G-Monitoring-Skill).

## Gate evidence (the pipeline's audit trail)

- **G0** ✅ — baseline measured; a gap exists that RAG alone doesn't close
    - benchmark: `TeleAgentBench v0 (5 state-based scenarios), live Ollama, TWO runs`
    - run1: `{'qwen3:8b': '80%', 'qwen2.5:14b': '60%', 'mistral-small-2409': '20% (broken tool-calling)'}`
    - run2_fair: `{'qwen3:8b': '80%', 'qwen2.5:14b': '60%', 'mistral-small3.2': '40%'}`
    - BASE_LOCKED: `qwen3:8b — 80% both runs; beats qwen2.5:14b and a fairly-tested mistral-small3.2; and the only tier trainable on a single 24GB L4.`
    - mistral_note: `3.2 (40%) >> 2409 (20%): fairness caveat confirmed, still not the pick.`
    - gap: `qos-mobility-correlation failed by ALL models in BOTH runs -> robust, RAG-irrelevant behavioural gap; targeted by the G1 synth-correlation demonstrations.`
- **G1** ✅ — outcome-validated dataset assembled; contamination rules enforced
    - buckets: `{'trajectory': 300, 'synth-intent': 150, 'synth-diagnosis': 112, 'general': 188}`
    - total: `750`
    - train: `713`
    - val: `37`
    - general_source: `databricks-dolly-15k (CC BY-SA 3.0)`
    - gap_targeted: `cross-domain correlation (diagnose->audit_mobility->conclude)`
- **G2** ❌ NOT PASSED — tuned model beats base+RAG on held-out scenarios without general regression
    - eval: `TeleAgentBench (5 scenarios), transformers 4-bit, base vs base+LoRA on the L4`
    - base_success: `60%`
    - ft_success: `80%`
    - improved: `intent-draft-submit (base fail -> ft PASS); 0 regressions; safety-gate held for both`
    - TARGET_gap_qos_mobility: `STILL FAILS for the fine-tuned model (despite 300 correlation demos)`
    - verdict: `Tuned model beats base overall (60->80) and fixed intent-drafting, BUT the specifically-targeted correlation gap did NOT close, and these dev scenarios overlap the training distribution (not a clean held-out test). G2 NOT cleanly passed.`
- **G3** ❌ NOT PASSED — licences cleared; hedged model card written; artifacts published

> ⚠️ **This card is a DRAFT**: not all gates have passed. Do not publish until every gate above is ✅ (G3 includes the licence checklist below).

## Training data (curated)

- train: `713`
- val: `37`
- base_success: `60%`
- ft_success: `80%`
- targeted_gap_closed: `NO (qos-mobility-correlation still fails)`

## Limitations (mandatory honesty)

- Evaluated on **TeleAgentBench v0** (5 public dev scenarios + held-out set where stated) and
  TeleQnA — narrow proxies for real network operations.
- Judges are programmatic/state-based but scenarios are **simulated**; real-RF behavior is not
  covered unless explicitly stated.
- Control actions in deployment remain **human-approval-gated** (the toolkit enforces this);
  this model does not change that and must not be deployed without the gate.

## Licence checklist (complete before publishing — G3 requirement)

- [ ] **Base model licence** permits adapter redistribution (prefer Apache-2.0 bases).
- [ ] **Self-generated trajectories**: publishable (ours), but confirm no proprietary API
      responses are embedded verbatim (Amarisoft remote-API caveat).
- [ ] **TeleQnA**: eval-only — confirm it never entered training data (contamination report).
- [ ] **Tele-Data / TSpec-LLM**: 3GPP/ETSI-derived — check redistribution terms if any extract
      was used for RAG-augmented data generation.
- [ ] **5G3E**: no explicit LICENSE file upstream — contact authors before publishing anything
      derived from it.
