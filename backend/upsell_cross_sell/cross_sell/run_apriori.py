import argparse
import pandas as pd
import os
import logging
from apriori_engine import generate_cross_sell_rules

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Run Apriori Cross-Sell Rule Generation")
    parser.add_argument('--min-support', type=float, default=0.005, help="Minimum support threshold")
    parser.add_argument('--min-confidence', type=float, default=0.10, help="Minimum confidence threshold")
    parser.add_argument('--min-lift', type=float, default=1.0, help="Minimum lift threshold")
    parser.add_argument('--top-n', type=int, default=20, help="Number of top rules to display")
    
    args = parser.parse_args()
    
    # Paths to data
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'data')
    
    products_path = os.path.join(data_dir, 'products.csv')
    invoices_path = os.path.join(data_dir, 'invoices.csv')
    invoice_items_path = os.path.join(data_dir, 'invoice_items.csv')
    rules_out_path = os.path.join(data_dir, 'cross_sell_rules.csv')
    
    # Check if files exist
    for path in [products_path, invoices_path, invoice_items_path]:
        if not os.path.exists(path):
            logger.error(f"File not found: {path}")
            return
            
    # Load Data
    logger.info("Loading data...")
    products = pd.read_csv(products_path)
    invoices = pd.read_csv(invoices_path)
    invoice_items = pd.read_csv(invoice_items_path)
    
    # Compute Dataset Statistics
    num_invoices = len(invoices['invoice_id'].unique())
    num_unique_products = len(products['product_id'].unique())
    
    # Avg products per invoice
    items_per_invoice = invoice_items.groupby('invoice_id')['product_id'].nunique()
    avg_products_per_invoice = items_per_invoice.mean()
    
    print("\n=== Dataset Statistics ===")
    print(f"* number of invoices: {num_invoices}")
    print(f"* number of unique products: {num_unique_products}")
    print(f"* average products per invoice: {avg_products_per_invoice:.2f}")
    
    # Generate Rules
    logger.info("Generating Apriori rules... This may take a moment.")
    rules, stats = generate_cross_sell_rules(
        invoice_items=invoice_items,
        products=products,
        min_support=args.min_support,
        min_confidence=args.min_confidence,
        min_lift=args.min_lift
    )
    
    # Apriori Statistics
    print("\n=== Apriori Statistics ===")
    print(f"* number of frequent itemsets: {stats.get('num_frequent_itemsets', 0)}")
    print(f"* number of association rules: {stats.get('num_association_rules', 0)}")
    print(f"* number of one-to-one rules: {stats.get('num_one_to_one_rules', 0)}")
    
    if rules.empty:
        logger.warning("No cross-sell rules were generated.")
        return
        
    # Save to CSV
    rules.to_csv(rules_out_path, index=False)
    logger.info(f"Saved rules to {rules_out_path}")
    
    # Display Top N Rules
    print(f"\n=== Top {args.top_n} Rules ===")
    print("Source → Recommendation | Support | Confidence | Lift | Score")
    print("-" * 70)
    
    top_rules = rules.head(args.top_n)
    for _, row in top_rules.iterrows():
        source = row['source_product']
        reco = row['recommended_product']
        sup = row['support']
        conf = row['confidence']
        lift = row['lift']
        score = row['association_score']
        print(f"{source} → {reco} | {sup:.4f} | {conf:.4f} | {lift:.2f} | {score:.2f}")

if __name__ == "__main__":
    main()
