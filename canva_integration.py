"""
CANVA Integration for MemberSync
Allows users to design cards using CANVA templates and API
"""

import os
import requests
from flask import request, redirect, url_for, session, jsonify
import sqlite3
from functools import wraps

# CANVA API Configuration
CANVA_API_BASE = "https://api.canva.com/rest/v1"
CANVA_AUTH_URL = "https://www.canva.com/api/oauth"

def get_canva_config():
    """Get CANVA configuration from environment"""
    return {
        'client_id': os.getenv('CANVA_CLIENT_ID'),
        'client_secret': os.getenv('CANVA_CLIENT_SECRET'),
        'redirect_uri': os.getenv('CANVA_REDIRECT_URI', 'https://memberssync.com/canva/callback'),
        'scope': 'design:edit design:read design:upload'
    }

def canva_oauth_url():
    """Generate CANVA OAuth URL"""
    config = get_canva_config()
    if not config['client_id']:
        return None
    
    params = {
        'client_id': config['client_id'],
        'redirect_uri': config['redirect_uri'],
        'response_type': 'code',
        'scope': config['scope'],
        'state': 'membersync_integration'
    }
    
    auth_url = f"{CANVA_AUTH_URL}/authorize?" + "&".join([f"{k}={v}" for k, v in params.items()])
    return auth_url

@app.route('/canva/connect')
@require_login
def canva_connect():
    """Connect to CANVA"""
    auth_url = canva_oauth_url()
    if not auth_url:
        flash('CANVA integration not configured', 'error')
        return redirect(url_for('settings'))
    
    return redirect(auth_url)

@app.route('/canva/callback')
def canva_callback():
    """Handle CANVA OAuth callback"""
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code or state != 'membersync_integration':
        flash('Invalid CANVA authorization', 'error')
        return redirect(url_for('settings'))
    
    # Exchange code for access token
    config = get_canva_config()
    token_data = exchange_canva_code(code, config)
    
    if token_data.get('access_token'):
        # Store CANVA access token for user
        store_canva_token(session.get('user_id'), token_data['access_token'])
        flash('CANVA connected successfully!', 'success')
        return redirect(url_for('card_designer'))
    
    flash('Failed to connect CANVA', 'error')
    return redirect(url_for('settings'))

def exchange_canva_code(code, config):
    """Exchange authorization code for access token"""
    try:
        response = requests.post(f"{CANVA_API_BASE}/oauth/token", data={
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'redirect_uri': config['redirect_uri'],
            'grant_type': 'authorization_code'
        })
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
            
    except Exception as e:
        print(f"CANVA token exchange error: {e}")
        return None

def store_canva_token(user_id, access_token):
    """Store CANVA access token for user"""
    try:
        db = sqlite3.connect('database.db')
        cursor = db.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO canva_tokens (user_id, access_token, created_at)
            VALUES (?, ?, ?)
        ''', (user_id, access_token))
        
        db.commit()
        return True
        
    except Exception as e:
        print(f"Error storing CANVA token: {e}")
        return False

def get_user_canva_token(user_id):
    """Get user's CANVA access token"""
    try:
        db = sqlite3.connect('database.db')
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT access_token FROM canva_tokens WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        return result[0] if result else None
        
    except Exception as e:
        print(f"Error getting CANVA token: {e}")
        return None

# Create canva_tokens table
def create_canva_tokens_table():
    """Create table for storing CANVA tokens"""
    try:
        db = sqlite3.connect('database.db')
        cursor = db.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS canva_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                access_token TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        db.commit()
        return True
        
    except Exception as e:
        print(f"Error creating CANVA tokens table: {e}")
        return False

# Add to your app startup
# In init_db() or main():
create_canva_tokens_table()
