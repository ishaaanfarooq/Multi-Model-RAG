#!/usr/bin/env sh
# One command reproduces every number in eval/BASELINE.md.
#
#   cd backend && sh eval/run_all.sh                 # local model from LLM_MODEL (default in .env / compose)
#   cd backend && LLM_MODEL=llama3.2 sh eval/run_all.sh llama32   # same suites, another model, labelled
#   Inside Docker: docker exec -w /app multimodelrag-backend-1 sh eval/run_all.sh
#
# Takes ~50 minutes on a 4 GB GPU with a 3B model (the answers suite and the ablation
# dominate). Results land in eval/results/ and one line per run in results/history.md.
set -e
LABEL="${1:-repro}"
# Greedy decoding for evaluation. With the model's default sampling, 12-16% of answers change verdict
# between two runs of the IDENTICAL system; at temperature 0 it is 1-2% (eval/SIGNIFICANCE.md, section 3),
# so a difference between two runs means a difference between two systems. BASELINE.md's original figures
# were sampled and will differ from a greedy re-run by a few questions. Production is unaffected: this
# variable is unset there. To sample here too: OLLAMA_TEMPERATURE=0.8 sh eval/run_all.sh
export OLLAMA_TEMPERATURE="${OLLAMA_TEMPERATURE:-0}"
echo "== decoding temperature for this run: $OLLAMA_TEMPERATURE =="
cd "$(dirname "$0")/.."
echo "== index ==";        python -B -W ignore -m eval.build_index
echo "== routing ==";      python -B -W ignore -m eval.run_eval --suite routing --runs 3 --label "routing_$LABEL" | grep -E '^\|'
echo "== retrieval ==";    for m in dense hybrid; do python -B -W ignore -m eval.run_eval --suite retrieval --retrieval $m --label "ret_${m}_$LABEL" | grep -E '^\|'; done
                           python -B -W ignore -m eval.run_eval --suite retrieval --retrieval bm25 --no-rerank --label "ret_bm25_$LABEL" | grep -E '^\|'
echo "== answers ==";      python -B -W ignore -m eval.run_eval --suite answers --judge --retrieval hybrid --label "answers_$LABEL" | grep -E '^\|'
echo "== ablation ==";     python -B -W ignore -m eval.ablation --label "$LABEL" | grep -E '^\|'
echo "== abstention ==";   python -B -W ignore -m eval.abstention --label "$LABEL" | grep -E '^\|'
echo "== verifier ==";     python -B -W ignore -m eval.verifier_eval --label "$LABEL" | grep -E '^\|'
echo "== significance ==";  python -B -W ignore -m eval.significance
echo "== appendix ==";     python -B -W ignore -m eval.failure_analysis
echo "== latency ==";      python -B -W ignore -m eval.latency_report
echo "done: see eval/results/history.md and eval/FAILURE_ANALYSIS.md"
