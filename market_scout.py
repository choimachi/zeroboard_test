"""ZEROBOARD Ver.36: cost-free shortlist and alternative discovery from saved reports.

Scores are *editorial triage*, not demand, sales, or profit predictions.
Never invokes APIs or writes to the database.
"""
import re


def normalize(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def signature(title):
    """Conservative fuzzy-match key for near-duplicate titles."""
    return re.sub(r'[^\w一-龯ぁ-んァ-ン]+', '', normalize(title).lower())


def evaluate_idea(idea, sources, rejected_titles=()):
    title = normalize(idea.get('title'))
    reader = normalize(idea.get('reader'))
    paid = normalize(idea.get('paid_value'))
    validation = normalize(idea.get('validation'))
    ids = [str(x) for x in (idea.get('source_ids') or [])]
    linked = [sources[sid] for sid in ids if sid in sources]
    issues = []
    signals = []
    # Score is a bounded editorial checklist, never a purchase-probability estimate.
    score = 0
    if reader and len(reader) >= 6:
        score += 2; signals.append('想定読者が記載されている（仮説）')
    else: issues.append('購入者像を具体化する')
    if paid and len(paid) >= 18:
        score += 2; signals.append('有料部分の具体案がある（品質未検証）')
    else: issues.append('読者が購入後に得られる具体的価値を明記する')
    if validation and len(validation) >= 10:
        score += 1
    else: issues.append('費用をかけない購入意思テストが必要')
    if linked:
        score += 1; signals.append('根拠付きの話題を確認（購買根拠ではない）')
    else: issues.append('出典を確認できない')
    if any(x in title for x in ('速報','ニュースまとめ','最新ニュース')):
        score -= 2; issues.append('ニュースの要約だけでは有料価値が弱い')
    if any(x in title+paid for x in ('簡易レポート','投資判断','VC向け')):
        score -= 1; issues.append('専門性・権利・実務検証に必要な制作コストを再確認')
    if signature(title) in {signature(t) for t in rejected_titles}:
        score -= 4; issues.append('過去の制作保留テーマと同一：別ジャンルの候補を優先')
    if not any(word in (title+paid) for word in ('比較','分析','なぜ','背景','視点','考察','手順','チェック','具体例','検証')):
        issues.append('考察・分析または実用的な差別化を検討')
    score = max(0, min(6, score))
    return {'score':score, 'title':title, 'reader':reader, 'paid_value':paid,
            'validation':validation, 'linked_sources':linked, 'signals':signals,
            'issues':issues, 'decision':'追加調査候補' if score >= 4 and linked else '企画を再検討',
            'caveat':'スコアは企画情報の充実度。売上・購入需要の推定ではありません。'}


def shortlist(reports, validations, max_results=6):
    """Recent unique ideas from stored daily reports; rejected theme is de-prioritized."""
    dismissed = [v.get('candidate_title') for v in validations if v.get('candidate_title')]
    entries = []
    seen = set()
    for report in reports:
        sources = {str(s.get('id')):s for s in (report.get('source_items') or [])}
        for idea in (report.get('report') or {}).get('product_ideas') or []:
            if not isinstance(idea,dict): continue
            sig = signature(idea.get('title'))
            if not sig or sig in seen: continue
            seen.add(sig)
            item = evaluate_idea(idea,sources,dismissed)
            item['report_date'] = str(report.get('report_date') or '')
            item['report_id'] = report.get('id')
            item['already_researched'] = sig in {signature(t) for t in dismissed}
            entries.append(item)
    entries.sort(key=lambda x:(x['already_researched'], -x['score'], -len(x['linked_sources']), x['title']))
    return entries[:max_results]


def brief(item):
    source_lines = [f"- {s.get('title','見出し')}｜公開日 {s.get('published_date') or '不明'}｜取得日 {s.get('retrieved_at') or '不明'}｜{s.get('url') or ''}"
                    for s in item['linked_sources'][:4]]
    return '\n'.join([
        '【Ver.36／市場候補の調査依頼：購入需要未検証】',
        'テーマ：'+item['title'], '想定読者（仮説）：'+(item['reader'] or '未確認'),
        '購入者に届ける価値（仮説）：'+(item['paid_value'] or '未確認'),
        '低コスト検証案：'+(item['validation'] or '未確認'),
        '企画審査：'+item['decision']+'（企画の記述充実度であり売上予測ではない）',
        '未確認事項：'+'／'.join(item['issues']),
        'RSSで把握した話題の出典（記事本文・販売数・購入意思は未検証）：', *source_lines,
        'AI経営会議では制作承認でなく、追加調査と代替候補を議論すること。',
        'CEOの承認前に有料記事生成、公開、支出をしない。'
    ])[:7000]
