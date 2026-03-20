import sqlite3
import pandas as pd

def check_missing_nutrition():
    conn = sqlite3.connect('canteen.db')
    cursor = conn.cursor()
    
    # Get all recipes for 2026-03-09
    cursor.execute("SELECT name, ingredients FROM recipes WHERE date = '2026-03-09'")
    rows = cursor.fetchall()
    
    # Collect all unique ingredients
    all_ings = set()
    for name, ingredients in rows:
        ings = [i.strip() for i in ingredients.split(',') if i.strip()]
        all_ings.update(ings)
    
    print(f"Total unique ingredients on 2026-03-09: {len(all_ings)}")
    
    # Get ingredients already in nutrition table
    cursor.execute("SELECT ingredient FROM nutrition")
    known_ings = {row[0] for row in cursor.fetchall()}
    
    missing_ings = all_ings - known_ings
    print(f"Missing ingredients: {missing_ings}")
    
    conn.close()
    return list(missing_ings)

if __name__ == "__main__":
    check_missing_nutrition()
