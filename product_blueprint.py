"""ZEROBOARD Ver.46: local, deterministic, unapproved product blueprint drafts.

Uses only CEO inputs and the Ver.45 outline; no network, AI API, publishing,
or claims about sales/competition. Outputs a plan, not actual customer assets.
"""
from datetime import datetime, timezone

PROJECTS = {
    'AIでSNS投稿案を作る': {
        'output': '対象読者を決めたSNS投稿案3本と改善記録',
        'input': ['誰に届ける投稿か', '発信テーマ', '禁止したい表現・事実確認項目'],
        'steps': ['対象読者と投稿テーマを1つ選ぶ', '投稿の目的と避ける表現を3つ記録する', 'AIに投稿案3本の下書きを作らせる', '事実・誇張・権利を人が点検する', '3本を読み比べて言い回しを修正する', '第三者1人に分かりやすさを聞く', '完成した3本と改善記録を整理する'],
        'quality': ['各案の対象読者が分かる', '未確認の事実・実績を断定していない', '既存記事や投稿を丸写ししていない', '目的に沿った投稿案を3本保存できた'],
        'example': '入力例：読者=近所の社会人／テーマ=作業効率／禁止=実績の誇張。出力例：短文投稿3本。',
    },
    'AIで実用チェックリストを作る': {
        'output': '特定の作業に使う10項目のチェックリストと使用例',
        'input': ['誰のどの作業に使うか', '作業の順番', '確認に必要な根拠や専門家の監修要否'],
        'steps': ['対象読者と作業場面を絞る', '作業の開始条件と終了条件を書く', 'AIでチェック項目を15個出す', '重複・危険・未確認の項目を削る', '使う順に10項目へ整理する', '自分で1回試して曖昧な項目を修正する', '完成版と使用例を保存する'],
        'quality': ['対象作業が具体的に指定されている', 'すべての項目が行動・確認の形になっている', '重要な判断は根拠を確認する注記がある', '10項目と記入例が揃っている'],
        'example': '入力例：読者=初めての副業者／作業=公開前チェック。出力例：10項目と記入例。',
    },
    'AIでサービス紹介文を作る': {
        'output': '架空のサービス紹介文1本と修正理由のメモ',
        'input': ['誰に何を提供するか', '確認できるサービス内容', '実績・料金など未確認の事柄'],
        'steps': ['紹介するサービスと顧客を決める', 'サービスの確認できる事実を列挙する', 'AIに見出しと紹介文を下書きさせる', '存在しない実績・保証・価格を削除する', '読者視点で分かりにくい文を修正する', '第三者に内容が伝わるか確認する', '紹介文1本と改善メモを保存する'],
        'quality': ['提供サービスが明確である', '裏付けのない数値・実績がない', '問い合わせ等の導線が仮置きで区別されている', '修正前後を比較できる'],
        'example': '入力例：サービス=架空の家事代行／顧客=一人暮らし。実在の実績や料金は入れない。',
    },
    '独自の試作品（内容を手入力）': {
        'output': '試作品1つと、作成手順・検証記録',
        'input': ['試作品の用途', '完成物の形式', '対象読者と利用場面'],
        'steps': ['作りたいものを一文で定義する', '読者と用途を具体化する', '必要な素材や入力情報を洗い出す', '最小限の試作品を作る', '誤り・権利・使いやすさを確認する', '第三者に試してもらい改善点を聞く', '完成版と作成・修正の記録を残す'],
        'quality': ['完成物を実際に開いて確認できる', '第三者が用途を理解できる', '事実や出典が必要な箇所は要確認としている', '改善記録が保存されている'],
        'example': '入力例：個人の予定管理に使う記入シート1枚。目的と確認方法を記録する。',
    },
}


def build(plan45, project, daily_minutes=30, note=''):
    if not isinstance(plan45, dict) or plan45.get('version') != '45':
        raise ValueError('Ver.45の商品設計案を先に作成してください。')
    if project not in PROJECTS:
        raise ValueError('試作品の種類を選択してください。')
    if not isinstance(daily_minutes, int) or daily_minutes < 10 or daily_minutes > 120:
        raise ValueError('1日の作業時間は10〜120分にしてください。')
    detail = PROJECTS[project]
    note = str(note or '').strip()[:300]
    title = str(plan45.get('product_title') or '')[:160]
    reader = str(plan45.get('reader_hypothesis') or '')[:160]
    goal = str(plan45.get('buyer_outcome_hypothesis') or '')[:240]
    if not title or not reader or not goal:
        raise ValueError('Ver.45の商品名・読者・完成目標を確認してください。')
    days = []
    for i, task in enumerate(detail['steps'], 1):
        days.append({
            'day': i, 'time_budget_minutes': daily_minutes,
            'task': task,
            'checkpoint': ('その日の作業結果と疑問を1行以上記録する。'
                           if i < 7 else '完成物と改善記録が保存できたか確認する。'),
            'evidence_of_completion': f'Day{i}の作業メモまたはファイル（実物は未制作）',
        })
    return {
        'version': '46', 'status': 'DRAFT_NOT_APPROVED',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'product_title': title, 'reader_hypothesis': reader,
        'buyer_outcome_hypothesis': goal,
        'selected_project': project, 'deliverable_specification': detail['output'],
        'daily_minutes': daily_minutes, 'ceo_notes': note,
        'required_inputs': detail['input'],
        'seven_day_plan': days,
        'worksheet_fields': [
            {'name': '目的と読者', 'example': reader, 'blank': ''},
            {'name': '試作品の用途', 'example': detail['output'], 'blank': ''},
            {'name': '初期入力・素材', 'example': detail['input'][0], 'blank': ''},
            {'name': '使った指示文／手順', 'example': '自分が実際に使った文を記録', 'blank': ''},
            {'name': '出力・制作物の保存先', 'example': 'ファイル名やURL（公開前なら非公開）', 'blank': ''},
            {'name': '事実・権利の確認結果', 'example': '確認済み／要確認と根拠', 'blank': ''},
            {'name': '改善した点', 'example': '実際の修正点を1つ記録', 'blank': ''},
        ],
        'quality_gate': detail['quality'],
        'example_outline': detail['example'],
        'free_preview_test': [
            'Day1の内容を無料サンプルとして見せ、理解できるか聞く',
            '試作品の見本を対象読者3人に見せ、役立つ場面を尋ねる',
            '購入意向は質問のみでなく、登録や予約など実際の行動で別途検証する',
        ],
        'source_competitors': plan45.get('sources', [])[:3],
        'approval': {'content_production': False, 'publication': False, 'sales': False, 'spending': False},
        'limitations': '実行可能性のたたき台であり、実物・テンプレートファイル・記事本文は未制作。成果や売上を保証しません。競合の有料本文・販売実績・需要は未確認。',
    }


def meeting_brief(blueprint):
    lines = [
        '【Ver.46 PRODUCT BLUEPRINT：制作前の仮設計・CEO承認待ち】',
        '商品名：' + blueprint['product_title'],
        '読者（仮説）：' + blueprint['reader_hypothesis'],
        '読後の完成物（仮説）：' + blueprint['buyer_outcome_hypothesis'],
        '今回の試作品：' + blueprint['selected_project'],
        '具体的な納品物：' + blueprint['deliverable_specification'],
        '想定作業時間：毎日' + str(blueprint['daily_minutes']) + '分×7日（目安）',
        '7日間の制作工程：',
    ]
    lines.extend(f"Day{x['day']}：{x['task']}" for x in blueprint['seven_day_plan'])
    lines.append('品質チェック：')
    lines.extend('- '+x for x in blueprint['quality_gate'])
    lines.append('未検証・制限：'+blueprint['limitations'])
    lines.append('制作・公開・販売・支出はCEOの別途承認が必要。ここでは実行しない。')
    return '\n'.join(lines)[:7000]
