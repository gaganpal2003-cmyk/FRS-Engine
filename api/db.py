import os
import sqlite3
import hashlib
import json
import logging
import secrets
from pathlib import Path
from api.config import (
    DB_ENGINE,
    DB_HOST,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    SQLITE_DB_PATH,
    BASE_DIR
)

logger = logging.getLogger("frs_api.db")


class DatabaseManager:
    def __init__(self):
        self.engine_type = DB_ENGINE
        self.host = DB_HOST
        self.user = DB_USER
        self.password = DB_PASSWORD
        self.database = DB_NAME
        self.sqlite_path = SQLITE_DB_PATH
        self.is_sqlite = (self.engine_type == "sqlite")
        self.pool = None
        self._init_connection()

    def _init_connection(self):
        if self.is_sqlite:
            self._setup_sqlite()
            return

        # Attempt MySQL connection if configured
        try:
            import mysql.connector
            from mysql.connector import pooling
            self.pool = pooling.MySQLConnectionPool(
                pool_name="frs_pool",
                pool_size=5,
                pool_reset_session=True,
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            # Test connection
            conn = self.pool.get_connection()
            conn.close()
            self.is_sqlite = False
            logger.info(f"Connected to MySQL database at {self.host}:{self.database}")
        except Exception as e:
            logger.warning(
                f"MySQL connection to '{self.host}' failed ({e}). "
                "Automatically falling back to built-in SQLite engine."
            )
            self.pool = None
            self._setup_sqlite()

    def _setup_sqlite(self):
        self.is_sqlite = True
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.sqlite_path), check_same_thread=False, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.close()
        logger.info(f"Using built-in SQLite database at {self.sqlite_path}")

    def get_connection(self):
        if self.is_sqlite:
            conn = sqlite3.connect(str(self.sqlite_path), check_same_thread=False, timeout=30)
            conn.execute("PRAGMA foreign_keys=ON;")
            return conn
        if self.pool:
            try:
                return self.pool.get_connection()
            except Exception:
                pass
        import mysql.connector
        return mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database
        )

    def _format_query(self, query: str) -> str:
        if self.is_sqlite:
            # Replace %s parameter placeholder with SQLite ?
            query = query.replace("%s", "?")
            # Replace MySQL specific syntax
            query = query.replace("INSERT IGNORE INTO", "INSERT OR IGNORE INTO")
        return query

    def execute(self, query, params=None):
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            formatted_query = self._format_query(query)
            cursor.execute(formatted_query, params or ())
            conn.commit()
            last_id = cursor.lastrowid
            cursor.close()
            return last_id
        except Exception as e:
            logger.error(f"DB execute error: {e} | Query: {query}")
            raise
        finally:
            if conn:
                conn.close()

    def fetch_all(self, query, params=None, as_dict=False):
        conn = None
        try:
            conn = self.get_connection()
            formatted_query = self._format_query(query)
            if self.is_sqlite:
                if as_dict:
                    conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(formatted_query, params or ())
                rows = cursor.fetchall()
                if as_dict:
                    result = [dict(r) for r in rows]
                else:
                    result = [tuple(r) for r in rows]
            else:
                cursor = conn.cursor(dictionary=as_dict)
                cursor.execute(formatted_query, params or ())
                result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            logger.error(f"DB fetch_all error: {e} | Query: {query}")
            raise
        finally:
            if conn:
                conn.close()

    def fetch_one(self, query, params=None, as_dict=False):
        conn = None
        try:
            conn = self.get_connection()
            formatted_query = self._format_query(query)
            if self.is_sqlite:
                if as_dict:
                    conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(formatted_query, params or ())
                row = cursor.fetchone()
                if row is None:
                    result = None
                elif as_dict:
                    result = dict(row)
                else:
                    result = tuple(row)
            else:
                cursor = conn.cursor(dictionary=as_dict)
                cursor.execute(formatted_query, params or ())
                result = cursor.fetchone()
            cursor.close()
            return result
        except Exception as e:
            logger.error(f"DB fetch_one error: {e} | Query: {query}")
            raise
        finally:
            if conn:
                conn.close()

    def initialize_database(self):
        """Creates necessary API tables and syncs default tenant."""
        logger.info(f"Ensuring API multi-tenant tables exist ({'SQLite' if self.is_sqlite else 'MySQL'})...")

        if self.is_sqlite:
            self._create_tables_sqlite()
        else:
            self._create_tables_mysql()

        # Check if any client exists; if not, create default client
        clients = self.fetch_all("SELECT client_id, api_key_prefix FROM api_clients LIMIT 1;")
        if not clients:
            self._create_default_client_and_sync()

    def _create_tables_sqlite(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_clients (
                client_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                api_key_hash TEXT NOT NULL UNIQUE,
                api_key_prefix TEXT NOT NULL,
                rate_limit_per_min INTEGER DEFAULT 180,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_client_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                person_identifier TEXT NOT NULL,
                name TEXT NOT NULL,
                metadata TEXT NULL,
                is_blacklist INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES api_clients(client_id) ON DELETE CASCADE,
                UNIQUE(client_id, person_identifier)
            );
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_client_faces (
                face_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                identity_id INTEGER NOT NULL,
                face_encoding TEXT NOT NULL,
                face_image BLOB NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES api_clients(client_id) ON DELETE CASCADE,
                FOREIGN KEY (identity_id) REFERENCES api_client_identities(id) ON DELETE CASCADE
            );
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_recognition_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                matched_identity_id INTEGER NULL,
                confidence_score REAL NULL,
                processing_time_ms REAL NOT NULL,
                request_ip TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES api_clients(client_id) ON DELETE CASCADE
            );
        """)

    def _create_tables_mysql(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_clients (
                client_id INT AUTO_INCREMENT PRIMARY KEY,
                client_name VARCHAR(120) NOT NULL,
                api_key_hash VARCHAR(64) NOT NULL UNIQUE,
                api_key_prefix VARCHAR(16) NOT NULL,
                rate_limit_per_min INT DEFAULT 180,
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB;
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_client_identities (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                person_identifier VARCHAR(100) NOT NULL,
                name VARCHAR(150) NOT NULL,
                metadata JSON NULL,
                is_blacklist BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES api_clients(client_id) ON DELETE CASCADE,
                UNIQUE KEY uq_client_person (client_id, person_identifier)
            ) ENGINE=InnoDB;
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_client_faces (
                face_id INT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                identity_id INT NOT NULL,
                face_encoding LONGTEXT NOT NULL,
                face_image LONGBLOB NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES api_clients(client_id) ON DELETE CASCADE,
                FOREIGN KEY (identity_id) REFERENCES api_client_identities(id) ON DELETE CASCADE
            ) ENGINE=InnoDB;
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS api_recognition_logs (
                log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                client_id INT NOT NULL,
                matched_identity_id INT NULL,
                confidence_score FLOAT NULL,
                processing_time_ms FLOAT NOT NULL,
                request_ip VARCHAR(64) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES api_clients(client_id) ON DELETE CASCADE
            ) ENGINE=InnoDB;
        """)

    def _create_default_client_and_sync(self):
        """Creates the initial default client and imports existing desktop CairoFRS identities."""
        raw_token = secrets.token_hex(20)
        api_key = f"frs_live_{raw_token}"
        key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        key_prefix = api_key[:12]

        client_id = self.execute("""
            INSERT INTO api_clients (client_name, api_key_hash, api_key_prefix, rate_limit_per_min, is_active)
            VALUES (%s, %s, %s, %s, %s);
        """, ("Default Enterprise Client", key_hash, key_prefix, 300, 1 if self.is_sqlite else True))

        logger.info(f"Created default API Client ID: {client_id}")

        # Save default API key to a file for convenience
        key_file = BASE_DIR / ".default_api_key.txt"
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(f"Default Client ID: {client_id}\n")
            f.write(f"Client Name: Default Enterprise Client\n")
            f.write(f"API Key: {api_key}\n")
            f.write(f"Created At: {__import__('datetime').datetime.now().isoformat()}\n")

        print("\n" + "=" * 65)
        print(" [API INITIALIZATION] New Master Client Created!")
        print(f" Client ID : {client_id}")
        print(f" API Key   : {api_key}")
        print(f" Engine    : {'Built-in SQLite' if self.is_sqlite else 'MySQL'}")
        print(f" Saved to  : {key_file}")
        print("=" * 65 + "\n")

        # Now migrate existing identities from cairo_employee_identity if present (MySQL only)
        if not self.is_sqlite:
            try:
                existing_employees = self.fetch_all("""
                    SELECT id, name, employee_id, gender, DOB, mobile_number, job_profile, is_blacklist
                    FROM cairo_employee_identity;
                """, as_dict=True)

                if existing_employees:
                    logger.info(f"Syncing {len(existing_employees)} existing identities to Client {client_id}...")
                    for emp in existing_employees:
                        person_id = emp['employee_id'] or f"EMP_{emp['id']}"
                        metadata = json.dumps({
                            "gender": emp.get("gender"),
                            "dob": emp.get("DOB"),
                            "mobile": emp.get("mobile_number"),
                            "job_profile": emp.get("job_profile")
                        })
                        new_identity_id = self.execute("""
                            INSERT IGNORE INTO api_client_identities 
                            (client_id, person_identifier, name, metadata, is_blacklist)
                            VALUES (%s, %s, %s, %s, %s);
                        """, (client_id, person_id, emp['name'], metadata, bool(emp.get('is_blacklist', 0))))

                        if not new_identity_id:
                            row = self.fetch_one(
                                "SELECT id FROM api_client_identities WHERE client_id=%s AND person_identifier=%s",
                                (client_id, person_id)
                            )
                            new_identity_id = row[0] if row else None

                        if new_identity_id:
                            emp_faces = self.fetch_all("""
                                SELECT face_encoding, face_image 
                                FROM cairo_employee_faces 
                                WHERE employee_identity_id = %s;
                            """, (emp['id'],), as_dict=True)

                            for f in emp_faces:
                                if f.get("face_encoding"):
                                    self.execute("""
                                        INSERT INTO api_client_faces 
                                        (client_id, identity_id, face_encoding, face_image)
                                        VALUES (%s, %s, %s, %s);
                                    """, (client_id, new_identity_id, f["face_encoding"], f.get("face_image")))

                    logger.info(f"Successfully synced existing desktop identities to default client {client_id}!")
            except Exception as e:
                logger.warning(f"Could not auto-sync old employee identities: {e}")


# Singleton instance
db_manager = DatabaseManager()
