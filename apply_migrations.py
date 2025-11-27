import sqlite3
import os

def apply_migrations():
    db_path = 'database.db'
    migrations_dir = 'migrations'
    
    # Check if database exists, if not we'll create it
    db_exists = os.path.exists(db_path)
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create migrations table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Get list of applied migrations
    cursor.execute('SELECT name FROM migrations')
    applied_migrations = {row[0] for row in cursor.fetchall()}
    
    # Get list of migration files
    try:
        migration_files = sorted([f for f in os.listdir(migrations_dir) 
                               if f.endswith('.sql')])
    except FileNotFoundError:
        print(f"No migrations directory found at {migrations_dir}")
        return
    
    # Apply each migration that hasn't been applied yet
    for migration_file in migration_files:
        if migration_file not in applied_migrations:
            print(f"Applying migration: {migration_file}")
            try:
                with open(os.path.join(migrations_dir, migration_file), 'r') as f:
                    sql = f.read()
                    cursor.executescript(sql)
                
                # Record the migration as applied
                cursor.execute('INSERT INTO migrations (name) VALUES (?)', (migration_file,))
                conn.commit()
                print(f"Successfully applied {migration_file}")
                
            except Exception as e:
                print(f"Error applying {migration_file}: {e}")
                conn.rollback()
                break
    
    conn.close()

if __name__ == "__main__":
    apply_migrations()
