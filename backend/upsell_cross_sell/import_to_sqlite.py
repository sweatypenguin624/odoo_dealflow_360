#!/usr/bin/env python3
"""
Imports CSV datasets (~10,000+ records) into SQLite database (dealflow.db).

Imports:
  - products.csv          -> products_dataset
  - customers.csv         -> customers_dataset
  - invoices.csv          -> invoices
  - invoice_items.csv     -> invoice_items
  - cross_sell_rules.csv  -> cross_sell_rules & product_pairings
  - ml_training.csv       -> ml_training
  - ml_validation.csv     -> ml_validation
"""

import os
import sqlite3
import pandas as pd

def import_csvs_to_sqlite():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, 'data')
    backend_dir = os.path.dirname(base_dir)
    db_path = os.path.join(backend_dir, 'dealflow.db')
    
    print(f"Connecting to SQLite database at: {db_path}")
    conn = sqlite3.connect(db_path)
    
    files_to_import = [
        ('products.csv', 'products_dataset'),
        ('customers.csv', 'customers_dataset'),
        ('invoices.csv', 'invoices'),
        ('invoice_items.csv', 'invoice_items'),
        ('cross_sell_rules.csv', 'cross_sell_rules'),
        ('ml_training.csv', 'ml_training'),
        ('ml_validation.csv', 'ml_validation')
    ]
    
    print("\n--- Importing Datasets into SQLite ---")
    for csv_file, table_name in files_to_import:
        csv_path = os.path.join(data_dir, csv_file)
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df.to_sql(table_name, conn, if_exists='replace', index=False)
            print(f"✓ Imported {len(df):,} records into table '{table_name}' from {csv_file}")
        else:
            print(f"⚠ File not found: {csv_path}")

    # Seed product_pairings table in SQLite for live FastAPI router
    cross_sell_path = os.path.join(data_dir, 'cross_sell_rules.csv')
    products_path = os.path.join(data_dir, 'products.csv')
    
    if os.path.exists(cross_sell_path) and os.path.exists(products_path):
        print("\n--- Seeding product_pairings table from cross_sell_rules ---")
        rules = pd.read_csv(cross_sell_path)
        products = pd.read_csv(products_path)
        
        prod_map = dict(zip(products['product_name'], products['product_id']))
        
        pairings = []
        for _, row in rules.iterrows():
            base_id = prod_map.get(row['source_product'])
            sug_id = prod_map.get(row['recommended_product'])
            if base_id and sug_id:
                pairings.append({
                    'base_product_id': base_id,
                    'suggested_product_id': sug_id,
                    'co_purchase_score': float(row['association_score']),
                    'is_promoted': False
                })
                
        if pairings:
            pairings_df = pd.DataFrame(pairings)
            pairings_df.to_sql('product_pairings', conn, if_exists='replace', index_label='id')
            print(f"✓ Seeded {len(pairings_df):,} product pairings into table 'product_pairings'")

    conn.close()
    print("\n=== SQLite Data Migration Complete ===")

if __name__ == "__main__":
    import_csvs_to_sqlite()
