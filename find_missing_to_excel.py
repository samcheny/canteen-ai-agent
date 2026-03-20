import pandas as pd
import sqlite3
import re
from utils import clean_ingredient_name, parse_recipe_excel

def generate_missing_nutrition_excel():
    print("Parsing recipe1.xlsx...")
    recipes = parse_recipe_excel('recipe1.xlsx')
    if not recipes:
        print("Failed to parse recipes from recipe1.xlsx")
        return

    # 1. Collect all unique cleaned ingredients from recipe1
    all_ings = set()
    for r in recipes:
        ings = [i.strip() for i in r['ingredients'].split(',') if i.strip()]
        all_ings.update(ings)
    
    print(f"Total unique ingredients in recipe1: {len(all_ings)}")

    # 2. Connect to database and check existing nutrition
    conn = sqlite3.connect('canteen.db')
    df_nut = pd.read_sql_query("SELECT ingredient FROM nutrition", conn)
    known_ingredients = set(df_nut['ingredient'].tolist())
    conn.close()

    # 3. Find missing ones
    missing_ings = sorted(list(all_ings - known_ingredients))
    print(f"Found {len(missing_ings)} missing ingredients.")

    # 4. Generate Excel
    if missing_ings:
        missing_df = pd.DataFrame({
            'ingredient': missing_ings,
            'protein': 0.0,
            'fat': 0.0,
            'carb': 0.0,
            'calorie': 0.0,
            'fiber': 0.0,
            'vit_c': 0.0
        })
        output_file = 'missing_nutrition_data.xlsx'
        missing_df.to_excel(output_file, index=False)
        print(f"Excel file generated: {output_file}")
    else:
        print("No missing ingredients found!")

if __name__ == "__main__":
    generate_missing_nutrition_excel()
