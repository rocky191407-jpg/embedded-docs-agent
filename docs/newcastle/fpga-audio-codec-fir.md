# Real-Time Audio FIR Filter on FPGA (WM8731 codec)

A complete FPGA audio processing pipeline running on real hardware: I2C-based
initialisation of a Wolfson WM8731 audio codec, I2S serial-to-parallel input
adaptor, an 8-tap symmetric FIR low-pass filter, and PLL-derived clocking.
Built for Newcastle University EEE8088 (Computer Architecture) coursework.

> **Disclaimer:** This is my own coursework, originally submitted for
> assessment at Newcastle University. Published as a portfolio piece only.
> See [DISCLAIMER.md](DISCLAIMER.md).

## System overview

```
                    50 MHz                           Audio out
                      │                                 ▲
                      ▼                                 │
   ┌──────────────────────────────────────────────────────────────────┐
   │                       FPGA (Cyclone-class)                       │
   │                                                                  │
   │  ┌────────┐    ┌──────────────┐    ┌────────┐    ┌──────────────┐│
   │  │  PLL   │ ─> │  codec_init  │──> │  sync  │──> │ s2p_adaptor ││
   │  │        │    │ (I2C @ 100k) │    │        │    │  (I2S→16-bit)│
   │  └────────┘    └──────────────┘    └────────┘    └──────┬───────┘│
   │                                                         │        │
   │                                                         ▼        │
   │                                                  ┌─────────────┐ │
   │                                                  │  FIR (8-tap │ │
   │                                                  │   low-pass) │ │
   │                                                  └──────┬──────┘ │
   │                                                         │        │
   │                                  ┌──────────────────────▼──────┐ │
   │                                  │   s2p_adaptor (16-bit→I2S) │ │
   │                                  └─────────────────────────────┘ │
   └──────────────────────────────────────────────────────────────────┘
                      │                                 │
                      ▼                                 ▼
             SCLK / SDIN to                  I2S BCLK/LRCLK/DAT
            WM8731 control bus            to WM8731 ADC/DAC bus
```

## Modules

| File | Purpose | Lines |
|------|---------|-------|
| [`src/codec_init.vhd`](src/codec_init.vhd) | I2C transmitter — sends 11 register configs to WM8731 (R0–R9 + R15 reset). Initialises Line-In path, ADC/DAC power, master mode, 16-bit left-justified | 97 |
| [`src/s2p_adaptor.vhd`](src/s2p_adaptor.vhd) | I2S serial-to-parallel and parallel-to-serial. Generates BCLK / LRCLK from CLOCK_50, deserialises 16-bit samples, signals `ADCstb`/`ADCrdy` to FIR | 99 |
| [`src/FIR.vhd`](src/FIR.vhd) | 8-tap symmetric low-pass FIR. Handshake protocol with s2p_adaptor on both ADC (input) and DAC (output) sides. Latches input on `ADCstb` rising edge, computes MAC, raises `ADCrdy` | 105 |
| [`src/sync.vhd`](src/sync.vhd) | Reset/clock synchroniser between async and sync domains | — |
| [`src/pll.vhd`](src/pll.vhd) | Quartus-generated PLL — derives the codec's master clock from the FPGA 50 MHz | — |
| [`src/top_level_pt3.vhd`](src/top_level_pt3.vhd) | Top-level integration — wires all modules together for the final 3-part assignment | 208 |

## Testbenches

`testbench/` — full ModelSim verification for every module:

- `codec_init_tb.vhd` — bit-accurate I2C trace, verifies all 11 register writes
- `s2p_adaptor_tb.vhd` — drives synthetic I2S streams, checks parallel output
- `FIR_tb.vhd` — feeds known impulses, verifies 8-tap symmetric response
- `top_level_pt3_tb.vhd` — system-level integration test

## Simulation scripts

`simulation/*.do` — ModelSim TCL scripts to run each test, set up waveform views,
and generate the wave files used for the report.

## What this demonstrates

- **VHDL design** at module + system level (entity/architecture/process patterns,
  std_logic_vector, numeric_std)
- **I2C / I2S hardware protocols** implemented from scratch (no IP cores)
- **Multi-clock-domain design** (50 MHz main, codec MCLK, I2C SCLK)
- **Handshake protocols** between async modules (`stb`/`rdy` patterns)
- **DSP implementation** — symmetric FIR with multiplier-accumulator, fixed-point
  16-bit samples
- **End-to-end verification** — testbenches for every module + system testbench
- **Real hardware bring-up** — code targets actual WM8731 codec on the
  development board, not a simulation-only model
- **Quartus / ModelSim toolchain** — synthesis, place-and-route, timing closure

## Limitations / honest scope

- The FIR is fixed at 8 taps; a parameterised tap count would be a
  straightforward extension.
- No dynamic coefficient loading — taps are hard-coded after design freeze.
- I2C only writes; no readback of WM8731 status registers (write-only init was
  sufficient for the assignment).
- Full system tested in simulation; on-board verification was conducted in
  the lab and documented in the report.

## Build & simulate

```bash
# ModelSim (pre-installed on lab machines)
vsim -do simulation/run_codec_init.do      # I2C init
vsim -do simulation/run_s2p.do             # serial-parallel adaptor
vsim -do simulation/run_s2p_check.do       # adaptor with checker
# Top-level — open Quartus project final.qpf, then RTL Sim with pt3wave.do
```

## License

[MIT](LICENSE) — see file.

## Contact

Ruoqi Wang · MSc Embedded Systems and IoT, Newcastle University · wangrq021212@outlook.com
