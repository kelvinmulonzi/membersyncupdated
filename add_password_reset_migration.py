#!/usr/bin/env python3
"""
Password Reset Migration Script for MemberSync
This script adds the password reset functionality to an existing MemberSync database.
"""

import sqlite3
import os
from datetime import datetime

DATABASE = 'database.db'

def list_password_reset_tokens():
    """List all password reset tokens for debugging"""
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT prt.id, prt.user_id, u.username, prt.email, prt.token, 
                       prt.expires_at, prt.used, prt.created_at
                FROM password_reset_tokens prt
                LEFT JOIN users u ON prt.user_id = u.id
                ORDER BY prt.created_at DESC
            ''')
            tokens = cursor.fetchall()
            
            print("\n🔑 Password Reset Tokens:")
            print("-" * 80)
            if tokens:
                for token in tokens:
                    status = "USED" if token[6] else "ACTIVE"
                    print(f"ID: {token[0]}, User: {token[2]}, Email: {token[3]}")
                    print(f"    Token: {token[4][:20]}...")
                    print(f"    Expires: {token[5]}, Status: {status}, Created: {token[7]}")
                    print("-" * 80)
            else:
                print("No password reset tokens found")
                print("-" * 80)
            
    except Exception as e:
        print(f"Error listing tokens: {e}")

def create_test_reset_token():
    """Create a test password reset token for the first user"""
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            
            # Get first user
            cursor.execute("SELECT id, username, email FROM users LIMIT 1")
            user = cursor.fetchone()
            
            if not user:
                print("❌ No users found to create test token for")
                return False
            
            user_id, username, email = user
            test_token = f"test_reset_token_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Create test token (expires in 1 hour)
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, email, token, expires_at)
                VALUES (?, ?, ?, datetime('now', '+1 hour'))
            ''', (user_id, email, test_token))
            
            conn.commit()
            
            print(f"✅ Test password reset token created!")
            print(f"   User: {username}")
            print(f"   Email: {email}")
            print(f"   Token: {test_token}")
            print(f"   Test URL: http://localhost:5000/reset-password/{test_token}")
            print("\n⚠️  This is a test token - remember to delete it after testing")
            
            return True
            
    except Exception as e:
        print(f"❌ Error creating test token: {e}")
        return False

# Command line interface for easy testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "list-users":
            list_users()
        elif command == "list-tokens":
            list_password_reset_tokens()
        elif command == "create-test-token":
            create_test_reset_token()
        elif command == "cleanup":
            cleanup_expired_tokens()
        elif command == "verify":
            verify_migration()
        else:
            print("Available commands:")
            print("  python add_password_reset_migration.py list-users")
            print("  python add_password_reset_migration.py list-tokens")
            print("  python add_password_reset_migration.py create-test-token")
            print("  python add_password_reset_migration.py cleanup")
            print("  python add_password_reset_migration.py verify")
    else:
        # Run the full migration if no command specified
        main_migration() backup_database():
    """Create a backup of the existing database"""
    if os.path.exists(DATABASE):
        backup_name = f"database_backup_password_reset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        import shutil
        shutil.copy2(DATABASE, backup_name)
        print(f"✅ Database backup created: {backup_name}")
        return backup_name
    return None

def add_password_reset_table():
    """Add password reset tokens table to existing database"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            # Check if table already exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='password_reset_tokens'")
            if cursor.fetchone():
                print("ℹ️  Password reset tokens table already exists")
                return True
            
            # Create password reset tokens table
            cursor.execute('''
                CREATE TABLE password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    used INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Create index for faster token lookups
            cursor.execute('''
                CREATE INDEX idx_password_reset_token ON password_reset_tokens(token)
            ''')
            
            # Create index for cleanup of expired tokens
            cursor.execute('''
                CREATE INDEX idx_password_reset_expires ON password_reset_tokens(expires_at)
            ''')
            
            conn.commit()
            print("✅ Password reset tokens table created successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Error creating password reset tokens table: {e}")
        return False

def verify_migration():
    """Verify that the migration was successful"""
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            
            # Check if table exists and is accessible
            cursor.execute("SELECT COUNT(*) FROM password_reset_tokens")
            print("✅ Password reset tokens table is accessible")
            
            # Check table structure
            cursor.execute("PRAGMA table_info(password_reset_tokens)")
            columns = cursor.fetchall()
            expected_columns = ['id', 'user_id', 'email', 'token', 'expires_at', 'used', 'created_at']
            
            actual_columns = [col[1] for col in columns]
            for expected_col in expected_columns:
                if expected_col in actual_columns:
                    print(f"✅ Column '{expected_col}' exists")
                else:
                    print(f"❌ Column '{expected_col}' missing")
                    return False
            
            # Check indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='password_reset_tokens'")
            indexes = cursor.fetchall()
            print(f"✅ Found {len(indexes)} indexes on password_reset_tokens table")
            
            print("✅ Migration verification completed successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def test_password_reset_functionality():
    """Test basic password reset functionality"""
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            
            # Check if we have any users to test with
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            if user_count == 0:
                print("ℹ️  No users found - skipping functionality test")
                return True
            
            print(f"ℹ️  Found {user_count} users in database")
            
            # Test inserting a password reset token (will be cleaned up)
            test_token = "test_token_12345"
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, email, token, expires_at, used)
                VALUES (1, 'test@example.com', ?, datetime('now', '+1 day'), 0)
            ''', (test_token,))
            
            # Test retrieving the token
            cursor.execute("SELECT * FROM password_reset_tokens WHERE token = ?", (test_token,))
            result = cursor.fetchone()
            
            if result:
                print("✅ Password reset token insertion/retrieval test successful")
                
                # Clean up test token
                cursor.execute("DELETE FROM password_reset_tokens WHERE token = ?", (test_token,))
                conn.commit()
                print("✅ Test data cleaned up")
                return True
            else:
                print("❌ Password reset token test failed")
                return False
                
    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        return False

def cleanup_expired_tokens():
    """Clean up any expired password reset tokens"""
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            
            # Delete expired tokens
            cursor.execute('''
                DELETE FROM password_reset_tokens 
                WHERE expires_at < datetime('now')
            ''')
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            if deleted_count > 0:
                print(f"🧹 Cleaned up {deleted_count} expired password reset tokens")
            else:
                print("ℹ️  No expired tokens to clean up")
                
            return True
            
    except Exception as e:
        print(f"❌ Error cleaning up expired tokens: {e}")
        return False

def show_migration_summary():
    """Show a summary of what was accomplished"""
    
    print("\n" + "="*60)
    print("📊 PASSWORD RESET MIGRATION SUMMARY")
    print("="*60)
    print("✅ Added password_reset_tokens table to database")
    print("✅ Created indexes for optimal performance")
    print("✅ Database backup created (if database existed)")
    print("✅ Migration verified successfully")
    print("\n📊 Database Structure:")
    print("   password_reset_tokens table:")
    print("   - id (PRIMARY KEY)")
    print("   - user_id (FOREIGN KEY to users.id)")
    print("   - email (user's email address)")
    print("   - token (unique reset token)")
    print("   - expires_at (token expiration timestamp)")
    print("   - used (whether token has been used)")
    print("   - created_at (token creation timestamp)")
    print("\n🔧 Next Steps:")
    print("1. Update your app.py with the password reset code")
    print("2. Add the forgot_password.html template")
    print("3. Add the reset_password.html template")
    print("4. Update login.html to include forgot password link")
    print("5. Restart your MemberSync application")
    print("6. Test the forgot password functionality")
    print("\n💡 New Features Available:")
    print("• Forgot password link on login page")
    print("• Secure token generation and validation")
    print("• Email-based password reset process")
    print("• Token expiration (24 hours)")
    print("• One-time use tokens for security")
    print("• Password strength validation")
    print("="*60)

if __name__ == "__main__":
    print("🔐 MemberSync Password Reset Migration")
    print("="*50)
    
    # Check if database exists
    if not os.path.exists(DATABASE):
        print(f"❌ Database file '{DATABASE}' not found!")
        print("Please make sure you're running this script in the same directory as your MemberSync app.py")
        exit(1)
    
    print(f"📊 Found database: {DATABASE}")
    
    # Create backup
    backup_file = backup_database()
    
    try:
        # Add password reset table
        if add_password_reset_table():
            # Verify migration
            if verify_migration():
                # Test functionality
                if test_password_reset_functionality():
                    # Clean up any expired tokens
                    cleanup_expired_tokens()
                    # Show summary
                    show_migration_summary()
                    print("\n🎉 Password reset migration completed successfully!")
                    print("💡 Your original database is safe - a backup was created.")
                else:
                    print("\n⚠️  Migration completed but functionality test failed.")
                    print("The password reset table was created, but you may need to check the implementation.")
            else:
                print("\n❌ Migration verification failed. Please check the errors above.")
        else:
            print("\n❌ Migration failed. Please check the errors above.")
            if backup_file:
                print(f"💡 Your original database is safe - backup: {backup_file}")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user.")
        if backup_file:
            print(f"💡 Your original database is safe - backup: {backup_file}")
    except Exception as e:
        print(f"\n❌ Unexpected error during migration: {e}")
        if backup_file:
            print(f"💡 Your original database is safe - backup: {backup_file}")

# Additional utility functions for manual testing

def list_users():
    """List all users in the database for testing purposes"""
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, email, organization_id FROM users")
            users = cursor.fetchall()
            
            print("\n📋 Users in database:")
            print("-" * 50)
            for user in users:
                print(f"ID: {user[0]}, Username: {user[1]}, Email: {user[2]}, Org: {user[3]}")
            print("-" * 50)
            
    except Exception as e:
        print(f"Error listing users: {e}")

