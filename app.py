import streamlit as st
from docx import Document
import pandas as pd
import re
import os
import time
import random

def parse_lines(lines):
    questions = []
    current_question = None
    
    # 正则表达式匹配
    # 匹配题目：以数字开头，后面跟 . 或 、
    question_pattern = re.compile(r'^(\d+)[\.、\s](.*)')
    # 匹配选项：以 A-D 开头，后面跟 . 或 、
    option_pattern = re.compile(r'^([A-D])[\.、\s](.*)')
    # 匹配答案：包含“答案”关键字，支持 A-D 或 文本
    # 修改为更通用的匹配，捕获冒号后的所有内容
    answer_pattern = re.compile(r'^答案[:：\s]*(.*)')

    for text in lines:
        text = text.strip()
        if not text:
            continue
            
        # 检查是否是题目
        q_match = question_pattern.match(text)
        if q_match:
            # 如果之前有题目正在处理，先保存（除非是第一个）
            if current_question:
                questions.append(current_question)
            
            current_question = {
                "id": q_match.group(1),
                "content": q_match.group(2),
                "options": {},
                "answer": None,
                "user_answer": None,
                "type": "unknown" # 题目类型：choice (单选), judge (判断), text (主观/填空)
            }
            continue
            
        # 检查是否是选项
        opt_match = option_pattern.match(text)
        if current_question and opt_match:
            option_key = opt_match.group(1)
            option_content = opt_match.group(2)
            current_question["options"][option_key] = option_content
            current_question["type"] = "choice"
            continue
            
        # 检查是否是答案
        ans_match = answer_pattern.match(text)
        if current_question and ans_match:
            # 清理答案：去除首尾空格，以及末尾可能存在的句号
            raw_ans = ans_match.group(1).strip()
            current_question["answer"] = raw_ans.rstrip('.').rstrip('。')
            
            # 如果没有选项，且答案是 A 或 B，可能是判断题（有些判断题用A/B表示对错）
            # 或者题目内容包含“正确”、“错误”字样
            if not current_question["options"]:
                if current_question["answer"] in ['A', 'B'] and ("正确" in current_question["content"] or "错误" in current_question["content"] or "判断" in current_question["content"]):
                     current_question["type"] = "judge"
                     # 自动补全判断题选项
                     current_question["options"] = {'A': '正确', 'B': '错误'}
                else:
                    # 区分填空题和简答题
                    # 启发式规则：题目包含括号或答案包含“填空”
                    if "（）" in current_question["content"] or "()" in current_question["content"] or "填空" in current_question["answer"]:
                        current_question["type"] = "fill"
                    else:
                        current_question["type"] = "essay"
            elif current_question["type"] == "unknown":
                 # 有选项但没被标记为 choice (理论上不会发生，除非选项解析失败)
                 current_question["type"] = "choice"
            continue
            
        # 如果是题目的补充描述（多行题目），追加到 content
        if current_question and not opt_match and not ans_match:
             # 简单的追加逻辑
             current_question["content"] += " " + text

    # 添加最后一个题目
    if current_question:
        questions.append(current_question)
        
    return questions

def parse_docx(file):
    document = Document(file)
    lines = [para.text for para in document.paragraphs]
    return parse_lines(lines)

def parse_text(text):
    # 修复换行符切分问题，兼容不同系统的换行
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    return parse_lines(lines)

def clean_answer_key(text):
    if not text:
        return ""
    # 转半角、大写、去空格
    text = text.strip().upper()
    # 简单的全角转半角映射
    full_width = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    half_width = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    table = str.maketrans(full_width, half_width)
    text = text.translate(table)
    # 去除标点
    text = text.rstrip('.').rstrip('。').rstrip('、')
    return text

def refresh_cell_points():
    return random.randint(5, 25)

def init_game_state(total_questions, board_size=12):
    if 'game' not in st.session_state:
        st.session_state['game'] = {
            'board_size': board_size,
            'board_points': [refresh_cell_points() for _ in range(board_size)],
            'player_pos': 0,
            'bot_pos': 0,
            'prev_player_pos': 0,
            'prev_bot_pos': 0,
            'player_score': 0,
            'bot_score': 0,
            'auto_interval': 8,
            'bot_next_roll': time.time() + 8,
            'answered_questions': set(),
            'rewarded_questions': set(),
            'messages': []
        }
    game = st.session_state['game']
    if game.get('board_size') != board_size:
        game['board_size'] = board_size
        game['board_points'] = [refresh_cell_points() for _ in range(board_size)]
        game['player_pos'] = 0
        game['bot_pos'] = 0
        game['prev_player_pos'] = 0
        game['prev_bot_pos'] = 0
        game['player_score'] = 0
        game['bot_score'] = 0
        game['messages'] = []
        game['rewarded_questions'] = set()
        game['answered_questions'] = set()
    
    # Ensure prev_pos exists for existing sessions
    if 'prev_player_pos' not in game: game['prev_player_pos'] = game['player_pos']
    if 'prev_bot_pos' not in game: game['prev_bot_pos'] = game['bot_pos']

    if game.get('total_questions') != total_questions:
        game['answered_questions'] = set()
        game['rewarded_questions'] = set()
    game['total_questions'] = total_questions
    game.setdefault('answered_questions', set())
    game.setdefault('rewarded_questions', set())
    game.setdefault('messages', [])
    game.setdefault('bot_next_roll', time.time() + game.get('auto_interval', 8))
    return game

def record_game_message(game, text):
    game['messages'].insert(0, text)
    game['messages'] = game['messages'][:6]

def roll_and_collect(game, entity):
    steps = random.randint(1, 6)
    pos_key = f"{entity}_pos"
    prev_pos_key = f"prev_{entity}_pos"
    score_key = f"{entity}_score"
    
    # Record previous position before moving
    game[prev_pos_key] = game[pos_key]
    
    board_size = game['board_size']
    game[pos_key] = (game[pos_key] + steps) % board_size
    pos = game[pos_key]
    gained = game['board_points'][pos]
    game[score_key] += gained
    game['board_points'][pos] = refresh_cell_points()
    return steps, gained, pos

def player_reward_turn(game, reason):
    steps, gained, pos = roll_and_collect(game, 'player')
    record_game_message(game, f"🎯 {reason}：你掷出 {steps} 点，在格子 {pos + 1} 抢得 {gained} 分！")

def bot_auto_turn(game):
    steps, gained, pos = roll_and_collect(game, 'bot')
    record_game_message(game, f"🤖 人机掷出 {steps} 点，在格子 {pos + 1} 抢得 {gained} 分。")

def handle_bot_autoplay(game):
    now = time.time()
    interval = game.get('auto_interval', 8)
    if now >= game.get('bot_next_roll', 0):
        bot_auto_turn(game)
        game['bot_next_roll'] = now + interval

def render_board_html(game, current_player_pos=None, current_bot_pos=None):
    if current_player_pos is None: current_player_pos = game['player_pos']
    if current_bot_pos is None: current_bot_pos = game['bot_pos']
    
    board_size = game['board_size']
    points = game['board_points']
    
    html = """
    <style>
        .monopoly-board {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-top: 10px;
        }
        .monopoly-cell {
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            padding: 5px;
            text-align: center;
            background-color: #ffffff;
            position: relative;
            height: 70px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .monopoly-cell.active {
            border-color: #ff4b4b;
            background-color: #fff5f5;
            transform: scale(1.02);
        }
        .cell-id {
            font-size: 10px;
            color: #999;
            position: absolute;
            top: 2px;
            left: 4px;
        }
        .cell-points {
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
        }
        .cell-avatars {
            font-size: 20px;
            margin-top: 2px;
            height: 24px;
            line-height: 1;
        }
    </style>
    <div class="monopoly-board">
    """
    
    for i in range(board_size):
        cell_content = f'<div class="cell-id">#{i+1}</div>'
        cell_content += f'<div class="cell-points">+{points[i]}</div>'
        
        avatars = []
        if i == current_player_pos: avatars.append("👤")
        if i == current_bot_pos: avatars.append("🤖")
        
        avatar_html = f'<div class="cell-avatars">{" ".join(avatars)}</div>'
        cell_content += avatar_html
        
        active_class = "active" if avatars else ""
        html += f'<div class="monopoly-cell {active_class}">{cell_content}</div>'
        
    html += "</div>"
    return html

def reset_game_state():
    if 'game' in st.session_state:
        del st.session_state['game']

def schedule_auto_refresh(interval_seconds: int):
    interval_ms = max(int(interval_seconds * 1000), 1000)
    st.markdown(
        f"<script>setTimeout(() => window.location.reload(), {interval_ms});</script>",
        unsafe_allow_html=True
    )

def save_answers():
    """
    回调函数：在提交表单时保存用户的答题状态。
    Streamlit 的机制是：如果一个 widget 在某次运行中没有被渲染，它的 state 就会被清除。
    因为提交后我们不再渲染原始的 st.radio (而是渲染 disabled 的)，所以必须手动持久化保存答案。
    """
    if 'user_answers' not in st.session_state:
        st.session_state['user_answers'] = {}
    
    # 遍历 session_state，保存所有题目答案
    for k, v in st.session_state.items():
        if k.startswith('q_'):
            st.session_state['user_answers'][k] = v

def main():
    st.set_page_config(page_title="智能刷题系统", layout="wide")
    
    st.title("📝 智能刷题系统")
    st.markdown("上传 Word 格式的试卷，或直接粘贴文本，自动生成刷题界面。")
    
    with st.sidebar:
        st.header("试卷来源")
        input_method = st.radio("选择输入方式", ["上传文件", "粘贴文本"])
        
        uploaded_file = None
        pasted_text = None
        
        if input_method == "上传文件":
            uploaded_file = st.file_uploader("选择 .docx 文件", type="docx")
        else:
            pasted_text = st.text_area("粘贴试卷内容", height=300, placeholder="1. 题目...\\nA. 选项...\\n答案：A")
            parse_btn = st.button("解析文本")
        
        st.markdown("---")
        st.markdown("### 刷题设置")
        # 题目类型映射
        type_mapping = {
            "选择题": "choice",
            "判断题": "judge",
            "填空题": "fill",
            "简答题": "essay"
        }
        selected_types_labels = st.multiselect(
            "选择要练习的题型",
            list(type_mapping.keys()),
            default=list(type_mapping.keys())
        )
        selected_types = [type_mapping[label] for label in selected_types_labels]

        # 只看错题选项 (仅在提交后显示)
        show_errors = False
        if st.session_state.get('submitted'):
            st.markdown("---")
            show_errors = st.checkbox("只看错题 (仅显示自动判分错误的题目)")
            
        st.markdown("---")
        # 刷题模式选择
        mode = st.radio("刷题模式", ["考试模式", "练习模式"], help="考试模式：提交后统一判分；练习模式：做完一题立即显示答案。")
        
        st.markdown("---")
        font_size = st.slider("字体大小调节", min_value=14, max_value=30, value=18, step=1)
        
        st.markdown(f"""
        <style>
            /* 选项 (Radio buttons) */
            .stRadio p {{
                font_size: {font_size}px !important;
            }}
            /* 文本输入框 (Text Area) */
            .stTextArea textarea {{
                font_size: {font_size}px !important;
            }}
            .stTextArea label {{
                font_size: {font_size}px !important;
            }}
        </style>
        """, unsafe_allow_html=True)

        if mode == "练习模式":
            default_interval = st.session_state.get('game', {}).get('auto_interval', 8)
            auto_interval = st.slider("人机自动掷骰间隔 (秒)", min_value=3, max_value=30, value=int(default_interval), key="bot_interval_setting")
        else:
            auto_interval = st.session_state.get('game', {}).get('auto_interval', 8)

        st.markdown("---")
        st.markdown("### 试卷格式要求")
        st.markdown("""
        1. **题目**：以数字开头，如 `1. 什么是Python?`
        2. **选项**：以大写字母开头，如 `A. 编程语言`
        3. **答案**：单独一行，包含“答案”字样，如 `答案：A`
        """)
        
        if st.button("重置刷题状态"):
            if 'questions' in st.session_state:
                del st.session_state['questions']
            if 'submitted' in st.session_state:
                del st.session_state['submitted']
            if 'user_answers' in st.session_state:
                del st.session_state['user_answers']
            reset_game_state()
            # 清除所有答题记录
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith('q_') or k.startswith('disabled_')]
            for k in keys_to_clear:
                del st.session_state[k]
            st.rerun()

    # 处理上传文件
    if input_method == "上传文件" and uploaded_file is not None:
        if 'questions' not in st.session_state:
            try:
                questions = parse_docx(uploaded_file)
                if not questions:
                    st.error("未能解析出题目，请检查试卷格式。")
                else:
                    st.session_state['questions'] = questions
                    st.session_state['submitted'] = False
                    st.success(f"成功解析 {len(questions)} 道题目！")
            except Exception as e:
                st.error(f"解析文件时出错: {e}")
    
    # 处理粘贴文本
    if input_method == "粘贴文本" and parse_btn and pasted_text:
         try:
            questions = parse_text(pasted_text)
            if not questions:
                st.error("未能解析出题目，请检查文本格式。")
            else:
                st.session_state['questions'] = questions
                st.session_state['submitted'] = False
                st.success(f"成功解析 {len(questions)} 道题目！")
         except Exception as e:
            st.error(f"解析文本时出错: {e}")
    
    if 'questions' in st.session_state and st.session_state['questions']:
        questions = st.session_state['questions']
        
    if 'questions' in st.session_state and st.session_state['questions']:
        questions = st.session_state['questions']
        
        if mode == "考试模式":
            # 使用 form 包裹所有题目
            with st.form("quiz_form"):
                for idx, q in enumerate(questions):
                    # 过滤题目类型
                    if q['type'] not in selected_types:
                        continue

                    # 过滤错题
                    if show_errors and st.session_state.get('submitted'):
                        # 对于选择题和判断题，如果回答正确则跳过
                        if q['type'] in ['choice', 'judge']:
                            key = f"q_{idx}"
                            # 从持久化存储中获取答案
                            user_answers = st.session_state.get('user_answers', {})
                            user_choice = user_answers.get(key)
                            
                            user_choice_key = user_choice[0] if user_choice else None
                            if user_choice_key == q['answer'].strip():
                                continue
                        else:
                            # 对于主观题/填空题，因为无法自动判分，在“只看错题”模式下默认隐藏
                            # 或者您可以选择显示它们，这里选择隐藏以专注于明确的错误
                            continue

                    st.markdown(f"### 第 {q['id']} 题")
                    # 使用 HTML 增大字体
                    st.markdown(f"<div style='font-size: {font_size}px; font-weight: 500; margin-bottom: 10px;'>{q['content']}</div>", unsafe_allow_html=True)
                    
                    # 恢复用户的选择
                    key = f"q_{idx}"
                    
                    # 如果已经提交，显示正确/错误状态
                    if st.session_state.get('submitted'):
                        if q['type'] in ['choice', 'judge']:
                            options = [f"{k}. {v}" for k, v in q['options'].items()]
                            
                            # 从持久化存储中获取答案
                            user_answers = st.session_state.get('user_answers', {})
                            user_choice = user_answers.get(key)
                            
                            # 找出用户选了哪个选项的索引
                            index = None
                            if user_choice:
                                # user_choice 格式是 "A. 选项内容"
                                # 更稳健的获取 key 的方式：取第一个字符
                                choice_key = user_choice[0]
                                # 找到这个 key 在 options 列表中的位置
                                keys = list(q['options'].keys())
                                if choice_key in keys:
                                    index = keys.index(choice_key)
                            
                            st.radio("选择答案:", options, index=index, key=f"disabled_{idx}", disabled=True)
                            
                            correct_answer = q['answer'].strip() # 确保去除空格
                            user_choice_key = user_choice[0] if user_choice else None
                            
                            if user_choice_key == correct_answer:
                                st.success("✅ 回答正确")
                            else:
                                st.error(f"❌ 回答错误，正确答案是：{correct_answer}")
                        else:
                            # 主观题/填空题
                            # 从持久化存储中获取答案
                            user_answers = st.session_state.get('user_answers', {})
                            user_val = user_answers.get(key, "")
                            
                            st.text_area("您的回答:", value=user_val, key=f"disabled_{idx}", disabled=True)
                            st.info(f"参考答案：{q['answer']}")

                        st.markdown("---")
                        
                    else:
                        # 答题模式
                        if q['type'] in ['choice', 'judge']:
                            options = [f"{k}. {v}" for k, v in q['options'].items()]
                            st.radio("选择答案:", options, key=key, index=None)
                        else:
                            st.text_area("请输入答案:", key=key)
                        st.markdown("---")
                
                # 提交按钮 - 始终显示，但在提交后禁用或更改文本
                if not st.session_state.get('submitted'):
                    submitted = st.form_submit_button("提交试卷", on_click=save_answers)
                    if submitted:
                        st.session_state['submitted'] = True
                        st.rerun()
                else:
                    st.form_submit_button("试卷已提交", disabled=True)
            
            # 在表单外部显示“只重刷错题”按钮
            if st.session_state.get('submitted'):
                col1, col2 = st.columns([1, 4])
                with col1:
                    if st.button("🔄 只重刷错题"):
                        current_questions = st.session_state.get('questions', [])
                        incorrect_questions = []
                        debug_info = []
                        
                        for idx, q in enumerate(current_questions):
                            # 过滤题目类型 (只检查当前选中的题型，避免将未显示的题目误判为错题)
                            if q['type'] not in selected_types:
                                continue

                            # 获取用户答案
                            key = f"q_{idx}"
                            # 从持久化存储中获取答案
                            user_answers = st.session_state.get('user_answers', {})
                            user_choice = user_answers.get(key)
                            
                            # 判断逻辑：只针对客观题
                            if q['type'] in ['choice', 'judge']:
                                # 获取用户选择的 Key (A/B/C/D)
                                user_choice_key = user_choice[0] if user_choice else ""
                                user_choice_key = clean_answer_key(user_choice_key)
                                
                                # 获取正确答案 Key
                                correct_ans = clean_answer_key(q['answer'])
                                
                                if user_choice_key != correct_ans:
                                    incorrect_questions.append(q)
                                    debug_info.append(f"题号: {q['id']} | 你的答案: '{user_choice_key}' | 正确答案: '{correct_ans}' | 原始选择: '{user_choice}'")
                        
                        if incorrect_questions:
                            st.session_state['questions'] = incorrect_questions
                            st.session_state['submitted'] = False
                            # 清除所有答题记录，以便重刷
                            keys_to_clear = [k for k in st.session_state.keys() if k.startswith('q_') or k.startswith('disabled_')]
                            for k in keys_to_clear:
                                del st.session_state[k]
                            st.success(f"已筛选出 {len(incorrect_questions)} 道错题，开始重刷！")
                            
                            # 显示调试信息，帮助用户理解为什么被判错
                            with st.expander("查看判分详情 (Debug)"):
                                for info in debug_info:
                                    st.text(info)
                                    
                            if st.button("开始重刷"): # 增加一个确认按钮，让用户有机会看 debug 信息
                                st.rerun()
                        else:
                            st.warning("恭喜！没有发现客观题的错误。")
                
                st.info("点击侧边栏“重置刷题状态”可重新开始。")
        
        else:
            # 练习模式：不使用 form，实时反馈 + 大富翁游戏
            practice_questions = [(idx, q) for idx, q in enumerate(questions) if q['type'] in selected_types]
            if not practice_questions:
                st.info("当前筛选条件下没有题目可练习。")
                return

            game = init_game_state(len(practice_questions))
            if auto_interval:
                if auto_interval != game.get('auto_interval'):
                    game['auto_interval'] = auto_interval
                    game['bot_next_roll'] = time.time() + auto_interval
                else:
                    game['auto_interval'] = auto_interval

            # 自动刷新以驱动机器人
            schedule_auto_refresh(game['auto_interval'])
            handle_bot_autoplay(game)

            # CSS 样式：固定右侧游戏窗口
            st.markdown("""
                <style>
                /* 针对大富翁游戏区域的列进行固定 */
                div[data-testid="stHorizontalBlock"] > div:nth-of-type(2) {
                    position: sticky;
                    top: 4rem;
                    align-self: start;
                    z-index: 99;
                    background-color: white; /* 添加背景色防止透明 */
                    padding: 10px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.05); /* 添加阴影增加立体感 */
                }
                
                /* 修复深色模式下，强制白底后的文字颜色问题 */
                div[data-testid="stHorizontalBlock"] > div:nth-of-type(2) h3,
                div[data-testid="stHorizontalBlock"] > div:nth-of-type(2) span,
                div[data-testid="stHorizontalBlock"] > div:nth-of-type(2) p,
                div[data-testid="stHorizontalBlock"] > div:nth-of-type(2) div[data-testid="stMetricLabel"],
                div[data-testid="stHorizontalBlock"] > div:nth-of-type(2) div[data-testid="stMetricValue"] {
                    color: #31333F !important;
                }
                div[data-testid="stHorizontalBlock"] > div:nth-of-type(2) div[data-testid="stCaptionContainer"] {
                    color: #666666 !important;
                }
                </style>
            """, unsafe_allow_html=True)

            col_questions, col_game = st.columns([3, 2])

            with col_questions:
                for idx, q in practice_questions:
                    st.markdown(f"### 第 {q['id']} 题")
                    st.markdown(f"<div style='font-size: {font_size}px; font-weight: 500; margin-bottom: 10px;'>{q['content']}</div>", unsafe_allow_html=True)
                    key = f"q_{idx}"

                    if q['type'] in ['choice', 'judge']:
                        options = [f"{k}. {v}" for k, v in q['options'].items()]
                        st.radio("选择答案:", options, key=key, index=None)
                        user_choice = st.session_state.get(key)
                        if user_choice:
                            user_choice_key = clean_answer_key(user_choice[0])
                            correct_ans = clean_answer_key(q['answer'])
                            game['answered_questions'].add(idx)
                            if user_choice_key == correct_ans:
                                st.success("✅ 回答正确")
                                if idx not in game['rewarded_questions']:
                                    player_reward_turn(game, "答对一题")
                                    game['rewarded_questions'].add(idx)
                            else:
                                st.error(f"❌ 回答错误，正确答案是：{q['answer']}")
                    else:
                        st.text_area("请输入答案:", key=key)
                        user_val = st.session_state.get(key)
                        if user_val:
                            st.info(f"参考答案：{q['answer']}")
                            game['answered_questions'].add(idx)

                    st.markdown("---")

            with col_game:
                st.subheader("🎲 大富翁对战")
                st.caption("答对题目可掷骰前进；人机将按设定时间自动抢分。")
                
                # 使用 empty 占位符，确保可以在逻辑处理完后更新最新的积分
                score_board = st.empty()
                
                board_placeholder = st.empty()
                
                # 动画逻辑
                anim_speed = 0.15
                
                # 检查玩家移动
                if game['prev_player_pos'] != game['player_pos']:
                    start = game['prev_player_pos']
                    end = game['player_pos']
                    # 处理跨越终点的情况
                    if end < start: end += game['board_size']
                    
                    # 逐步显示移动过程
                    for i in range(start + 1, end + 1):
                        curr = i % game['board_size']
                        board_placeholder.markdown(render_board_html(game, current_player_pos=curr, current_bot_pos=game['prev_bot_pos']), unsafe_allow_html=True)
                        time.sleep(anim_speed)
                    
                    game['prev_player_pos'] = game['player_pos']
                
                # 检查人机移动
                elif game['prev_bot_pos'] != game['bot_pos']:
                    start = game['prev_bot_pos']
                    end = game['bot_pos']
                    if end < start: end += game['board_size']
                    
                    for i in range(start + 1, end + 1):
                        curr = i % game['board_size']
                        board_placeholder.markdown(render_board_html(game, current_player_pos=game['player_pos'], current_bot_pos=curr), unsafe_allow_html=True)
                        time.sleep(anim_speed)
                        
                    game['prev_bot_pos'] = game['bot_pos']
                
                else:
                    # 无移动，直接渲染
                    board_placeholder.markdown(render_board_html(game), unsafe_allow_html=True)

                # 在动画结束后更新积分板，确保显示最新积分
                with score_board.container():
                    score_cols = st.columns(2)
                    with score_cols[0]:
                        st.metric("你的积分", game['player_score'])
                    with score_cols[1]:
                        st.metric("人机积分", game['bot_score'])

                if game['messages']:
                    st.markdown("**最新动态**")
                    for msg in game['messages']:
                        st.write(msg)

            # 结算排名
            answered_count = len(game['answered_questions'])
            if answered_count >= len(practice_questions):
                standings = sorted([
                    ("你", game['player_score']),
                    ("人机", game['bot_score'])
                ], key=lambda x: x[1], reverse=True)
                rank_text = " | ".join([f"第{i+1}名：{name} ({score} 分)" for i, (name, score) in enumerate(standings)])
                st.success(f"全部题目完成！最终排名：{rank_text}")

if __name__ == "__main__":
    main()
