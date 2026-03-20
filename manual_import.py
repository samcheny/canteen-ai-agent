from utils import parse_recipe_excel, save_recipes_to_db
import sqlite3

def manual_import():
    print("Starting manual import of recipe1.xlsx...")
    recipes = parse_recipe_excel('recipe1.xlsx')
    if recipes:
        print(f"Parsed {len(recipes)} recipes. Saving to DB...")
        save_recipes_to_db(recipes)
        print("Import complete.")
        
        # Verify
        conn = sqlite3.connect('canteen.db')
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT date FROM recipes')
        dates = cursor.fetchall()
        print(f"Current dates in DB: {dates}")
        conn.close()
    else:
        print("Failed to parse recipe1.xlsx")

if __name__ == "__main__":
    manual_import()
