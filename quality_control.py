"""Ver.48 offline, deterministic draft checks. Not a professional or factual verification."""
from __future__ import annotations
import io
import json
import re
import zipfile
from datetime import datetime, timezone


CHECK_LABELS = {
    'consistency': '教材の一貫性',
    'concreteness': '手順の具体性',
    'usability': '購入者の実用性',
    'differentiation': '差別化の根拠',
    'accuracy': '正確性・表示上の注意',
}


def _finding(category: str, level: str, issue: str, evidence: str, action: str) -> dict:
    return {'category': category, 'level': level, 'issue': issue,
            'evidence': evidence[:260], 'action': action}


def review(assets: dict, guide: str, prompt: str, example: str) -> dict:
    """Rule-based findings, never claims to have run an LLM, internet, or full fact-check."""
    if not isinstance(assets, dict) or assets.get('version') != '47':
        raise ValueError('Ver.47の教材ドラフトが必要です。')
    guide, prompt, example = (str(x or '') for x in (guide, prompt, example))
    findings = []
    project = str(assets.get('project', ''))
    title = str(assets.get('product_title', ''))
    reader = str(assets.get('reader', ''))
    combined = '\n'.join((guide, prompt, example))

    # Consistency: title and selected project in guide; token checks are heuristic only.
    if title and title not in guide:
        findings.append(_finding('consistency', '要修正', '教材本文に商品名が見当たらない', title,
                                 '冒頭に商品名を明記し、本文と付録で表記を統一する。'))
    if project and project not in guide:
        findings.append(_finding('consistency', '要修正', '設計図の試作品名が教材本文に見当たらない', project,
                                 '購入者が作る具体的な成果物を冒頭に一文で書く。'))
    if project == 'AIでSNS投稿案を作る':
        if '投稿' not in example:
            findings.append(_finding('consistency','要修正','SNS投稿教材なのに作例に投稿への言及がない',
                                     example[:90], '作例に「想定読者・テーマ・投稿目的・投稿文・次の行動」を表示する。'))
        if re.search(r'作業メモ|明日の作業|終業前|5分だけ振り返る', example):
            findings.append(_finding('consistency','要確認','SNS投稿の作例が日々の作業メモ寄りで、教材の用途が曖昧',
                                     '作例内の「作業メモ」「明日の作業」等を検出',
                                     '架空の店舗・サービス等のSNS投稿を題材に、入力条件→AI出力→人による修正の例を揃える。'))

    # Concrete how-to: look for actual steps and worked execution, not only headings.
    day_hits = [n for n in range(1,8) if re.search(rf'(?i)day\s*{n}(?!\d)', guide)]
    if len(day_hits) != 7:
        findings.append(_finding('concreteness','要修正','7日間の工程が揃っていない',
                                 f'Dayの検出：{day_hits}', 'Day 1〜7の作業・提出物・確認方法を記載する。'))
    if len(guide) < 2600:
        findings.append(_finding('concreteness','要確認','教材本文が短く、初心者向けの説明量が不足する可能性',
                                 f'教材本文の文字数：{len(guide)}字（長さは機械的な目安）',
                                 '各Dayに「所要時間・入力例・操作手順・出来上がり・つまずいたとき」を追記し、読者テストする。'))
    if not re.search(r'入力例|記入例|実演|具体例', guide):
        findings.append(_finding('concreteness','要確認','本文に具体的な入力例が見当たらない',
                                 '入力例／記入例／実演／具体例の見出し・表現が未検出',
                                 'Day 3などで入力条件と実際の出力例を1組掲載する。'))
    if not re.search(r'うまくいか|エラー|失敗したとき|つまず|再試行', guide):
        findings.append(_finding('concreteness','要確認','読者が失敗したときの対処方法が見当たらない',
                                 '再試行・つまずき対策の表現が未検出',
                                 'よくある失敗を3つ選び、原因とやり直し手順を追記する。'))

    # Usability and template readiness.
    if len(prompt.strip()) < 150:
        findings.append(_finding('usability','要確認','購入者向けプロンプトが短く条件不足の可能性',
                                 f'プロンプト文字数：{len(prompt)}字',
                                 '読者、目的、入力欄、禁止事項、出力形式、検証手順を明記する。'))
    placeholders = re.findall(r'\[[^\]\n]{2,50}\]|【要確認】|【未設定】', combined)
    if placeholders:
        findings.append(_finding('usability','要確認','未入力のまま使えない欄・要確認表示が残っている',
                                 '例：' + ' / '.join(dict.fromkeys(placeholders[:5])),
                                 '入力欄の記入例を添え、販売する本文の未処理プレースホルダーを個別に確認する。'))
    rows = assets.get('worksheet_rows') or []
    if not rows or not any('購入者の記入欄' in x for x in rows if isinstance(x,dict)):
        findings.append(_finding('usability','要修正','購入者用ワークシートの記入欄が確認できない',
                                 f'行数：{len(rows)}', '購入者が入力できる項目をCSVで用意する。'))
    if len(example.strip()) < 300:
        findings.append(_finding('usability','要確認','作例が短く、途中の判断過程を学びにくい可能性',
                                 f'作例文字数：{len(example)}字',
                                 '入力→AI下書き→人間の修正→完成例を1セット作る。'))

    # No invented competitor differentiation. Absence is not competitor non-existence.
    if not re.search(r'競合|比較|違い|差別化', guide):
        findings.append(_finding('differentiation','未検証','競合との違いを確認した記述が見当たらない',
                                 '競合／比較／違い／差別化の表現が本文に未検出',
                                 '比較対象記事の原ページ、比較日、確認できた公開情報を記録し、未確認事項を分ける。'))
    else:
        findings.append(_finding('differentiation','未検証','差別化を主張できる根拠はこの自動検査では未確認',
                                 '競合の有料本文や販売実績にはアクセスしていません',
                                 '競合の公開範囲を人間が確認し、実在しない機能を欠点として挙げない。'))

    # Safety / factual claims: flags only, not full semantic verification.
    suspicious = re.findall(r'(?:必ず|絶対|誰でも|確実に).{0,24}(?:稼|売|成功|収益|成果)|(?:月収|売上|利益)\s*[0-9０-９]+', combined)
    if suspicious:
        findings.append(_finding('accuracy','要確認','成果や収益の断定に見える表現を検出',
                                 ' / '.join(suspicious[:3]), '検証できない断定を削除し、根拠や条件を併記する。'))
    if '架空' not in example:
        findings.append(_finding('accuracy','要修正','練習例が架空である旨が明示されていない',
                                 '作例内に「架空」の表示なし', '実績と誤解されないよう「架空の例・未検証」を明記する。'))
    findings.append(_finding('accuracy','未検証','著作権・数値の出典・再現性は自動確認できない',
                             '外部記事照合、実際のAI実行、権利調査は未実施',
                             'CEOまたは担当者が原資料を照合し、プロンプトと全7日を再現テストする。'))

    counts = {key: sum(f['category']==key for f in findings) for key in CHECK_LABELS}
    return {
        'version':'48', 'status':'DRAFT_REVIEW_NOT_APPROVAL',
        'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
        'product_title': title, 'project':project, 'reader':reader,
        'method':'local_rule_based_heuristics_no_ai_api',
        'check_labels': CHECK_LABELS, 'finding_counts':counts,
        'findings':findings,
        'release_decision':'保留（CEO・人間による実物検証と販売承認が必要）',
        'limitations':'見出し・語句・文字数・構造からの簡易チェック。正確性・著作権・需要・実行可能性・販売品質の保証ではない。レビュー自体は教材を修正しない。'
    }


def report_markdown(report:dict) -> str:
    lines = [f"# Ver.48 品質検査レポート：{report['product_title']}", '',
             f"- 判定：{report['release_decision']}",
             f"- 方式：{report['method']}",
             '- 注意：機械的な検出結果であり、品質保証・販売承認ではありません。', '']
    for key, label in CHECK_LABELS.items():
        lines.extend([f'## {label}', ''])
        selected = [x for x in report['findings'] if x['category']==key]
        if not selected: lines.append('- 今回のルールでは警告なし（品質確認済みを意味しません）')
        for f in selected:
            lines.extend([f"### [{f['level']}] {f['issue']}", f"- 検出根拠：{f['evidence']}",
                          f"- 修正案：{f['action']}", ''])
    return '\n'.join(lines)


def package_zip(report:dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('quality_report.md',report_markdown(report))
        z.writestr('quality_report.json',json.dumps(report,ensure_ascii=False,indent=2))
        z.writestr('README.txt','Ver.48の簡易レビュー結果です。未検証であり、教材の修正・公開・販売・支出は実施していません。\n')
    return buf.getvalue()
