import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import os
import time
from dotenv import load_dotenv
from zhipuai import ZhipuAI

load_dotenv()

# Initialize ZhipuAI client
client = ZhipuAI(api_key=os.getenv("ZHIPUAI_API_KEY"))

import re

def clean_ingredient_name(name):
    """
    Cleans ingredient name for better matching and AI lookup.
    Example: '豆腐(南)' -> '豆腐', '鸡蛋(均值)' -> '鸡蛋'
    """
    # Remove content in brackets and common suffixes
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'（.*?）', '', name)
    # Remove trailing '肉', '仁', '片', '丝' if preceded by something
    # But keep '牛肉', '猪肉'
    if len(name) > 2:
        name = re.sub(r'(?<!牛|猪)肉$', '', name)
        name = re.sub(r'仁$', '', name)
    return name.strip()

def get_db_connection(db_path='canteen.db'):
    return sqlite3.connect(db_path)

def parse_recipe_excel(file_path):
    """
    Parses the complex 'recipe1.xlsx' format.
    Returns a list of dictionaries with recipe info.
    """
    df = pd.read_excel(file_path)
    
    # Identify data rows (skipping headers)
    # The header is actually around row 0 or 1.
    # We look for where "日期" is.
    header_row_idx = -1
    for i, row in df.iterrows():
        if "日期" in str(row.values):
            header_row_idx = i
            break
    
    if header_row_idx == -1:
        return []

    # Rename columns based on header row
    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    recipes = []
    current_date = None
    current_meal = None
    
    for _, row in df.iterrows():
        # Update current date and meal if they exist in this row
        date_val = str(row.get('日期', 'nan')).strip()
        if date_val != 'nan' and date_val != 'None':
            current_date = date_val.split(' ')[0] # e.g. "2026-03-09"
        
        meal_val = str(row.get('餐点', 'nan')).strip()
        if meal_val != 'nan' and meal_val != 'None':
            current_meal = meal_val
            
        dish_name = str(row.get('套餐', 'nan')).strip()
        ingredients_str = str(row.get('食材组成', 'nan')).strip()
        
        if dish_name != 'nan' and dish_name != 'None' and ingredients_str != 'nan' and ingredients_str != 'None':
            # Example ingredients_str: "西芹54g/虾仁肉72g/腰果11g/辣椒(红，小)4g"
            parts = ingredients_str.split('/')
            ing_list = []
            gram_list = []
            
            import re
            for p in parts:
                # Regex to split name and grams (e.g. "西芹54g")
                match = re.search(r'([^\d]+)(\d+(\.\d+)?)g', p)
                if match:
                    raw_ing_name = match.group(1).strip()
                    ing_name = clean_ingredient_name(raw_ing_name) # Cleaned name for DB and analysis
                    ing_grams = match.group(2).strip()
                    ing_list.append(ing_name)
                    gram_list.append(ing_grams)
            
            if ing_list:
                recipes.append({
                    'name': dish_name,
                    'date': current_date,
                    'meal': current_meal,
                    'ingredients': ','.join(ing_list),
                    'grams': ','.join(gram_list)
                })
    
    return recipes

def save_recipes_to_db(recipes, status_callback=None):
    """
    Saves recipes and updates nutrition table using AI if needed.
    Returns a list of ingredients that AI failed to find.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Save recipes
    if status_callback: status_callback(label="正在保存菜谱数据...")
    for r in recipes:
        cursor.execute('''
            INSERT INTO recipes (name, date, meal, ingredients, grams)
            VALUES (?, ?, ?, ?, ?)
        ''', (r['name'], r['date'], r['meal'], r['ingredients'], r['grams']))
    conn.commit() # Commit recipes first so they are visible even if nutrition lookup takes time
    
    # 2. Collect all unique ingredients from the recipes
    all_ings = set()
    for r in recipes:
        ings = [i.strip() for i in r['ingredients'].split(',') if i.strip()]
        all_ings.update(ings)
    
    # 3. Filter for unknown ingredients
    df_nut = pd.read_sql_query("SELECT ingredient FROM nutrition", conn)
    known_ingredients = set(df_nut['ingredient'].tolist())
    
    # Apply fuzzy matching for missing check
    unknown_ingredients = set()
    known_cleaned = {clean_ingredient_name(k) for k in known_ingredients}
    for ing in all_ings:
        if clean_ingredient_name(ing) not in known_cleaned:
            unknown_ingredients.add(ing)
    
    failed_ingredients = list(unknown_ingredients)
    
    if failed_ingredients:
        if status_callback: status_callback(label=f"发现 {len(failed_ingredients)} 种食材缺少营养数据，请在侧边栏手动补充。")
        print(f"Found {len(failed_ingredients)} ingredients with missing data.")
    
    conn.close()
    
    # 5. Update missing_nutrition_data.xlsx if there are failed ingredients
    if failed_ingredients:
        try:
            missing_df = pd.DataFrame({
                'ingredient': failed_ingredients,
                'protein': 0.0,
                'fat': 0.0,
                'carb': 0.0,
                'calorie': 0.0,
                'fiber': 0.0,
                'vit_c': 0.0
            })
            missing_df.to_excel('missing_nutrition_data.xlsx', index=False)
        except Exception as e:
            print(f"Failed to update missing_nutrition_data.xlsx: {e}")

    if status_callback: status_callback(label="数据库同步完成！")
    print("Database sync complete.")
    return failed_ingredients

def load_data_from_db(date=None):
    conn = get_db_connection()
    query = "SELECT * FROM recipes"
    if date:
        query += f" WHERE date = '{date}'"
    df_recipes = pd.read_sql_query(query, conn)
    df_students = pd.read_sql_query("SELECT * FROM students", conn)
    df_nutrition = pd.read_sql_query("SELECT * FROM nutrition", conn)
    conn.close()
    return df_recipes, df_students, df_nutrition

def analyze_nutrition(df_recipes, df_nutrition):
    total_nutrition = {
        'protein': 0,
        'fat': 0,
        'carb': 0,
        'calorie': 0,
        'fiber': 0,
        'vit_c': 0
    }
    
    # Pre-process nutrition for fast lookup using CLEANED names as keys
    nutrition_map = {}
    for _, row in df_nutrition.iterrows():
        cleaned_key = clean_ingredient_name(row['ingredient'])
        nutrition_map[cleaned_key] = row.to_dict()

    # Data list for per-dish nutrition table
    dish_nutrition_list = []

    for _, row in df_recipes.iterrows():
        dish_name = row['name']
        meal_type = row.get('meal', '未知')
        ingredients = row['ingredients'].split(',')
        grams = row['grams'].split(',')
        
        dish_nut = {
            '餐点': meal_type,
            '菜品名称': dish_name,
            '热量 (kcal)': 0.0,
            '蛋白质 (g)': 0.0,
            '脂肪 (g)': 0.0,
            '碳水 (g)': 0.0,
            '纤维 (g)': 0.0,
            '维C (mg)': 0.0
        }

        for ing, g in zip(ingredients, grams):
            ing_cleaned = clean_ingredient_name(ing.strip())
            try:
                g = float(g)
            except:
                continue
                
            if ing_cleaned in nutrition_map:
                nut = nutrition_map[ing_cleaned]
                # Update dish nutrition
                dish_nut['蛋白质 (g)'] += nut['protein'] * (g / 100)
                dish_nut['脂肪 (g)'] += nut['fat'] * (g / 100)
                dish_nut['碳水 (g)'] += nut['carb'] * (g / 100)
                dish_nut['热量 (kcal)'] += nut['calorie'] * (g / 100)
                dish_nut['纤维 (g)'] += nut['fiber'] * (g / 100)
                dish_nut['维C (mg)'] += nut['vit_c'] * (g / 100)

        # Round values for table
        for key in ['热量 (kcal)', '蛋白质 (g)', '脂肪 (g)', '碳水 (g)', '纤维 (g)', '维C (mg)']:
            dish_nut[key] = round(dish_nut[key], 2)
            
        dish_nutrition_list.append(dish_nut)

        # Update total nutrition
        total_nutrition['protein'] += dish_nut['蛋白质 (g)']
        total_nutrition['fat'] += dish_nut['脂肪 (g)']
        total_nutrition['carb'] += dish_nut['碳水 (g)']
        total_nutrition['calorie'] += dish_nut['热量 (kcal)']
        total_nutrition['fiber'] += dish_nut['纤维 (g)']
        total_nutrition['vit_c'] += dish_nut['维C (mg)']

    # Create DataFrame for per-dish nutrition
    df_dish_nutrition = pd.DataFrame(dish_nutrition_list)

    # Hide the meal column when showing per-dish nutrition details
    if '餐点' in df_dish_nutrition.columns:
        df_dish_nutrition = df_dish_nutrition.drop(columns=['餐点'])

    # 1. Text Summary
    summary = f"""
    ### 营养分析结果
    - **总能量**: {total_nutrition['calorie']:.2f} kcal
    - **蛋白质**: {total_nutrition['protein']:.2f} g
    - **脂肪**: {total_nutrition['fat']:.2f} g
    - **碳水化合物**: {total_nutrition['carb']:.2f} g
    - **膳食纤维**: {total_nutrition['fiber']:.2f} g
    - **维生素C**: {total_nutrition['vit_c']:.2f} mg
    """

    # 2. Charts
    # Pie chart: Energy source
    # Energy: Protein 4kcal/g, Fat 9kcal/g, Carb 4kcal/g
    energy_data = {
        '来源': ['蛋白质', '脂肪', '碳水'],
        '能量 (kcal)': [
            total_nutrition['protein'] * 4,
            total_nutrition['fat'] * 9,
            total_nutrition['carb'] * 4
        ]
    }
    fig_pie = px.pie(energy_data, values='能量 (kcal)', names='来源', title='热量来源分布')

    # Core nutrition bar chart with different colors per nutrient
    nut_comp = {
        '营养素': ['蛋白质', '脂肪', '碳水', '膳食纤维'],
        '含量 (g)': [
            total_nutrition['protein'],
            total_nutrition['fat'],
            total_nutrition['carb'],
            total_nutrition['fiber']
        ]
    }
    fig_bar = px.bar(
        nut_comp,
        x='营养素',
        y='含量 (g)',
        color='营养素',
        title='核心营养素对比',
        color_discrete_map={
            '蛋白质': '#1f77b4',
            '脂肪': '#ff7f0e',
            '碳水': '#2ca02c',
            '膳食纤维': '#d62728'
        }
    )
    # Set bar width smaller for clearer display
    fig_bar.update_traces(marker_line_width=1, width=0.4)

    # Radar chart: Normalized nutrition (target based)
    targets = {'protein': 75, 'fat': 65, 'carb': 300, 'fiber': 25, 'vit_c': 100}
    categories = ['蛋白质', '脂肪', '碳水', '膳食纤维', '维生素C']
    values = [
        total_nutrition['protein'] / targets['protein'],
        total_nutrition['fat'] / targets['fat'],
        total_nutrition['carb'] / targets['carb'],
        total_nutrition['fiber'] / targets['fiber'],
        total_nutrition['vit_c'] / targets['vit_c']
    ]
    
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name='当前营养值 (占比目标)'
    ))
    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, max(values) + 0.2 if values else 1])),
        showlegend=False,
        title='营养均衡度雷达图'
    )

    # Combine bar and radar into side-by-side subplot
    from plotly.subplots import make_subplots
    fig_side_by_side = make_subplots(
        rows=1,
        cols=2,
        specs=[[{'type': 'xy'}, {'type': 'polar'}]],
        subplot_titles=('核心营养素对比', '营养均衡度雷达图')
    )

    for trace in fig_bar.data:
        fig_side_by_side.add_trace(trace, row=1, col=1)

    fig_side_by_side.add_trace(
        go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            name='当前营养值 (占比目标)'
        ),
        row=1,
        col=2
    )

    # Reduce radar visual dominance and avoid遮挡表头
    fig_side_by_side.update_layout(
        showlegend=False,
        height=420,
        margin=dict(t=80, b=20, l=20, r=20),
        title={
            'text': '营养素对比与均衡度',
            'x': 0.5,
            'xanchor': 'center'
        }
    )
    fig_side_by_side.update_polars(
        radialaxis=dict(range=[0, max(values) + 0.2 if values else 1], visible=True),
        angularaxis=dict(tickfont=dict(size=11)),
        bgcolor='rgba(0,0,0,0)'
    )

    # 修改子图比例位置，避免雷达图过拔高挡住表头
    fig_side_by_side.layout['polar'].domain = {'x': [0.55, 0.95], 'y': [0.1, 0.8]}
    fig_side_by_side.layout['xaxis'].domain = [0.05, 0.5]

    return {
        "text": summary,
        "charts": [fig_pie, fig_side_by_side],
        "data": total_nutrition,
        "table": df_dish_nutrition
    }

def check_allergies(df_recipes, df_students):
    risks = []
    recipe_ingredients = []
    
    # Collect all ingredients from the menu and clean them
    for _, row in df_recipes.iterrows():
        ingredients = [i.strip() for i in row['ingredients'].split(',')]
        for ing in ingredients:
            ing_cleaned = clean_ingredient_name(ing)
            recipe_ingredients.append({'recipe': row['name'], 'ingredient_cleaned': ing_cleaned, 'ingredient_raw': ing})
            
    df_menu_ing = pd.DataFrame(recipe_ingredients)
    
    # Clean allergens in students table
    df_students_clean = df_students.copy()
    # Handle cases where allergen might be NaN
    df_students_clean['allergen'] = df_students_clean['allergen'].fillna('')
    df_students_clean['allergen_cleaned'] = df_students_clean['allergen'].apply(clean_ingredient_name)
    
    # Merge on cleaned names
    matches = df_menu_ing.merge(df_students_clean, left_on='ingredient_cleaned', right_on='allergen_cleaned')
    
    if matches.empty:
        return {
            "text": "✅ 该日期菜谱安全，未发现学生过敏风险。",
            "table": None
        }
    else:
        summary_text = f"⚠️ 发现 {len(matches)} 处过敏风险！请注意以下学生及菜品。"
        # Show raw names in the report for clarity
        risk_table = matches[['class_name', 'student_name', 'allergen', 'recipe']].rename(columns={
            'class_name': '班级',
            'student_name': '学生姓名',
            'allergen': '过敏原',
            'recipe': '相关菜品'
        })
        return {
            "text": summary_text,
            "table": risk_table
        }

def get_ai_suggestions(nutrition_summary):
    prompt = f"""
    你是一位专业的智慧食堂营养师。请根据以下营养分析结果，给出针对性的改进建议。
    建议字数控制在400字以内，重点从蛋白质多样性、蔬菜种类、脂肪控制、主食粗细搭配等角度出发，确保建议具体可行。

    营养分析结果：
    {nutrition_summary}

    请以专业、亲切的口吻回答。
    """
    
    try:
        # User requested 3-second delay before AI response
        time.sleep(3)
        response = client.chat.completions.create(
            model="glm-4.7-flash",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,
            max_tokens=65536,
            extra_body={
                "thinking": {
                    "type": "enabled"
                }
            }
        )
        return {
            "text": f"### 💡 AI 营养师改进建议\n\n{response.choices[0].message.content}",
            "chart": None,
            "table": None
        }
    except Exception as e:
        return {
            "text": f"AI建议生成失败: {str(e)}",
            "chart": None,
            "table": None
        }

def agent_process(query, df_recipes, df_students, df_nutrition):
    query = query.lower()
    
    # Check for comprehensive analysis
    if '综合分析' in query:
        # 1. Nutrition Analysis
        nut_res = analyze_nutrition(df_recipes, df_nutrition)
        
        # 2. Allergy Check
        allergy_res = check_allergies(df_recipes, df_students)
        
        # 3. AI Suggestions
        ai_res = get_ai_suggestions(nut_res['text'])
        
        return {
            "type": "comprehensive",
            "nutrition": nut_res,
            "allergy": allergy_res,
            "suggestions": ai_res
        }
    
    if any(k in query for k in ['过敏', '风险', 'allergy']):
        return check_allergies(df_recipes, df_students)
    
    elif any(k in query for k in ['分析', '营养', '报告', 'nutrition']):
        res = analyze_nutrition(df_recipes, df_nutrition)
        return res
    
    elif any(k in query for k in ['建议', '改进', '优化', 'suggestion']):
        nut_res = analyze_nutrition(df_recipes, df_nutrition)
        return get_ai_suggestions(nut_res['text'])
    
    else:
        # Default behavior: try to determine with GLM if it's a general question or just provide nutrition analysis
        prompt = f"用户问：'{query}'。如果这是一个关于食堂菜谱营养、过敏或建议的问题，请直接回答。如果是通用的，请简单介绍你的功能（营养分析、过敏检查、AI改进建议）。"
        try:
            # User requested 3-second delay before AI response
            time.sleep(3)
            response = client.chat.completions.create(
                model="glm-4.7-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                max_tokens=65536,
                extra_body={
                    "thinking": {
                        "type": "enabled"
                    }
                }
            )
            return {"text": response.choices[0].message.content}
        except Exception as e:
            return {"text": "我是一个AI营养师，可以帮您分析菜谱营养、检查过敏风险并提供改进建议。您可以试着问我'分析对应日期营养'或'检查过敏风险'。"}
