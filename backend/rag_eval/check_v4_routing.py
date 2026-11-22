"""Development regression of French question -> catalog plan (not a production accuracy claim)."""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rag.planner import maybe_plan


def run() -> tuple[int, int]:
    path=Path(__file__).with_name('v4_regression_questions.jsonl')
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    passed=0
    for item in rows:
        plan=maybe_plan(item['question'],item['role'])
        got=(plan.dataset,plan.metric,plan.group_by) if plan else (None,None,None)
        expected=(item['dataset'],item['metric'],item['group_by'])
        if got==expected:
            passed+=1
        else:
            print('MISMATCH',item['question'], '\n expected',expected,'\n actual  ',got)
    print(f'French question routing regression: {passed}/{len(rows)}')
    return passed,len(rows)


if __name__=='__main__':
    ok,total=run()
    raise SystemExit(0 if ok==total else 1)
