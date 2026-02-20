from flask import Flask, render_template, request, redirect, url_for, Response, session, flash, g, send_file, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import sys
import qrcode
from datetime import datetime, timedelta, date
from collections import defaultdict
import calendar
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time
from twilio.rest import Client
import schedule
from datetime import datetime
from flask_babel import Babel, _, get_locale, ngettext
import json
from flask_babel import Babel
import re
import requests
from urllib.parse import quote
from dotenv import load_dotenv
from functools import wraps
import tempfile
from email.mime.base import MIMEBase
from email import encoders
from werkzeug.utils import secure_filename
from PIL import Image
import io
import base64
import secrets
import hashlib
from PIL import Image, ImageDraw, ImageFont
import phonenumbers
from phonenumbers import geocoder, carrier, NumberParseException
from phonenumbers import PhoneNumberFormat
from orange_sms import OrangeSMS


# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

load_dotenv()  # Load from .env file

# Photos are stored directly in static/uploads/
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key_here')  # Use environment variable

# ============================================================================
# MIDDLEWARE
# ============================================================================

@app.before_request
def before_request():
    """Run before each request"""
    # Check organization status for logged-in users (except global superadmin)
    if session.get('user_id') and not session.get('is_global_superadmin'):
        try:
            db = get_db()
            cursor = db.cursor()
            
            # Check if user's organization is still active
            cursor.execute("""
                SELECT o.status 
                FROM users u 
                JOIN organizations o ON u.organization_id = o.id 
                WHERE u.id = ?
            """, (session.get('user_id'),))
            
            result = cursor.fetchone()
            if result and result[0] != 'active':
                # Organization is inactive, log out user
                session.clear()
                flash('Your organization has been deactivated. Please contact support.', 'danger')
                return redirect(url_for('login'))
                
        except Exception as e:
            # If there's an error checking organization status, log it but don't break the request
            print(f"Error checking organization status: {e}")

DATABASE = 'database.db'

# Email Configuration
SMTP_SERVER = 'smtp.gmail.com'  
SMTP_PORT = 587
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS', 'memberssync@gmail.com')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', 'brlo wufm mjsd hfdj')

# Twilio Configuration (optional for SMS)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', 'your-twilio-sid')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', 'your-twilio-token')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', 'your-twilio-phone')

# Global Admin Secret Key - MUST be changed in production
GLOBAL_ADMIN_SECRET = os.getenv('GLOBAL_ADMIN_SECRET', 'MemberSync_GlobalAdmin_2024_SecureKey_ChangeMe')

# ============================================================================
# DATABASE CONNECTION AND INITIALIZATION
# ============================================================================

def get_db():
    """Get database connection with proper configuration"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, timeout=20.0)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL;')
        g.db.execute('PRAGMA busy_timeout=20000;')
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Properly close database connection"""
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception as e:
            print(f"Error closing database: {e}")

# Create folders
os.makedirs('static/qr_codes', exist_ok=True)

# ============================================================================
# AUTHORIZATION HELPER FUNCTIONS
# ============================================================================

def is_global_superadmin():
    """Check if current user is a global superadmin"""
    return session.get('is_global_superadmin') == 1

def is_global_admin():
    """Check if current user is a global admin (distinct from global superadmin) - DEPRECATED"""
    # This function is deprecated - global admin role is being removed
    return False

def is_org_superadmin():
    """Check if current user is an organization superadmin with enhanced capabilities"""
    return session.get('is_superadmin') == 1

def has_org_superadmin_capabilities():
    """Check if current user has organization superadmin capabilities (includes former global admin features)"""
    return is_org_superadmin() or is_global_superadmin()

def get_user_organization_id():
    """Get current user's organization ID"""
    return session.get('organization_id')

def get_user_location_id():
    """Get current user's assigned location ID
    
    Returns:
        int or None: Location ID if user is assigned to a specific location, None for org-wide access
    """
    return session.get('location_id')

def is_location_admin():
    """Check if current user is an admin assigned to a specific location (store manager)
    
    Returns:
        bool: True if user is an admin with location assignment, False otherwise
    """
    return (session.get('is_admin') and 
            session.get('location_id') is not None and 
            not session.get('is_superadmin') and
            not session.get('is_global_superadmin'))

def has_location_access():
    """Check if user has location-specific access restriction
    
    Returns:
        bool: True if user is restricted to specific location, False if org-wide or global access
    """
    return is_location_admin()

def can_access_organization(target_org_id):
    """Check if current user can access a specific organization"""
    if is_global_superadmin():
        return True
    
    # Organization superadmin now has enhanced capabilities (former global admin features)
    if has_org_superadmin_capabilities() or session.get('is_admin'):
        return get_user_organization_id() == target_org_id
    
    return False

def can_access_location(location_id):
    """Check if current user can access a specific location
    
    Args:
        location_id (int): The location ID to check access for
        
    Returns:
        bool: True if user can access the location, False otherwise
    """
    try:
        # Global superadmin can access any location
        if is_global_superadmin():
            return True
        
        # Organization superadmin can access any location in their org
        if is_org_superadmin():
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT organization_id FROM locations WHERE id = ?', (location_id,))
            result = cursor.fetchone()
            if result:
                return result[0] == get_user_organization_id()
            return False
        
        # Location admin can only access their assigned location
        if is_location_admin():
            return get_user_location_id() == location_id
        
        # Regular users can access locations in their organization
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT organization_id FROM locations WHERE id = ?', (location_id,))
        result = cursor.fetchone()
        if result:
            return result[0] == get_user_organization_id()
        
        return False
        
    except Exception as e:
        print(f"Error checking location access: {e}")
        return False

def get_admin_location_filter():
    """Get SQL filter clause for admin's location restriction
    
    Returns:
        tuple: (filter_clause, params) for SQL query
        
    Examples:
        - Global Superadmin: ("", ())
        - Org Superadmin: ("AND m.organization_id = ?", (org_id,))
        - Location Admin: ("AND m.location_id = ?", (location_id,)) or recent check-in filter
    """
    # Global superadmin has no filter
    if is_global_superadmin():
        return "", ()
    
    # Organization superadmin sees all in their org
    if is_org_superadmin():
        org_id = get_user_organization_id()
        return "AND m.organization_id = ?", (org_id,)
    
    # Location admin sees only their location's members
    if is_location_admin():
        location_id = get_user_location_id()
        org_id = get_user_organization_id()
        # Show members who have this location as home OR last checked in here
        return """AND m.organization_id = ? 
                  AND (m.location_id = ? OR m.membership_id IN (
                      SELECT membership_id FROM checkins 
                      WHERE location_id = ? 
                      ORDER BY checkin_time DESC 
                      LIMIT 1
                  ))""", (org_id, location_id, location_id)
    
    # Default: org filter for regular admins
    org_id = get_user_organization_id()
    if org_id:
        return "AND m.organization_id = ?", (org_id,)
    
    return "AND 1=0", ()  # No access

def can_access_member(membership_id):
    """Check if current user can access a specific member
    
    Access is granted if:
    1. User is a global superadmin, OR
    2. User is an organization superadmin in the same org, OR
    3. User is a location admin and member is in the same organization, OR
    4. User is in the same organization as the member
    """
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get member's organization and location
        cursor.execute("""
            SELECT m.organization_id, o.status as org_status, m.location_id
            FROM members m
            LEFT JOIN organizations o ON m.organization_id = o.id
            WHERE m.membership_id = ?
        """, (membership_id,))
        
        row = cursor.fetchone()
        
        if not row:
            return False  # Member not found
        
        member_org_id = row[0] if isinstance(row, tuple) else row['organization_id']
        member_location_id = row[2] if isinstance(row, tuple) else row['location_id']
        
        # Global superadmin can access any member
        if is_global_superadmin():
            return True
            
        # Organization superadmin can access all members in their organization
        if has_org_superadmin_capabilities():
            return get_user_organization_id() == member_org_id
        
        # Location admin can access any member in their organization
        if is_location_admin():
            user_org_id = get_user_organization_id()
            # Only check if they're in the same organization
            return member_org_id == user_org_id
            
        # Regular organization admins can access members in their organization
        if session.get('is_admin'):
            return get_user_organization_id() == member_org_id
            
        # Organization users can access any member in their organization
        if get_user_organization_id() == member_org_id:
            return True
            
        return False
        
    except Exception as e:
        print(f"Error checking member access: {e}")
        return False

def get_accessible_organizations():
    """Get list of organizations current user can access"""
    if is_global_superadmin():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM organizations ORDER BY name')
        return cursor.fetchall()
    
    elif has_org_superadmin_capabilities():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM organizations WHERE id = ?', 
                      (get_user_organization_id(),))
        return cursor.fetchall()
    
    return []

def get_accessible_locations(organization_id=None):
    """Get list of locations current user can access
    
    Args:
        organization_id (int, optional): Specific organization to get locations for
        
    Returns:
        list: List of locations accessible to current user
    """
    try:
        db = get_db()
        cursor = db.cursor()
        
        if is_global_superadmin():
            # Global Super Admin can access all locations
            if organization_id:
                # Get locations for specific organization
                cursor.execute('''
                    SELECT l.id, l.name, l.organization_id, o.name as organization_name
                    FROM locations l
                    JOIN organizations o ON l.organization_id = o.id
                    WHERE l.organization_id = ?
                    ORDER BY l.name
                ''', (organization_id,))
            else:
                # Get all locations from all organizations
                cursor.execute('''
                    SELECT l.id, l.name, l.organization_id, o.name as organization_name
                    FROM locations l
                    JOIN organizations o ON l.organization_id = o.id
                    ORDER BY o.name, l.name
                ''')
            return cursor.fetchall()
            
        elif has_org_superadmin_capabilities():
            # Organization Super Admin can access locations in their organization
            org_id = organization_id if organization_id else get_user_organization_id()
            cursor.execute('''
                SELECT l.id, l.name, l.organization_id, o.name as organization_name
                FROM locations l
                JOIN organizations o ON l.organization_id = o.id
                WHERE l.organization_id = ?
                ORDER BY l.name
            ''', (org_id,))
            return cursor.fetchall()
            
        elif is_location_admin():
            # Location Admin can only access their assigned location
            location_id = get_user_location_id()
            org_id = get_user_organization_id()
            cursor.execute('''
                SELECT l.id, l.name, l.organization_id, o.name as organization_name
                FROM locations l
                JOIN organizations o ON l.organization_id = o.id
                WHERE l.id = ? AND l.organization_id = ?
            ''', (location_id, org_id))
            return cursor.fetchall()
            
        return []
        
    except Exception as e:
        print(f"Error getting accessible locations: {e}")
        return []

# ============================================================================
# CURRENCY SYMBOLS (SIMPLIFIED - NO API CALLS OR CONVERSION)
# ============================================================================

# Note: Currency system simplified - only symbols are used, no exchange rate conversions
# All prices are stored and displayed in their original currency with appropriate symbols

def get_supported_currencies():
    """Get list of supported currency symbols (simplified - no conversion)"""
    return {
        'USD': {'name': 'US Dollar', 'symbol': '$'},
        'EUR': {'name': 'Euro', 'symbol': '€'},
        'GBP': {'name': 'British Pound', 'symbol': '£'},
        'XAF': {'name': 'Central African CFA Franc', 'symbol': 'FCFA'}
    }

def get_currency_symbol_for_code(currency_code='USD'):
    """Get currency symbol for a given currency code"""
    currencies = get_supported_currencies()
    return currencies.get(currency_code, {}).get('symbol', '$')

def get_user_preferred_currency():
    """Get user's preferred currency code (for symbol display only)"""
    try:
        # Simplified: Read from session first (user preference)
        if 'preferred_currency' in session:
            return session['preferred_currency']
        
        # Fall back to organization default currency
        org_id = session.get('organization_id')
        if org_id:
            currency_code = get_setting('currency_code', 'USD', org_id)
            return currency_code or 'USD'
        
        return 'USD'
    except Exception as e:
        print(f"Error getting preferred currency: {e}")
        return 'USD'

def convert_price_to_user_currency(amount, user_currency=None):
    """Display price with user's preferred currency symbol (no conversion)"""
    try:
        if not user_currency:
            user_currency = get_user_preferred_currency()
        
        # Get currency symbol
        symbol = get_currency_symbol_for_code(user_currency)
        
        # Return the amount as-is with the symbol (no conversion)
        return amount, symbol
        
    except Exception as e:
        print(f"Error getting currency symbol: {e}")
        return amount, '$'

def update_user_preferred_currency(currency_code):
    """Update user's preferred currency preference (simplified - session-based for symbol display)"""
    try:
        # Simplified: Just store in session for symbol display
        session['preferred_currency'] = currency_code
        return True
        
    except Exception as e:
        print(f"Error updating currency preference: {e}")
        return False

# ============================================================================
# DATABASE QUERY FILTERS
# ============================================================================

def get_members_query_filter():
    """Get WHERE clause for filtering members based on user access level"""
    # Debug logging
    print(f"DEBUG: is_global_superadmin() = {is_global_superadmin()}")
    print(f"DEBUG: has_org_superadmin_capabilities() = {has_org_superadmin_capabilities()}")
    print(f"DEBUG: is_org_superadmin() = {is_org_superadmin()}")
    print(f"DEBUG: is_location_admin() = {is_location_admin()}")
    
    if is_global_superadmin():
        print("DEBUG: Global Superadmin - Returning empty filter (access to all members)")
        return "", ()
    elif has_org_superadmin_capabilities():
        print("DEBUG: Organization Superadmin - Returning organization filter")
        return "WHERE m.organization_id = ?", (get_user_organization_id(),)
    elif is_location_admin():
        print("DEBUG: Location Admin - Returning location filter")
        location_id = get_user_location_id()
        org_id = get_user_organization_id()
        return """WHERE m.organization_id = ? 
                  AND (m.location_id = ? OR EXISTS (
                      SELECT 1 FROM checkins c 
                      WHERE c.membership_id = m.membership_id 
                      AND c.location_id = ?
                      AND c.checkin_time >= datetime('now', '-30 days')
                  ))""", (org_id, location_id, location_id)
    
    print("DEBUG: Returning no access filter")
    return "WHERE 1=0", ()

def get_payments_query_filter():
    """Get WHERE clause for filtering payments based on user access level"""
    if is_global_superadmin():
        return "", ()
    elif has_org_superadmin_capabilities():
        return "WHERE p.organization_id = ?", (get_user_organization_id(),)
    elif is_location_admin():
        # Location admin sees payments for members at their location
        location_id = get_user_location_id()
        org_id = get_user_organization_id()
        return """WHERE p.organization_id = ? 
                  AND p.membership_id IN (
                      SELECT membership_id FROM members 
                      WHERE organization_id = ? AND (
                          location_id = ? OR membership_id IN (
                              SELECT membership_id FROM checkins 
                              WHERE location_id = ?
                              AND checkin_time >= datetime('now', '-30 days')
                          )
                      )
                  )""", (org_id, org_id, location_id, location_id)
    return "WHERE 1=0", ()

def get_organizations():
    """Get list of organizations based on user access level"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if is_global_superadmin():
            # Global Superadmin can see all organizations
            cursor.execute('SELECT id, name, industry FROM organizations WHERE status = "active" ORDER BY name')
        else:
            # Regular users can only see their organization
            user_org_id = get_user_organization_id()
            cursor.execute('SELECT id, name, industry FROM organizations WHERE id = ? AND status = "active"', (user_org_id,))
        
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting organizations: {e}")
        return []

def get_organizations_query_filter():
    """Get WHERE clause for filtering organizations based on user access level"""
    if is_global_superadmin():
        return "", ()
    elif has_org_superadmin_capabilities():
        return "WHERE o.id = ?", (get_user_organization_id(),)
    return "WHERE 1=0", ()

def get_notifications_query_filter():
    """Get WHERE clause for filtering notifications based on user access level"""
    if is_global_superadmin():
        return "", ()
    elif has_org_superadmin_capabilities():
        return "WHERE n.organization_id = ?", (get_user_organization_id(),)
    return "WHERE 1=0", ()

def add_photo_column_to_members():
    """Add photo column to members table if it doesn't exist"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            # Check if photo column exists
            cursor.execute("PRAGMA table_info(members)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'photo_filename' not in columns:
                print("Adding 'photo_filename' column to members table...")
                cursor.execute('ALTER TABLE members ADD COLUMN photo_filename TEXT')
                conn.commit()
                print("✅ Photo column added successfully!")
                return True
            else:
                print("ℹ️ Photo column already exists")
                return True
                
    except Exception as e:
        print(f"❌ Error adding photo column: {e}")
        return False


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def migrate_to_global_counter_system():
    """
    Migrate existing data to use the global counter system for all entities.
    This function should be called once to update existing users and members.
    """
    try:
        with sqlite3.connect(DATABASE, timeout=30.0) as conn:
            cursor = conn.cursor()
            
            print("🔄 Starting migration to global counter system...")
            
            # Step 1: Add user_id column to users table if it doesn't exist
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'user_id' not in columns:
                print("📝 Adding user_id column to users table...")
                cursor.execute("ALTER TABLE users ADD COLUMN user_id TEXT")
            
            # Step 2: Get all existing users and assign global IDs
            cursor.execute("SELECT id, username, organization_id, created_at FROM users ORDER BY created_at ASC, id ASC")
            users = cursor.fetchall()
            
            if users:
                print(f"📋 Found {len(users)} users to migrate...")
                
                global_counter = 1
                for user_id, username, org_id, created_at in users:
                    # Check if user already has a user_id
                    cursor.execute("SELECT user_id FROM users WHERE id = ?", (user_id,))
                    existing_user_id = cursor.fetchone()[0]
                    
                    if not existing_user_id:
                        new_user_id = f"USR-{global_counter:06d}"
                        cursor.execute("UPDATE users SET user_id = ? WHERE id = ?", (new_user_id, user_id))
                        print(f"   ✅ Updated user: {username} → {new_user_id}")
                        global_counter += 1
                    else:
                        # Extract counter from existing user_id
                        if existing_user_id.startswith("USR-"):
                            counter = int(existing_user_id.split("-")[1])
                            global_counter = max(global_counter, counter + 1)
            
            # Step 3: Get all existing members and assign global IDs
            cursor.execute("SELECT id, membership_id, name, organization_id, created_at FROM members ORDER BY created_at ASC, id ASC")
            members = cursor.fetchall()
            
            if members:
                print(f"📋 Found {len(members)} members to migrate...")
                
                for member_id, current_membership_id, name, org_id, created_at in members:
                    # Check if member already has a proper global ID
                    if not current_membership_id.startswith("MBR-") or len(current_membership_id.split("-")[1]) < 6:
                        new_membership_id = f"MBR-{global_counter:06d}"
                        cursor.execute("UPDATE members SET membership_id = ? WHERE id = ?", (new_membership_id, member_id))
                        
                        # Update related payments
                        cursor.execute("UPDATE payments SET membership_id = ? WHERE membership_id = ?", (new_membership_id, current_membership_id))
                        
                        print(f"   ✅ Updated member: {name} → {new_membership_id}")
                        global_counter += 1
                    else:
                        # Extract counter from existing membership_id
                        counter = int(current_membership_id.split("-")[1])
                        global_counter = max(global_counter, counter + 1)
            
            conn.commit()
            print("✅ Migration to global counter system completed successfully!")
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        raise

def migrate_database_schema():
    """
    Migrate existing database schema to enforce global member ID uniqueness.
    This function should be called once to update the database constraints.
    """
    try:
        with sqlite3.connect(DATABASE, timeout=30.0) as conn:
            cursor = conn.cursor()
            
            print("🔄 Starting database schema migration...")
            
            # Check if the global uniqueness constraint already exists
            cursor.execute("""
                SELECT sql FROM sqlite_master 
                WHERE type='table' AND name='members'
            """)
            
            table_sql = cursor.fetchone()
            if table_sql and 'membership_id TEXT NOT NULL UNIQUE' in table_sql[0]:
                print("✅ Database schema already has global uniqueness constraint.")
                return
            
            print("📝 Updating database schema to enforce global member ID uniqueness...")
            
            # Create a new table with the updated schema
            cursor.execute("""
                CREATE TABLE members_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    membership_type TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expiration_date TEXT,
                    status TEXT DEFAULT 'active',
                    payment_status TEXT DEFAULT 'Unpaid',
                    notification_sent TEXT DEFAULT 'no',
                    organization_id INTEGER NOT NULL,
                    location_id INTEGER,
                    photo_filename TEXT,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
                )
            """)
            
            # Copy data from old table to new table
            cursor.execute("""
                INSERT INTO members_new 
                SELECT * FROM members
            """)
            
            # Drop the old table
            cursor.execute("DROP TABLE members")
            
            # Rename the new table
            cursor.execute("ALTER TABLE members_new RENAME TO members")
            
            # Update the payments table foreign key constraint
            cursor.execute("""
                CREATE TABLE payments_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    original_amount REAL,
                    discount_amount REAL DEFAULT 0,
                    date TEXT DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    payment_type TEXT DEFAULT 'membership_fee',
                    discount_code TEXT,
                    organization_id INTEGER NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (membership_id) REFERENCES members(membership_id) ON DELETE CASCADE
                )
            """)
            
            # Copy payments data
            cursor.execute("""
                INSERT INTO payments_new 
                SELECT * FROM payments
            """)
            
            # Drop old payments table and rename new one
            cursor.execute("DROP TABLE payments")
            cursor.execute("ALTER TABLE payments_new RENAME TO payments")
            
            conn.commit()
            print("✅ Database schema migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Error during schema migration: {e}")
        raise

def init_db():
    """Initialize database with proper connection handling and organization_id support"""
    try:
        db_exists = os.path.exists(DATABASE)
        
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA foreign_keys=ON;')
            cursor = conn.cursor()
            
            # Check if this is an existing database with data
            if db_exists:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                if 'members' in tables and 'organizations' in tables and 'users' in tables:
                    # Check if we have data in members table
                    cursor.execute("SELECT COUNT(*) FROM members")
                    member_count = cursor.fetchone()[0]
                    if member_count > 0:
                        print(f"ℹ️  Found existing database with {member_count} members. Preserving data...")
            
            # ORGANIZATIONS (top-level entities)
            # SUBSCRIPTION_PACKAGES (subscription tiers)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscription_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    max_organizations INTEGER NOT NULL,
                    price REAL DEFAULT 0.0,
                    features TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS organizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    industry TEXT,
                    location TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    subscription_package_id INTEGER DEFAULT 1,
                    created_by_user_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (subscription_package_id) REFERENCES subscription_packages(id),
                    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
                    UNIQUE(name, location)
                )
            ''')

            # LOCATIONS (optional: stores, branches)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    address TEXT,
                    city TEXT,
                    state TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    UNIQUE(name, organization_id)
                )
            ''')

            # USERS (admins or managers)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    email TEXT,
                    password_hash TEXT NOT NULL,
                    organization_id INTEGER NOT NULL,
                    location_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    is_superadmin INTEGER DEFAULT 0,
                    is_global_superadmin INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
                    UNIQUE(username, organization_id)
                )
            ''')
            
            # Create index for location-based queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_location ON users(location_id)')

            # MEMBERS (customers/members)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    membership_type TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expiration_date TEXT,
                    status TEXT DEFAULT 'active',
                    payment_status TEXT DEFAULT 'Unpaid',
                    notification_sent TEXT DEFAULT 'no',
                    organization_id INTEGER NOT NULL,
                    location_id INTEGER,
                    photo_filename TEXT,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
                )
            ''')

            # PAYMENTS (payment records)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    original_amount REAL,
                    discount_amount REAL DEFAULT 0,
                    date TEXT DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    payment_type TEXT DEFAULT 'membership_fee',
                    discount_code TEXT,
                    organization_id INTEGER NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (membership_id) REFERENCES members(membership_id) ON DELETE CASCADE
                )
            ''')

            # DISCOUNTS (discount codes)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS discounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    description TEXT,
                    discount_type TEXT NOT NULL,
                    discount_value REAL NOT NULL,
                    min_amount REAL DEFAULT 0,
                    max_uses INTEGER DEFAULT NULL,
                    current_uses INTEGER DEFAULT 0,
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT DEFAULT 'active',
                    organization_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    UNIQUE(code, organization_id)
                )
            ''')

            # DISCOUNT_USAGE (track discount usage)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS discount_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discount_id INTEGER NOT NULL,
                    membership_id TEXT NOT NULL,
                    amount_saved REAL NOT NULL,
                    organization_id INTEGER NOT NULL,
                    used_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (discount_id) REFERENCES discounts(id) ON DELETE CASCADE,
                    FOREIGN KEY (membership_id, organization_id) REFERENCES members(membership_id, organization_id) ON DELETE CASCADE,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                )
            ''')

            # NOTIFICATIONS (notification history)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'sent',
                    organization_id INTEGER NOT NULL,
                    FOREIGN KEY (membership_id, organization_id) REFERENCES members(membership_id, organization_id) ON DELETE CASCADE,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                )
            ''')

            # SETTINGS (organization-specific settings)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT NOT NULL,
                    organization_id INTEGER NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    UNIQUE(setting_key, organization_id)
                )
            ''')

            # GLOBAL_SETTINGS (system-wide settings)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS global_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_key TEXT UNIQUE NOT NULL,
                    setting_value TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # SCHEDULED_TASKS table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    message_content TEXT NOT NULL,
                    schedule_time TEXT,
                    status TEXT DEFAULT 'active',
                    organization_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                )
            ''')

            # Create Global Admin Organization (ID = 1) if it doesn't exist
            cursor.execute('''
                INSERT OR IGNORE INTO organizations (id, name, industry)
                VALUES (1, 'Global System Administration', 'System Management')
            ''')

            # Create Global Superadmin User if it doesn't exist
            cursor.execute('''
                SELECT id FROM users
                WHERE username = ? AND organization_id = 1
            ''', ('globaladmin',))

            if not cursor.fetchone():
                try:
                    # Generate unique user ID
                    user_id = generate_unique_user_id(1, "USR")
                    
                    cursor.execute('''
                        INSERT INTO users (user_id, username, email, password_hash, organization_id, is_admin, is_superadmin, is_global_superadmin)
                        VALUES (?, ?, ?, ?, 1, 1, 1, 1)
                    ''', (user_id, 'globaladmin', 'admin@system.local',
                          generate_password_hash('ChangeMe123!')))

                    print("=" * 60)
                    print("🚀 INITIAL GLOBAL SUPERADMIN CREATED")
                    print("=" * 60)
                    print("Username: globaladmin")
                    print("Password: ChangeMe123!")
                    print("Organization: Global System Administration")
                    print("=" * 60)
                    print("⚠️  IMPORTANT: Change this password immediately!")
                    print("=" * 60)
                except sqlite3.IntegrityError as e:
                    print(f"⚠️  Global admin already exists or conflict: {e}")

            conn.commit()
            print("✅ Database initialized successfully with superadmin support")
            # Password reset tokens table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
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
            
            conn.commit()
            print("✅ Password reset tokens table initialized")
            # Create index for faster token lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_password_reset_token ON password_reset_tokens(token)
            ''')

            # Create index for cleanup of expired tokens
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_password_reset_expires ON password_reset_tokens(expires_at)
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prepaid_balances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL,
                    organization_id INTEGER NOT NULL,
                    current_balance REAL DEFAULT 0.0,
                    total_recharged REAL DEFAULT 0.0,
                    total_spent REAL DEFAULT 0.0,
                    total_bonus_earned REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (membership_id, organization_id) REFERENCES members(membership_id, organization_id) ON DELETE CASCADE,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    UNIQUE(membership_id, organization_id)
                )
            ''')

            # PREPAID_TRANSACTIONS table - tracks all recharge and usage transactions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prepaid_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL,
                    organization_id INTEGER NOT NULL,
                    transaction_type TEXT NOT NULL, -- 'recharge', 'usage', 'bonus', 'fee'
                    amount REAL NOT NULL,
                    bonus_amount REAL DEFAULT 0.0,
                    bonus_percentage REAL DEFAULT 0.0,
                    balance_before REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    description TEXT,
                    admin_user_id INTEGER,
                    transaction_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (membership_id, organization_id) REFERENCES members(membership_id, organization_id) ON DELETE CASCADE,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')

            # PREPAID_BONUS_TIERS table - configurable bonus tiers per organization
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prepaid_bonus_tiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER NOT NULL,
                    tier_name TEXT NOT NULL,
                    min_amount REAL NOT NULL,
                    max_amount REAL,
                    bonus_percentage REAL NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    membership_id TEXT NOT NULL,
                    organization_id INTEGER NOT NULL,
                    checkin_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    checkout_time TEXT,
                    status TEXT DEFAULT 'checked_in',
                    service_type TEXT,
                    location_id INTEGER,
                    notes TEXT,
                    admin_user_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (membership_id, organization_id) REFERENCES members(membership_id, organization_id) ON DELETE CASCADE,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
                    FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')

            # AUDIT_LOGS table - comprehensive activity tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    action TEXT NOT NULL,
                    table_name TEXT,
                    record_id TEXT,
                    old_values TEXT,
                    new_values TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    organization_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                )
            ''')
            
            # Create index for faster audit log queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_audit_logs_date ON audit_logs(created_at)
            ''')

            # Create indexes for better performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkins_member_org
                ON checkins(membership_id, organization_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkins_date
                ON checkins(date(checkin_time))
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkins_status
                ON checkins(status)
            ''')

            # Create check-in settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkin_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER NOT NULL,
                    require_checkout INTEGER DEFAULT 0,
                    auto_checkout_hours INTEGER DEFAULT 24,
                    allow_multiple_checkins INTEGER DEFAULT 0,
                    require_service_type INTEGER DEFAULT 0,
                    send_checkin_notifications INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    UNIQUE(organization_id)
                )
            ''')

            # Create service types table for customizable services
            print("🏷️  Creating service_types table...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS service_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    color TEXT DEFAULT '#007bff',
                    is_active INTEGER DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    UNIQUE(name, organization_id)
                )
            ''')

            # Create check-in analytics table for daily summaries
            print("📊 Creating checkin_analytics table...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkin_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    total_checkins INTEGER DEFAULT 0,
                    unique_members INTEGER DEFAULT 0,
                    peak_hour INTEGER,
                    avg_duration_minutes INTEGER DEFAULT 0,
                    most_used_service TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                    UNIQUE(organization_id, date)
                )
            ''')

            # Insert default service types for each organization
            print("🎯 Adding default service types...")
            cursor.execute('SELECT id, name FROM organizations')
            organizations = cursor.fetchall()

            default_services = [
                ('Gym', 'General gym and fitness equipment', '#28a745'),
                ('Pool', 'Swimming pool and aquatic activities', '#17a2b8'),
                ('Spa', 'Spa and wellness services', '#6f42c1'),
                ('Classes', 'Group fitness and training classes', '#fd7e14'),
                ('Meeting', 'Business meetings and conferences', '#6c757d'),
                ('Event', 'Special events and functions', '#e83e8c'),
                ('Consultation', 'Personal consultations and appointments', '#20c997'),
                ('Other', 'Other services not listed above', '#6c757d')
            ]

            for org_id, org_name in organizations:
                print(f"   📝 Adding services for {org_name}...")
                for i, (service_name, description, color) in enumerate(default_services):
                    try:
                        cursor.execute('''
                            INSERT OR IGNORE INTO service_types
                            (organization_id, name, description, color, sort_order)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (org_id, service_name, description, color, i))
                    except sqlite3.IntegrityError:
                        pass  # Service already exists

            # Create default settings for each organization
            print("⚙️  Creating default check-in settings...")
            for org_id, org_name in organizations:
                cursor.execute('''
                    INSERT OR IGNORE INTO checkin_settings (organization_id)
                    VALUES (?)
                ''', (org_id,))

            # Add check-in related columns to notifications table if they don't exist
            print("🔔 Updating notifications table...")
            cursor.execute("PRAGMA table_info(notifications)")
            notification_columns = [column[1] for column in cursor.fetchall()]

            if 'checkin_id' not in notification_columns:
                cursor.execute('ALTER TABLE notifications ADD COLUMN checkin_id INTEGER')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_notifications_checkin
                    ON notifications(checkin_id)
                ''')

            conn.commit()

            # Verify the migration
            print("✅ Verifying migration...")

            # Check if all tables were created
            required_tables = ['checkins', 'checkin_settings', 'service_types', 'checkin_analytics']
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]

            missing_tables = [table for table in required_tables if table not in existing_tables]
            if missing_tables:
                print(f"❌ Missing tables: {missing_tables}")
                return False

            # Check data counts
            cursor.execute('SELECT COUNT(*) FROM service_types')
            service_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM checkin_settings')
            settings_count = cursor.fetchone()[0]

            print(f"📊 Migration Summary:")
            print(f"   • Service types created: {service_count}")
            print(f"   • Organization settings: {settings_count}")
            print(f"   • All required tables: ✅")
            print(f"   • All indexes created: ✅")

            return True

            conn.commit()
            print("✅ Prepaid card tables created successfully!")
            
            
            return True

    except sqlite3.Error as e:
        print(f"❌ Database error during migration: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during migration: {e}")
        return False

    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        raise
        print(f"❌ Error creating prepaid tables: {e}")
        return False

# ============================================================================
# DECORATORS FOR ACCESS CONTROL
# ============================================================================

def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# MAP VISUALIZATION ROUTES
# ============================================================================

@app.route('/map')
@require_login
def map_visualization():
    """Interactive map visualization of members and locations"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get organization filter
        if is_global_superadmin():
            filter_org_id = request.args.get('org_id', type=int)
            if filter_org_id:
                org_filter = "WHERE l.organization_id = ?"
                org_params = (filter_org_id,)
            else:
                org_filter = ""
                org_params = ()
        else:
            org_id = session.get('organization_id')
            org_filter = "WHERE l.organization_id = ?"
            org_params = (org_id,)
        
        # Get locations with member counts
        cursor.execute(f'''
            SELECT 
                l.id,
                l.name,
                l.city,
                l.state,
                l.address,
                COUNT(DISTINCT m.id) as member_count,
                COUNT(DISTINCT CASE WHEN m.status = 'active' THEN m.id END) as active_members,
                o.name as org_name
            FROM locations l
            LEFT JOIN members m ON l.id = m.location_id AND l.organization_id = m.organization_id
            LEFT JOIN organizations o ON l.organization_id = o.id
            {org_filter}
            GROUP BY l.id, l.name, l.city, l.state, l.address, o.name
            ORDER BY member_count DESC
        ''', org_params)
        
        locations_data = cursor.fetchall()
        
        # Get check-in statistics by location
        cursor.execute(f'''
            SELECT 
                l.id,
                l.name,
                COUNT(c.id) as total_checkins,
                COUNT(CASE WHEN date(c.checkin_time) = date('now') THEN 1 END) as today_checkins
            FROM locations l
            LEFT JOIN checkins c ON l.id = c.location_id
            {org_filter}
            GROUP BY l.id, l.name
        ''', org_params)
        
        checkin_data = {row[0]: {'total': row[2], 'today': row[3]} for row in cursor.fetchall()}
        
        # Prepare locations for map
        locations = []
        for loc in locations_data:
            location_info = {
                'id': loc[0],
                'name': loc[1],
                'city': loc[2] or 'Unknown',
                'state': loc[3] or 'Unknown',
                'address': loc[4] or 'No address',
                'member_count': loc[5],
                'active_members': loc[6],
                'org_name': loc[7],
                'total_checkins': checkin_data.get(loc[0], {}).get('total', 0),
                'today_checkins': checkin_data.get(loc[0], {}).get('today', 0)
            }
            locations.append(location_info)
        
        # Get organizations for filter
        organizations = []
        if is_global_superadmin():
            cursor.execute('SELECT id, name FROM organizations WHERE status = "active" ORDER BY name')
            organizations = cursor.fetchall()
        
        # Get overall statistics
        cursor.execute(f'''
            SELECT 
                COUNT(DISTINCT l.id) as total_locations,
                COUNT(DISTINCT m.id) as total_members,
                COUNT(DISTINCT CASE WHEN m.status = 'active' THEN m.id END) as active_members
            FROM locations l
            LEFT JOIN members m ON l.id = m.location_id AND l.organization_id = m.organization_id
            {org_filter}
        ''', org_params)
        
        stats = cursor.fetchone()
        
        return render_template('map_visualization.html',
                             locations=locations,
                             organizations=organizations,
                             stats=stats,
                             is_global_superadmin=is_global_superadmin())
        
    except Exception as e:
        flash(f'Error loading map: {e}', 'danger')
        return render_template('map_visualization.html',
                             locations=[],
                             organizations=[],
                             stats={'total_locations': 0, 'total_members': 0, 'active_members': 0})

@app.route('/api/location_details/<int:location_id>')
@require_login
def location_details_api(location_id):
    """Get detailed information about a location for map popup"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get location details
        cursor.execute('''
            SELECT 
                l.id, l.name, l.city, l.state, l.address,
                o.name as org_name,
                COUNT(DISTINCT m.id) as member_count,
                COUNT(DISTINCT CASE WHEN m.status = 'active' THEN m.id END) as active_members
            FROM locations l
            LEFT JOIN organizations o ON l.organization_id = o.id
            LEFT JOIN members m ON l.id = m.location_id AND l.organization_id = m.organization_id
            WHERE l.id = ?
            GROUP BY l.id, l.name, l.city, l.state, l.address, o.name
        ''', (location_id,))
        
        location = cursor.fetchone()
        if not location:
            return {'success': False, 'error': 'Location not found'}
        
        # Get recent check-ins
        cursor.execute('''
            SELECT 
                m.name, c.checkin_time, c.service_type
            FROM checkins c
            JOIN members m ON c.membership_id = m.membership_id
            WHERE c.location_id = ?
            ORDER BY c.checkin_time DESC
            LIMIT 5
        ''', (location_id,))
        
        recent_checkins = cursor.fetchall()
        
        return {
            'success': True,
            'location': {
                'id': location[0],
                'name': location[1],
                'city': location[2],
                'state': location[3],
                'address': location[4],
                'org_name': location[5],
                'member_count': location[6],
                'active_members': location[7]
            },
            'recent_checkins': [
                {
                    'member_name': c[0],
                    'checkin_time': c[1],
                    'service_type': c[2]
                } for c in recent_checkins
            ]
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.route('/map/heatmap')
@require_login
def map_heatmap():
    """Heatmap visualization of member distribution"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        org_id = session.get('organization_id')
        
        # Get member locations with coordinates
        cursor.execute('''
            SELECT l.city, l.state, COUNT(m.id) as member_count
            FROM locations l
            LEFT JOIN members m ON l.id = m.location_id
            WHERE l.organization_id = ?
            GROUP BY l.city, l.state
        ''', (org_id,))
        
        locations = cursor.fetchall()
        
        # Convert to heatmap format [lat, lng, intensity]
        heatmap_data = []
        for loc in locations:
            city = loc[0]
            if city in cameroon_cities:
                coords = cameroon_cities[city]
                heatmap_data.append([coords[0], coords[1], loc[2] / 10])
        
        return render_template('map_heatmap.html', heatmap_data=heatmap_data)
        
    except Exception as e:
        flash(f'Error loading heatmap: {e}', 'danger')
        return redirect(url_for('map_visualization'))


def require_global_superadmin(f):
    """Decorator to require global superadmin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_global_superadmin():
            flash('Access denied. Global superadmin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def require_global_admin(f):
    """Decorator to require global admin privileges (DEPRECATED - Use require_org_superadmin instead)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Redirect to organization superadmin requirement
        if not has_org_superadmin_capabilities():
            flash('Access denied. Organization superadmin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def require_superadmin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_org_superadmin():
            flash('Access denied. Superadmin privileges required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def require_org_superadmin(f):
    """Decorator to require organization superadmin privileges (with enhanced capabilities)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not has_org_superadmin_capabilities():
            flash('Access denied. Organization superadmin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """Decorator to require admin privileges (org admin, org superadmin, or global superadmin)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_admin = session.get('is_admin', False)
        is_global_superadmin_user = session.get('is_global_superadmin', False)
        is_org_superadmin_user = session.get('is_superadmin', False)
        
        if not (is_admin or is_global_superadmin_user or is_org_superadmin_user):
            flash('Access denied. Administrator privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def require_member_access(f):
    """Decorator to require member access (admin, superadmin, or global admin)"""
    """Fixed decorator to ensure user has access to the requested member"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get membership_id from route parameters
        membership_id = kwargs.get('membership_id')
        if not membership_id:
            # Try to get from URL path
            from flask import request
            path_parts = request.path.split('/')
            if len(path_parts) > 2:
                membership_id = path_parts[-1]  # Get last part of path
        
        if not membership_id:
            flash('Member ID not provided.', 'danger')
            return redirect(url_for('members'))
        
        # Check access
        if not can_access_member(membership_id):
            flash('Access denied to this member.', 'danger')
            return redirect(url_for('members'))
                
        return f(*args, **kwargs)
    return decorated_function

def require_organization_access(f):
    """Decorator to ensure user has access to the requested organization"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        org_id = kwargs.get('org_id')
        
        if not org_id:
            flash('Organization ID not provided.', 'danger')
            return redirect(url_for('dashboard'))

        if not can_access_organization(org_id):
            flash('Access denied to this organization.', 'danger')
            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)
    return decorated_function

def require_prepaid_access(f):
    """Decorator to require prepaid management access (org admin or org superadmin only, no global admins)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Explicitly block global admins from prepaid management
        if session.get('is_global_superadmin'):
            flash('Access denied. Global administrators cannot manage prepaid cards.', 'danger')
            return redirect(url_for('dashboard'))
            
        # Check if user has org admin or superadmin privileges
        is_admin = session.get('is_admin', False)
        is_superadmin = session.get('is_superadmin', False)
        
        if not (is_admin or is_superadmin):
            flash('Access denied. Organization administrator privileges required for prepaid management.', 'danger')
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# CAMEROON PHONE NUMBER VALIDATION AND FORMATTING
# ============================================================================

def validate_cameroon_phone(phone):
    """Validate Cameroon phone number using phonenumbers library"""
    if not phone:
        return False, "Phone number is required"

    try:
        # Remove any whitespace
        phone_clean = phone.strip()

        # Parse the number with Cameroon country code
        parsed_number = phonenumbers.parse(phone_clean, "CM")

        # Validate the number
        if not phonenumbers.is_valid_number(parsed_number):
            return False, "Invalid Cameroon phone number"

        if not phonenumbers.is_possible_number(parsed_number):
            return False, "Phone number is not possible for Cameroon"

        # Check if it's actually a Cameroon number
        if parsed_number.country_code != 237:
            return False, "Phone number must be a Cameroon number (+237)"

        return True, None

    except NumberParseException as e:
        error_messages = {
            NumberParseException.INVALID_COUNTRY_CODE: "Invalid country code",
            NumberParseException.NOT_A_NUMBER: "Not a valid phone number",
            NumberParseException.TOO_SHORT_NSN: "Phone number is too short",
            NumberParseException.TOO_LONG: "Phone number is too long"
        }
        return False, error_messages.get(e.error_type, "Invalid phone number format")
    except Exception as e:
        return False, f"Error validating phone number: {str(e)}"

def format_cameroon_phone(phone):
    """Format phone number to Cameroon international format (+237...)"""
    if not phone:
        return phone

    try:
        # Parse the number
        parsed_number = phonenumbers.parse(phone.strip(), "CM")

        # Format to E.164 format (+237XXXXXXXXX)
        formatted = phonenumbers.format_number(parsed_number, PhoneNumberFormat.E164)
        return formatted

    except NumberParseException:
        # If parsing fails, try to clean and format manually
        # Remove all non-digit characters
        digits = ''.join(filter(str.isdigit, phone))

        # If starts with 237, add +
        if digits.startswith('237'):
            return f'+{digits}'

        # If starts with 6 or 2 (Cameroon mobile/landline), add +237
        if digits.startswith(('6', '2')) and len(digits) == 9:
            return f'+237{digits}'

        # Return as-is if can't format
        return phone
    except Exception:
        return phone

def get_phone_info(phone):
    """Get detailed information about a Cameroon phone number"""
    try:
        parsed_number = phonenumbers.parse(phone.strip(), "CM")

        if phonenumbers.is_valid_number(parsed_number):
            return {
                'is_valid': True,
                'formatted': phonenumbers.format_number(parsed_number, PhoneNumberFormat.INTERNATIONAL),
                'e164': phonenumbers.format_number(parsed_number, PhoneNumberFormat.E164),
                'national': phonenumbers.format_number(parsed_number, PhoneNumberFormat.NATIONAL),
                'carrier': carrier.name_for_number(parsed_number, "en"),
                'location': geocoder.description_for_number(parsed_number, "en"),
                'country_code': f'+{parsed_number.country_code}',
                'national_number': str(parsed_number.national_number)
            }
        else:
            return {'is_valid': False}

    except Exception as e:
        return {'is_valid': False, 'error': str(e)}

@app.route('/debug/test-phone', methods=['GET', 'POST'])
@require_login
def test_phone_validation():
    """Test Cameroon phone number validation"""
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()

        # Validate
        is_valid, error = validate_cameroon_phone(phone)

        # Get info
        phone_info = get_phone_info(phone) if is_valid else {}

        return render_template('test_phone.html',
                             phone=phone,
                             is_valid=is_valid,
                             error=error,
                             info=phone_info)

    return render_template('test_phone.html')

# ========================================================================
# Create upload directories
# =======================================================================


os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_and_save_photo(file, membership_id):
    """Process and save member photo"""
    if file and allowed_file(file.filename):
        try:
            # Open image using PIL
            image = Image.open(file.stream)

            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')

            # Resize image to standard size (300x400) while maintaining aspect ratio
            image.thumbnail((300, 400), Image.Resampling.LANCZOS)

            # Create a new image with white background
            new_image = Image.new('RGB', (300, 400), (255, 255, 255))

            # Calculate position to center the image
            x = (300 - image.width) // 2
            y = (400 - image.height) // 2

            # Paste the resized image onto the white background
            new_image.paste(image, (x, y))

            # Save the processed image
            filename = f"{membership_id}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            new_image.save(filepath, 'JPEG', quality=85, optimize=True)

            return filename
        except Exception as e:
            print(f"Error processing photo: {e}")
            return None
    return None

def delete_member_photo(membership_id):
    """Delete member photo file"""
    try:
        filename = f"{membership_id}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
    except Exception as e:
        print(f"Error deleting photo: {e}")
    return False


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_next_global_counter():
    """
    Get the next global counter value for any entity (user, admin, member).
    This ensures a single sequential counter across all entity types.
    """
    import time
    
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            # Enable WAL mode for better concurrency
            cursor.execute('PRAGMA journal_mode=WAL;')
            
            # Use a more robust approach with retry logic
            max_attempts = 10
            base_delay = 0.01  # 10ms base delay
            
            for attempt in range(max_attempts):
                try:
                    # Get the maximum counter from all entity types
                    cursor.execute("""
                        SELECT COALESCE(MAX(global_counter), 0) + 1
                        FROM (
                            SELECT CAST(SUBSTR(membership_id, 5) AS INTEGER) as global_counter FROM members WHERE membership_id LIKE 'MBR-%'
                            UNION ALL
                            SELECT CAST(SUBSTR(user_id, 5) AS INTEGER) as global_counter FROM users WHERE user_id LIKE 'USR-%'
                        )
                    """)
                    
                    next_counter = cursor.fetchone()[0]
                    
                    # Add a small increment based on attempt to reduce collision probability
                    if attempt > 0:
                        next_counter += attempt
                    
                    return next_counter
                    
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower():
                        # Database is locked, wait and retry
                        time.sleep(base_delay * (attempt + 1))
                        continue
                    else:
                        raise
            
            # If we get here, all attempts failed
            raise Exception(f"Could not get global counter after {max_attempts} attempts")
            
    except Exception as e:
        raise Exception(f"Error getting next global counter: {e}")

def generate_unique_membership_id(organization_id, prefix="MBR"):
    """
    Generate a globally unique membership ID using the global counter system.
    This ensures sequential numbering across all entity types.
    """
    try:
        next_counter = get_next_global_counter()
        membership_id = f"{prefix}-{next_counter:06d}"
        return membership_id
        
    except Exception as e:
        raise Exception(f"Error generating membership ID: {e}")

def generate_unique_user_id(organization_id, prefix="USR"):
    """
    Generate a globally unique user ID using the global counter system.
    This ensures sequential numbering across all entity types.
    """
    try:
        next_counter = get_next_global_counter()
        user_id = f"{prefix}-{next_counter:06d}"
        return user_id
        
    except Exception as e:
        raise Exception(f"Error generating user ID: {e}")

def migrate_to_global_unique_membership_ids():
    """
    Migrate existing membership IDs to ensure global uniqueness across all organizations.
    This function should be run once to clean up existing data and enforce global uniqueness.
    """
    try:
        with sqlite3.connect(DATABASE, timeout=30.0) as conn:
            cursor = conn.cursor()
            
            print("🔄 Starting migration to global unique membership IDs...")
            
            # Get all members ordered by creation date to maintain chronological order
            cursor.execute("""
                SELECT id, membership_id, name, organization_id, created_at 
                FROM members 
                ORDER BY created_at ASC, id ASC
            """)
            
            members = cursor.fetchall()
            
            if not members:
                print("ℹ️  No members found to migrate.")
                return
            
            print(f"📋 Found {len(members)} members to process...")
            
            # Track used IDs globally
            used_ids = set()
            updates_needed = []
            global_counter = 1
            
            for member_id, current_membership_id, name, org_id, created_at in members:
                # Check if this ID is already used globally
                if current_membership_id in used_ids:
                    print(f"   ⚠️  Found duplicate ID: {current_membership_id} for member: {name} (Org: {org_id})")
                    
                    # Generate new globally unique ID
                    new_id = f"MBR-{global_counter:06d}"
                    
                    # Ensure the new ID is truly unique
                    while new_id in used_ids:
                        global_counter += 1
                        new_id = f"MBR-{global_counter:06d}"
                    
                    updates_needed.append((member_id, current_membership_id, new_id, name, org_id))
                    used_ids.add(new_id)
                    global_counter += 1
                else:
                    # Check if the current ID follows the new format, if not, update it
                    if not current_membership_id.startswith("MBR-") or len(current_membership_id.split("-")[1]) < 6:
                        new_id = f"MBR-{global_counter:06d}"
                        
                        # Ensure the new ID is truly unique
                        while new_id in used_ids:
                            global_counter += 1
                            new_id = f"MBR-{global_counter:06d}"
                        
                        updates_needed.append((member_id, current_membership_id, new_id, name, org_id))
                        used_ids.add(new_id)
                        global_counter += 1
                    else:
                        used_ids.add(current_membership_id)
            
            # Apply updates
            if updates_needed:
                print(f"🔄 Updating {len(updates_needed)} membership IDs...")
                
                for member_id, old_id, new_id, name, org_id in updates_needed:
                    try:
                        # Update the member record
                        cursor.execute("""
                            UPDATE members 
                            SET membership_id = ? 
                            WHERE id = ?
                        """, (new_id, member_id))
                        
                        # Update related payments
                        cursor.execute("""
                            UPDATE payments 
                            SET membership_id = ? 
                            WHERE membership_id = ?
                        """, (new_id, old_id))
                        
                        print(f"   ✅ Updated: {old_id} → {new_id} (Member: {name}, Org: {org_id})")
                        
                    except Exception as e:
                        print(f"   ❌ Error updating {old_id}: {e}")
                        continue
                
                conn.commit()
                print(f"✅ Successfully migrated {len(updates_needed)} membership IDs to global uniqueness!")
            else:
                print("✅ All membership IDs are already globally unique!")
            
            # Verify global uniqueness
            cursor.execute("""
                SELECT membership_id, COUNT(*) as count
                FROM members 
                GROUP BY membership_id 
                HAVING COUNT(*) > 1
            """)
            
            duplicates = cursor.fetchall()
            if duplicates:
                print(f"⚠️  Warning: Found {len(duplicates)} duplicate IDs after migration:")
                for membership_id, count in duplicates:
                    print(f"   - {membership_id}: {count} occurrences")
            else:
                print("✅ Global uniqueness verified - no duplicates found!")
                
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        raise

def fix_duplicate_membership_ids():
    """
    Fix existing duplicate membership IDs by reassigning them with proper sequential numbers.
    This function should be run once to clean up existing data.
    """
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            print("🔧 Starting duplicate membership ID cleanup...")
            
            # First, let's check for cross-organization duplicates
            cursor.execute("""
                SELECT membership_id, COUNT(*) as count, 
                       GROUP_CONCAT(organization_id) as org_ids,
                       GROUP_CONCAT((SELECT name FROM organizations WHERE id = members.organization_id)) as org_names
                FROM members 
                GROUP BY membership_id 
                HAVING COUNT(*) > 1
            """)
            
            cross_org_duplicates = cursor.fetchall()
            
            if cross_org_duplicates:
                print(f"⚠️  Found {len(cross_org_duplicates)} membership IDs used across multiple organizations:")
                for membership_id, count, org_ids, org_names in cross_org_duplicates:
                    print(f"   {membership_id} used in: {org_names}")
                
                # For cross-organization duplicates, we'll reassign the later organizations
                for membership_id, count, org_ids, org_names in cross_org_duplicates:
                    org_id_list = [int(x) for x in org_ids.split(',')]
                    
                    # Keep the first organization's member, reassign others
                    keep_org_id = min(org_id_list)
                    reassign_org_ids = [oid for oid in org_id_list if oid != keep_org_id]
                    
                    print(f"   📋 Keeping {membership_id} in organization {keep_org_id}, reassigning others...")
                    
                    for reassign_org_id in reassign_org_ids:
                        # Get the member to reassign
                        cursor.execute("""
                            SELECT id, name FROM members 
                            WHERE membership_id = ? AND organization_id = ?
                        """, (membership_id, reassign_org_id))
                        
                        member_to_reassign = cursor.fetchone()
                        if member_to_reassign:
                            member_id, member_name = member_to_reassign
                            
                            # Generate new unique ID for this organization
                            new_id = generate_unique_membership_id(reassign_org_id, "MBR")
                            
                            print(f"      🔄 Reassigning {member_name} from {membership_id} to {new_id}")
                            
                            # Update the membership_id
                            cursor.execute("""
                                UPDATE members 
                                SET membership_id = ? 
                                WHERE id = ?
                            """, (new_id, member_id))
                            
                            # Update related records (payments, etc.)
                            cursor.execute("""
                                UPDATE payments 
                                SET membership_id = ? 
                                WHERE membership_id = ? AND organization_id = ?
                            """, (new_id, membership_id, reassign_org_id))
            
            # Now check for within-organization duplicates
            cursor.execute("SELECT id, name FROM organizations ORDER BY id")
            organizations = cursor.fetchall()
            
            for org_id, org_name in organizations:
                print(f"📋 Processing organization: {org_name} (ID: {org_id})")
                
                # Get all members for this organization, ordered by creation date
                cursor.execute("""
                    SELECT id, membership_id, name, created_at 
                    FROM members 
                    WHERE organization_id = ? 
                    ORDER BY created_at ASC
                """, (org_id,))
                
                members = cursor.fetchall()
                
                if not members:
                    print(f"   ℹ️  No members found for {org_name}")
                    continue
                
                # Track used IDs for this organization
                used_ids = set()
                updates_needed = []
                
                for member_id, current_membership_id, name, created_at in members:
                    # Check if this ID is already used in this organization
                    if current_membership_id in used_ids:
                        print(f"   ⚠️  Found duplicate ID: {current_membership_id} for member: {name}")
                        
                        # Generate new unique ID for this organization
                        new_id = generate_unique_membership_id(org_id, "MBR")
                        
                        updates_needed.append((member_id, current_membership_id, new_id, name))
                        used_ids.add(new_id)
                    else:
                        used_ids.add(current_membership_id)
                
                # Apply updates
                if updates_needed:
                    print(f"   🔄 Updating {len(updates_needed)} duplicate IDs...")
                    for member_id, old_id, new_id, name in updates_needed:
                        # Update the membership_id
                        cursor.execute("""
                            UPDATE members 
                            SET membership_id = ? 
                            WHERE id = ?
                        """, (new_id, member_id))
                        
                        # Update related records (payments, etc.)
                        cursor.execute("""
                            UPDATE payments 
                            SET membership_id = ? 
                            WHERE membership_id = ? AND organization_id = ?
                        """, (new_id, old_id, org_id))
                        
                        print(f"      ✅ {name}: {old_id} → {new_id}")
                    
                    conn.commit()
                    print(f"   ✅ Updated {len(updates_needed)} members in {org_name}")
                else:
                    print(f"   ✅ No duplicates found in {org_name}")
            
            print("🎉 Duplicate membership ID cleanup completed!")
            return True
            
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return False

def add_member_safe(membership_id, name, email, phone, membership_type, organization_id, location_id=None, created_by=None):
    """Safely add a member with proper conflict handling for membership_id"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id FROM members
                WHERE membership_id = ? AND organization_id = ?
            ''', (membership_id, organization_id))

            if cursor.fetchone():
                raise ValueError(f"Membership ID '{membership_id}' already exists for this organization")

            cursor.execute('''
                INSERT INTO members
                (membership_id, name, email, phone, membership_type, organization_id, location_id, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (membership_id, name, email, phone, membership_type, organization_id, location_id, created_by))

            conn.commit()
            return cursor.lastrowid

    except sqlite3.IntegrityError as e:
        raise ValueError(f"Database constraint violation: {e}")
    except Exception as e:
        raise Exception(f"Error adding member: {e}")

def get_members_by_organization(organization_id):
    """Get all members for a specific organization"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    m.id,
                    m.membership_id,
                    m.name,
                    m.email,
                    m.phone,
                    m.membership_type,
                    m.created_at,
                    m.expiration_date,
                    m.status,
                    m.payment_status,
                    m.notification_sent,
                    m.organization_id,
                    m.location_id,
                    l.name as location_name,
                    o.name as organization_name
                FROM members m
                LEFT JOIN locations l ON m.location_id = l.id
                LEFT JOIN organizations o ON m.organization_id = o.id
                WHERE m.organization_id = ?
                ORDER BY m.created_at DESC
            ''', (organization_id,))

            return cursor.fetchall()

    except Exception as e:
        raise Exception(f"Error fetching members: {e}")

def get_payments_by_organization(organization_id):
    """Get all payments for a specific organization"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    p.id,
                    p.membership_id,
                    p.amount,
                    p.original_amount,
                    p.discount_amount,
                    p.date,
                    p.notes,
                    p.payment_type,
                    p.discount_code,
                    p.organization_id,
                    m.name as member_name,
                    o.name as organization_name
                FROM payments p
                LEFT JOIN members m ON p.membership_id = m.membership_id AND p.organization_id = m.organization_id
                LEFT JOIN organizations o ON p.organization_id = o.id
                WHERE p.organization_id = ?
                ORDER BY p.date DESC
            ''', (organization_id,))

            return cursor.fetchall()

    except Exception as e:
        raise Exception(f"Error fetching payments: {e}")

def calculate_expiration_date(membership_type):
    """Calculate expiration date based on membership type"""
    today = datetime.now()
    return (today + timedelta(days=365)).strftime('%Y-%m-%d')  # Default 1 year

def send_email_notification(email, subject, message):
    """Send email notification"""
    try:
        print(f"DEBUG: Attempting to send email to: {email}")
        print(f"DEBUG: Email configuration - Server: {SMTP_SERVER}, Port: {SMTP_PORT}")
        print(f"DEBUG: Email address: {EMAIL_ADDRESS}")
        print(f"DEBUG: Email password length: {len(EMAIL_PASSWORD) if EMAIL_PASSWORD else 0}")
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = subject

        msg.attach(MIMEText(message, 'html'))

        print(f"DEBUG: Connecting to SMTP server...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.set_debuglevel(1)  # Enable SMTP debugging
        print(f"DEBUG: Starting TLS...")
        server.starttls()
        print(f"DEBUG: Logging in to email server...")
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        print(f"DEBUG: Sending email...")
        server.send_message(msg)
        print(f"DEBUG: Email sent successfully!")
        server.quit()
        return True
    except Exception as e:
        print(f"DEBUG: Email error details: {type(e).__name__}: {str(e)}")
        print(f"DEBUG: Full error traceback:")
        import traceback
        traceback.print_exc()
        return False

def send_sms_notification_twilio(phone, message):
    """Send SMS notification via Twilio"""
    try:
        if (not TWILIO_ACCOUNT_SID or TWILIO_ACCOUNT_SID == 'your-twilio-sid' or
            not TWILIO_AUTH_TOKEN or TWILIO_AUTH_TOKEN == 'your-twilio-token' or
            not TWILIO_PHONE_NUMBER or TWILIO_PHONE_NUMBER == 'your-twilio-phone'):
            print("⚠️ Twilio credentials not configured. Skipping Twilio fallback.")
            return False, "Twilio credentials not configured"
            
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )
        return True, None
    except Exception as e:
        print(f"Twilio SMS error: {e}")
        return False, str(e)

def send_sms_notification_orange(phone, message):
    """Send SMS notification via Orange API (Supports International)"""
    try:
        # Parse number, default to Cameroon (CM) if no country code provided
        try:
            parsed = phonenumbers.parse(phone, "CM")
        except NumberParseException:
            return False, "Invalid phone number format"
            
        if not phonenumbers.is_valid_number(parsed):
            return False, "Invalid phone number"
            
        # Format to E.164 (e.g. +237..., +254...)
        formatted_phone = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
        
        # Use Orange SMS service
        sms_service = OrangeSMS()
        success, response = sms_service.send_sms(formatted_phone, message)
        
        if success:
            print(f"✅ SMS sent successfully via Orange to {formatted_phone} (Carrier: {carrier.name_for_number(parsed, 'en')})")
            return True, None
        else:
            print(f"❌ Failed to send Orange SMS to {formatted_phone}: {response}")
            return False, f"Orange API: {response}"
    except Exception as e:
        print(f"❌ Orange SMS error: {e}")
        return False, f"Orange Exception: {str(e)}"

def send_sms_notification(phone, message):
    """Send SMS notification with priority: Orange -> Twilio"""
    # 1. Try Orange first for ALL numbers (Local & International like Safaricom)
    success, error = send_sms_notification_orange(phone, message)
    if success:
        return True, None
    
    print(f"⚠️ Orange SMS failed ({error}), falling back to Twilio...")
    
    # 2. Fallback to Twilio (Reliable for international)
    return send_sms_notification_twilio(phone, message)

def send_org_superadmin_welcome_email(username, email, org_name, user_id):
    """Send welcome email to newly created Organization Super Admin"""
    try:
        subject = f"🎉 Welcome to MemberSync - Organization Super Admin Access"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ padding: 30px; background: #f8f9fa; }}
                .box {{ background: white; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #667eea; }}
                .features {{ background: white; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .feature-item {{ padding: 10px 0; border-bottom: 1px solid #e9ecef; }}
                .feature-item:last-child {{ border-bottom: none; }}
                .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ padding: 20px; text-align: center; color: #6c757d; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>👑 Welcome to MemberSync!</h1>
                    <p>Organization Super Admin Access Granted</p>
                </div>
                
                <div class="content">
                    <h2>Hello {username}! 🎉</h2>
                    <p>Congratulations! Your Organization Super Admin account has been successfully created.</p>
                    
                    <div class="box">
                        <h3>📋 Your Account Details</h3>
                        <ul>
                            <li><strong>Username:</strong> {username}</li>
                            <li><strong>User ID:</strong> {user_id}</li>
                            <li><strong>Organization:</strong> {org_name}</li>
                            <li><strong>Role:</strong> Organization Super Admin</li>
                            <li><strong>Email:</strong> {email}</li>
                        </ul>
                    </div>
                    
                    <div class="features">
                        <h3>🚀 Your Super Admin Privileges Include:</h3>
                        
                        <div class="feature-item">
                            <strong>👥 Full Member Management</strong><br>
                            <small>Register, edit, delete members, and manage their profiles</small>
                        </div>
                        
                        <div class="feature-item">
                            <strong>💰 Payment & Financial Control</strong><br>
                            <small>Process payments, manage prepaid cards, create discount codes</small>
                        </div>
                        
                        <div class="feature-item">
                            <strong>👨‍💼 User & Admin Management</strong><br>
                            <small>Create and manage additional admins and users for your organization</small>
                        </div>
                        
                        <div class="feature-item">
                            <strong>✅ Check-in System</strong><br>
                            <small>Monitor facility access, track member attendance and usage</small>
                        </div>
                        
                        <div class="feature-item">
                            <strong>📧 Communication Center</strong><br>
                            <small>Send email and SMS notifications to members</small>
                        </div>
                        
                        <div class="feature-item">
                            <strong>📊 Advanced Reports & Analytics</strong><br>
                            <small>Export data, view insights, and track organization performance</small>
                        </div>
                        
                        <div class="feature-item">
                            <strong>⚙️ Organization Settings</strong><br>
                            <small>Configure prepaid settings, bonus tiers, and system preferences</small>
                        </div>
                    </div>
                    
                    <div style="text-align: center;">
                        <a href="http://localhost:5000/login" class="button">Login to Your Dashboard</a>
                    </div>
                    
                    <div class="box" style="background: #fff3cd; border-left-color: #ffc107;">
                        <h4>🔐 Security Tips:</h4>
                        <ul>
                            <li>Keep your login credentials secure</li>
                            <li>Use a strong, unique password</li>
                            <li>Never share your admin credentials</li>
                            <li>Enable two-factor authentication if available</li>
                        </ul>
                    </div>
                    
                    <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
                    
                    <p>Best regards,<br>
                    <strong>The MemberSync Team</strong></p>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from MemberSync. Please do not reply to this email.</p>
                    <p>&copy; 2024 MemberSync. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send the email
        send_email_notification(email, subject, html_content)
        print(f"✅ Welcome email sent to Organization Super Admin: {username} ({email})")
        return True
        
    except Exception as e:
        print(f"❌ Error sending Organization Super Admin welcome email: {e}")
        raise

def validate_phone_number_enhanced(phone):
    """Enhanced phone number validation with international support using phonenumbers library."""
    if not phone:
        return False, "Phone number is required."

    try:
        # Parse the number. We assume 'CM' (Cameroon) for numbers without a country code.
        # This allows users to enter local Cameroon numbers like '6...'.
        # For other countries, they MUST enter the full number with '+', e.g., '+254...'.
        parsed_number = phonenumbers.parse(phone.strip(), "CM")

        if not phonenumbers.is_valid_number(parsed_number):
            return False, "The phone number is not valid. Please include the country code for non-Cameroon numbers (e.g., +254...)."
        
        return True, None

    except NumberParseException as e:
        error_messages = {
            NumberParseException.INVALID_COUNTRY_CODE: "Invalid country code.",
            NumberParseException.NOT_A_NUMBER: "This is not a valid phone number.",
            NumberParseException.TOO_SHORT_NSN: "The phone number is too short.",
            NumberParseException.TOO_LONG: "The phone number is too long."
        }
        return False, error_messages.get(e.error_type, "Invalid phone number format.")
    except Exception as e:
        return False, f"An unexpected error occurred: {str(e)}"

def format_phone_number(phone):
    """Format phone number to standard international E.164 format (+... )"""
    if not phone:
        return phone

    try:
        # Parse with 'CM' as the default region for local numbers.
        # International numbers with '+' will be parsed correctly.
        parsed_number = phonenumbers.parse(phone.strip(), "CM")
        
        # Format to E.164 format (+XXXXXXXXXXX)
        return phonenumbers.format_number(parsed_number, PhoneNumberFormat.E164)

    except (NumberParseException, Exception):
        # If parsing fails, return the original string as a fallback.
        return phone.strip()

def validate_membership_id_immutability(current_id, submitted_id):
    """Validate that membership ID cannot be changed once assigned"""
    if not submitted_id:
        return True, None
    
    if submitted_id.strip() != current_id:
        return False, f"Membership ID '{current_id}' cannot be changed once assigned. This field is immutable for data integrity."
    
    return True, None

def get_deduction_fee_percentage():
    """Get the deduction fee percentage from global settings"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT setting_value FROM global_settings WHERE setting_key = ?', ('deduction_fee_percentage',))
        result = cursor.fetchone()
        if result:
            return float(result[0])
        else:
            # Set default fee percentage
            cursor.execute('''
                INSERT INTO global_settings (setting_key, setting_value, updated_at)
                VALUES ('deduction_fee_percentage', '2.5', datetime('now'))
            ''')
            db.commit()
            return 2.5
    except Exception as e:
        print(f"Error getting deduction fee percentage: {e}")
        import traceback
        traceback.print_exc()
        return 2.5  # Default fallback

# ============================================================================
# SUBSCRIPTION PACKAGES MANAGEMENT
# ============================================================================

def initialize_subscription_packages():
    """Initialize default subscription packages"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # First, add missing columns to users table if needed
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_global_admin' not in user_columns:
            print("Adding 'is_global_admin' column to users table...")
            cursor.execute('ALTER TABLE users ADD COLUMN is_global_admin INTEGER DEFAULT 0')
            db.commit()
        
        if 'subscription_package_id' not in user_columns:
            print("Adding 'subscription_package_id' column to users table...")
            cursor.execute('ALTER TABLE users ADD COLUMN subscription_package_id INTEGER')
            db.commit()
        
        if 'preferred_currency' not in user_columns:
            print("Adding 'preferred_currency' column to users table...")
            cursor.execute('ALTER TABLE users ADD COLUMN preferred_currency TEXT DEFAULT "USD"')
            db.commit()
        
        # Add subscription_package_id column to organizations if it doesn't exist
        cursor.execute("PRAGMA table_info(organizations)")
        org_columns = [column[1] for column in cursor.fetchall()]
        
        if 'subscription_package_id' not in org_columns:
            print("Adding 'subscription_package_id' column to organizations table...")
            cursor.execute('ALTER TABLE organizations ADD COLUMN subscription_package_id INTEGER DEFAULT 1')
            db.commit()
            print("✅ Added subscription_package_id column to organizations table")
        
        # Update existing organizations to have default package (Admin - ID 1)
        cursor.execute('UPDATE organizations SET subscription_package_id = 1 WHERE subscription_package_id IS NULL')
        print("✅ Updated existing organizations with default package")
        
        # Update existing users to have default package based on their role
        # Global superadmins get the highest package (ID 4)
        cursor.execute('''
            UPDATE users SET subscription_package_id = 4 
            WHERE is_global_superadmin = 1 AND subscription_package_id IS NULL
        ''')
        
        # Regular superadmins get package 2 (1-5 orgs)
        cursor.execute('''
            UPDATE users SET subscription_package_id = 2 
            WHERE is_superadmin = 1 AND is_global_superadmin = 0 AND subscription_package_id IS NULL
        ''')
        
        # Regular admins get package 1 (1 org)
        cursor.execute('''
            UPDATE users SET subscription_package_id = 1 
            WHERE is_admin = 1 AND is_superadmin = 0 AND is_global_superadmin = 0 AND subscription_package_id IS NULL
        ''')
        
        # Users without any admin role get package 1 (1 org)
        cursor.execute('''
            UPDATE users SET subscription_package_id = 1 
            WHERE is_admin = 0 AND is_superadmin = 0 AND is_global_superadmin = 0 AND subscription_package_id IS NULL
        ''')
        
        print("✅ Updated existing users with appropriate packages based on their roles")
        
        # Enforce limits on existing records
        violations = enforce_existing_limits()
        if violations:
            print("⚠️  Some users exceed their package limits. Please review and adjust packages in User Management.")
        
        # Check if packages already exist
        cursor.execute('SELECT COUNT(*) FROM subscription_packages')
        if cursor.fetchone()[0] > 0:
            print("✅ Subscription packages already exist")
            return True
        
        # Define default packages
        packages = [
            {
                'name': 'Admin',
                'description': 'Basic admin access for single organization',
                'max_organizations': 1,
                'price': 0.0,
                'features': '{"member_management": true, "payment_processing": true, "basic_reports": true}'
            },
            {
                'name': 'Super Admin (1-5 Orgs)',
                'description': 'Super admin access for up to 5 organizations',
                'max_organizations': 5,
                'price': 49.99,
                'features': '{"member_management": true, "payment_processing": true, "advanced_reports": true, "multi_org": true, "communication_center": true}'
            },
            {
                'name': 'Super Admin (1-10 Orgs)',
                'description': 'Super admin access for up to 10 organizations',
                'max_organizations': 10,
                'price': 99.99,
                'features': '{"member_management": true, "payment_processing": true, "advanced_reports": true, "multi_org": true, "communication_center": true, "priority_support": true}'
            },
            {
                'name': 'Super Admin (10+ Orgs)',
                'description': 'Unlimited super admin access for enterprise',
                'max_organizations': 9999,
                'price': 199.99,
                'features': '{"member_management": true, "payment_processing": true, "advanced_reports": true, "multi_org": true, "communication_center": true, "priority_support": true, "white_label": true, "api_access": true}'
            }
        ]
        
        # Insert packages
        for pkg in packages:
            cursor.execute('''
                INSERT INTO subscription_packages (name, description, max_organizations, price, features, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (pkg['name'], pkg['description'], pkg['max_organizations'], pkg['price'], pkg['features']))
        
        db.commit()
        print("✅ Subscription packages initialized successfully")
        return True
        
    except Exception as e:
        print(f"Error initializing subscription packages: {e}")
        return False

def get_user_package(user_id):
    """Get user's subscription package details"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT sp.id, sp.name, sp.description, sp.max_organizations, sp.price, sp.features
            FROM users u
            LEFT JOIN subscription_packages sp ON u.subscription_package_id = sp.id
            WHERE u.id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        if result and result[0]:
            return {
                'id': result[0],
                'name': result[1],
                'description': result[2],
                'max_organizations': result[3],
                'price': result[4],
                'features': result[5]
            }
        return None
        
    except Exception as e:
        print(f"Error getting user package: {e}")
        return None

def get_user_organization_count(user_id):
    """Get count of organizations a user has created/owns
    
    Counts organizations created by this user. Uses created_by_user_id if available,
    otherwise falls back to checking user's role and assigned organization.
    """
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if user is Global Super Admin
        cursor.execute('SELECT is_global_superadmin, organization_id FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            return 0
        
        is_global_superadmin = result[0]
        user_org_id = result[1]
        
        # Global Super Admin is exempt from limits (can create unlimited orgs)
        # Return current count for informational purposes
        if is_global_superadmin:
            cursor.execute('SELECT COUNT(*) FROM organizations WHERE status = "active"')
            count = cursor.fetchone()[0]
            return count
        
        # Check if created_by_user_id column exists (newer schema)
        cursor.execute("PRAGMA table_info(organizations)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'created_by_user_id' in columns:
            # Count organizations created by this user
            cursor.execute('''
                SELECT COUNT(*) FROM organizations 
                WHERE created_by_user_id = ? AND status = "active"
            ''', (user_id,))
            count = cursor.fetchone()[0]
            return count
        else:
            # Fallback: For other users, they are limited to their organization
            # (In the current design, each user belongs to ONE organization)
            if user_org_id:
                return 1
            return 0
        
    except Exception as e:
        print(f"Error getting organization count: {e}")
        return 0

def check_organization_limit(user_id):
    """Check if user can add more organizations based on their package"""
    try:
        package = get_user_package(user_id)
        if not package:
            return False, "No subscription package assigned"
        
        current_count = get_user_organization_count(user_id)
        max_allowed = package['max_organizations']
        
        if current_count >= max_allowed:
            return False, f"Organization limit reached. Your package allows {max_allowed} organizations."
        
        return True, None
        
    except Exception as e:
        print(f"Error checking organization limit: {e}")
        return False, "Error checking organization limit"

def can_add_organization(user_id):
    """Simple boolean check for organization limit"""
    can_add, _ = check_organization_limit(user_id)
    return can_add

def enforce_existing_limits():
    """Enforce organization limits on existing records"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get all users with their package info
        cursor.execute('''
            SELECT u.id, u.username, sp.max_organizations
            FROM users u
            LEFT JOIN subscription_packages sp ON u.subscription_package_id = sp.id
            WHERE u.subscription_package_id IS NOT NULL
        ''')
        
        users = cursor.fetchall()
        violations = []
        
        for user_id, username, max_orgs in users:
            if max_orgs is None:
                continue
                
            current_count = get_user_organization_count(user_id)
            if current_count > max_orgs:
                violations.append({
                    'user_id': user_id,
                    'username': username,
                    'current_count': current_count,
                    'max_allowed': max_orgs
                })
        
        if violations:
            print(f"⚠️  Found {len(violations)} users exceeding their package limits:")
            for violation in violations:
                print(f"   - {violation['username']}: {violation['current_count']} orgs (max: {violation['max_allowed']})")
        else:
            print("✅ All users are within their package limits")
            
        return violations
        
    except Exception as e:
        print(f"Error enforcing existing limits: {e}")
        return []

# ============================================================================
# AUDIT LOGGING SYSTEM
# ============================================================================

def log_audit(action, table_name=None, record_id=None, old_values=None, new_values=None):
    """Log audit trail for user actions"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get user information from session
        user_id = session.get('user_id')
        username = session.get('username')
        org_id = session.get('organization_id')
        
        # Get IP address and user agent
        ip_address = request.remote_addr if request else None
        user_agent = request.user_agent.string if request and request.user_agent else None
        
        # Convert old/new values to JSON
        old_values_json = json.dumps(old_values) if old_values else None
        new_values_json = json.dumps(new_values) if new_values else None
        
        cursor.execute('''
            INSERT INTO audit_logs 
            (user_id, username, action, table_name, record_id, old_values, new_values, 
             ip_address, user_agent, organization_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, action, table_name, record_id, old_values_json, new_values_json,
              ip_address, user_agent, org_id))
        
        db.commit()
        return True
        
    except Exception as e:
        print(f"Error logging audit: {e}")
        return False

def get_audit_logs(limit=100, action=None, user_id=None, table_name=None, start_date=None, end_date=None):
    """Retrieve audit logs with filters"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Build filter conditions
        conditions = []
        params = []
        
        # Organization filter (for non-global admins)
        if not is_global_superadmin():
            conditions.append('organization_id = ?')
            params.append(org_id)
        
        # Action filter
        if action:
            conditions.append('action = ?')
            params.append(action)
        
        # User filter
        if user_id:
            conditions.append('user_id = ?')
            params.append(user_id)
        
        # Table filter
        if table_name:
            conditions.append('table_name = ?')
            params.append(table_name)
        
        # Date range filter
        if start_date:
            conditions.append('date(created_at) >= ?')
            params.append(start_date)
        
        if end_date:
            conditions.append('date(created_at) <= ?')
            params.append(end_date)
        
        where_clause = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
        
        cursor.execute(f'''
            SELECT 
                id, user_id, username, action, table_name, record_id, 
                old_values, new_values, ip_address, created_at
            FROM audit_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        ''', params + [limit])
        
        return cursor.fetchall()
        
    except Exception as e:
        print(f"Error retrieving audit logs: {e}")
        return []

def calculate_deduction_fee(amount):
    """Calculate fee for prepaid deductions"""
    fee_percentage = get_deduction_fee_percentage()
    return amount * (fee_percentage / 100)

def apply_deduction_fee(membership_id, organization_id, amount, admin_user_id, description="", input_currency=None, original_amount=None, original_currency=None):
    """Apply deduction with fee calculation"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Simplified: No currency conversion, just use amount as-is
        deduction_amount = float(amount)
        
        # Get current balance
        balance_info = get_prepaid_balance(membership_id, organization_id)
        if not balance_info:
            return False, "Could not retrieve balance information"
        
        current_balance = balance_info['current_balance']
        
        if current_balance < deduction_amount:
            return False, "Insufficient balance for deduction"
        
        # Calculate fee (only on deductions, not recharges)
        fee_amount = calculate_deduction_fee(deduction_amount)
        total_deduction = deduction_amount + fee_amount
        
        if current_balance < total_deduction:
            return False, f"Insufficient balance. Required: {total_deduction:.2f} (including {fee_amount:.2f} fee)"
        
        # Update balance
        new_balance = current_balance - total_deduction
        
        cursor.execute('''
            UPDATE prepaid_balances 
            SET current_balance = ?, total_spent = total_spent + ?, updated_at = datetime('now')
            WHERE membership_id = ? AND organization_id = ?
        ''', (new_balance, total_deduction, membership_id, organization_id))
        
        # Record deduction transaction
        cursor.execute('''
            INSERT INTO prepaid_transactions 
            (membership_id, organization_id, transaction_type, amount, balance_before, balance_after, 
             description, admin_user_id, transaction_date)
            VALUES (?, ?, 'usage', ?, ?, ?, ?, ?, datetime('now'))
        ''', (membership_id, organization_id, deduction_amount, current_balance, new_balance, 
              f"{description} (Fee: {fee_amount:.2f})", admin_user_id))
        
        # Record fee transaction
        cursor.execute('''
            INSERT INTO prepaid_transactions 
            (membership_id, organization_id, transaction_type, amount, balance_before, balance_after, 
             description, admin_user_id, transaction_date)
            VALUES (?, ?, 'fee', ?, ?, ?, ?, ?, datetime('now'))
        ''', (membership_id, organization_id, fee_amount, new_balance, new_balance, 
              f"Service fee ({get_deduction_fee_percentage()}%)", admin_user_id))
        
        # ✅ SEND NOTIFICATION (THIS WAS MISSING!)
        currency_symbol = get_currency_symbol()
        detailed_description = f"{description} (includes {currency_symbol}{fee_amount:.2f} service fee)"
        send_usage_notification(membership_id, organization_id, total_deduction, new_balance, detailed_description)

        db.commit()
        
        # Create success message (simplified - no currency conversion)
        return True, f"Deduction successful. Amount: {deduction_amount:.2f}, Fee: {fee_amount:.2f}, Total: {total_deduction:.2f}"
        
    except Exception as e:
        print(f"Error applying deduction with fee: {e}")
        return False, f"Error processing deduction: {e}"

# ============================================================================
# SETTINGS FUNCTIONS
# ============================================================================

def get_setting(key, default_value=None, organization_id=None):
    """Get a setting value from the database"""
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            
            if organization_id:
                cursor.execute('SELECT setting_value FROM settings WHERE setting_key = ? AND organization_id = ?', 
                             (key, organization_id))
            else:
                cursor.execute('SELECT setting_value FROM global_settings WHERE setting_key = ?', (key,))
            
            result = cursor.fetchone()
            return result[0] if result else default_value
    except sqlite3.Error as e:
        print(f"Error getting setting {key}: {e}")
        return default_value


def get_currency_symbol():
    """Get the current currency symbol"""
    return get_setting('currency_symbol', '$')

def get_currency_code():
    """Get the current currency code"""
    return get_setting('currency_code', 'USD')

def get_default_language():
    """Get the default language setting"""
    return get_setting('default_language', 'en')

def fix_database_schema():
    """Fix missing columns in existing database - only if tables exist"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()

            print("🔧 Checking and fixing database schema...")

            # First check if any tables exist at all
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]

            if not existing_tables:
                print("ℹ️  No tables found. Will run full initialization...")
                return True  # Let init_db() handle everything

            print(f"Found existing tables: {existing_tables}")

            # Only fix members table if it exists - ADD PHOTO COLUMN
            if 'members' in existing_tables:
                cursor.execute("PRAGMA table_info(members)")
                member_columns = [column[1] for column in cursor.fetchall()]

                if 'photo_filename' not in member_columns:
                    print("Adding 'photo_filename' column to members table...")
                    cursor.execute('ALTER TABLE members ADD COLUMN photo_filename TEXT')

            # ... rest of existing fix_database_schema code ...

            conn.commit()
            print("✅ Database schema updated successfully!")
            return True

    except Exception as e:
        print(f"❌ Error fixing database schema: {e}")
        return False

# ============================================================================
# BABEL/LANGUAGE CONFIGURATION
# ============================================================================

babel = Babel()
babel.init_app(app)

LANGUAGES = {
    'en': 'English',
    'fr': 'Français', 
    'es': 'Español'
}

def get_current_locale():
    """Get current locale without causing recursion"""
    if request.args.get('lang'):
        session['language'] = request.args.get('lang')
    
    if 'language' in session and session['language'] in LANGUAGES:
        return session['language']
    
    return request.accept_languages.best_match(LANGUAGES.keys()) or 'en'


@app.context_processor
def inject_currency():
    """Make currency symbol and code available in all templates with proper updates"""
    org_name = None
    currency_symbol = '$'  # Default fallback
    currency_code = 'USD'  # Default fallback
    current_lang = 'en'    # Default fallback
    
    try:
        # Get organization info if user is logged in
        if 'organization_id' in session and 'user_id' in session:
            db = get_db()
            cursor = db.cursor()
            
            org_id = session['organization_id']
            
            # Get organization name
            cursor.execute("SELECT name FROM organizations WHERE id = ?", (org_id,))
            result = cursor.fetchone()
            if result:
                org_name = result[0] if isinstance(result, tuple) else result["name"]
            
            # Get currency settings for this organization
            currency_symbol = get_setting('currency_symbol', '$', org_id) or '$'
            currency_code = get_setting('currency_code', 'USD', org_id) or 'USD'
            current_lang = get_setting('default_language', 'en', org_id) or 'en'
            
            # Update session with current language if it's different
            if session.get('language') != current_lang:
                session['language'] = current_lang
        
        # Use session language if available
        if 'language' in session:
            current_lang = session['language']
        
        # Ensure current language is valid
        if current_lang not in LANGUAGES:
            current_lang = 'en'

        return {
            'LANGUAGES': LANGUAGES,
            'CURRENT_LANGUAGE': current_lang,
            'currency_symbol': currency_symbol,
            'currency_code': currency_code,
            'user_preferred_currency': get_user_preferred_currency(),
            'organization_name': org_name,
            'is_global_superadmin': is_global_superadmin(),
            'is_org_superadmin': is_org_superadmin(),
            'has_org_superadmin_capabilities': has_org_superadmin_capabilities(),
            'convert_price_to_user_currency': convert_price_to_user_currency,
            'get_supported_currencies': get_supported_currencies
        }

    except Exception as e:
        print(f"Error in context processor: {e}")
        # Return safe defaults on error
        return {
            'LANGUAGES': LANGUAGES,
            'CURRENT_LANGUAGE': 'en',
            'currency_symbol': '$',
            'currency_code': 'USD',
            'user_preferred_currency': 'USD',
            'organization_name': None,
            'is_global_superadmin': False,
            'is_org_superadmin': False,
            'has_org_superadmin_capabilities': False,
            'convert_price_to_user_currency': convert_price_to_user_currency,
            'get_supported_currencies': get_supported_currencies
        }

# Enhanced currency functions that refresh from database
def get_currency_symbol(force_refresh=False):
    """Get the current currency symbol with optional force refresh"""
    try:
        if 'organization_id' in session:
            org_id = session['organization_id']
            return get_setting('currency_symbol', '$', org_id) or '$'
        return '$'
    except Exception:
        return '$'

def get_currency_code(force_refresh=False):
    """Get the current currency code with optional force refresh"""
    try:
        if 'organization_id' in session:
            org_id = session['organization_id']
            return get_setting('currency_code', 'USD', org_id) or 'USD'
        return 'USD'
    except Exception:
        return 'USD'

def get_default_language(force_refresh=False):
    """Get the default language setting with optional force refresh"""
    try:
        if 'organization_id' in session:
            org_id = session['organization_id']
            return get_setting('default_language', 'en', org_id) or 'en'
        return 'en'
    except Exception:
        return 'en'

# ============================================================================
# DISCOUNT VALIDATION FUNCTIONS
# ============================================================================

def validate_discount_code(code, amount, membership_id=None):
    """Validate discount code and return discount info"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        org_id = session.get('organization_id')
        cursor.execute('''
            SELECT id, code, discount_type, discount_value, min_amount, 
                   max_uses, current_uses, start_date, end_date, status
            FROM discounts 
            WHERE code = ? AND organization_id = ? AND status = 'active'
        ''', (code.upper(), org_id))
        
        discount = cursor.fetchone()
        
        if not discount:
            return None, "Invalid or inactive discount code"
        
        discount_id, code, discount_type, discount_value, min_amount, max_uses, current_uses, start_date, end_date, status = discount
        
        # Check date validity
        today = datetime.now().date()
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            if today < start:
                return None, "Discount code not yet active"
        
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            if today > end:
                return None, "Discount code has expired"
        
        # Check usage limits
        if max_uses and current_uses >= max_uses:
            return None, "Discount code usage limit reached"
        
        # Check minimum amount
        if amount < min_amount:
            return None, f"Minimum amount of {get_currency_symbol()}{min_amount} required"
        
        # Check if user already used this discount
        if membership_id:
            cursor.execute('''
                SELECT COUNT(*) FROM discount_usage 
                WHERE discount_id = ? AND membership_id = ? AND organization_id = ?
            ''', (discount_id, membership_id, org_id))
            if cursor.fetchone()[0] > 0:
                return None, "You have already used this discount code"
        
        # Calculate discount amount
        if discount_type == 'percentage':
            discount_amount = amount * (discount_value / 100)
        else:  # fixed
            discount_amount = discount_value
        
        discount_amount = min(discount_amount, amount)
        
        return {
            'id': discount_id,
            'code': code,
            'type': discount_type,
            'value': discount_value,
            'amount': discount_amount,
            'final_amount': amount - discount_amount
        }, None
        
    except Exception as e:
        return None, f"Error validating discount: {e}"

def apply_discount(discount_id, membership_id, amount_saved):
    """Apply discount and update usage"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        org_id = session.get('organization_id')
        
        cursor.execute('''
            INSERT INTO discount_usage (discount_id, membership_id, amount_saved, organization_id)
            VALUES (?, ?, ?, ?)
        ''', (discount_id, membership_id, amount_saved, org_id))
        
        cursor.execute('''
            UPDATE discounts 
            SET current_uses = current_uses + 1 
            WHERE id = ?
        ''', (discount_id,))
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error applying discount: {e}")
        return False

# ============================================================================
# ROUTES - AUTHENTICATION
# =======================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Enhanced login route with comprehensive error handling"""
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            print(f"🔐 Login attempt for username: {username}")

            if not username or not password:
                flash('❌ Username and password are required.', 'danger')
                return render_template('login.html')

            # Use safe login query
            user_data = safe_login_query(username)

            if not user_data:
                print(f"❌ User not found: {username}")
                flash('❌ Invalid username or password.', 'danger')
                return render_template('login.html')

            # Convert to dict for easier access
            user = {
                'id': user_data[0],
                'username': user_data[1],
                'email': user_data[2],
                'password_hash': user_data[3],
                'organization_id': user_data[4],
                'is_admin': user_data[5] if len(user_data) > 5 else 0,
                'is_superadmin': user_data[6] if len(user_data) > 6 else 0,
                'is_global_superadmin': user_data[7] if len(user_data) > 7 else 0,
                'is_global_admin': user_data[8] if len(user_data) > 8 else 0,
                'org_name': user_data[9] if len(user_data) > 9 else 'Unknown',
                'org_status': user_data[10] if len(user_data) > 10 else 'active',
                'location_id': user_data[11] if len(user_data) > 11 else None,
                'location_name': user_data[12] if len(user_data) > 12 else None
            }

            print(f"✅ User found: {user['username']}, Admin: {user['is_admin']}, SuperAdmin: {user['is_superadmin']}, GlobalSuper: {user['is_global_superadmin']}, GlobalAdmin: {user['is_global_admin']}")

            # Verify password
            if not check_password_hash(user['password_hash'], password):
                print(f"❌ Invalid password for user: {username}")
                flash('❌ Invalid username or password.', 'danger')
                return render_template('login.html')

            # Check organization status (except for global superadmin)
            if not user['is_global_superadmin'] and user['org_status'] != 'active':
                flash('❌ Your organization is currently inactive. Please contact support.', 'danger')
                return render_template('login.html')

            # Clear and set session
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email'] or ''
            session['organization_id'] = user['organization_id']
            session['organization_name'] = user['org_name'] or 'Unknown'
            session['location_id'] = user['location_id']  # NEW: Store location assignment
            session['location_name'] = user['location_name']  # NEW: Store location name
            session['is_admin'] = bool(user['is_admin'])
            session['is_superadmin'] = bool(user['is_superadmin'])
            session['is_global_superadmin'] = bool(user['is_global_superadmin'])
            # Global admin role is deprecated - set to False
            session['is_global_admin'] = False
            session['admin'] = True  # Legacy compatibility

            print(f"✅ Session created for {username}")
            print(f"   Organization: {session.get('organization_name')}")
            print(f"   Location: {session.get('location_name', 'N/A')}")
            print(f"   Permissions: Admin={session.get('is_admin')}, Super={session.get('is_superadmin')}, GlobalSuper={session.get('is_global_superadmin')}, GlobalAdmin={session.get('is_global_admin')}")

            flash(f'✅ Welcome back, {username}!', 'success')

            if session['is_global_superadmin']:
                flash('🌟 Global Superadmin access granted.', 'info')
            elif session['is_superadmin']:
                flash(f'🏢 Organization Superadmin access for {session.get("organization_name", "Unknown")}.', 'info')
            elif session['is_admin']:
                location_name = session.get('location_name')
                org_name = session.get("organization_name", "Unknown")
                if location_name:
                    flash(f'📍 Location Admin access for {location_name} ({org_name}).', 'info')
                else:
                    flash(f'👤 Organization Admin access for {org_name}.', 'info')

            return redirect(url_for('dashboard'))

        except Exception as e:
            print(f"❌ Unexpected error during login: {e}")
            flash('❌ Login error. Please try again.', 'danger')

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Organization Super Admin signup - Creates new organization with full admin privileges"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        org_name = request.form.get('org_name', '').strip()
        industry = request.form.get('industry', '').strip()
        location = request.form.get('location', '').strip()
        
        # Validation
        errors = []
        if not all([username, email, password, org_name, location]):
            errors.append('Username, email, password, organization name, and location are required')
        if len(username) < 3:
            errors.append('Username must be at least 3 characters long')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters long')
        if '@' not in email:
            errors.append('Please enter a valid email address')
        if len(org_name) < 2:
            errors.append('Organization name must be at least 2 characters long')
        if len(location) < 2:
            errors.append('Location must be at least 2 characters long')
            
        if errors:
            for error in errors:
                flash(f'❌ {error}', 'danger')
            return render_template('signup.html')
        
        try:
            db = get_db()
            cursor = db.cursor()
            
            # Check if username already exists globally
            cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?)', (username,))
            if cursor.fetchone():
                flash('❌ Username already exists. Please choose a different one.', 'danger')
                return render_template('signup.html')
            
            # Check if email already exists globally
            cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(?)', (email,))
            if cursor.fetchone():
                flash('❌ Email already registered. Please use a different email.', 'danger')
                return render_template('signup.html')
            
            # Check if organization with same name AND location already exists
            cursor.execute('''
                SELECT id FROM organizations 
                WHERE LOWER(name) = LOWER(?) AND LOWER(location) = LOWER(?)
            ''', (org_name, location))
            existing_org = cursor.fetchone()
            
            if existing_org:
                flash('❌ An organization with this name already exists at this location. Please choose a different name or location.', 'danger')
                return render_template('signup.html')
            
            # Create new organization with default settings
            # Location is now required, no default fallback
            
            cursor.execute('''
                INSERT INTO organizations (name, industry, location, status, subscription_package_id, created_by_user_id) 
                VALUES (?, ?, ?, 'active', 1, NULL)
            ''', (org_name, industry or 'Not Specified', location))
            org_id = cursor.lastrowid
            
            # Update created_by_user_id after user is created
            # This will be set in a later step
            
            # Create Organization Super Admin user
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            
            # Generate unique user ID
            user_id = generate_unique_user_id(org_id, "USR")
            
            cursor.execute('''
                INSERT INTO users (user_id, username, email, password_hash, organization_id, 
                                 is_admin, is_superadmin, is_global_superadmin, subscription_package_id, created_by)
                VALUES (?, ?, ?, ?, ?, 1, 1, 0, 1, NULL)
            ''', (user_id, username, email, password_hash, org_id))
            
            new_user_id = cursor.lastrowid
            
            # Update organization to track who created it
            cursor.execute('''
                UPDATE organizations 
                SET created_by_user_id = ? 
                WHERE id = ?
            ''', (new_user_id, org_id))
            
            db.commit()
            
            # Log the creation in audit logs
            try:
                log_audit(
                    action='ORG_SUPERADMIN_SIGNUP',
                    table_name='users',
                    record_id=new_user_id,
                    new_values={
                        'user_id': user_id,
                        'username': username,
                        'email': email,
                        'organization_id': org_id,
                        'organization_name': org_name,
                        'is_admin': True,
                        'is_superadmin': True,
                        'role': 'Organization Super Admin',
                        'signup_method': 'public_signup'
                    }
                )
            except Exception as log_error:
                print(f"Warning: Failed to log audit entry: {log_error}")
            
            # Send welcome email to the new Organization Super Admin
            email_sent = False
            try:
                send_org_superadmin_welcome_email(username, email, org_name, user_id)
                email_sent = True
            except Exception as email_error:
                print(f"Warning: Failed to send welcome email: {email_error}")
            
            flash('🎉 Organization Super Admin account created successfully! You now have full administrative privileges for your organization.', 'success')
            if email_sent:
                flash('📧 A welcome email has been sent to your registered email address.', 'info')
            else:
                flash('⚠️ Welcome email could not be sent. Please verify your email configuration.', 'warning')
            return redirect(url_for('login'))
            
        except sqlite3.IntegrityError as e:
            db.rollback()
            flash('❌ Account creation failed. Please try again.', 'danger')
            print(f"Database error: {e}")
        except Exception as e:
            db.rollback()
            flash('❌ An unexpected error occurred during signup. Please try again.', 'danger')
            print(f"Error during signup: {e}")
    
    return render_template('signup.html')

@app.route('/check-global-admin-status')
def check_global_admin_status():
    """Check if global admins exist (for conditional UI display)"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_global_superadmin = 1')
        global_admin_count = cursor.fetchone()[0]
        return jsonify({'global_admins_exist': global_admin_count > 0})
    except Exception as e:
        return jsonify({'global_admins_exist': True, 'error': str(e)})

@app.route('/admin/signup', methods=['GET', 'POST'])
def admin_signup():
    """Global admin signup with secret key - RESTRICTED ACCESS"""
    # Check if user is already logged in as global superadmin
    if session.get('is_global_superadmin'):
        flash('You are already logged in as a Global Superadmin.', 'info')
        return redirect(url_for('dashboard'))
    
    # Check if there are already global superadmins (prevent multiple global admins)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_global_superadmin = 1')
        global_admin_count = cursor.fetchone()[0]
        
        if global_admin_count > 0:
            flash('Global Superadmin accounts already exist. Contact system administrator for access.', 'warning')
            return redirect(url_for('login'))
    except Exception as e:
        print(f"Error checking global admin count: {e}")
        flash('System error. Please try again later.', 'danger')
        return redirect(url_for('login'))

@app.route('/global-admin/signup', methods=['GET', 'POST'])
def global_admin_signup():
    """Global Admin signup - requires Global Superadmin approval"""
    # Only allow if user is logged in as Global Superadmin
    if not is_global_superadmin():
        flash('Access denied. Global Superadmin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        errors = []
        if not all([username, email, password]):
            errors.append('Username, email, and password are required')
        if password != confirm_password:
            errors.append('Passwords do not match')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters long')
        if '@' not in email:
            errors.append('Please enter a valid email address')
        
        if errors:
            for error in errors:
                flash(f'❌ {error}', 'error')
        else:
            try:
                db = get_db()
                cursor = db.cursor()
                
                # Check if username already exists
                cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?)', (username,))
                if cursor.fetchone():
                    flash('❌ Username already exists. Please choose a different one.', 'error')
                else:
                    # Check if email already exists
                    cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(?)', (email,))
                    if cursor.fetchone():
                        flash('❌ Email already registered. Please use a different email.', 'error')
                    else:
                        # Create Global Admin account
                        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                        
                        cursor.execute('''
                            INSERT INTO users (username, email, password_hash, organization_id, 
                                             is_admin, is_superadmin, is_global_superadmin, is_global_admin)
                            VALUES (?, ?, ?, 1, 1, 0, 0, 1)
                        ''', (username, email, password_hash))
                        
                        db.commit()
                        
                        # Log the creation
                        log_audit(
                            action='GLOBAL_ADMIN_CREATED',
                            table_name='users',
                            record_id=cursor.lastrowid,
                            new_values={
                                'username': username,
                                'email': email,
                                'is_global_admin': True,
                                'created_by': session.get('username', 'Unknown')
                            }
                        )
                        
                        flash(f'✅ Global Admin account created successfully for {username}!', 'success')
                        return redirect(url_for('manage_users'))
                        
            except sqlite3.IntegrityError as e:
                db.rollback()
                flash('❌ Error creating account. Please try again.', 'error')
                print(f"Database error: {e}")
            except Exception as e:
                db.rollback()
                flash('❌ An unexpected error occurred', 'error')
                print(f"Error: {e}")
    
    return render_template('global_admin_signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# ============================================================================
# ROUTES - DASHBOARD AND MAIN PAGES
# ============================================================================

@app.route('/')
def index():
    # Serve the memberssync-website index.html as the landing page
    return send_from_directory('memberssync-website', 'index.html')

@app.route('/index.html')
def index_html():
    # Handle requests for /index.html (for navigation links)
    return send_from_directory('memberssync-website', 'index.html')

@app.route('/features.html')
def features():
    return send_from_directory('memberssync-website', 'features.html')

@app.route('/solutions.html')
def solutions():
    return send_from_directory('memberssync-website', 'solutions.html')

@app.route('/pricing.html')
def pricing():
    return send_from_directory('memberssync-website', 'pricing.html')

@app.route('/how-it-works.html')
def how_it_works():
    return send_from_directory('memberssync-website', 'how-it-works.html')

@app.route('/about.html')
def about():
    return send_from_directory('memberssync-website', 'about.html')

@app.route('/contact.html')
def contact():
    return send_from_directory('memberssync-website', 'contact.html')

@app.route('/dashboard')
@require_login
def dashboard():
    """Enhanced dashboard with comprehensive analytics, organization filtering, and check-in statistics"""
    try:
        db = get_db()
        cursor = db.cursor()

        accessible_orgs = get_accessible_organizations()
        selected_org_id = request.args.get('org_id', type=int)
        selected_location_id = request.args.get('location_id', type=int)

        # Organization and location filter logic
        location_id = session.get('location_id') if is_location_admin() else None
        
        if is_global_superadmin():
            if selected_org_id:
                current_org_id = selected_org_id
                if selected_location_id:
                    # Global Super Admin: Filter by specific organization and location
                    org_filter = "WHERE m.organization_id = ? AND m.location_id = ?"
                    org_params = (selected_org_id, selected_location_id)
                else:
                    # Global Super Admin: Filter by organization only
                    org_filter = "WHERE m.organization_id = ?"
                    org_params = (selected_org_id,)
            else:
                # Global Super Admin: No filter (all organizations)
                org_filter = ""
                org_params = ()
                current_org_id = None
        elif is_org_superadmin():
            # Organization Super Admin: Can filter by location within their org
            current_org_id = get_user_organization_id()
            if selected_location_id:
                # Organization Super Admin: Filter by specific location
                org_filter = "WHERE m.organization_id = ? AND m.location_id = ?"
                org_params = (current_org_id, selected_location_id)
            else:
                # Organization Super Admin: All members in their organization
                org_filter = "WHERE m.organization_id = ?"
                org_params = (current_org_id,)
        elif location_id:
            # Location Admin sees only their location's data
            current_org_id = get_user_organization_id()
            org_filter = """WHERE m.organization_id = ? 
                            AND (m.location_id = ? OR EXISTS (
                                SELECT 1 FROM checkins c 
                                WHERE c.membership_id = m.membership_id 
                                AND c.location_id = ?
                                AND c.checkin_time >= datetime('now', '-30 days')
                            ))"""
            org_params = (current_org_id, location_id, location_id)
        else:
            current_org_id = get_user_organization_id()
            org_filter = "WHERE m.organization_id = ?"
            org_params = (current_org_id,)

        # Get comprehensive member statistics
        cursor.execute(f'''
            SELECT
                COUNT(*) as total_members,
                COUNT(CASE WHEN m.status = 'active' THEN 1 END) as active_members,
                COUNT(CASE WHEN m.status = 'expired' THEN 1 END) as expired_members,
                COUNT(CASE WHEN m.payment_status = 'Paid' THEN 1 END) as paid_members,
                COUNT(CASE WHEN m.payment_status = 'Unpaid' THEN 1 END) as unpaid_members
            FROM members m
            {org_filter}
        ''', org_params)
        stats = cursor.fetchone()

        # Get total payments with proper filtering
        if is_global_superadmin():
            if selected_org_id:
                if selected_location_id:
                    # Global Super Admin: Filter by specific organization and location
                    payment_filter = "WHERE p.organization_id = ? AND p.membership_id IN (SELECT membership_id FROM members WHERE organization_id = ? AND location_id = ?)"
                    payment_params = (selected_org_id, selected_org_id, selected_location_id)
                else:
                    # Global Super Admin: Filter by organization only
                    payment_filter = "WHERE p.organization_id = ?"
                    payment_params = (selected_org_id,)
            else:
                # Global Super Admin: No filter (all organizations)
                payment_filter = ""
                payment_params = ()
        elif is_org_superadmin():
            # Organization Super Admin: Can filter by location within their org
            current_org_id = get_user_organization_id()
            if selected_location_id:
                # Organization Super Admin: Filter by specific location
                payment_filter = "WHERE p.organization_id = ? AND p.membership_id IN (SELECT membership_id FROM members WHERE organization_id = ? AND location_id = ?)"
                payment_params = (current_org_id, current_org_id, selected_location_id)
            else:
                # Organization Super Admin: All payments in their organization
                payment_filter = "WHERE p.organization_id = ?"
                payment_params = (current_org_id,)
        elif location_id:
            # Location Admin sees only their location's payments
            current_org_id = get_user_organization_id()
            payment_filter = """WHERE p.organization_id = ? 
                              AND p.membership_id IN (
                                  SELECT membership_id FROM members 
                                  WHERE organization_id = ? AND (
                                      location_id = ? OR membership_id IN (
                                          SELECT membership_id FROM checkins 
                                          WHERE location_id = ?
                                          AND checkin_time >= datetime('now', '-30 days')
                                      )
                                  )
                              )"""
            payment_params = (current_org_id, current_org_id, location_id, location_id)
        else:
            # Default: organization filter
            current_org_id = get_user_organization_id()
            payment_filter = "WHERE p.organization_id = ?"
            payment_params = (current_org_id,)
        
        cursor.execute(f'''
            SELECT COALESCE(SUM(amount), 0) as total_payments
            FROM payments p
            {payment_filter}
        ''', payment_params)
        total_payments = cursor.fetchone()['total_payments']

        # Get prepaid analytics
        if current_org_id:
            prepaid_analytics = get_prepaid_analytics(current_org_id)
        else:
            # Global view - sum all organizations
            cursor.execute('''
                SELECT
                    COALESCE(SUM(current_balance), 0) AS total_balance,
                    COALESCE(SUM(total_recharged), 0) AS total_recharged,
                    COALESCE(SUM(total_spent), 0) AS total_spent,
                    COALESCE(SUM(total_bonus_earned), 0) AS total_bonus,
                    COUNT(*) AS active_cards
                FROM prepaid_balances
                WHERE current_balance > 0
            ''')
            prepaid_result = cursor.fetchone()
            prepaid_analytics = {
                'total_balance': prepaid_result[0] if prepaid_result else 0,
                'total_recharged': prepaid_result[1] if prepaid_result else 0,
                'total_spent': prepaid_result[2] if prepaid_result else 0,
                'total_bonus': prepaid_result[3] if prepaid_result else 0,
                'active_cards': prepaid_result[4] if prepaid_result else 0,
                'recent_transactions': 0
            }

        # Get check-in statistics for dashboard
        checkin_org_filter = org_filter.replace('m.', 'c.') if org_filter else ""
        cursor.execute(f'''
            SELECT
                COUNT(*) as todays_checkins,
                COUNT(CASE WHEN status = 'checked_in' THEN 1 END) as currently_checked_in,
                COUNT(DISTINCT membership_id) as unique_visitors_today
            FROM checkins c
            {checkin_org_filter}
            {'AND' if checkin_org_filter else 'WHERE'} date(c.checkin_time) = date('now')
        ''', org_params)
        checkin_stats = cursor.fetchone()

        # Get members expiring in next 7 days
        warning_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        cursor.execute(f'''
            SELECT COUNT(*) as expiring_soon
            FROM members m
            {org_filter}
            {'AND' if org_filter else 'WHERE'} m.expiration_date <= ? AND m.status = 'active'
        ''', org_params + (warning_date,))
        expiring_soon = cursor.fetchone()['expiring_soon']

        # Get recent members
        cursor.execute(f'''
            SELECT m.membership_id, m.name, m.membership_type, m.expiration_date, m.status, o.name as org_name
            FROM members m
            JOIN organizations o ON m.organization_id = o.id
            {org_filter}
            ORDER BY m.created_at DESC
            LIMIT 5
        ''', org_params)
        recent_members = cursor.fetchall()

        # Get recent payments
        cursor.execute(f'''
            SELECT p.*, m.name, o.name as org_name
            FROM payments p
            JOIN members m ON p.membership_id = m.membership_id AND p.organization_id = m.organization_id
            JOIN organizations o ON p.organization_id = o.id
            {payment_filter}
            ORDER BY p.date DESC
            LIMIT 10
        ''', payment_params)
        recent_payments = cursor.fetchall()

        # Get recent prepaid transactions (use same filter as payments since both relate to members)
        prepaid_filter = payment_filter.replace('p.', 'pt.') if payment_filter else ""
        cursor.execute(f'''
            SELECT pt.*, m.name
            FROM prepaid_transactions pt
            JOIN members m ON pt.membership_id = m.membership_id AND pt.organization_id = m.organization_id
            {prepaid_filter}
            ORDER BY pt.transaction_date DESC
            LIMIT 5
        ''', payment_params)
        recent_prepaid_transactions = cursor.fetchall()

        # Get expiring memberships (next 30 days)
        cursor.execute(f'''
            SELECT m.*, o.name as org_name
            FROM members m
            JOIN organizations o ON m.organization_id = o.id
            {org_filter}
            {'AND' if org_filter else 'WHERE'} m.expiration_date BETWEEN date('now') AND date('now', '+30 days')
            AND m.status = 'active'
            ORDER BY m.expiration_date ASC
            LIMIT 10
        ''', org_params)
        expiring_memberships = cursor.fetchall()

        # Chart data for member registrations
        cursor.execute(f'''
            SELECT strftime('%Y-%m', m.created_at) as month, COUNT(*)
            FROM members m
            {org_filter}
            GROUP BY month
            ORDER BY month
        ''', org_params)
        member_chart_data = cursor.fetchall()

        member_chart_labels = [row[0] for row in member_chart_data] if member_chart_data else []
        member_chart_values = [row[1] for row in member_chart_data] if member_chart_data else []

        # Chart data for payments
        cursor.execute(f'''
            SELECT strftime('%Y-%m', p.date) as month, SUM(p.amount)
            FROM payments p
            {payment_filter}
            {'AND' if payment_filter else 'WHERE'} p.date IS NOT NULL
            GROUP BY month
            ORDER BY month
        ''', payment_params)
        payment_chart_data = cursor.fetchall()

        payment_chart_labels = [row[0] for row in payment_chart_data] if payment_chart_data else []
        payment_chart_values = [row[1] for row in payment_chart_data] if payment_chart_data else []
        
        # Convert payment chart values to user's preferred currency
        converted_payment_chart_values = []
        for value in payment_chart_values:
            converted_amount, _ = convert_price_to_user_currency(value)
            converted_payment_chart_values.append(converted_amount)

        # Get accessible locations for dropdown
        accessible_locations = []
        if is_org_superadmin():
            # Organization Super Admin: Get locations in their organization
            accessible_locations = get_accessible_locations()
        elif is_global_superadmin():
            # Global Super Admin: Get ALL locations from ALL organizations
            accessible_locations = get_accessible_locations()  # No org_id = all locations

        return render_template('dashboard.html',
            stats=stats,
            recent_payments=recent_payments,
            recent_prepaid_transactions=recent_prepaid_transactions,
            prepaid_analytics=prepaid_analytics,
            checkin_stats=checkin_stats,
            expiring_memberships=expiring_memberships,
            accessible_orgs=accessible_orgs,
            accessible_locations=accessible_locations,
            selected_org_id=selected_org_id,
            selected_location_id=selected_location_id,
            is_global_superadmin=is_global_superadmin(),
            is_org_superadmin=is_org_superadmin(),
            total_members=stats['total_members'],
            active_members=stats['active_members'],
            expired_members=stats['expired_members'],
            paid_members=stats['paid_members'],
            unpaid_members=stats['unpaid_members'],
            total_payments=total_payments,
            expiring_soon=expiring_soon,
            recent_members=recent_members,
            member_chart_labels=member_chart_labels,
            member_chart_values=member_chart_values,
            payment_chart_labels=payment_chart_labels,
            payment_chart_values=converted_payment_chart_values
        )

    except sqlite3.Error as e:
        flash(f"Dashboard error: {e}", "danger")
        return render_template(
            "dashboard.html",
            **default_dashboard_data()
        )



@app.route('/api/locations/<int:org_id>')
@require_login
def api_get_locations(org_id):
    """API endpoint to get locations for an organization"""
    try:
        # Check if user has access to this organization
        if not is_global_superadmin() and get_user_organization_id() != org_id:
            return jsonify({'error': 'Access denied'}), 403
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
        locations = cursor.fetchall()
        
        return jsonify({
            'locations': [{'id': loc[0], 'name': loc[1]} for loc in locations]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/register', methods=['GET', 'POST'])
@require_login
def register():
    """Register member with optional initial prepaid balance and robust error handling"""
    # Restrict global admins from registering members
    if session.get('is_global_superadmin'):
        flash('Global admins cannot register new members. Please use an organization admin account.', 'danger')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        # Input validation
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        membership_type = request.form.get('membership_type', '').strip()
        photo = request.files.get('photo')
        initial_prepaid = request.form.get('initial_prepaid', '0').strip()

        # Validate required fields
        if not name or not phone or not membership_type:
            flash("Name, phone, and membership type are required.", "danger")
            return render_template('register.html')

        # Validate email format if provided
        if email and not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash("Invalid email format.", "danger")
            return render_template('register.html')

        # Enhanced phone validation (Allows International)
        is_valid_phone, phone_error = validate_phone_number_enhanced(phone)
        if not is_valid_phone:
            flash(f"❌ Phone validation error: {phone_error}", "danger")
            flash("📱 Please enter a valid phone number (e.g., +237... or +254...)", "info")
            return render_template('register.html')
        
        # Format phone number to E.164 format (International Standard)
        phone = format_phone_number(phone)
        
        #  Get phone info for logging (optional)
        phone_info = get_phone_info(phone)
        if phone_info.get('is_valid'):
            print(f"📱 Registering member with phone: {phone_info['formatted']}")
            print(f"   Carrier: {phone_info.get('carrier', 'Unknown')}")
            print(f"   Location: {phone_info.get('location', 'Unknown')}")

        # Validate prepaid amount
        try:
            initial_prepaid_amount = float(initial_prepaid) if initial_prepaid else 0.0
            if initial_prepaid_amount < 0:
                flash("Prepaid amount cannot be negative.", "danger")
                return render_template('register.html')
        except ValueError:
            flash("Invalid prepaid amount format.", "danger")
            return render_template('register.html')

        try:
            db = get_db()
            cursor = db.cursor()
            
            # Handle organization assignment for Global Superadmin
            if session.get('is_global_superadmin'):
                org_id = request.form.get('organization_id', type=int)
                if not org_id:
                    flash("Organization is required.", "danger")
                    return render_template('register.html', organizations=get_organizations())
            else:
                org_id = session.get('organization_id', 1)

            # Generate unique membership ID using centralized function
            membership_id = generate_unique_membership_id(org_id, "MBR")
            photo_filename = None

            # Set initial status as pending - will be updated to active after payment
            status = 'Pending'

            # Process photo upload BEFORE database insert
            photo_error = False
            if photo and photo.filename:
                try:
                    photo_filename = process_and_save_photo(photo, membership_id)
                    if not photo_filename:
                        photo_error = True
                except Exception as photo_err:
                    app.logger.error(f"Photo processing error: {photo_err}")
                    photo_error = True

            # Get location_id from form or auto-assign based on user role
            location_id = request.form.get('location_id', type=int)
            
            # Auto-assign for location admin if not provided
            if not location_id and is_location_admin():
                location_id = session.get('location_id')
            
            # Validate location_id is provided
            if not location_id:
                flash('Location is required. Please select a location for this member.', 'danger')
                return render_template('register.html', organizations=get_organizations() if is_global_superadmin() else None)
            
            # Get the user ID of the person creating this member
            created_by = session.get('user_id')
            
            # Insert the new member with the generated ID and pending status
            cursor.execute('''
                INSERT INTO members (membership_id, name, email, phone, membership_type, 
                                  organization_id, location_id, photo_filename, status, payment_status, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'Unpaid', ?)
            ''', (membership_id, name, email, phone, membership_type, org_id, location_id, photo_filename, created_by))

            # Log audit trail for member creation
            log_audit(
                action='CREATE_MEMBER',
                table_name='members',
                record_id=membership_id,
                new_values={
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'membership_type': membership_type,
                    'status': 'pending'
                }
            )

            # Generate QR code
            qr_error = False
            try:
                qr_data = membership_id
                qr_img = qrcode.make(qr_data)

                # Ensure QR codes directory exists
                qr_dir = 'static/qr_codes'
                os.makedirs(qr_dir, exist_ok=True)

                qr_path = f'{qr_dir}/{membership_id}.png'
                qr_img.save(qr_path)
            except Exception as qr_err:
                app.logger.error(f"QR code generation error: {qr_err}")
                qr_error = True

            # Add initial prepaid balance if specified
            prepaid_result = None
            prepaid_error = False
            if initial_prepaid_amount > 0:
                try:
                    admin_user_id = session.get('user_id')
                    success, result = recharge_prepaid_card(
                        membership_id,
                        org_id,
                        initial_prepaid_amount,
                        admin_user_id,
                        "Initial prepaid balance"
                    )
                    if success:
                        prepaid_result = result
                    else:
                        prepaid_error = True
                        app.logger.error(f"Prepaid recharge failed: {result}")
                except Exception as prepaid_err:
                    app.logger.error(f"Prepaid processing error: {prepaid_err}")
                    prepaid_error = True

            # Commit the transaction
            db.commit()

            # Send welcome email
            email_error = False
            if email:
                print(f"DEBUG: Email provided for member: {email}")
                try:
                    # Calculate expiration date for email
                    expiration_date = calculate_expiration_date(membership_type)
                    print(f"DEBUG: Calculated expiration date: {expiration_date}")
                    
                    if prepaid_result and initial_prepaid_amount > 0:
                        # Send email with prepaid info
                        print(f"DEBUG: Sending welcome email with prepaid info")
                        send_welcome_email_with_prepaid(
                            membership_id, name, email, membership_type,
                            expiration_date, initial_prepaid_amount, prepaid_result
                        )
                    else:
                        # Send standard welcome email
                        print(f"DEBUG: Sending standard welcome email")
                        welcome_subject = f"🎉 Welcome to MemberSync! - {membership_id}"
                        exp_date = datetime.strptime(expiration_date, '%Y-%m-%d').strftime('%B %d, %Y')

                        welcome_message = f"""
                        <html>
                        <body>
                            <h2>Welcome to MemberSync!</h2>
                            <p>Dear {name},</p>
                            <p>Thank you for registering with us! Your membership details:</p>
                            <ul>
                                <li><strong>Membership ID:</strong> {membership_id}</li>
                                <li><strong>Membership Type:</strong> {membership_type}</li>
                                <li><strong>Expiration Date:</strong> {exp_date}</li>
                            </ul>
                            <p>Please keep your membership ID for future reference.</p>
                            <p>Best regards,<br>The MemberSync Team</p>
                        </body>
                        </html>
                        """

                        email_sent = send_email_notification(email, welcome_subject, welcome_message)
                        print(f"DEBUG: Email sending result: {email_sent}")
                        if not email_sent:
                            email_error = True
                            print(f"DEBUG: Email sending failed, setting email_error to True")
                except Exception as email_err:
                    print(f"DEBUG: Exception in email sending: {email_err}")
                    app.logger.error(f"Email sending error: {email_err}")
                    email_error = True
            else:
                print(f"DEBUG: No email provided for member, skipping email sending")

            # Build success message with warnings
            success_msg = f"Member registered successfully! Membership ID: {membership_id}"
            warnings = []

            if prepaid_result and initial_prepaid_amount > 0:
                success_msg += f" with initial prepaid balance of {get_currency_symbol()}{prepaid_result['new_balance']:.2f}"
                if prepaid_result.get('bonus_amount', 0) > 0:
                    success_msg += f" (including {get_currency_symbol()}{prepaid_result['bonus_amount']:.2f} bonus)"
                success_msg += "!"

            if prepaid_error:
                warnings.append("Failed to add prepaid balance")
            if photo_error:
                warnings.append("Error processing photo")
            if qr_error:
                warnings.append("QR code could not be generated")
            if email_error:
                warnings.append("Welcome email could not be sent")

            if warnings:
                flash(f"{success_msg} However, some issues occurred: {', '.join(warnings)}.", "warning")
            else:
                flash(success_msg, "success")

            # Redirect based on whether prepaid was used
            if initial_prepaid_amount > 0:
                return redirect(url_for('prepaid_card_management', membership_id=membership_id))
            else:
                return redirect(url_for('payments', membership_id=membership_id))

        except sqlite3.Error as e:
            app.logger.error(f"Database error during registration: {e}")
            flash(f"Database error: {str(e)}", "danger")
            return render_template('register.html')
        except Exception as e:
            app.logger.error(f"Unexpected error during registration: {e}")
            flash("An unexpected error occurred. Please try again.", "danger")
            return render_template('register.html')

    # Get organizations for Global Superadmin
    organizations = get_organizations() if session.get('is_global_superadmin') else []
    
    # Get locations for Organization Super Admin
    locations = []
    if is_org_superadmin() and not is_global_superadmin():
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
        locations = cursor.fetchall()
    
    return render_template('register.html', organizations=organizations, locations=locations)

# Add this missing function for sending welcome email with prepaid info
def send_welcome_email_with_prepaid(membership_id, name, email, membership_type, expiration_date, initial_amount, prepaid_result):
    """Send welcome email with prepaid card information"""
    try:
        currency = get_currency_symbol()
        exp_date = datetime.strptime(expiration_date, '%Y-%m-%d').strftime('%B %d, %Y')

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; text-align: center;">
                <h2>🎉 Welcome to MemberSync!</h2>
            </div>
            <div style="padding: 20px; background: #f8f9fa;">
                <h3>Hello {name}!</h3>
                <p>Thank you for registering with us! Your membership details:</p>

                <div style="background: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4>Membership Information:</h4>
                    <ul>
                        <li><strong>Membership ID:</strong> {membership_id}</li>
                        <li><strong>Membership Type:</strong> {membership_type}</li>
                        <li><strong>Expiration Date:</strong> {exp_date}</li>
                    </ul>
                </div>

                <div style="background: white; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #28a745;">
                    <h4>💳 Your Prepaid Card:</h4>
                    <ul>
                        <li><strong>Initial Recharge:</strong> {currency}{initial_amount:.2f}</li>
                        <li><strong>Bonus Amount:</strong> {currency}{prepaid_result.get('bonus_amount', 0):.2f}</li>
                        <li><strong>Total Balance:</strong> {currency}{prepaid_result['new_balance']:.2f}</li>
                    </ul>
                    <p>You can use your prepaid balance for services and payments!</p>
                </div>

                <p>Please keep your membership ID for future reference.</p>
                <p>Best regards,<br>The MemberSync Team</p>
            </div>
        </body>
        </html>
        """

        return send_email_notification(email, f"🎉 Welcome to MemberSync! - {membership_id}", html_content)

    except Exception as e:
        print(f"Error sending welcome email with prepaid info: {e}")
        return False




# ============================================================================
# ROUTES - MEMBER MANAGEMENT
# ============================================================================

@app.route('/members')
@require_login
def members():
    """View members with organization filtering and search"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        is_superadmin = is_global_superadmin()
        has_org_superadmin_access = has_org_superadmin_capabilities()
        
        search = request.args.get('search', '')
        status_filter = request.args.get('status', '')
        org_filter_id = request.args.get('organization', 'all')
        location_filter_id = request.args.get('location', 'all')
        
        query = '''
            SELECT m.membership_id, m.name, m.email, m.phone, 
                   m.membership_type, m.expiration_date, m.status, 
                   m.organization_id, m.created_at,
                   o.name as organization_name, 
                   l.name as location_name
            FROM members m 
            JOIN organizations o ON m.organization_id = o.id 
            LEFT JOIN locations l ON m.location_id = l.id
'''
        
        params = []
        conditions = []
        
        if is_superadmin:
            # Global Superadmin can filter by organization and location
            if org_filter_id and org_filter_id != 'all':
                conditions.append('m.organization_id = ?')
                params.append(org_filter_id)
                
                # If location filter is also set, add location condition
                if location_filter_id and location_filter_id != 'all':
                    conditions.append('m.location_id = ?')
                    params.append(location_filter_id)
        elif has_org_superadmin_access:
            # Organization Superadmin can see all members in their organization (all locations)
            org_id = session.get('organization_id')
            if org_id:
                conditions.append('m.organization_id = ?')
                params.append(org_id)
                
                # Organization Superadmin can also filter by location within their org
                if location_filter_id and location_filter_id != 'all':
                    conditions.append('m.location_id = ?')
                    params.append(location_filter_id)
            else:
                flash("Organization not found. Please log in again.", "danger")
                return redirect(url_for('login'))
        elif is_location_admin():
            # Location Admin can only see members at their assigned location
            org_id = session.get('organization_id')
            location_id = session.get('location_id')
            if org_id and location_id:
                # Show members assigned to this location OR who recently checked in here
                conditions.append('m.organization_id = ?')
                params.append(org_id)
                conditions.append('''(m.location_id = ? OR EXISTS (
                    SELECT 1 FROM checkins c 
                    WHERE c.membership_id = m.membership_id 
                    AND c.location_id = ?
                    AND c.checkin_time >= datetime('now', '-30 days')
                ))''')
                params.extend([location_id, location_id])
            else:
                flash("Location assignment not found. Please contact your administrator.", "danger")
                return redirect(url_for('dashboard'))
        elif session.get('is_admin') and not session.get('is_superadmin'):
            # Regular admin without location assignment - they need a location!
            org_id = session.get('organization_id')
            location_id = session.get('location_id')
            
            if not location_id:
                flash("⚠️ Your account is not assigned to a location. Please contact your Organization Superadmin to assign you to a store location.", "warning")
                # Show no members until location is assigned
                conditions.append('1=0')  # This will return no results
            else:
                # This admin has a location, treat them as location admin
                if org_id:
                    conditions.append('m.organization_id = ?')
                    params.append(org_id)
                    conditions.append('''(m.location_id = ? OR EXISTS (
                        SELECT 1 FROM checkins c 
                        WHERE c.membership_id = m.membership_id 
                        AND c.location_id = ?
                        AND c.checkin_time >= datetime('now', '-30 days')
                    ))''')
                    params.extend([location_id, location_id])
        else:
            # Non-admin users should not access this page
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for('dashboard'))
        
        if search:
            conditions.append('(m.name LIKE ? OR m.email LIKE ? OR m.membership_id LIKE ?)')
            search_param = f'%{search}%'
            params.extend([search_param, search_param, search_param])
        
        if status_filter and status_filter != 'all':
            conditions.append('m.status = ?')
            params.append(status_filter)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY m.created_at DESC'
        
        cursor.execute(query, params)
        members = cursor.fetchall()
        
        if is_superadmin:
            # Global Superadmin can see all organizations
            cursor.execute('SELECT id, name FROM organizations ORDER BY name')
            accessible_orgs = cursor.fetchall()
        else:
            # Global Admin and others see only their accessible organizations
            accessible_orgs = get_accessible_organizations()
        
        # Get accessible locations for dropdown
        accessible_locations = []
        if is_superadmin and org_filter_id and org_filter_id != 'all':
            # Global Super Admin: Get locations for selected organization
            accessible_locations = get_accessible_locations(int(org_filter_id))
        elif has_org_superadmin_access:
            # Organization Super Admin: Get locations in their organization
            accessible_locations = get_accessible_locations()
        
        return render_template('members.html', 
                             members=members,
                             accessible_orgs=accessible_orgs,
                             accessible_locations=accessible_locations,
                             search_query=search,
                             status_filter=status_filter,
                             is_global_superadmin=is_superadmin,
                             has_org_superadmin_capabilities=has_org_superadmin_access,
                             selected_org=org_filter_id,
                             selected_location=location_filter_id)
        
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return render_template('members.html', 
                             members=[],
                             accessible_orgs=[],
                             search_query='',
                             status_filter='',
                             is_global_superadmin=False,
                             has_org_superadmin_capabilities=False,
                             selected_org='all')


@app.route('/member/<membership_id>')
@require_login
def member_profile(membership_id):
    """
    Display comprehensive member profile with check-in history,
    prepaid balance, and membership details.
    """
    try:
        # Check access first
        if not can_access_member(membership_id):
            flash('Access denied to this member.', 'danger')
            return redirect(url_for('members'))
        
        db = get_db()
        cursor = db.cursor()

        # Get member basic information with organization validation
        cursor.execute('''
            SELECT
                m.membership_id, m.name, m.email, m.phone, m.membership_type,
                m.expiration_date, m.status, m.created_at, m.photo_filename,
                m.organization_id, o.name as organization_name
            FROM members m
            JOIN organizations o ON m.organization_id = o.id
            WHERE m.membership_id = ?
        ''', (membership_id,))

        member = cursor.fetchone()

        if not member:
            flash("Member not found.", "danger")
            return redirect(url_for('members'))

        # Get organization ID from member data - MUST be at top for use in all queries
        org_id = member[9]  # organization_id is at index 9
        print(f"DEBUG - member_profile: org_id = {org_id}, membership_id = {membership_id}")

        # Calculate membership expiration details safely
        days_until_expiry = None
        expiry_status = 'unknown'

        try:
            if member[5]:  # expiration_date exists and is not None
                exp_date = datetime.strptime(member[5], '%Y-%m-%d')
                today = datetime.now()
                # Calculate days as integer
                days_until_expiry = int((exp_date - today).days)

                if days_until_expiry < 0:
                    expiry_status = 'expired'
                elif days_until_expiry <= 7:
                    expiry_status = 'warning'
                else:
                    expiry_status = 'active'
            else:
                days_until_expiry = None
                expiry_status = 'no_expiry'
        except (ValueError, TypeError) as e:
            print(f"Error parsing expiration date for member {membership_id}: {e}")
            days_until_expiry = None
            expiry_status = 'invalid_date'

        # Get prepaid balance
        try:
            prepaid_balance = get_prepaid_balance(membership_id, org_id)
            if not prepaid_balance or not isinstance(prepaid_balance, dict):
                print(f"Warning: prepaid_balance is not a dict. Type: {type(prepaid_balance)}, Value: {prepaid_balance}")
                prepaid_balance = {
                    'current_balance': 0.0,
                    'total_recharged': 0.0,
                    'total_spent': 0.0,
                    'total_bonus_earned': 0.0
                }
            # Ensure all keys exist with default values
            prepaid_balance.setdefault('current_balance', 0.0)
            prepaid_balance.setdefault('total_recharged', 0.0)
            prepaid_balance.setdefault('total_spent', 0.0)
            prepaid_balance.setdefault('total_bonus_earned', 0.0)
        except Exception as e:
            print(f"Error getting prepaid balance for member {membership_id}: {e}")
            import traceback
            traceback.print_exc()
            prepaid_balance = {
                'current_balance': 0.0,
                'total_recharged': 0.0,
                'total_spent': 0.0,
                'total_bonus_earned': 0.0
            }

        # Get recent prepaid transactions
        try:
            cursor.execute('''
                SELECT
                    transaction_type, amount, bonus_amount, balance_after, 
                    transaction_date, description
                FROM prepaid_transactions
                WHERE membership_id = ? AND organization_id = ?
                ORDER BY transaction_date DESC
                LIMIT 5
            ''', (membership_id, org_id))
            recent_prepaid_transactions = cursor.fetchall()
        except Exception as e:
            print(f"Error getting prepaid transactions for member {membership_id}: {e}")
            recent_prepaid_transactions = []

        # Get recent payments
        try:
            cursor.execute('''
                SELECT
                    amount, date, notes, payment_type, discount_amount
                FROM payments
                WHERE membership_id = ? AND organization_id = ?
                ORDER BY date DESC
                LIMIT 5
            ''', (membership_id, org_id))
            recent_payments = cursor.fetchall()
        except Exception as e:
            print(f"Error getting payments for member {membership_id}: {e}")
            recent_payments = []

        # Get current check-in status
        try:
            current_checkin = is_member_checked_in(membership_id, org_id)
            if not current_checkin:
                current_checkin = {'is_checked_in': False}
        except Exception as e:
            print(f"Error getting check-in status for member {membership_id}: {e}")
            current_checkin = {'is_checked_in': False}

        # Get recent check-ins with duration calculation
        try:
            cursor.execute('''
                SELECT
                    checkin_time, checkout_time, service_type, status,
                    CASE
                        WHEN checkout_time IS NOT NULL THEN
                            ROUND((julianday(checkout_time) - julianday(checkin_time)) * 24, 1)
                        ELSE
                            ROUND((julianday('now') - julianday(checkin_time)) * 24, 1)
                    END as duration_hours
                FROM checkins
                WHERE membership_id = ? AND organization_id = ?
                ORDER BY checkin_time DESC
                LIMIT 5
            ''', (membership_id, org_id))
            recent_checkins = cursor.fetchall()
        except Exception as e:
            print(f"Error getting recent check-ins for member {membership_id}: {e}")
            recent_checkins = []

        # Get comprehensive check-in statistics
        try:
            cursor.execute('''
                SELECT
                    COUNT(*) as total_visits,
                    COUNT(CASE
                        WHEN date(checkin_time) >= date('now', '-30 days')
                        THEN 1
                    END) as visits_last_30_days,
                    AVG(CASE
                        WHEN checkout_time IS NOT NULL THEN
                            (julianday(checkout_time) - julianday(checkin_time)) * 24
                        ELSE NULL
                    END) as avg_duration_hours
                FROM checkins
                WHERE membership_id = ? AND organization_id = ?
            ''', (membership_id, org_id))
            checkin_stats = cursor.fetchone()

            # Convert to dict for easier template access
            if checkin_stats:
                checkin_stats = {
                    'total_visits': int(checkin_stats[0]) if checkin_stats[0] is not None else 0,
                    'visits_last_30_days': int(checkin_stats[1]) if checkin_stats[1] is not None else 0,
                    'avg_duration_hours': round(float(checkin_stats[2]) if checkin_stats[2] is not None else 0, 1)
                }
            else:
                checkin_stats = {
                    'total_visits': 0,
                    'visits_last_30_days': 0,
                    'avg_duration_hours': 0
                }
        except Exception as e:
            print(f"Error getting check-in statistics for member {membership_id}: {e}")
            checkin_stats = {
                'total_visits': 0,
                'visits_last_30_days': 0,
                'avg_duration_hours': 0
            }

        return render_template(
            'member_profile.html',
            member=member,
            days_until_expiry=days_until_expiry,
            expiry_status=expiry_status,
            prepaid_balance=prepaid_balance,
            recent_prepaid_transactions=recent_prepaid_transactions,
            recent_payments=recent_payments,
            current_checkin=current_checkin,
            recent_checkins=recent_checkins,
            checkin_stats=checkin_stats
        )

    except sqlite3.Error as e:
        print(f"Database error in member_profile for {membership_id}: {e}")
        flash(f"Database error: {e}", "danger")
        return redirect(url_for('members'))
    except Exception as e:
        print(f"Unexpected error in member_profile for {membership_id}: {e}")
        import traceback
        traceback.print_exc()  # Print full stack trace for debugging
        print(f"DEBUG - prepaid_balance type: {type(prepaid_balance) if 'prepaid_balance' in locals() else 'not set'}")
        print(f"DEBUG - prepaid_balance value: {prepaid_balance if 'prepaid_balance' in locals() else 'not set'}")
        flash(f"An unexpected error occurred: {e}", "danger")
        return redirect(url_for('members'))

@app.route('/edit/<membership_id>', methods=['GET', 'POST'])
@require_login
def edit_member(membership_id):
    """Edit member with proper access control and membership ID immutability"""
    try:
        # Check access first
        if not can_access_member(membership_id):
            flash('Access denied to this member.', 'danger')
            return redirect(url_for('members'))
        
        db = get_db()
        cursor = db.cursor()

        if request.method == 'POST':
            # MEMBERSHIP ID IMMUTABILITY: Prevent any attempts to change membership ID
            submitted_membership_id = request.form.get('membership_id', '').strip()
            if submitted_membership_id and submitted_membership_id != membership_id:
                flash('Membership ID cannot be changed once assigned. This field is immutable for data integrity.', 'danger')
                return redirect(url_for('edit_member', membership_id=membership_id))
            
            name = request.form['name']
            email = request.form['email']
            phone = request.form['phone']
            membership_type = request.form['membership_type']
            expiration_date = request.form['expiration_date']
            photo = request.files.get('photo')
            remove_photo = request.form.get('remove_photo') == 'on'
            
            # Handle status updates (if provided)
            status = request.form.get('status')
            payment_status = request.form.get('payment_status')
            
            # Handle organization assignment for Global Super Admins
            new_organization_id = None
            if is_global_superadmin():
                new_organization_id = request.form.get('organization_id', type=int)

            # Enhanced phone validation
            is_valid_phone, phone_error = validate_phone_number_enhanced(phone)
            if not is_valid_phone:
                flash(f"Phone validation error: {phone_error}", "danger")
                return redirect(url_for('edit_member', membership_id=membership_id))
            
            # Format phone number
            phone = format_phone_number(phone)
            
            # Get organization_id for photo processing
            org_id = session.get('organization_id')

            # Get current photo filename
            cursor.execute('SELECT photo_filename FROM members WHERE membership_id = ?', (membership_id,))
            current_photo = cursor.fetchone()
            current_photo_filename = current_photo[0] if current_photo else None

            new_photo_filename = current_photo_filename

            # Handle photo removal
            if remove_photo and current_photo_filename:
                delete_member_photo(membership_id)
                new_photo_filename = None

            # Handle new photo upload
            elif photo and photo.filename:
                # Delete old photo if exists
                if current_photo_filename:
                    delete_member_photo(membership_id)
                
                # Process and save new photo
                new_photo_filename = process_and_save_photo(photo, membership_id)
                if not new_photo_filename:
                    flash("Error processing new photo. Other changes saved.", "warning")
                    new_photo_filename = current_photo_filename

            # Get old values for audit
            cursor.execute('SELECT name, email, phone, membership_type, expiration_date, organization_id, status, payment_status FROM members WHERE membership_id = ?', (membership_id,))
            old_data = cursor.fetchone()
            old_values = {
                'name': old_data[0],
                'email': old_data[1],
                'phone': old_data[2],
                'membership_type': old_data[3],
                'expiration_date': old_data[4],
                'organization_id': old_data[5],
                'status': old_data[6],
                'payment_status': old_data[7]
            } if old_data else {}
            
            # Prepare update query and values
            update_fields = ['name = ?', 'email = ?', 'phone = ?', 'membership_type = ?', 'expiration_date = ?', 'photo_filename = ?']
            update_values = [name, email, phone, membership_type, expiration_date, new_photo_filename]
            
            # Add status fields if provided
            if status:
                update_fields.append('status = ?')
                update_values.append(status)
            
            if payment_status:
                update_fields.append('payment_status = ?')
                update_values.append(payment_status)
            
            # Add organization change if applicable
            if new_organization_id and new_organization_id != old_values.get('organization_id'):
                update_fields.append('organization_id = ?')
                update_values.append(new_organization_id)
            
            # Add membership_id for WHERE clause
            update_values.append(membership_id)
            
            # Execute the update
            cursor.execute(f'''
                UPDATE members
                SET {', '.join(update_fields)}
                WHERE membership_id = ?
            ''', update_values)

            # Prepare new values for audit log
            new_values = {
                'name': name,
                'email': email,
                'phone': phone,
                'membership_type': membership_type,
                'expiration_date': expiration_date
            }
            
            # Add status fields to new_values if they're being changed
            if status:
                new_values['status'] = status
            if payment_status:
                new_values['payment_status'] = payment_status
            
            # Add organization_id to new_values if it's being changed
            if new_organization_id and new_organization_id != old_values.get('organization_id'):
                new_values['organization_id'] = new_organization_id
            
            # Log audit trail for member update
            log_audit(
                action='UPDATE_MEMBER',
                table_name='members',
                record_id=membership_id,
                old_values=old_values,
                new_values=new_values
            )

            db.commit()
            flash("Member updated successfully!", "success")
            return redirect(url_for('member_profile', membership_id=membership_id))

        cursor.execute('''
            SELECT m.name, m.email, m.phone, m.membership_type, m.expiration_date, m.photo_filename, m.organization_id,
                   o.name as organization_name
            FROM members m
            LEFT JOIN organizations o ON m.organization_id = o.id
            WHERE m.membership_id = ?
        ''', (membership_id,))
        member_data = cursor.fetchone()

        if member_data:
            # Get organizations for Global Super Admins
            organizations = []
            if is_global_superadmin():
                cursor.execute('SELECT id, name, industry FROM organizations WHERE status = "active" ORDER BY name')
                organizations = cursor.fetchall()
            
            return render_template('edit_member.html', 
                                 membership_id=membership_id, 
                                 member=member_data,
                                 organizations=organizations,
                                 is_global_superadmin=is_global_superadmin())
        else:
            flash("Member not found.", "danger")
            return redirect(url_for('members'))

    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return redirect(url_for('members'))

@app.route('/delete/<membership_id>')
@require_login
def delete_member(membership_id):
    """Delete member with proper access control"""
    try:
        # Check access first
        if not can_access_member(membership_id):
            flash('Access denied to this member.', 'danger')
            return redirect(url_for('members'))
        
        db = get_db()
        cursor = db.cursor()

        # Get organization_id for proper deletion
        cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
        member_data = cursor.fetchone()
        
        if not member_data:
            flash("Member not found.", "danger")
            return redirect(url_for('members'))
        
        org_id = member_data[0] if isinstance(member_data, tuple) else member_data['organization_id']

        # Delete member and their related records with organization context
        cursor.execute('''
            DELETE FROM payments 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        cursor.execute('''
            DELETE FROM notifications 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        cursor.execute('''
            DELETE FROM prepaid_transactions 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        cursor.execute('''
            DELETE FROM prepaid_balances 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        cursor.execute('''
            DELETE FROM checkins 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        cursor.execute('''
            DELETE FROM members 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))

        db.commit()

        # Delete QR code file if it exists
        qr_path = f'static/qr_codes/{membership_id}.png'
        if os.path.exists(qr_path):
            os.remove(qr_path)

        # Delete photo file if it exists
        delete_member_photo(membership_id)

        flash("Member deleted successfully!", "success")
        return redirect(url_for('members'))

    except sqlite3.Error as e:
        flash(f"Delete error: {e}", "danger")
        return redirect(url_for('members'))

# ============================================================================
# FIXED PAYMENT ROUTES
# ============================================================================

@app.route('/payments/<membership_id>', methods=['GET', 'POST'])
@require_login
def payments(membership_id):
    """Payments route with access control for viewing and adding payments"""
    try:
        # Check access first
        if not can_access_member(membership_id):
            flash('Access denied to this member.', 'danger')
            return redirect(url_for('members'))
        
        # Prevent global admins from adding payments
        if request.method == 'POST' and session.get('is_global_superadmin'):
            flash('Access denied. Global administrators cannot add payments.', 'danger')
            return redirect(url_for('payments', membership_id=membership_id))
        
        # Get member's organization
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
        member_data = cursor.fetchone()
        
        if not member_data:
            flash("Member not found.", "danger")
            return redirect(url_for('members'))
        
        org_id = member_data[0] if isinstance(member_data, tuple) else member_data['organization_id']

        if request.method == 'POST':
            payment_method = request.form.get('payment_method', 'cash')
            original_amount = float(request.form['amount'])
            notes = request.form['notes']
            discount_code = request.form.get('discount_code', '').strip()
            date = datetime.now().strftime('%Y-%m-%d')
            final_amount = original_amount
            discount_amount = 0

            # Apply discount if provided
            if discount_code:
                discount_info, error = validate_discount_code(discount_code, original_amount, membership_id)
                if discount_info:
                    final_amount = discount_info['final_amount']
                    discount_amount = discount_info['amount']

            if payment_method == 'prepaid':
                # Use prepaid balance with fee calculation
                admin_user_id = session.get('user_id')
                success, result = apply_deduction_fee(
                    membership_id, org_id, final_amount, admin_user_id, 
                    f"Payment: {notes}" if notes else "Membership payment"
                )
                
                if success:
                    # Record the payment in regular payments table too for tracking
                    cursor.execute('''
                        INSERT INTO payments (membership_id, organization_id, original_amount, amount, date, notes, discount_code, discount_amount, payment_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'prepaid')
                    ''', (membership_id, org_id, original_amount, final_amount, date, notes, discount_code, discount_amount))
                    
                    if discount_code and discount_info:
                        apply_discount(discount_info['id'], membership_id, discount_amount)
                    
                    flash(f"Payment processed using prepaid balance! {result}", "success")
                else:
                    flash(f"Prepaid payment failed: {result}", "danger")
            else:
                # Regular cash/card payment
                if discount_code and discount_info:
                    if apply_discount(discount_info['id'], membership_id, discount_amount):
                        cursor.execute('''
                            INSERT INTO payments (membership_id, organization_id, original_amount, amount, date, notes, discount_code, discount_amount)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (membership_id, org_id, original_amount, final_amount, date, notes, discount_code, discount_amount))
                        flash("Payment with discount added successfully!", "success")
                    else:
                        flash("Payment added but discount application failed.", "warning")
                else:
                    cursor.execute('''
                        INSERT INTO payments (membership_id, organization_id, original_amount, amount, date, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (membership_id, org_id, original_amount, final_amount, date, notes))
                    flash("Payment added successfully!", "success")

            # Update member status to active after successful payment
            cursor.execute('''
                UPDATE members 
                SET status = 'active', 
                    payment_status = 'Paid',
                    expiration_date = CASE 
                        WHEN membership_type = 'monthly' THEN date('now', '+1 month')
                        WHEN membership_type = 'quarterly' THEN date('now', '+3 months')
                        WHEN membership_type = 'annual' THEN date('now', '+1 year')
                        ELSE date('now', '+1 year')
                    END
                WHERE membership_id = ? AND organization_id = ?
            ''', (membership_id, org_id))

            db.commit()

        # Get all payments for the member
        cursor.execute('''
            SELECT amount, date, notes, discount_code, discount_amount, original_amount, payment_type
            FROM payments
            WHERE membership_id = ? AND organization_id = ?
            ORDER BY date DESC
        ''', (membership_id, org_id))
        payment_list = cursor.fetchall()
        
        # Get prepaid balance for payment option
        prepaid_balance = get_prepaid_balance(membership_id, org_id)

        return render_template('payments.html',
                             membership_id=membership_id,
                             payments=payment_list,
                             prepaid_balance=prepaid_balance,
                             currency_symbol=get_currency_symbol())

    except sqlite3.Error as e:
        flash(f"Payment error: {e}", "danger")
        return render_template('payments.html',
                             membership_id=membership_id,
                             payments=[],
                             prepaid_balance={'current_balance': 0},
                             currency_symbol=get_currency_symbol())
    except ValueError:
        flash("Invalid amount entered", "danger")
        return render_template('payments.html',
                             membership_id=membership_id,
                             payments=[],
                             prepaid_balance={'current_balance': 0},
                             currency_symbol=get_currency_symbol())

# ============================================================================
# ADDITIONAL UTILITY FUNCTIONS
# ============================================================================

def debug_user_permissions():
    """Debug function to check current user permissions"""
    print(f"Debug - User Session Data:")
    print(f"  user_id: {session.get('user_id')}")
    print(f"  username: {session.get('username')}")
    print(f"  organization_id: {session.get('organization_id')}")
    print(f"  is_admin: {session.get('is_admin')}")
    print(f"  is_superadmin: {session.get('is_superadmin')}")
    print(f"  is_global_superadmin: {session.get('is_global_superadmin')}")
    print(f"  is_global_superadmin(): {is_global_superadmin()}")
    print(f"  is_org_superadmin(): {is_org_superadmin()}")
    print(f"  get_user_organization_id(): {get_user_organization_id()}")

# Add this route for debugging (remove in production)
@app.route('/debug/permissions')
@require_login
def debug_permissions():
    """Debug route to check user permissions"""
    debug_user_permissions()
    
    permissions_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
    <h1>User Permissions Debug</h1>
    <h2>Session Data:</h2>
    <ul>
        <li><strong>User ID:</strong> {session.get('user_id')}</li>
        <li><strong>Username:</strong> {session.get('username')}</li>
        <li><strong>Organization ID:</strong> {session.get('organization_id')}</li>
        <li><strong>Is Admin:</strong> {session.get('is_admin')}</li>
        <li><strong>Is Superadmin:</strong> {session.get('is_superadmin')}</li>
        <li><strong>Is Global Superadmin:</strong> {session.get('is_global_superadmin')}</li>
    </ul>
    
    <h2>Function Results:</h2>
    <ul>
        <li><strong>is_global_superadmin():</strong> {is_global_superadmin()}</li>
        <li><strong>is_org_superadmin():</strong> {is_org_superadmin()}</li>
        <li><strong>get_user_organization_id():</strong> {get_user_organization_id()}</li>
    </ul>
    
    <p><a href="/dashboard">← Back to Dashboard</a></p>
    </body>
    </html>
    """
    
    return permissions_html


######################################################################################################################

@app.route('/member_photo/<membership_id>')
@require_login
def member_photo(membership_id):
    """Serve member photo with proper validation and detailed logging"""
    try:
        print(f"\n🔍 Attempting to serve photo for member: {membership_id}")
        db = get_db()
        cursor = db.cursor()
        
        # Get organization ID from session
        org_id = session.get('organization_id')
        print(f"🔑 Session org_id: {org_id}")
        
        # Verify access to member
        if not can_access_organization_member(membership_id, org_id):
            print(f"❌ Access denied for member {membership_id} in org {org_id}")
            abort(404)
        
        # Query for member's photo filename
        cursor.execute('''
            SELECT photo_filename FROM members 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        result = cursor.fetchone()
        print(f"📋 Database query result: {result}")
        
        if result and result[0]:  # If we have a photo filename
            filename = result[0]
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            abs_filepath = os.path.abspath(filepath)
            print(f"📂 Looking for photo at: {abs_filepath}")
            
            if os.path.exists(filepath):
                print(f"✅ Found photo file, sending...")
                return send_file(filepath, mimetype='image/jpeg')
            else:
                print(f"❌ Photo file not found at: {abs_filepath}")
        else:
            print(f"ℹ️  No photo_filename found in database for member {membership_id}")
        
        # Fall back to default avatar
        default_path = 'static/images/default-avatar.png'
        abs_default_path = os.path.abspath(default_path)
        print(f"🔄 Falling back to default avatar at: {abs_default_path}")
        
        if os.path.exists(default_path):
            print("✅ Found default avatar, sending...")
            return send_file(default_path, mimetype='image/png')
        else:
            print(f"❌ Default avatar not found at: {abs_default_path}")
            abort(404)
            
    except Exception as e:
        import traceback
        print(f"🔥 Error in member_photo route: {str(e)}")
        traceback.print_exc()
        abort(404)


# Add route for QR code verification with photo
@app.route('/verify/<membership_id>')
def verify_member(membership_id):
    """Verify member by QR code scan - shows photo and details"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT m.membership_id, m.name, m.email, m.phone, m.membership_type, 
                   m.expiration_date, m.status, m.created_at, m.photo_filename,
                   o.name as organization_name
            FROM members m
            LEFT JOIN organizations o ON m.organization_id = o.id
            WHERE m.membership_id = ?
        ''', (membership_id,))
        
        member = cursor.fetchone()
        
        if not member:
            return render_template('verify_result.html', 
                                 member=None, 
                                 error="Member not found")
        
        # Calculate expiry information
        expiry_date = None
        days_diff = None
        expiry_status = 'unknown'
        
        if member[5]:  # expiration_date
            try:
                expiry_date = datetime.strptime(member[5], "%Y-%m-%d")
                today = datetime.now().date()
                days_diff = (expiry_date.date() - today).days
                
                if days_diff < 0:
                    expiry_status = 'expired'
                elif days_diff <= 7:
                    expiry_status = 'warning'
                else:
                    expiry_status = 'active'
                    
            except ValueError as e:
                print(f"Date parsing error for member {membership_id}: {e}")
                expiry_status = 'invalid'
        
        return render_template('verify_result.html',
                             member=member,
                             expiry_date=expiry_date,
                             days_diff=days_diff,
                             expiry_status=expiry_status,
                             error=None)
                             
    except sqlite3.Error as e:
        return render_template('verify_result.html', 
                             member=None, 
                             error=f"Database error: {e}")
    except Exception as e:
        return render_template('verify_result.html', 
                             member=None, 
                             error=f"Unexpected error: {e}")




@app.route('/card/<membership_id>')
@require_login
@require_member_access
def member_card(membership_id):
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT membership_id, name, membership_type, email, phone, expiration_date, status, created_at, photo_filename, organization_id
            FROM members
            WHERE membership_id = ?
        ''', (membership_id,))
        
        member = cursor.fetchone()
        
        if not member:
            flash("Member not found.", "danger")
            return redirect(url_for('members'))
        
        # Calculate expiry information
        expiry_date = None
        days_diff = None
        expiry_status = 'unknown'
        
        if member[5]:  # expiration_date
            try:
                expiry_date = datetime.strptime(member[5], "%Y-%m-%d")
                today = datetime.now().date()
                days_diff = (expiry_date.date() - today).days
                
                if days_diff < 0:
                    expiry_status = 'expired'
                elif days_diff <= 7:
                    expiry_status = 'warning'
                else:
                    expiry_status = 'active'
                    
            except ValueError as e:
                print(f"Date parsing error for member {membership_id}: {e}")
                expiry_status = 'invalid'
        
        # Get organization's card design settings
        # First try to get organization_id from the member record
        member_org_id = member[9] if len(member) > 9 else None
        
        # Debug: Print values to understand what's happening
        print(f"DEBUG: Member data length: {len(member)}")
        print(f"DEBUG: Member organization_id: {member_org_id}")
        print(f"DEBUG: Session organization_id: {session.get('organization_id')}")
        
        # Use member's organization_id if available, otherwise use session organization_id
        org_id_to_use = member_org_id if member_org_id else session.get('organization_id')
        
        print(f"DEBUG: Organization ID to use: {org_id_to_use}")
        
        if org_id_to_use:
            cursor.execute('''
                SELECT card_company_name, card_primary_color, card_secondary_color
                FROM organizations
                WHERE id = ?
            ''', (org_id_to_use,))
            
            org_data = cursor.fetchone()
            org = {
                'card_company_name': org_data[0] if org_data and org_data[0] else 'MemberSync',
                'card_primary_color': org_data[1] if org_data and org_data[1] else '#667eea',
                'card_secondary_color': org_data[2] if org_data and org_data[2] else '#764ba2'
            }
        else:
            # Fallback to default values
            org = {
                'card_company_name': 'MemberSync',
                'card_primary_color': '#667eea',
                'card_secondary_color': '#764ba2'
            }
        
        return render_template("member_card.html",
                             member=member,
                             expiry_date=expiry_date,
                             days_diff=days_diff,
                             expiry_status=expiry_status,
                             org=org)
                             
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return redirect(url_for('members'))
    except Exception as e:
        flash(f"Unexpected error: {e}", "danger")
        return redirect(url_for('members'))

# Add this route to your app.py file

@app.route('/send_digital_card_email/<membership_id>', methods=['POST'])
@require_login
@require_member_access
def send_digital_card_email(membership_id):
    """Send digital membership card via email"""
    try:
        # Get form data
        recipient_email = request.form.get('recipientEmail', '').strip()
        email_subject = request.form.get('emailSubject', '').strip()
        email_message = request.form.get('emailMessage', '').strip()
        
        # Validate inputs
        if not recipient_email or '@' not in recipient_email:
            return {'success': False, 'error': 'Valid email address is required'}
        
        if not email_subject:
            return {'success': False, 'error': 'Email subject is required'}
        
        # Get member information
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT membership_id, name, email, phone, membership_type, 
                   expiration_date, status, created_at, organization_id
            FROM members 
            WHERE membership_id = ?
        ''', (membership_id,))
        
        member = cursor.fetchone()
        
        if not member:
            return {'success': False, 'error': 'Member not found'}
        
        # Check if user can access this member's organization
        member_org_id = member[8] if len(member) > 8 else member['organization_id']
        
        if not can_access_organization(member_org_id):
            return {'success': False, 'error': 'Access denied'}
        
        # Handle uploaded card image
        card_image = request.files.get('cardImage')
        
        if not card_image:
            return {'success': False, 'error': 'Card image is required'}
        
        # Save the image temporarily
        import tempfile
        import os
        
        temp_dir = tempfile.mkdtemp()
        image_path = os.path.join(temp_dir, f'card_{membership_id}.png')
        card_image.save(image_path)
        
        try:
            # Prepare email content
            member_name = member[1] if isinstance(member, tuple) else member['name']
            member_type = member[4] if isinstance(member, tuple) else member['membership_type']
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 20px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                    }}
                    .content {{
                        background: #f8f9fa;
                        padding: 20px;
                        border-radius: 0 0 10px 10px;
                    }}
                    .card-preview {{
                        text-align: center;
                        margin: 20px 0;
                        padding: 20px;
                        background: white;
                        border-radius: 10px;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 20px;
                        color: #666;
                        font-size: 14px;
                    }}
                    .btn {{
                        display: inline-block;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 12px 25px;
                        text-decoration: none;
                        border-radius: 25px;
                        margin: 10px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>🎉 Your Digital Membership Card</h1>
                    <p>MemberSync Digital Membership System</p>
                </div>
                
                <div class="content">
                    <h2>Hello {member_name}!</h2>
                    
                    <p>{email_message}</p>
                    
                    <div class="card-preview">
                        <h3>📱 Your Digital Membership Card</h3>
                        <p><strong>Member ID:</strong> {membership_id}</p>
                        <p><strong>Membership Type:</strong> {member_type}</p>
                        <p><em>Your digital membership card is attached to this email as an image.</em></p>
                    </div>
                    
                    <h3>📋 How to use your digital card:</h3>
                    <ul>
                        <li>Save the attached image to your phone's photo gallery</li>
                        <li>Show the card at any of our locations</li>
                        <li>The QR code can be scanned for quick verification</li>
                        <li>Keep this email for your records</li>
                    </ul>
                    
                    <h3>💡 Tips:</h3>
                    <ul>
                        <li>Add the image to your phone's wallet app if supported</li>
                        <li>Take a screenshot for easy access</li>
                        <li>Print the card if you prefer a physical copy</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>This email was sent from MemberSync Digital Membership System</p>
                    <p>If you have any questions, please contact our support team</p>
                    <p><em>Thank you for being a valued member!</em></p>
                </div>
            </body>
            </html>
            """
            
            # Send email with attachment
            success = send_email_with_attachment(
                recipient_email,
                email_subject,
                html_content,
                image_path,
                f'Digital_Membership_Card_{membership_id}.png'
            )
            
            if success:
                # Log the email notification
                cursor.execute('''
                    INSERT INTO notifications (membership_id, organization_id, type, message, sent_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (membership_id, member_org_id, 'digital_card_email', 
                      f'Digital card emailed to {recipient_email}', 
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                
                db.commit()
                
                return {'success': True, 'message': 'Digital card sent successfully!'}
            else:
                return {'success': False, 'error': 'Failed to send email. Please check email configuration.'}
                
        finally:
            # Clean up temporary file
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                os.rmdir(temp_dir)
            except Exception as e:
                print(f"Error cleaning up temp files: {e}")
    
    except Exception as e:
        print(f"Error sending digital card email: {e}")
        return {'success': False, 'error': f'Server error: {str(e)}'}


def send_email_with_attachment(to_email, subject, html_content, attachment_path, attachment_name):
    """Send email with attachment using SMTP"""
    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        import smtplib
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add HTML content
        msg.attach(MIMEText(html_content, 'html'))
        
        # Add attachment
        with open(attachment_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename= {attachment_name}'
        )
        msg.attach(part)
        
        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ADDRESS, to_email, text)
        server.quit()
        
        return True
        
    except Exception as e:
        print(f"Email sending error: {e}")
        return False

@app.route('/physical_card/<membership_id>')
@require_login
@require_global_superadmin
@require_member_access
def physical_card(membership_id):
    """Generate a physical wallet-sized membership card for printing"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT membership_id, name, email, phone, membership_type, 
                   expiration_date, status, created_at, organization_id
            FROM members 
            WHERE membership_id = ?
        ''', (membership_id,))
        
        member = cursor.fetchone()
        
        if not member:
            flash("Member not found.", "danger")
            return redirect(url_for('members'))
        
        # Calculate expiry status (optional for physical card)
        expiry_date = None
        days_diff = None
        expiry_status = 'unknown'
        
        if member[5]:  # expiration_date
            try:
                expiry_date = datetime.strptime(member[5], "%Y-%m-%d")
                today = datetime.now().date()
                days_diff = (expiry_date.date() - today).days
                
                if days_diff < 0:
                    expiry_status = 'expired'
                elif days_diff <= 7:
                    expiry_status = 'warning'
                else:
                    expiry_status = 'active'
                    
            except ValueError as e:
                print(f"Date parsing error for member {membership_id}: {e}")
                expiry_status = 'invalid'
        
        # Get organization's card design settings
        # First try to get organization_id from the member record
        member_org_id = member[8] if len(member) > 8 else None
        
        # Debug: Print values to understand what's happening
        print(f"DEBUG Physical Card: Member data length: {len(member)}")
        print(f"DEBUG Physical Card: Member organization_id: {member_org_id}")
        print(f"DEBUG Physical Card: Session organization_id: {session.get('organization_id')}")
        
        # Use member's organization_id if available, otherwise use session organization_id
        org_id_to_use = member_org_id if member_org_id else session.get('organization_id')
        
        print(f"DEBUG Physical Card: Organization ID to use: {org_id_to_use}")
        
        if org_id_to_use:
            try:
                cursor.execute('''
                    SELECT card_primary_color, card_secondary_color, card_company_name
                    FROM organizations
                    WHERE id = ?
                ''', (org_id_to_use,))
                
                org_data = cursor.fetchone()
                org = {
                    'card_primary_color': org_data[0] if org_data and org_data[0] else '#1e3c72',
                    'card_secondary_color': org_data[1] if org_data and org_data[1] else '#2a5298',
                    'card_company_name': org_data[2] if org_data and org_data[2] else 'MemberSync'
                }
            except sqlite3.OperationalError as e:
                if "no such column" in str(e):
                    # Fallback to default values if columns don't exist
                    org = {
                        'card_primary_color': '#1e3c72',
                        'card_secondary_color': '#2a5298',
                        'card_company_name': 'MemberSync'
                    }
                else:
                    raise e
        else:
            # Fallback to default values
            org = {
                'card_primary_color': '#1e3c72',
                'card_secondary_color': '#2a5298',
                'card_company_name': 'MemberSync'
            }
        
        # Render the physical card template
        return render_template("physical_card.html",
                             member=member,
                             org=org,
                             expiry_date=expiry_date,
                             days_diff=days_diff,
                             expiry_status=expiry_status)
                             
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return redirect(url_for('members'))
    except Exception as e:
        flash(f"Unexpected error: {e}", "danger")
        return redirect(url_for('members'))


# Add this route for generating a standalone digital card page (for email links)
@app.route('/digital_card/<membership_id>')
def standalone_digital_card(membership_id):
    """Generate a standalone digital card page that can be shared via email link"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT membership_id, name, email, phone, membership_type, 
                   expiration_date, status, created_at
            FROM members 
            WHERE membership_id = ?
        ''', (membership_id,))
        
        member = cursor.fetchone()
        
        if not member:
            return "Member not found", 404
        
        # Calculate expiry status
        expiry_date = None
        days_diff = None
        expiry_status = 'unknown'
        
        if member[5]:  # expiration_date
            try:
                expiry_date = datetime.strptime(member[5], "%Y-%m-%d")
                today = datetime.now().date()
                days_diff = (expiry_date.date() - today).days
                
                if days_diff < 0:
                    expiry_status = 'expired'
                elif days_diff <= 7:
                    expiry_status = 'warning'
                else:
                    expiry_status = 'active'
                    
            except ValueError as e:
                print(f"Date parsing error for member {membership_id}: {e}")
                expiry_status = 'invalid'
        
        # Render the standalone digital card template
        return render_template("standalone_digital_card.html",
                             member=member,
                             expiry_date=expiry_date,
                             days_diff=days_diff,
                             expiry_status=expiry_status)
                             
    except sqlite3.Error as e:
        return f"Database error: {e}", 500
    except Exception as e:
        return f"Unexpected error: {e}", 500



@app.route('/renew/<membership_id>', methods=['GET', 'POST'])
@require_login
@require_member_access
def renew_membership(membership_id):
    try:
        db = get_db()
        cursor = db.cursor()

        if request.method == 'POST':
            cursor.execute('SELECT membership_type FROM members WHERE membership_id = ?', (membership_id,))
            member = cursor.fetchone()
            
            if member:
                membership_type = member[0]
                new_expiration = calculate_expiration_date(membership_type)
                
                cursor.execute('''
                    UPDATE members 
                    SET expiration_date = ?, status = 'active', notification_sent = 'no'
                    WHERE membership_id = ?
                ''', (new_expiration, membership_id))
                
                # Add renewal payment record
                amount = request.form.get('amount', 0)
                if amount:
                    cursor.execute('''
                        INSERT INTO payments (membership_id, organization_id, amount, date, notes, payment_type)
                        VALUES (?, ?, ?, ?, ?, 'renewal')
                    ''', (membership_id, session.get('organization_id'), amount, 
                          datetime.now().strftime('%Y-%m-%d'), 'Membership renewal'))
                
                db.commit()
                flash(f"Membership {membership_id} renewed successfully!", "success")
                return redirect(url_for('member_profile', membership_id=membership_id))

        cursor.execute('''
            SELECT membership_id, name, email, phone, membership_type, expiration_date, status
            FROM members WHERE membership_id = ?
        ''', (membership_id,))
        member = cursor.fetchone()

        if member:
            return render_template('renew_membership.html', member=member)
        else:
            flash("Member not found.", "danger")
            return redirect(url_for('members'))

    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return redirect(url_for('members'))

# ============================================================================
# ROUTES - LOCATION MANAGEMENT
# ============================================================================

@app.route('/locations')
@require_login
@require_org_superadmin
def manage_locations():
    """Manage locations (stores/branches) - Global Superadmin sees all, Organization Superadmin sees their org"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if is_global_superadmin():
            # Global Superadmin sees ALL locations from ALL organizations
            cursor.execute('''
                SELECT l.id, l.name, l.address, l.city, l.state, l.created_at,
                       COUNT(DISTINCT u.id) as admin_count,
                       COUNT(DISTINCT m.id) as member_count,
                       o.name as org_name,
                       o.id as org_id
                FROM locations l
                LEFT JOIN organizations o ON l.organization_id = o.id
                LEFT JOIN users u ON l.id = u.location_id AND u.is_admin = 1
                LEFT JOIN members m ON l.id = m.location_id
                GROUP BY l.id
                ORDER BY o.name, l.name
            ''')
            locations = cursor.fetchall()
            org_name = 'All Organizations'
        else:
            # Organization Superadmin sees only their organization's locations
            org_id = session.get('organization_id')
            cursor.execute('''
                SELECT l.id, l.name, l.address, l.city, l.state, l.created_at,
                       COUNT(DISTINCT u.id) as admin_count,
                       COUNT(DISTINCT m.id) as member_count,
                       NULL as org_name,
                       NULL as org_id
                FROM locations l
                LEFT JOIN users u ON l.id = u.location_id AND u.is_admin = 1
                LEFT JOIN members m ON l.id = m.location_id
                WHERE l.organization_id = ?
                GROUP BY l.id
                ORDER BY l.name
            ''', (org_id,))
            locations = cursor.fetchall()
            
            # Get organization info
            cursor.execute('SELECT name FROM organizations WHERE id = ?', (org_id,))
            org_result = cursor.fetchone()
            org_name = org_result[0] if org_result else 'Unknown'
        
        return render_template('manage_locations.html', 
                             locations=locations,
                             organization_name=org_name,
                             is_superadmin=is_org_superadmin(),
                             is_global_superadmin=is_global_superadmin())
        
    except Exception as e:
        flash(f'❌ Error loading locations: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/create_location', methods=['GET', 'POST'])
@require_login
@require_org_superadmin
def create_location():
    """Create a new location (store/branch) - Organization Superadmin only"""
    try:
        org_id = session.get('organization_id')
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            address = request.form.get('address', '').strip()
            city = request.form.get('city', '').strip()
            state = request.form.get('state', '').strip()
            
            # Validation
            if not name:
                flash('❌ Location name is required.', 'danger')
                return render_template('create_location.html')
            
            db = get_db()
            cursor = db.cursor()
            
            # Check if location name already exists in this organization
            cursor.execute('''
                SELECT id FROM locations 
                WHERE LOWER(name) = LOWER(?) AND organization_id = ?
            ''', (name, org_id))
            
            if cursor.fetchone():
                flash('❌ A location with this name already exists in your organization.', 'danger')
                return render_template('create_location.html')
            
            # Create location
            cursor.execute('''
                INSERT INTO locations (name, address, city, state, organization_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, address, city, state, org_id))
            
            location_id = cursor.lastrowid
            db.commit()
            
            # Log the creation
            log_audit(
                action='LOCATION_CREATED',
                table_name='locations',
                record_id=location_id,
                new_values={
                    'name': name,
                    'address': address,
                    'city': city,
                    'state': state,
                    'organization_id': org_id,
                    'created_by': session.get('username', 'Unknown')
                }
            )
            
            flash(f'✅ Location "{name}" created successfully!', 'success')
            return redirect(url_for('manage_locations'))
        
        return render_template('create_location.html')
        
    except Exception as e:
        flash(f'❌ Error creating location: {e}', 'danger')
        return redirect(url_for('manage_locations'))

@app.route('/edit_location/<int:location_id>', methods=['GET', 'POST'])
@require_login
@require_org_superadmin
def edit_location(location_id):
    """Edit location details - Organization Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Verify location belongs to organization
        cursor.execute('''
            SELECT id, name, address, city, state, organization_id
            FROM locations
            WHERE id = ? AND organization_id = ?
        ''', (location_id, org_id))
        
        location = cursor.fetchone()
        if not location:
            flash('❌ Location not found or access denied.', 'danger')
            return redirect(url_for('manage_locations'))
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            address = request.form.get('address', '').strip()
            city = request.form.get('city', '').strip()
            state = request.form.get('state', '').strip()
            
            # Validation
            if not name:
                flash('❌ Location name is required.', 'danger')
                return render_template('edit_location.html', location=location)
            
            # Check for duplicate name (excluding current location)
            cursor.execute('''
                SELECT id FROM locations 
                WHERE LOWER(name) = LOWER(?) AND organization_id = ? AND id != ?
            ''', (name, org_id, location_id))
            
            if cursor.fetchone():
                flash('❌ A location with this name already exists.', 'danger')
                return render_template('edit_location.html', location=location)
            
            # Store old values for audit
            old_values = {
                'name': location[1],
                'address': location[2],
                'city': location[3],
                'state': location[4]
            }
            
            # Update location
            cursor.execute('''
                UPDATE locations
                SET name = ?, address = ?, city = ?, state = ?
                WHERE id = ?
            ''', (name, address, city, state, location_id))
            
            db.commit()
            
            # Log the update
            log_audit(
                action='LOCATION_UPDATED',
                table_name='locations',
                record_id=location_id,
                old_values=old_values,
                new_values={
                    'name': name,
                    'address': address,
                    'city': city,
                    'state': state
                }
            )
            
            flash(f'✅ Location "{name}" updated successfully!', 'success')
            return redirect(url_for('manage_locations'))
        
        location_data = {
            'id': location[0],
            'name': location[1],
            'address': location[2],
            'city': location[3],
            'state': location[4]
        }
        
        return render_template('edit_location.html', location=location_data)
        
    except Exception as e:
        flash(f'❌ Error editing location: {e}', 'danger')
        return redirect(url_for('manage_locations'))

@app.route('/delete_location/<int:location_id>', methods=['POST'])
@require_login
@require_org_superadmin
def delete_location(location_id):
    """Delete a location - Organization Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Verify location belongs to organization
        cursor.execute('''
            SELECT name FROM locations
            WHERE id = ? AND organization_id = ?
        ''', (location_id, org_id))
        
        location = cursor.fetchone()
        if not location:
            flash('❌ Location not found or access denied.', 'danger')
            return redirect(url_for('manage_locations'))
        
        location_name = location[0]
        
        # Check if any admins are assigned to this location
        cursor.execute('SELECT COUNT(*) FROM users WHERE location_id = ?', (location_id,))
        admin_count = cursor.fetchone()[0]
        
        if admin_count > 0:
            flash(f'⚠️ Cannot delete location "{location_name}". {admin_count} admin(s) are still assigned to it. Please reassign them first.', 'warning')
            return redirect(url_for('manage_locations'))
        
        # Delete location (members with this location will have location_id set to NULL due to ON DELETE SET NULL)
        cursor.execute('DELETE FROM locations WHERE id = ?', (location_id,))
        db.commit()
        
        # Log the deletion
        log_audit(
            action='LOCATION_DELETED',
            table_name='locations',
            record_id=location_id,
            old_values={'name': location_name, 'organization_id': org_id}
        )
        
        flash(f'✅ Location "{location_name}" deleted successfully.', 'success')
        return redirect(url_for('manage_locations'))
        
    except Exception as e:
        flash(f'❌ Error deleting location: {e}', 'danger')
        return redirect(url_for('manage_locations'))

# ============================================================================
# ROUTES - ORGANIZATION MANAGEMENT
# ============================================================================

@app.route('/organizations')
@require_login
@require_org_superadmin
def manage_organizations():
    """Organization superadmin can manage their own organization, Global superadmin can manage all organizations"""
    db = get_db()
    cursor = db.cursor()

    try:
        # Build query based on user role
        if is_global_superadmin():
            # Global superadmin sees all organizations
            cursor.execute('''
                SELECT 
                    o.id,
                    o.name,
                    COALESCE(o.industry, '') as industry,
                    o.created_at,
                    COALESCE(o.status, 'active') as status,
                    o.subscription_package_id,
                    sp.name as package_name,
                    sp.max_organizations as package_max_orgs
                FROM organizations o
                LEFT JOIN subscription_packages sp ON o.subscription_package_id = sp.id
                ORDER BY o.name
            ''')
        else:
            # Organization superadmin sees only their own organization
            cursor.execute('''
                SELECT 
                    o.id,
                    o.name,
                    COALESCE(o.industry, '') as industry,
                    o.created_at,
                    COALESCE(o.status, 'active') as status,
                    o.subscription_package_id,
                    sp.name as package_name,
                    sp.max_organizations as package_max_orgs
                FROM organizations o
                LEFT JOIN subscription_packages sp ON o.subscription_package_id = sp.id
                WHERE o.id = ?
                ORDER BY o.name
            ''', (get_user_organization_id(),))
        
        basic_orgs = cursor.fetchall()
        
        org_list = []
        for org in basic_orgs:
            org_id = org[0]
            
            # Get user count
            cursor.execute("SELECT COUNT(*) FROM users WHERE organization_id = ?", (org_id,))
            user_count = cursor.fetchone()[0] or 0
            
            # Get member count
            member_count = 0
            try:
                cursor.execute("SELECT COUNT(*) FROM members WHERE organization_id = ?", (org_id,))
                member_count = cursor.fetchone()[0] or 0
            except sqlite3.Error:
                pass
            
            # Get location count
            location_count = 0
            try:
                cursor.execute("SELECT COUNT(*) FROM locations WHERE organization_id = ?", (org_id,))
                location_count = cursor.fetchone()[0] or 0
            except sqlite3.Error:
                pass
            
            org_dict = {
                'id': org[0],
                'name': org[1] or '',
                'industry': org[2] or '',
                'created_at': org[3] or '',
                'status': org[4] or 'active',
                'is_active': (org[4] or 'active') == 'active',
                'user_count': user_count,
                'member_count': member_count,
                'location_count': location_count,
                'subscription_package_id': org[5],
                'package_name': org[6] or 'No Package',
                'package_max_orgs': org[7] or 0
            }
            org_list.append(org_dict)

        # Get unique packages for filter dropdown
        cursor.execute('SELECT DISTINCT name FROM subscription_packages ORDER BY name')
        packages = [{'name': row[0]} for row in cursor.fetchall()]

        return render_template('manage_organizations.html', organizations=org_list, packages=packages)

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        flash(f"Database error: {e}", "danger")
        return render_template('manage_organizations.html', organizations=[])
    except Exception as e:
        print(f"General error: {e}")
        flash(f"Error loading organizations: {e}", "danger")
        return render_template('manage_organizations.html', organizations=[])


@app.route('/update_org_location/<int:org_id>', methods=['POST'])
@require_login
def update_org_location(org_id):
    """Update organization location (debug endpoint)"""
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400
    
    data = request.get_json()
    location = data.get('location')
    
    if not location:
        return jsonify({'error': 'Location is required'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute('''
            UPDATE organizations 
            SET location = ? 
            WHERE id = ?
        ''', (location, org_id))
        db.commit()
        
        return jsonify({
            'success': True,
            'message': f'Updated location for organization {org_id} to: {location}'
        })
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/debug_org_data/<int:org_id>')
@require_login
def debug_org_data(org_id):
    """Debug endpoint to check organization data and schema"""
    db = get_db()
    cursor = db.cursor()
    
    # Check if location column exists
    cursor.execute("PRAGMA table_info(organizations)")
    columns = [col[1] for col in cursor.fetchall()]
    
    # Get organization data
    cursor.execute('SELECT * FROM organizations WHERE id = ?', (org_id,))
    org_data = cursor.fetchone()
    
    # Get column names
    cursor.execute('PRAGMA table_info(organizations)')
    col_names = [col[1] for col in cursor.fetchall()]
    
    # Combine column names with data
    org_dict = dict(zip(col_names, org_data)) if org_data else {}
    
    return jsonify({
        'has_location_column': 'location' in columns,
        'organization_data': org_dict,
        'all_columns': columns
    })

@app.route('/create_organization', methods=['GET', 'POST'])
@require_global_superadmin
def create_organization():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        industry = request.form.get('industry', '').strip()
        location = request.form.get('location', '').strip()
        subscription_package_id = request.form.get('subscription_package_id', type=int)
        
        # Validation
        errors = []
        if not name:
            errors.append('Organization name is required')
        if not location:
            errors.append('Location is required')
        
        if errors:
            for error in errors:
                flash(f'❌ {error}', 'error')
            return render_template('create_organization.html', 
                                name=name, 
                                industry=industry,
                                location=location,
                                subscription_package_id=subscription_package_id)
        
        # Default to free package (ID 1) if not specified
        if not subscription_package_id:
            subscription_package_id = 1
        
        # Check if user has reached their package limit (skip for Global Super Admin)
        user_id = session.get('user_id')
        is_global_superadmin_user = bool(session.get('is_global_superadmin'))
        
        if not is_global_superadmin_user:
            can_add, error_message = check_organization_limit(user_id)
            if not can_add:
                flash(error_message, 'error')
                return render_template('create_organization.html', 
                                    name=name, 
                                    industry=industry,
                                    location=location,
                                    subscription_package_id=subscription_package_id)
        
        db = get_db()
        cursor = db.cursor()
        try:
            # Check if organization with same name AND location already exists
            cursor.execute('''
                SELECT id FROM organizations 
                WHERE LOWER(name) = LOWER(?) AND LOWER(location) = LOWER(?)
            ''', (name, location))
            if cursor.fetchone():
                flash('❌ An organization with this name already exists at this location. Please choose a different combination.', 'error')
                return render_template('create_organization.html', 
                                    name=name, 
                                    industry=industry,
                                    location=location,
                                    subscription_package_id=subscription_package_id)
            
            # Verify package exists and is active
            cursor.execute('SELECT id, name FROM subscription_packages WHERE id = ? AND is_active = 1', (subscription_package_id,))
            package = cursor.fetchone()
            if not package:
                flash('Invalid subscription package selected', 'error')
                return render_template('create_organization.html', 
                                    name=name, 
                                    industry=industry,
                                    location=location,
                                    subscription_package_id=subscription_package_id)
            
            # Location is now required, no default fallback
            
            cursor.execute("""
                INSERT INTO organizations (name, industry, location, status, subscription_package_id, created_by_user_id, created_at) 
                VALUES (?, ?, ?, 'active', ?, ?, CURRENT_TIMESTAMP)
            """, (name, industry, location, subscription_package_id, user_id))
            db.commit()
            flash(f"Organization created successfully with {package[1]} package!", "success")
            return redirect(url_for('manage_organizations'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            if 'UNIQUE constraint failed' in str(e):
                flash('❌ An organization with this name already exists at this location. Please use a different name or location.', 'error')
            else:
                flash('❌ Error creating organization. Please try again.', 'error')
            return render_template('create_organization.html', 
                                name=name, 
                                industry=industry,
                                location=location,
                                subscription_package_id=subscription_package_id)
    
    # GET request - load packages for selection
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name, description, max_organizations, price FROM subscription_packages WHERE is_active = 1 ORDER BY max_organizations ASC')
    packages = cursor.fetchall()
    
    # Check user's current organization count and package limits
    user_id = session.get('user_id')
    user_package = get_user_package(user_id)
    current_org_count = get_user_organization_count(user_id)
    
    return render_template('create_organization.html', 
                         packages=packages, 
                         user_package=user_package,
                         current_org_count=current_org_count)

@app.route('/switch_organization/<int:org_id>')
@require_login
@require_global_superadmin
def switch_organization(org_id):
    """Switch to a different organization (Global Superadmin only)"""
    db = get_db()
    cursor = db.cursor()
    
    # Verify the organization exists
    cursor.execute('SELECT id, name FROM organizations WHERE id = ?', (org_id,))
    org = cursor.fetchone()
    
    if not org:
        flash('Organization not found', 'danger')
        return redirect(url_for('manage_organizations'))
    
    # Update session with new organization
    session['organization_id'] = org[0]
    session['organization_name'] = org[1]
    
    flash(f'Switched to organization: {org[1]}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/organization/<int:org_id>')
@require_login
def view_organization(org_id):
    """View organization details"""
    db = get_db()
    cursor = db.cursor()
    
    is_global_superadmin_user = bool(session.get('is_global_superadmin'))
    user_org_id = session.get('organization_id')
    
    if isinstance(user_org_id, str) and user_org_id.isdigit():
        user_org_id = int(user_org_id)
    
    has_permission = is_global_superadmin_user or (user_org_id == org_id)
    
    if not has_permission:
        flash('You do not have permission to view this organization.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        cursor.execute('''
            SELECT o.id, o.name, o.industry, o.location, o.created_at, o.status,
                   COUNT(DISTINCT u.id) as user_count,
                   COUNT(DISTINCT m.id) as member_count,
                   COUNT(DISTINCT l.id) as location_count
            FROM organizations o
            LEFT JOIN users u ON o.id = u.organization_id
            LEFT JOIN members m ON o.id = m.organization_id
            LEFT JOIN locations l ON o.id = l.organization_id
            WHERE o.id = ?
            GROUP BY o.id, o.name, o.industry, o.location, o.created_at, o.status
        ''', (org_id,))
        
        org_data = cursor.fetchone()
        
        if not org_data:
            flash('Organization not found.', 'error')
            return redirect(url_for('dashboard'))
        
        organization = {
            'id': org_data[0],
            'name': org_data[1],
            'industry': org_data[2],
            'location': org_data[3],
            'created_at': org_data[4],
            'status': org_data[5],
            'user_count': org_data[6],
            'member_count': org_data[7],
            'location_count': org_data[8]
        }
        
        # Get recent data
        cursor.execute('''
            SELECT id, name, address, city, state
            FROM locations
            WHERE organization_id = ?
            ORDER BY name
        ''', (org_id,))
        locations = [dict(zip([col[0] for col in cursor.description], row)) 
                    for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, username, email, created_at, is_admin
            FROM users
            WHERE organization_id = ?
            ORDER BY created_at DESC
            LIMIT 5
        ''', (org_id,))
        recent_users = [dict(zip([col[0] for col in cursor.description], row)) 
                       for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT id, membership_id, name as first_name, '' as last_name, 
                   email, created_at
            FROM members
            WHERE organization_id = ?
            ORDER BY created_at DESC
            LIMIT 5
        ''', (org_id,))
        recent_members = []
        for row in cursor.fetchall():
            member_dict = dict(zip([col[0] for col in cursor.description], row))
            name_parts = member_dict['first_name'].split(' ', 1)
            member_dict['first_name'] = name_parts[0]
            member_dict['last_name'] = name_parts[1] if len(name_parts) > 1 else ''
            recent_members.append(member_dict)
        
        return render_template('view_organization.html',
                             organization=organization,
                             locations=locations,
                             recent_users=recent_users,
                             recent_members=recent_members)
        
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return redirect(url_for('dashboard'))

@app.route('/organization/<int:org_id>/edit', methods=['GET', 'POST'])
@require_login
def edit_organization(org_id):
    """Edit organization details"""
    db = get_db()
    cursor = db.cursor()
    
    is_global_superadmin_user = bool(session.get('is_global_superadmin'))
    user_org_id = session.get('organization_id')
    is_admin = bool(session.get('is_admin'))
    
    if isinstance(user_org_id, str) and user_org_id.isdigit():
        user_org_id = int(user_org_id)
    
    has_permission = is_global_superadmin_user or (user_org_id == org_id and is_admin)
    
    if not has_permission:
        flash('You do not have permission to edit this organization.', 'error')
        return redirect(url_for('dashboard'))
    
    # Get organization with package information
    cursor.execute('''
        SELECT o.*, sp.name as package_name, sp.max_organizations, sp.price
        FROM organizations o
        LEFT JOIN subscription_packages sp ON o.subscription_package_id = sp.id
        WHERE o.id = ?
    ''', (org_id,))
    org_data = cursor.fetchone()
    
    if not org_data:
        flash('Organization not found.', 'error')
        return redirect(url_for('manage_organizations') if is_global_superadmin_user else url_for('dashboard'))
    
    organization = dict(zip([col[0] for col in cursor.description], org_data))
    
    # Get all subscription packages for dropdown (only for Global Super Admin)
    packages = []
    if is_global_superadmin_user:
        cursor.execute('''
            SELECT id, name, description, max_organizations, price, is_active
            FROM subscription_packages
            WHERE is_active = 1
            ORDER BY max_organizations ASC
        ''')
        packages = cursor.fetchall()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        industry = request.form.get('industry', '').strip()
        location = request.form.get('location', '').strip()
        subscription_package_id = request.form.get('subscription_package_id', type=int)
        
        # Store old package for logging
        old_package_id = organization.get('subscription_package_id')
        
        # Validation
        if not name or not location:
            flash('❌ Organization name and location are required.', 'error')
        else:
            try:
                # Check if another org with same name+location exists (excluding current org)
                cursor.execute('''
                    SELECT id FROM organizations 
                    WHERE LOWER(name) = LOWER(?) AND LOWER(location) = LOWER(?) AND id != ?
                ''', (name, location, org_id))
                if cursor.fetchone():
                    flash('❌ An organization with this name already exists at this location.', 'error')
                else:
                    # Global Super Admin can change package, others cannot
                    if is_global_superadmin_user and subscription_package_id:
                        # Verify package exists and is active
                        cursor.execute('''
                            SELECT id, name FROM subscription_packages 
                            WHERE id = ? AND is_active = 1
                        ''', (subscription_package_id,))
                        package = cursor.fetchone()
                        
                        if not package:
                            flash('Invalid subscription package selected.', 'error')
                            return render_template('edit_organization.html', 
                                                 organization=organization, 
                                                 packages=packages)
                        
                        cursor.execute('''
                            UPDATE organizations 
                            SET name = ?, industry = ?, location = ?, subscription_package_id = ?
                            WHERE id = ?
                        ''', (name, industry, location, subscription_package_id, org_id))
                        
                        # Log the package change if it was changed
                        if old_package_id != subscription_package_id:
                            log_audit(
                                action='ORG_PACKAGE_CHANGED',
                                table_name='organizations',
                                record_id=org_id,
                                old_values={'subscription_package_id': old_package_id},
                                new_values={
                                    'subscription_package_id': subscription_package_id,
                                    'package_name': package[1],
                                    'changed_by': session.get('username', 'Unknown')
                                }
                            )
                            flash(f'Organization updated successfully! Package changed to: {package[1]}', 'success')
                        else:
                            flash('Organization updated successfully!', 'success')
                    else:
                        # Regular admin update (no package change)
                        cursor.execute('''
                            UPDATE organizations 
                            SET name = ?, industry = ?, location = ?
                            WHERE id = ?
                        ''', (name, industry, location, org_id))
                        flash('Organization updated successfully!', 'success')
                    
                    db.commit()
                    
                    if is_global_superadmin_user:
                        return redirect(url_for('manage_organizations'))
                    else:
                        return redirect(url_for('dashboard'))
                        
            except sqlite3.IntegrityError as e:
                flash('Error updating organization. Please try again.', 'error')
                print(f"Database error: {e}")
    
    return render_template('edit_organization.html', 
                         organization=organization, 
                         packages=packages,
                         is_global_superadmin=is_global_superadmin_user)

@app.route('/organization/<int:org_id>/delete', methods=['POST'])
@require_login
@require_org_superadmin
def delete_organization(org_id):
    """Delete an organization - Organization superadmin can delete their own org, Global superadmin can delete any org"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("SELECT name FROM organizations WHERE id = ?", (org_id,))
        org = cursor.fetchone()
        
        if not org:
            flash("Organization not found.", "danger")
            return redirect(url_for('manage_organizations'))
        
        # Access control: Organization superadmin can only delete their own organization
        if not is_global_superadmin() and get_user_organization_id() != org_id:
            flash("Access denied. You can only manage your own organization.", "danger")
            return redirect(url_for('manage_organizations'))
        
        cursor.execute("SELECT COUNT(*) FROM members WHERE organization_id = ?", (org_id,))
        member_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE organization_id = ? AND (is_admin = 1 OR is_superadmin = 1)", (org_id,))
        admin_user_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE organization_id = ? AND is_admin = 0 AND is_superadmin = 0 AND is_global_superadmin = 0", (org_id,))
        regular_user_count = cursor.fetchone()[0]
        
        if member_count > 0 or regular_user_count > 0:
            flash(f"Cannot delete organization '{org[0]}'. It has {member_count} members and {regular_user_count} regular users.", "danger")
            return redirect(url_for('manage_organizations'))
        
        cursor.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
        db.commit()
        
        flash(f"Organization '{org[0]}' deleted successfully.", "success")
        
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Error deleting organization: {e}", "danger")
    
    return redirect(url_for('manage_organizations'))

@app.route('/organization/<int:org_id>/activate', methods=['POST'])
@require_login
@require_org_superadmin
def activate_organization(org_id):
    """Activate an organization - Organization superadmin can activate their own org, Global superadmin can activate any org"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("SELECT name FROM organizations WHERE id = ?", (org_id,))
        org = cursor.fetchone()
        
        if not org:
            flash("Organization not found.", "danger")
            return redirect(url_for('manage_organizations'))
        
        # Access control: Organization superadmin can only activate their own organization
        if not is_global_superadmin() and get_user_organization_id() != org_id:
            flash("Access denied. You can only manage your own organization.", "danger")
            return redirect(url_for('manage_organizations'))
        
        # Check if organization is already active
        cursor.execute("SELECT status FROM organizations WHERE id = ?", (org_id,))
        current_status = cursor.fetchone()
        if current_status and current_status[0] == 'active':
            flash(f"Organization '{org[0]}' is already active.", "warning")
            return redirect(url_for('manage_organizations'))
        
        # Activate the organization
        cursor.execute("UPDATE organizations SET status = 'active' WHERE id = ?", (org_id,))
        
        # Log the activation for audit purposes
        log_audit(
            action='ORGANIZATION_ACTIVATED',
            table_name='organizations',
            record_id=org_id,
            new_values={
                'organization_id': org_id,
                'organization_name': org[0],
                'status': 'active',
                'activated_by': session.get('username', 'Unknown')
            }
        )
        
        db.commit()
        
        # Get count of affected users for reporting
        cursor.execute("SELECT COUNT(*) FROM users WHERE organization_id = ?", (org_id,))
        user_count = cursor.fetchone()[0]
        
        flash(f"Organization '{org[0]}' activated successfully. {user_count} users can now login again.", "success")
            
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Error activating organization: {e}", "danger")
    
    return redirect(url_for('manage_organizations'))

@app.route('/organization/<int:org_id>/deactivate', methods=['POST'])
@require_login
@require_org_superadmin
def deactivate_organization(org_id):
    """Deactivate an organization and enforce restrictions - Organization superadmin can deactivate their own org, Global superadmin can deactivate any org"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Prevent deactivating the global system administration organization
        if org_id == 1:
            flash("Cannot deactivate the Global System Administration organization.", "danger")
            return redirect(url_for('manage_organizations'))
        
        cursor.execute("SELECT name FROM organizations WHERE id = ?", (org_id,))
        org = cursor.fetchone()
        
        if not org:
            flash("Organization not found.", "danger")
            return redirect(url_for('manage_organizations'))
        
        # Access control: Organization superadmin can only deactivate their own organization
        if not is_global_superadmin() and get_user_organization_id() != org_id:
            flash("Access denied. You can only manage your own organization.", "danger")
            return redirect(url_for('manage_organizations'))
        
        # Check if organization is already inactive
        cursor.execute("SELECT status FROM organizations WHERE id = ?", (org_id,))
        current_status = cursor.fetchone()
        if current_status and current_status[0] == 'inactive':
            flash(f"Organization '{org[0]}' is already inactive.", "warning")
            return redirect(url_for('manage_organizations'))
        
        # Deactivate the organization
        cursor.execute("UPDATE organizations SET status = 'inactive' WHERE id = ?", (org_id,))
        
        # Log the deactivation for audit purposes
        log_audit(
            action='ORGANIZATION_DEACTIVATED',
            table_name='organizations',
            record_id=org_id,
            new_values={
                'organization_id': org_id,
                'organization_name': org[0],
                'status': 'inactive',
                'deactivated_by': session.get('username', 'Unknown')
            }
        )
        
        db.commit()
        
        # Get count of affected users for reporting
        cursor.execute("SELECT COUNT(*) FROM users WHERE organization_id = ?", (org_id,))
        user_count = cursor.fetchone()[0]
        
        flash(f"Organization '{org[0]}' deactivated successfully. {user_count} users will be unable to login until the organization is reactivated.", "success")
            
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Error deactivating organization: {e}", "danger")
    
    return redirect(url_for('manage_organizations'))

# ============================================================================
# ROUTES - NOTIFICATIONS AND COMMUNICATION
# ============================================================================

@app.route('/notifications')
@require_login
def notifications():
    """View notifications with organization filtering"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        org_filter, org_params = get_notifications_query_filter()
        
        query = '''
            SELECT n.membership_id, m.name, n.type, n.message, n.sent_at, n.organization_id
            FROM notifications n
            JOIN members m ON n.membership_id = m.membership_id AND n.organization_id = m.organization_id
        '''
        
        params = list(org_params)
        
        if org_filter:
            query += ' ' + org_filter
        
        query += ' ORDER BY n.sent_at DESC LIMIT 50'
        
        cursor.execute(query, params)
        notifications_list = cursor.fetchall()
        
        return render_template('notifications.html', notifications=notifications_list)
        
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return render_template('notifications.html', notifications=[])

@app.route('/clear_notifications')
@require_login
def clear_notifications():
    """Clear notifications with organization filtering"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        org_filter, org_params = get_notifications_query_filter()
        
        if org_filter:
            delete_query = 'DELETE FROM notifications ' + org_filter
            cursor.execute(delete_query, org_params)
        else:
            cursor.execute('DELETE FROM notifications')
        
        db.commit()
        flash("Notification history has been cleared.", "success")
        
    except sqlite3.Error as e:
        flash(f"Error clearing notifications: {e}", "danger")
    
    return redirect(url_for('notifications'))

@app.route('/communication')
@require_login
def communication_center():
    """Communication center with organization filtering support"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get organization filter
        if is_global_superadmin():
            # Global superadmin can see all members or filter by organization
            filter_org_id = request.args.get('org_id', type=int)
            
            if filter_org_id:
                # Filter by specific organization
                cursor.execute('''
                    SELECT m.membership_id, m.name, m.email, m.phone, m.membership_type, m.status, m.organization_id, o.name as org_name
                    FROM members m
                    JOIN organizations o ON m.organization_id = o.id
                    WHERE m.organization_id = ?
                    ORDER BY m.name
                ''', (filter_org_id,))
            else:
                # Get all members from all organizations
                cursor.execute('''
                    SELECT m.membership_id, m.name, m.email, m.phone, m.membership_type, m.status, m.organization_id, o.name as org_name
                    FROM members m
                    JOIN organizations o ON m.organization_id = o.id
                    ORDER BY m.name
                ''')
            
            members = cursor.fetchall()
            
            # Get organizations for filter dropdown
            cursor.execute('SELECT id, name FROM organizations WHERE status = "active" ORDER BY name')
            organizations = cursor.fetchall()
        else:
            # Regular admin: only see their organization's members
            organization_id = session.get('organization_id')
            if not organization_id:
                flash("Organization not found. Please contact administrator.", "danger")
                return redirect(url_for('dashboard'))
            
            cursor.execute('''
                SELECT m.membership_id, m.name, m.email, m.phone, m.membership_type, m.status, m.organization_id, o.name as org_name
                FROM members m
                JOIN organizations o ON m.organization_id = o.id
                WHERE m.organization_id = ?
                ORDER BY m.name
            ''', (organization_id,))
            members = cursor.fetchall()
            
            organizations = []
            filter_org_id = None
        
        # Get recent communications
        if is_global_superadmin() and filter_org_id:
            cursor.execute('''
                SELECT n.membership_id, m.name, n.type, n.message, n.sent_at
                FROM notifications n
                JOIN members m ON n.membership_id = m.membership_id
                WHERE n.type LIKE 'bulk_%' AND n.organization_id = ?
                ORDER BY n.sent_at DESC
                LIMIT 10
            ''', (filter_org_id,))
        elif is_global_superadmin():
            cursor.execute('''
                SELECT n.membership_id, m.name, n.type, n.message, n.sent_at
                FROM notifications n
                JOIN members m ON n.membership_id = m.membership_id
                WHERE n.type LIKE 'bulk_%'
                ORDER BY n.sent_at DESC
                LIMIT 10
            ''')
        else:
            cursor.execute('''
                SELECT n.membership_id, m.name, n.type, n.message, n.sent_at
                FROM notifications n
                JOIN members m ON n.membership_id = m.membership_id
                WHERE n.type LIKE 'bulk_%' AND n.organization_id = ?
                ORDER BY n.sent_at DESC
                LIMIT 10
            ''', (organization_id,))
        
        recent_communications = cursor.fetchall()
        
        return render_template('communication_center.html', 
                             members=members, 
                             recent_communications=recent_communications,
                             organizations=organizations if is_global_superadmin() else [],
                             selected_org_id=filter_org_id if is_global_superadmin() else None,
                             is_global_superadmin=is_global_superadmin())
    
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return render_template('communication_center.html', members=[], recent_communications=[])

@app.route('/send_message', methods=['POST'])
@require_login
def send_message():
    """Send message to selected members or entire organization with optional file attachment"""
    try:
        recipient_type = request.form.get('recipient_type', 'individual')
        message_type = request.form.get('message_type')
        subject = request.form.get('subject', '')
        message_content = request.form.get('message_content', '')
        attachment = request.files.get('attachment')
        
        if not message_content:
            flash("Please enter a message.", "warning")
            return redirect(url_for('communication_center'))
        
        # Handle file upload
        attachment_path = None
        attachment_filename = None
        if attachment and attachment.filename:
            # Validate file
            allowed_extensions = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'txt'}
            max_file_size = 5 * 1024 * 1024  # 5MB
            
            # Check file extension
            file_ext = attachment.filename.rsplit('.', 1)[1].lower() if '.' in attachment.filename else ''
            if file_ext not in allowed_extensions:
                flash(f"Invalid file type. Allowed: {', '.join(allowed_extensions)}", "danger")
                return redirect(url_for('communication_center'))
            
            # Check file size
            attachment.seek(0, os.SEEK_END)
            file_size = attachment.tell()
            attachment.seek(0)
            
            if file_size > max_file_size:
                flash(f"File too large. Maximum size: 5MB", "danger")
                return redirect(url_for('communication_center'))
            
            # Save file temporarily
            import tempfile
            temp_dir = tempfile.mkdtemp()
            attachment_filename = secure_filename(attachment.filename)
            attachment_path = os.path.join(temp_dir, attachment_filename)
            attachment.save(attachment_path)
        
        db = get_db()
        cursor = db.cursor()
        
        if recipient_type == 'individual':
            selected_members = request.form.getlist('selected_members')
            if not selected_members:
                flash("Please select at least one member.", "warning")
                return redirect(url_for('communication_center'))
                
            placeholders = ','.join(['?' for _ in selected_members])
            
            # Check user role and apply appropriate filters
            if is_global_superadmin():
                cursor.execute(f'''
                    SELECT membership_id, name, email, phone, organization_id
                    FROM members 
                    WHERE membership_id IN ({placeholders})
                ''', selected_members)
                members_data = cursor.fetchall()
                
            else:
                organization_id = session.get('organization_id')
                if not organization_id:
                    flash("Organization not found. Please contact administrator.", "danger")
                    return redirect(url_for('communication_center'))
                
                cursor.execute(f'''
                    SELECT membership_id, name, email, phone, organization_id
                    FROM members 
                    WHERE membership_id IN ({placeholders}) AND organization_id = ?
                ''', selected_members + [organization_id])
                
                members_data = cursor.fetchall()
                
                if len(members_data) != len(selected_members):
                    flash("Some selected members don't belong to your organization.", "danger")
                    return redirect(url_for('communication_center'))
        
        else:  # Organization-based sending
            if is_global_superadmin():
                organization_ids = request.form.getlist('selected_organizations')
                if not organization_ids:
                    flash("Please select at least one organization.", "warning")
                    return redirect(url_for('communication_center'))
                
                placeholders = ','.join(['?' for _ in organization_ids])
                
                # Get all active members from the selected organizations
                cursor.execute(f'''
                    SELECT membership_id, name, email, phone, organization_id
                    FROM members 
                    WHERE organization_id IN ({placeholders}) AND status = 'active'
                ''', organization_ids)
                members_data = cursor.fetchall()
                
            else:
                organization_id = session.get('organization_id')
                if not organization_id:
                    flash("Organization not found. Please contact administrator.", "danger")
                    return redirect(url_for('communication_center'))
                
                # Get all active members from the selected organization
                cursor.execute('''
                    SELECT membership_id, name, email, phone, organization_id
                    FROM members 
                    WHERE organization_id = ? AND status = 'active'
                ''', (organization_id,))
                members_data = cursor.fetchall()
            
            if not members_data:
                flash("No active members found in the selected organization(s).", "warning")
                return redirect(url_for('communication_center'))
        
        # Proceed with sending messages
        email_recipients = []
        sms_recipients = []
        
        for member in members_data:
            member_id, name, email, phone, member_org_id = member
            
            personalized_message = message_content.replace('[NAME]', name).replace('[MEMBER_ID]', member_id)
            
            if message_type in ['email', 'both'] and email:
                email_recipients.append((email, name))  # Store email with name
            
            if message_type in ['sms', 'both'] and phone:
                if validate_phone_number_enhanced(phone)[0]:
                    sms_recipients.append(phone)
        
        email_sent = 0
        email_failed = 0
        sms_sent = 0
        sms_failed = 0
        
        # Send emails with optional attachment
        if message_type in ['email', 'both'] and email_recipients:
            formatted_message = message_content.replace('\n', '<br>')
            
            for email, name in email_recipients:
                personalized_html = formatted_message.replace('[NAME]', name)
                
                html_message = f"""
                <html>
                <body>
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #0d6efd;">MemberSync Message</h2>
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px;">
                        {personalized_html}
                    </div>
                    {f'<p style="margin-top: 20px;"><strong>📎 Attachment:</strong> {attachment_filename}</p>' if attachment_filename else ''}
                    <br>
                    <p style="color: #6c757d; font-size: 14px;">
                        Best regards,<br>
                        MemberSync Team
                    </p>
                </div>
            </body>
            </html>
            """
                
                # Send with or without attachment
                if attachment_path:
                    if send_email_with_attachment(email, subject, html_message, attachment_path, attachment_filename):
                        email_sent += 1
                    else:
                        email_failed += 1
                else:
                    if send_email_notification(email, subject, html_message):
                        email_sent += 1
                    else:
                        email_failed += 1
        
        # Send SMS (no attachments for SMS)
        last_sms_error = None
        if message_type in ['sms', 'both'] and sms_recipients:
            sms_message = message_content[:160] + "..." if len(message_content) > 160 else message_content
            for phone in sms_recipients:
                formatted_phone = format_phone_number(phone)
                if formatted_phone:
                    success, error = send_sms_notification(formatted_phone, sms_message)
                    if success:
                        sms_sent += 1
                    else:
                        sms_failed += 1
                        last_sms_error = error
                else:
                    sms_failed += 1
        
        # Log communication for each member
        for member_id, name, email, phone, member_org_id in members_data:
            log_message = f"Subject: {subject}\nMessage: {message_content[:100]}...\nAttachment: {attachment_filename if attachment_filename else 'None'}\nSent: {email_sent + sms_sent}, Failed: {email_failed + sms_failed}"
            cursor.execute('''
                INSERT INTO notifications (membership_id, organization_id, type, message, sent_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (member_id, member_org_id, f'bulk_{message_type}', log_message, 
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        db.commit()
        
        # Clean up temporary file
        if attachment_path and os.path.exists(attachment_path):
            try:
                os.remove(attachment_path)
                os.rmdir(os.path.dirname(attachment_path))
            except:
                pass
        
        total_sent = email_sent + sms_sent
        total_failed = email_failed + sms_failed
        
        if total_sent > 0:
            attachment_msg = f" (with attachment: {attachment_filename})" if attachment_filename else ""
            flash(f"✅ Message sent successfully{attachment_msg}! Delivered: {total_sent}, Failed: {total_failed}", "success")
        else:
            if sms_recipients and sms_failed > 0:
                error_msg = f"❌ Failed to send SMS. Error: {last_sms_error}" if last_sms_error else "❌ Failed to send SMS. Check console logs."
                flash(error_msg, "danger")
            else:
                flash("❌ Failed to send messages. Please check your configuration.", "danger")
    
    except Exception as e:
        flash(f"Error sending message: {e}", "danger")
        print(f"Communication error: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('communication_center'))


# ============================================================================
# ROUTES - DISCOUNT MANAGEMENT
# ============================================================================

@app.route('/discounts')
@require_login
def manage_discounts():
    try:
        db = get_db()
        cursor = db.cursor()
        
        org_id = session.get('organization_id')
        cursor.execute('''
            SELECT id, code, description, discount_type, discount_value, 
                   min_amount, max_uses, current_uses, start_date, end_date, status
            FROM discounts 
            WHERE organization_id = ?
            ORDER BY created_at DESC
        ''', (org_id,))
        discounts = cursor.fetchall()
        
        return render_template('manage_discounts.html', discounts=discounts)
    
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
        return render_template('manage_discounts.html', discounts=[])

@app.route('/create_discount', methods=['GET', 'POST'])
@require_login
def create_discount():
    if request.method == 'POST':
        try:
            code = request.form['code'].upper().strip()
            description = request.form['description']
            discount_type = request.form['discount_type']
            discount_value = float(request.form['discount_value'])
            min_amount = float(request.form.get('min_amount', 0))
            max_uses = request.form.get('max_uses')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            
            if discount_type == 'percentage' and (discount_value <= 0 or discount_value > 100):
                flash("Percentage discount must be between 1-100", "danger")
                return render_template('create_discount.html')
            
            if discount_type == 'fixed' and discount_value <= 0:
                flash("Fixed discount must be greater than 0", "danger")
                return render_template('create_discount.html')
            
            db = get_db()
            cursor = db.cursor()
            
            org_id = session.get('organization_id')
            cursor.execute('''
                INSERT INTO discounts (code, description, discount_type, discount_value, 
                                     min_amount, max_uses, start_date, end_date, organization_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, description, discount_type, discount_value, min_amount, 
                  int(max_uses) if max_uses else None, start_date if start_date else None, 
                  end_date if end_date else None, org_id))
            
            db.commit()
            flash("Discount code created successfully!", "success")
            return redirect(url_for('manage_discounts'))
            
        except ValueError:
            flash("Invalid numeric values", "danger")
        except sqlite3.IntegrityError:
            flash("Discount code already exists", "danger")
        except Exception as e:
            flash(f"Error creating discount: {e}", "danger")
    
    return render_template('create_discount.html')

@app.route('/validate_discount_ajax', methods=['POST'])
@require_login
def validate_discount_ajax():
    """AJAX endpoint to validate discount codes"""
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        amount = float(data.get('amount', 0))
        membership_id = data.get('membership_id')
        
        if not code:
            return {'valid': False, 'message': 'Please enter a discount code'}
        
        discount_info, error = validate_discount_code(code, amount, membership_id)
        
        if discount_info:
            return {
                'valid': True,
                'discount': discount_info,
                'message': f'Discount applied! You save {get_currency_symbol()}{discount_info["amount"]:.2f}'
            }
        else:
            return {'valid': False, 'message': error}
            
    except Exception as e:
        return {'valid': False, 'message': f'Error: {e}'}

# ============================================================================
# ROUTES - SETTINGS AND UTILITIES
# ============================================================================

@app.route('/subscription_packages')
@require_login
@require_global_superadmin
def manage_subscription_packages():
    """Manage subscription packages - Global Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get all subscription packages
        cursor.execute('''
            SELECT id, name, description, max_organizations, price, is_active, created_at
            FROM subscription_packages
            ORDER BY max_organizations ASC
        ''')
        packages = cursor.fetchall()
        
        # Get user count for each package
        package_stats = []
        for pkg in packages:
            cursor.execute('''
                SELECT COUNT(*) FROM users WHERE subscription_package_id = ?
            ''', (pkg[0],))
            user_count = cursor.fetchone()[0]
            
            # Get organization count for this package
            cursor.execute('''
                SELECT COUNT(*) FROM organizations WHERE subscription_package_id = ?
            ''', (pkg[0],))
            org_count = cursor.fetchone()[0]
            
            package_stats.append({
                'id': pkg[0],
                'name': pkg[1],
                'description': pkg[2],
                'max_organizations': pkg[3],
                'price': pkg[4],
                'is_active': pkg[5],
                'created_at': pkg[6],
                'user_count': user_count,
                'org_count': org_count
            })
        
        return render_template('subscription_packages.html', packages=package_stats)
        
    except Exception as e:
        flash(f'Error loading subscription packages: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/subscription_packages/create', methods=['GET', 'POST'])
@require_login
@require_global_superadmin
def create_subscription_package():
    """Create new subscription package - Max 4 packages allowed"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check current package count
        cursor.execute('SELECT COUNT(*) FROM subscription_packages')
        current_count = cursor.fetchone()[0]
        
        if current_count >= 4:
            flash('Maximum of 4 subscription packages allowed', 'error')
            return redirect(url_for('manage_subscription_packages'))
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            max_organizations = request.form.get('max_organizations', type=int)
            price = request.form.get('price', type=float)
            features = request.form.get('features', '{}')
            
            if not all([name, description, max_organizations is not None]):
                flash('Name, description, and max organizations are required', 'error')
                return render_template('create_subscription_package.html')
            
            if max_organizations <= 0:
                flash('Max organizations must be greater than 0', 'error')
                return render_template('create_subscription_package.html')
            
            try:
                cursor.execute('''
                    INSERT INTO subscription_packages (name, description, max_organizations, price, features, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                ''', (name, description, max_organizations, price or 0.0, features))
                db.commit()
                flash('Subscription package created successfully!', 'success')
                return redirect(url_for('manage_subscription_packages'))
            except sqlite3.IntegrityError:
                flash('A package with this name already exists', 'error')
                return render_template('create_subscription_package.html')
        
        return render_template('create_subscription_package.html')
        
    except Exception as e:
        flash(f'Error creating package: {e}', 'error')
        return redirect(url_for('manage_subscription_packages'))

@app.route('/subscription_packages/<int:package_id>/edit', methods=['GET', 'POST'])
@require_login
@require_global_superadmin
def edit_subscription_package(package_id):
    """Edit subscription package"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            max_organizations = request.form.get('max_organizations', type=int)
            price = request.form.get('price', type=float)
            features = request.form.get('features', '{}')
            is_active = bool(request.form.get('is_active'))
            
            if not all([name, description, max_organizations is not None]):
                flash('Name, description, and max organizations are required', 'error')
                return redirect(url_for('edit_subscription_package', package_id=package_id))
            
            if max_organizations <= 0:
                flash('Max organizations must be greater than 0', 'error')
                return redirect(url_for('edit_subscription_package', package_id=package_id))
            
            try:
                cursor.execute('''
                    UPDATE subscription_packages 
                    SET name = ?, description = ?, max_organizations = ?, price = ?, features = ?, is_active = ?
                    WHERE id = ?
                ''', (name, description, max_organizations, price or 0.0, features, int(is_active), package_id))
                db.commit()
                flash('Subscription package updated successfully!', 'success')
                return redirect(url_for('manage_subscription_packages'))
            except sqlite3.IntegrityError:
                flash('A package with this name already exists', 'error')
                return redirect(url_for('edit_subscription_package', package_id=package_id))
        
        # GET request - load package data
        cursor.execute('''
            SELECT id, name, description, max_organizations, price, features, is_active
            FROM subscription_packages WHERE id = ?
        ''', (package_id,))
        package = cursor.fetchone()
        
        if not package:
            flash('Package not found', 'error')
            return redirect(url_for('manage_subscription_packages'))
        
        return render_template('edit_subscription_package.html', package=package)
        
    except Exception as e:
        flash(f'Error editing package: {e}', 'error')
        return redirect(url_for('manage_subscription_packages'))

@app.route('/subscription_packages/<int:package_id>/delete', methods=['POST'])
@require_login
@require_global_superadmin
def delete_subscription_package(package_id):
    """Delete subscription package"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if package is in use
        cursor.execute('SELECT COUNT(*) FROM users WHERE subscription_package_id = ?', (package_id,))
        user_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM organizations WHERE subscription_package_id = ?', (package_id,))
        org_count = cursor.fetchone()[0]
        
        if user_count > 0 or org_count > 0:
            flash(f'Cannot delete package. It is currently used by {user_count} users and {org_count} organizations', 'error')
            return redirect(url_for('manage_subscription_packages'))
        
        cursor.execute('DELETE FROM subscription_packages WHERE id = ?', (package_id,))
        db.commit()
        flash('Subscription package deleted successfully!', 'success')
        return redirect(url_for('manage_subscription_packages'))
        
    except Exception as e:
        flash(f'Error deleting package: {e}', 'error')
        return redirect(url_for('manage_subscription_packages'))

@app.route('/assign_package/<int:user_id>', methods=['POST'])
@require_login
@require_global_superadmin
def assign_package(user_id):
    """Assign subscription package to a user"""
    try:
        package_id = request.form.get('package_id')
        
        if not package_id:
            flash('Please select a package', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        
        db = get_db()
        cursor = db.cursor()
        
        # Get the new package details
        cursor.execute('SELECT name, max_organizations FROM subscription_packages WHERE id = ?', (package_id,))
        package = cursor.fetchone()
        if not package:
            flash('Invalid package selected', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        
        package_name, max_orgs = package
        
        # Check if user has more organizations than the new package allows
        current_org_count = get_user_organization_count(user_id)
        if current_org_count > max_orgs:
            flash(f'Cannot assign {package_name} package. User has {current_org_count} organizations but package only allows {max_orgs}.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        
        # Update user's package
        cursor.execute('''
            UPDATE users SET subscription_package_id = ? WHERE id = ?
        ''', (package_id, user_id))
        
        db.commit()
        flash(f'Subscription package changed to {package_name} successfully!', 'success')
        
    except Exception as e:
        flash(f'Error assigning package: {e}', 'danger')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/assign_organization/<int:user_id>', methods=['POST'])
@require_login
@require_global_superadmin
def assign_organization(user_id):
    """Assign organization to a user"""
    try:
        organization_id = request.form.get('organization_id', type=int)
        
        if not organization_id:
            flash('Please select an organization', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        
        db = get_db()
        cursor = db.cursor()
        
        # Verify organization exists and is active
        cursor.execute('SELECT id, name FROM organizations WHERE id = ? AND status = "active"', (organization_id,))
        organization = cursor.fetchone()
        if not organization:
            flash('Invalid organization selected', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        
        org_id, org_name = organization
        
        # Check if user's package allows this organization
        user_package = get_user_package(user_id)
        if user_package:
            current_org_count = get_user_organization_count(user_id)
            max_allowed = user_package['max_organizations']
            
            # If user is being assigned to a new organization, check limits
            cursor.execute('SELECT organization_id FROM users WHERE id = ?', (user_id,))
            current_org = cursor.fetchone()
            
            if not current_org or current_org[0] != organization_id:
                if current_org_count >= max_allowed:
                    flash(f'Cannot assign organization. User has reached their package limit of {max_allowed} organizations.', 'danger')
                    return redirect(request.referrer or url_for('dashboard'))
        
        # Update user's organization
        cursor.execute('''
            UPDATE users SET organization_id = ? WHERE id = ?
        ''', (organization_id, user_id))
        
        db.commit()
        flash(f'User assigned to {org_name} successfully!', 'success')
        
    except Exception as e:
        flash(f'Error assigning organization: {e}', 'danger')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@require_login
@require_global_superadmin
def edit_user(user_id):
    """Edit user details - Global Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            is_admin = bool(request.form.get('is_admin'))
            is_superadmin = bool(request.form.get('is_superadmin'))
            # Global admin role is deprecated
            is_global_admin = False
            
            # Additional fields for Global Super Admins
            organization_id = request.form.get('organization_id', type=int)
            subscription_package_id = request.form.get('subscription_package_id', type=int)
            user_status = request.form.get('user_status', 'active')
            
            # Validation
            if not username:
                flash('Username is required', 'error')
                return redirect(url_for('edit_user', user_id=user_id))
            
            # Check if username already exists (excluding current user)
            cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND id != ?', (username, user_id))
            if cursor.fetchone():
                flash('Username already exists', 'error')
                return redirect(url_for('edit_user', user_id=user_id))
            
            # Check if email already exists (excluding current user)
            if email:
                cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(?) AND id != ?', (email, user_id))
                if cursor.fetchone():
                    flash('Email already exists', 'error')
                    return redirect(url_for('edit_user', user_id=user_id))
            
            # Get current user data for audit log
            cursor.execute('SELECT username, email, is_admin, is_superadmin, organization_id, subscription_package_id FROM users WHERE id = ?', (user_id,))
            old_data = cursor.fetchone()
            
            # Prepare update query with new fields (removed global_admin)
            update_fields = ['username = ?', 'email = ?', 'is_admin = ?', 'is_superadmin = ?']
            update_values = [username, email, int(is_admin), int(is_superadmin)]
            
            # Add organization and package if provided
            if organization_id:
                update_fields.append('organization_id = ?')
                update_values.append(organization_id)
            
            if subscription_package_id:
                update_fields.append('subscription_package_id = ?')
                update_values.append(subscription_package_id)
            
            update_values.append(user_id)
            
            # Update user
            cursor.execute(f'''
                UPDATE users 
                SET {', '.join(update_fields)}
                WHERE id = ?
            ''', update_values)
            
            db.commit()
            
            # Prepare old and new values for audit log
            old_values = {
                'username': old_data[0],
                'email': old_data[1],
                'is_admin': old_data[2],
                'is_superadmin': old_data[3],
                'organization_id': old_data[4],
                'subscription_package_id': old_data[5]
            }
            
            new_values = {
                'username': username,
                'email': email,
                'is_admin': is_admin,
                'is_superadmin': is_superadmin
            }
            
            # Add organization and package changes if provided
            if organization_id:
                new_values['organization_id'] = organization_id
            if subscription_package_id:
                new_values['subscription_package_id'] = subscription_package_id
            
            # Log the changes
            log_audit(
                action='USER_UPDATED',
                table_name='users',
                record_id=user_id,
                old_values=old_values,
                new_values=new_values
            )
            
            flash('User updated successfully!', 'success')
            return redirect(url_for('manage_users'))
        
        # GET request - load user data
        cursor.execute('''
            SELECT u.id, u.username, u.email, u.is_admin, u.is_superadmin, 
                   u.organization_id, u.subscription_package_id,
                   o.name as organization_name,
                   sp.name as package_name
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            LEFT JOIN subscription_packages sp ON u.subscription_package_id = sp.id
            WHERE u.id = ?
        ''', (user_id,))
        
        user = cursor.fetchone()
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('manage_users'))
        
        # Get organizations and packages for dropdowns
        cursor.execute('SELECT id, name, industry FROM organizations WHERE status = "active" ORDER BY name')
        organizations = cursor.fetchall()
        
        cursor.execute('SELECT id, name, max_organizations FROM subscription_packages ORDER BY id')
        packages = cursor.fetchall()
        
        user_data = {
            'id': user[0],
            'username': user[1],
            'email': user[2],
            'is_admin': user[3],
            'is_superadmin': user[4],
            'organization_id': user[5],
            'subscription_package_id': user[6],
            'organization_name': user[7],  # Fixed: was user[8]
            'package_name': user[8]  # Fixed: was user[9]
        }
        
        return render_template('edit_user.html', 
                             user=user_data, 
                             organizations=organizations,
                             packages=packages)
        
    except Exception as e:
        flash(f'Error loading user: {e}', 'error')
        print(f"Error in edit_user: {e}")
        return redirect(url_for('manage_users'))

@app.route('/org_admins')
@require_login
@require_org_superadmin
def manage_org_admins():
    """Manage organization admins - Global Superadmin sees all, Organization Superadmin sees their org"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if is_global_superadmin():
            # Global Superadmin sees ALL admins from ALL organizations
            cursor.execute('''
                SELECT u.id, u.user_id, u.username, u.email, u.is_admin, u.is_superadmin, 
                       u.created_at, o.name as organization_name, u.location_id, l.name as location_name
                FROM users u
                JOIN organizations o ON u.organization_id = o.id
                LEFT JOIN locations l ON u.location_id = l.id
                WHERE (u.is_admin = 1 OR u.is_superadmin = 1) AND u.is_global_superadmin = 0
                ORDER BY o.name, u.created_at DESC
            ''')
            admins = cursor.fetchall()
            
            # Get all locations for global view
            cursor.execute('SELECT id, name, organization_id FROM locations ORDER BY name')
            locations = cursor.fetchall()
        else:
            # Organization Superadmin sees only their organization's admins
            org_id = session.get('organization_id')
            cursor.execute('''
                SELECT u.id, u.user_id, u.username, u.email, u.is_admin, u.is_superadmin, 
                       u.created_at, o.name as organization_name, u.location_id, l.name as location_name
                FROM users u
                JOIN organizations o ON u.organization_id = o.id
                LEFT JOIN locations l ON u.location_id = l.id
                WHERE u.organization_id = ? AND (u.is_admin = 1 OR u.is_superadmin = 1)
                ORDER BY u.created_at DESC
            ''', (org_id,))
            admins = cursor.fetchall()
            
            # Get all locations for assignment options
            cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
            locations = cursor.fetchall()
        
        return render_template('manage_org_admins.html', 
                             admins=admins, 
                             locations=locations,
                             is_global_superadmin=is_global_superadmin())
        
    except Exception as e:
        flash(f'Error loading admins: {e}', 'danger')
        return render_template('manage_org_admins.html', admins=[])

@app.route('/create_org_admin', methods=['GET', 'POST'])
@require_login
@require_org_superadmin
def create_org_admin():
    """Create a new admin for the organization - Organization Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            is_superadmin = bool(request.form.get('is_superadmin'))
            location_id = request.form.get('location_id', type=int)  # NEW: Location assignment
            
            # Validation
            if not all([username, email, password, confirm_password]):
                flash('All fields are required.', 'danger')
                cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
                locations = cursor.fetchall()
                return render_template('create_org_admin.html', locations=locations)
            
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
                locations = cursor.fetchall()
                return render_template('create_org_admin.html', locations=locations)
            
            if len(password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
                locations = cursor.fetchall()
                return render_template('create_org_admin.html', locations=locations)
            
            # Check if username already exists in this organization
            cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND organization_id = ?', (username, org_id))
            if cursor.fetchone():
                flash('Username already exists in this organization.', 'danger')
                cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
                locations = cursor.fetchall()
                return render_template('create_org_admin.html', locations=locations)
            
            # Check if email already exists
            cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(?)', (email,))
            if cursor.fetchone():
                flash('Email already registered.', 'danger')
                cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
                locations = cursor.fetchall()
                return render_template('create_org_admin.html', locations=locations)
            
            # Superadmins should not be assigned to specific locations (org-wide access)
            if is_superadmin:
                location_id = None
            
            # Create admin user
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            user_id = generate_unique_user_id(org_id, "USR")
            created_by = session.get('user_id')  # Track who created this admin
            
            cursor.execute('''
                INSERT INTO users (user_id, username, email, password_hash, organization_id, 
                                 is_admin, is_superadmin, location_id, subscription_package_id, created_by)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, 1, ?)
            ''', (user_id, username, email, password_hash, org_id, int(is_superadmin), location_id, created_by))
            
            db.commit()
            
            # Get location name if assigned
            location_name = None
            if location_id:
                cursor.execute('SELECT name FROM locations WHERE id = ?', (location_id,))
                loc_result = cursor.fetchone()
                location_name = loc_result[0] if loc_result else None
            
            # Log the creation
            log_audit(
                action='ORG_ADMIN_CREATED',
                table_name='users',
                record_id=cursor.lastrowid,
                new_values={
                    'username': username,
                    'email': email,
                    'is_admin': True,
                    'is_superadmin': is_superadmin,
                    'organization_id': org_id,
                    'location_id': location_id,
                    'location_name': location_name,
                    'created_by': session.get('username', 'Unknown')
                }
            )
            
            if location_name:
                flash(f'✅ Location Admin account created for {username} at {location_name}!', 'success')
            else:
                flash(f'✅ Admin account created successfully for {username}!', 'success')
            return redirect(url_for('manage_org_admins'))
        
        # GET request - load locations for assignment
        cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
        locations = cursor.fetchall()
        
        return render_template('create_org_admin.html', locations=locations)
        
    except Exception as e:
        flash(f'Error creating admin: {e}', 'danger')
        return render_template('create_org_admin.html')

@app.route('/org_admin/<int:admin_id>/delete', methods=['POST'])
@require_login
@require_org_superadmin
def delete_org_admin(admin_id):
    """Delete an organization admin - Organization Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Get admin details for logging
        cursor.execute('''
            SELECT username, email, is_superadmin 
            FROM users 
            WHERE id = ? AND organization_id = ? AND (is_admin = 1 OR is_superadmin = 1)
        ''', (admin_id, org_id))
        
        admin = cursor.fetchone()
        if not admin:
            flash('Admin not found or access denied.', 'danger')
            return redirect(url_for('manage_org_admins'))
        
        # Prevent self-deletion
        if admin_id == session.get('user_id'):
            flash('You cannot delete your own account.', 'danger')
            return redirect(url_for('manage_org_admins'))
        
        # Delete the admin
        cursor.execute('DELETE FROM users WHERE id = ? AND organization_id = ?', (admin_id, org_id))
        
        if cursor.rowcount == 0:
            flash('Admin not found or access denied.', 'danger')
        else:
            db.commit()
            
            # Log the deletion
            log_audit(
                action='ORG_ADMIN_DELETED',
                table_name='users',
                record_id=admin_id,
                old_values={
                    'username': admin[0],
                    'email': admin[1],
                    'is_superadmin': admin[2],
                    'organization_id': org_id
                },
                new_values={}
            )
            
            flash(f'Admin "{admin[0]}" has been deleted successfully.', 'success')
        
        return redirect(url_for('manage_org_admins'))
        
    except Exception as e:
        flash(f'Error deleting admin: {e}', 'danger')
        return redirect(url_for('manage_org_admins'))

@app.route('/org_admin/<int:admin_id>/edit', methods=['GET', 'POST'])
@require_login
@require_org_superadmin
def edit_org_admin(admin_id):
    """Edit an organization admin - Organization Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Get admin details with location information
        cursor.execute('''
            SELECT id, username, email, is_admin, is_superadmin, location_id
            FROM users 
            WHERE id = ? AND organization_id = ? AND (is_admin = 1 OR is_superadmin = 1)
        ''', (admin_id, org_id))
        
        admin = cursor.fetchone()
        if not admin:
            flash('Admin not found or access denied.', 'danger')
            return redirect(url_for('manage_org_admins'))
        
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            is_superadmin = 1 if request.form.get('is_superadmin') else 0
            is_admin = 1  # Always set to 1 for organization admins
            location_id = request.form.get('location_id', type=int)  # NEW: Location assignment
            
            # Superadmins should not be assigned to locations (org-wide access)
            if is_superadmin:
                location_id = None
            
            # Validation
            if not username or not email:
                flash('Username and email are required.', 'danger')
                return render_template('edit_org_admin.html', admin=admin)
            
            # Check if username/email already exists (excluding current admin)
            cursor.execute('''
                SELECT id FROM users 
                WHERE (username = ? OR email = ?) AND id != ? AND organization_id = ?
            ''', (username, email, admin_id, org_id))
            
            if cursor.fetchone():
                flash('Username or email already exists in your organization.', 'danger')
                return render_template('edit_org_admin.html', admin=admin)
            
            # Prepare update data
            update_fields = ['username = ?', 'email = ?', 'is_admin = ?', 'is_superadmin = ?', 'location_id = ?']
            update_values = [username, email, is_admin, is_superadmin, location_id]
            
            # Add password if provided
            if password:
                password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                update_fields.append('password_hash = ?')
                update_values.append(password_hash)
            
            update_values.append(admin_id)
            
            # Update the admin
            cursor.execute(f'''
                UPDATE users 
                SET {', '.join(update_fields)}
                WHERE id = ? AND organization_id = ?
            ''', update_values + [org_id])
            
            if cursor.rowcount == 0:
                flash('Admin not found or access denied.', 'danger')
            else:
                db.commit()
                
                # Get location name if assigned
                location_name = None
                if location_id:
                    cursor.execute('SELECT name FROM locations WHERE id = ?', (location_id,))
                    loc_result = cursor.fetchone()
                    location_name = loc_result[0] if loc_result else None
                
                # Log the update
                log_audit(
                    action='ORG_ADMIN_UPDATED',
                    table_name='users',
                    record_id=admin_id,
                    old_values={
                        'username': admin[1],
                        'email': admin[2],
                        'is_admin': admin[3],
                        'is_superadmin': admin[4],
                        'location_id': admin[5]
                    },
                    new_values={
                        'username': username,
                        'email': email,
                        'is_admin': is_admin,
                        'is_superadmin': is_superadmin,
                        'location_id': location_id,
                        'location_name': location_name
                    }
                )
                
                flash(f'✅ Admin "{username}" has been updated successfully.', 'success')
                return redirect(url_for('manage_org_admins'))
        
        # GET request - load locations for assignment
        cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
        locations = cursor.fetchall()
        
        admin_data = {
            'id': admin[0],
            'username': admin[1],
            'email': admin[2],
            'is_admin': admin[3],
            'is_superadmin': admin[4],
            'location_id': admin[5]
        }
        
        return render_template('edit_org_admin.html', admin=admin_data, locations=locations)
        
    except Exception as e:
        flash(f'Error editing admin: {e}', 'danger')
        return redirect(url_for('manage_org_admins'))

@app.route('/create_user', methods=['GET', 'POST'])
@require_login
@require_global_superadmin
def create_user():
    """Create a new user - Global Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if request.method == 'POST':
            user_type = request.form.get('user_type', '').strip()
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Handle different user types
            if user_type == 'member':
                # Member creation
                member_name = request.form.get('member_name', '').strip()
                member_phone = request.form.get('member_phone', '').strip()
                member_organization_id = request.form.get('member_organization_id', type=int)
                membership_type = request.form.get('membership_type', '').strip()
                
                # Validate member fields
                if not all([member_name, member_phone, member_organization_id, membership_type]):
                    flash('❌ All member information is required', 'error')
                    return redirect(url_for('create_user'))
                
                # Create member using existing register logic
                try:
                    # Generate unique membership ID using centralized function
                    membership_id = generate_unique_membership_id(member_organization_id, "MBR")
                    
                    # Get the user ID of the person creating this member
                    created_by = session.get('user_id')
                    
                    # Insert member
                    cursor.execute('''
                        INSERT INTO members (membership_id, name, email, phone, membership_type, organization_id, status, created_at, created_by)
                        VALUES (?, ?, ?, ?, ?, ?, 'active', datetime('now'), ?)
                    ''', (membership_id, member_name, email, member_phone, membership_type, member_organization_id, created_by))
                    
                    # Create user account for member
                    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                    # Generate unique user ID
                    user_id = generate_unique_user_id(member_organization_id, "USR")
                    
                    cursor.execute('''
                        INSERT INTO users (user_id, username, email, password_hash, organization_id, is_admin, is_superadmin, subscription_package_id, created_by)
                        VALUES (?, ?, ?, ?, ?, 0, 0, 1, ?)
                    ''', (user_id, username, email, password_hash, member_organization_id, created_by))
                    
                    db.commit()
                    
                    # Log the creation
                    log_audit(
                        action='MEMBER_CREATED',
                        table_name='members',
                        record_id=cursor.lastrowid,
                        new_values={
                            'membership_id': membership_id,
                            'name': member_name,
                            'email': email,
                            'phone': member_phone,
                            'membership_type': membership_type,
                            'organization_id': member_organization_id,
                            'created_by': session.get('username', 'Unknown')
                        }
                    )
                    
                    flash(f'✅ Member "{member_name}" created successfully with ID: {membership_id}!', 'success')
                    return redirect(url_for('manage_users'))
                    
                except Exception as e:
                    db.rollback()
                    flash(f'❌ Error creating member: {e}', 'error')
                    print(f"Error creating member: {e}")
                    return redirect(url_for('create_user'))
            
            else:
                # Admin user creation
                organization_id = request.form.get('organization_id', type=int)
                
                # Set roles based on user type
                is_admin = (user_type == 'admin')
                is_superadmin = (user_type == 'superadmin')
                # Global admin role is deprecated
                is_global_admin = False
            
            # Validation
            errors = []
            if not all([username, email, password]):
                errors.append('Username, email, and password are required')
            if password != confirm_password:
                errors.append('Passwords do not match')
            if len(password) < 6:
                errors.append('Password must be at least 6 characters long')
            if '@' not in email:
                errors.append('Please enter a valid email address')
            if not organization_id:
                errors.append('Organization is required')
            
            if errors:
                for error in errors:
                    flash(f'❌ {error}', 'error')
            else:
                # Check if username already exists
                cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(?)', (username,))
                if cursor.fetchone():
                    flash('❌ Username already exists. Please choose a different one.', 'error')
                else:
                    # Check if email already exists
                    cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(?)', (email,))
                    if cursor.fetchone():
                        flash('❌ Email already registered. Please use a different email.', 'error')
                    else:
                        # Verify organization exists and get its package
                        cursor.execute('''
                            SELECT o.id, o.name, o.subscription_package_id, p.name as package_name
                            FROM organizations o
                            LEFT JOIN subscription_packages p ON o.subscription_package_id = p.id
                            WHERE o.id = ? AND o.status = "active"
                        ''', (organization_id,))
                        organization = cursor.fetchone()
                        
                        if not organization:
                            flash('❌ Invalid organization selected', 'error')
                        else:
                            org_id, org_name, org_package_id, package_name = organization
                            
                            # Global admin role is deprecated - use standard package assignment
                            subscription_package_id = org_package_id or 1  # Use organization's package
                            
                            # Create user
                            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                            
                            # Generate unique user ID
                            user_id = generate_unique_user_id(organization_id, "USR")
                            
                            # Get the user ID of the person creating this user
                            created_by = session.get('user_id')
                            
                            cursor.execute('''
                                INSERT INTO users (user_id, username, email, password_hash, organization_id, 
                                                 is_admin, is_superadmin, subscription_package_id, created_by)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (user_id, username, email, password_hash, organization_id, 
                                  int(is_admin), int(is_superadmin), subscription_package_id, created_by))
                            
                            db.commit()
                            
                            # Log the creation
                            log_audit(
                                action='USER_CREATED',
                                table_name='users',
                                record_id=cursor.lastrowid,
                                new_values={
                                    'username': username,
                                    'email': email,
                                    'user_type': user_type,
                                    'organization_id': organization_id,
                                    'organization_name': org_name,
                                    'is_admin': is_admin,
                                    'is_superadmin': is_superadmin,
                                    'subscription_package_id': subscription_package_id,
                                    'package_name': package_name or 'System Package',
                                    'created_by': session.get('username', 'Unknown')
                                }
                            )
                            
                            flash(f'✅ User "{username}" created successfully!', 'success')
                            return redirect(url_for('manage_users'))
        
        # GET request - load form data
        # Get all organizations with their package information
        cursor.execute('''
            SELECT o.id, o.name, o.industry, o.subscription_package_id, 
                   p.name as package_name, p.price as package_price
            FROM organizations o
            LEFT JOIN subscription_packages p ON o.subscription_package_id = p.id
            WHERE o.status = 'active'
            ORDER BY o.name ASC
        ''')
        organizations = cursor.fetchall()
        
        # Get all packages (for reference, but not used in form anymore)
        cursor.execute('''
            SELECT id, name, description, max_organizations, price
            FROM subscription_packages
            WHERE is_active = 1
            ORDER BY max_organizations ASC
        ''')
        packages = cursor.fetchall()
        
        return render_template('create_user.html', organizations=organizations, packages=packages)
        
    except Exception as e:
        flash(f'Error loading create user form: {e}', 'error')
        print(f"Error in create_user: {e}")
        return redirect(url_for('manage_users'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@require_login
@require_global_superadmin
def delete_user(user_id):
    """Delete user - Global Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get user data before deletion for audit log
        cursor.execute('''
            SELECT username, email, is_admin, is_superadmin, is_global_admin, 
                   organization_id, subscription_package_id
            FROM users WHERE id = ?
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        if not user_data:
            flash('User not found', 'error')
            return redirect(url_for('manage_users'))
        
        # Prevent deletion of Global Superadmin accounts
        cursor.execute('SELECT is_global_superadmin FROM users WHERE id = ?', (user_id,))
        is_global_superadmin = cursor.fetchone()
        if is_global_superadmin and is_global_superadmin[0]:
            flash('Cannot delete Global Superadmin accounts', 'error')
            return redirect(url_for('manage_users'))
        
        # Log the deletion
        log_audit(
            action='USER_DELETED',
            table_name='users',
            record_id=user_id,
            old_values={
                'username': user_data[0],
                'email': user_data[1],
                'is_admin': user_data[2],
                'is_superadmin': user_data[3],
                'is_global_admin': user_data[4],
                'organization_id': user_data[5],
                'subscription_package_id': user_data[6]
            },
            new_values={}
        )
        
        # Delete the user
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        db.commit()
        
        flash(f'User "{user_data[0]}" deleted successfully!', 'success')
        
    except Exception as e:
        flash(f'Error deleting user: {e}', 'error')
        print(f"Error in delete_user: {e}")
    
    return redirect(url_for('manage_users'))

# ============================================================================
# CURRENCY CONVERSION ROUTES
# ============================================================================

# ===========================================================================
# CURRENCY PREFERENCE API (SIMPLIFIED - SYMBOL ONLY, NO CONVERSION)
# ===========================================================================

@app.route('/api/update_currency_preference', methods=['POST'])
@require_login
def api_update_currency_preference():
    """API endpoint for updating user's currency preference"""
    try:
        data = request.get_json()
        currency = data.get('currency')
        
        if not currency:
            return jsonify({
                'success': False,
                'error': 'Currency is required'
            }), 400
        
        # Validate currency
        supported_currencies = get_supported_currencies()
        if currency not in supported_currencies:
            return jsonify({
                'success': False,
                'error': 'Unsupported currency'
            }), 400
        
        # Update user preference
        if update_user_preferred_currency(currency):
            return jsonify({
                'success': True,
                'message': f'Currency preference updated to {currency}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update currency preference'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ===========================================================================
# ORGANIZATION LIMITS ENFORCEMENT
# ===========================================================================

@app.route('/enforce_limits')
@require_login
@require_global_superadmin
def enforce_limits():
    """Manually enforce organization limits on all users"""
    try:
        violations = enforce_existing_limits()
        
        if violations:
            flash(f'Found {len(violations)} users exceeding their package limits. Please review User Management.', 'warning')
        else:
            flash('All users are within their package limits.', 'success')
            
    except Exception as e:
        flash(f'Error enforcing limits: {e}', 'danger')
    
    return redirect(request.referrer or url_for('manage_users'))

@app.route('/manage_users')
@require_login
@require_global_superadmin
def manage_users():
    """Manage all users - Global Superadmin only"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get all users with their organization and package info
        cursor.execute('''
            SELECT 
                u.id, u.username, u.email, u.is_admin, u.is_superadmin, 
                u.is_global_superadmin, u.is_global_admin, u.subscription_package_id,
                u.organization_id,
                o.name as organization_name,
                sp.name as package_name, sp.max_organizations as max_orgs
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            LEFT JOIN subscription_packages sp ON u.subscription_package_id = sp.id
            ORDER BY u.id
        ''')
        users_data = cursor.fetchall()
        
        # Get organization counts for each user
        users = []
        for user_data in users_data:
            user_id = user_data[0]
            org_count = get_user_organization_count(user_id)
            
            user_dict = {
                'id': user_data[0],
                'username': user_data[1],
                'email': user_data[2],
                'is_admin': user_data[3],
                'is_superadmin': user_data[4],
                'is_global_superadmin': user_data[5],
                'is_global_admin': user_data[6],
                'subscription_package_id': user_data[7],
                'organization_id': user_data[8],
                'organization_name': user_data[9],
                'package_name': user_data[10],
                'max_orgs': user_data[11] or 0,
                'org_count': org_count
            }
            users.append(user_dict)
        
        # Get all packages for the modal
        cursor.execute('''
            SELECT id, name, description, max_organizations, price
            FROM subscription_packages
            WHERE is_active = 1
            ORDER BY max_organizations ASC
        ''')
        packages = cursor.fetchall()
        
        # Get all organizations for the modal
        cursor.execute('''
            SELECT id, name, industry
            FROM organizations
            WHERE status = 'active'
            ORDER BY name ASC
        ''')
        organizations = cursor.fetchall()
        
        return render_template('manage_users.html', users=users, packages=packages, organizations=organizations)
        
    except Exception as e:
        flash(f'Error loading users: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/fee_settings', methods=['GET', 'POST'])
@require_login
@require_global_superadmin
def fee_settings():
    """Global Admin fee management settings"""
    if request.method == 'POST':
        try:
            fee_percentage = float(request.form.get('deduction_fee_percentage', 0))
            
            if fee_percentage < 0 or fee_percentage > 100:
                flash('Fee percentage must be between 0 and 100', 'danger')
                return redirect(url_for('fee_settings'))
            
            # Update fee percentage
            update_setting('deduction_fee_percentage', str(fee_percentage))
            flash(f'Fee percentage updated to {fee_percentage}%', 'success')
            return redirect(url_for('fee_settings'))
            
        except ValueError:
            flash('Invalid fee percentage value', 'danger')
            return redirect(url_for('fee_settings'))
    
    # Get current fee percentage
    current_fee = get_deduction_fee_percentage()
    return render_template('fee_settings.html', current_fee=current_fee)

@app.route('/settings', methods=['GET', 'POST'])
@require_login
def admin_settings():
    """Enhanced admin settings with card design options"""
    # Get organization ID
    org_id = session.get('organization_id')
    if not org_id:
        flash("Organization not found. Please log in again.", "danger")
        return redirect(url_for('login'))
    
    # Get database connection
    db = get_db()
    cursor = db.cursor()
    if request.method == 'POST':
        try:
            if 'save_general' in request.form:
                # Handle general settings form submission
                currency_symbol = request.form.get('currency_symbol', '').strip()
                currency_code = request.form.get('currency_code', 'USD').strip()
                default_language = request.form.get('default_language', 'en').strip()
                
                # Validation
                if not currency_symbol:
                    flash("Currency symbol is required.", "danger")
                    return redirect(url_for('admin_settings'))
                
                if len(currency_symbol) > 5:
                    flash("Currency symbol must be 5 characters or less.", "danger")
                    return redirect(url_for('admin_settings'))
                
                if currency_code not in ['USD', 'EUR', 'GBP', 'XAF']:
                    flash("Invalid currency code selected.", "danger")
                    return redirect(url_for('admin_settings'))
                
                if default_language not in ['en', 'fr', 'es']:
                    flash("Invalid language selected.", "danger")
                    return redirect(url_for('admin_settings'))
                
                # Update settings
                updates_made = []
                errors = []
                
                # Update currency symbol
                if update_setting('currency_symbol', currency_symbol, org_id):
                    updates_made.append("Currency symbol")
                else:
                    errors.append("currency symbol")
                
                # Update currency code
                if update_setting('currency_code', currency_code, org_id):
                    updates_made.append("Currency code")
                else:
                    errors.append("currency code")
                
                # Update default language
                if update_setting('default_language', default_language, org_id):
                    updates_made.append("Default language")
                    # Immediately update session language
                    session['language'] = default_language
                else:
                    errors.append("default language")
                
                # Provide feedback
                if updates_made and not errors:
                    flash("✅ General settings updated successfully!", "success")
                elif updates_made and errors:
                    flash(f"⚠️ Partially updated: {', '.join(updates_made)}. Failed: {', '.join(errors)}", "warning")
                else:
                    flash("❌ Failed to update general settings. Please try again.", "danger")
                
            elif 'save_card' in request.form:
                # Handle card design form submission
                card_company_name = request.form.get('card_company_name', '').strip()
                card_primary_color = request.form.get('card_primary_color', '#667eea').strip()
                card_secondary_color = request.form.get('card_secondary_color', '#764ba2').strip()
                
                # Validate colors (simple regex for hex colors)
                import re
                if not re.match(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', card_primary_color):
                    flash("Invalid primary color format. Please use a valid hex color code.", "danger")
                    return redirect(url_for('admin_settings') + '#card')
                    
                if not re.match(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', card_secondary_color):
                    flash("Invalid secondary color format. Please use a valid hex color code.", "danger")
                    return redirect(url_for('admin_settings') + '#card')
                
                try:
                    # Update organization with card design settings
                    cursor.execute('''
                        UPDATE organizations 
                        SET card_company_name = ?, 
                            card_primary_color = ?, 
                            card_secondary_color = ?
                        WHERE id = ?
                    ''', (card_company_name, card_primary_color, card_secondary_color, org_id))
                    
                    db.commit()
                    flash("✅ Card design settings saved successfully!", "success")
                    
                except Exception as e:
                    db.rollback()
                    flash(f"❌ Error saving card design: {str(e)}", "danger")
                    print(f"Card design save error: {e}")
                
                # Redirect back to card tab after saving
                return redirect(url_for('admin_settings') + '#card')
        
        except Exception as e:
            flash(f"❌ Error updating settings: {str(e)}", "danger")
            print(f"Settings update error: {e}")
        
        return redirect(url_for('admin_settings'))
    
    # GET request - display current settings
    try:
        # Get current organization's card design settings
        cursor.execute('''
            SELECT card_company_name, card_primary_color, card_secondary_color
            FROM organizations 
            WHERE id = ?
        ''', (org_id,))
        
        org_data = cursor.fetchone()
        card_company_name = org_data[0] if org_data and org_data[0] else ''
        card_primary_color = org_data[1] if org_data and org_data[1] else '#667eea'
        card_secondary_color = org_data[2] if org_data and org_data[2] else '#764ba2'
        
        # Get current general settings
        current_symbol = get_setting('currency_symbol', '$', org_id) or '$'
        current_code = get_setting('currency_code', 'USD', org_id) or 'USD'
        current_language = get_setting('default_language', 'en', org_id) or 'en'
        
        # Ensure current_language is valid
        if current_language not in ['en', 'fr', 'es']:
            current_language = 'en'
        
        # Define available currencies
        currencies = [
            ('$', 'USD', 'US Dollar'),
            ('€', 'EUR', 'Euro'),
            ('£', 'GBP', 'British Pound'),
            ('XAF', 'XAF', 'Central African Franc')
        ]
        
        # Define available languages
        languages = {
            'en': 'English',
            'fr': 'Français',
            'es': 'Español'
        }
        
        return render_template('admin_settings.html',
                             current_symbol=current_symbol,
                             current_code=current_code,
                             current_language=current_language,
                             currencies=currencies,
                             LANGUAGES=languages,
                             card_company_name=card_company_name,
                             card_primary_color=card_primary_color,
                             card_secondary_color=card_secondary_color)
        
    except Exception as e:
        flash(f"Error loading settings: {str(e)}", "danger")
        print(f"Settings load error: {e}")
        
        # Return with safe defaults
        return render_template('admin_settings.html',
                             current_symbol='$',
                             current_code='USD',
                             current_language='en',
                             currencies=[('$', 'USD', 'US Dollar')],
                             LANGUAGES={'en': 'English'})

# Add a route to force refresh settings
@app.route('/refresh-settings')
@require_login
def refresh_settings():
    """Force refresh settings and redirect to dashboard"""
    try:
        org_id = session.get('organization_id')
        if org_id:
            # Get fresh settings from database
            current_language = get_setting('default_language', 'en', org_id) or 'en'
            session['language'] = current_language
        
        flash("Settings refreshed successfully!", "success")
    except Exception as e:
        flash(f"Error refreshing settings: {e}", "warning")
    
    return redirect(url_for('dashboard'))

# Enhanced setting functions with better error handling
def get_setting(key, default_value=None, organization_id=None):
    """Get a setting value from the database with enhanced error handling"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if organization_id:
            cursor.execute('SELECT setting_value FROM settings WHERE setting_key = ? AND organization_id = ?', 
                         (key, organization_id))
        else:
            cursor.execute('SELECT setting_value FROM global_settings WHERE setting_key = ?', (key,))
        
        result = cursor.fetchone()
        if result:
            return result[0] if isinstance(result, tuple) else result['setting_value']
        else:
            return default_value
            
    except sqlite3.Error as e:
        print(f"Database error getting setting {key}: {e}")
        return default_value
    except Exception as e:
        print(f"Error getting setting {key}: {e}")
        return default_value

def update_setting(key, value, organization_id=None):
    """Update a setting value in the database with enhanced error handling"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if organization_id:
            # Check if setting exists
            cursor.execute('SELECT id FROM settings WHERE setting_key = ? AND organization_id = ?', 
                         (key, organization_id))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute('''
                    UPDATE settings 
                    SET setting_value = ?, updated_at = datetime('now')
                    WHERE setting_key = ? AND organization_id = ?
                ''', (value, key, organization_id))
            else:
                cursor.execute('''
                    INSERT INTO settings (setting_key, setting_value, organization_id, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                ''', (key, value, organization_id))
        else:
            # Global setting
            cursor.execute('''
                INSERT OR REPLACE INTO global_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, datetime('now'))
            ''', (key, value))
        
        db.commit()
        print(f"✅ Successfully updated setting {key} = {value}")  # Debug log
        return True
        
    except sqlite3.Error as e:
        print(f"Database error updating setting {key}: {e}")
        try:
            db.rollback()
        except:
            pass
        return False
    except Exception as e:
        print(f"Error updating setting {key}: {e}")
        return False

# Add a debug route to check settings
@app.route('/debug/check-settings')
@require_login
def debug_check_settings():
    """Debug route to check current settings"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Check if settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        settings_table_exists = cursor.fetchone() is not None
        
        # Get all settings for this org
        if settings_table_exists and org_id:
            cursor.execute('SELECT setting_key, setting_value, updated_at FROM settings WHERE organization_id = ?', (org_id,))
            org_settings = cursor.fetchall()
        else:
            org_settings = []
        
        # Check global settings
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='global_settings'")
        global_table_exists = cursor.fetchone() is not None
        
        if global_table_exists:
            cursor.execute('SELECT setting_key, setting_value, updated_at FROM global_settings')
            global_settings = cursor.fetchall()
        else:
            global_settings = []
        
        html = f"""
        <html>
        <head><title>Settings Debug</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>Settings Debug Information</h1>
        
        <h2>Organization ID: {org_id}</h2>
        
        <h3>Table Status:</h3>
        <ul>
            <li>Settings table exists: {'Yes' if settings_table_exists else 'No'}</li>
            <li>Global settings table exists: {'Yes' if global_table_exists else 'No'}</li>
        </ul>
        
        <h3>Organization Settings ({len(org_settings)} found):</h3>
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr><th>Key</th><th>Value</th><th>Updated At</th></tr>
        """
        
        for setting in org_settings:
            html += f"<tr><td>{setting[0]}</td><td>{setting[1]}</td><td>{setting[2]}</td></tr>"
        
        html += f"""
        </table>
        
        <h3>Global Settings ({len(global_settings)} found):</h3>
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr><th>Key</th><th>Value</th><th>Updated At</th></tr>
        """
        
        for setting in global_settings:
            html += f"<tr><td>{setting[0]}</td><td>{setting[1]}</td><td>{setting[2]}</td></tr>"
        
        html += """
        </table>
        
        <h3>Test Current Values:</h3>
        <ul>
        """
        
        html += f"<li>Currency Symbol: '{get_setting('currency_symbol', '$', org_id)}'</li>"
        html += f"<li>Currency Code: '{get_setting('currency_code', 'USD', org_id)}'</li>"
        html += f"<li>Default Language: '{get_setting('default_language', 'en', org_id)}'</li>"
        
        html += """
        </ul>
        
        <br>
        <a href="/settings">← Back to Settings</a>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"<html><body><h1>Error: {e}</h1><a href='/settings'>← Back to Settings</a></body></html>"

# Add this route to create missing settings tables
@app.route('/debug/create-settings-tables')
@require_login
def create_settings_tables():
    """Create settings tables if they don't exist"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Create settings table for organization-specific settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                organization_id INTEGER NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                UNIQUE(setting_key, organization_id)
            )
        ''')
        
        # Create global_settings table for system-wide settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        db.commit()
        
        return """
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>✅ Settings Tables Created Successfully!</h1>
        
        <p>Both <code>settings</code> and <code>global_settings</code> tables have been created.</p>
        
        <h3>Next Steps:</h3>
        <ol>
            <li><a href="/debug/check-settings">Check current settings</a></li>
            <li><a href="/settings">Go to Settings page</a></li>
            <li>Try updating your currency and language settings</li>
        </ol>
        
        <a href="/dashboard">← Back to Dashboard</a>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>❌ Error Creating Settings Tables</h1>
        <p>Error: {str(e)}</p>
        <a href="/dashboard">← Back to Dashboard</a>
        </body>
        </html>
        """

@app.route('/set_language/<language>')
def set_language(language=None):
    if language and language in LANGUAGES:
        session['language'] = language
        if session.get('admin'):
            org_id = session.get('organization_id')
            update_setting('default_language', language, org_id)
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/export')
@require_login
def export_members():
    try:
        db = get_db()
        cursor = db.cursor()
        
        if is_global_superadmin():
            cursor.execute('''
                SELECT membership_id, name, email, phone, membership_type, 
                       expiration_date, status, organization_id
                FROM members ORDER BY organization_id, created_at DESC
            ''')
            filename = "all_members_export.csv"
        else:
            admin_org_id = session.get('organization_id')
            if not admin_org_id:
                flash("Organization ID not found in session.", "danger")
                return redirect(url_for('members'))
            
            cursor.execute('''
                SELECT membership_id, name, email, phone, membership_type, 
                       expiration_date, status, organization_id
                FROM members 
                WHERE organization_id = ? 
                ORDER BY created_at DESC
            ''', (admin_org_id,))
            filename = f"org_{admin_org_id}_members_export.csv"
        
        members = cursor.fetchall()
        
        csv_content = "Membership ID,Name,Email,Phone,Membership Type,Expiration Date,Status,Organization ID\n"
        
        for m in members:
            csv_content += ",".join(str(field) if field else "" for field in m) + "\n"
        
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except sqlite3.Error as e:                                                                                                                     
        flash(f"Export error: {e}", "danger")                                                                                                      
        return redirect(url_for('members'))

@app.route('/test_email')
@require_login
def test_email():
    test_email_address = "nextsmiles44@gmail.com"

    html_content = f"""
    <html>
    <body>
        <h2>Email Configuration Test</h2>
        <p>If you're reading this, your email configuration is working correctly!</p>
        <p>Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body>
    </html>
    """

    success = send_email_notification(
        test_email_address,
        "�� MemberSync Email Test",
        html_content
    )

    if success:
        flash("✅ Test email sent successfully! Check your inbox.", "success")
    else:
        flash("❌ Test email failed. Check the console for error details.", "danger")

    return redirect(url_for('dashboard'))

@app.route('/send_manual_reminder/<membership_id>')
@require_login
@require_member_access
def send_manual_reminder(membership_id):
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT name, email, phone, membership_type, expiration_date
            FROM members WHERE membership_id = ?
        ''', (membership_id,))
        
        member = cursor.fetchone()
        
        if member:
            name, email, phone, membership_type, expiration_date = member
            exp_date = datetime.strptime(expiration_date, '%Y-%m-%d').strftime('%B %d, %Y')
            
            email_subject = f"🔔 Membership Renewal Reminder - {membership_id}"
            email_message = f"""
            <html>
            <body>
                <h2>Membership Renewal Reminder</h2>
                <p>Dear {name},</p>
                <p>This is a friendly reminder that your <strong>{membership_type}</strong> membership (ID: {membership_id}) expires on <strong>{exp_date}</strong>.</p>
                <p>Please contact us to renew your membership.</p>
                <p>Thank you!</p>
                <br>
                <p>Best regards,<br>MemberSync Team</p>
            </body>
            </html>
            """
            
            email_sent = False
            if email:
                email_sent = send_email_notification(email, email_subject, email_message)
            
            org_id = session.get('organization_id')
            cursor.execute('''
                INSERT INTO notifications (membership_id, organization_id, type, message, sent_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (membership_id, org_id, 'manual_reminder', 
                  f"Manual reminder sent - Email: {email_sent}", 
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            db.commit()
            
            if email_sent:
                flash("Reminder sent successfully!", "success")
            else:
                flash("Failed to send reminder. Check email configuration.", "warning")
        else:
            flash("Member not found.", "danger")
            
    except Exception as e:
        flash(f"Error sending reminder: {e}", "danger")
    
    return redirect(url_for('member_profile', membership_id=membership_id))

# ============================================================================
# SCHEDULER FUNCTIONS
# ============================================================================

def check_expiring_memberships():
    """Check for memberships expiring in the next 7 days"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT id, task_name, task_type, message_content, schedule_time, organization_id
            FROM scheduled_tasks
            WHERE status = 'active'
        ''')
        
        tasks = cursor.fetchall()
        
        for task in tasks:
            task_id, task_name, task_type, message_content, schedule_time, organization_id = task
            
            if task_type == 'inactive':
                cursor.execute('''
                    SELECT membership_id, name, email, phone
                    FROM members 
                    WHERE status = 'active' 
                    AND organization_id = ?
                    AND datetime(created_at) < datetime('now', '-30 days')
                ''', (organization_id,))
                inactive_members = cursor.fetchall()
                
                for member in inactive_members:
                    member_id, name, email, phone = member
                    personalized_message = message_content.replace('[NAME]', name).replace('[MEMBER_ID]', member_id)
                    
                    if email:
                        send_email_notification(email, f"We Miss You - {task_name}", personalized_message)
                    if phone and validate_phone_number_enhanced(phone)[0]:
                        send_sms_notification(format_phone_number(phone), personalized_message[:160])
            
            elif task_type == 'custom':
                cursor.execute('''
                    SELECT membership_id, name, email, phone
                    FROM members 
                    WHERE status = 'active' AND organization_id = ?
                ''', (organization_id,))
                all_members = cursor.fetchall()
                
                for member in all_members:
                    member_id, name, email, phone = member
                    personalized_message = message_content.replace('[NAME]', name).replace('[MEMBER_ID]', member_id)
                    
                    if email:
                        send_email_notification(email, task_name, personalized_message)
                    if phone and validate_phone_number_enhanced(phone)[0]:
                        send_sms_notification(format_phone_number(phone), personalized_message[:160])
    
    except Exception as e:
        print(f"Error running scheduled tasks: {e}")

def run_scheduler():
    """Run the scheduler in a separate thread"""
    schedule.every().day.at("09:00").do(check_expiring_memberships)
    
    while True:
        schedule.run_pending()
        time.sleep(3600)

# ============================================================================
# DEVELOPMENT/DEBUG ROUTES (REMOVE IN PRODUCTION)
# ============================================================================

@app.route('/create-initial-admin')
def create_initial_admin():
    """One-time route to create the first global admin (remove after use)"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_global_superadmin = 1')
        admin_count = cursor.fetchone()[0]
        
        if admin_count > 0:
            return """
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f8f9fa; border-radius: 10px;">
                <h2 style="color: #dc3545;">❌ Access Denied</h2>
                <p>Global admin already exists. This route is no longer available for security reasons.</p>
                <p><a href="/login" style="color: #007bff; text-decoration: none;">← Back to Login</a></p>
            </div>
            """
        
        username = "globaladmin"
        password = "TempPass123!"
        email = "admin@membersync.local"
        
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, organization_id, 
                             is_admin, is_superadmin, is_global_superadmin)
            VALUES (?, ?, ?, 1, 1, 1, 1)
        ''', (username, email, password_hash))
        
        db.commit()
        
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 10px;">
            <h2 style="color: #155724;">✅ Initial Global Admin Created Successfully!</h2>
            <div style="background: white; padding: 15px; border-radius: 5px; margin: 15px 0;">
                <p><strong>Username:</strong> <code>{username}</code></p>
                <p><strong>Password:</strong> <code>{password}</code></p>
                <p><strong>Email:</strong> <code>{email}</code></p>
            </div>
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 15px 0;">
                <p><strong style="color: #856404;">⚠️ IMPORTANT SECURITY NOTICE:</strong></p>
                <ul style="color: #856404; margin: 10px 0;">
                    <li>Log in immediately and change the password</li>
                    <li>Update the email address to your actual email</li>
                    <li>This route will be disabled after first use</li>
                    <li>Remove this route from production code</li>
                </ul>
            </div>
            <p style="text-align: center;">
                <a href="/login" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                    🔐 Login Now
                </a>
            </p>
        </div>
        """
        
    except Exception as e:
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 10px;">
            <h2 style="color: #721c24;">❌ Error</h2>
            <p>Error creating initial admin: {e}</p>
            <p><a href="/login" style="color: #007bff; text-decoration: none;">← Back to Login</a></p>
        </div>
        """
##############################################################################

# Add this debug route to your app.py (remove after debugging)
@app.route('/debug/check-db')
def debug_check_db():
    """Debug route to check database status"""
    try:
        db = get_db()
        cursor = db.cursor()

        # Check if organizations table exists and has data
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='organizations'")
        org_table_exists = cursor.fetchone() is not None

        # Check if users table exists and has data
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        users_table_exists = cursor.fetchone() is not None

        # Check organizations
        if org_table_exists:
            cursor.execute("SELECT id, name FROM organizations LIMIT 5")
            organizations = cursor.fetchall()
        else:
            organizations = []

        # Check users
        if users_table_exists:
            cursor.execute("SELECT id, username, email, organization_id, is_global_superadmin FROM users LIMIT 5")
            users = cursor.fetchall()
        else:
            users = []

        # Check for global admin specifically
        if users_table_exists:
            cursor.execute("SELECT username, email, organization_id, is_global_superadmin FROM users WHERE username = 'globaladmin'")
            global_admin = cursor.fetchone()
        else:
            global_admin = None

        debug_info = f"""
        <html>
        <head><title>Database Debug Info</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>Database Debug Information</h1>

        <h2>Table Status:</h2>
        <ul>
            <li>Organizations table exists: <strong>{'Yes' if org_table_exists else 'No'}</strong></li>
            <li>Users table exists: <strong>{'Yes' if users_table_exists else 'No'}</strong></li>
        </ul>

        <h2>Organizations ({len(organizations)} found):</h2>
        <ul>
        """

        for org in organizations:
            debug_info += f"<li>ID: {org[0]}, Name: {org[1]}</li>"

        debug_info += f"""
        </ul>

        <h2>Users ({len(users)} found):</h2>
        <ul>
        """

        for user in users:
            debug_info += f"<li>ID: {user[0]}, Username: {user[1]}, Email: {user[2]}, Org ID: {user[3]}, Global Admin: {user[4]}</li>"

        debug_info += f"""
        </ul>

        <h2>Global Admin Status:</h2>
        """

        if global_admin:
            debug_info += f"""
            <div style="background: #d4edda; padding: 15px; border-radius: 5px;">
                <strong>✅ Global Admin Found:</strong><br>
                Username: {global_admin[0]}<br>
                Email: {global_admin[1]}<br>
                Organization ID: {global_admin[2]}<br>
                Is Global Superadmin: {global_admin[3]}
            </div>
            """
        else:
            debug_info += """
            <div style="background: #f8d7da; padding: 15px; border-radius: 5px;">
                <strong>❌ No Global Admin Found</strong>
            </div>
            """

        debug_info += """
        <br>
        <a href="/login">← Back to Login</a>
        </body>
        </html>
        """

        return debug_info

    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>Database Error</h1>
        <div style="background: #f8d7da; padding: 15px; border-radius: 5px; color: #721c24;">
            <strong>Error:</strong> {str(e)}
        </div>
        <br>
        <a href="/login">← Back to Login</a>
        </body>
        </html>
        """

#############################################################################

# Add this route to manually initialize the database
@app.route('/debug/init-db')
def debug_init_db():
    """Manually initialize database and create global admin"""
    try:
        # Force initialize database
        init_db()

        # Check if global admin was created
        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT username, email FROM users WHERE username = 'globaladmin'")
        global_admin = cursor.fetchone()

        if global_admin:
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>✅ Database Initialized Successfully!</h1>
            <div style="background: #d4edda; padding: 15px; border-radius: 5px;">
                <h3>Global Admin Created:</h3>
                <p><strong>Username:</strong> {global_admin[0]}</p>
                <p><strong>Password:</strong> ChangeMe123!</p>
                <p><strong>Email:</strong> {global_admin[1]}</p>
            </div>
            <br>
            <a href="/login" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                Go to Login
            </a>
            </body>
            </html>
            """
        else:
            return """
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>❌ Database Initialization Failed</h1>
            <p>Global admin was not created. Check the console for errors.</p>
            <a href="/login">← Back to Login</a>
            </body>
            </html>
            """

    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>❌ Database Initialization Error</h1>
        <div style="background: #f8d7da; padding: 15px; border-radius: 5px; color: #721c24;">
            <strong>Error:</strong> {str(e)}
        </div>
        <a href="/login">← Back to Login</a>
        </body>
        </html>
        """


# Add this route to your app.py to fix the database schema
@app.route('/debug/fix-schema')
def fix_database_schema():
    """Fix missing columns in the database"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        messages = []
        
        # Check and add missing columns to users table
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add missing columns if they don't exist
        if 'is_global_superadmin' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_global_superadmin INTEGER DEFAULT 0')
            messages.append("✅ Added is_global_superadmin column")
        else:
            messages.append("ℹ️ is_global_superadmin column already exists")
        
        if 'is_superadmin' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_superadmin INTEGER DEFAULT 0')
            messages.append("✅ Added is_superadmin column")
        else:
            messages.append("ℹ️ is_superadmin column already exists")
        
        if 'is_admin' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
            messages.append("✅ Added is_admin column")
        else:
            messages.append("ℹ️ is_admin column already exists")
        
        # Check organizations table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='organizations'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE organizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    industry TEXT,
                    location TEXT DEFAULT 'Not Specified',
                    status TEXT DEFAULT 'active',  
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            messages.append("✅ Created organizations table")
        
        # Check if Global Admin Organization exists
        cursor.execute('SELECT id FROM organizations WHERE id = 1')
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO organizations (id, name, industry, status)
                VALUES (1, 'Global System Administration', 'System Management', 'active')
            ''')
            messages.append("✅ Created Global Admin Organization")
        else:
            messages.append("ℹ️ Global Admin Organization already exists")
        
        # Check if global admin user exists
        cursor.execute('SELECT id FROM users WHERE username = ? AND organization_id = 1', ('globaladmin',))
        if not cursor.fetchone():
            password_hash = generate_password_hash('ChangeMe123!')
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, organization_id, is_admin, is_superadmin, is_global_superadmin)
                VALUES (?, ?, ?, 1, 1, 1, 1)
            ''', ('globaladmin', 'admin@system.local', password_hash))
            messages.append("✅ Created global admin user")
        else:
            # Update existing user to have proper permissions
            cursor.execute('''
                UPDATE users 
                SET is_admin = 1, is_superadmin = 1, is_global_superadmin = 1, organization_id = 1
                WHERE username = ? AND organization_id = 1
            ''', ('globaladmin',))
            messages.append("✅ Updated global admin user permissions")
        
        db.commit()
        
        # Verify the fix
        cursor.execute('SELECT username, email, is_admin, is_superadmin, is_global_superadmin FROM users WHERE username = ?', ('globaladmin',))
        admin_user = cursor.fetchone()
        
        html_response = f"""
        <html>
        <head>
            <title>Database Schema Fixed</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                .success {{ background: #d4edda; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .info {{ background: #d1ecf1; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .credential-box {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .btn {{ background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 5px; }}
            </style>
        </head>
        <body>
            <h1>🔧 Database Schema Fixed!</h1>
            
            <h2>Changes Made:</h2>
            <ul>
        """
        
        for message in messages:
            html_response += f"<li>{message}</li>"
        
        html_response += """
            </ul>
            
            <div class="credential-box">
                <h3>🔑 Login Credentials:</h3>
        """
        
        if admin_user:
            html_response += f"""
                <p><strong>Username:</strong> {admin_user[0]}</p>
                <p><strong>Password:</strong> ChangeMe123!</p>
                <p><strong>Email:</strong> {admin_user[1]}</p>
                <p><strong>Permissions:</strong> Admin: {admin_user[2]}, Superadmin: {admin_user[3]}, Global Superadmin: {admin_user[4]}</p>
            """
        
        html_response += """
            </div>
            
            <h3>Next Steps:</h3>
            <ol>
                <li>Go to the login page</li>
                <li>Use the credentials above</li>
                <li>Change the password immediately after login</li>
            </ol>
            
            <a href="/login" class="btn">🔐 Go to Login</a>
            <a href="/debug/check-db" class="btn">🔍 Check Database Status</a>
        </body>
        </html>
        """
        
        return html_response
        
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>❌ Schema Fix Error</h1>
        <div style="background: #f8d7da; padding: 15px; border-radius: 5px; color: #721c24;">
            <strong>Error:</strong> {str(e)}
        </div>
        <p>You may need to delete the database.db file and restart the application.</p>
        <a href="/login">← Back to Login</a>
        </body>
        </html>
        """
##############################################################################

# Add these missing routes to your app.py

# ============================================================================
# MISSING ROUTES - ADD THESE TO YOUR APP.PY
# ============================================================================

@app.route('/schedule_message', methods=['GET', 'POST'])
@require_login
def schedule_message():
    """Schedule messages for later delivery"""
    if request.method == 'POST':
        try:
            task_name = request.form.get('task_name', '').strip()
            task_type = request.form.get('task_type', '')
            message_content = request.form.get('message_content', '').strip()
            schedule_time = request.form.get('schedule_time', '')

            if not all([task_name, task_type, message_content]):
                flash('All fields are required for scheduling messages.', 'danger')
                return render_template('schedule_message.html')

            org_id = session.get('organization_id')

            db = get_db()
            cursor = db.cursor()

            cursor.execute('''
                INSERT INTO scheduled_tasks (task_name, task_type, message_content, schedule_time, organization_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (task_name, task_type, message_content, schedule_time, org_id))

            db.commit()
            flash('Message scheduled successfully!', 'success')
            return redirect(url_for('communication_center'))

        except Exception as e:
            flash(f'Error scheduling message: {e}', 'danger')

    return render_template('schedule_message.html')

@app.route('/scheduled_tasks')
@require_login
def scheduled_tasks():
    """View and manage scheduled tasks"""
    try:
        db = get_db()
        cursor = db.cursor()

        org_id = session.get('organization_id')
        cursor.execute('''
            SELECT id, task_name, task_type, message_content, schedule_time, status, created_at
            FROM scheduled_tasks
            WHERE organization_id = ?
            ORDER BY created_at DESC
        ''', (org_id,))

        tasks = cursor.fetchall()
        return render_template('scheduled_tasks.html', tasks=tasks)

    except Exception as e:
        flash(f'Error loading scheduled tasks: {e}', 'danger')
        return render_template('scheduled_tasks.html', tasks=[])

@app.route('/delete_scheduled_task/<int:task_id>', methods=['POST'])
@require_login
def delete_scheduled_task(task_id):
    """Delete a scheduled task"""
    try:
        db = get_db()
        cursor = db.cursor()

        org_id = session.get('organization_id')
        cursor.execute('DELETE FROM scheduled_tasks WHERE id = ? AND organization_id = ?', (task_id, org_id))
        db.commit()

        flash('Scheduled task deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting task: {e}', 'danger')

    return redirect(url_for('scheduled_tasks'))

@app.route('/prepaid_reports')
@require_login
def prepaid_reports():
    """Comprehensive prepaid reports with filters and export"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Get filter parameters
        start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        transaction_type = request.args.get('transaction_type', 'all')
        member_id = request.args.get('member_id', '')
        
        # Build filter query
        filters = []
        params = []
        
        if is_global_superadmin():
            # Global admins can see all organizations or filter by org
            filter_org_id = request.args.get('org_id', type=int)
            if filter_org_id:
                filters.append('pt.organization_id = ?')
                params.append(filter_org_id)
                org_id = filter_org_id
        else:
            # Regular admins see only their organization
            filters.append('pt.organization_id = ?')
            params.append(org_id)
        
        # Location filter handling
        # Location admins: Automatically restricted to their assigned location (cannot override)
        # Org super admins: Can optionally filter by location
        location_id = None
        if is_location_admin():
            # Location admin is automatically restricted to their assigned location
            location_id = session.get('location_id')
            if location_id:
                filters.append('m.location_id = ?')
                params.append(location_id)
        elif is_org_superadmin():
            # Org super admin can optionally filter by location
            location_id = request.args.get('location_id', type=int)
            if location_id:
                filters.append('m.location_id = ?')
                params.append(location_id)
        
        # Date range filter
        filters.append('date(pt.transaction_date) BETWEEN ? AND ?')
        params.extend([start_date, end_date])
        
        # Transaction type filter
        if transaction_type != 'all':
            filters.append('pt.transaction_type = ?')
            params.append(transaction_type)
        
        # Member ID filter
        if member_id:
            filters.append('pt.membership_id LIKE ?')
            params.append(f'%{member_id}%')
        
        where_clause = ' AND '.join(filters) if filters else '1=1'
        
        # Get detailed transactions
        cursor.execute(f'''
            SELECT 
                pt.id,
                pt.membership_id,
                m.name as member_name,
                pt.transaction_type,
                pt.amount,
                pt.bonus_amount,
                pt.balance_before,
                pt.balance_after,
                pt.description,
                pt.transaction_date,
                o.name as organization_name,
                l.name as location_name
            FROM prepaid_transactions pt
            JOIN members m ON pt.membership_id = m.membership_id AND pt.organization_id = m.organization_id
            JOIN organizations o ON pt.organization_id = o.id
            LEFT JOIN locations l ON m.location_id = l.id
            WHERE {where_clause}
            ORDER BY pt.transaction_date DESC
            LIMIT 500
        ''', params)
        
        transactions = cursor.fetchall()
        
        # Calculate statistics (join with members for location filtering)
        cursor.execute(f'''
            SELECT 
                COUNT(*) as total_transactions,
                SUM(CASE WHEN pt.transaction_type = 'recharge' THEN pt.amount ELSE 0 END) as total_recharges,
                SUM(CASE WHEN pt.transaction_type = 'usage' THEN pt.amount ELSE 0 END) as total_usage,
                SUM(CASE WHEN pt.transaction_type = 'fee' THEN pt.amount ELSE 0 END) as total_fees,
                SUM(CASE WHEN pt.transaction_type = 'bonus' THEN pt.amount ELSE 0 END) as total_bonuses,
                COUNT(DISTINCT pt.membership_id) as unique_members
            FROM prepaid_transactions pt
            JOIN members m ON pt.membership_id = m.membership_id AND pt.organization_id = m.organization_id
            WHERE {where_clause}
        ''', params)
        
        stats = cursor.fetchone()
        statistics = {
            'total_transactions': stats[0] or 0,
            'total_recharges': float(stats[1]) if stats[1] else 0.0,
            'total_usage': float(stats[2]) if stats[2] else 0.0,
            'total_fees': float(stats[3]) if stats[3] else 0.0,
            'total_bonuses': float(stats[4]) if stats[4] else 0.0,
            'unique_members': stats[5] or 0,
            'net_balance': (float(stats[1]) if stats[1] else 0.0) - (float(stats[2]) if stats[2] else 0.0)
        }
        
        # Get organizations for filter (Global Admin only)
        organizations = []
        if is_global_superadmin():
            cursor.execute('SELECT id, name FROM organizations ORDER BY name')
            organizations = cursor.fetchall()
        
        # Get locations for filter (Org Super Admin only)
        accessible_locations = []
        if is_org_superadmin() and org_id:
            cursor.execute('SELECT id, name FROM locations WHERE organization_id = ? ORDER BY name', (org_id,))
            accessible_locations = cursor.fetchall()
        
        # Get location breakdown for org super admins (prepaid stats per location)
        location_breakdown = []
        if is_org_superadmin() and org_id:
            cursor.execute('''
                SELECT 
                    l.id,
                    l.name,
                    COUNT(DISTINCT m.membership_id) as unique_members,
                    COUNT(pt.id) as total_transactions,
                    COALESCE(SUM(CASE WHEN pt.transaction_type = 'recharge' THEN pt.amount ELSE 0 END), 0) as total_recharges,
                    COALESCE(SUM(CASE WHEN pt.transaction_type = 'usage' THEN pt.amount ELSE 0 END), 0) as total_usage,
                    COALESCE(SUM(pt.bonus_amount), 0) as total_bonus
                FROM locations l
                LEFT JOIN members m ON l.id = m.location_id AND l.organization_id = m.organization_id
                LEFT JOIN prepaid_transactions pt ON m.membership_id = pt.membership_id AND m.organization_id = pt.organization_id
                WHERE l.organization_id = ?
                GROUP BY l.id, l.name
                ORDER BY l.name
            ''', (org_id,))
            location_breakdown = cursor.fetchall()
        
        # Get location name for location admins
        location_name = None
        if is_location_admin() and location_id:
            cursor.execute('SELECT name FROM locations WHERE id = ? AND organization_id = ?', (location_id, org_id))
            result = cursor.fetchone()
            location_name = result[0] if result else None
        
        return render_template('prepaid_reports.html',
                             transactions=transactions,
                             statistics=statistics,
                             start_date=start_date,
                             end_date=end_date,
                             transaction_type=transaction_type,
                             member_id=member_id,
                             location_id=location_id,
                             location_name=location_name,
                             organizations=organizations,
                             accessible_locations=accessible_locations,
                             location_breakdown=location_breakdown,
                             is_global_superadmin=is_global_superadmin(),
                             is_org_superadmin=is_org_superadmin(),
                             is_location_admin=is_location_admin())
        
    except Exception as e:
        flash(f'Error loading prepaid reports: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/audit_logs')
@require_login
@require_global_admin
def view_audit_logs():
    """View audit logs with filtering - Global Admin access"""
    try:
        # Get filter parameters
        action = request.args.get('action', '')
        table_name = request.args.get('table_name', '')
        user_id = request.args.get('user_id', type=int)
        start_date = request.args.get('start_date', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        limit = request.args.get('limit', 100, type=int)
        
        # Get audit logs with filters
        logs = get_audit_logs(
            limit=limit,
            action=action if action else None,
            user_id=user_id,
            table_name=table_name if table_name else None,
            start_date=start_date,
            end_date=end_date
        )
        
        # Get distinct actions for filter
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT DISTINCT action FROM audit_logs ORDER BY action')
        actions = [row[0] for row in cursor.fetchall()]
        
        # Get distinct tables for filter
        cursor.execute('SELECT DISTINCT table_name FROM audit_logs WHERE table_name IS NOT NULL ORDER BY table_name')
        tables = [row[0] for row in cursor.fetchall()]
        
        return render_template('audit_logs.html',
                             logs=logs,
                             actions=actions,
                             tables=tables,
                             selected_action=action,
                             selected_table=table_name,
                             selected_user_id=user_id,
                             start_date=start_date,
                             end_date=end_date,
                             limit=limit)
        
    except Exception as e:
        flash(f'Error loading audit logs: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/prepaid_reports/export_csv')
@require_login
def export_prepaid_reports_csv():
    """Export prepaid reports to CSV"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Get same filters as main report
        start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        transaction_type = request.args.get('transaction_type', 'all')
        member_id = request.args.get('member_id', '')
        
        # Build filter query (same as main report)
        filters = []
        params = []
        
        if is_global_superadmin():
            filter_org_id = request.args.get('org_id', type=int)
            if filter_org_id:
                filters.append('pt.organization_id = ?')
                params.append(filter_org_id)
                org_id = filter_org_id
        else:
            filters.append('pt.organization_id = ?')
            params.append(org_id)
        
        # Location filter handling (same logic as main report)
        # Location admins: Automatically restricted to their assigned location (cannot override)
        # Org super admins: Can optionally filter by location
        location_id = None
        if is_location_admin():
            # Location admin is automatically restricted to their assigned location
            location_id = session.get('location_id')
            if location_id:
                filters.append('m.location_id = ?')
                params.append(location_id)
        elif is_org_superadmin():
            # Org super admin can optionally filter by location
            location_id = request.args.get('location_id', type=int)
            if location_id:
                filters.append('m.location_id = ?')
                params.append(location_id)
        
        filters.append('date(pt.transaction_date) BETWEEN ? AND ?')
        params.extend([start_date, end_date])
        
        if transaction_type != 'all':
            filters.append('pt.transaction_type = ?')
            params.append(transaction_type)
        
        if member_id:
            filters.append('pt.membership_id LIKE ?')
            params.append(f'%{member_id}%')
        
        where_clause = ' AND '.join(filters) if filters else '1=1'
        
        # Get transactions
        cursor.execute(f'''
            SELECT 
                pt.transaction_date,
                pt.membership_id,
                m.name,
                pt.transaction_type,
                pt.amount,
                pt.bonus_amount,
                pt.balance_before,
                pt.balance_after,
                pt.description,
                o.name,
                l.name as location_name
            FROM prepaid_transactions pt
            JOIN members m ON pt.membership_id = m.membership_id AND pt.organization_id = m.organization_id
            JOIN organizations o ON pt.organization_id = o.id
            LEFT JOIN locations l ON m.location_id = l.id
            WHERE {where_clause}
            ORDER BY pt.transaction_date DESC
        ''', params)
        
        transactions = cursor.fetchall()
        
        # Generate CSV
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Date', 'Membership ID', 'Member Name', 'Type', 'Amount', 'Bonus', 'Balance Before', 'Balance After', 'Description', 'Organization', 'Location/Store'])
        
        # Write data
        for trans in transactions:
            writer.writerow(trans)
        
        # Create response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=prepaid_report_{start_date}_to_{end_date}.csv'}
        )
        
    except Exception as e:
        flash(f'Error exporting report: {e}', 'danger')
        return redirect(url_for('prepaid_reports'))

@app.route('/reports')
@require_login
def reports():
    """Generate various reports with location filtering for super admins"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Get location filter from request
        selected_location_id = request.args.get('location_id', type=int)
        
        # Build filters based on user role
        member_filter_parts = []
        member_params = []
        
        if is_global_superadmin():
            # Global admin can filter by organization
            filter_org_id = request.args.get('org_id', type=int)
            if filter_org_id:
                member_filter_parts.append('m.organization_id = ?')
                member_params.append(filter_org_id)
                org_id = filter_org_id
        else:
            # Org admin sees only their organization
            member_filter_parts.append('m.organization_id = ?')
            member_params.append(org_id)
        
        # Location filter for org super admins
        if is_org_superadmin() and selected_location_id:
            member_filter_parts.append('m.location_id = ?')
            member_params.append(selected_location_id)
        
        member_filter = 'WHERE ' + ' AND '.join(member_filter_parts) if member_filter_parts else ''

        # Member statistics
        cursor.execute(f'''
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'expired' THEN 1 END) as expired,
                COUNT(CASE WHEN status = 'inactive' THEN 1 END) as inactive
            FROM members m
            {member_filter}
        ''', member_params)
        member_stats = cursor.fetchone()

        # Payment statistics
        payment_filter_parts = []
        payment_params = []
        
        if is_global_superadmin():
            filter_org_id = request.args.get('org_id', type=int)
            if filter_org_id:
                payment_filter_parts.append('p.organization_id = ?')
                payment_params.append(filter_org_id)
        else:
            payment_filter_parts.append('p.organization_id = ?')
            payment_params.append(org_id)
        
        # Location filter via member join
        if is_org_superadmin() and selected_location_id:
            payment_filter_parts.append('m.location_id = ?')
            payment_params.append(selected_location_id)
        
        payment_filter = 'WHERE ' + ' AND '.join(payment_filter_parts) if payment_filter_parts else ''
        
        cursor.execute(f'''
            SELECT
                COUNT(*) as total_payments,
                COALESCE(SUM(p.amount), 0) as total_amount,
                COALESCE(AVG(p.amount), 0) as avg_amount
            FROM payments p
            LEFT JOIN members m ON p.membership_id = m.membership_id AND p.organization_id = m.organization_id
            {payment_filter}
        ''', payment_params)
        payment_stats = cursor.fetchone()
        
        # Get location breakdown for org super admins
        location_breakdown = []
        if is_org_superadmin() and org_id:
            cursor.execute('''
                SELECT 
                    l.id,
                    l.name,
                    COUNT(m.id) as total_members,
                    COUNT(CASE WHEN m.status = 'active' THEN 1 END) as active_members,
                    COALESCE(SUM(p.amount), 0) as total_payments
                FROM locations l
                LEFT JOIN members m ON l.id = m.location_id AND l.organization_id = m.organization_id
                LEFT JOIN payments p ON m.membership_id = p.membership_id AND m.organization_id = p.organization_id
                WHERE l.organization_id = ?
                GROUP BY l.id, l.name
                ORDER BY l.name
            ''', (org_id,))
            location_breakdown = cursor.fetchall()
        
        # Get accessible locations for filter dropdown
        accessible_locations = []
        if is_org_superadmin() and org_id:
            cursor.execute('''
                SELECT id, name FROM locations 
                WHERE organization_id = ?
                ORDER BY name
            ''', (org_id,))
            accessible_locations = cursor.fetchall()
        
        # Get organizations for global admin
        organizations = []
        if is_global_superadmin():
            cursor.execute('SELECT id, name FROM organizations ORDER BY name')
            organizations = cursor.fetchall()

        return render_template('reports.html',
                             member_stats=member_stats,
                             payment_stats=payment_stats,
                             location_breakdown=location_breakdown,
                             accessible_locations=accessible_locations,
                             organizations=organizations,
                             selected_location_id=selected_location_id,
                             is_org_superadmin=is_org_superadmin(),
                             is_global_superadmin=is_global_superadmin())

    except Exception as e:
        print(f"Error in reports: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error generating reports: {e}', 'danger')
        return render_template('reports.html', 
                             member_stats=None, 
                             payment_stats=None,
                             location_breakdown=[],
                             accessible_locations=[],
                             organizations=[])

@app.route('/analytics')
@require_login
def analytics():
    """View analytics dashboard"""
    try:
        db = get_db()
        cursor = db.cursor()

        org_filter, org_params = get_members_query_filter()

        # Monthly member registrations
        cursor.execute(f'''
            SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
            FROM members m
            {org_filter}
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        ''', org_params)
        monthly_registrations = cursor.fetchall()

        # Membership type distribution
        cursor.execute(f'''
            SELECT membership_type, COUNT(*) as count
            FROM members m
            {org_filter}
            GROUP BY membership_type
        ''', org_params)
        membership_distribution = cursor.fetchall()

        return render_template('analytics.html',
                             monthly_registrations=monthly_registrations,
                             membership_distribution=membership_distribution)

    except Exception as e:
        flash(f'Error loading analytics: {e}', 'danger')
        return render_template('analytics.html',
                             monthly_registrations=[],
                             membership_distribution=[])

@app.route('/profile')
@require_login
def user_profile():
    """User profile page"""
    try:
        db = get_db()
        cursor = db.cursor()

        user_id = session.get('user_id')
        cursor.execute('''
            SELECT u.id, u.username, u.email, u.password_hash, u.organization_id, 
                   u.created_at, u.is_admin, u.is_superadmin, u.is_global_superadmin,
                   u.is_global_admin, u.subscription_package_id,
                   o.name as organization_name,
                   sp.name as package_name
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            LEFT JOIN subscription_packages sp ON u.subscription_package_id = sp.id
            WHERE u.id = ?
        ''', (user_id,))

        user = cursor.fetchone()
        return render_template('user_profile.html', user=user)

    except Exception as e:
        flash(f'Error loading profile: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/update_profile', methods=['GET', 'POST'])
@require_login
def update_profile():
    """Update user profile"""
    if request.method == 'GET':
        # Show update profile form
        try:
            db = get_db()
            cursor = db.cursor()
            user_id = session.get('user_id')
            
            cursor.execute('''
                SELECT u.id, u.username, u.email, u.password_hash, u.organization_id, 
                       u.created_at, u.is_admin, u.is_superadmin, u.is_global_superadmin,
                       u.is_global_admin, u.subscription_package_id,
                       o.name as organization_name,
                       sp.name as package_name
                FROM users u
                LEFT JOIN organizations o ON u.organization_id = o.id
                LEFT JOIN subscription_packages sp ON u.subscription_package_id = sp.id
                WHERE u.id = ?
            ''', (user_id,))
            
            user = cursor.fetchone()
            return render_template('update_profile.html', user=user)
            
        except Exception as e:
            flash(f'Error loading profile: {e}', 'danger')
            return redirect(url_for('user_profile'))
    
    else:  # POST request
        try:
            user_id = session.get('user_id')
            email = request.form.get('email', '').strip()
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            # Validate password confirmation
            if new_password and new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for('update_profile'))

            db = get_db()
            cursor = db.cursor()

            # Verify current password if changing password
            if new_password:
                cursor.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()

                if not user or not check_password_hash(user[0], current_password):
                    flash('Current password is incorrect.', 'danger')
                    return redirect(url_for('update_profile'))

                # Update with new password
                new_password_hash = generate_password_hash(new_password)
                cursor.execute('''
                    UPDATE users SET email = ?, password_hash = ?
                    WHERE id = ?
                ''', (email, new_password_hash, user_id))

                flash('Profile and password updated successfully!', 'success')
            else:
                # Update only email
                cursor.execute('UPDATE users SET email = ? WHERE id = ?', (email, user_id))
                flash('Profile updated successfully!', 'success')

            db.commit()

        except Exception as e:
            flash(f'Error updating profile: {e}', 'danger')

        return redirect(url_for('user_profile'))

@app.route('/bulk_actions')
@require_login
def bulk_actions():
    """Bulk actions page for members"""
    try:
        db = get_db()
        cursor = db.cursor()

        org_filter, org_params = get_members_query_filter()
        cursor.execute(f'''
            SELECT membership_id, name, email, phone, status
            FROM members m
            {org_filter}
            ORDER BY name
        ''', org_params)

        members = cursor.fetchall()
        return render_template('bulk_actions.html', members=members)

    except Exception as e:
        flash(f'Error loading bulk actions: {e}', 'danger')
        return render_template('bulk_actions.html', members=[])

@app.route('/process_bulk_action', methods=['POST'])
@require_login
def process_bulk_action():
    """Process bulk actions on members"""
    try:
        action = request.form.get('action')
        selected_members = request.form.getlist('selected_members')

        if not selected_members:
            flash('Please select at least one member.', 'warning')
            return redirect(url_for('bulk_actions'))

        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')

        if action == 'activate':
            placeholders = ','.join(['?' for _ in selected_members])
            cursor.execute(f'''
                UPDATE members SET status = 'active'
                WHERE membership_id IN ({placeholders}) AND organization_id = ?
            ''', selected_members + [org_id])
            flash(f'Activated {len(selected_members)} members.', 'success')

        elif action == 'deactivate':
            placeholders = ','.join(['?' for _ in selected_members])
            cursor.execute(f'''
                UPDATE members SET status = 'inactive'
                WHERE membership_id IN ({placeholders}) AND organization_id = ?
            ''', selected_members + [org_id])
            flash(f'Deactivated {len(selected_members)} members.', 'success')

        elif action == 'delete':
            placeholders = ','.join(['?' for _ in selected_members])
            # Delete related records first
            cursor.execute(f'''
                DELETE FROM payments
                WHERE membership_id IN ({placeholders}) AND organization_id = ?
            ''', selected_members + [org_id])
            cursor.execute(f'''
                DELETE FROM notifications
                WHERE membership_id IN ({placeholders}) AND organization_id = ?
            ''', selected_members + [org_id])
            cursor.execute(f'''
                DELETE FROM members
                WHERE membership_id IN ({placeholders}) AND organization_id = ?
            ''', selected_members + [org_id])
            flash(f'Deleted {len(selected_members)} members.', 'success')

        db.commit()

    except Exception as e:
        flash(f'Error processing bulk action: {e}', 'danger')

    return redirect(url_for('bulk_actions'))

@app.route('/api/validate_discount', methods=['POST'])
@require_login
def api_validate_discount():
    """API endpoint for discount validation"""
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        amount = float(data.get('amount', 0))
        membership_id = data.get('membership_id')

        discount_info, error = validate_discount_code(code, amount, membership_id)

        if discount_info:
            return {
                'success': True,
                'discount': {
                    'code': discount_info['code'],
                    'type': discount_info['type'],
                    'value': discount_info['value'],
                    'amount': discount_info['amount'],
                    'final_amount': discount_info['final_amount']
                }
            }
        else:
            return {'success': False, 'error': error}

    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/debug/test-db')
def test_db_connection():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        return f"Database connection successful: {result}"
    except Exception as e:
        return f"Database connection failed: {str(e)}"




##############################################################################

# Add this function to your app.py file and call it before app.run()

def fix_database_schema():
    """Fix missing columns in the database"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if organizations table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='organizations'")
        if cursor.fetchone():
            # Add location column to organizations table if it doesn't exist
            try:
                cursor.execute('ALTER TABLE organizations ADD COLUMN location TEXT DEFAULT "Not Specified"')
                # Update existing records with default value
                cursor.execute('UPDATE organizations SET location = "Not Specified" WHERE location IS NULL')
                print("✅ Added 'location' column to organizations table with default values")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e):
                    raise
                print("ℹ️ 'location' column already exists in organizations table")
                
        db.commit()
        return True
    except Exception as e:
        print(f"❌ Error fixing database schema: {e}")
        db.rollback()
        return False

@app.route('/fix_org_location')
def fix_org_location():
    """Manually add location column to organizations table if it doesn't exist"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            # Check if location column exists
            cursor.execute("PRAGMA table_info(organizations)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'location' not in columns:
                print("Adding 'location' column to organizations table...")
                cursor.execute('ALTER TABLE organizations ADD COLUMN location TEXT DEFAULT "Not Specified"')
                # Update existing records with default value
                cursor.execute('UPDATE organizations SET location = "Not Specified" WHERE location IS NULL')
                conn.commit()
                return "Successfully added 'location' column to organizations table with default values"
            else:
                # Check if any organizations have NULL location values and fix them
                cursor.execute('SELECT COUNT(*) FROM organizations WHERE location IS NULL')
                null_count = cursor.fetchone()[0]
                if null_count > 0:
                    cursor.execute('UPDATE organizations SET location = "Not Specified" WHERE location IS NULL')
                    conn.commit()
                    return f"Updated {null_count} organizations with default location value"
                else:
                    return "'location' column already exists in organizations table and all records have values"
    except Exception as e:
        return f"Error: {str(e)}"

def fix_database_schema():
    """Fix missing columns in existing database"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            print("🔧 Checking and fixing database schema...")
            
            # First check if any tables exist at all
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            if not existing_tables:
                print("ℹ️  No tables found. Will run full initialization...")
                return True  # Let init_db() handle everything
            
            print(f"Found existing tables: {existing_tables}")
            
            # Check and add missing columns to organizations table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='organizations'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(organizations)")
                org_columns = [column[1] for column in cursor.fetchall()]
                
                if 'status' not in org_columns:
                    print("Adding 'status' column to organizations table...")
                    cursor.execute('ALTER TABLE organizations ADD COLUMN status TEXT DEFAULT "active"')
                
                if 'location' not in org_columns:
                    print("Adding 'location' column to organizations table...")
                    cursor.execute('ALTER TABLE organizations ADD COLUMN location TEXT DEFAULT "Not Specified"')
                    # Update existing records with default value
                    cursor.execute('UPDATE organizations SET location = "Not Specified" WHERE location IS NULL')
            
                if 'created_at' not in org_columns:
                    print("Adding 'created_at' column to organizations table...")
                    cursor.execute('ALTER TABLE organizations ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP')
            
            # Check and add missing columns to users table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(users)")
                user_columns = [column[1] for column in cursor.fetchall()]
                
                if 'is_global_superadmin' not in user_columns:
                    print("Adding 'is_global_superadmin' column to users table...")
                    cursor.execute('ALTER TABLE users ADD COLUMN is_global_superadmin INTEGER DEFAULT 0')
                
                if 'is_superadmin' not in user_columns:
                    print("Adding 'is_superadmin' column to users table...")
                    cursor.execute('ALTER TABLE users ADD COLUMN is_superadmin INTEGER DEFAULT 0')
                
                if 'is_admin' not in user_columns:
                    print("Adding 'is_admin' column to users table...")
                    cursor.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
            
            # Ensure Global System Administration organization exists
            cursor.execute('SELECT id FROM organizations WHERE id = 1')
            if not cursor.fetchone():
                print("Creating Global System Administration organization...")
                cursor.execute('''
                    INSERT INTO organizations (id, name, industry, location, status)
                    VALUES (1, 'Global System Administration', 'System Management', 'Global', 'active')
                ''')
            else:
                # Update existing organization to have status
                cursor.execute('''
                    UPDATE organizations 
                    SET status = 'active' 
                    WHERE id = 1 AND (status IS NULL OR status = '')
                ''')
            
            # Ensure global admin user exists with proper permissions
            cursor.execute('SELECT id FROM users WHERE username = ? AND organization_id = 1', ('globaladmin',))
            if not cursor.fetchone():
                print("Creating global admin user...")
                password_hash = generate_password_hash('ChangeMe123!')
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, organization_id, is_admin, is_superadmin, is_global_superadmin)
                    VALUES (?, ?, ?, 1, 1, 1, 1)
                ''', ('globaladmin', 'admin@system.local', password_hash))
            else:
                # Update existing user permissions
                cursor.execute('''
                    UPDATE users 
                    SET is_admin = 1, is_superadmin = 1, is_global_superadmin = 1
                    WHERE username = ? AND organization_id = 1
                ''', ('globaladmin',))
            
            conn.commit()
            print("✅ Database schema fixed successfully!")
            
            return True
            
    except Exception as e:
        print(f"❌ Error fixing database schema: {e}")
        return False

# Also, update your login function to handle missing status column gracefully
def safe_login_query(username):
    """Safe login query that handles missing columns and fetches location info"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Try the full query with all columns including location_id
        try:
            cursor.execute('''
                SELECT u.id, u.username, u.email, u.password_hash, u.organization_id,
                       u.is_admin, u.is_superadmin, u.is_global_superadmin, u.is_global_admin,
                       o.name as org_name, o.status as org_status, u.location_id,
                       l.name as location_name
                FROM users u
                LEFT JOIN organizations o ON u.organization_id = o.id
                LEFT JOIN locations l ON u.location_id = l.id
                WHERE LOWER(u.username) = LOWER(?)
            ''', (username,))
            return cursor.fetchone()
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            
            # Try without location columns
            if "no such column" in error_msg:
                print("⚠️  Database missing columns, using fallback query...")
                cursor.execute('''
                    SELECT u.id, u.username, u.email, u.password_hash, u.organization_id,
                           u.is_admin, u.is_superadmin, u.is_global_superadmin, u.is_global_admin,
                           o.name as org_name, 'active' as org_status, NULL as location_id,
                           NULL as location_name
                    FROM users u
                    LEFT JOIN organizations o ON u.organization_id = o.id
                    WHERE LOWER(u.username) = LOWER(?)
                ''', (username,))
                return cursor.fetchone()
            else:
                raise
    except Exception as e:
        print(f"Login query error: {e}")
        return None

##############################################################################



# ============================================================================
# INITIALIZATION AND MAIN
# ============================================================================

# Initialize Babel
babel = Babel()
babel.init_app(app)

# Start scheduler in background
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# Replace the fix_database_schema function and the main initialization block at the bottom of your app.py

def fix_database_schema():
    """Fix missing columns in existing database - only if tables exist"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            print("🔧 Checking and fixing database schema...")
            
            # First check if any tables exist at all
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            if not existing_tables:
                # Update existing global admin if it exists
                cursor.execute('SELECT id FROM users WHERE username = ?', ('globaladmin',))
                if cursor.fetchone():
                    print("Updating existing global admin user permissions...")
                    cursor.execute('''
                        UPDATE users 
                        SET is_admin = 1, is_superadmin = 1, is_global_superadmin = 1, organization_id = 1
                        WHERE username = ? 
                    ''', ('globaladmin',))
            
            # Fix organizations data if table exists
            if 'organizations' in existing_tables:
                cursor.execute('SELECT id FROM organizations WHERE id = 1')
                if not cursor.fetchone():
                    print("Creating Global System Administration organization...")
                    cursor.execute('''
                        INSERT INTO organizations (id, name, industry, location, status)
                        VALUES (1, 'Global System Administration', 'System Management', 'Global', 'active')
                    ''')
                else:
                    # Update existing organization to have status
                    cursor.execute('''
                        UPDATE organizations 
                        SET status = 'active' 
                        WHERE id = 1 AND (status IS NULL OR status = '')
                    ''')
            
            conn.commit()
            print("✅ Database schema updated successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Error fixing database schema: {e}")
        return False

def seed_default_locations():
    """Seed default locations (Bastos, Famla, Bepanda) if they don't exist"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            # Get all organizations
            cursor.execute('SELECT id, name FROM organizations')
            organizations = cursor.fetchall()
            
            if not organizations:
                return
            
            # Default locations to add
            default_locations = [
                ('Bastos', 'Yaounde', 'Centre'),
                ('Famla', 'Bafoussam', 'West'),
                ('Bepanda', 'Douala', 'Littoral')
            ]
            
            for org_id, org_name in organizations:
                for name, city, state in default_locations:
                    # Check if location exists for this org
                    cursor.execute('SELECT id FROM locations WHERE name = ? AND organization_id = ?', (name, org_id))
                    if not cursor.fetchone():
                        print(f"📍 Seeding location '{name}' for organization '{org_name}'")
                        cursor.execute('''
                            INSERT INTO locations (organization_id, name, address, city, state)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (org_id, name, f'{name} Main Road', city, state))
            
            conn.commit()
            print("✅ Default locations seeded successfully")
    except Exception as e:
        print(f"❌ Error seeding locations: {e}")

def apply_migrations_internal():
    """Apply database migrations with smart duplicate column detection"""
    migrations_dir = 'migrations'
    
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
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
            if not os.path.exists(migrations_dir):
                print(f"ℹ️  No migrations directory found at {migrations_dir}")
                return True
            
            migration_files = sorted([f for f in os.listdir(migrations_dir) 
                                   if f.endswith('.sql')])
            
            # Apply each migration that hasn't been applied yet
            migrations_applied = 0
            migrations_skipped = 0
            
            for migration_file in migration_files:
                if migration_file not in applied_migrations:
                    print(f"📝 Applying migration: {migration_file}")
                    try:
                        with open(os.path.join(migrations_dir, migration_file), 'r') as f:
                            sql = f.read()
                            cursor.executescript(sql)
                        
                        # Record the migration as applied
                        cursor.execute('INSERT INTO migrations (name) VALUES (?)', (migration_file,))
                        conn.commit()
                        print(f"✅ Successfully applied {migration_file}")
                        migrations_applied += 1
                        
                    except sqlite3.OperationalError as e:
                        error_msg = str(e).lower()
                        # Check if it's a duplicate column error (already applied manually or by init_db)
                        if 'duplicate column' in error_msg or 'already exists' in error_msg:
                            print(f"ℹ️  Migration {migration_file} already applied (column exists)")
                            # Mark as applied since the schema change is already present
                            cursor.execute('INSERT OR IGNORE INTO migrations (name) VALUES (?)', (migration_file,))
                            conn.commit()
                            migrations_skipped += 1
                        else:
                            print(f"⚠️  Error applying {migration_file}: {e}")
                            # Mark as applied to prevent re-attempts
                            cursor.execute('INSERT OR IGNORE INTO migrations (name) VALUES (?)', (migration_file,))
                            conn.commit()
                            
                    except Exception as e:
                        print(f"⚠️  Error applying {migration_file}: {e}")
                        # Mark as applied to prevent re-attempts
                        cursor.execute('INSERT OR IGNORE INTO migrations (name) VALUES (?)', (migration_file,))
                        conn.commit()
            
            if migrations_applied > 0:
                print(f"✅ Applied {migrations_applied} new migration(s)")
            if migrations_skipped > 0:
                print(f"ℹ️  Skipped {migrations_skipped} already-applied migration(s)")
            if migrations_applied == 0 and migrations_skipped == 0:
                print("ℹ️  All migrations are up to date")
            
            return True
            
    except Exception as e:
        print(f"❌ Error in migration system: {e}")
        return False

def init_db_safely():
    """Initialize database with better error handling"""
    try:
        # First check if database file exists and has content
        db_exists = os.path.exists(DATABASE)
        
        if db_exists:
            # Check if it has tables
            with sqlite3.connect(DATABASE, timeout=20.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                
                if tables:
                    print(f"📊 Found existing database with {len(tables)} tables")
                    # Try to fix schema for existing database
                    if not fix_database_schema():
                        print("⚠️  Schema fix failed, but continuing with initialization...")
                else:
                    print("📊 Empty database file found, initializing...")
        else:
            print("📊 No database file found, creating new database...")
        
        # Run full initialization
        init_db()
        
        # Apply migrations
        print("\n🔄 Applying database migrations...")
        if not apply_migrations_internal():
            print("⚠️  Some migrations failed, but continuing...")
        
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
# =============================================================================
# Avatar and Migration Script for photo support
# ============================================================================

def migrate_database():
    """Add photo support to existing MemberSync database"""
    
    print("🔄 Starting database migration for photo support...")
    
    try:
        # Create backup of existing database
        if os.path.exists(DATABASE):
            backup_name = f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            import shutil
            shutil.copy2(DATABASE, backup_name)
            print(f"✅ Database backup created: {backup_name}")
        
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            
            # Check if members table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
            if not cursor.fetchone():
                print("❌ Members table not found. Please run the main application first.")
                return False
            
            # Check current schema
            cursor.execute("PRAGMA table_info(members)")
            columns = [column[1] for column in cursor.fetchall()]
            print(f"📋 Current members table columns: {columns}")
            
            # Add photo_filename column if it doesn't exist
            if 'photo_filename' not in columns:
                print("➕ Adding photo_filename column to members table...")
                cursor.execute('ALTER TABLE members ADD COLUMN photo_filename TEXT')
                print("✅ photo_filename column added successfully")
            else:
                print("ℹ️  photo_filename column already exists")
            
            # Create upload directories
            upload_dirs = [
                'static/uploads',
                'static/uploads/photos',
                'static/images'
            ]
            
            for directory in upload_dirs:
                if not os.path.exists(directory):
                    os.makedirs(directory)
                    print(f"📁 Created directory: {directory}")
                else:
                    print(f"ℹ️  Directory already exists: {directory}")
            
            # Verify the migration
            cursor.execute("PRAGMA table_info(members)")
            new_columns = [column[1] for column in cursor.fetchall()]
            
            if 'photo_filename' in new_columns:
                print("✅ Migration completed successfully!")
                print(f"📋 Updated members table columns: {new_columns}")
                
                # Count existing members
                cursor.execute("SELECT COUNT(*) FROM members")
                member_count = cursor.fetchone()[0]
                print(f"👥 Found {member_count} existing members")
                
                if member_count > 0:
                    print("💡 Existing members can now upload photos by editing their profiles")
                
                return True
            else:
                print("❌ Migration failed - photo_filename column not found after addition")
                return False
                
    except sqlite3.Error as e:
        print(f"❌ Database error during migration: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during migration: {e}")
        return False

def verify_migration():
    """Verify that the migration was successful"""
    
    print("\n🔍 Verifying migration...")
    
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            
            # Check if photo_filename column exists and is accessible
            cursor.execute("SELECT photo_filename FROM members LIMIT 1")
            print("✅ photo_filename column is accessible")
            
            # Check directory structure
            required_dirs = [
                'static/uploads/photos',
                'static/images'
            ]
            
            for directory in required_dirs:
                if os.path.exists(directory):
                    print(f"✅ Directory exists: {directory}")
                else:
                    print(f"❌ Directory missing: {directory}")
                    return False
            
            print("✅ Migration verification completed successfully!")
            return True
            
    except sqlite3.Error as e:
        print(f"❌ Verification failed - Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Verification failed - Error: {e}")
        return False

def create_sample_member_with_photo():
    """Create a sample member entry to test photo functionality"""
    
    print("\n👤 Creating sample member for testing...")
    
    try:
        with sqlite3.connect(DATABASE, timeout=10.0) as conn:
            cursor = conn.cursor()
            
            # Check if sample member already exists
            cursor.execute("SELECT COUNT(*) FROM members WHERE membership_id = 'SAMPLE-001'")
            if cursor.fetchone()[0] > 0:
                print("ℹ️  Sample member already exists")
                return True
            
            # Get organization ID (use 1 as default)
            cursor.execute("SELECT id FROM organizations ORDER BY id LIMIT 1")
            org_result = cursor.fetchone()
            org_id = org_result[0] if org_result else 1
            
            # Create sample member
            from datetime import datetime, timedelta
            expiration_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
            
            cursor.execute('''
                INSERT INTO members (
                    membership_id, name, email, phone, membership_type, 
                    created_at, expiration_date, status, organization_id, 
                    payment_status, photo_filename, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'SAMPLE-001',
                'Sample Member',
                'sample@example.com',
                '+1-555-0123',
                'Gold',
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                expiration_date,
                'active',
                org_id,
                'Paid',
                None,  # No photo initially
                None   # created_by - NULL for sample data
            ))
            
            conn.commit()
            print("✅ Sample member created successfully!")
            print("📝 Member ID: SAMPLE-001")
            print("💡 You can now test photo upload by editing this member's profile")
            return True
            
    except sqlite3.Error as e:
        print(f"❌ Error creating sample member: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def show_migration_summary():
    """Show a summary of what was accomplished"""
    
    print("\n" + "="*60)
    print("📊 MIGRATION SUMMARY")
    print("="*60)
    print("✅ Added photo_filename column to members table")
    print("✅ Created necessary upload directories")
    print("✅ Database backup created (if database existed)")
    print("\n📁 Directory Structure:")
    print("   static/uploads/photos/     - Member photo storage")
    print("   static/images/            - Default avatar images")
    print("\n🔧 Next Steps:")
    print("1. Run the create_default_avatar.py script")
    print("2. Restart your MemberSync application")
    print("3. Test photo upload by editing a member profile")
    print("4. Scan QR codes to see photos in verification")
    print("\n💡 New Features Available:")
    print("• Photo upload during member registration")
    print("• Photo management in member edit form")
    print("• Photo display in digital membership cards")
    print("• Photo verification when scanning QR codes")
    print("• Email digital cards with member photos")
    print("="*60)

if __name__ == "__main__":
    print("🚀 MemberSync Photo Support Migration")
    print("="*50)
    
    # Run migration
    if migrate_database():
        # Verify migration
        if verify_migration():
            # Create sample member
            create_sample_member_with_photo()
            # Show summary
            show_migration_summary()
            print("\n🎉 Migration completed successfully!")
            print("💡 You can now restart your MemberSync application to use photo features.")
        else:
            print("\n❌ Migration verification failed. Please check the errors above.")
    else:
        print("\n❌ Migration failed. Please check the errors above.")
        print("💡 Your original database is safe - a backup was created.")


from PIL import Image, ImageDraw, ImageFont


def create_default_avatar():
    """Create a default avatar image for members without photos"""
    
    # Create static/images directory if it doesn't exist
    os.makedirs('static/images', exist_ok=True)
    
    # Create a 300x400 image with a gradient background
    img = Image.new('RGB', (300, 400), color='white')
    draw = ImageDraw.Draw(img)
    
    # Create gradient background
    for y in range(400):
        # Create a blue gradient
        color_value = int(255 - (y / 400) * 50)  # From light blue to darker blue
        color = (102, 126, 234, color_value)  # Blue gradient
        draw.line([(0, y), (300, y)], fill=(102, 126, 234))
    
    # Create a circle for the avatar
    circle_center = (150, 150)
    circle_radius = 80
    
    # Draw circle background
    draw.ellipse([
        circle_center[0] - circle_radius,
        circle_center[1] - circle_radius,
        circle_center[0] + circle_radius,
        circle_center[1] + circle_radius
    ], fill='white', outline=(102, 126, 234), width=3)
    
    # Draw a simple user icon
    # Head (smaller circle)
    head_radius = 25
    head_center = (150, 130)
    draw.ellipse([
        head_center[0] - head_radius,
        head_center[1] - head_radius,
        head_center[0] + head_radius,
        head_center[1] + head_radius
    ], fill=(102, 126, 234))
    
    # Body (arc)
    body_radius = 40
    body_center = (150, 200)
    draw.ellipse([
        body_center[0] - body_radius,
        body_center[1] - body_radius,
        body_center[0] + body_radius,
        body_center[1] + body_radius
    ], fill=(102, 126, 234))
    
    # Add text
    try:
        # Try to use a nice font
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        # Fallback to default font
        font = ImageFont.load_default()
    
    text = "NO PHOTO"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = (300 - text_width) // 2
    text_y = 300
    
    draw.text((text_x, text_y), text, fill=(102, 126, 234), font=font)
    
    # Add smaller text
    try:
        small_font = ImageFont.truetype("arial.ttf", 16)
    except:
        small_font = ImageFont.load_default()
    
    small_text = "Upload photo in member profile"
    small_bbox = draw.textbbox((0, 0), small_text, font=small_font)
    small_width = small_bbox[2] - small_bbox[0]
    small_x = (300 - small_width) // 2
    small_y = 340
    
    draw.text((small_x, small_y), small_text, fill=(150, 150, 150), font=small_font)
    
    # Save the image
    img.save('static/images/default-avatar.png', 'PNG')
    print("✅ Default avatar created at static/images/default-avatar.png")

if __name__ == "__main__":
    create_default_avatar()

# ========================================================================
def add_password_reset_table():
    """Add password reset tokens table to existing database"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()

            # Create password reset tokens table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
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

            conn.commit()
            print("✅ Password reset tokens table created successfully!")
            return True

    except Exception as e:
        print(f"❌ Error creating password reset tokens table: {e}")
        return False

# Add these helper functions after your existing utility functions

def generate_reset_token():
    """Generate a secure random token for password reset"""
    return secrets.token_urlsafe(32)

def create_reset_token(user_id, email):
    """Create a password reset token for a user"""
    try:
        db = get_db()
        cursor = db.cursor()

        # Generate token and expiration (24 hours from now)
        token = generate_reset_token()
        expires_at = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

        # Invalidate any existing tokens for this user
        cursor.execute('''
            UPDATE password_reset_tokens
            SET used = 1
            WHERE user_id = ? AND used = 0
        ''', (user_id,))

        # Create new token
        cursor.execute('''
            INSERT INTO password_reset_tokens (user_id, email, token, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, email, token, expires_at))

        db.commit()
        return token

    except Exception as e:
        print(f"Error creating reset token: {e}")
        return None

def validate_reset_token(token):
    """Validate a password reset token"""
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT user_id, email, expires_at, used
            FROM password_reset_tokens
            WHERE token = ?
        ''', (token,))

        result = cursor.fetchone()
        if not result:
            return None, "Invalid reset token"

        user_id, email, expires_at, used = result

        if used:
            return None, "Reset token has already been used"

        # Check if token has expired
        expires_datetime = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S')
        if datetime.now() > expires_datetime:
            return None, "Reset token has expired"

        return {
            'user_id': user_id,
            'email': email
        }, None

    except Exception as e:
        print(f"Error validating reset token: {e}")
        return None, "Error validating token"

def mark_token_as_used(token):
    """Mark a reset token as used"""
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            UPDATE password_reset_tokens
            SET used = 1
            WHERE token = ?
        ''', (token,))

        db.commit()
        return True

    except Exception as e:
        print(f"Error marking token as used: {e}")
        return False

def send_password_reset_email(email, token, username):
    """Send password reset email"""
    try:
        reset_link = f"http://localhost:5000/reset-password/{token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
                    color: white;
                    padding: 30px 20px;
                    text-align: center;
                    border-radius: 10px 10px 0 0;
                }}
                .content {{
                    background: #f8f9fa;
                    padding: 30px 20px;
                    border-radius: 0 0 10px 10px;
                }}
                .reset-button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 25px;
                    margin: 20px 0;
                    font-weight: bold;
                }}
                .warning-box {{
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    color: #666;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🔐 Password Reset Request</h1>
                <p>MemberSync Account Recovery</p>
            </div>

            <div class="content">
                <h2>Hello {username}!</h2>

                <p>We received a request to reset the password for your MemberSync account associated with this email address.</p>

                <div style="text-align: center;">
                    <a href="{reset_link}" class="reset-button">
                        🔑 Reset My Password
                    </a>
                </div>

                <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                <p style="background: white; padding: 10px; border-radius: 5px; word-break: break-all;">
                    <strong>{reset_link}</strong>
                </p>

                <div class="warning-box">
                    <h4>⚠️ Important Security Information:</h4>
                    <ul>
                        <li>This link will expire in <strong>24 hours</strong></li>
                        <li>The link can only be used <strong>once</strong></li>
                        <li>If you didn't request this reset, please ignore this email</li>
                        <li>Your password will remain unchanged until you complete the reset process</li>
                    </ul>
                </div>

                <h3>Need Help?</h3>
                <p>If you're having trouble with the password reset process, please contact your system administrator.</p>
            </div>

            <div class="footer">
                <p>This email was sent from MemberSync Password Recovery System</p>
                <p>If you didn't request this password reset, please ignore this email</p>
                <p><em>© 2024 MemberSync - Secure Membership Management</em></p>
            </div>
        </body>
        </html>
        """

        return send_email_notification(
            email,
            "🔐 MemberSync Password Reset Request",
            html_content
        )

    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False

# Add these routes after your existing authentication routes

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password requests"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')

        if '@' not in email:
            flash('Please enter a valid email address.', 'danger')
            return render_template('forgot_password.html')

        try:
            db = get_db()
            cursor = db.cursor()

            # Find user by email
            cursor.execute('''
                SELECT id, username, email, organization_id
                FROM users
                WHERE LOWER(email) = LOWER(?)
            ''', (email,))

            user = cursor.fetchone()

            if user:
                user_id, username, user_email, org_id = user

                # Check if organization is active (except for global superadmin)
                if org_id != 1:  # Not global admin
                    cursor.execute('SELECT status FROM organizations WHERE id = ?', (org_id,))
                    org_result = cursor.fetchone()
                    if not org_result or org_result[0] != 'active':
                        flash('Your organization account is currently inactive. Please contact support.', 'danger')
                        return render_template('forgot_password.html')

                # Generate reset token
                token = create_reset_token(user_id, user_email)

                if token:
                    # Send reset email
                    if send_password_reset_email(user_email, token, username):
                        flash('Password reset instructions have been sent to your email address. Please check your inbox and spam folder.', 'success')
                        return redirect(url_for('login'))
                    else:
                        flash('Error sending reset email. Please try again or contact support.', 'danger')
                else:
                    flash('Error generating reset token. Please try again.', 'danger')
            else:
                # Don't reveal whether email exists - security best practice
                flash('If an account with that email exists, password reset instructions have been sent.', 'info')
                return redirect(url_for('login'))

        except Exception as e:
            print(f"Error in forgot password: {e}")
            flash('An error occurred while processing your request. Please try again.', 'danger')

    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset with token"""
    # Validate token
    token_data, error = validate_reset_token(token)

    if error:
        flash(f'Password reset failed: {error}', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        if not new_password:
            flash('Please enter a new password.', 'danger')
            return render_template('reset_password.html', token=token, email=token_data['email'])

        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('reset_password.html', token=token, email=token_data['email'])

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token, email=token_data['email'])

        try:
            db = get_db()
            cursor = db.cursor()

            # Update user password
            new_password_hash = generate_password_hash(new_password)
            cursor.execute('''
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
            ''', (new_password_hash, token_data['user_id']))

            # Mark token as used
            mark_token_as_used(token)

            db.commit()

            # Send confirmation email
            cursor.execute('SELECT username FROM users WHERE id = ?', (token_data['user_id'],))
            username = cursor.fetchone()[0]

            send_password_change_confirmation(token_data['email'], username)

            flash('Your password has been reset successfully! You can now log in with your new password.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            print(f"Error resetting password: {e}")
            flash('An error occurred while resetting your password. Please try again.', 'danger')

    return render_template('reset_password.html', token=token, email=token_data['email'])

def send_password_change_confirmation(email, username):
    """Send confirmation email after password change"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                    color: white;
                    padding: 30px 20px;
                    text-align: center;
                    border-radius: 10px 10px 0 0;
                }}
                .content {{
                    background: #f8f9fa;
                    padding: 30px 20px;
                    border-radius: 0 0 10px 10px;
                }}
                .success-box {{
                    background: #d4edda;
                    border: 1px solid #c3e6cb;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    color: #666;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>✅ Password Successfully Changed</h1>
                <p>MemberSync Security Notification</p>
            </div>

            <div class="content">
                <h2>Hello {username}!</h2>

                <div class="success-box">
                    <h4>🔐 Your password has been successfully changed</h4>
                    <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Account:</strong> {email}</p>
                </div>

                <p>Your MemberSync account password has been successfully updated. You can now log in using your new password.</p>

                <h3>Security Tips:</h3>
                <ul>
                    <li>Keep your password secure and don't share it with anyone</li>
                    <li>Use a unique password that you don't use for other accounts</li>
                    <li>Consider using a password manager</li>
                    <li>If you notice any suspicious activity, contact support immediately</li>
                </ul>

                <h3>Didn't change your password?</h3>
                <p>If you did not request this password change, please contact your system administrator immediately as your account may have been compromised.</p>
            </div>

            <div class="footer">
                <p>This email was sent from MemberSync Security System</p>
                <p><em>© 2024 MemberSync - Secure Membership Management</em></p>
            </div>
        </body>
        </html>
        """

        return send_email_notification(
            email,
            "✅ MemberSync Password Changed Successfully",
            html_content
        )

    except Exception as e:
        print(f"Error sending password change confirmation: {e}")
        return False

# Update your existing init_db() function to include the password reset table
# Add this line in your init_db() function after creating other tables:
# add_password_reset_table()

# Update your main block to ensure the password reset table exists
def ensure_password_reset_table():
    """Ensure password reset table exists in existing database"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()

            # Check if password_reset_tokens table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='password_reset_tokens'")
            if not cursor.fetchone():
                print("Creating password_reset_tokens table...")
                add_password_reset_table()
                return True
            else:
                print("✅ Password reset tokens table already exists")
                return True

    except Exception as e:
        print(f"❌ Error checking password reset table: {e}")
        return False

#=================================================================================================
#=================================================================================================

# PREPAID CARD UTILITY FUNCTIONS
# ===============================================================================================

def get_prepaid_balance(membership_id, organization_id):
    """Get current prepaid balance for a member"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT current_balance, total_recharged, total_spent, total_bonus_earned
            FROM prepaid_balances
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, organization_id))
        
        result = cursor.fetchone()
        if result:
            return {
                'current_balance': float(result[0]) if result[0] is not None else 0.0,
                'total_recharged': float(result[1]) if result[1] is not None else 0.0,
                'total_spent': float(result[2]) if result[2] is not None else 0.0,
                'total_bonus_earned': float(result[3]) if result[3] is not None else 0.0
            }
        else:
            # Create initial balance record
            cursor.execute('''
                INSERT INTO prepaid_balances (membership_id, organization_id, current_balance)
                VALUES (?, ?, 0.0)
            ''', (membership_id, organization_id))
            db.commit()
            
            return {
                'current_balance': 0.0,
                'total_recharged': 0.0,
                'total_spent': 0.0,
                'total_bonus_earned': 0.0
            }
            
    except Exception as e:
        print(f"Error getting prepaid balance: {e}")
        return None

def calculate_bonus(amount, organization_id):
    """Calculate bonus amount based on organization's bonus tiers"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT bonus_percentage, tier_name
            FROM prepaid_bonus_tiers
            WHERE organization_id = ? 
              AND is_active = 1
              AND min_amount <= ?
              AND (max_amount IS NULL OR max_amount >= ?)
            ORDER BY min_amount DESC
            LIMIT 1
        ''', (organization_id, amount, amount))
        
        result = cursor.fetchone()
        if result:
            bonus_percentage, tier_name = result
            bonus_amount = amount * (bonus_percentage / 100)
            return bonus_amount, bonus_percentage, tier_name
        else:
            # Default: no bonus
            return 0.0, 0.0, "No Bonus"
            
    except Exception as e:
        print(f"Error calculating bonus: {e}")
        return 0.0, 0.0, "Error"

def recharge_prepaid_card(membership_id, organization_id, amount, admin_user_id, description="", override_bonus=None, input_currency=None):
    """Recharge a member's prepaid card with bonus calculation"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Simplified: No currency conversion, just use amount as-is
        recharge_amount = float(amount)
        
        # Get current balance
        balance_info = get_prepaid_balance(membership_id, organization_id)
        if balance_info is None:
            return False, "Error getting current balance"
        
        current_balance = balance_info['current_balance']
        
        # Calculate bonus
        if override_bonus is not None:
            bonus_amount = override_bonus
            bonus_percentage = (override_bonus / recharge_amount * 100) if recharge_amount > 0 else 0
            tier_name = "Custom Bonus"
        else:
            bonus_amount, bonus_percentage, tier_name = calculate_bonus(recharge_amount, organization_id)
        
        # Calculate new balance
        total_credit = recharge_amount + bonus_amount
        new_balance = current_balance + total_credit
        
        # Start transaction
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            # Record recharge transaction
            cursor.execute('''
                INSERT INTO prepaid_transactions 
                (membership_id, organization_id, transaction_type, amount, bonus_amount, 
                 bonus_percentage, balance_before, balance_after, description, admin_user_id)
                VALUES (?, ?, 'recharge', ?, ?, ?, ?, ?, ?, ?)
            ''', (membership_id, organization_id, recharge_amount, bonus_amount, bonus_percentage,
                  current_balance, new_balance, description, admin_user_id))
            
            # Record bonus transaction if applicable
            if bonus_amount > 0:
                cursor.execute('''
                    INSERT INTO prepaid_transactions 
                    (membership_id, organization_id, transaction_type, amount, bonus_amount, 
                     bonus_percentage, balance_before, balance_after, description, admin_user_id)
                    VALUES (?, ?, 'bonus', ?, ?, ?, ?, ?, ?, ?)
                ''', (membership_id, organization_id, bonus_amount, bonus_amount, bonus_percentage,
                      current_balance + recharge_amount, new_balance, f"{tier_name} ({bonus_percentage}%)", admin_user_id))
            
            # Update balance
            cursor.execute('''
                UPDATE prepaid_balances 
                SET current_balance = ?,
                    total_recharged = total_recharged + ?,
                    total_bonus_earned = total_bonus_earned + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE membership_id = ? AND organization_id = ?
            ''', (new_balance, recharge_amount, bonus_amount, membership_id, organization_id))
            
            cursor.execute('COMMIT')
            
            # Send notification
            send_recharge_notification(membership_id, organization_id, recharge_amount, bonus_amount, new_balance, tier_name)
            
            return True, {
                'amount': recharge_amount,
                'bonus_amount': bonus_amount,
                'bonus_percentage': bonus_percentage,
                'tier_name': tier_name,
                'new_balance': new_balance,
                'total_credit': total_credit
            }
            
        except Exception as e:
            cursor.execute('ROLLBACK')
            print(f"Transaction error: {e}")
            return False, f"Transaction failed: {e}"
            
    except Exception as e:
        print(f"Error recharging prepaid card: {e}")
        return False, f"Recharge failed: {e}"

def use_prepaid_balance(membership_id, organization_id, amount, admin_user_id, description="Service payment", input_currency=None):
    """Use prepaid balance for a service/payment"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Simplified: No currency conversion, just use amount as-is
        usage_amount = float(amount)
        
        # Get current balance
        balance_info = get_prepaid_balance(membership_id, organization_id)
        if balance_info is None:
            return False, "Error getting current balance"
        
        current_balance = balance_info['current_balance']
        
        # Check if sufficient balance
        if current_balance < usage_amount:
            return False, f"Insufficient balance. Current: {current_balance:.2f}, Required: {usage_amount:.2f}"
        
        new_balance = current_balance - usage_amount
        
        # Start transaction
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            # Record usage transaction
            cursor.execute('''
                INSERT INTO prepaid_transactions 
                (membership_id, organization_id, transaction_type, amount, bonus_amount, 
                 bonus_percentage, balance_before, balance_after, description, admin_user_id)
                VALUES (?, ?, 'usage', ?, 0.0, 0.0, ?, ?, ?, ?)
            ''', (membership_id, organization_id, usage_amount, current_balance, new_balance, description, admin_user_id))
            
            # Update balance
            cursor.execute('''
                UPDATE prepaid_balances 
                SET current_balance = ?,
                    total_spent = total_spent + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE membership_id = ? AND organization_id = ?
            ''', (new_balance, usage_amount, membership_id, organization_id))
            
            cursor.execute('COMMIT')
            
            # Send notification
            send_usage_notification(membership_id, organization_id, usage_amount, new_balance, description)
            
            return True, {
                'amount_used': usage_amount,
                'new_balance': new_balance,
                'description': description
            }
            
        except Exception as e:
            cursor.execute('ROLLBACK')
            print(f"Usage transaction error: {e}")
            return False, f"Usage failed: {e}"
            
    except Exception as e:
        print(f"Error using prepaid balance: {e}")
        return False, f"Usage failed: {e}"

# ============================================================================
# NOTIFICATION FUNCTIONS
# ============================================================================

def send_recharge_notification(membership_id, organization_id, amount, bonus_amount, new_balance, tier_name):
    """Send notification after prepaid card recharge"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get member details
        cursor.execute('''
            SELECT name, email, phone FROM members 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, organization_id))
        
        member = cursor.fetchone()
        if not member:
            return False
        
        name, email, phone = member
        currency = get_currency_symbol()
        
        # Create message
        if bonus_amount > 0:
            message = f"Hello {name}, your prepaid card has been recharged with {currency}{amount:.2f} (+{currency}{bonus_amount:.2f} {tier_name} bonus). New balance: {currency}{new_balance:.2f}. - MemberSync"
        else:
            message = f"Hello {name}, your prepaid card has been recharged with {currency}{amount:.2f}. New balance: {currency}{new_balance:.2f}. - MemberSync"
        
        # Send SMS if phone number available
        if phone and validate_phone_number_enhanced(phone)[0]:
            send_sms_notification(format_phone_number(phone), message)
        
        # Send email if email available
        if email:
            email_subject = "💳 Prepaid Card Recharged - MemberSync"
            email_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; text-align: center;">
                    <h2>💳 Prepaid Card Recharged</h2>
                </div>
                <div style="padding: 20px; background: #f8f9fa;">
                    <h3>Hello {name}!</h3>
                    <p>Your prepaid card has been successfully recharged.</p>
                    
                    <div style="background: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h4>Recharge Details:</h4>
                        <ul>
                            <li><strong>Recharge Amount:</strong> {currency}{amount:.2f}</li>
                            {f'<li><strong>Bonus Amount:</strong> {currency}{bonus_amount:.2f} ({tier_name})</li>' if bonus_amount > 0 else ''}
                            <li><strong>Total Credit:</strong> {currency}{amount + bonus_amount:.2f}</li>
                            <li><strong>New Balance:</strong> {currency}{new_balance:.2f}</li>
                        </ul>
                    </div>
                    
                    <p>You can now use your prepaid balance for services and payments.</p>
                    <p>Thank you for using MemberSync!</p>
                </div>
            </body>
            </html>
            """
            send_email_notification(email, email_subject, email_html)
        
        # Log notification
        cursor.execute('''
            INSERT INTO notifications (membership_id, organization_id, type, message, sent_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (membership_id, organization_id, 'prepaid_recharge', message, 
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        db.commit()
        return True
        
    except Exception as e:
        print(f"Error sending recharge notification: {e}")
        return False

def send_usage_notification(membership_id, organization_id, amount, new_balance, description):
    """Send notification after prepaid balance usage"""
    try:
        print(f"\n=== DEBUG: Usage Notification ===")
        print(f"Membership ID: {membership_id}")
        print(f"Organization ID: {organization_id}")
        print(f"Amount: {amount}")
        print(f"New Balance: {new_balance}")
        print(f"Description: {description}")
        
        db = get_db()
        cursor = db.cursor()
        
        # Get member details
        cursor.execute('''
            SELECT name, email, phone FROM members 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, organization_id))
        
        member = cursor.fetchone()
        if not member:
            print(f"ERROR: Member not found - {membership_id}")
            return False
        
        name, email, phone = member
        print(f"Member found: {name}")
        print(f"Email: {email}, Phone: {phone}")
        
        # Get currency symbol
        currency = get_currency_symbol()
        print(f"Currency symbol: {currency}")
        
        # Create message
        message = f"Hello {name}, {currency}{amount:.2f} has been deducted from your prepaid card for {description}. Remaining balance: {currency}{new_balance:.2f}. - MemberSync"
        print(f"SMS Message prepared: {message[:50]}...")
        
        # Send SMS if phone number available
        sms_sent = False
        if phone and validate_phone_number_enhanced(phone)[0]:
            print(f"Attempting to send SMS to: {phone}")
            success, _ = send_sms_notification(format_phone_number(phone), message)
            sms_sent = success
            print(f"SMS sent: {sms_sent}")
        else:
            print(f"No valid phone number for SMS")
        
        # Send email if email available
        email_sent = False
        if email:
            print(f"Attempting to send email to: {email}")
            email_subject = "💳 Prepaid Card Used - MemberSync"
            email_html = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 0;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
                        color: white;
                        padding: 30px 20px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                    }}
                    .content {{
                        background: #f8f9fa;
                        padding: 30px 20px;
                        border-radius: 0 0 10px 10px;
                    }}
                    .transaction-box {{
                        background: white;
                        padding: 20px;
                        border-radius: 8px;
                        margin: 20px 0;
                        border-left: 4px solid #007bff;
                    }}
                    .amount {{
                        font-size: 24px;
                        color: #dc3545;
                        font-weight: bold;
                    }}
                    .balance {{
                        font-size: 20px;
                        color: #28a745;
                        font-weight: bold;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 20px;
                        padding: 20px;
                        color: #666;
                        font-size: 12px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>💳 Prepaid Card Transaction</h1>
                    <p>Your prepaid balance has been used</p>
                </div>
                
                <div class="content">
                    <h2>Hello {name}!</h2>
                    <p>Your prepaid card has been used for a transaction.</p>
                    
                    <div class="transaction-box">
                        <h3>📋 Transaction Details:</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0;"><strong>Amount Used:</strong></td>
                                <td style="padding: 8px 0; text-align: right;" class="amount">-{currency}{amount:.2f}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0;"><strong>Description:</strong></td>
                                <td style="padding: 8px 0; text-align: right;">{description}</td>
                            </tr>
                            <tr style="border-top: 2px solid #dee2e6;">
                                <td style="padding: 8px 0;"><strong>Remaining Balance:</strong></td>
                                <td style="padding: 8px 0; text-align: right;" class="balance">{currency}{new_balance:.2f}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;">💡 <strong>Tip:</strong> You can recharge your prepaid card anytime at any of our locations or through your member portal.</p>
                    </div>
                    
                    <p>Thank you for using MemberSync!</p>
                    
                    <p style="color: #666; font-size: 14px;">
                        <em>Transaction Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</em>
                    </p>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from MemberSync</p>
                    <p>Please do not reply to this email</p>
                    <p>&copy; 2024 MemberSync - Prepaid Card Management System</p>
                </div>
            </body>
            </html>
            """
            
            email_sent = send_email_notification(email, email_subject, email_html)
            print(f"Email sent: {email_sent}")
        else:
            print(f"No email address available")
        
        # Log notification in database
        print(f"Logging notification to database...")
        cursor.execute('''
            INSERT INTO notifications (membership_id, organization_id, type, message, sent_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (membership_id, organization_id, 'prepaid_usage', message, 
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        # Commit the transaction
        try:
            db.commit()
            print(f"✅ Database commit successful")
        except Exception as commit_error:
            print(f"❌ Database commit error: {commit_error}")
            import traceback
            traceback.print_exc()
            return False
        
        print(f"=== Notification Summary ===")
        print(f"SMS sent: {sms_sent}")
        print(f"Email sent: {email_sent}")
        print(f"Database logged: True")
        print(f"================================\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR in send_usage_notification: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# BONUS TIER MANAGEMENT FUNCTIONS
# ============================================================================

def create_default_bonus_tiers(organization_id):
    """Create default bonus tiers for an organization"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        default_tiers = [
            ("Bronze", 0, 9999.99, 0),      # 0% bonus for amounts under 10K
            ("Silver", 10000, 49999.99, 5),  # 5% bonus for 10K-50K
            ("Gold", 50000, 99999.99, 10),   # 10% bonus for 50K-100K
            ("Platinum", 100000, None, 20)   # 20% bonus for 100K+
        ]
        
        for tier_name, min_amount, max_amount, bonus_percentage in default_tiers:
            cursor.execute('''
                INSERT INTO prepaid_bonus_tiers 
                (organization_id, tier_name, min_amount, max_amount, bonus_percentage)
                VALUES (?, ?, ?, ?, ?)
            ''', (organization_id, tier_name, min_amount, max_amount, bonus_percentage))
        
        db.commit()
        return True
        
    except Exception as e:
        print(f"Error creating default bonus tiers: {e}")
        return False

def get_bonus_tiers(organization_id):
    """Get all bonus tiers for an organization"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT id, tier_name, min_amount, max_amount, bonus_percentage, is_active
            FROM prepaid_bonus_tiers
            WHERE organization_id = ?
            ORDER BY min_amount
        ''', (organization_id,))
        
        return cursor.fetchall()
        
    except Exception as e:
        print(f"Error getting bonus tiers: {e}")
        return []

# ============================================================================
# PREPAID CARD ROUTES
# ============================================================================

@app.route('/prepaid_card/<membership_id>')
@require_login
@require_prepaid_access
def prepaid_card_management(membership_id):
    """Prepaid card management page for a member"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                flash('Member not found.', 'danger')
                return redirect(url_for('members'))
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                flash('Organization not found.', 'danger')
                return redirect(url_for('members'))
        
        # Get member details
        cursor.execute('''
            SELECT name, email, phone, membership_type FROM members 
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        member = cursor.fetchone()
        if not member:
            flash('Member not found.', 'danger')
            return redirect(url_for('members'))
        
        # Get prepaid balance
        balance_info = get_prepaid_balance(membership_id, org_id)
        
        # Get transaction history
        cursor.execute('''
            SELECT transaction_type, amount, bonus_amount, bonus_percentage,
                   balance_before, balance_after, description, transaction_date
            FROM prepaid_transactions
            WHERE membership_id = ? AND organization_id = ?
            ORDER BY transaction_date DESC
            LIMIT 20
        ''', (membership_id, org_id))
        
        transactions = cursor.fetchall()
        
        # Get bonus tiers
        bonus_tiers = get_bonus_tiers(org_id)
        
        return render_template('prepaid_card_management.html',
                             member=member,
                             membership_id=membership_id,
                             balance_info=balance_info,
                             transactions=transactions,
                             bonus_tiers=bonus_tiers)
        
    except Exception as e:
        flash(f'Error loading prepaid card: {e}', 'danger')
        return redirect(url_for('members'))

@app.route('/prepaid_recharge/<membership_id>', methods=['POST'])
@require_login
@require_prepaid_access
def prepaid_recharge(membership_id):
    """Process prepaid card recharge"""
    try:
        amount = float(request.form.get('amount', 0))
        description = request.form.get('description', 'Prepaid card recharge')
        override_bonus_percentage = request.form.get('override_bonus_percentage', '').strip()
        
        if amount <= 0:
            flash('Invalid recharge amount.', 'danger')
            return redirect(url_for('prepaid_card_management', membership_id=membership_id))
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                flash('Member not found.', 'danger')
                return redirect(url_for('members'))
            org_id = member_result[0]
        else:
            org_id = session.get('organization_id')
            if not org_id:
                flash('Organization not found.', 'danger')
                return redirect(url_for('members'))
        
        admin_user_id = session.get('user_id')
        
        # Handle override bonus percentage (convert to amount)
        override_bonus_amount = None
        if override_bonus_percentage:
            try:
                bonus_percent = float(override_bonus_percentage)
                if 0 <= bonus_percent <= 20:  # Validate 0-20% range
                    override_bonus_amount = amount * (bonus_percent / 100)
                else:
                    flash('Bonus percentage must be between 0% and 20%.', 'warning')
            except ValueError:
                flash('Invalid bonus percentage.', 'warning')
        
        # Process recharge
        success, result = recharge_prepaid_card(
            membership_id, org_id, amount, admin_user_id, 
            description, override_bonus_amount
        )
        
        if success:
            flash(f'✅ Prepaid card recharged successfully! Amount: ${result["amount"]:.2f}, Bonus: ${result["bonus_amount"]:.2f}, New Balance: ${result["new_balance"]:.2f}', 'success')
        else:
            flash(f'❌ Recharge failed: {result}', 'danger')
        
    except ValueError:
        flash('Invalid amount entered.', 'danger')
    except Exception as e:
        flash(f'Error processing recharge: {e}', 'danger')
    
    return redirect(url_for('prepaid_card_management', membership_id=membership_id))

@app.route('/prepaid_usage/<membership_id>', methods=['POST'])
@require_login
@require_prepaid_access
def prepaid_usage(membership_id):
    """Initiate prepaid usage with OTP verification"""
    try:
        amount = float(request.form.get('amount', 0))
        description = request.form.get('description', 'Service payment')
        
        if amount <= 0:
            flash('Invalid usage amount.', 'danger')
            return redirect(url_for('prepaid_card_management', membership_id=membership_id))
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                flash('Member not found.', 'danger')
                return redirect(url_for('members'))
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                flash('Organization not found.', 'danger')
                return redirect(url_for('members'))
        
        # Check balance before sending OTP
        balance_info = get_prepaid_balance(membership_id, org_id)
        if not balance_info:
             flash('Could not retrieve balance information.', 'danger')
             return redirect(url_for('prepaid_card_management', membership_id=membership_id))
             
        current_balance = balance_info['current_balance']
        
        # Calculate fee to check total required
        fee_amount = calculate_deduction_fee(amount)
        total_deduction = amount + fee_amount
        
        if current_balance < total_deduction:
             flash(f"Insufficient balance. Required: {get_currency_symbol()}{total_deduction:.2f} (including {get_currency_symbol()}{fee_amount:.2f} fee)", "danger")
             return redirect(url_for('prepaid_card_management', membership_id=membership_id))

        # Generate OTP
        otp = secrets.randbelow(1000000)
        otp_str = f"{otp:06d}"
        
        # Get member contact info
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT name, email, phone FROM members WHERE membership_id = ? AND organization_id = ?', (membership_id, org_id))
        member = cursor.fetchone()
        
        if not member:
             flash('Member not found.', 'danger')
             return redirect(url_for('prepaid_card_management', membership_id=membership_id))
             
        name, email, phone = member
        
        # Send OTP via Email
        if email:
            send_email_notification(
                email, 
                "🔐 Prepaid Transaction OTP", 
                f"Hello {name},<br><br>Your OTP for prepaid transaction of {get_currency_symbol()}{amount:.2f} is: <strong>{otp_str}</strong>.<br>Do not share this code."
            )
            
        # Send OTP via SMS
        if phone and validate_phone_number_enhanced(phone)[0]:
             send_sms_notification(format_phone_number(phone), f"MemberSync: Your OTP for prepaid transaction is {otp_str}.")

        # Store in session
        session['prepaid_otp_context'] = {
            'otp': otp_str,
            'membership_id': membership_id,
            'org_id': org_id,
            'amount': amount,
            'description': description,
            'timestamp': time.time()
        }
        
        return render_template('verify_prepaid_otp.html', membership_id=membership_id, amount=amount, description=description)

    except ValueError:
        flash('Invalid amount entered.', 'danger')
        return redirect(url_for('prepaid_card_management', membership_id=membership_id))
    except Exception as e:
        flash(f'Error initiating usage: {e}', 'danger')
        return redirect(url_for('prepaid_card_management', membership_id=membership_id))

@app.route('/verify_prepaid_otp', methods=['POST'])
@require_login
@require_prepaid_access
def verify_prepaid_otp():
    """Verify OTP and process prepaid usage"""
    otp_input = request.form.get('otp', '').strip()
    context = session.get('prepaid_otp_context')
    
    if not context:
        flash('Session expired or invalid transaction. Please try again.', 'danger')
        return redirect(url_for('dashboard'))
        
    membership_id = context.get('membership_id')
    
    # Verify OTP
    if otp_input != context.get('otp'):
        flash('Invalid OTP. Please try again.', 'danger')
        return render_template('verify_prepaid_otp.html', membership_id=membership_id, amount=context.get('amount'), description=context.get('description'))
        
    # Check expiry (e.g., 5 minutes)
    if time.time() - context.get('timestamp', 0) > 300:
        session.pop('prepaid_otp_context', None)
        flash('OTP expired. Please initiate transaction again.', 'danger')
        return redirect(url_for('prepaid_card_management', membership_id=membership_id))
        
    # Process Transaction
    try:
        org_id = context.get('org_id')
        amount = context.get('amount')
        description = context.get('description')
        admin_user_id = session.get('user_id')
        
        success, result = apply_deduction_fee(
            membership_id, org_id, amount, admin_user_id, description
        )
        
        if success:
            session.pop('prepaid_otp_context', None)
            flash(f'✅ {result}', 'success')
        else:
            flash(f'❌ Usage failed: {result}', 'danger')
            
    except Exception as e:
        flash(f'Error processing usage: {e}', 'danger')
    
    return redirect(url_for('prepaid_card_management', membership_id=membership_id))

@app.route('/prepaid_bonus_tiers')
@require_login
@require_prepaid_access
@require_superadmin
def manage_bonus_tiers():
    """Manage bonus tiers for the organization"""
    org_id = session.get('organization_id')
    bonus_tiers = get_bonus_tiers(org_id)
    
    return render_template('manage_bonus_tiers.html', bonus_tiers=bonus_tiers)

@app.route('/create_bonus_tier', methods=['POST'])
@require_login
@require_superadmin
def create_bonus_tier():
    """Create a new bonus tier"""
    try:
        tier_name = request.form.get('tier_name', '').strip()
        min_amount = float(request.form.get('min_amount', 0))
        max_amount = request.form.get('max_amount', '').strip()
        bonus_percentage = float(request.form.get('bonus_percentage', 0))
        
        if not tier_name:
            flash('Tier name is required.', 'danger')
            return redirect(url_for('manage_bonus_tiers'))
        
        if min_amount < 0 or bonus_percentage < 0:
            flash('Amounts and percentage must be positive.', 'danger')
            return redirect(url_for('manage_bonus_tiers'))
        
        max_amount_value = float(max_amount) if max_amount else None
        
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        cursor.execute('''
            INSERT INTO prepaid_bonus_tiers 
            (organization_id, tier_name, min_amount, max_amount, bonus_percentage)
            VALUES (?, ?, ?, ?, ?)
        ''', (org_id, tier_name, min_amount, max_amount_value, bonus_percentage))
        
        db.commit()
        flash('Bonus tier created successfully!', 'success')
        
    except ValueError:
        flash('Invalid numeric values entered.', 'danger')
    except Exception as e:
        flash(f'Error creating bonus tier: {e}', 'danger')
    
    return redirect(url_for('manage_bonus_tiers'))

# ============================================================================
# INTEGRATION WITH EXISTING PAYMENT SYSTEM
# ============================================================================

def add_prepaid_payment_option():
    """Add prepaid payment option to existing payment forms"""
    # This function should be integrated into your existing payment routes
    # to allow members to pay using their prepaid balance
    pass

# ============================================================================
# UPDATE MEMBER PROFILE TO INCLUDE PREPAID BALANCE
# ============================================================================

def update_member_profile_with_prepaid():
    """Update member profile template to show prepaid balance"""
    # Add this to your member_profile route:
    """
    # Get prepaid balance
    balance_info = get_prepaid_balance(membership_id, session.get('organization_id'))
    
    # Pass to template
    return render_template('member_profile.html', 
                         member=member, 
                         prepaid_balance=balance_info,
                         ...)
    """
    pass

# ============================================================================
# ANALYTICS AND REPORTING
# ============================================================================

def get_prepaid_analytics(organization_id):
    """Get prepaid card analytics for dashboard"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Total prepaid metrics
        cursor.execute('''
            SELECT 
                COALESCE(SUM(current_balance), 0) as total_balance,
                COALESCE(SUM(total_recharged), 0) as total_recharged,
                COALESCE(SUM(total_spent), 0) as total_spent,
                COALESCE(SUM(total_bonus_earned), 0) as total_bonus,
                COUNT(*) as active_cards
            FROM prepaid_balances
            WHERE organization_id = ? AND current_balance > 0
        ''', (organization_id,))
        
        metrics = cursor.fetchone()
        
        # Recent transactions
        cursor.execute('''
            SELECT COUNT(*) 
            FROM prepaid_transactions
            WHERE organization_id = ? 
              AND transaction_date >= datetime('now', '-30 days')
        ''', (organization_id,))
        
        recent_transactions = cursor.fetchone()[0]
        
        return {
            'total_balance': metrics[0] if metrics else 0,
            'total_recharged': metrics[1] if metrics else 0,
            'total_spent': metrics[2] if metrics else 0,
            'total_bonus': metrics[3] if metrics else 0,
            'active_cards': metrics[4] if metrics else 0,
            'recent_transactions': recent_transactions
        }
        
    except Exception as e:
        print(f"Error getting prepaid analytics: {e}")
        return None


#=================================================================================================
# Whole checkin process
#================================================================================================

# ============================================================================
# CHECK-IN SYSTEM ROUTES AND FUNCTIONS
# ============================================================================

def is_member_checked_in(membership_id, organization_id):
    """Check if member is currently checked in"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT id, checkin_time, service_type
            FROM checkins
            WHERE membership_id = ? AND organization_id = ? AND status = 'checked_in'
            ORDER BY checkin_time DESC
            LIMIT 1
        ''', (membership_id, organization_id))
        
        result = cursor.fetchone()
        if result:
            return {
                'id': result[0],
                'checkin_time': result[1],
                'service_type': result[2],
                'is_checked_in': True
            }
        return {'is_checked_in': False}
        
    except Exception as e:
        print(f"Error checking member status: {e}")
        return {'is_checked_in': False}

def get_checkin_settings(organization_id):
    """Get check-in settings for organization"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT require_checkout, auto_checkout_hours, allow_multiple_checkins,
                   require_service_type, send_checkin_notifications
            FROM checkin_settings
            WHERE organization_id = ?
        ''', (organization_id,))
        
        result = cursor.fetchone()
        if result:
            return {
                'require_checkout': bool(result[0]),
                'auto_checkout_hours': result[1],
                'allow_multiple_checkins': bool(result[2]),
                'require_service_type': bool(result[3]),
                'send_checkin_notifications': bool(result[4])
            }
        else:
            # Create default settings
            cursor.execute('''
                INSERT INTO checkin_settings (organization_id)
                VALUES (?)
            ''', (organization_id,))
            db.commit()
            return {
                'require_checkout': False,
                'auto_checkout_hours': 24,
                'allow_multiple_checkins': False,
                'require_service_type': False,
                'send_checkin_notifications': True
            }
            
    except Exception as e:
        print(f"Error getting checkin settings: {e}")
        return {}

def get_service_types(org_id):
    """Get service types for an organization"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT id, name, description, color
            FROM service_types
            WHERE organization_id = ? AND is_active = 1
            ORDER BY name
        ''', (org_id,))
        
        return cursor.fetchall()
        
    except Exception as e:
        print(f"Error getting service types: {e}")
        return []

def get_all_service_types():
    """Get all available service types across all organizations for global admin"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT st.id, st.name, st.description, st.color, o.name as organization_name
            FROM service_types st
            JOIN organizations o ON st.organization_id = o.id
            WHERE st.is_active = 1
            ORDER BY o.name, st.name
        ''')
        
        return cursor.fetchall()
        
    except Exception as e:
        print(f"Error getting all service types: {e}")
        return []

def process_member_checkin(membership_id, organization_id, service_type=None, notes=""):
    """Process member check-in"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get member details
        cursor.execute('''
            SELECT name, status, expiration_date FROM members
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, organization_id))
        
        member = cursor.fetchone()
        if not member:
            return False, "Member not found"
        
        name, status, expiration_date = member
        
        # Check member status
        if status != 'active':
            return False, f"Member status is {status}. Only active members can check in."
        
        # Check expiration
        if expiration_date:
            exp_date = datetime.strptime(expiration_date, '%Y-%m-%d').date()
            if exp_date < datetime.now().date():
                return False, "Membership has expired. Please renew to check in."
        
        # Get settings
        settings = get_checkin_settings(organization_id)
        
        # Check if already checked in
        current_status = is_member_checked_in(membership_id, organization_id)
        if current_status['is_checked_in'] and not settings.get('allow_multiple_checkins', False):
            return False, f"Member is already checked in since {current_status['checkin_time']}"
        
        # Process check-in
        admin_user_id = session.get('user_id')
        
        cursor.execute('''
            INSERT INTO checkins (membership_id, organization_id, service_type, notes, admin_user_id, status)
            VALUES (?, ?, ?, ?, ?, 'checked_in')
        ''', (membership_id, organization_id, service_type, notes, admin_user_id))
        
        checkin_id = cursor.lastrowid
        
        # Send notification if enabled
        if settings.get('send_checkin_notifications', True):
            send_checkin_notification(membership_id, organization_id, 'checkin', service_type)
        
        db.commit()
        
        return True, {
            'checkin_id': checkin_id,
            'member_name': name,
            'service_type': service_type,
            'checkin_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        print(f"Error processing checkin: {e}")
        return False, f"Check-in failed: {e}"

def process_member_checkout(membership_id, organization_id):
    """Process member check-out"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Find active check-in
        cursor.execute('''
            SELECT id, checkin_time, service_type
            FROM checkins
            WHERE membership_id = ? AND organization_id = ? AND status = 'checked_in'
            ORDER BY checkin_time DESC
            LIMIT 1
        ''', (membership_id, organization_id))
        
        checkin = cursor.fetchone()
        if not checkin:
            return False, "No active check-in found for this member"
        
        checkin_id, checkin_time, service_type = checkin
        
        # Update check-in record
        cursor.execute('''
            UPDATE checkins
            SET checkout_time = CURRENT_TIMESTAMP, status = 'checked_out'
            WHERE id = ?
        ''', (checkin_id,))
        
        # Send notification
        settings = get_checkin_settings(organization_id)
        if settings.get('send_checkin_notifications', True):
            send_checkin_notification(membership_id, organization_id, 'checkout', service_type)
        
        db.commit()
        
        return True, {
            'checkin_id': checkin_id,
            'checkout_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        print(f"Error processing checkout: {e}")
        return False, f"Check-out failed: {e}"

def send_checkin_notification(membership_id, organization_id, action, service_type=None):
    """Send check-in/out notification"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get member details
        cursor.execute('''
            SELECT name, email, phone FROM members
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, organization_id))
        
        member = cursor.fetchone()
        if not member:
            return False
        
        name, email, phone = member
        
        if action == 'checkin':
            message = f"Hello {name}, you have successfully checked in"
            if service_type:
                message += f" for {service_type}"
            message += f" at {datetime.now().strftime('%H:%M')}. - MemberSync"
        else:
            message = f"Hello {name}, you have checked out at {datetime.now().strftime('%H:%M')}. Thank you for visiting! - MemberSync"
        
        # Send SMS if available
        if phone and validate_phone_number_enhanced(phone)[0]:
            send_sms_notification(format_phone_number(phone), message)
        
        # Log notification
        cursor.execute('''
            INSERT INTO notifications (membership_id, organization_id, type, message, sent_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (membership_id, organization_id, f'checkin_{action}', message,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        db.commit()
        return True
        
    except Exception as e:
        print(f"Error sending checkin notification: {e}")
        return False

# ============================================================================
# CHECK-IN ROUTES
# ============================================================================

@app.route('/checkin')
@require_login
def checkin_dashboard():
    """Check-in dashboard with current status and quick actions"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get organization_id with support for global admin switching
        org_id = session.get('organization_id')
        organizations = []
        
        # For global admins, get all organizations for switching
        if is_global_superadmin():
            cursor.execute('SELECT id, name FROM organizations WHERE status = "active" ORDER BY name')
            organizations = cursor.fetchall()
        
        # Get today's check-in statistics
        if is_global_superadmin():
            # Global admin: get stats from all organizations
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_checkins,
                    COUNT(CASE WHEN status = 'checked_in' THEN 1 END) as currently_checked_in,
                    COUNT(DISTINCT membership_id) as unique_visitors
                FROM checkins
                WHERE date(checkin_time) = date('now')
            ''')
        else:
            # Org admin: get stats from specific organization
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_checkins,
                    COUNT(CASE WHEN status = 'checked_in' THEN 1 END) as currently_checked_in,
                    COUNT(DISTINCT membership_id) as unique_visitors
                FROM checkins
                WHERE organization_id = ? AND date(checkin_time) = date('now')
            ''', (org_id,))
        
        today_stats = cursor.fetchone()
        
        # Get currently checked in members
        if is_global_superadmin():
            # Global admin: get from all organizations
            cursor.execute('''
                SELECT c.membership_id, m.name, c.checkin_time, c.service_type,
                       ROUND((julianday('now') - julianday(c.checkin_time)) * 24, 1) as hours_checked_in
                FROM checkins c
                JOIN members m ON c.membership_id = m.membership_id AND c.organization_id = m.organization_id
                WHERE c.status = 'checked_in'
                ORDER BY c.checkin_time DESC
            ''')
        else:
            # Org admin: get from specific organization
            cursor.execute('''
                SELECT c.membership_id, m.name, c.checkin_time, c.service_type,
                       ROUND((julianday('now') - julianday(c.checkin_time)) * 24, 1) as hours_checked_in
                FROM checkins c
                JOIN members m ON c.membership_id = m.membership_id AND c.organization_id = m.organization_id
                WHERE c.organization_id = ? AND c.status = 'checked_in'
                ORDER BY c.checkin_time DESC
            ''', (org_id,))
        
        current_checkins = cursor.fetchall()
        
        # Get recent check-ins (last 10)
        if is_global_superadmin():
            # Global admin: get from all organizations
            cursor.execute('''
                SELECT c.membership_id, m.name, c.checkin_time, c.checkout_time, 
                       c.service_type, c.status
                FROM checkins c
                JOIN members m ON c.membership_id = m.membership_id AND c.organization_id = m.organization_id
                ORDER BY c.checkin_time DESC
                LIMIT 10
            ''')
        else:
            # Org admin: get from specific organization
            cursor.execute('''
                SELECT c.membership_id, m.name, c.checkin_time, c.checkout_time, 
                       c.service_type, c.status
                FROM checkins c
                JOIN members m ON c.membership_id = m.membership_id AND c.organization_id = m.organization_id
                WHERE c.organization_id = ?
                ORDER BY c.checkin_time DESC
                LIMIT 10
            ''', (org_id,))
        
        recent_checkins = cursor.fetchall()
        
        # Get service types for quick actions
        if is_global_superadmin():
            # Global admin: get service types from all organizations
            service_types = get_all_service_types()
        else:
            # Org admin: get service types from specific organization
            service_types = get_service_types(org_id)
        
        return render_template('checkin_dashboard.html',
                             today_stats=today_stats,
                             current_checkins=current_checkins,
                             recent_checkins=recent_checkins,
                             service_types=service_types,
                             organizations=organizations)
        
    except Exception as e:
        flash(f'Error loading check-in dashboard: {e}', 'danger')
        return render_template('checkin_dashboard.html',
                             today_stats=(0, 0, 0),
                             current_checkins=[],
                             recent_checkins=[],
                             service_types=[],
                             organizations=[])

@app.route('/checkin/scan')
@require_login
def checkin_scan():
    """QR code scanner page for check-in"""
    org_id = session.get('organization_id')
    service_types = get_service_types(org_id)
    settings = get_checkin_settings(org_id)
    
    return render_template('checkin_scanner.html',
                         service_types=service_types,
                         settings=settings)

@app.route('/switch_organization/<int:org_id>', methods=['POST'])
@require_login
def switch_checkin_organization(org_id):
    """Switch organization for check-in dashboard (for global admins)"""
    try:
        if not is_global_superadmin():
            return {'success': False, 'error': 'Access denied'}
        
        # Verify organization exists
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id, name FROM organizations WHERE id = ?', (org_id,))
        org = cursor.fetchone()
        
        if not org:
            return {'success': False, 'error': 'Organization not found'}
        
        # Update session with new organization
        session['organization_id'] = org_id
        session['organization_name'] = org[1]
        
        return {'success': True, 'message': f'Switched to {org[1]}'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/checkin/process', methods=['POST'])
@require_login
def process_checkin():
    """Process check-in from QR scan or manual entry"""
    try:
        # Log request data for debugging
        print("\n=== Received check-in request ===")
        print(f"Request method: {request.method}")
        print(f"Content-Type: {request.content_type}")
        print(f"Form data: {request.form}")
        print(f"JSON data: {request.get_json(silent=True) or 'No JSON data'}")
        print(f"Request headers: {dict(request.headers)}")
        
        # Get data from form or JSON
        if request.is_json:
            data = request.get_json() or {}
            membership_id = str(data.get('membership_id', '')).strip()
            action = data.get('action', 'checkin')
            service_type = data.get('service_type', '')
            notes = data.get('notes', '')
        else:
            membership_id = request.form.get('membership_id', '').strip()
            action = request.form.get('action', 'checkin')
            service_type = request.form.get('service_type', '')
            notes = request.form.get('notes', '')
        
        print(f"Processing {action} for member: {membership_id}")
        
        if not membership_id:
            print("Error: No membership ID provided")
            return {'success': False, 'error': 'Membership ID is required'}
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                return {'success': False, 'error': 'Member not found'}
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                return {'success': False, 'error': 'Organization not found'}
        
        print(f"Organization ID: {org_id}")
        print(f"Service type: {service_type}")
        print(f"Notes: {notes}")
        print("===============================\n")
        
        if action == 'checkin':
            success, result = process_member_checkin(membership_id, org_id, service_type, notes)
        elif action == 'checkout':
            success, result = process_member_checkout(membership_id, org_id)
        else:
            return {'success': False, 'error': 'Invalid action'}
        
        if success:
            return {'success': True, 'data': result}
        else:
            return {'success': False, 'error': result}
            
    except Exception as e:
        return {'success': False, 'error': f'Processing failed: {e}'}

@app.route('/checkin/member_info/<membership_id>')
@require_login
def checkin_member_info(membership_id):
    """Get member information for check-in verification"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        # Get member details
        cursor.execute('''
            SELECT m.membership_id, m.name, m.email, m.phone, m.membership_type,
                   m.expiration_date, m.status, m.photo_filename
            FROM members m
            WHERE m.membership_id = ? AND m.organization_id = ?
        ''', (membership_id, org_id))
        
        member = cursor.fetchone()
        if not member:
            return {'success': False, 'error': 'Member not found'}
        
        # Get prepaid balance
        balance_info = get_prepaid_balance(membership_id, org_id)
        
        # Check current check-in status
        checkin_status = is_member_checked_in(membership_id, org_id)
        
        # Calculate expiry information
        expiry_status = 'unknown'
        days_until_expiry = None
        
        if member[5]:  # expiration_date
            try:
                exp_date = datetime.strptime(member[5], '%Y-%m-%d').date()
                today = datetime.now().date()
                days_until_expiry = (exp_date - today).days
                
                if days_until_expiry < 0:
                    expiry_status = 'expired'
                elif days_until_expiry <= 7:
                    expiry_status = 'warning'
                else:
                    expiry_status = 'active'
            except ValueError:
                expiry_status = 'invalid'
        
        member_data = {
            'membership_id': member[0],
            'name': member[1],
            'email': member[2],
            'phone': member[3],
            'membership_type': member[4],
            'expiration_date': member[5],
            'status': member[6],
            'photo_filename': member[7],
            'expiry_status': expiry_status,
            'days_until_expiry': days_until_expiry,
            'prepaid_balance': balance_info['current_balance'] if balance_info else 0,
            'checkin_status': checkin_status
        }
        
        return {'success': True, 'member': member_data}
        
    except Exception as e:
        return {'success': False, 'error': f'Error getting member info: {e}'}

@app.route('/checkin/status')
@require_login
def checkin_status():
    """Get current check-in status for navbar updates"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        
        cursor.execute('''
            SELECT COUNT(*) FROM checkins
            WHERE organization_id = ? AND status = 'checked_in'
        ''', (org_id,))
        
        active_count = cursor.fetchone()[0]
        
        return {'success': True, 'active_count': active_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/checkin/history/<membership_id>')
@require_login
@require_member_access
def member_checkin_history(membership_id):
    """View check-in history for a specific member"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                flash('Member not found.', 'danger')
                return redirect(url_for('members'))
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                flash('Organization not found.', 'danger')
                return redirect(url_for('members'))
        
        # Get member details
        cursor.execute('''
            SELECT name, membership_type, status FROM members
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        member = cursor.fetchone()
        if not member:
            flash('Member not found.', 'danger')
            return redirect(url_for('members'))
        
        # Get check-in history
        cursor.execute('''
            SELECT checkin_time, checkout_time, service_type, status, notes,
                   CASE 
                       WHEN checkout_time IS NOT NULL THEN 
                           ROUND((julianday(checkout_time) - julianday(checkin_time)) * 24, 1)
                       ELSE 
                           ROUND((julianday('now') - julianday(checkin_time)) * 24, 1)
                   END as duration_hours
            FROM checkins
            WHERE membership_id = ? AND organization_id = ?
            ORDER BY checkin_time DESC
        ''', (membership_id, org_id))
        
        checkin_history = cursor.fetchall()
        
        # Get statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_visits,
                COUNT(CASE 
                    WHEN date(checkin_time) >= date('now', '-30 days') 
                    THEN 1 
                END) as visits_last_30_days,
                AVG(CASE 
                    WHEN checkout_time IS NOT NULL THEN 
                        (julianday(checkout_time) - julianday(checkin_time)) * 24
                    ELSE NULL 
                END) as avg_duration_hours
            FROM checkins
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, org_id))
        
        stats = cursor.fetchone()
        
        return render_template('member_checkin_history.html',
                             member=member,
                             membership_id=membership_id,
                             checkin_history=checkin_history,
                             stats=stats)
        
    except Exception as e:
        flash(f'Error loading check-in history: {e}', 'danger')
        return redirect(url_for('members'))

@app.route('/checkin/reports')
@require_login
def checkin_reports():
    """Check-in reports and analytics with location filtering"""
    try:
        db = get_db()
        cursor = db.cursor()
        org_id = session.get('organization_id')
        location_id = session.get('location_id') if is_location_admin() else None
        
        # Date range from request (default last 30 days)
        start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Build location filter
        location_filter = ""
        params = [org_id, start_date, end_date]
        
        if location_id:
            # Location admin sees only their location's check-ins
            location_filter = "AND location_id = ?"
            params.insert(1, location_id)
        
        # Daily statistics (for daily chart)
        cursor.execute(f'''
            SELECT 
                date(checkin_time) as check_date,
                COUNT(*) as total_checkins,
                COUNT(DISTINCT membership_id) as unique_visitors,
                AVG(CASE 
                    WHEN checkout_time IS NOT NULL THEN 
                        (julianday(checkout_time) - julianday(checkin_time)) * 24
                    ELSE NULL 
                END) as avg_duration
            FROM checkins
            WHERE organization_id = ? 
              {location_filter}
              AND date(checkin_time) BETWEEN ? AND ?
            GROUP BY date(checkin_time)
            ORDER BY check_date DESC
        ''', params)
        
        daily_breakdown = cursor.fetchall()
        
        # Service type statistics (for service chart)
        cursor.execute(f'''
            SELECT 
                COALESCE(service_type, 'No Service') as service,
                COUNT(*) as count
            FROM checkins
            WHERE organization_id = ? 
              {location_filter}
              AND date(checkin_time) BETWEEN ? AND ?
            GROUP BY service_type
            ORDER BY count DESC
        ''', params)
        
        service_breakdown = cursor.fetchall()
        
        # Hourly distribution (for hourly chart)
        cursor.execute('''
            SELECT 
                strftime('%H', checkin_time) as hour,
                COUNT(*) as count
            FROM checkins
            WHERE organization_id = ? 
              AND date(checkin_time) BETWEEN ? AND ?
            GROUP BY strftime('%H', checkin_time)
            ORDER BY hour
        ''', (org_id, start_date, end_date))
        
        hourly_breakdown = cursor.fetchall()
        
        # Top visitors
        cursor.execute('''
            SELECT 
                c.membership_id,
                m.name,
                COUNT(*) as visit_count,
                MAX(c.checkin_time) as last_visit
            FROM checkins c
            JOIN members m ON c.membership_id = m.membership_id AND c.organization_id = m.organization_id
            WHERE c.organization_id = ? 
              AND date(c.checkin_time) BETWEEN ? AND ?
            GROUP BY c.membership_id, m.name
            ORDER BY visit_count DESC
            LIMIT 10
        ''', (org_id, start_date, end_date))
        
        top_visitors = cursor.fetchall()
        
        # Calculate summary statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_checkins,
                COUNT(DISTINCT membership_id) as unique_members,
                AVG(CASE 
                    WHEN checkout_time IS NOT NULL THEN 
                        (julianday(checkout_time) - julianday(checkin_time)) * 24
                    ELSE NULL 
                END) as avg_duration
            FROM checkins
            WHERE organization_id = ? 
              AND date(checkin_time) BETWEEN ? AND ?
        ''', (org_id, start_date, end_date))
        
        summary = cursor.fetchone()
        
        return render_template('checkin_reports.html',
                             summary=summary,
                             daily_breakdown=daily_breakdown,
                             service_breakdown=service_breakdown,
                             hourly_breakdown=hourly_breakdown,
                             top_visitors=top_visitors,
                             start_date=start_date,
                             end_date=end_date)
        
    except Exception as e:
        flash(f'Error loading reports: {e}', 'danger')
        return render_template('checkin_reports.html',
                             summary=None,
                             daily_breakdown=[],
                             service_breakdown=[],
                             hourly_breakdown=[],
                             top_visitors=[],
                             start_date=start_date,
                             end_date=end_date)

@app.route('/checkin/settings', methods=['GET', 'POST'])
@require_login
@require_superadmin
def checkin_settings():
    """Manage check-in settings"""
    org_id = session.get('organization_id')
    
    if request.method == 'POST':
        try:
            require_checkout = bool(request.form.get('require_checkout'))
            auto_checkout_hours = int(request.form.get('auto_checkout_hours', 24))
            allow_multiple_checkins = bool(request.form.get('allow_multiple_checkins'))
            require_service_type = bool(request.form.get('require_service_type'))
            send_checkin_notifications = bool(request.form.get('send_checkin_notifications'))
            
            db = get_db()
            cursor = db.cursor()
            
            cursor.execute('''
                UPDATE checkin_settings
                SET require_checkout = ?, auto_checkout_hours = ?, 
                    allow_multiple_checkins = ?, require_service_type = ?,
                    send_checkin_notifications = ?, updated_at = CURRENT_TIMESTAMP
                WHERE organization_id = ?
            ''', (require_checkout, auto_checkout_hours, allow_multiple_checkins,
                  require_service_type, send_checkin_notifications, org_id))
            
            if cursor.rowcount == 0:
                # Insert if not exists
                cursor.execute('''
                    INSERT INTO checkin_settings 
                    (organization_id, require_checkout, auto_checkout_hours, 
                     allow_multiple_checkins, require_service_type, send_checkin_notifications)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (org_id, require_checkout, auto_checkout_hours, allow_multiple_checkins,
                      require_service_type, send_checkin_notifications))
            
            db.commit()
            flash('Check-in settings updated successfully!', 'success')
            
        except Exception as e:
            flash(f'Error updating settings: {e}', 'danger')
    
    # Get current settings
    settings = get_checkin_settings(org_id)
    service_types = get_service_types(org_id)
    
    return render_template('checkin_settings.html',
                         settings=settings,
                         service_types=service_types)


# Add these routes to your app.py file after the existing check-in routes

@app.route('/checkin/member_status/<membership_id>')
@require_login
def checkin_member_status(membership_id):
    """Get member status for check-in verification - AJAX endpoint"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            # Normalize membership ID format (handle both MBR/0001 and MBR-0001)
            normalized_id = membership_id.replace('/', '-')
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ? OR membership_id = ?', (membership_id, normalized_id))
            member_result = cursor.fetchone()
            if not member_result:
                return {
                    'success': False, 
                    'error': f'Member {membership_id} not found'
                }
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                return {
                    'success': False, 
                    'error': 'Organization not found'
                }
        
        # Normalize membership ID format (handle both MBR/0001 and MBR-0001)
        normalized_id = membership_id.replace('/', '-')
        
        # Get member details with all required information
        cursor.execute('''
            SELECT m.membership_id, m.name, m.email, m.phone, m.membership_type,
                   m.expiration_date, m.status, m.payment_status, m.photo_filename,
                   m.created_at, o.name as org_name
            FROM members m
            JOIN organizations o ON m.organization_id = o.id
            WHERE (m.membership_id = ? OR m.membership_id = ?) AND m.organization_id = ?
        ''', (membership_id, normalized_id, org_id))
        
        member_row = cursor.fetchone()
        if not member_row:
            return {
                'success': False, 
                'error': f'Member {membership_id} not found in your organization'
            }
        
        # Convert to dict for easier handling
        member = {
            'membership_id': member_row[0],
            'name': member_row[1],
            'email': member_row[2] or '',
            'phone': member_row[3] or '',
            'membership_type': member_row[4] or '',
            'expiration_date': member_row[5],
            'status': member_row[6],
            'payment_status': member_row[7] or 'Unknown',
            'photo_filename': member_row[8],
            'created_at': member_row[9],
            'org_name': member_row[10]
        }
        
        # Validation checks
        validation_errors = []
        
        # Check member status
        if member['status'] != 'active':
            validation_errors.append(f"Member status is '{member['status']}'. Only active members can check in.")
        
        # Check expiration
        days_until_expiry = None
        expiry_status = 'unknown'
        expiration_display = 'Not specified'
        
        if member['expiration_date']:
            try:
                exp_date = datetime.strptime(member['expiration_date'], '%Y-%m-%d').date()
                today = datetime.now().date()
                days_until_expiry = (exp_date - today).days
                
                if days_until_expiry < 0:
                    expiry_status = 'expired'
                    expiration_display = f"Expired {abs(days_until_expiry)} days ago"
                    validation_errors.append("Membership has expired. Please renew to check in.")
                elif days_until_expiry == 0:
                    expiry_status = 'expires_today'
                    expiration_display = "Expires today"
                elif days_until_expiry <= 7:
                    expiry_status = 'warning'
                    expiration_display = f"Expires in {days_until_expiry} days"
                else:
                    expiry_status = 'active'
                    expiration_display = f"Valid for {days_until_expiry} days"
                    
            except ValueError:
                expiry_status = 'invalid'
                expiration_display = 'Invalid date format'
                validation_errors.append("Invalid expiration date format.")
        
        # Get current check-in status
        checkin_status = is_member_checked_in(member['membership_id'], org_id)
        
        # Get prepaid balance
        prepaid_balance = get_prepaid_balance(member['membership_id'], org_id)
        if not prepaid_balance:
            prepaid_balance = {
                'current_balance': 0.0,
                'total_recharged': 0.0,
                'total_spent': 0.0,
                'total_bonus_earned': 0.0
            }
        
        # Format prepaid balance for display
        currency_symbol = get_currency_symbol()
        prepaid_display = {
            'current_balance': prepaid_balance['current_balance'],
            'formatted_balance': f"{currency_symbol}{prepaid_balance['current_balance']:.2f}",
            'total_recharged': prepaid_balance['total_recharged'],
            'total_spent': prepaid_balance['total_spent'],
            'total_bonus_earned': prepaid_balance['total_bonus_earned']
        }
        
        # Prepare member data for response
        member_data = {
            'membership_id': member['membership_id'],
            'name': member['name'],
            'email': member['email'],
            'phone': member['phone'],
            'membership_type': member['membership_type'],
            'expiration_date': member['expiration_date'],
            'status': member['status'],
            'payment_status': member['payment_status'],
            'photo_filename': member['photo_filename'],
            'photo_url': url_for('member_photo', membership_id=member['membership_id']) if member['photo_filename'] else url_for('static', filename='images/default-avatar.png'),
            'days_until_expiry': days_until_expiry,
            'expiry_status': expiry_status,
            'expiration_display': expiration_display
        }
        
        # Return response
        if validation_errors:
            return {
                'success': False,
                'error': '; '.join(validation_errors),
                'member': member_data,
                'checkin_status': checkin_status,
                'prepaid_balance': prepaid_display
            }
        else:
            return {
                'success': True,
                'member': member_data,
                'checkin_status': checkin_status,
                'prepaid_balance': prepaid_display
            }
            
    except Exception as e:
        print(f"Error in checkin_member_status: {e}")
        return {
            'success': False, 
            'error': f'Error checking member status: {str(e)}'
        }

@app.route('/checkin/process', methods=['POST'])
@require_login
def checkin_process():
    """Process check-in from scanner - AJAX endpoint"""
    try:
        data = request.get_json()
        if not data:
            return {'success': False, 'error': 'No data received'}
        
        membership_id = data.get('membership_id', '').strip()
        service_type = data.get('service_type', '').strip()
        location_id = data.get('location_id')
        notes = data.get('notes', '').strip()
        
        if not membership_id:
            return {'success': False, 'error': 'Membership ID is required'}
        
        # Normalize membership ID format
        membership_id = membership_id.replace('/', '-')
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                return {'success': False, 'error': 'Member not found'}
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                return {'success': False, 'error': 'Organization not found'}
        
        admin_user_id = session.get('user_id')
        
        # Process the check-in
        success, result = process_member_checkin(
            membership_id, org_id, service_type, notes, location_id, admin_user_id
        )
        
        if success:
            return {
                'success': True,
                'data': {
                    'message': f"✅ {result['member_name']} checked in successfully!",
                    'member_name': result['member_name'],
                    'service_type': result.get('service_type'),
                    'checkin_time': result.get('checkin_time'),
                    'checkin_id': result.get('checkin_id')
                }
            }
        else:
            return {'success': False, 'error': result}
            
    except Exception as e:
        print(f"Error in checkin_process: {e}")
        return {'success': False, 'error': f'Processing error: {str(e)}'}

@app.route('/checkin/checkout', methods=['POST'])
@require_login
def checkin_checkout():
    """Process check-out from scanner - AJAX endpoint"""
    try:
        data = request.get_json()
        if not data:
            return {'success': False, 'error': 'No data received'}
        
        membership_id = data.get('membership_id', '').strip()
        notes = data.get('notes', '').strip()
        
        if not membership_id:
            return {'success': False, 'error': 'Membership ID is required'}
        
        # Normalize membership ID format
        membership_id = membership_id.replace('/', '-')
        
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                return {'success': False, 'error': 'Member not found'}
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                return {'success': False, 'error': 'Organization not found'}
        
        # Process the check-out
        success, result = process_member_checkout(membership_id, org_id, notes)
        
        if success:
            return {
                'success': True,
                'data': {
                    'message': f"👋 {result.get('member_name', 'Member')} checked out successfully!",
                    'member_name': result.get('member_name'),
                    'checkout_time': result.get('checkout_time'),
                    'duration': result.get('duration')
                }
            }
        else:
            return {'success': False, 'error': result}
            
    except Exception as e:
        print(f"Error in checkin_checkout: {e}")
        return {'success': False, 'error': f'Checkout error: {str(e)}'}

@app.route('/checkin/quick_checkout/<membership_id>', methods=['POST'])
@require_login
@require_member_access
def quick_checkout(membership_id):
    """Quick checkout for member history page"""
    try:
        # Get organization_id - use member data for global admins, session for org admins
        if is_global_superadmin():
            # Global admin: get organization_id from member data
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
            member_result = cursor.fetchone()
            if not member_result:
                flash('Member not found.', 'danger')
                return redirect(url_for('member_checkin_history', membership_id=membership_id))
            org_id = member_result[0]
        else:
            # Org admin: use session organization_id
            org_id = session.get('organization_id')
            if not org_id:
                flash('Organization not found.', 'danger')
                return redirect(url_for('member_checkin_history', membership_id=membership_id))
        
        success, result = process_member_checkout(membership_id, org_id)
        
        if success:
            flash(f"✅ Member checked out successfully!", 'success')
        else:
            flash(f"❌ Checkout failed: {result}", 'danger')
            
    except Exception as e:
        flash(f"Error processing checkout: {e}", 'danger')
    
    return redirect(url_for('member_checkin_history', membership_id=membership_id))

# Updated helper functions with better error handling and member name support

def process_member_checkin(membership_id, organization_id, service_type=None, notes="", location_id=None, admin_user_id=None):
    """Enhanced process member check-in with better error handling"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get member details
        cursor.execute('''
            SELECT name, status, expiration_date FROM members
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, organization_id))
        
        member = cursor.fetchone()
        if not member:
            return False, "Member not found"
        
        name, status, expiration_date = member
        
        # Check member status
        if status != 'active':
            return False, f"Member status is {status}. Only active members can check in."
        
        # Check expiration
        if expiration_date:
            try:
                exp_date = datetime.strptime(expiration_date, '%Y-%m-%d').date()
                if exp_date < datetime.now().date():
                    return False, "Membership has expired. Please renew to check in."
            except ValueError:
                return False, "Invalid expiration date format."
        
        # Get settings
        settings = get_checkin_settings(organization_id)
        
        # Check if already checked in
        current_status = is_member_checked_in(membership_id, organization_id)
        if current_status['is_checked_in'] and not settings.get('allow_multiple_checkins', False):
            return False, f"Member is already checked in since {current_status['checkin_time']}"
        
        # Get current user ID if not provided
        if not admin_user_id:
            admin_user_id = session.get('user_id')
        
        # Process check-in
        cursor.execute('''
            INSERT INTO checkins (membership_id, organization_id, service_type, notes, admin_user_id, status, location_id)
            VALUES (?, ?, ?, ?, ?, 'checked_in', ?)
        ''', (membership_id, organization_id, service_type, notes, admin_user_id, location_id))
        
        checkin_id = cursor.lastrowid
        
        # Send notification if enabled
        if settings.get('send_checkin_notifications', True):
            send_checkin_notification(membership_id, organization_id, 'checkin', service_type)
        
        db.commit()
        
        return True, {
            'checkin_id': checkin_id,
            'member_name': name,
            'service_type': service_type,
            'checkin_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        print(f"Error processing checkin: {e}")
        return False, f"Check-in failed: {e}"

def process_member_checkout(membership_id, organization_id, notes=""):
    """Enhanced process member check-out with better error handling"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get member name
        cursor.execute('''
            SELECT name FROM members
            WHERE membership_id = ? AND organization_id = ?
        ''', (membership_id, organization_id))
        
        member_result = cursor.fetchone()
        member_name = member_result[0] if member_result else "Unknown Member"
        
        # Find active check-in
        cursor.execute('''
            SELECT id, checkin_time, service_type
            FROM checkins
            WHERE membership_id = ? AND organization_id = ? AND status = 'checked_in'
            ORDER BY checkin_time DESC
            LIMIT 1
        ''', (membership_id, organization_id))
        
        checkin = cursor.fetchone()
        if not checkin:
            return False, "No active check-in found for this member"
        
        checkin_id, checkin_time, service_type = checkin
        
        # Calculate duration
        try:
            checkin_dt = datetime.strptime(checkin_time, '%Y-%m-%d %H:%M:%S')
            duration_hours = (datetime.now() - checkin_dt).total_seconds() / 3600
            duration_text = f"{duration_hours:.1f} hours"
        except:
            duration_text = "Unknown"
        
        # Update check-in record
        cursor.execute('''
            UPDATE checkins
            SET checkout_time = CURRENT_TIMESTAMP, status = 'checked_out', notes = COALESCE(notes || '; ' || ?, notes, ?)
            WHERE id = ?
        ''', (notes, notes, checkin_id))
        
        # Send notification
        settings = get_checkin_settings(organization_id)
        if settings.get('send_checkin_notifications', True):
            send_checkin_notification(membership_id, organization_id, 'checkout', service_type)
        
        db.commit()
        
        return True, {
            'checkin_id': checkin_id,
            'member_name': member_name,
            'checkout_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'duration': duration_text
        }
        
    except Exception as e:
        print(f"Error processing checkout: {e}")
        return False, f"Check-out failed: {e}"

def can_access_organization_member(membership_id, organization_id):
    """Check if current user can access a specific member"""
    try:
        if is_global_superadmin() or is_global_admin():
            return True
        
        if is_org_superadmin():
            return get_user_organization_id() == organization_id
        
        # Regular users can only access members in their organization
        return get_user_organization_id() == organization_id
        
    except Exception:
        return False

# Add a function to get default dashboard data in case of errors
def default_dashboard_data():
    """Return default empty data for dashboard in case of errors"""
    return {
        'stats': {'total_members': 0, 'active_members': 0, 'expired_members': 0, 'paid_members': 0, 'unpaid_members': 0},
        'recent_payments': [],
        'recent_prepaid_transactions': [],
        'prepaid_analytics': {'total_balance': 0, 'total_recharged': 0, 'total_spent': 0, 'total_bonus': 0, 'active_cards': 0, 'recent_transactions': 0},
        'checkin_stats': {'todays_checkins': 0, 'currently_checked_in': 0, 'unique_visitors_today': 0},
        'expiring_memberships': [],
        'accessible_orgs': [],
        'selected_org_id': None,
        'is_global_superadmin': False,
        'is_org_superadmin': False,
        'total_members': 0,
        'active_members': 0,
        'expired_members': 0,
        'paid_members': 0,
        'unpaid_members': 0,
        'total_payments': 0,
        'expiring_soon': 0,
        'recent_members': [],
        'member_chart_labels': [],
        'member_chart_values': [],
        'payment_chart_labels': [],
        'payment_chart_values': []
    }

#=================================================================================================

if __name__ == "__main__":
    with app.app_context():
        if not init_db_safely():
            print("❌ Database initialization failed. Please check the errors above.")
            print("\n🔧 TROUBLESHOOTING:")
            print("1. Delete the 'database.db' file if it exists")
            print("2. Restart the application")
            print("3. Check file permissions in the directory")
            
            # Ask user if they want to delete the database file
            if os.path.exists(DATABASE):
                response = input(f"\n⚠️  Delete corrupted database file '{DATABASE}'? (y/N): ")
                if response.lower() in ['y', 'yes']:
                    try:
                        os.remove(DATABASE)
                        print(f"✅ Deleted {DATABASE}")
                        print("🔄 Please restart the application now.")
                    except Exception as e:
                        print(f"❌ Failed to delete database: {e}")
            exit(1)

    # Initialize subscription packages within app context
    try:
        with app.app_context():
            initialize_subscription_packages()
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize subscription packages: {e}")
    
    print("\n" + "="*60)
    print("🚀 MemberSync Flask Application Starting...")
    print("="*60)
    print("📱 Access your application at: http://localhost:5000")
    print("🔐 Default global admin login:")
    print("   Username: globaladmin")
    print("   Password: ChangeMe123!")
    print("="*60)


# ============================================================================
# API ROUTES FOR MEMBER APPLICATION
# ============================================================================

def add_member_password_column():
    """Migration: Add password_hash to members table for member app login"""
    try:
        with sqlite3.connect(DATABASE, timeout=20.0) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(members)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'password_hash' not in columns:
                print("🔧 Adding 'password_hash' column to members table...")
                cursor.execute('ALTER TABLE members ADD COLUMN password_hash TEXT')
                conn.commit()
                print("✅ Password column added to members table")
            return True
    except Exception as e:
        print(f"❌ Error adding password column: {e}")
        return False

@app.route('/api/v1/login', methods=['POST'])
def api_member_login():
    """API Endpoint for Member Login"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        identifier = data.get('identifier', '').strip() # Can be email, phone, or membership_id
        password = data.get('password', '')
        
        if not identifier or not password:
            return jsonify({'success': False, 'error': 'Identifier and password required'}), 400
            
        db = get_db()
        cursor = db.cursor()
        
        # Find member by email, phone, or membership_id
        cursor.execute('''
            SELECT membership_id, name, email, phone, password_hash, status, organization_id, photo_filename
            FROM members 
            WHERE email = ? OR phone = ? OR membership_id = ?
        ''', (identifier, identifier, identifier))
        
        member = cursor.fetchone()
        
        if not member:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
            
        # Check password
        stored_hash = member['password_hash']
        if not stored_hash or not check_password_hash(stored_hash, password):
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
            
        if member['status'] != 'active':
            return jsonify({'success': False, 'error': 'Account is not active'}), 403

        # Return member data (In a real app, you would return a JWT token here)
        return jsonify({
            'success': True,
            'member': {
                'membership_id': member['membership_id'],
                'name': member['name'],
                'email': member['email'],
                'phone': member['phone'],
                'organization_id': member['organization_id'],
                'photo_url': url_for('member_photo', membership_id=member['membership_id'], _external=True) if member['photo_filename'] else None
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/register', methods=['POST'])
def api_member_register():
    """API Endpoint for Member Self-Registration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        password = data.get('password', '')
        organization_id = data.get('organization_id', 1) # Default to org 1 if not specified
        membership_type = data.get('membership_type', 'Standard')
        
        if not all([name, email, phone, password]):
            return jsonify({'success': False, 'error': 'Name, email, phone, and password are required'}), 400
            
        db = get_db()
        cursor = db.cursor()
        
        # Check if email or phone already exists
        cursor.execute('SELECT id FROM members WHERE email = ? OR phone = ?', (email, phone))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'Email or phone already registered'}), 409
            
        # Generate ID and Hash Password
        membership_id = generate_unique_membership_id(organization_id, "MBR")
        password_hash = generate_password_hash(password)
        
        # Insert Member
        cursor.execute('''
            INSERT INTO members (membership_id, name, email, phone, password_hash, 
                               membership_type, organization_id, status, created_at, payment_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', datetime('now'), 'Unpaid')
        ''', (membership_id, name, email, phone, password_hash, membership_type, organization_id))
        
        db.commit()
        
        # Generate QR Code (Optional but good for consistency)
        try:
            qr_img = qrcode.make(membership_id)
            qr_dir = 'static/qr_codes'
            os.makedirs(qr_dir, exist_ok=True)
            qr_img.save(f'{qr_dir}/{membership_id}.png')
        except Exception as e:
            print(f"QR Gen Error: {e}")

        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'member': {
                'membership_id': membership_id,
                'name': name,
                'email': email,
                'organization_id': organization_id
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/set-password', methods=['POST'])
def api_set_password():
    """Helper endpoint to set password for existing members (since they don't have one)"""
    try:
        data = request.get_json()
        membership_id = data.get('membership_id')
        password = data.get('password')
        
        if not membership_id or not password:
            return jsonify({'success': False, 'error': 'Missing data'}), 400
            
        db = get_db()
        cursor = db.cursor()
        
        password_hash = generate_password_hash(password)
        
        cursor.execute('UPDATE members SET password_hash = ? WHERE membership_id = ?', 
                      (password_hash, membership_id))
        db.commit()
        
        return jsonify({'success': True, 'message': 'Password set successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/members/<membership_id>/profile', methods=['GET'])
def api_get_profile(membership_id):
    """Get member profile data"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT m.membership_id, m.name, m.email, m.phone, m.membership_type, 
                   m.expiration_date, m.status, m.photo_filename, o.name as org_name
            FROM members m
            JOIN organizations o ON m.organization_id = o.id
            WHERE m.membership_id = ?
        ''', (membership_id,))
        
        member = cursor.fetchone()
        if not member:
            return jsonify({'success': False, 'error': 'Member not found'}), 404
            
        return jsonify({
            'success': True,
            'data': {
                'membership_id': member['membership_id'],
                'name': member['name'],
                'email': member['email'],
                'phone': member['phone'],
                'type': member['membership_type'],
                'expiration': member['expiration_date'],
                'status': member['status'],
                'organization': member['org_name'],
                'photo_url': url_for('member_photo', membership_id=member['membership_id'], _external=True) if member['photo_filename'] else None
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/members/<membership_id>/prepaid', methods=['GET'])
def api_get_prepaid(membership_id):
    """Get prepaid balance and recent transactions"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get organization ID for this member
        cursor.execute('SELECT organization_id FROM members WHERE membership_id = ?', (membership_id,))
        result = cursor.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Member not found'}), 404
        org_id = result[0]
        
        # Get Balance
        balance_info = get_prepaid_balance(membership_id, org_id)
        
        # Get Transactions
        cursor.execute('''
            SELECT transaction_type, amount, balance_after, description, transaction_date
            FROM prepaid_transactions
            WHERE membership_id = ? AND organization_id = ?
            ORDER BY transaction_date DESC LIMIT 20
        ''', (membership_id, org_id))
        
        transactions = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'balance': balance_info,
            'transactions': transactions
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/v1/members/<membership_id>/checkins', methods=['GET'])
def api_get_checkins(membership_id):
    """Get check-in history"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT checkin_time, checkout_time, service_type, status
            FROM checkins
            WHERE membership_id = ?
            ORDER BY checkin_time DESC LIMIT 20
        ''', (membership_id,))
        
        history = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'history': history
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Ensure members have password column for API
    add_member_password_column()
    
    # Seed default locations
    seed_default_locations()
    
    app.run(debug=True, host='0.0.0.0', port=5000)
