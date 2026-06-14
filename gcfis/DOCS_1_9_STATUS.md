# Attachments 1–9 — honest implementation status (post-s54)

Verdict: docs 1–9 are a *positioning/liquidity/flow-first* re-architecture. The conceptual spine
already exists in GCFIS (change-centric, regime-conditional, product-confluence, gamma-aware entry).
This turn fixed the concrete output bug you flagged and implemented the market-specific spine (doc 5).
The deeper microstructure layers (real absorption/flow-type, decision-stack UI, expectation-gap) are
sequenced below — NOT claimed as done. I will not pretend 9 docs of work shipped in one turn.

## The bug you showed (BREN.JK) — FIXED + verified
- IDX is **buy-only**; the card drew a SHORT (target Rp4,000 BELOW entry Rp4,302, px Rp4,110) — nonsense.
- Root cause: the GEX chart recomputed direction from the bearish phase and ignored the (correct) WAIT
  recommendation. Now: long-only markets never draw a short layout; bearish IDX → range (Entry below px,
  target ABOVE), labelled buy-only; stale-entry ('harga sudah lewat entry') flagged. US/crypto/FX/commodity
  shorts unaffected. Verified: `t_long_only_idx` + card unit checks.

## Doc-by-doc
| Doc | Theme | Status |
|-----|-------|--------|
| 1 | Positioning/liquidity > macro; quad = context not signal; flow-type (accumulation vs distribution vs short-cover) | **Partial.** GCFIS already treats quad as context + product-confluence (not quad→buy); accumulation/distribution split exists (exit_signal, crowded-rolling-over, broker). **Next:** explicit Expectation-Gap engine + 4-way flow-type classifier as first-class scores. |
| 2 | Orderflow/absorption; "big green ≠ smart money" | **Partial.** Absorption proxy (Effort-vs-Result) exists in the BRAIN/broker work. **Next:** fold an Absorption + Flow-Efficiency + Aggression-Persistence score into the per-ticker contract (needs tick/L2 for the real version; proxy from OHLCV+volume now). |
| 3 | Hierarchical filter (eliminate 99%) + entry types + stop=thesis-invalidation + separate categories | **Partial.** GCFIS has the funnel (regime→positioning→flow→entry) + gamma-aware entry types + RR gate. **Next:** hard elimination Stage-1 (liquidity/noise/structure) + per-category buckets (structural / tactical / mean-rev / event). |
| 4 | Alpha Center = outliers/convexity, bottleneck = constraint, Flow-Imbalance/Float | **Partial.** Bottleneck engine + node→ticker + migration + reflexivity (runaway) exist. **Next:** Flow-Imbalance/Float ("holy-grail") metric + the 4 explicit sections (Early Monsters / Squeeze / Rotation / Distribution). |
| 5 | **Market-specific filters (IDX≠US≠crypto≠FX≠commodity)** | **DONE (core).** `markets.py` registry: per-market long_only + dominant drivers + bottleneck priorities; long-only enforced end-to-end (the BREN.JK fix). **Next:** weight each market's confluence by its own drivers (foreign-flow/broker for IDX; dealer/earnings for US; leverage/supply for crypto). |
| 6 | Entry/stop/target + "what do I look at" decision stack | **Partial.** Entry/stop/target/RR + reason exist. **Next:** the explicit decision stack per card — Opportunity-Type / Why-Now / Who's-Trapped / Market-State / Invalidation / Execution. |
| 7 | TRR/LRR + greeks → market MODE (pinning/expansion/squeeze/distribution) → execution | **Partial.** Dealer gamma sign already gates entry (momentum vs mean-revert). **Next:** an explicit 4-mode classifier driving execution style + target map. |
| 8–9 | TRR/LRR = response zones, regime/gamma-conditional, not static S/R | **Acknowledged.** GCFIS entry already conditions on gamma regime; TRR/LRR as response-zone (not S/R) is the next-step for 6/7. |

## Concrete next sequence (highest ROI first)
1. **Decision stack** per ticker (doc 6/7): Type / Why-Now / Who's-Trapped / Market-Mode / Invalidation / Execution — turns every card into a "what do I do now".
2. **4-way flow-type + absorption** scores (doc 1/2) as first-class contract fields.
3. **Market-conditional confluence weights** (doc 5 deepening): each market ranks by its own drivers.
4. **Flow-Imbalance/Float + 4 Alpha-Center sections** (doc 4).
Each shipped one at a time, tested, visible — not a blind rewrite.
