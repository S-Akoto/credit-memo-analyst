# Deterministic Credit Underwriting & Memo Engine

An institutional-grade commercial credit underwriting pipeline that separates **deterministic financial math & stress testing** from **structured Gemini Credit Committee Memo synthesis**.

**Live Underwriting Dossier:** [https://s-akoto.github.io/credit-memo-analyst/](https://s-akoto.github.io/credit-memo-analyst/)

---

## Architecture

```mermaid
flowchart LR
    A[Borrower Packet<br/>JSON or PDF] --> B[src/underwrite.py<br/>Deterministic Ratios & 2D Stress]
    C&[YAML Policy Rules<br/>SME & Agri-Supply Chain] --> B
    B --> D[src/memo.py<br/>Gemini Structured Credit Memo]
    D --> E[output/*_memo.md<br/>Formal Markdown Memo]
    D --> F[docs/index.html<br/>Interactive Plotly Dossier]
```

## Core Capabilities & Design Principles

1. **Strict Separation of Arithmetic & Narrative (`src/underwrite.py`)**
   * Exact Python logic computes multi-year EBITDA, Pro-Forma DSCR, Pro-Forma Debt/EBITDA, Current Ratio, Interest Coverage, and working capital turnover days.
   * Executes a 25-scenario 2D sensitivity matrix (Revenue shocks `[r0, -20%]` x COGS inflation `[0%, +12%]`) plus a `+200/250 bps` interest-rate shock to identify sub-1.00x break-even thresholds before the LLM writes a single word.

2. **Configurable Policy Profiles (`config/`)**
   * `sme_commercial.yaml`: Small-business equipment and working capital term lending (DSOR >= 1.25x, Debt/EBITDA <= 3.50x).
   * `agri_supply_chain.yaml`: Seasonal grain aggregation and supply-chain working capital finance (DSCR >= 1.35x, Current Ratio >= 1.30x, higher commodity cost-spike stress testing).
hÌ¸€¨©A¥¹…¹¥…°A…­•Ğ%¹•ÍÑ¥½¸€¡ÍÉŒ½Á‘™}¥¹•ÍĞ¹Áå€¤¨¨(€€€¨áÑÉ…ÑÌÕ¹ÍÑÉÕÑÕÉ•‰½ÉÉ½İ•ÈÁ…­•ÑÌ¥¹Ñ¼Í¡•µ„µÙ…±¥‘…Ñ•	½ÉÉ½İ•ÉA…­•Ñ€)M=8™¥±•ÌÙ¥„ÁåÁ‘™€…¹•µ¥¹¤ÍÑÉÕÑÕÉ•½ÕÑÁÕÑÌ¸((Ğ¸€¨©ÕÑ½µ…Ñ•É•‘¥Ğ½µµ¥ÑÑ•”5•µ½Ì€˜%¹Ñ•É…Ñ¥Ù”½ÍÍ¥•È€¡ÍÉŒ½Á¥Á•±¥¹”¹Áå€¤¨¨(€€€¨•¹•É…Ñ•Ì™½Éµ…°5…É­‘½İ¸µ•µ½Ì¥¸½ÕÑÁÕĞ½€…¹„µÕ±Ñ¤µ‰½ÉÉ½İ•È¥¹Ñ•É…Ñ¥Ù”!Q50‘…Í¡‰½…É¥¸‘½Ì½¥¹‘•à¹¡Ñµ±€İ¥Ñ A±½Ñ±äMHÍÑÉ•ÍÌ¡•…Ñµ…ÁÌ…¹½Ù•¹…¹ĞÍ½É•…É‘Ì¸((ŒŒ1½…°M•ÑÕÀ()‰…Í )ÁåÑ¡½¸Ì€µ´Ù•¹Ø€¹Ù•¹Ø)Í½ÕÉ”€¹Ù•¹Ø½‰¥¸½…Ñ¥Ù…Ñ”)Á¥À¥¹ÍÑ…±°€µÈÉ•ÅÕ¥É•µ•¹ÑÌ¹ÑáĞ()•áÁ½ÉĞ5%9%}A%}-dô‰å½ÕÈµ…Á¤µ­•äˆ()AeQ!=9AQ ô¸ÁåÑ¡½¸ÍÉŒ½Á¥Á•±¥¹”¹Áä)½Á•¸‘½Ì½¥¹‘•à¹¡Ñµ°)€(