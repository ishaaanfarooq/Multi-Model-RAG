# Is the verification module right?

*2026-09-21 · `OLLAMA_TEMPERATURE=0 python -m eval.verifier_eval` · qwen2.5:3b · results in `eval/results/verifier_*.json`*

The pipeline's last stage labels each answer verified or flags it, and the interface shows a warning on
flagged answers. Every other suite measures the *answer*. Nothing had measured that *label*: when the
verifier says an answer is supported, is it?

## Method: answers whose groundedness is known by construction

A judge's opinion cannot grade a judge, so the test answers are built, not rated. Starting from real
generated answers that contain the gold fact and whose evidence is in their context:

| class | how it is made | truth |
|---|---|---|
| correct | the real answer, untouched | should **pass** |
| fabricated sentence | one invented sentence inserted after the first sentence; every one uses a term verified absent from the corpus (*"benchmarked on eight A100 GPUs"*, *"a BLEU score of 41.2"*) | should **fail** |
| fabricated, vague | the same, but the invented sentence contains nothing checkable (*"widely regarded as the most popular choice among enterprise developers"*) | should **fail** |
| number swapped | one figure that appears in the context changed to one that does not (1000 → 1350) | should **fail** |
| wrong document | a correct answer to a *different* question from a *different* document | should **fail** |

Tests pin the construction: the fabrications' terms are checked against the corpus, the vague ones are
checked to contain no specifics, and case-building is deterministic.

## Before: what the shipped verifier got right

| class | n | lexical support alone | LLM judge (full context) | **shipped `verify_fast`** |
|---|---|---|---|---|
| correct (should pass) | 42 | 0.67, 13 undecided | 0.93 | **0.93** |
| fabricated sentence | 42 | 0.02 | 0.74 | **0.71** |
| number swapped | 6 | 0.17 | 0.33 | **0.33** |
| wrong document | 42 | 0.98 | 1.00 | **1.00** |

Two findings.

**The fast verifier lost nothing.** The efficiency pass replaced "ask the model every time" with "lexical
support first, the model only when unsure". It is as accurate as the full judge (0.71 vs 0.74 on
fabrications, identical elsewhere) at 0.6 s instead of 1.9 s, consulting the model on 39% of answers.

**One invented sentence got through 29% of the time, a changed number 67%.** Of the 12 fabricated answers
that passed, 6 never reached the model: a long answer keeps its sentence-level support above 0.75 with one
bad sentence in it. The other 6 reached the model and it waved them through. Both number swaps that
auto-passed had support **1.00**: changing `1000` to `1350` leaves every other word supported. Nothing in
the verifier checked whether the *concrete* things an answer states appear in its sources.

## The change: unsupported specifics

`verification/specifics.py` extracts the checkable tokens of an answer and looks for them in the sources:

- numbers with two or more digits, or a decimal (rounding a source figure is accepted: 79.14 supports 79.1);
- identifier-like terms: a digit with a letter (`A100`), all capitals (`BLEU`), an internal capital (`PostgreSQL`);
- capitalised words that are not sentence-initial and not part of a Title Case run (`Kubernetes`).

`verify_fast` runs it **before** the lexical auto-pass, because that is where the misses were, and before
the model, so a hit costs no model call. The reason names the tokens, and the warning shown to the user
now does too: *"Check before relying on this: the answer mentions '41.2', 'A100', which do not appear in
the retrieved sources"* instead of a generic banner. `VERIFY_SPECIFICS=0` restores the old behaviour.

## After (final run, reported as it came out)

| class | n | lexical alone | LLM judge | **shipped `verify_fast`** | before |
|---|---|---|---|---|---|
| correct (should pass) | 43 | 0.65 | 0.93 | **0.91** | 0.93 |
| fabricated sentence | 43 | 0.05 | 0.84 | **1.00** | 0.71 |
| fabricated, vague | 43 | 0.05 | 0.51 | **0.56** | – |
| number swapped | 8 | 0.12 | 0.50 | **1.00** | 0.33 |
| wrong document | 43 | 0.98 | 1.00 | **1.00** | 1.00 |

Model consulted on 26% of answers (was 39%); 0.5 s per verdict. The deterministic check beats the model
judge on exactly the cases where a judge is weakest, and makes verification cheaper, not dearer.

**What it cost.** Four correct answers were flagged in the final run. Three are the older paths (the model
judge once, the lexical floor twice). One is the new check: it flagged `RESTful`, a word the model used to
describe a FastAPI service and the sources never use. That is 1 false alarm in 43 (2%) for closing a 29%
miss rate. On 89 held-out correct answers from earlier runs (47 sampled qwen2.5, 42 llama3.2) it flagged 3:
one was a tokenizer bug (`CNNs/RNNs`, fixed), and two were **real**: llama3.2 had copied the prompt
template's example table header (`Branch/Program | Fee Amount | Duration`) into its answers.

It also found hallucinations inside answers the harness had scored *correct*, because they contain the
gold fact: one expands RAG as "Relevant Aspects Generation"; another cites a "Section 3.1" the sources do
not have. Contains-gold measures whether the right fact is present, not whether everything else is true.

## Limits

- **Vague fabrication is not solved.** An invented sentence with no figure, identifier or name passes 44%
  of the time, and the model judge alone does no better (0.51). Six of those never reach the model, because
  lexical support stays above 0.75. This check cannot help by design. It is the honest open problem, and
  the place a stronger judge model would earn its cost.
- **The rule was tuned on its own evaluation.** Title Case runs, document-structure words ("Section"), a
  short allowlist of generic computing acronyms (`GPU`, `HTTP`, `API`; not `JWT`, `TLS`, `BLEU`) and the
  plural-stemming fix all came from reading its false alarms. The held-out figures above are the fairer
  estimate; the final table was run once after the last change and is reported as it came out.
- **General vocabulary still trips it** (`RESTful`). The cost of a false alarm is one warning banner naming
  the word; retries are disabled (`max_retries = 0`), so there is no latency cost.
- **Derived figures are flagged.** A sum or percentage the model computed is not in the sources. For a 3B
  model, that is arguably a feature; for a stronger model it would need an arithmetic check.
- **The web path is unmeasured.** The evaluation uses the document corpus. Checked live on three web
  answers: "330 metres" and "Linus Torvalds… 1991" passed because their sources contain them; no false warnings.
- **Base answers vary between runs** (42, 44, 48, 43 correct answers across four greedy runs): greedy decoding
  on this GPU is nearly, not perfectly, deterministic (`SIGNIFICANCE.md`, section 3). `number swapped` has
  n = 6–11, so read its rate as direction, not magnitude.
