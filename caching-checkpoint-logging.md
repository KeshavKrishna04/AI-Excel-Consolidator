# Caching, Checkpointing & Logging – How It Works in This Project

## 🧩 Big Picture

At a high level, the agent is doing something simple:

1. You ask a question
2. It checks if it has already answered something similar
3. If yes → it returns instantly (cache hit)
4. If no → it reads the data, thinks, answers, and saves that result (checkpoint)

What we’ve added on top of this is a **lightweight memory system** (via a log file) and **basic observability** (via logging), without overcomplicating the project.

---

# 🔁 End-to-End Flow (What actually happens)

### When you run FastAPI or `run_benchmark.py`

```id="flow1"
Question → Agent → Answer → (maybe cached) → Logged → Stored
```

Let’s walk through it properly.

---

# 📥 1. Input comes in

### Either:

* From FastAPI (`/ask`)
* Or from `run_benchmark.py` (looping through `question_bank.json`)

At this point, we just have:

```id="flow2"
question = "Was Avogadro a professor at the University of Turin?"
```

---

# 🧠 2. We normalize the question

Before doing anything fancy, we clean it up:

```python id="code1"
normalized_q = question.strip().lower()
```

This is important because:

* "Was Avogadro a professor?"
* "was avogadro a professor?"

→ should be treated as the same thing

---

# ⚡ 3. Cache lookup (first decision point)

We load `agent-checkpoint.log` into memory like a simple dictionary:

```python id="code2"
cache = {
    normalized_question: answer
}
```

Then:

```python id="code3"
if normalized_q in cache:
    → CACHE HIT
    → return answer immediately
else:
    → CACHE MISS
```

### What you’ll see in terminal:

```
CACHE HIT
```

or

```
CACHE MISS
```

---

# 📂 4. If CACHE MISS → Load data

Now the agent actually needs to “think”.

It reads files from the `outputs/` folder:

| File Type         | How it’s handled |
| ----------------- | ---------------- |
| `.xlsx`           | pandas DataFrame |
| `.csv`            | pandas DataFrame |
| `.txt` / `.clean` | plain text       |

This gets stored in the LangGraph state:

```id="flow3"
state["data"]
state["source_type"]
```

---

# 🔗 5. LangGraph pipeline kicks in

This is defined in:

```id="flow4"
graph/qa_graph.py
```

### Flow inside the graph:

```id="flow5"
Question → Reason → Answer → Checkpoint
```

---

## 🧩 Node breakdown (simple terms)

### 1. Reasoning Node

* Understands the question
* Figures out what part of data is relevant

---

### 2. Answer Node

* Uses the data + LLM
* Generates final answer

---

### 3. Checkpoint Node (very important)

This is where memory is written.

---

# 💾 6. Checkpointing (writing memory)

After every answer, we append to:

```id="flow6"
agent-checkpoint.log
```

Example entry:

```json id="code4"
{
  "question": "Was Avogadro a professor at the University of Turin?",
  "normalized_question": "was avogadro a professor at the university of turin?",
  "answer": "Yes",
  "source_type": "clean"
}
```

### Key points:

* Append-only (we never overwrite)
* Acts as:

  * cache
  * history
  * debugging trace

---

# 🔄 7. Next time same question comes in

Flow becomes:

```id="flow7"
Question → Normalize → Cache Lookup → HIT → Return instantly
```

No:

* file reading
* no LangGraph
* no LLM call

---

# 📊 8. Where performance improvement comes from

| Scenario    | What happens   | Latency    |
| ----------- | -------------- | ---------- |
| First time  | Full reasoning | ~3–8 sec   |
| Second time | Cache hit      | ~0.001 sec |

That’s exactly what Vijay wanted to test.

---

# 🧾 9. Logging (what and why)

We added simple logging (nothing fancy):

### Console output:

```
CACHE MISS
CACHE HIT
[checkpoint] written
```

### Why this matters:

* You can **see behavior in real time**
* Helps debug:

  * Is caching working?
  * Is checkpoint writing?
* Makes the system explainable

---

# 🔁 Control Flow (clean view)

```id="flow8"
Incoming Question
     ↓
Normalize
     ↓
Cache Lookup
     ↓
 ┌───────────────┐
 │ CACHE HIT     │ → return answer
 └───────────────┘
     ↓
 ┌───────────────┐
 │ CACHE MISS    │
 └───────────────┘
     ↓
Load Data (outputs/)
     ↓
LangGraph Execution
     ↓
Generate Answer
     ↓
Write Checkpoint
     ↓
Return Answer
```

---

# 🔄 Data Flow (what moves where)

```id="flow9"
question_bank.json / API
        ↓
normalized question
        ↓
agent-checkpoint.log (cache lookup)
        ↓
[if miss]
        ↓
outputs/ files → parsed data
        ↓
LangGraph state
        ↓
LLM answer
        ↓
agent-checkpoint.log (append)
        ↓
performance_report.md
```

---

# ⚙️ Design Choices (why we did it this way)

### ✔ Simple file-based cache

* No DB
* Easy to inspect
* Works immediately

---

### ✔ Append-only checkpointing

* No risk of overwriting data
* Easy to debug history

---

### ✔ Question-based caching (not table-based)

* Works for:

  * Excel
  * CSV
  * Text
  * Any dataset

---

### ✔ No over-engineering

* No embeddings
* No vector DB
* Just straightforward caching (as requested)

---

# 🚀 What this enables

* Faster repeated queries
* Persistent memory across runs
* Works with any dataset format
* Easy to debug and explain

---

# 🧠 Final note (important insight)

Right now, caching works **only for exact (normalized) matches**.

So:

```
"Was Avogadro a professor?"
vs
"Was Avogadro a professor at the University of Turin?"
```

→ treated as different

That’s expected for now (naive caching).

---

# ✅ Summary

We essentially added:

* A **cache layer** before reasoning
* A **checkpoint layer** after answering
* A **logging layer** to observe everything

All of this without breaking the existing pipeline.

---

If you want, I can also convert this into a **diagram you can show Vijay** (very helpful during explanation).
