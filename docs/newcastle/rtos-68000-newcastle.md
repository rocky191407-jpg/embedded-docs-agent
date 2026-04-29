# Mini-RTOS for Motorola 68000

A pre-emptive multitasking real-time operating system implemented in 68000 assembly,
written for Newcastle University EEE8087 (Real-Time Embedded Systems) coursework.

> **Disclaimer:** This is my own coursework, originally submitted for assessment at
> Newcastle University. Published as a portfolio piece only. The assignment brief,
> lecture materials, and any teaching content from the module are NOT included.
> See [DISCLAIMER.md](DISCLAIMER.md).

## What it does

A minimal RTOS that runs on the Easy68K simulator and provides:

| Feature | Where |
|---------|-------|
| **Vector table** (reset, Level-1 timer interrupt, TRAP #0 system calls) | `src/main.x68` (lines 13–22) |
| **Reset routine** — initialises Ready List, mutex, TCB array, sets up T0 | `src/main.x68` (lines 25–46) |
| **First-Level Interrupt Handler (FLIH)** — common context save for D0–D7, A0–A6, USP, SR, PC | `src/main.x68` (lines 50–96) |
| **Round-Robin scheduler + Dispatcher** — restores all registers, pushes SR/PC for RTE | `src/main.x68` (lines 122–149) |
| **Task Control Block (TCB)** — 84-byte struct with all registers, SP, SR, PC, next pointer, used flag | `src/main.x68` (lines 172–198) |
| **System calls** via TRAP #0 (D0=function id, D1/D2=args): | `src/syscalls.x68` |
| &nbsp;&nbsp;• `SC_CREATE` — create new task | |
| &nbsp;&nbsp;• `SC_INITM` — initialise mutex | |
| &nbsp;&nbsp;• `SC_WAITM` / `SC_SIGM` — wait / signal mutex (skeleton) | |
| &nbsp;&nbsp;• `SC_WAITT` — wait N timer ticks | |
| **Timer-driven preemption** — Level-1 autovector interrupt every 100 ms | |
| **Demo task T0** — toggles LED at `$E00010` | `src/main.x68` (lines 202–210) |

## Memory layout

| Range | Purpose |
|-------|---------|
| `$0000`–`$00FF` | Exception vector table (reset SP, reset PC, timer ISR, trap ISR) |
| `$0600`–`$0FFF` | Kernel data (system time, mutex, ready/wait list pointers, TCB array) |
| `$1000`–`$1FFF` | Kernel code (reset, FLIH, scheduler, dispatcher, syscalls) |
| `$2000`–`$7FFF` | User task code (T0, T1, …) |
| `$8000`         | Initial supervisor stack pointer (grows down) |

## Design notes

- **Pre-emptive multitasking**: timer interrupt forces the running task into the kernel; dispatcher picks the next task from a circular Ready List.
- **Context switching**: full register set (D0–D7, A0–A6, USP, SR, PC) saved into the running task's TCB.
- **User Mode for tasks**: `SR` is initialised to `$0000` so tasks run with the User Stack Pointer.
- **Interrupt safety**: TRAP handler raises interrupt mask to `$0700` to prevent timer interrupts during system calls.

## Reports

The `reports/` directory contains my four assessed documents:

- `1.docx` — Part 1: System Architecture and Initialisation
- `2.docx` — Part 2: System Calls, Mutex, and Task Lifecycle
- `3.docx` — Part 3: Scheduler, Dispatcher, and Performance Analysis
- `User Manual.docx` — End-user guide for running the demo

## Build & run

1. Open `src/main.x68` in [Easy68K](http://www.easy68k.com/).
2. Assemble (F9). Output `.S68` is the Motorola S-record loader file.
3. Run in the Easy68K simulator. Enable Hardware → Auto Interrupt 1 (timer).
4. The LED at `$E00010` will toggle, demonstrating the timer interrupt + dispatcher.

## What this demonstrates

- Bare-metal embedded systems programming
- Real-time operating system design from scratch
- Preemptive scheduling and context switching
- Interrupt handling and synchronisation primitives
- Documentation discipline (formal technical reports)

## Limitations / honest scope

- The Mutex implementation is a skeleton (init + wait/signal logic). Priority inheritance is **not** implemented — a Mutex with priority inheritance would be a sensible next extension.
- Currently demonstrates 2 tasks (T0 + room for T1 via `SC_CREATE`). The TCB array is sized for up to 8 tasks.
- Memory protection / privilege isolation between user tasks is not implemented (out of scope for the module).

## License

[MIT](LICENSE) — see file.

## Contact

Ruoqi Wang · MSc Embedded Systems and IoT, Newcastle University · wangrq021212@outlook.com
