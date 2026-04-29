# M2M PID Motor Control over TCP (Raspberry Pi)

A two-Pi machine-to-machine system where one Raspberry Pi reads motor speed
from an incremental encoder and another runs a PID closed-loop speed
controller over TCP. Written for Newcastle University EEE8089 (M2M Technology
and Internet of Things) coursework, **Group 10**.

> **Disclaimer:** This is a coursework project I contributed to as part of
> Group 10 at Newcastle University. Published as a portfolio piece only.
> Group attribution and contribution scope is described below. The assignment
> brief, lecture materials, and any teaching content are NOT included.
> See [DISCLAIMER.md](DISCLAIMER.md).

## Architecture

```
   ┌─────────────┐                       ┌─────────────────┐
   │ Raspberry   │                       │ Raspberry Pi    │
   │ Pi 1        │      Ethernet         │ 2               │
   │             │  ─── TCP/SSH ──>      │                 │
   │ encoder.c   │   freq samples        │ controller.c    │
   │ (sensor)    │                       │ (PID + driver)  │
   └─────────────┘                       └─────────────────┘
        │                                        │
        ▼                                        ▼
  Incremental                              DC motor driver
  encoder pulses                           (analogue out)
```

The system maps onto the OSI 7-layer model: physical Ethernet, MAC framing,
IP, **TCP** for reliable transport, **SSH** for an authenticated session, and
the encoder/controller user programs at the application layer exchanging
data via stdin/stdout pipes.

## Components

### `src/encoder.c` — multithreaded encoder reader

| Feature | Detail |
|---------|--------|
| Threading | `pthread_create` reader thread |
| Synchronisation | `pthread_mutex_t` protects shared `freq_counter` |
| Sample period | 20 ms (50 Hz) |
| Reader loop | `fgets` from stdin (encoder pulse stream), increment counter |
| Main loop | `usleep` 20 ms, snapshot counter under mutex, reset, emit frequency |

### `src/controller.c` — PID closed-loop controller

| Feature | Detail |
|---------|--------|
| Algorithm | Classical PID: `u = Kp·e + Ki·∫e dt + Kd·de/dt` |
| Sample period | 20 ms (matches encoder) |
| Tunables | `Kp=10.0`, `Ki=50.0`, `Kd=1.0`, gain scaler `Km=100.0` |
| Setpoint | 1.0 Hz (target motor frequency) |
| Output | Scaled and offset (737 + PID·Km) for analogue motor driver board |

### `src/run_local.sh` — local pipe demo

Local single-Pi demo using shell pipes:
`encoder | tee samples.dat | controller | tee controller_output.log > /dev/serial0`.

For the cross-Pi M2M setup the equivalent is `ssh pi2 "./controller" < encoder_output`.

## What this demonstrates

- Multithreaded C with `pthread` and mutex-based synchronisation
- Real-time control loop with bounded sample period
- PID algorithm implementation from scratch
- Network-distributed control (encoder on one machine, controller on another)
- OSI-layer reasoning across a small embedded network
- Linux IPC (pipes, stdio streaming)

## Build & run

```bash
# Compile (on Raspberry Pi or Linux dev machine)
gcc -Wall -O2 encoder.c -o encoder -lpthread
gcc -Wall -O2 controller.c -o controller

# Local demo (needs serial-attached driver board)
./run_local.sh

# Cross-Pi (replace 192.168.x.x with the controller Pi's address)
./encoder | ssh pi@192.168.x.x './controller > /dev/serial0'
```

## Group attribution

This was a Group 10 project for EEE8089. My contribution areas were:

- **TODO — fill in honestly before publishing.** Examples of how to phrase:
  - "PID coefficient tuning and validation against step-response measurements"
  - "Encoder thread synchronisation and sample-period stability"
  - "OSI-layer mapping discussion in the report"
  - "Cross-Pi TCP integration and SSH session setup"

If your contribution was small, say so — recruiters respect honesty.

## Limitations / honest scope

- No formal stability analysis (Bode / root-locus); tuning was empirical.
- No anti-windup on the integral term.
- Sample period is software-timed via `usleep`, not interrupt-driven — jitter under heavy network load.
- Single-loop design; multi-loop / cascade control was out of scope.

## License

[MIT](LICENSE) — see file.

## Contact

Ruoqi Wang · MSc Embedded Systems and IoT, Newcastle University · wangrq021212@outlook.com
