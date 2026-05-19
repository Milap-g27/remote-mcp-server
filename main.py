from fastmcp import FastMCP
import os
import sqlite3
import tempfile

# Use temporary directory which should be writable
TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"Database path: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")

def init_db():
    try:
        # Create database with explicit write permissions
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")  # Better for concurrent access
            c.execute("""
                CREATE TABLE IF NOT EXISTS expenses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT '',
                    type TEXT DEFAULT 'expense' CHECK(type IN ('expense', 'credit'))
                )
            """)
            
            # Migrate existing table if type column doesn't exist
            cursor = c.execute("PRAGMA table_info(expenses)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'type' not in columns:
                print("Migrating database: adding type column...")
                c.execute("ALTER TABLE expenses ADD COLUMN type TEXT DEFAULT 'expense' CHECK(type IN ('expense', 'credit'))")
                print("Migration complete")
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS categories(
                    name TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
            """)
            # Test write access
            c.execute("INSERT OR IGNORE INTO expenses(date, amount, category) VALUES ('2000-01-01', 0, 'test')")
            c.execute("DELETE FROM expenses WHERE category = 'test'")
            print("Database initialized successfully with write access")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

def ensure_category_exists(category: str):
    """Ensure a category exists in the database, create if it doesn't."""
    try:
        from datetime import datetime
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                "INSERT OR IGNORE INTO categories(name, created_at) VALUES (?, ?)",
                (category, datetime.now().isoformat())
            )
            c.commit()
    except Exception as e:
        print(f"Error ensuring category exists: {e}")

init_db()

@mcp.tool()
async def add_expense(date: str, amount: float, category: str, subcategory: str = "", note: str = "") -> dict:
    """Add a new expense entry to the database.
    
    Args:
        date: Expense date in YYYY-MM-DD format
        amount: Expense amount
        category: Expense category (will be auto-created if doesn't exist)
        subcategory: Optional subcategory
        note: Optional note/description
        
    Returns:
        Dict with status, id (if successful), and message
    """
    try:
        # Ensure category exists
        ensure_category_exists(category)
        
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note, type) VALUES (?,?,?,?,?,?)",
                (date, amount, category, subcategory, note, 'expense')
            )
            expense_id = cur.lastrowid
            c.commit()  # Explicit commit
            return {"status": "success", "id": expense_id, "message": "Expense added successfully"}
    except sqlite3.OperationalError as e:
        if "readonly" in str(e).lower():
            return {"status": "error", "message": "Database is in read-only mode. Check file permissions."}
        return {"status": "error", "message": f"Database error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}

@mcp.tool()
async def add_credit(date: str, amount: float, category: str, subcategory: str = "", note: str = "") -> dict:
    """Add a new credit/income entry to the database.
    
    Args:
        date: Credit date in YYYY-MM-DD format
        amount: Credit amount
        category: Credit category (e.g., Salary, Freelance, Investment, etc.)
        subcategory: Optional subcategory
        note: Optional note/description
        
    Returns:
        Dict with status, id (if successful), and message
    """
    try:
        # Ensure category exists
        ensure_category_exists(category)
        
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note, type) VALUES (?,?,?,?,?,?)",
                (date, amount, category, subcategory, note, 'credit')
            )
            credit_id = cur.lastrowid
            c.commit()  # Explicit commit
            return {"status": "success", "id": credit_id, "message": "Credit added successfully"}
    except sqlite3.OperationalError as e:
        if "readonly" in str(e).lower():
            return {"status": "error", "message": "Database is in read-only mode. Check file permissions."}
        return {"status": "error", "message": f"Database error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}
    
@mcp.tool()
async def list_expenses(start_date: str, end_date: str, transaction_type: str = "all") -> list[dict]:
    """List expense/credit entries within an inclusive date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        transaction_type: Type filter - 'expense', 'credit', or 'all' (default: 'all')
        
    Returns:
        List of transaction dictionaries
    """
    try:
        with sqlite3.connect(DB_PATH) as c:
            query = """
                SELECT id, date, amount, category, subcategory, note, type
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """
            params = [start_date, end_date]
            
            if transaction_type in ['expense', 'credit']:
                query += " AND type = ?"
                params.append(transaction_type)
            
            query += " ORDER BY date DESC, id DESC"
            
            cur = c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        return [{"status": "error", "message": f"Error listing expenses: {str(e)}"}]

@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str | None = None, transaction_type: str = "all") -> list[dict]:
    """Summarize expenses/credits by category within an inclusive date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        category: Optional category filter
        transaction_type: Type filter - 'expense', 'credit', or 'all' (default: 'all')
        
    Returns:
        List of summary dictionaries by category
    """
    try:
        with sqlite3.connect(DB_PATH) as c:
            query = """
                SELECT category, type, SUM(amount) AS total_amount, COUNT(*) as count
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)
            
            if transaction_type in ['expense', 'credit']:
                query += " AND type = ?"
                params.append(transaction_type)

            query += " GROUP BY category, type ORDER BY total_amount DESC"

            cur = c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        return [{"status": "error", "message": f"Error summarizing expenses: {str(e)}"}]

@mcp.tool()
async def get_balance(start_date: str, end_date: str) -> dict:
    """Calculate net balance (credits - expenses) for a date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Dict with total_credits, total_expenses, and net_balance
    """
    try:
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                """
                SELECT 
                    COALESCE(SUM(CASE WHEN type = 'credit' THEN amount ELSE 0 END), 0) as total_credits,
                    COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) as total_expenses
                FROM expenses
                WHERE date BETWEEN ? AND ?
                """,
                (start_date, end_date)
            )
            result = cur.fetchone()
            total_credits = result[0]
            total_expenses = result[1]
            net_balance = total_credits - total_expenses
            
            return {
                "start_date": start_date,
                "end_date": end_date,
                "total_credits": total_credits,
                "total_expenses": total_expenses,
                "net_balance": net_balance
            }
    except Exception as e:
        return {"status": "error", "message": f"Error calculating balance: {str(e)}"}

@mcp.resource("expense://categories", mime_type="application/json")
async def categories() -> str:
    """Get available expense categories."""
    try:
        # Provide default categories if file doesn't exist
        default_categories = {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other"
            ]
        }
        
        try:
            with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            import json
            return json.dumps(default_categories, indent=2)
    except Exception as e:
        return f'{{"error": "Could not load categories: {str(e)}"}}'

@mcp.tool()
async def list_all_categories() -> list[str]:
    """List all categories that have been used (both predefined and auto-created).
    
    Returns:
        List of all category names
    """
    try:
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute("SELECT DISTINCT category FROM expenses ORDER BY category")
            return [row[0] for row in cur.fetchall()]
    except Exception as e:
        return [f"Error: {str(e)}"]

# Start the server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=port
    )