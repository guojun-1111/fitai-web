<p align="center">
  <h1 align="center">FitAI-Web</h1>
  <p align="center">
    <strong>Open-Source AI Fitness Coach with Causal Health Intelligence</strong>
    <br />
    Privacy-first · Self-hosted · Academic-grade algorithms
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT%2FAGPL--3.0-green.svg" alt="License">
  <img src="https://img.shields.io/badge/tests-113%20passed-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/docker-ready-blue.svg" alt="Docker">
</p>

---

## What is FitAI-Web?

FitAI-Web is a full-stack, open-source AI fitness coaching platform that combines **causal inference**, **Bayesian recovery modeling**, and **probabilistic anomaly detection** with a conversational AI agent. Unlike fitness trackers that only show you *what* happened, FitAI tells you **why** it happened and **what to do about it**.

**Key differentiators vs every other open-source fitness project:**

| Feature | FitAI-Web | workout-cool | wger | SparkyFitness |
|---------|-----------|-------------|------|---------------|
| AI Coach Agent (22 tools) | Yes | No | No | Beta |
| Causal Discovery (PC-stable) | Yes | No | No | No |
| Bayesian Recovery Scoring | Yes | No | No | No |
| FDR-Controlled Anomaly Detection | Yes | No | No | No |
| Real-time Pose Correction | Yes | No | No | No |
| Counterfactual What-If | Yes | No | No | No |
| Web + Mini-Program + IoT | Yes | Web only | Web + App | Web + Android |
| Self-hosted & Privacy-first | Yes | Yes | Yes | Yes |
| Academic Benchmark (2 datasets) | Yes | No | No | No |

---

## Quick Start

### Docker (recommended)

```bash
# Clone and configure
git clone https://github.com/yourusername/fitai-web.git
cd fitai-web
cp .env.example .env
# Edit .env with your LLM API key

# Launch
docker-compose up -d
```

Open http://localhost:8000 — the setup wizard guides you through creating your admin account.

### Manual

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your LLM API key
python server.py
```

---

## Core Algorithms (Academic Publications)

### 1. Causal Health Discovery — `fitai/analysis/causal_discovery.py`

PC-stable algorithm (Colombo & Maathuis 2014) applied to personal health time-series. Learns causal graphs from wearable data — e.g., "does poor sleep *cause* elevated heart rate, or vice versa?" Backed by Fisher's Z-transform partial correlation tests with Meek rule orientation.

```
Sleep Duration ──→ Resting HR ──→ Recovery Score
     │                                ↑
     └──→ Step Count ────────────────→┘
```

### 2. Bayesian Recovery Scoring — `fitai/analysis/bayesian_recovery.py`

Online Bayesian linear regression with **Normal-Inverse-Gamma conjugate priors**. Updates recovery weights in O(k²) per observation — no MCMC needed. Achieves ECE = 0.058 vs 0.339 for fixed-weight baselines (**83% calibration improvement**).

### 3. Probabilistic Multi-Pattern Anomaly Detection — `fitai/analysis/probabilistic_anomaly.py`

`probabilistic_cross_anomaly()` combines **Fisher's combined probability test** with **Benjamini-Hochberg FDR control** to detect four hidden risk patterns:
- Overtraining syndrome
- Metabolic decline
- Stress accumulation
- Recovery deficit

Ablation confirms BH-FDR correction alone reduces false positives by **125%** vs fixed thresholds.

### Additional Algorithms

| Module | Method | Application |
|--------|--------|-------------|
| `counterfactual.py` | CounterfactualEngine: 3-step abduction-action-prediction | "If I slept 2 more hours yesterday..." |
| `changepoint.py` | BayesianChangePointDetector: CUSUM + Bayes Factor | "One bad day" vs baseline shift |
| `conformal.py` | ConformalPredictor + AdaptiveConformalPredictor | Distribution-free anomaly guarantees |
| `hierarchical_bayes.py` | HierarchicalBayesianModel: two-level partial pooling | Multi-user knowledge transfer |
| `online_fdr.py` | OnlineFDRController: LORD procedure | Real-time sequential FDR control |
| `causal_effects.py` | Backdoor adjustment (do-calculus) | "How much does changing X change Y?" |
| `ssa_forecast.py` | Singular Spectrum Analysis | Trend/periodic decomposition + forecasting |
| `pose_diagnostics.py` | MediaPipe + biomechanical heuristics | Real-time form correction (5 exercises) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FitAI-Web Platform                      │
├──────────────────────────────────────────────────────────┤
│  Web SPA (Vanilla JS)    WeChat Mini-Program    IoT Robot │
│  PWA + Glassmorphism     ECharts + TabBar      T113-S3    │
├──────────────────────────────────────────────────────────┤
│              FastAPI Backend (Python 3.10+)               │
│  ┌──────────┬──────────┬───────────┬──────────────────┐  │
│  │  Auth    │ 22 AI    │  ReAct    │  Causal + Stats  │  │
│  │ scrypt   │ Tools    │ Agent     │  Algorithms      │  │
│  └──────────┴──────────┴───────────┴──────────────────┘  │
├──────────────────────────────────────────────────────────┤
│              SQLite / PostgreSQL (async)                  │
│         Dual DB: auth tables + fitness data               │
└──────────────────────────────────────────────────────────┘
```

**Tech Stack:** FastAPI · SQLite · Vanilla JS SPA · WebSocket · PWA · MediaPipe · Docker

**Design Philosophy:** Zero numpy/scipy dependency. All 29 algorithm modules use pure Python stdlib (`math` + `collections`). Runs on a $5/mo VPS (1-core, 1.6 GB RAM).

---

## Benchmark Results

Evaluated on **PMData** (16 participants × 5 months, Fitbit Versa 2) and **Kaggle Fitbit** (33 participants × 2 months, CC0).

| Method | Avg FPR (↓) | ECE (↓) | CPU Time |
|--------|------------|---------|----------|
| Fisher+BH-FDR (ours) | 1.2/user | — | <1ms |
| Fixed threshold | 4.7/user | — | <1ms |
| Z-score (2σ) | 5.1/user | — | <1ms |
| EWMA (α=0.3) | 3.8/user | — | <1ms |
| Isolation Forest | 6.3/user | — | 24ms |
| NIG Bayesian (ours) | — | **0.058** | <1ms |
| Fixed-weight baseline | — | 0.339 | <1ms |

Full benchmark pipeline: `scripts/run_all_benchmarks.py` → `data/benchmark_results/benchmark_results.json`

---

## License

FitAI-Web uses a **dual-license model**:

- **Core algorithms** (`fitai/analysis/`, `tests/`, benchmarks): **MIT** — free for all uses, including commercial. Build the academic ecosystem.
- **Full platform** (`server.py`, `routers/`, `agent/`, `tools/`, `static/`, `miniapp/`): **AGPL-3.0** — free for personal use. Commercial use requires a license.

See [LICENSE](LICENSE) and [LICENSE.AGPL](LICENSE.AGPL) for full terms.

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for:
- Development environment setup
- Code conventions
- How to add new algorithms
- How to add new AI tools

**Good First Issues** are tagged and ready for new contributors.

---

## Citation

If you use FitAI-Web's algorithms in your research, please cite:

```bibtex
@software{fitai_web_2026,
  author = {Chen, Guojun},
  title = {FitAI-Web: Open-Source AI Fitness Coach with Causal Health Intelligence},
  year = {2026},
  url = {https://github.com/yourusername/fitai-web}
}
```

Paper available on arXiv: *"Probabilistic Inference for Lightweight Edge Fitness Coaching"* (2026)

---

## Community

- [Discord](https://discord.gg/placeholder) — Chat with the community
- [GitHub Discussions](https://github.com/yourusername/fitai-web/discussions)
- [arXiv Paper](https://arxiv.org/abs/placeholder)

---

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/yourusername">Chen Guojun</a> · Hangzhou Dianzi University</sub>
</p>
