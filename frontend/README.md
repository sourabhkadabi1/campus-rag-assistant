# PESU RAG Assistant — Frontend (Phase 5)

A modern, responsive, dark/light mode Next.js 14 (App Router) web application designed for college students and academic administrators.

## Features

### 1. Student App (`/`)
- **Scoped Student Identity**: Scoped to the authenticated student's semester and department (e.g. Semester 3 CSE).
- **Streaming SSE Chat (`/ask`)**: Token-by-token streaming, markdown rendering, and KaTeX mathematical equation typesetting.
- **Syntax-Highlighted Code**: Code blocks with language badges and one-click copy buttons.
- **Verified Source Cards**: Grounded citations showing document name, chapter, and page range, with an interactive modal to preview the verified PDF page.
- **Detailed Question Detection**: Auto-detects in-depth questions (>40 words or keywords like `step by step`, `derive`, `prove`, `compare`, `with example`, `numerical`) and applies 2-unit quota charging.
- **Thinking Mode (Gemini Flash Thinking)**: Available for Paid tier students for complex derivations and proofs.
- **Live Queue Position Banner**: Displays queue position and estimated wait time during peak campus exam traffic.
- **Live Quota & Thinking Indicators**: Tooltip showing remaining question units, token counts, thinking credits, and midnight UTC reset timer.
- **Upgrade Prompts & Hint Badges**: Contextual upgrade recommendations when detailed questions could benefit from Thinking mode.

### 2. Pricing & Plans (`/pricing`)
- Exact pricing copy matching `PROJECT.md`.
- Free Plan (₹0): 10 question units/day, 40k tokens, semester document access, book & page citations, free summaries.
- Premium Plan (₹99/mo or ₹449/sem): 30 units/day, 100k tokens, 1 thinking credit/day, priority queue, longer answers.
- Seamless Razorpay order creation and webhook verification with mock fallback for testing.

### 3. Admin Control Center (`/admin`)
- **Document Upload & Ingestion**: PDF drag-and-drop, metadata selection (Dept, Sem 1-8, Subject, Academic Year, Doc Type), and live ingestion progress tracker.
- **Model Verification & Status Panel**: Live status for Gemini Flash Lite, Gemma, Groq, Flash Thinking, and Summary models; toggles, cooldown clearing, and API reverification.
- **Margin Dashboard**: Today's and 7-day spend, remaining balance, runway days, cache hit rate, detailed share, and 40% margin alert banner.
- **Balance & Runtime Controls**: Live `PREMIUM_ENABLED` toggle switch, account balance editor, and model token pricing table.
- **Plan Management**: Plan overview and batch manual plan granting.

## Running Locally

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser.

3. Build for production:
   ```bash
   npm run build
   npm run start
   ```
