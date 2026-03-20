import pandas as pd
import sqlite3

def import_nutrition_from_excel(file_path='missing_nutrition_data.xlsx'):
    print(f"Reading {file_path}...")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Failed to read excel: {e}")
        return

    conn = sqlite3.connect('canteen.db')
    cursor = conn.cursor()
    
    count = 0
    for _, row in df.iterrows():
        ing = str(row['ingredient']).strip()
        # Ensure values are numeric
        try:
            protein = float(row.get('protein', 0))
            fat = float(row.get('fat', 0))
            carb = float(row.get('carb', 0))
            calorie = float(row.get('calorie', 0))
            fiber = float(row.get('fiber', 0))
            vit_c = float(row.get('vit_c', 0))
            
            cursor.execute('''
                INSERT OR REPLACE INTO nutrition (ingredient, protein, fat, carb, calorie, fiber, vit_c)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (ing, protein, fat, carb, calorie, fiber, vit_c))
            count += 1
        except Exception as e:
            print(f"Skipping {ing} due to error: {e}")

    conn.commit()
    conn.close()
    print(f"Successfully imported/updated {count} ingredients in the nutrition table.")

if __name__ == "__main__":
    import_nutrition_from_excel()
