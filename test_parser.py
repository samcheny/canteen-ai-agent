import pandas as pd
import re

def test_parse():
    df = pd.read_excel('recipe1.xlsx')
    header_row_idx = -1
    for i, row in df.iterrows():
        if "日期" in str(row.values):
            header_row_idx = i
            break
    
    if header_row_idx == -1:
        print("Header not found")
        return

    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    current_date = None
    current_meal = None
    
    for idx, row in df.iterrows():
        date_val = str(row.get('日期', 'nan')).strip()
        if date_val != 'nan' and date_val != 'None':
            current_date = date_val.split(' ')[0]
        
        meal_val = str(row.get('餐点', 'nan')).strip()
        if meal_val != 'nan' and meal_val != 'None':
            current_meal = meal_val
            
        dish_name = str(row.get('套餐', 'nan')).strip()
        ingredients_str = str(row.get('食材组成', 'nan')).strip()
        
        if dish_name != 'nan' and dish_name != 'None' and ingredients_str != 'nan' and ingredients_str != 'None':
            parts = ingredients_str.split('/')
            print(f"Dish: {dish_name} | Date: {current_date} | Meal: {current_meal}")
            for p in parts:
                match = re.search(r'([^\d]+)(\d+(\.\d+)?)g', p)
                if match:
                    print(f"  - {match.group(1).strip()}: {match.group(2)}g")
        if idx > 10: break

if __name__ == "__main__":
    test_parse()
