import streamlit as st
from openai import OpenAI
from supabase import create_client
import json
from datetime import date, datetime


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
# 日付チェック
# ==================================================

def normalize_due_date(value):

    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    try:
        datetime.strptime(
            value,
            "%Y-%m-%d"
        )

        return value

    except ValueError:
        return None


# ==================================================
# 優先順位チェック
# ==================================================

def normalize_priority(value):

    if value in [
        "高",
        "中",
        "低"
    ]:
        return value

    return "中"


# ==================================================
# Supabaseから過去会議を読み込む
# ==================================================

def load_meeting_history(limit=None):

    try:

        query = (
            supabase
            .table("meeting_history")
            .select(
                "id, created_at, topic, final, "
                "decision, goal, deadline, "
                "next_action, result, status, "
                "priority, due_date"
            )
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
    status="未着手",
    priority="中",
    due_date=None
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
                    "status": status,
                    "priority":
                        normalize_priority(
                            priority
                        ),
                    "due_date":
                        normalize_due_date(
                            due_date
                        )
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

def create_structured_memory(
    topic,
    final
):

    today_string = (
        date.today().isoformat()
    )

    prompt = f"""
あなたはZEROBOARD AIの経営記憶管理AIです。

今日は {today_string} です。

以下のAI経営会議の最終判断から、
将来の経営判断で使うべき重要情報を
抽出してください。


【議題】

{topic}


【議長AIの最終判断】

{final}


以下のJSON形式だけで回答してください。

{{
    "decision": "最終的に何をすると決めたか",
    "goal": "具体的な目標。なければ空文字",
    "deadline": "人間が読むための期限表現",
    "next_action": "CEOが次に実行すべき最も具体的な行動",
    "result": "",
    "status": "未着手",
    "priority": "高・中・低のいずれか",
    "due_date": "YYYY-MM-DD"
}}

priorityは必ず
「高」「中」「低」
のどれかにしてください。

判断基準：

高：
売上・利益・重大な問題・
期限が近い・経営上重要

中：
重要だが緊急ではない

低：
後回しでも経営への影響が小さい


due_dateについて：

・必ず可能な限り具体的な日付に変換
・YYYY-MM-DD形式
・「7日以内」なら今日から7日後
・「1ヶ月以内」なら合理的な期限日を設定
・期限を合理的に決められない場合は null

説明文やMarkdownは付けないでください。
"""

    try:

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        raw = (
            response
            .output_text
            .strip()
        )

        raw = raw.replace(
            "```json",
            ""
        )

        raw = raw.replace(
            "```",
            ""
        )

        raw = raw.strip()

        memory = json.loads(raw)

        return {
            "decision":
                memory.get(
                    "decision",
                    ""
                ),

            "goal":
                memory.get(
                    "goal",
                    ""
                ),

            "deadline":
                memory.get(
                    "deadline",
                    ""
                ),

            "next_action":
                memory.get(
                    "next_action",
                    ""
                ),

            "result": "",

            "status": "未着手",

            "priority":
                normalize_priority(
                    memory.get(
                        "priority",
                        "中"
                    )
                ),

            "due_date":
                normalize_due_date(
                    memory.get(
                        "due_date"
                    )
                )
        }

    except Exception:

        return {
            "decision": "",
            "goal": "",
            "deadline": "",
            "next_action": "",
            "result": "",
            "status": "未着手",
            "priority": "中",
            "due_date": None
        }


# ==================================================
# 過去会議から関連記憶を選ぶ
# ==================================================

def select_relevant_memories(
    current_topic
):

    history = (
        load_meeting_history(
            limit=20
        )
    )

    if not history:
        return []

    memory_list = []

    for meeting in history:

        memory_list.append(
            {
                "id":
                    meeting.get("id"),

                "topic":
                    meeting.get(
                        "topic",
                        ""
                    ),

                "final":
                    meeting.get(
                        "final",
                        ""
                    ),

                "decision":
                    meeting.get(
                        "decision",
                        ""
                    ),

                "goal":
                    meeting.get(
                        "goal",
                        ""
                    ),

                "deadline":
                    meeting.get(
                        "deadline",
                        ""
                    ),

                "next_action":
                    meeting.get(
                        "next_action",
                        ""
                    ),

                "result":
                    meeting.get(
                        "result",
                        ""
                    ),

                "status":
                    meeting.get(
                        "status",
                        ""
                    ),

                "priority":
                    meeting.get(
                        "priority",
                        ""
                    ),

                "due_date":
                    meeting.get(
                        "due_date"
                    )
            }
        )

    selector_prompt = f"""
あなたはZEROBOARD AIの記憶管理AIです。

今回のCEOの議題と、
過去のAI経営会議を比較してください。

今回の議題を考えるうえで
本当に参考になる過去会議だけを
最大3件選んでください。

関連性が低い場合は、
無理に選ばず0件でも構いません。


【今回の議題】

{current_topic}


【過去の会議】

{json.dumps(
    memory_list,
    ensure_ascii=False
)}


回答は必ずJSON配列だけにしてください。

例：

[10, 7, 3]

関連する記憶がない場合：

[]

説明文やMarkdownは付けないでください。
"""

    try:

        response = client.responses.create(
            model="gpt-5-mini",
            input=selector_prompt
        )

        raw = (
            response
            .output_text
            .strip()
        )

        raw = raw.replace(
            "```json",
            ""
        )

        raw = raw.replace(
            "```",
            ""
        )

        raw = raw.strip()

        selected_ids = (
            json.loads(raw)
        )

        if not isinstance(
            selected_ids,
            list
        ):
            return []

        selected_ids = (
            selected_ids[:3]
        )

        selected_memories = []

        for meeting in history:

            if (
                meeting.get("id")
                in selected_ids
            ):

                selected_memories.append(
                    meeting
                )

        return selected_memories

    except Exception:

        return []


# ==================================================
# AI役員へ渡す記憶文章
# ==================================================

def build_memory_context(
    memories
):

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

決定事項：
{memory.get("decision", "")}

目標：
{memory.get("goal", "")}

期限：
{memory.get("deadline", "")}

実期限：
{memory.get("due_date", "")}

優先順位：
{memory.get("priority", "")}

次の行動：
{memory.get("next_action", "")}

結果：
{memory.get("result", "")}

状態：
{memory.get("status", "")}

過去の最終経営判断：
{memory.get("final", "")}

--------------------
"""
        )

    return """
【ZEROBOARD 長期記憶】

以下は今回の議題に関連すると
判断された過去のAI経営会議です。

過去の判断を絶対視する必要はありません。

ただし、

・以前決めた方針
・以前設定した目標
・期限
・優先順位
・以前の次の行動
・実行結果
・現在のステータス
・以前指摘されたリスク
・今回と矛盾する判断

があれば考慮してください。

特に、
優先順位が高い未完了案件や
期限切れ案件が今回の議題と
関連する場合は重視してください。

今回の状況の方が合理的なら、
過去の判断を修正して構いません。


""" + "\n".join(blocks)


# ==================================================
# AIに質問
# ==================================================

def ask_ai(
    role,
    meeting_topic,
    memory_context=""
):

    response = client.responses.create(
        model="gpt-5-mini",
        instructions=role,
        input=f"""
経営会議の議題：

{meeting_topic}


{memory_context}


日本語で回答してください。

具体的で実行可能な意見を
出してください。

結論だけでなく、
その理由も簡潔に説明してください。

過去のZEROBOARD記憶がある場合は、
必要に応じてその内容も
考慮してください。

ただし、
過去の判断を盲目的に
踏襲してはいけません。
"""
    )

    return response.output_text


# ==================================================
# CEO DASHBOARD
# ==================================================

st.header(
    "📊 CEO DASHBOARD"
)

st.caption(
    "ZEROBOARDが記憶している現在の経営課題"
)

dashboard_items = (
    load_meeting_history()
)


# ==================================================
# 構造化された案件だけ対象
# ==================================================

dashboard_items = [
    item
    for item in dashboard_items
    if (
        item.get("decision")
        or item.get("next_action")
    )
]


# ==================================================
# ステータス集計
# ==================================================

not_started = sum(
    1
    for item in dashboard_items
    if item.get("status") == "未着手"
)

in_progress = sum(
    1
    for item in dashboard_items
    if item.get("status") == "進行中"
)

completed = sum(
    1
    for item in dashboard_items
    if item.get("status") == "完了"
)


col1, col2, col3 = (
    st.columns(3)
)

with col1:

    st.metric(
        "🔴 未着手",
        not_started
    )

with col2:

    st.metric(
        "🟡 進行中",
        in_progress
    )

with col3:

    st.metric(
        "🟢 完了",
        completed
    )


# ==================================================
# 未完了案件
# ==================================================

active_items = [
    item
    for item in dashboard_items
    if item.get("status")
    in [
        "未着手",
        "進行中"
    ]
]


# ==================================================
# 優先順位で並び替え
# ==================================================

priority_order = {
    "高": 0,
    "中": 1,
    "低": 2
}


def dashboard_sort_key(item):

    priority = item.get(
        "priority"
    )

    priority_number = (
        priority_order.get(
            priority,
            1
        )
    )

    due = item.get(
        "due_date"
    )

    if due:

        try:

            due_value = (
                datetime.strptime(
                    due,
                    "%Y-%m-%d"
                ).date()
            )

        except ValueError:

            due_value = date.max

    else:

        due_value = date.max

    return (
        priority_number,
        due_value
    )


active_items.sort(
    key=dashboard_sort_key
)


# ==================================================
# ACTIVE DECISIONS
# ==================================================

if active_items:

    st.subheader(
        "🎯 ACTIVE DECISIONS"
    )

    today = date.today()

    for item in active_items:

        item_id = (
            item.get("id")
        )

        item_topic = (
            item.get(
                "topic",
                "議題なし"
            )
        )

        decision = (
            item.get(
                "decision",
                ""
            )
        )

        goal = (
            item.get(
                "goal",
                ""
            )
        )

        deadline = (
            item.get(
                "deadline",
                ""
            )
        )

        next_action = (
            item.get(
                "next_action",
                ""
            )
        )

        result = (
            item.get(
                "result",
                ""
            )
        )

        status = (
            item.get(
                "status"
            )
            or "未着手"
        )

        priority = (
            item.get(
                "priority"
            )
            or "中"
        )

        due_date = (
            item.get(
                "due_date"
            )
        )


        # ==========================================
        # ステータスアイコン
        # ==========================================

        if status == "進行中":
            status_icon = "🟡"

        else:
            status_icon = "🔴"


        # ==========================================
        # 優先順位アイコン
        # ==========================================

        if priority == "高":

            priority_icon = "🔥"

        elif priority == "低":

            priority_icon = "💤"

        else:

            priority_icon = "⚡"


        # ==========================================
        # 期限判定
        # ==========================================

        due_message = ""

        if due_date:

            try:

                due_object = (
                    datetime.strptime(
                        due_date,
                        "%Y-%m-%d"
                    ).date()
                )

                remaining_days = (
                    due_object - today
                ).days

                if remaining_days < 0:

                    due_message = (
                        f"🚨 期限切れ "
                        f"{abs(remaining_days)}日"
                    )

                elif remaining_days == 0:

                    due_message = (
                        "🚨 今日が期限"
                    )

                elif remaining_days <= 3:

                    due_message = (
                        f"⚠️ あと"
                        f"{remaining_days}日"
                    )

                else:

                    due_message = (
                        f"⏰ あと"
                        f"{remaining_days}日"
                    )

            except ValueError:

                due_message = ""


        expander_title = (
            f"{priority_icon} "
            f"{status_icon} "
            f"#{item_id}｜"
            f"{item_topic}"
        )

        if due_message:

            expander_title += (
                f"｜{due_message}"
            )


        with st.expander(
            expander_title
        ):

            st.write(
                f"**優先順位：** "
                f"{priority_icon} "
                f"{priority}"
            )

            if decision:

                st.write(
                    f"**🎯 決定事項：** "
                    f"{decision}"
                )

            if goal:

                st.write(
                    f"**📈 目標：** "
                    f"{goal}"
                )

            if deadline:

                st.write(
                    f"**⏰ 期限：** "
                    f"{deadline}"
                )

            if due_date:

                st.write(
                    f"**📅 実期限：** "
                    f"{due_date}"
                )

            if due_message:

                if (
                    "期限切れ"
                    in due_message
                    or "今日が期限"
                    in due_message
                ):

                    st.error(
                        due_message
                    )

                elif (
                    remaining_days
                    <= 3
                ):

                    st.warning(
                        due_message
                    )

                else:

                    st.info(
                        due_message
                    )

            if next_action:

                st.write(
                    f"**🚀 NEXT ACTION：** "
                    f"{next_action}"
                )

            st.divider()


            # ======================================
            # ステータス変更
            # ======================================

            status_options = [
                "未着手",
                "進行中",
                "完了",
                "中止"
            ]

            new_status = st.selectbox(
                "状態",
                status_options,
                index=(
                    status_options.index(
                        status
                    )
                    if status
                    in status_options
                    else 0
                ),
                key=f"status_{item_id}"
            )


            # ======================================
            # 実行結果
            # ======================================

            new_result = st.text_area(
                "📊 実行結果・進捗メモ",
                value=result or "",
                placeholder=(
                    "例：Instagram投稿を7日間実施。"
                    "新規問い合わせ3件、来店1件。"
                ),
                key=f"result_{item_id}"
            )


            # ======================================
            # 保存
            # ======================================

            if st.button(
                "💾 進捗を保存",
                key=f"save_{item_id}"
            ):

                try:

                    (
                        supabase
                        .table(
                            "meeting_history"
                        )
                        .update(
                            {
                                "status":
                                    new_status,

                                "result":
                                    new_result
                            }
                        )
                        .eq(
                            "id",
                            item_id
                        )
                        .execute()
                    )

                    st.toast(
                        "💾 進捗を保存しました"
                    )

                    st.rerun()

                except Exception as update_error:

                    st.error(
                        "進捗の保存に失敗しました。"
                    )

                    st.code(
                        str(update_error)
                    )

else:

    st.info(
        "現在進行中の経営課題はありません。"
    )


st.divider()


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

            # ======================================
            # 関連記憶
            # ======================================

            with st.spinner(
                "🧠 ZEROBOARDが過去の記憶を検索中..."
            ):

                relevant_memories = (
                    select_relevant_memories(
                        topic
                    )
                )

                memory_context = (
                    build_memory_context(
                        relevant_memories
                    )
                )

                st.session_state.used_memories = (
                    relevant_memories
                )


            # ======================================
            # 第1ラウンド
            # ======================================

            with st.spinner(
                "AI役員が第1ラウンドを議論中..."
            ):

                strategy = ask_ai(
                    """
あなたはZEROBOARD AIの戦略担当役員です。

市場機会、
競争優位、
事業モデル、
成長可能性

の観点からCEOの議題を分析してください。

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

の観点からCEOの議題を分析してください。

過去のZEROBOARD記憶がある場合、
以前の顧客戦略や集客方針も
必要に応じて考慮してください。
""",
                    topic,
                    memory_context
                )

                finance = ask_ai(
                    """
あなたはZEROBOARD AIの財務担当役員です。

必要資金、
売上、
利益、
コスト、
採算性

の観点からCEOの議題を分析してください。

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
あなたはZEROBOARD AIのリスク担当役員です。

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


            # ======================================
            # 第2ラウンド
            # ======================================

            with st.spinner(
                "AI役員が第2ラウンドを討論中..."
            ):

                strategy_round2 = ask_ai(
                    """
あなたはZEROBOARD AIの戦略担当役員です。

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
あなたはZEROBOARD AIの財務担当役員です。

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
あなたはZEROBOARD AIのリスク担当役員です。

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


            # ======================================
            # 議長AI
            # ======================================

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


            with st.spinner(
                "議長AIが記憶と議論を統合中..."
            ):

                final_response = (
                    client.responses.create(
                        model="gpt-5-mini",
                        input=chairman_prompt
                    )
                )

                final = (
                    final_response
                    .output_text
                )


            # ======================================
            # セッション保存
            # ======================================

            st.session_state.last_topic = (
                topic
            )

            st.session_state.meeting_result = {
                "strategy":
                    strategy,

                "marketing":
                    marketing,

                "finance":
                    finance,

                "risk":
                    risk,

                "strategy_round2":
                    strategy_round2,

                "marketing_round2":
                    marketing_round2,

                "finance_round2":
                    finance_round2,

                "risk_round2":
                    risk_round2,

                "final":
                    final
            }


            # ======================================
            # 構造化
            # ======================================

            with st.spinner(
                "🧠 ZEROBOARDが経営判断を"
                "記憶として整理中..."
            ):

                structured_memory = (
                    create_structured_memory(
                        topic,
                        final
                    )
                )


            # ======================================
            # Supabase保存
            # ======================================

            saved = save_meeting(
                topic=topic,

                final=final,

                decision=(
                    structured_memory[
                        "decision"
                    ]
                ),

                goal=(
                    structured_memory[
                        "goal"
                    ]
                ),

                deadline=(
                    structured_memory[
                        "deadline"
                    ]
                ),

                next_action=(
                    structured_memory[
                        "next_action"
                    ]
                ),

                result=(
                    structured_memory[
                        "result"
                    ]
                ),

                status=(
                    structured_memory[
                        "status"
                    ]
                ),

                priority=(
                    structured_memory[
                        "priority"
                    ]
                ),

                due_date=(
                    structured_memory[
                        "due_date"
                    ]
                )
            )

            if saved:

                st.toast(
                    "🧠 経営判断を"
                    "長期記憶へ保存しました"
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

                decision = memory.get(
                    "decision",
                    ""
                )

                goal = memory.get(
                    "goal",
                    ""
                )

                deadline = memory.get(
                    "deadline",
                    ""
                )

                next_action = memory.get(
                    "next_action",
                    ""
                )

                status = memory.get(
                    "status",
                    ""
                )

                priority = memory.get(
                    "priority",
                    ""
                )

                due_date = memory.get(
                    "due_date",
                    ""
                )

                result_memory = memory.get(
                    "result",
                    ""
                )

                if priority:
                    st.write(
                        f"**優先順位：** "
                        f"{priority}"
                    )

                if decision:
                    st.write(
                        f"**決定事項：** "
                        f"{decision}"
                    )

                if goal:
                    st.write(
                        f"**目標：** "
                        f"{goal}"
                    )

                if deadline:
                    st.write(
                        f"**期限：** "
                        f"{deadline}"
                    )

                if due_date:
                    st.write(
                        f"**実期限：** "
                        f"{due_date}"
                    )

                if next_action:
                    st.write(
                        f"**次の行動：** "
                        f"{next_action}"
                    )

                if result_memory:
                    st.write(
                        f"**結果：** "
                        f"{result_memory}"
                    )

                if status:
                    st.write(
                        f"**状態：** "
                        f"{status}"
                    )

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

    result = (
        st.session_state.meeting_result
    )

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


    st.divider()

    st.subheader(
        "2️⃣ 第2ラウンド・役員討論"
    )

    with st.expander(
        "🧠 戦略担当役員・再検討"
    ):
        st.markdown(
            result[
                "strategy_round2"
            ]
        )

    with st.expander(
        "📣 マーケティング担当役員・再検討"
    ):
        st.markdown(
            result[
                "marketing_round2"
            ]
        )

    with st.expander(
        "💰 財務担当役員・再検討"
    ):
        st.markdown(
            result[
                "finance_round2"
            ]
        )

    with st.expander(
        "⚠️ リスク担当役員・再検討"
    ):
        st.markdown(
            result[
                "risk_round2"
            ]
        )


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

meeting_history = (
    load_meeting_history()
)


if meeting_history:

    st.success(
        f"{len(meeting_history)}件の"
        "会議記録を読み込みました。"
    )

    for meeting in meeting_history:

        meeting_id = (
            meeting.get(
                "id",
                "?"
            )
        )

        meeting_topic = (
            meeting.get(
                "topic",
                "議題なし"
            )
        )

        meeting_final = (
            meeting.get(
                "final",
                ""
            )
        )

        created_at = (
            meeting.get(
                "created_at",
                ""
            )
        )

        decision = (
            meeting.get(
                "decision",
                ""
            )
        )

        goal = (
            meeting.get(
                "goal",
                ""
            )
        )

        deadline = (
            meeting.get(
                "deadline",
                ""
            )
        )

        next_action = (
            meeting.get(
                "next_action",
                ""
            )
        )

        meeting_result = (
            meeting.get(
                "result",
                ""
            )
        )

        status = (
            meeting.get(
                "status",
                ""
            )
        )

        priority = (
            meeting.get(
                "priority",
                ""
            )
        )

        due_date = (
            meeting.get(
                "due_date",
                ""
            )
        )


        with st.expander(
            f"#{meeting_id}｜"
            f"{meeting_topic}"
        ):

            if created_at:
                st.caption(
                    f"保存日時："
                    f"{created_at}"
                )

            if priority:
                st.write(
                    f"**🔥 優先順位：** "
                    f"{priority}"
                )

            if decision:
                st.write(
                    f"**🎯 決定事項：** "
                    f"{decision}"
                )

            if goal:
                st.write(
                    f"**📈 目標：** "
                    f"{goal}"
                )

            if deadline:
                st.write(
                    f"**⏰ 期限：** "
                    f"{deadline}"
                )

            if due_date:
                st.write(
                    f"**📅 実期限：** "
                    f"{due_date}"
                )

            if next_action:
                st.write(
                    f"**🚀 次の行動：** "
                    f"{next_action}"
                )

            if meeting_result:
                st.write(
                    f"**📊 結果：** "
                    f"{meeting_result}"
                )

            if status:
                st.write(
                    f"**📌 状態：** "
                    f"{status}"
                )

            st.divider()

            st.markdown(
                meeting_final
            )

else:

    st.info(
        "Supabaseに保存された"
        "会議履歴はまだありません。"
    )
