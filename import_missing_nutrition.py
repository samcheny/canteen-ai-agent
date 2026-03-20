import sqlite3
import pandas as pd

def import_missing_nutrition(excel_path='missing_nutrition_data.xlsx', db_path='canteen.db'):
    try:
        # 1. Read Excel data
        df = pd.read_excel(excel_path)
        
        # 2. Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 3. Import data using INSERT OR REPLACE
        # Columns in Excel: ingredient, protein, fat, carb, calorie, fiber, vit_c
        # Columns in DB: ingredient, protein, fat, carb, calorie, fiber, vit_c
        
        data_to_import = []
        for _, row in df.iterrows():
            data_to_import.append((
                row['ingredient'],
                row['protein'],
                row['fat'],
                row['carb'],
                row['calorie'],
                row['fiber'],
                row['vit_c']
            ))
        
        cursor.executemany('''
            INSERT OR REPLACE INTO nutrition (ingredient, protein, fat, carb, calorie, fiber, vit_c)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', data_to_import)
        
        conn.commit()
        count = len(data_to_import)
        conn.close()
        
        print(f"成功从 {excel_path} 导入 {count} 条营养数据到 {db_path}。")
        return True
    except Exception as e:
        print(f"导入失败: {e}")
        return False

if __name__ == "__main__":
    import_missing_nutrition()
