import random
import sqlite3
from datetime import datetime, timedelta

# Connect to database
conn = sqlite3.connect('Database.db')
c = conn.cursor()

# Generate 5 random timestamps in the format 'YYYY-MM-DD HH:MM:SS' within the last 5 days as strings
now = datetime.now()
five_days_ago = now - timedelta(days=5)
timestamps = []
for i in range(5):
    random_time = five_days_ago + timedelta(days=random.randint(0, 4), hours=random.randint(0, 23), minutes=random.randint(0, 59), seconds=random.randint(0, 59))
    timestamp_str = random_time.strftime('%Y-%m-%d %H:%M:%S')
    timestamps.append(timestamp_str)

# Update database with timestamps
for i, timestamp in enumerate(timestamps):
    name = str(i + 1)
    date_str, time_str = timestamp.split(' ')
    c.execute("UPDATE Markers SET date = ?, time = ? WHERE name = ?", (date_str, time_str, name))

# Commit changes and close database connection
conn.commit()
conn.close()
