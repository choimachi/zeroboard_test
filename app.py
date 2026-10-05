import streamlit as st
from openai import OpenAI
from supabase import create_client
import json


# ==================================================
# ページ設定
# ==================================================

st.set_page_config(
    page_title="ZEROBOARD AI",
    page_icon="🧠",
    layout="centered"
)

st.title("🧠 ZEROBOARD AI")
st.caption("AI経営会議システム")

st.write(
    "あなたがCEO。4人のAI役員が議論し、"
    "最後に議長AIが経営判断をまとめます。"
)

st.divider()


# ==================================================
# OpenAI接続
# ==================================================

client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)


# ==================================================
# Supabase接続
# ==================================================

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)


# ==================================================
# セッション初期化
# ==================================================

if "meeting_result" not in st.session_state:
    st.session_state.meeting_result = None

if "last_topic" not in st.session_state:
    st.session_state.last_topic = ""

if "used_memories" not in st.session_state:
    st.session_state.used_memories = []


# ==================================================
# Supabaseから過去会議を読み込む
# ==================================================

def load_meeting_history(limit=None):

    try:

        query = (
            supabase
            .table("meeting_history")
            .select("id, created_at, topic, final")
            .order("created_at", desc=True)
        )

        if limit:
            query = query.limit(limit)

        response = query.execute()

        return response.data or []

    except Exception as db_error:

        st.warning(
            "過去の会議履歴をSupabaseから"
            "読み込めませんでした。"
        )

        st.code(str(db_error))

        return []


# ==================================================
# Supabaseへ会議を保存
# ==================================================

def save_meeting(
    topic,
    final,
    decision="",
    goal="",
    deadline="",
    next_action="",
    result="",
    status="未着手"
):

    try:

        (
            supabase
            .table("meeting_history")
            .insert(
                {
                    "topic": topic,
                    "final": final,
                    "decision": decision,
                    "goal": goal,
                    "deadline": deadline,
                    "next_action": next_action,
                    "result": result,
                    "status": status
                }
            )
            .execute()
        )

        return True

    except Exception as db_error:

        st.warning(
            "AI経営会議は完了しましたが、"
            "Supabaseへの履歴保存に失敗しました。"
        )

        st.code(str(db_error))

        return False
# ==================================================
# 議長判断を構造化された経営記憶へ変換
# ==================================================

def create_structured_memory(topic, final):

    prompt = f"""
あなたはZEROBOARD AIの経営記憶管理AIです。

以下のAI経営会議の最終判断から、
将来の経営判断で使うべき重要情報を抽出してください。


【議題】

{topic}


【議長AIの最終判断】

{final}


以下のJSON形式だけで回答してください。

{{
    "decision": "最終的に何をすると決めたか",
    "goal": "具体的な目標。なければ空文字",
    "deadline": "期限。なければ空文字",
    "next_action": "CEOが次に実行すべき最も具体的な行動",
    "result": "",
    "status": "未着手"
}}

説明文、
Markdown、
```json
などは付けないでください。
"""

    try:

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        raw = response.output_text.strip()

        raw = raw.replace("```json", "")
        raw = raw.replace("```", "")
        raw = raw.strip()

        memory = json.loads(raw)

        return {
            "decision": memory.get(
                "decision",
                ""
            ),
            "goal": memory.get(
                "goal",
                ""
            ),
            "deadline": memory.get(
                "deadline",
                ""
            ),
            "next_action": memory.get(
                "next_action",
                ""
            ),
            "result": "",
            "status": "未着手"
        }

    except Exception:

        # 記憶整理に失敗しても
        # AI経営会議そのものは止めない
        return {
            "decision": "",
            "goal": "",
            "deadline": "",
            "next_action": "",
            "result": "",
            "status": "未着手"
        }

# ==================================================
# 過去会議から関連記憶を選ぶ
# ==================================================

def select_relevant_memories(current_topic):

    # Ver.1では直近20件を候補にする
    history = load_meeting_history(limit=20)

    if not history:
        return []

    memory_list = []

    for meeting in history:

        memory_list.append(
            {
                "id": meeting.get("id"),
                "topic": meeting.get("topic", ""),
                "final": meeting.get("final", "")
            }
        )

    selector_prompt = f"""
あなたはZEROBOARD AIの記憶管理AIです。

今回のCEOの議題と、
過去のAI経営会議を比較してください。

今回の議題を考えるうえで
本当に参考になる過去会議だけを選んでください。

最大3件です。

関連性が低い場合は、
無理に選ばず0件でも構いません。


【今回の議題】

{current_topic}


【過去の会議】

{json.dumps(memory_list, ensure_ascii=False)}


回答は必ずJSON配列だけにしてください。

例：

[10, 7, 3]

関連する記憶がない場合：

[]

説明文やMarkdownは一切付けないでください。
"""

    try:

        response = client.responses.create(
            model="gpt-5-mini",
            input=selector_prompt
        )

        raw = response.output_text.strip()

        # ```json ... ``` が返った場合にも対応
        raw = raw.replace("```json", "")
        raw = raw.replace("```", "")
        raw = raw.strip()

        selected_ids = json.loads(raw)

        if not isinstance(selected_ids, list):
            return []

        # 最大3件まで
        selected_ids = selected_ids[:3]

        selected_memories = []

        for meeting in history:

            if meeting.get("id") in selected_ids:

                selected_memories.append(meeting)

        return selected_memories

    except Exception:

        # 記憶選択に失敗しても
        # 本体の経営会議は止めない
        return []


# ==================================================
# AI役員へ渡す記憶文章を作る
# ==================================================

def build_memory_context(memories):

    if not memories:

        return """
【過去のZEROBOARD記憶】

今回の議題に直接関連する
過去の経営会議は見つかりませんでした。

過去の判断に無理に合わせず、
今回の情報を基準に判断してください。
"""

    blocks = []

    for memory in memories:

        blocks.append(
            f"""
--------------------

過去会議ID：
{memory.get("id")}

過去の議題：
{memory.get("topic", "")}

過去の最終経営判断：
{memory.get("final", "")}

--------------------
"""
        )

    return """
【ZEROBOARD 長期記憶】

以下は今回の議題に関連すると判断された
過去のAI経営会議です。

過去の判断を絶対視する必要はありません。

ただし、

・以前決めた方針
・以前指摘されたリスク
・過去の数字
・以前のアクションプラン
・今回と矛盾する判断

があれば考慮してください。

今回の状況の方が合理的なら、
過去の判断を修正して構いません。


""" + "\n".join(blocks)


# ==================================================
# AIに質問する関数
# ==================================================

def ask_ai(role, meeting_topic, memory_context=""):

    response = client.responses.create(
        model="gpt-5-mini",
        instructions=role,
        input=f"""
経営会議の議題：

{meeting_topic}


{memory_context}


日本語で回答してください。

具体的で実行可能な意見を出してください。

結論だけでなく、
その理由も簡潔に説明してください。

過去のZEROBOARD記憶がある場合は、
必要に応じてその内容も考慮してください。

ただし、
過去の判断を盲目的に踏襲してはいけません。
"""
    )

    return response.output_text


# ==================================================
# CEO 議題入力
# ==================================================

topic = st.text_area(
    "CEO、今日の議題を入力してください",
    placeholder=(
        "例：以前考えたAI副業を"
        "月10万円まで伸ばすには？"
    ),
    height=120
)


# ==================================================
# AI経営会議開始
# ==================================================

if st.button(
    "🚀 AI経営会議を開始",
    type="primary"
):

    if not topic.strip():

        st.warning(
            "まず議題を入力してください。"
        )

    else:

        try:

            # ==========================================
            # 関連記憶を検索
            # ==========================================

            with st.spinner(
                "🧠 ZEROBOARDが過去の記憶を検索中..."
            ):

                relevant_memories = (
                    select_relevant_memories(topic)
                )

                memory_context = (
                    build_memory_context(
                        relevant_memories
                    )
                )

                st.session_state.used_memories = (
                    relevant_memories
                )


            # ==========================================
            # 第1ラウンド
            # ==========================================

            with st.spinner(
                "AI役員が第1ラウンドを議論中..."
            ):

                strategy = ask_ai(
                    """
あなたはZEROBOARD AIの
戦略担当役員です。

市場機会、
競争優位、
事業モデル、
成長可能性

の観点から
CEOの議題を分析してください。

過去のZEROBOARD記憶がある場合、
以前の経営判断との連続性や
方針変更の必要性も考えてください。
""",
                    topic,
                    memory_context
                )


                marketing = ask_ai(
                    """
あなたはZEROBOARD AIの
マーケティング担当役員です。

顧客、
集客、
販売方法、
価格、
ブランド

の観点から
CEOの議題を分析してください。

過去のZEROBOARD記憶がある場合、
以前の顧客戦略や集客方針も
必要に応じて考慮してください。
""",
                    topic,
                    memory_context
                )


                finance = ask_ai(
                    """
あなたはZEROBOARD AIの
財務担当役員です。

必要資金、
売上、
利益、
コスト、
採算性

の観点から
CEOの議題を分析してください。

数字を使えるところは
具体的に示してください。

過去のZEROBOARD記憶に
以前の売上目標や費用、
利益計画などが存在する場合は、
今回との整合性も確認してください。
""",
                    topic,
                    memory_context
                )


                risk = ask_ai(
                    """
あなたはZEROBOARD AIの
リスク担当役員です。

失敗要因、
法的リスク、
競合、
実行上の問題、
見落としやすい点

を厳しく分析してください。

過去のZEROBOARD記憶に
以前指摘されたリスクがある場合、
それが解決されたかどうかも
考えてください。
""",
                    topic,
                    memory_context
                )


            # ==========================================
            # 第1ラウンドまとめ
            # ==========================================

            first_round = f"""
CEOの議題：

{topic}


{memory_context}


====================

【第1ラウンド】

====================


【戦略担当役員】

{strategy}


【マーケティング担当役員】

{marketing}


【財務担当役員】

{finance}


【リスク担当役員】

{risk}
"""


            # ==========================================
            # 第2ラウンド
            # ==========================================

            with st.spinner(
                "AI役員が第2ラウンドを討論中..."
            ):

                strategy_round2 = ask_ai(
                    """
あなたはZEROBOARD AIの
戦略担当役員です。

これは経営会議の第2ラウンドです。

他の3役員を含む
第1ラウンドの意見を読み、
戦略担当として議論を深めてください。

・賛成する意見
・反対または修正したい意見
・過去の判断との整合性
・その理由
・第1ラウンドから修正した最終提案

を具体的に述べてください。
""",
                    first_round
                )


                marketing_round2 = ask_ai(
                    """
あなたはZEROBOARD AIの
マーケティング担当役員です。

これは経営会議の第2ラウンドです。

他の役員の意見を踏まえて、

・賛成する意見
・反対または修正したい意見
・市場、顧客、集客面から見た理由
・過去の判断との整合性
・修正した最終提案

を具体的に述べてください。
""",
                    first_round
                )


                finance_round2 = ask_ai(
                    """
あなたはZEROBOARD AIの
財務担当役員です。

これは経営会議の第2ラウンドです。

他の役員の意見を踏まえて、

・賛成する意見
・数字的に問題のある意見
・利益、費用、回収期間から見た理由
・過去の財務判断との整合性
・修正した最終提案

を具体的に述べてください。
""",
                    first_round
                )


                risk_round2 = ask_ai(
                    """
あなたはZEROBOARD AIの
リスク担当役員です。

これは経営会議の第2ラウンドです。

他の役員の意見を踏まえて、

・賛成する意見
・危険だと思う意見
・過去に指摘されたリスク
・失敗要因や実行上の問題
・リスクを抑えた修正案

を具体的に述べてください。
""",
                    first_round
                )


            # ==========================================
            # 議長AI
            # ==========================================

            chairman_prompt = f"""
あなたはZEROBOARD AIの議長です。


CEOの議題：

{topic}


====================

【参照されたZEROBOARD記憶】

====================

{memory_context}


以下はAI役員による
2ラウンドの経営会議です。


====================

【第1ラウンド】

====================


【戦略担当】

{strategy}


【マーケティング担当】

{marketing}


【財務担当】

{finance}


【リスク担当】

{risk}


====================

【第2ラウンド】

====================


【戦略担当】

{strategy_round2}


【マーケティング担当】

{marketing_round2}


【財務担当】

{finance_round2}


【リスク担当】

{risk_round2}


これらを統合して、
CEO向けの最終経営判断を作ってください。

過去のZEROBOARD記憶がある場合は、
今回の判断との関係も考慮してください。

過去の判断と今回の判断が変わる場合は、
なぜ変更するのか明確にしてください。


必ず以下の形式で回答してください。


## 🎯 経営判断

実行すべきか、
修正すべきか、
見送るべきかを説明


## 🧠 過去の判断との関係

過去のZEROBOARD記憶を
どう今回の判断に使ったかを説明

関連記憶がなければ、
「今回直接参照すべき過去判断なし」
と記載


## 💡 理由

重要な理由を整理


## 💰 収益モデル

どうやって利益を作るか


## ⚠️ 最大のリスク

最も注意すべき問題


## 🚀 最初の一歩

CEOが今日からできる
具体的な行動


## 📅 7日間アクションプラン

Day1〜Day7まで
具体的に提示
"""


            # ==========================================
            # 議長AI 最終判断
            # ==========================================

            with st.spinner(
                "議長AIが記憶と議論を統合中..."
            ):

                final_response = client.responses.create(
                    model="gpt-5-mini",
                    input=chairman_prompt
                )

                final = final_response.output_text


            # ==========================================
            # セッションへ保存
            # ==========================================

            st.session_state.last_topic = topic

            st.session_state.meeting_result = {

                "strategy": strategy,

                "marketing": marketing,

                "finance": finance,

                "risk": risk,

                "strategy_round2":
                    strategy_round2,

                "marketing_round2":
                    marketing_round2,

                "finance_round2":
                    finance_round2,

                "risk_round2":
                    risk_round2,

                "final": final
            }


# ==========================================
# 経営判断を構造化
# ==========================================

with st.spinner(
    "🧠 ZEROBOARDが経営判断を記憶として整理中..."
):

    structured_memory = create_structured_memory(
        topic,
        final
    )


# ==========================================
# Supabaseへ永久保存
# ==========================================

saved = save_meeting(
    topic=topic,
    final=final,
    decision=structured_memory["decision"],
    goal=structured_memory["goal"],
    deadline=structured_memory["deadline"],
    next_action=structured_memory["next_action"],
    result=structured_memory["result"],
    status=structured_memory["status"]
)

if saved:

    st.toast(
        "🧠 経営判断を長期記憶へ保存しました"
    )

        except Exception as e:

            st.error(
                "AIとの通信または処理中に"
                "エラーが発生しました。"
            )

            st.code(
                str(e)
            )


# ==================================================
# 今回参照した記憶
# ==================================================

if st.session_state.meeting_result:

    st.divider()

    st.header(
        "🧠 今回参照した過去の記憶"
    )

    used_memories = (
        st.session_state.used_memories
    )

    if used_memories:

        st.success(
            f"{len(used_memories)}件の"
            "過去会議を参照しました。"
        )

        for memory in used_memories:

            with st.expander(
                f"記憶 #{memory.get('id')}｜"
                f"{memory.get('topic', '')}"
            ):

                st.markdown(
                    memory.get(
                        "final",
                        ""
                    )
                )

    else:

        st.info(
            "今回の議題に直接関連する"
            "過去の会議はありませんでした。"
        )


# ==================================================
# 今回の会議結果表示
# ==================================================

if st.session_state.meeting_result:

    result = st.session_state.meeting_result

    st.divider()

    st.header(
        "🏢 AI経営会議"
    )

    st.subheader(
        "📋 議題"
    )

    st.write(
        st.session_state.last_topic
    )


    # ==============================================
    # 第1ラウンド
    # ==============================================

    st.subheader(
        "1️⃣ 第1ラウンド"
    )

    with st.expander(
        "🧠 戦略担当役員"
    ):

        st.markdown(
            result["strategy"]
        )

    with st.expander(
        "📣 マーケティング担当役員"
    ):

        st.markdown(
            result["marketing"]
        )

    with st.expander(
        "💰 財務担当役員"
    ):

        st.markdown(
            result["finance"]
        )

    with st.expander(
        "⚠️ リスク担当役員"
    ):

        st.markdown(
            result["risk"]
        )


    # ==============================================
    # 第2ラウンド
    # ==============================================

    st.divider()

    st.subheader(
        "2️⃣ 第2ラウンド・役員討論"
    )

    with st.expander(
        "🧠 戦略担当役員・再検討"
    ):

        st.markdown(
            result["strategy_round2"]
        )

    with st.expander(
        "📣 マーケティング担当役員・再検討"
    ):

        st.markdown(
            result["marketing_round2"]
        )

    with st.expander(
        "💰 財務担当役員・再検討"
    ):

        st.markdown(
            result["finance_round2"]
        )

    with st.expander(
        "⚠️ リスク担当役員・再検討"
    ):

        st.markdown(
            result["risk_round2"]
        )


    # ==============================================
    # 議長AI
    # ==============================================

    st.divider()

    st.header(
        "👑 議長AI 最終判断"
    )

    st.markdown(
        result["final"]
    )

    st.success(
        "AI経営会議が完了しました。"
    )


# ==================================================
# ZEROBOARD MEMORY
# ==================================================

st.divider()

st.header(
    "🧠 ZEROBOARD MEMORY"
)

st.caption(
    "Supabaseに永久保存されているAI経営会議"
)

meeting_history = load_meeting_history()


# ==================================================
# 過去会議表示
# ==================================================

if meeting_history:

    st.success(
        f"{len(meeting_history)}件の"
        "会議記録を読み込みました。"
    )

    for meeting in meeting_history:

        meeting_id = meeting.get(
            "id",
            "?"
        )

        meeting_topic = meeting.get(
            "topic",
            "議題なし"
        )

        meeting_final = meeting.get(
            "final",
            ""
        )

        created_at = meeting.get(
            "created_at",
            ""
        )

        with st.expander(
            f"#{meeting_id}｜{meeting_topic}"
        ):

            if created_at:

                st.caption(
                    f"保存日時：{created_at}"
                )

            st.markdown(
                meeting_final
            )

else:

    st.info(
        "Supabaseに保存された"
        "会議履歴はまだありません。"
    )
