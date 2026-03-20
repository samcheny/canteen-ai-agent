import streamlit as st
import pandas as pd
from utils import load_data_from_db, analyze_nutrition, check_allergies, get_ai_suggestions, agent_process, parse_recipe_excel, save_recipes_to_db, clean_ingredient_name
import sqlite3

# --- Page Config ---
st.set_page_config(page_title="杨绫食堂AI营养师", layout="wide")

# --- App Title ---
st.title(" 杨绫食堂 AI 营养师系统")
st.markdown("---")

# --- Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "df_recipes" not in st.session_state:
    st.session_state.df_recipes = None
if "df_students" not in st.session_state:
    st.session_state.df_students = None
if "df_nutrition" not in st.session_state:
    st.session_state.df_nutrition = None

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ 数据源管理")
    source_type = st.radio("选择数据源", ["数据库", "上传 Excel 文件"])
    
    if source_type == "上传 Excel 文件":
        st.subheader("📁 上传菜谱数据")
        uploaded_file = st.file_uploader("上传 Excel 文件 (配餐方案格式)", type=["xlsx"])
        if uploaded_file:
            # ... (existing recipe upload logic) ...
            try:
                with open("temp_upload.xlsx", "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                recipes = parse_recipe_excel("temp_upload.xlsx")
                if recipes:
                    # ... (existing recipe parsing and check logic) ...
                    upload_dates = {r['date'] for r in recipes}
                    conn = sqlite3.connect('canteen.db')
                    existing_dates = pd.read_sql_query("SELECT DISTINCT date FROM recipes", conn)['date'].tolist()
                    conn.close()
                    
                    duplicates = upload_dates.intersection(set(existing_dates))
                    
                    can_proceed = True
                    if duplicates:
                        st.warning(f"⚠️ 检测到以下日期在数据库中已存在数据: {', '.join(sorted(list(duplicates)))}")
                        overwrite = st.checkbox("确定要覆盖这些日期的数据吗？", value=False)
                        if not overwrite:
                            can_proceed = False
                            if st.button("取消上传"):
                                st.rerun() 
                        else:
                            st.info("💡 点击下方按钮开始覆盖导入")

                    if can_proceed:
                        if st.button("开始导入菜谱数据") if duplicates else True:
                            with st.status("正在处理菜谱 Excel 文件...", expanded=True) as status:
                                if duplicates:
                                    conn = sqlite3.connect('canteen.db')
                                    cursor = conn.cursor()
                                    for d in duplicates:
                                        cursor.execute("DELETE FROM recipes WHERE date = ?", (d,))
                                    conn.commit()
                                    conn.close()
                                    status.update(label="已清理旧数据，准备插入新数据...", state="running")

                                failed_ings = save_recipes_to_db(recipes, status_callback=status.update)
                                status.update(label="菜谱数据处理完成！", state="complete", expanded=False)
                                
                                if failed_ings:
                                    st.warning(f"⚠️ 导入完成，但发现 {len(failed_ings)} 种食材缺少营养数据：{', '.join(failed_ings)}")
                                    st.info("已自动生成/更新 `missing_nutrition_data.xlsx`。请在下方补全入口手动补充。")
                                else:
                                    st.success(f"成功导入 {len(recipes)} 条菜谱数据，并已同步营养库。")
                                
                                df_recipes, df_students, df_nutrition = load_data_from_db()
                                st.session_state.df_recipes = df_recipes
                                st.session_state.df_students = df_students
                                st.session_state.df_nutrition = df_nutrition
                else:
                    st.error("无法解析 Excel 文件，请检查格式是否正确。")
            except Exception as e:
                st.error(f"处理失败: {e}")
        
        st.markdown("---")
        st.subheader("👥 上传学生数据")
        uploaded_students = st.file_uploader("上传学生信息 Excel (班级, 姓名, 过敏原, 身高, 体重)", type=["xlsx"], key="student_uploader")
        if uploaded_students:
            try:
                df_stu_upload = pd.read_excel(uploaded_students)
                required_stu_cols = {'班级', '姓名', '过敏原', '身高', '体重'}
                if required_stu_cols.issubset(df_stu_upload.columns):
                    if st.button("确认导入学生数据"):
                        conn = sqlite3.connect('canteen.db')
                        cursor = conn.cursor()
                        # Clear existing students for fresh import or handle as needed
                        # Here we clear and replace to keep it simple as requested
                        cursor.execute("DELETE FROM students")
                        
                        stu_data_to_import = []
                        for _, row in df_stu_upload.iterrows():
                            if pd.notna(row['姓名']):
                                stu_data_to_import.append((
                                    str(row['班级']).strip(),
                                    str(row['姓名']).strip(),
                                    str(row['过敏原']).strip() if pd.notna(row['过敏原']) else '',
                                    float(row['身高']) if pd.notna(row['身高']) else 0.0,
                                    float(row['体重']) if pd.notna(row['体重']) else 0.0
                                ))
                        
                        cursor.executemany('''
                            INSERT INTO students (class_name, student_name, allergen, height, weight)
                            VALUES (?, ?, ?, ?, ?)
                        ''', stu_data_to_import)
                        conn.commit()
                        conn.close()
                        st.success(f"✅ 成功导入 {len(stu_data_to_import)} 名学生信息！")
                        # Reload data
                        _, df_students, _ = load_data_from_db()
                        st.session_state.df_students = df_students
                        st.rerun()
                else:
                    st.error("上传的文件格式不正确，请确保包含所需的列：班级, 姓名, 过敏原, 身高, 体重。")
            except Exception as e:
                st.error(f"学生数据导入失败: {e}")
        st.markdown("---")

    # --- Date Selection (Shared by both modes) ---
    st.subheader("📅 选择分析日期")
    conn = sqlite3.connect('canteen.db')
    try:
        available_dates_str = pd.read_sql_query("SELECT DISTINCT date FROM recipes", conn)['date'].tolist()
    except:
        available_dates_str = []
    conn.close()
    
    # Initialize selected_date
    selected_date = None
    
    # Convert strings to datetime.date objects for calendar filtering
    available_dates = []
    for d in available_dates_str:
        try:
            if '-' in d:
                available_dates.append(pd.to_datetime(d).date())
            else:
                available_dates.append(pd.to_datetime(d, format='%Y%m%d').date())
        except:
            continue
    
    if available_dates:
        min_date = min(available_dates)
        max_date = max(available_dates)
        
        selected_date_obj = st.date_input(
            "选择具体日期进行分析",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            help="只能选择数据库中已有的日期"
        )
        
        # Convert back to string to match DB format (YYYY-MM-DD)
        selected_date = selected_date_obj.strftime('%Y-%m-%d')
        
        # Check if selected date actually has data
        if selected_date_obj not in available_dates:
            st.error("⚠️ 该日期暂无菜谱数据")
            selected_date = None
        
        if st.button("加载该日期数据") and selected_date:
            df_recipes, df_students, df_nutrition = load_data_from_db(selected_date)
            st.session_state.df_recipes = df_recipes
            st.session_state.df_students = df_students
            st.session_state.df_nutrition = df_nutrition
            st.success(f"已加载 {selected_date} 的数据！")
    else:
        st.warning("数据库中暂无数据，请先上传 Excel 文件。")

    # --- Manual Student Entry ---
    st.markdown("---")
    st.subheader("👤 手动添加学生")
    with st.expander("点击展开添加表单"):
        with st.form("manual_student_form", clear_on_submit=True):
            new_class = st.text_input("班级", placeholder="如：一年级一班")
            new_name = st.text_input("姓名")
            new_allergen = st.text_input("过敏原", placeholder="如有多个请用逗号隔开")
            col_h, col_w = st.columns(2)
            with col_h:
                new_height = st.number_input("身高 (cm)", min_value=0.0, step=0.1)
            with col_w:
                new_weight = st.number_input("体重 (kg)", min_value=0.0, step=0.1)
            
            if st.form_submit_button("添加学生"):
                if new_name and new_class:
                    conn = sqlite3.connect('canteen.db')
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO students (class_name, student_name, allergen, height, weight)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (new_class, new_name, new_allergen, new_height, new_weight))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ 学生 {new_name} 已成功添加！")
                    # Reload students
                    _, df_students, _ = load_data_from_db()
                    st.session_state.df_students = df_students
                    st.rerun()
                else:
                    st.error("❌ 姓名和班级为必填项！")

    # --- Student Selection for AI Analysis ---
    st.markdown("---")
    st.subheader("🎯 体质分析对象")
    if st.session_state.df_students is not None and not st.session_state.df_students.empty:
        student_names = ["全部学生 (普适建议)"] + sorted(st.session_state.df_students['student_name'].tolist())
        selected_student = st.selectbox(
            "选择学生进行个性化分析",
            options=student_names,
            index=0,
            help="选中特定学生后，AI 将根据其身高体重提供针对性的饮食建议。"
        )
        st.session_state.selected_student = None if selected_student == "全部学生 (普适建议)" else selected_student
    else:
        st.info("暂无学生数据，请先上传或手动添加。")
        st.session_state.selected_student = None

    # --- Manual Nutrition Entry ---
    if st.session_state.df_recipes is not None:
        st.markdown("---")
        st.subheader("📝 补全食材营养")
        
        # Check for missing ingredients with fuzzy matching
        conn = sqlite3.connect('canteen.db')
        all_ings_raw = set()
        for ings_str in st.session_state.df_recipes['ingredients']:
            all_ings_raw.update([i.strip() for i in ings_str.split(',') if i.strip()])
        
        # All ingredients in recipes cleaned
        all_ings_cleaned = {clean_ingredient_name(i) for i in all_ings_raw}
        
        # All known ingredients in nutrition library cleaned
        known_ings_raw = pd.read_sql_query("SELECT ingredient FROM nutrition", conn)['ingredient'].tolist()
        known_ings_cleaned = {clean_ingredient_name(i) for i in known_ings_raw}
        
        missing_ings = sorted(list(all_ings_cleaned - known_ings_cleaned))
        conn.close()
        
        if missing_ings:
            st.warning(f"检测到 {len(missing_ings)} 种食材缺少数据 (模糊匹配已开启)")
            
            # --- Added: Batch Import Option ---
            st.markdown("### 📥 批量补全营养数据")
            # Create a template for download
            missing_df = pd.DataFrame({
                'ingredient': missing_ings,
                'protein': [0.0]*len(missing_ings),
                'fat': [0.0]*len(missing_ings),
                'carb': [0.0]*len(missing_ings),
                'calorie': [0.0]*len(missing_ings),
                'fiber': [0.0]*len(missing_ings),
                'vit_c': [0.0]*len(missing_ings)
            })
            
            # Use Excel to download
            import io
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                missing_df.to_excel(writer, index=False, sheet_name='MissingData')
            processed_data = output.getvalue()
            
            st.download_button(
                label="📥 下载缺失数据模板 (Excel)",
                data=processed_data,
                file_name='missing_nutrition_template.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
            uploaded_missing = st.file_uploader("上传补全后的模板文件", type=["xlsx"], key="missing_uploader")
            if uploaded_missing:
                try:
                    df_upload = pd.read_excel(uploaded_missing)
                    # Simple validation
                    required_cols = {'ingredient', 'protein', 'fat', 'carb', 'calorie', 'fiber', 'vit_c'}
                    if required_cols.issubset(df_upload.columns):
                        if st.button("确认批量导入"):
                            conn = sqlite3.connect('canteen.db')
                            cursor = conn.cursor()
                            data_to_import = []
                            for _, row in df_upload.iterrows():
                                # Only import if name is not empty
                                if pd.notna(row['ingredient']):
                                    data_to_import.append((
                                        str(row['ingredient']).strip(),
                                        float(row['protein']) if pd.notna(row['protein']) else 0.0,
                                        float(row['fat']) if pd.notna(row['fat']) else 0.0,
                                        float(row['carb']) if pd.notna(row['carb']) else 0.0,
                                        float(row['calorie']) if pd.notna(row['calorie']) else 0.0,
                                        float(row['fiber']) if pd.notna(row['fiber']) else 0.0,
                                        float(row['vit_c']) if pd.notna(row['vit_c']) else 0.0
                                    ))
                            
                            cursor.executemany('''
                                INSERT OR REPLACE INTO nutrition (ingredient, protein, fat, carb, calorie, fiber, vit_c)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', data_to_import)
                            conn.commit()
                            conn.close()
                            st.success(f"✅ 成功批量导入 {len(data_to_import)} 条数据！")
                            st.rerun()
                    else:
                        st.error("上传的文件格式不正确，请确保包含所需的列。")
                except Exception as e:
                    st.error(f"批量导入失败: {e}")

            st.markdown("---")
            st.markdown("### ✍️ 单个手动补全")
            selected_ing = st.selectbox("选择要补全的食材", missing_ings)
            
            with st.form("nutrition_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    protein = st.number_input("蛋白质 (g/100g)", min_value=0.0, step=0.1)
                    fat = st.number_input("脂肪 (g/100g)", min_value=0.0, step=0.1)
                    carb = st.number_input("碳水 (g/100g)", min_value=0.0, step=0.1)
                with col2:
                    calorie = st.number_input("热量 (kcal/100g)", min_value=0.0, step=1.0)
                    fiber = st.number_input("纤维 (g/100g)", min_value=0.0, step=0.1)
                    vit_c = st.number_input("维C (mg/100g)", min_value=0.0, step=0.1)
                
                if st.form_submit_button("保存营养数据"):
                    conn = sqlite3.connect('canteen.db')
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO nutrition (ingredient, protein, fat, carb, calorie, fiber, vit_c)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (selected_ing, protein, fat, carb, calorie, fiber, vit_c))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ {selected_ing} 数据已保存！")
                    # Force reload data
                    df_recipes, df_students, df_nutrition = load_data_from_db(selected_date)
                    st.session_state.df_nutrition = df_nutrition
                    st.rerun()
        else:
            st.success("✨ 所有食材营养数据已补全")

    # Data Preview (Hidden as requested)
    # if st.session_state.df_recipes is not None:
    #     st.markdown("---")
    #     st.subheader("📊 数据预览")
    #     with st.expander("当前菜谱 (Recipes)"):
    #         st.dataframe(st.session_state.df_recipes, use_container_width=True)
    #     with st.expander("学生信息 (Students)"):
    #         st.dataframe(st.session_state.df_students, use_container_width=True)
    #     with st.expander("营养库 (Nutrition)"):
    #         st.dataframe(st.session_state.df_nutrition, use_container_width=True)

# --- Chat Interface ---
st.subheader("💬 AI 营养咨询")

# CSS for compact prompt buttons (chips) and fixed positioning
st.markdown("""
<style>
    /* 1. 基础按钮样式 (Chips) */
    .stButton > button {
        border-radius: 20px !important;
        background-color: #f8f9fb !important;
        color: #31333f !important;
        border: 1px solid #d1d4dc !important;
        padding: 0.1rem 0.8rem !important;
        font-size: 0.85rem !important;
        height: auto !important;
        min-height: 0 !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button:hover {
        border-color: #ff4b4b !important;
        color: #ff4b4b !important;
        background-color: white !important;
        box-shadow: 0 4px 8px rgba(255,75,75,0.1) !important;
        transform: translateY(-1px);
    }
    
    /* 2. 强制将按钮所在的列容器固定在视口底部 */
    /* 我们使用 data-testid 来精准定位按钮所在的行 */
    [data-testid="stHorizontalBlock"]:has(button[key="btn_nut"]) {
        position: fixed !important;
        bottom: 100px !important; /* 紧贴聊天框上方 */
        left: 50% !important;
        transform: translateX(-50%) !important;
        z-index: 1000000 !important; /* 极高优先级，确保在所有层级之上 */
        background-color: rgba(255, 255, 255, 0.8) !important; /* 半透明背景，磨砂玻璃效果 */
        backdrop-filter: blur(10px) !important;
        padding: 10px 20px !important;
        border-radius: 15px !important;
        width: auto !important;
        min-width: 300px !important;
        display: flex !important;
        justify-content: center !important;
        gap: 10px !important;
        box-shadow: 0 -5px 15px rgba(0,0,0,0.03) !important;
    }

    /* 3. 响应式：在侧边栏展开时自动偏移 */
    @media (min-width: 992px) {
        [data-testid="stHorizontalBlock"]:has(button[key="btn_nut"]) {
            /* 这里的偏移需要根据 Streamlit 侧边栏宽度微调，通常居中即可 */
            margin-left: 0; 
        }
    }

    /* 4. 优化消息列表底部间距，防止内容被遮挡 */
    .stChatMessageContainer {
        padding-bottom: 150px !important;
    }
    
    /* 隐藏按钮容器原有的默认边距 */
    [data-testid="stHorizontalBlock"]:has(button[key="btn_nut"]) div[data-testid="stVerticalBlock"] {
        padding: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# Container for messages to ensure buttons stay at the bottom
chat_container = st.container()

with chat_container:
    # Display historical messages
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message.get("type") == "comprehensive":
                st.subheader("📊 综合营养评估报告")
                # 1. Nutrition Analysis
                # Show per-dish table first if exists
                if message["nutrition"].get("table") is not None:
                    st.markdown("#### 🍱 各菜品营养明细")
                    st.dataframe(message["nutrition"]["table"], use_container_width=True)
                
                st.markdown(message["nutrition"]["text"])
                for j, chart in enumerate(message["nutrition"].get("charts", [])):
                    st.plotly_chart(chart, use_container_width=True, key=f"hist_nut_{i}_{j}")
                # 2. Allergy Check
                st.markdown(f"### ⚠️ 过敏风险提示\n{message['allergy']['text']}")
                if message['allergy'].get("table") is not None:
                    st.dataframe(message["allergy"]["table"], use_container_width=True)
                # 3. AI Suggestions
                st.markdown(message["suggestions"]["text"])
            else:
                st.markdown(message.get("content", ""))
                if "table" in message and message["table"] is not None:
                    # Show per-dish table for regular nutrition analysis
                    if message["role"] == "assistant" and "蛋白质" in str(message.get("content", "")):
                        st.markdown("#### 🍱 各菜品营养明细")
                    st.dataframe(message["table"], use_container_width=True)
                if "charts" in message:
                    for j, chart in enumerate(message["charts"]):
                        st.plotly_chart(chart, use_container_width=True, key=f"hist_{i}_{j}")

    # --- Welcome Message (if no messages) ---
    if not st.session_state.messages:
        with st.chat_message("assistant"):
            st.markdown("""
            👋 您好！我是您的智慧食堂 AI 营养师。
            
            请先在左侧**加载数据库数据**或**上传 Excel 文件**。
            我可以帮您：
            1.  **📊 营养分析**：计算对应日期菜谱的热量及各类营养素。
            2.  **⚠️ 过敏检查**：快速识别对某些食材过敏的学生风险。
            3.  **💡 改进建议**：基于当前营养数据，由 DOUBAO 提供专业饮食建议。
            4.  **📑 综合分析**：一次性完成上述所有分析并按顺序展示。
            
            您可以直接点击下方的快捷提示或在对话框中输入需求。
            """)

# --- Chat Input Area ---
# Show quick prompt buttons above input
prompt_cols = st.columns([1.8, 1.5, 6])
with prompt_cols[0]:
    if st.button("📊 分析对应日期营养", key="btn_nut"):
        st.session_state.pending_prompt = "分析对应日期营养"
with prompt_cols[1]:
    if st.button("⚠️ 检查过敏风险", key="btn_all"):
        st.session_state.pending_prompt = "检查过敏风险"

# Chat input
input_prompt = st.chat_input("您可以问我：'分析对应日期营养'、'检查过敏风险' 或 '给出改进建议'")
if input_prompt:
    st.session_state.pending_prompt = input_prompt

# Process the prompt if it exists in session state
if "pending_prompt" in st.session_state:
    prompt = st.session_state.pending_prompt
    del st.session_state.pending_prompt
    
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Rerun to show user message immediately and then process
    # (Actually, in Streamlit, it will continue executing. Let's process it here.)
    
    with chat_container:
        with st.chat_message("user"):
            st.markdown(prompt)

        # Process by AI / Agent
        if st.session_state.df_recipes is None:
            response_text = "❌ 请先在侧边栏加载或上传数据！"
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            with st.chat_message("assistant"):
                st.markdown(response_text)
        else:
            with st.chat_message("assistant"):
                # Call agent logic from utils
                with st.spinner("AI 正在分析中..."):
                    # Get selected student name from session state
                    selected_student_name = st.session_state.get("selected_student")
                    
                    result = agent_process(
                        prompt, 
                        st.session_state.df_recipes, 
                        st.session_state.df_students, 
                        st.session_state.df_nutrition,
                        selected_student_name=selected_student_name
                    )
                
                if result.get("type") == "comprehensive":
                    st.subheader("📊 综合营养评估报告")
                    # 1. Nutrition Analysis
                    # Show per-dish table first
                    if result["nutrition"].get("table") is not None:
                        st.markdown("#### 🍱 各菜品营养明细")
                        st.dataframe(result["nutrition"]["table"], use_container_width=True)
                    
                    st.markdown(result["nutrition"]["text"])
                    for j, chart in enumerate(result["nutrition"].get("charts", [])):
                        st.plotly_chart(chart, use_container_width=True, key=f"new_nut_{len(st.session_state.messages)}_{j}")
                    # 2. Allergy Check
                    st.markdown(f"### ⚠️ 过敏风险提示\n{result['allergy']['text']}")
                    if result['allergy'].get("table") is not None:
                        st.dataframe(result["allergy"]["table"], use_container_width=True)
                    # 3. AI Suggestions
                    st.markdown(result["suggestions"]["text"])
                    
                    # Save as comprehensive type
                    msg_data = {"role": "assistant", "type": "comprehensive", **result}
                else:
                    # Display text response
                    st.markdown(result["text"])
                    
                    # Display charts if any
                    charts = result.get("charts", [])
                    if "chart" in result and result["chart"] is not None:
                        charts.append(result["chart"])
                    
                    for k, chart in enumerate(charts):
                        st.plotly_chart(chart, use_container_width=True, key=f"new_{len(st.session_state.messages)}_{k}")
                    
                    # Display table if any
                    table = result.get("table")
                    if table is not None:
                        st.dataframe(table, use_container_width=True)
                    
                    # Save assistant response
                    msg_data = {"role": "assistant", "content": result["text"]}
                    if charts:
                        msg_data["charts"] = charts
                    if table is not None:
                        msg_data["table"] = table
                
                st.session_state.messages.append(msg_data)
                st.rerun() # Refresh to update chat container properly
