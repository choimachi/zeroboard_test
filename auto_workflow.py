"""Ver.50 AUTO WORKFLOW: local rule-based orchestration only.
No network, paid API, posting, billing, sales, or autonomous LLM decisions.
"""
from __future__ import annotations
import io
import json
import zipfile
from datetime import datetime, timezone
import value_design
import product_blueprint
import product_builder
import quality_control
import revision_engine


def run(title: str, reader: str, goal: str, fmt: str, project: str,
        daily_minutes: int = 30, notes: str = '', competitor_items=None,
        auto_apply_suggestions: bool = True) -> dict:
    """Produces a non-approved draft and two rule-based reviews, stopping after one revision."""
    plan = value_design.build(title, reader, goal, fmt, competitor_items)
    blueprint = product_blueprint.build(plan, project, daily_minutes, notes)
    assets = product_builder.build(blueprint)
    initial = {
        'guide': assets['guide_markdown'],
        'prompt': assets['copyable_prompt'],
        'example': assets['fictional_example'],
    }
    first = quality_control.review(assets, **initial)
    proposal = revision_engine.propose(assets, initial['guide'], initial['prompt'], initial['example'], first['findings'])
    final = dict(proposal['suggested']) if auto_apply_suggestions else dict(initial)
    second = quality_control.review(assets, **final)
    return {
        'version': '50', 'status': 'DRAFT_CEO_REVIEW_REQUIRED',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'execution_mode': 'local_rule_based_no_ai_no_network_no_spending',
        'title': title, 'reader': reader, 'goal': goal,
        'plan': plan, 'blueprint': blueprint, 'assets': assets,
        'first_review': first, 'proposal': proposal,
        'suggestions_applied_to_export_draft': bool(auto_apply_suggestions),
        'final_text': final, 'second_review': second,
        'summary': {
            'initial_findings': len(first['findings']),
            'revision_suggestions': len(proposal['changes']),
            'final_findings': len(second['findings']),
        },
        'approval': {'content': False, 'publication': False, 'sale': False, 'spending': False},
        'limitations': ('市場調査を新規実行しておらず、競合は提供済みの公開見出しに限ります。'
                        'ルールに基づく草稿・簡易検査で、AI社員の自律思考や実物の再現テストは行っていません。'
                        'CEOによる全文確認・事実／著作権／需要確認が必要です。'),
    }


def package_zip(result: dict) -> bytes:
    if result.get('version') != '50':
        raise ValueError('Ver.50の実行結果が必要です。')
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('01_guide_DRAFT.md', result['final_text']['guide'])
        z.writestr('02_prompt_DRAFT.txt', result['final_text']['prompt'])
        z.writestr('03_example_DRAFT.txt', result['final_text']['example'])
        z.writestr('04_quality_before.md', quality_control.report_markdown(result['first_review']))
        z.writestr('05_quality_after.md', quality_control.report_markdown(result['second_review']))
        z.writestr('06_changes.txt', '\n'.join(result['proposal']['changes']) or '自動修正案なし')
        z.writestr('07_plan.json', json.dumps(result['plan'], ensure_ascii=False, indent=2))
        z.writestr('08_blueprint.json', json.dumps(result['blueprint'], ensure_ascii=False, indent=2))
        z.writestr('09_worksheet.csv', product_builder.csv_text(result['assets']['worksheet_rows']))
        z.writestr('10_full_report.json', json.dumps(result, ensure_ascii=False, indent=2))
        z.writestr('README.txt', '未承認の制作草稿です。AI API・外部通信・公開・販売・決済は実行していません。人間が確認してください。\n')
    return b.getvalue()
