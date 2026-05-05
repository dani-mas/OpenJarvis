# Mining Pearl on Apple Silicon (and other CPU hosts)

OpenJarvis can mine the [Pearl](https://github.com/pearl-research-labs/pearl) chain
on Apple Silicon Macs (M1/M2/M3/M4) using the `cpu-pearl` provider. **This is
v1**: decoupled CPU mining. Your existing local LLM workflow (Ollama, MLX-LM,
llama.cpp, vLLM) is untouched; mining runs in the background as a separate
process.

## Honest expectations

**Hashrate on Apple Silicon CPU is far below what an H100 produces with
Pearl's `vllm-miner`.** A rough rule of thumb (subject to network difficulty):

- M2 Max / M4 Max: ≪ 1 share per second at typical mainnet difficulty
- H100 with `vllm-miner`: meaningfully higher, plus the mining work is
  amortized over real LLM inference

If you want to mine for yield, this isn't the path. If you want to participate
in the network from the hardware you own, with no special hardware purchase,
this is the path.

A future v2 will add Apple-GPU acceleration via PyTorch MPS or a custom MLX
plugin. v3 may add a native Metal kernel. **Neither is shipped today.**

## Prerequisites

- macOS arm64 (M1, M2, M3, M4) — or Linux x86_64 / aarch64
- Python 3.12 (`brew install python@3.12` or use `uv venv --python 3.12`)
- Rust toolchain (`brew install rust` or `curl https://sh.rustup.rs -sSf | sh`)
- Your own running [`pearld`](https://github.com/pearl-research-labs/pearl#node)
  node, RPC reachable on `http://localhost:44107`
- A Pearl Taproot wallet address from `oyster` (Pearl's wallet CLI)
- ~1 GB free disk for the Pearl source clone and build artifacts

## Install

```bash
# from your OpenJarvis repo
uv sync --extra mining-pearl-cpu
```

If Pearl wheels are not yet on PyPI (still true as of 2026-05-05), `uv sync`
succeeds but doesn't install the actual Pearl Python packages. Run:

```bash
jarvis mine init    # OJ detects the missing wheels and offers to build
                    # via the build-from-pin path; ~3-5 minutes on first run.
```

`mine init` will:
1. Clone Pearl at the version OJ has tested against
2. Run `maturin build --release` for `py-pearl-mining`
3. Install the resulting wheel + the `miner-base`, `pearl-gateway` packages
4. Walk you through wallet address / pearld RPC config
5. Run a short calibration to estimate your share-per-hour rate

## Run

```bash
jarvis mine start    # launch gateway + miner-loop subprocesses
jarvis mine status   # check live stats from the metrics endpoint
jarvis mine doctor   # capability matrix (great when something goes wrong)
jarvis mine stop     # stop mining
jarvis mine logs -f  # tail logs from ~/.openjarvis/logs/mining/
```

## Reading `mine doctor`

Each row is one check. `✓` means the check passed; `✗` shows the actionable fix.

```
$ jarvis mine doctor
Hardware
  GPU vendor          apple                            ✓
  Apple chip          M2 Max                           ✓
Pearl install
  py-pearl-mining     0.1.0 (cp312-abi3-macos-arm64)   ✓
  miner-base          0.1.0                            ✓
  pearl-gateway       0.1.0                            ✓
Pearl node
  RPC                 http://localhost:44107           ✓
  Block height        442107 (synced)                  ✓
Wallet
  Address format      prl1q...                         ✓
Provider capability
  cpu-pearl           SUPPORTED  (calibrated 0.X share/h on M2 Max)
Notes
  - This is decoupled mining: your normal LLM inference is unaffected
  - Hashrate is far below H100 mining; see this doc above
  - Metal-accelerated mining: planned for v2; not available yet
Session
  Sidecar             absent (not running)
```

## Limitations

- **Windows is not supported in v1.** Pearl's pure-Rust miner builds on
  Windows in principle but the cross-platform install path is untested. Use
  WSL2 if you must.
- **No coupling to inference yet.** v1 is a separate process; your CPU does
  mining, your GPU does inference. They don't share work. v2 changes this.
- **No PyTorch-MPS yet.** v1 stays on the CPU path. v2 will move the math
  to MPS for Apple-GPU acceleration.
- **No multi-host pool.** Solo mining only. The pool work is a separate spec.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `mine doctor` says `Pearl Python packages not installed` | Wheels not built yet | Run `jarvis mine init` |
| `pearl-gateway` log shows `connection refused` to `http://localhost:44107` | `pearld` not running | Start `pearld` per Pearl's README |
| `mine status` shows `last_error: gateway metrics unreachable` | `pearl-gateway` crashed | Check `~/.openjarvis/logs/mining/pearl-gateway.log` |
| Build fails with `error: linker 'cc' not found` | Xcode CLT not installed | `xcode-select --install` |
| `maturin build` complains about `tikv-jemallocator` | macOS SDK too old | Update macOS / Xcode |

For anything not on this list, capture `~/.openjarvis/logs/mining/` and open
an issue at https://github.com/open-jarvis/OpenJarvis/issues.

## What changes in v2 / v3

- **v2 (months):** PyTorch-MPS acceleration plus optional plugin into MLX-LM
  or `llama-cpp-python`. Same `cpu-pearl` config; users opt in via a new
  `apple-mps-pearl` provider when v2 ships.
- **v3 (only if v2 perf is insufficient):** Native Metal kernel as a Pearl
  upstream contribution. No user-visible change other than higher hashrate.
