# Ver.49 local suggestion-only drafting. No LLM, internet or publishing.
from __future__ import annotations
import difflib
import io
import json
import zipfile


def propose(assets: dict, guide: str, prompt: str, example: star, findings: list[dict]) -> dict:
    if assets.get('version') != '47':
        raise ValueError('Ver.47の教材データを先に作成してください。')
    guide, prompt, example = map(str, (guide, prompt, example))
    updated = {'guide':guide, 'prompt':prompt, 'example':example}
    changes = []
    codes = {x.get('issue','') for x in findings}
    def add(section: str, marker: str, text: str, reason: str):
        if marker not in updated[section]:
            updated[section] += '\n\n' + text.strip() + '\n'
            changes.append(reason)

    if assets.get('project') == 'AIでSNS投稿案を作る' and any('SNS投稿' in x for x in codes):
        updated['example'] = '''【架空のSNS投稿教材の作例／実際の成果・体験談ではありません】
題材：架空の小さな雑貨店（実在の店舗ではありません）
想定読者：週末に小物を探している近隣の人
テーマ：新入荷の文房具を紹介する
投稿目的：商品の存在を知ってもらい、来店前に在庫を問い合わせてもらう
禁止表現：売上No.1・完売続出・口コミ多数など裏付けのない表現

【AIへの入力例】
「架空の雑貨店のSNS投稿案を3本。読者は近隣の文房具好き。
目的は新入荷商品の紹介。価格・在庫・レビューは不明なので断定しない。
各案は見出し、本文、次の行動で構成して。」

【AIの下書き例（例示。実際のAI出力ログではありません）】
見出し：手帳時間がちょっと楽しくなる文房具
本文：新しい文房具を紹介しています。気になるアイテムはお気軽にお問い合わせください。
次の行動：在庫状況は事前にご確認ください。

【人間の修正例】
見出し：新入荷の文房具をご紹介
本文：店頭に新しい文房具が届きました。写真と一緒に特徴をご紹介します。
次の行動：価格・在庫はお問い合わせください。

【確認すること】商品が本当に入荷したか、掲載写真の権利、営業時間・在庫を店側が確認。
【注意】入力→下書き→修正は説明用の架空例です。再現性・効果は未検証。
'''
        changes.append('SNS投稿教材の作例を、架空の店の「入力条件→下書き例→人間による修正例」へ差し替え（自動生成の実行結果ではない）')
    if '教材本文が短く、初心者向けの説明量が不足する可能性' in codes or '本文に具体的な入力例が見当たらない' in codes or '読者が失敗したときの対処方法が見当たらない' in codes:
        add('guide','### 初心者が実際に進めるための補足（編集用）', '''### 初心者が実際に進めるための補足（編集用）
※この節は一般的な編集用ひな型。実際の所要時間・成果は検証していません。
1. 最初に「誰に・何を・何のために」を一行ずつ記入する。
2. 付属のAI指示文の角括弧を記入例に置き換えてから入力する。
3. 出力をそのまま使わず、誤った事実・誇張・権利侵害がないか確認する。
4. 問題を見つけたら、修正条件を一つ追加して再作成する。
5. 最終案と未確認事項をワークシートに記録する。

#### 入力例（架空）
想定読者：近所の文房具好き／目的：入荷案内／禁止：実績や価格の捏造
出力例の正しさは人間が確認すること。

#### うまくいかない場合
- 案が一般的すぎる：対象読者と商品の特徴を具体化する。
- 誇張や未確認情報が含まれる：その文を削除し、確認できる情報だけで作り直す。
- 読者の次の行動が曖昧：問い合わせ等、実際に可能な行動を一つだけ示す。

#### Dayごとの提出物の確認
各Day終了時に「作ったもの・判断に迷った点・翌日に直す点」を記録する。
''','初心者向けの入力例・失敗時の対処・作業結果記録のひな型を追記')
    if '購入者向けプロンプトが短く条件不足の可能性' in codes:
        add('prompt','【出力後のチェック】','''【出力後のチェック】
- 実在の人物・店・商品について不明な点は推測で埋めず【要確認】と書く。
- 出典のない数字、効果、実績の断定は避ける。
- 文章を読む人の次の行動を明確にする。
- 最後に「利用者が確認する項目」を3つ示す。
''','AI指示文に出力後の安全・事実確認項目を追加')
    if '練習例が架空である旨が明示されていない' in codes:
        updated['example'] = '【架空の例・実績ではありません】\n' + updated['example']
        changes.append('作例が架空の例である旨を明示')
    if any('差別化' in x or '競合との違い' in x for x in codes):
        add('guide','### 競合比較と独自価値（未検証）', '''### 競合比較と独自価値（未検証）
本教材の独自価値はまだ検証されていません。
比較対象のURL・公開日・無料公開部分・価格の確認状況を記録してから、類似点と相違点を検討します。
競合の有料本文が読めない場合、付属物の有無を断定してはいけません。
''','未確認の競合比較についての注意と記録欄を追記')
    if any('未入力のまま' in x for x in codes):
        add('guide','### 配布前に記入する項目（未完了）', '''### 配布前に記入する項目（未完了）
以下の例示プレースホルダーは、公開前に購入者向け説明と記入例を揃えてください。
購入者が自分で入力する空欄は、説明を添えた上で残します。
''','入力欄の説明を追記（入力不足の自動解消とはみなさない）')
    return {'version':'49', 'status':'PROPOSAL_ONLY_NOT_APPROVED', 'product_title':assets.get('product_title',''),
            'source_findings_count':len(findings), 'changes':changes,
            'original':{'guide':guide,'prompt':prompt,'example':example}, 'suggested':updated,
            'limitations':'ルールベースの参考修正案です。差別化・事実・著作権・再現性・需要は確認していません。採用後も再検査し、CEOが販売前に確認してください。'}


def compare_text(before: str, after: str) -> str:
    return '\n'.join(difflib.unified_diff(before.splitlines(),after.splitlines(),fromfile='修正前',tofile='修正案',lineterm='')) or '変更なし'


def package_zip(proposal:dict)->bytes:
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name,text in proposal['suggested'].items():
            z.writestr({'guide':'01_guide_proposed.md','prompt':'02_prompt_proposed.txt','example':'03_example_proposed.txt'}[name],text)
        z.writestr('revision_summary.json',json.dumps({'version':49,'changes':proposal['changes'],'limitations':proposal['limitations']},ensure_ascii=False,indent=2))
        z.writestr('README.txt','Ver.49 修正案は未承認です。公開・販売・外部送信・決済は行っていません。\n')
    return b.getvalue()
