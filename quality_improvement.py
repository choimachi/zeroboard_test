"""Ver.55: CEO-authorized, one-request quality improvement, never auto-publish."""
from __future__ import annotations
import copy
import ceo_approval
import quality_control
import ai_revision_agent

# These findings require externally checked facts, rights or real user validation.
HUMAN_REVIEW_CATEGORIES = {'differentiation'}

def triage(draft: dict) -> dict:
    review = quality_control.review(draft['assets'], **draft['final_text'])
    fixable, human = [], []
    for finding in review['findings']:
        category = finding['category']
        issue = finding['issue']
        if (category in HUMAN_REVIEW_CATEGORIES
                or '著作権' in issue or '数値の出典' in issue
                or '外部' in finding.get('action', '')
                or '販売実績' in issue):
            human.append(finding)
        else:
            fixable.append(finding)
    return {'review': review, 'fixable': fixable, 'human': human,
            'source_id': ceo_approval.fingerprint(draft)}


def improve(client, draft: dict, selected_issues: list[str]) -> dict:
    """Exactly one API call through Ver.54 agent; caller gates behind CEO authentication/consent."""
    plan = triage(draft)
    choices = {f['issue']: f for f in plan['fixable']}
    if not selected_issues or len(selected_issues) > 8 or len(set(selected_issues)) != len(selected_issues):
        raise ValueError('文章で改善できる指摘を1〜8件選択してください。')
    if any(issue not in choices for issue in selected_issues):
        raise ValueError('対象外の指摘が含まれています。人による検証が必要な項目はAIに解消扱いさせません。')
    lines = ['品質検査に基づく教材の改善指示。以下の項目を優先し、既存の重要事項・Day 1〜7の構成を保持してください。',
             '修正できない内容を根拠なく補わず、未確認の事実・実績・許諾を創作しないでください。',
             '変更内容が実際に教材・プロンプト・作例に反映されるよう編集してください。']
    for issue in selected_issues:
        f = choices[issue]
        lines.append('指摘：' + issue + ' ／ 推奨対応：' + str(f['action']))
    instruction = '\n'.join(lines)
    result = ai_revision_agent.revise(client, draft, instruction)
    proposal = result['proposed_draft']
    proposal['quality_improvement'] = {'parent_draft_id_sha256': plan['source_id'],
                                      'target_issues': list(selected_issues),
                                      'method': 'one_ceo_authorized_openai_request',
                                      'requires_human_review': [f['issue'] for f in plan['human']]}
    proposal['approval'] = {'content': False, 'publication': False, 'sale': False, 'spending': False}
    result['proposed_draft'] = proposal
    result['selected_issues'] = list(selected_issues)
    result['remaining_findings'] = proposal['second_review']['findings']
    result['human_findings'] = plan['human']
    return result
