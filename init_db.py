import sqlite3
import pandas as pd

def init_database(db_path='canteen.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Create recipes table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        meal TEXT,                 -- Added for meal type (lunch/dinner)
        ingredients TEXT NOT NULL, -- Comma separated ingredients
        grams TEXT NOT NULL        -- Comma separated grams corresponding to ingredients
    )
    ''')

    # 2. Create students table (previously allergies)
    cursor.execute('DROP TABLE IF EXISTS allergies')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL,
        student_name TEXT NOT NULL,
        allergen TEXT,
        height REAL DEFAULT 0,
        weight REAL DEFAULT 0
    )
    ''')

    # 3. Create nutrition table (values per 100g)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS nutrition (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient TEXT NOT NULL UNIQUE,
        protein REAL DEFAULT 0,
        fat REAL DEFAULT 0,
        carb REAL DEFAULT 0,
        calorie REAL DEFAULT 0,
        fiber REAL DEFAULT 0,
        vit_c REAL DEFAULT 0
    )
    ''')

    # Seed data for nutrition
    nutrition_data = [
        ('大米', 7.4, 0.8, 77.9, 347, 0.7, 0),
        ('鸡蛋', 13.3, 8.8, 2.8, 144, 0, 0),
        ('西红柿', 0.9, 0.2, 4.0, 19, 0.5, 14),
        ('猪肉', 17.0, 30.6, 1.0, 343, 0, 0),
        ('青椒', 1.0, 0.2, 4.5, 23, 1.4, 72),
        ('鸡胸肉', 24.6, 1.9, 0.6, 118, 0, 0),
        ('西兰花', 4.1, 0.6, 4.3, 33, 1.6, 51),
        ('土豆', 2.0, 0.2, 17.2, 77, 0.7, 27),
        ('花生', 24.8, 44.3, 13.0, 567, 5.5, 0),
        ('牛奶', 3.3, 3.6, 4.8, 64, 0, 1),
        ('虾', 18.6, 0.8, 2.8, 93, 0, 0)
    ]
    cursor.executemany('INSERT OR IGNORE INTO nutrition (ingredient, protein, fat, carb, calorie, fiber, vit_c) VALUES (?, ?, ?, ?, ?, ?, ?)', nutrition_data)

    # Seed data for students
    students_data = [
        ('一年级一班', '张三', '花生', 120.5, 25.0),
        ('一年级二班', '李四', '虾', 122.0, 26.5),
        ('二年级一班', '王五', '鸡蛋', 130.0, 30.0)
    ]
    cursor.executemany('INSERT OR IGNORE INTO students (class_name, student_name, allergen, height, weight) VALUES (?, ?, ?, ?, ?)', students_data)

    # Seed data for recipes
    recipes_data = [
        ('西红柿炒鸡蛋', '2026-03-14', '午餐', '西红柿,鸡蛋', '200,100'),
        ('青椒炒肉', '2026-03-14', '午餐', '青椒,猪肉', '150,100'),
        ('清蒸大虾', '2026-03-14', '午餐', '虾', '200'),
        ('白菜土豆丝', '2026-03-15', '午餐', '土豆,西兰花', '200,100')
    ]
    cursor.executemany('INSERT OR IGNORE INTO recipes (name, date, meal, ingredients, grams) VALUES (?, ?, ?, ?, ?)', recipes_data)

    conn.commit()
    conn.close()
    print(f"Database {db_path} initialized successfully.")

if __name__ == "__main__":
    init_database()
