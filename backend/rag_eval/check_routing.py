"""Standalone regression check. Run: python rag_eval/check_routing.py"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.planner import maybe_plan

DATA = Path(__file__).with_name('routing_questions.jsonl')
rows = [json.loads(s) for s in DATA.read_text(encoding='utf-8').splitlines() if s.strip()]
passed = 0
for row in rows:
    plan = maybe_plan(row['question'], row['role'])
    result = (plan.dataset if plan else None, plan.metric if plan else None,
              plan.group_by if plan else None)
    expected = (row['dataset'], row['metric'], row['group_by'])
    match = (result == expected)
    passed += match
    if not match:
        print('MISMATCH', row['question'])
        print(' Expected:', expected)
        print(' Observed:', result)
print(f'Routing agreement: {passed}/{len(rows)} = {100*passed/len(rows):.1f}%')
if passed != len(rows):
    raise SystemExit(1)
