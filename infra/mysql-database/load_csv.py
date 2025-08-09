#!/usr/bin/env python3
"""
Script to load health.csv data into MySQL database.
This script connects to a MySQL database and loads data from health.csv file.
"""

import os
import pandas as pd
import mysql.connector
from mysql.connector import Error
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': "3306",
    'user': 'root',
    'password': '',  # Empty password as per configuration
    'database': 'health_data'  # Database will be created if it doesn't exist
}

# CSV file path
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'health.csv')

def create_database_if_not_exists(connection):
    """Create the database if it doesn't exist."""
    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        logger.info(f"Database '{DB_CONFIG['database']}' created or already exists.")
    except Error as e:
        logger.error(f"Error creating database: {e}")
        raise

def create_table_if_not_exists(connection):
    """Create the table if it doesn't exist."""
    try:
        cursor = connection.cursor()
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        # Create table based on CSV structure
        create_table_query = """
        CREATE TABLE IF NOT EXISTS health_disparities (
            id INT AUTO_INCREMENT PRIMARY KEY,
            edition VARCHAR(10),
            report_type VARCHAR(100),
            measure_name VARCHAR(100),
            state_name VARCHAR(50),
            subpopulation VARCHAR(100),
            value FLOAT,
            lower_ci FLOAT,
            upper_ci FLOAT,
            source VARCHAR(255),
            source_date VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_table_query)
        logger.info("Table 'health_disparities' created or already exists.")
    except Error as e:
        logger.error(f"Error creating table: {e}")
        raise

def load_data_from_csv(connection):
    """Load data from CSV file into the database."""
    try:
        # Read CSV file
        logger.info(f"Reading CSV file: {CSV_FILE}")
        df = pd.read_csv(CSV_FILE)

        # Replace NaN with None, which is SQL's NULL
        df = df.astype(object).where(df.notna(), None)

        # Use database
        cursor = connection.cursor()
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        # Insert data in batches
        batch_size = 1000
        total_rows = len(df)
        
        logger.info(f"Starting to load {total_rows} rows into database")
        
        for i in range(0, total_rows, batch_size):
            batch = df.iloc[i:i+batch_size]
            
            # Prepare values for insertion
            # This par is unnecessary but is more like a placeholder for future data manipulations.
            # The none values check or correction is at the beginning of the 'try'
            # but the main objective of this script is upload data into mysql database
            values = []
            for _, row in batch.iterrows():
                # Handle NaN values
                # value = row['value'] if pd.notna(row['value']) else None
                # lower_ci = row['lower_ci'] if pd.notna(row['lower_ci']) else None
                # upper_ci = row['upper_ci'] if pd.notna(row['upper_ci']) else None

                values.append((
                    row['edition'],
                    row['report_type'],
                    row['measure_name'],
                    row['state_name'],
                    row['subpopulation'],
                    row['value'],
                    row['lower_ci'],
                    row['upper_ci'],
                    row['source'],
                    row['source_date']
                ))
            
            # Insert batch
            insert_query = """
            INSERT INTO health_disparities 
            (edition, report_type, measure_name, state_name, subpopulation, 
             value, lower_ci, upper_ci, source, source_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(insert_query, values)
            connection.commit()
            
            logger.info(f"Inserted rows {i} to {min(i+batch_size, total_rows)} of {total_rows}")
        
        logger.info("Data loading completed successfully")
    except Error as e:
        logger.error(f"Error loading data: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

def main():
    """Main function to execute the data loading process."""
    connection = None
    try:
        # Connect to MySQL server
        logger.info("Connecting to MySQL server...")
        # This connection section uses a dictionary but can be hardcoded
        connection = mysql.connector.connect(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        
        if connection.is_connected():
            logger.info("Connected to MySQL server")
            
            # Create database and table
            create_database_if_not_exists(connection)
            create_table_if_not_exists(connection)
            
            # Load data
            load_data_from_csv(connection)
            
            logger.info("Process completed successfully")
    except Error as e:
        logger.error(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Close connection
        if connection and connection.is_connected():
            connection.close()
            logger.info("MySQL connection closed")

if __name__ == "__main__":
    main()