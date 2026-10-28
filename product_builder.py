"""Ver.47 PRODUCT BUILDER: deterministic, local draft assets; not verified products.

No external calls, LLM calls, publishing, payment, or database writes.
"""
from __future__ import annotations
import csv
import io
import json
import zipfile
from datetime import datetime, timezone

PROMPTS = {
    'AIでSNS投稿案を作る': '''あなたはSNS投稿の編集補助です。以下の入力だけを根拠に、日本語の短文投稿案を3本作ってください。\n読者：[読者を入力]\nテーマ：[テーマを入力]\n投稿の目的：[目的を入力]\n避ける表現：[禁止表現を入力]\n条件：各案は「見出し／本文／読者の次の行動」の3段構成。未確認の数字・実績・体験談を創作しない。他人の投稿を複製しない。分からない点は【要確認】と表示する。最後に人間が確認すべき箇所を3点挙げる。''',
    'AIで実用チェックリストを作る': '''あなたは作業手順の編集補助です。対象読者：[読者]。対象作業：[作業名]。開始条件：[開始条件]。終了条件：[終了条件]。行動または観察で確認できる項目を10個作成し、各項目に「確認方法」と「未確認ならどうするか」を付けてください。法務・医療・税務など専門判断は一般向けの断定を避け、【専門家確認】と明記。''',
    'AIでサービス紹介文を作る': '''あなたはサービス紹介文の編集補助です。顧客：[読者]。サービス：[サービス内容]。確認済みの提供範囲：[範囲]。確認済みの価格：[価格または未定]。これだけを根拠に見出し・紹介文・利用上の注意・問い合わせ前の確認事項を作成。未提供サービス・架空の実績・口コミ・割引を作らない。不明点は【要確認】とする。''',
    '独自の試作品（内容を手入力）': '''あなたは試作品づくりの補助です。対象読者：[読者]。達成したいこと：[目的]。作るもの：[形式]。入力素材：[素材]。最小構成を具体化し、作成手順を5段階、チェックポイントを5つ示してください。未提供素材や実績を想像で埋めず【要確認】とする。''',
}

EXAMPLES = {
    'AIでSNS投稿案を作る': '''【架空の練習例：公開前に必ず編集】\n想定読者：忙しい社会人／テーマ：日々の作業メモ\n\n案1 見出し：明日の作業を3つに絞る\n本文：今日の終わりに「明日最初にやること」を3つ書き出してみよう。優先度は自分の予定に合わせて調整。\n次の行動：紙に3つメモする。\n\n案2 見出し：5分だけ振り返る\n本文：終業前に「進んだこと／困ったこと／次の一歩」をそれぞれ1行記録。無理なく続く形を探そう。\n次の行動：今日の記録を1件残す。\n\n案3 見出し：指示文に条件を足してみる\n本文：AIに文章を頼むときは、読者と目的、避けたい表現も添えてみよう。出力内容は人間が確認する。\n次の行動：自分のテーマで試作する。\n\n※効果・再現性は未検証。架空の教材見本。''',
    'AIで実用チェックリストを作る': '''【架空の練習例：投稿前チェック】\n□ 読者が一文で分かるか\n□ 一番伝えたいことは明確か\n□ 事実と意見を分けたか\n□ 数字の出典を確認したか\n□ 他者の文章を無断転載していないか\n□ 個人情報が含まれていないか\n□ 誇張や断定がないか\n□ 読者の次の行動が分かるか\n□ スマホで読める長さか\n□ 公開前に最終確認したか\n※専門分野は別途確認が必要。''',
    'AIでサービス紹介文を作る': '''【架空のサービスの例】\n見出し：部屋の片づけを始める前の相談窓口（架空）\n説明：片づけの目的と希望日時を整理する相談サービスの紹介例です。実際の提供範囲や対応エリアは【要確認】。\n料金：【未設定】。サービス提供実績：【未確認】。\n相談前に確認：希望する作業内容、場所、日程。\n※実在の業者や提供実績を表す文章ではありません。''',
    '独自の試作品（内容を手入力）': '''【架空の例：1枚の予定整理シート】\n目的：今週やることを見える化する。\n欄1：やること／欄2：期限／欄3：所要時間の見込み／欄4：完了チェック。\n使い方：3件だけ記入→順番を決める→週末に振り返る。\n※入力内容と結果は例示で、効果は未検証。''',
}


def build(blueprint: dict) -> dict:
    if not isinstance(blueprint, dict) or blueprint.get('version') != '46':
        raise ValueError('Ver.46の設計図を作成してください。')
    project = blueprint.get('selected_project')
    if project not in PROMPTS:
        raise ValueError('対応する試作品を選択してください。')
    title = str(blueprint.get('product_title') or '')[:160]
    reader = str(blueprint.get('reader_hypothesis') or '')[:160]
    goal = str(blueprint.get('buyer_outcome_hypothesis') or '')[:240]
    if not all((title, reader, goal)):
        raise ValueError('商品名・読者・完成目標を確認してください。')
    days = blueprint.get('seven_day_plan') or []
    if len(days) != 7:
        raise ValueError('7日間の設計図が不足しています。')
    outline = [
        '# ' + title + '｜教材ドラフト（未承認）',
        '',
        '想定読者（仮説）：' + reader,
        '購入者の目標（未検証）：' + goal,
        '試作品：' + project,
        '',
        '## 無料公開用の下書き（原稿ではなく構成）',
        '1. 想定読者が抱える悩みを具体化する（実際の声は未検証）',
        '2. 作業前に知っておくべき基本の考え方',
        '3. 自分で試せるミニ課題：テーマと読者を1行ずつ書く',
        '',
        '## 有料部分の下書き（完成前・販売不可）',
        '### 使い方',
        '付属のプロンプトを自分の条件に書き換えてAIに入力し、結果は必ず人間が検証する。',
        '### 7日間の練習',
    ]
    for day in days:
        outline.append(f"- Day {day['day']}：{day['task']}／確認：{day['checkpoint']}")
    outline += [
        '', '### 完成基準',
        *['- ' + str(x) for x in blueprint.get('quality_gate', [])],
        '', '### 販売前の確認',
        '- 付属テンプレートを実際に使って再現テストする',
        '- 出典・著作権・個人情報・専門的な正確性を確認する',
        '- 値付け・公開・販売はCEOが別途承認する',
        '', '※教材ドラフト。成果、販売実績、競合の有料部分は確認していません。'
    ]
    worksheet = [
        {'入力項目': str(f.get('name','')), '記入例（仮）': str(f.get('example','')), '購入者の記入欄': ''}
        for f in blueprint.get('worksheet_fields', [])
    ]
    for day in days:
        worksheet.append({'入力項目': f"Day{day['day']}の結果", '記入例（仮）': str(day['task']), '購入者の記入欄': ''})
    return {
        'version': '47', 'status': 'DRAFT_NOT_VERIFIED_OR_APPROVED',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_blueprint_created_at_utc': blueprint.get('created_at_utc'),
        'product_title': title, 'reader': reader, 'project': project,
        'guide_markdown': '\n'.join(outline),
        'copyable_prompt': PROMPTS[project],
        'fictional_example': EXAMPLES[project],
        'worksheet_rows': worksheet,
        'quality_checklist': list(blueprint.get('quality_gate', [])),
        'verification_tasks': [
            '実際のAIでプロンプトを実行し、修正前後を記録する（この画面は実行していない）',
            '全7日分を1回通して所要時間を測る',
            '想定読者に無料試作品を見せて感想と行動を確認する',
            '権利・事実・安全性・掲載条件を人間がチェックする',
            '価格・販売・公開・費用はCEOが別途承認する',
        ],
        'limitations': 'ひな型と架空の例を作成しただけで、AIによる原稿生成・実際の再現検証・市場需要検証は行っていません。販売可能な完成教材ではありません。',
    }


def csv_text(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=['入力項目','記入例（仮）','購入者の記入欄'])
    writer.writeheader()
    writer.writerows(rows)
    return '\ufeff' + buf.getvalue()  # Excel-friendly UTF-8 with BOM.


def package_zip(assets: dict, guide: str, prompt: str, example: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('01_guide_draft.md', guide)
        z.writestr('02_prompt_draft.txt', prompt)
        z.writestr('03_fictional_example.txt', example)
        z.writestr('04_worksheet.csv', csv_text(assets['worksheet_rows']))
        z.writestr('05_quality_checklist.txt', '\n'.join('- ' + x for x in assets['quality_checklist']))
        z.writestr('README.txt', 'ZEROBOARD Ver.47 未承認の教材草稿です。人間による検証、著作権確認、CEOの販売承認が必要です。\n')
    return buf.getvalue()


def meeting_brief(assets: dict) -> str:
    return '\n'.join([
        '【Ver.47 PRODUCT BUILDER：未検証・未承認の教材ドラフト】',
        '商品：' + assets['product_title'],
        '読者（仮説）：' + assets['reader'],
        '試作品：' + assets['project'],
        '作成物：教材構成草稿、AI入力プロンプト、架空の作例、記入式ワークシート、品質チェック',
        '未検証事項：' + '／'.join(assets['verification_tasks']),
        'CEO承認前の公開・販売・支出・商品化は禁止。',
    ])[:7000]
