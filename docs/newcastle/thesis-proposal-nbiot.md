# Integrating NB-IoT with Intermittent Computing for Battery-Free IoT

**MSc Individual Research Project — Thesis Proposal**
*Newcastle University, MSc Embedded Systems and IoT, 2025–2026 (60 credits)*
*Author: Ruoqi Wang · Student ID 250256068*

> The full proposal PDF lives at
> [`Thesis_Proposal_NB-IoT_Intermittent_Computing.pdf`](Thesis_Proposal_NB-IoT_Intermittent_Computing.pdf).
> This README is the engineering-friendly summary.
>
> **Disclaimer:** Submitted as part of EEE8161 / Individual Research Project at
> Newcastle University. Published here as a portfolio piece only — see
> [DISCLAIMER.md](DISCLAIMER.md).

## TL;DR

NB-IoT was designed for low-power, battery-backed devices. Battery-free
energy-harvesting IoT devices have ~400,000× less stored energy than a CR2032
coin cell. **Can NB-IoT actually run on a microcapacitor?** This proposal
maps out the energy mismatch, pinpoints where existing checkpointing schemes
(Chinchilla, OSDI '18) break under the NB-IoT protocol stack, and proposes a
co-design path through cellular-scale communication on intermittently powered
devices — an enabler for 6G Ambient IoT (A-IoT).

## The core energy mismatch

| Metric                                | Battery-backed NB-IoT  | Battery-free harvester |
|---------------------------------------|------------------------|------------------------|
| Energy buffer                         | CR2032: **2,000 J**    | 1 mF cap: **0.005 J**  |
| Peak uplink current (NB-IoT, 20 dB CE)| **250 mA** × up to 128 retransmissions | Cannot sustain |
| Continuous-energy assumption          | Yes (battery)          | No (intermittent)      |

**400,000× gap.** A single NB-IoT uplink burst — required for 20 dB coverage
enhancement — exceeds the entire energy budget of a microcapacitor by orders
of magnitude. Existing 3GPP Rel-13 power optimisations (PSM, eDRX) target
multi-year battery life, *not* sub-second power outages.

## Research questions

1. **Forward progress under power loss.** When a battery-free device loses
   power mid-execution, how do existing checkpointing mechanisms — e.g.
   Chinchilla's adaptive dynamic checkpointing [4] — interact with the NB-IoT
   protocol stack's stateful procedures (cell search, RACH, RLC retransmissions)?
2. **Energy-bounded task decomposition.** Given that a single uplink burst
   exceeds the entire microcapacitor budget, how should the NB-IoT connection
   process be **decomposed into energy-feasible sub-tasks** that can resume
   across power outages?
3. **Energy allocation policy.** Limited harvested energy must be split among
   sensing, computing, and NB-IoT communication. What scheduling policy
   maximises end-to-end system utility under stochastic energy availability?
4. **HW/SW co-design.** How do we co-optimise the energy harvester, capacitor
   sizing, RF front end, and software (intermittent runtime, task scheduler,
   checkpoint frequency) to close the energy gap?

## Expected contributions

- An **energy-feasibility analysis model** mapping NB-IoT communication phases
  (cell search → RACH → uplink data → ACK) onto intermittent power constraints
- A **task decomposition and scheduling strategy** that splits NB-IoT
  transactions into sub-tasks aligned with capacitor energy windows, with
  checkpoint placement chosen to minimise lost work on power failure
- A **theoretical foundation** for cellular-scale battery-free devices in
  future 6G A-IoT systems, where 3GPP is actively standardising backscatter
  and ambient-powered communication [2]

## Why this matters (industrial relevance)

- **3GPP A-IoT for 6G** is on the standards roadmap [2] — sub-microwatt
  backscatter devices that need cellular-grade reachability
- **Deployment scenarios** where battery replacement is impractical or
  impossible: structural health monitoring, environmental sensing, smart
  agriculture, implantable / wearable medical devices
- **Existing intermittent-computing research** (Chinchilla [4], Mayfly,
  InK) targets microcontroller-local execution; **none** address the
  multi-second, high-peak-current demands of NB-IoT uplink

## Key references

| # | Citation | Why it matters |
|---|----------|----------------|
| [1] | Popli, Jha, Jain. *A Survey on Energy Efficient NB-IoT*. IEEE Access 7, 2019, pp. 16739–16776 | NB-IoT energy profile, 128-repetition uplink, PSM/eDRX |
| [2] | Zheng et al. *Ambient IoT Toward 6G*. IEEE Access 12, 2024, pp. 146668–146677 | 3GPP A-IoT standardisation, backscatter, sub-μW devices |
| [3] | Sijapati & Amsaad. *Batteryless Systems for IoT*. IEEE MWSCAS 68, 2025, pp. 1090–1094 | Survey of microcapacitor-based intermittent systems |
| [4] | Maeng & Lucia. *Adaptive Dynamic Checkpointing for Safe Efficient Intermittent Computing*. USENIX OSDI 13, 2018, pp. 129–144 | Chinchilla — the closest checkpointing baseline |

## Skills demonstrated

- **Literature review** across four research communities: cellular networking
  (NB-IoT / 3GPP), intermittent computing (OSDI), embedded systems (MWSCAS),
  and 6G standardisation
- **Quantitative energy reasoning** — peak-current vs. capacitor-energy
  feasibility, retransmission cost, dB-to-energy mapping
- **Cross-layer system thinking** — RF front end ↔ protocol stack ↔
  intermittent runtime ↔ application
- **Identifying a real research gap** — existing intermittent-computing
  literature stops at MCU-local execution; cellular-scale battery-free
  communication is unaddressed

## Status

- ✅ Proposal submitted (March 2026)
- ⏳ Full 60-credit dissertation in progress, due summer 2026
- 📓 Implementation track (MSP430-FR / NB-IoT modem testbench) being scoped

## Contact

Ruoqi Wang · MSc Embedded Systems and IoT, Newcastle University
· wangrq021212@outlook.com

## License

Documentation under [MIT](LICENSE). The included thesis-proposal PDF is the
author's own coursework submission and is reproduced with the same license.
