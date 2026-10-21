import sqlite3

# 连接到数据库
conn = sqlite3.connect('stock_analysis.db')
cursor = conn.cursor()

# 查询股票数量
cursor.execute("SELECT COUNT(*) FROM stock_basic;")
count = cursor.fetchone()[0]

print(f"数据库中的股票数量: {count}")

# 关闭连接
conn.close()