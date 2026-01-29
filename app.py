import os
import json
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = 'readscape-secret-key-2024'
app.config['BOOKS_STORAGE'] = 'books_storage'
app.config['COVERS_STORAGE'] = 'covers'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Database configuration
DB_CONFIG = {
    'host': os.getenv('MYSQLHOST'),
    'user': os.getenv('MYSQLUSER'),
    'password': os.getenv('MYSQLPASSWORD'),
    'database': os.getenv('MYSQLDATABASE'),
    'port': int(os.getenv('MYSQLPORT', 3306))
}

def get_db_connection():
    print("DB_CONFIG:", DB_CONFIG)
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        print("✅ Database connected successfully")
        return connection
    except Error as e:
        print(f"❌ Database connection error: {e}")
        return None


def token_required(f):
    """Decorator for token-based authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Token is missing!'}), 401
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        # Simple token validation (in production, use JWT)
        try:
            user_id = int(token)
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user:
                return jsonify({'message': 'Invalid token!'}), 401
            
            request.user_id = user_id
        except:
            return jsonify({'message': 'Invalid token!'}), 401
        
        return f(*args, **kwargs)
    return decorated

@app.route('/covers/<path:filename>')
def get_cover_image(filename):
    return send_from_directory(app.config['COVERS_STORAGE'], filename)

@app.route('/register', methods=['POST'])
def register():
    """Register new user"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'message': 'Username and password required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'message': 'Username already exists'}), 400
        
        # Insert new user
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, password)
        )
        user_id = cursor.lastrowid
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': 'User created successfully',
            'user_id': user_id
        }), 201
        
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    """User login"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'message': 'Username and password required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute(
            "SELECT * FROM users WHERE username = %s AND password = %s",
            (username, password)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user:
            # Use user ID as simple token (in production, use JWT)
            token = str(user['id'])
            return jsonify({
                'token': token,
                'user': user
            }), 200
        else:
            return jsonify({'message': 'Invalid credentials'}), 401
            
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/books', methods=['GET'])
@token_required
def get_books():
    try:
        category = request.args.get('category')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if category:
            cursor.execute(
                "SELECT * FROM books WHERE category = %s ORDER BY title",
                (category,)
            )
        else:
            cursor.execute("SELECT * FROM books ORDER BY title")

        books = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify(books), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/books/<int:book_id>/content', methods=['GET'])
@token_required
def get_book_content(book_id):
    """Get book content from file"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT file_name FROM books WHERE id = %s", (book_id,))
        book = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not book:
            return jsonify({'message': 'Book not found'}), 404
        
        file_path = os.path.join(app.config['BOOKS_STORAGE'], book['file_name'])
        
        if not os.path.exists(file_path):
            return jsonify({'message': 'Book file not found'}), 404
        
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        return content, 200
        
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/save-book', methods=['POST'])
@token_required
def save_book():
    """Save book to user's library"""
    try:
        data = request.get_json()
        book_id = data.get('book_id')
        user_id = request.user_id
        
        if not book_id:
            return jsonify({'message': 'Book ID required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if book exists
        cursor.execute("SELECT id FROM books WHERE id = %s", (book_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'message': 'Book not found'}), 404
        
        # Check if already saved
        cursor.execute(
            "SELECT id FROM saved_books WHERE user_id = %s AND book_id = %s",
            (user_id, book_id)
        )
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'message': 'Book already saved'}), 400
        
        # Save book
        cursor.execute(
            "INSERT INTO saved_books (user_id, book_id, timestamp) VALUES (%s, %s, %s)",
            (user_id, book_id, datetime.now())
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Book saved successfully'}), 201
        
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/saved-books', methods=['GET'])
@token_required
def get_saved_books():
    try:
        user_id = request.user_id
        category = request.args.get('category')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if category:
            cursor.execute("""
                SELECT b.* FROM books b
                INNER JOIN saved_books sb ON b.id = sb.book_id
                WHERE sb.user_id = %s AND b.category = %s
                ORDER BY sb.timestamp DESC
            """, (user_id, category))
        else:
            cursor.execute("""
                SELECT b.* FROM books b
                INNER JOIN saved_books sb ON b.id = sb.book_id
                WHERE sb.user_id = %s
                ORDER BY sb.timestamp DESC
            """, (user_id,))

        books = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify(books), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500
    
@app.route('/saved-books/<int:book_id>', methods=['DELETE'])
@token_required
def remove_saved_book(book_id):
    """Remove book from user's library"""
    try:
        user_id = request.user_id

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM saved_books WHERE user_id = %s AND book_id = %s",
            (user_id, book_id)
        )

        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'message': 'Book not found in library'}), 404

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'message': 'Book removed successfully'}), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/user/profile', methods=['PUT'])
@token_required
def update_profile():
    """Update user profile"""
    try:
        user_id = request.user_id
        data = request.get_json()
        
        bio = data.get('bio')
        instagram = data.get('instagram')
        facebook = data.get('facebook')
        tiktok = data.get('tiktok')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users 
            SET bio = %s, instagram = %s, facebook = %s, tiktok = %s
            WHERE id = %s
        """, (bio, instagram, facebook, tiktok, user_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Profile updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

