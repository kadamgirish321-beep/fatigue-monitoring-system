import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",         # CHANGE THIS
        password="root", # CHANGE THIS
        database="fatigue_db"
    )

def insert_reading(user_id, ear, mar, blink_count, blink_rate, fatigue_status):
    db = get_connection()
    cursor = db.cursor()
    cursor.execute("""INSERT INTO readings (user_id, ear, mar, blink_count, blink_rate, fatigue_status)
                      VALUES (%s, %s, %s, %s, %s, %s)""",
                   (user_id, ear, mar, blink_count, blink_rate, fatigue_status))
    db.commit()
    cursor.close()
    db.close()
