import sqlite3
import pandas as pd
from utils import get_nutrition_from_ai, clean_ingredient_name

def sync_missing_nutrition():
    conn = sqlite3.connect('canteen.db')
    cursor = conn.cursor()
    
    # 1. Clean up existing recipe ingredients in DB for 2026-03-09
    cursor.execute("SELECT id, ingredients FROM recipes WHERE date = '2026-03-09'")
    rows = cursor.fetchall()
    for row_id, ingredients in rows:
        cleaned_ings = [clean_ingredient_name(i.strip()) for i in ingredients.split(',') if i.strip()]
        cursor.execute("UPDATE recipes SET ingredients = ? WHERE id = ?", (','.join(cleaned_ings), row_id))
    conn.commit()

    # 2. Identify missing ingredients for 2026-03-09
    cursor.execute("SELECT ingredients FROM recipes WHERE date = '2026-03-09'")
    rows = cursor.fetchall()
    
    all_ings = set()
    for (ingredients,) in rows:
        ings = [i.strip() for i in ingredients.split(',') if i.strip()]
        all_ings.update(ings)
        
    cursor.execute("SELECT ingredient FROM nutrition")
    known_ings = {row[0] for row in cursor.fetchall()}
    
    missing_ings = all_ings - known_ings
    
    print(f"Found {len(missing_ings)} missing ingredients.")
    
    # 2. Fetch from AI and save
    for i, ing in enumerate(missing_ings):
        print(f"[{i+1}/{len(missing_ings)}] Fetching nutrition for: {ing}...")
        nut_data = get_nutrition_from_ai(ing)
        
        if nut_data:
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO nutrition (ingredient, protein, fat, carb, calorie, fiber, vit_c)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ing, 
                    nut_data.get('protein', 0), 
                    nut_data.get('fat', 0), 
                    nut_data.get('carb', 0), 
                    nut_data.get('calorie', 0), 
                    nut_data.get('fiber', 0), 
                    nut_data.get('vit_c', 0)
                ))
                conn.commit()
                print(f"  Successfully saved {ing}.")
            except Exception as e:
                print(f"  Error saving {ing}: {e}")
        else:
            print(f"  Failed to get nutrition for {ing}.")
            
    conn.close()
    print("Sync complete.")

if __name__ == "__main__":
    sync_missing_nutrition()
