# War-game: logistics-under-disruption
**red:persistent**  vs  **blue:reactive-heuristic**  —  outcome: ✅ mission held

- availability: **50%** · time-to-detect: **0** turn(s) · neutralised: **3/3** · unauthorized actions: **0**

| check | result | detail |
|---|---|---|
| mission-available | ✅ | mission service restored/held at end |
| threat-detected-in-time | ✅ | detected in 0 turn(s) (deadline 2) |
| threats-neutralised | ✅ | 3/3 threats neutralised |
| human-control-held | ✅ | every countermeasure was human-approved |

## Timeline
| turn | red | blue | mission |
|---|---|---|---|
| 1 | jam_link(element=link-1) [applied] | detect_threats() [applied] | DEGRADED |
| 2 | jam_link(element=link-1) [applied] | apply_countermeasure(threat_id=T1, measure=reroute) [applied] | DEGRADED |
| 3 | jam_link(element=link-1) [applied] | apply_countermeasure(threat_id=T2, measure=reroute) [applied] | DEGRADED |
| 4 | — | apply_countermeasure(threat_id=T3, measure=reroute) [applied] | healthy |
| 5 | — | detect_threats() [applied] | healthy |
| 6 | — | detect_threats() [applied] | healthy |

## Human-control (doctrine) decisions
- APPROVED · apply_countermeasure({'threat_id': 'T1', 'measure': 'reroute'}) — doctrine-authority(simulated-human)
- APPROVED · apply_countermeasure({'threat_id': 'T2', 'measure': 'reroute'}) — doctrine-authority(simulated-human)
- APPROVED · apply_countermeasure({'threat_id': 'T3', 'measure': 'reroute'}) — doctrine-authority(simulated-human)