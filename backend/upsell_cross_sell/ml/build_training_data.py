import pandas as pd
import numpy as np
import os
import sys
import logging
from tqdm import tqdm

# Add parent directory to path to import cross_sell and upsell modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from cross_sell.apriori_engine import generate_cross_sell_rules
from cross_sell.recommender import recommend_cross_sell
from upsell.upsell_engine import recommend_upsell

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def build_training_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'data')
    
    products = pd.read_csv(os.path.join(data_dir, 'products.csv'))
    customers = pd.read_csv(os.path.join(data_dir, 'customers.csv'))
    invoices = pd.read_csv(os.path.join(data_dir, 'invoices.csv'))
    invoice_items = pd.read_csv(os.path.join(data_dir, 'invoice_items.csv'))
    rules = pd.read_csv(os.path.join(data_dir, 'cross_sell_rules.csv'))
    
    # Sort invoices chronologically
    invoices['invoice_date'] = pd.to_datetime(invoices['invoice_date'])
    invoices = invoices.sort_values('invoice_date').reset_index(drop=True)
    
    # Limit invoices to 5000 to keep generation fast (Hackathon scale)
    invoices = invoices.head(5000)
    
    # Pre-calculate margins
    products['margin'] = products['selling_price'] - products['cost_price']
    min_margin = products['margin'].min()
    max_margin = products['margin'].max()
    if max_margin > min_margin:
        products['normalized_margin'] = (products['margin'] - min_margin) / (max_margin - min_margin)
    else:
        products['normalized_margin'] = 0.0
        
    # State dictionaries to avoid data leakage
    customer_spend = {}
    customer_invoice_count = {}
    product_popularity = {}
    customer_category_affinity = {}
    customer_brand_affinity = {}
    
    examples = []
    
    # Group items by invoice for fast lookup
    items_by_invoice = invoice_items.groupby('invoice_id')
    
    logger.info("Iterating over invoices to generate chronological features and examples...")
    for idx, invoice in tqdm(invoices.iterrows(), total=len(invoices)):
        inv_id = invoice['invoice_id']
        cust_id = invoice['customer_id']
        inv_total = invoice['total_amount']
        
        if inv_id not in items_by_invoice.groups:
            continue
            
        items = items_by_invoice.get_group(inv_id)
        purchased_product_ids = items['product_id'].tolist()
        
        # 1. Extract historical features (state BEFORE this invoice)
        hist_spend = customer_spend.get(cust_id, 0.0)
        hist_count = customer_invoice_count.get(cust_id, 0)
        hist_avg = hist_spend / hist_count if hist_count > 0 else 0.0
        
        cust_row = customers[customers['customer_id'] == cust_id]
        customer_tier = cust_row.iloc[0]['tier'] if not cust_row.empty else 'Silver'
        
        cat_affinity = customer_category_affinity.get(cust_id, {})
        brand_affinity = customer_brand_affinity.get(cust_id, {})
        
        # ==================================================
        # 2. Generate CROSS-SELL EXAMPLES
        # ==================================================
        for current_product_id in purchased_product_ids:
            # We treat current_product_id as the seed, and the rest as "actuals"
            # In a real scenario, they had current_product_id and Apriori generated candidates.
            # If the candidate was in the rest of the invoice, it's a positive.
            candidates_df = recommend_cross_sell(
                customer_id=cust_id,
                invoice_product_ids=[current_product_id],
                rules=rules,
                products=products,
                customers=customers,
                top_n=10 # get more candidates to find negatives
            )
            
            if candidates_df.empty:
                continue
                
            for _, cand in candidates_df.iterrows():
                cand_id = cand['product_id']
                target = 1 if cand_id in purchased_product_ids else 0
                
                # Fetch product historical popularity
                pop = product_popularity.get(cand_id, 0)
                
                # Fetch affinities
                cand_cat = cand['category']
                cand_brand = products[products['product_id'] == cand_id].iloc[0].get('brand', '')
                c_aff = cat_affinity.get(cand_cat, 0)
                b_aff = brand_affinity.get(cand_brand, 0)
                
                examples.append({
                    'recommendation_type': 'cross_sell',
                    'customer_id': cust_id,
                    'customer_tier': customer_tier,
                    'customer_total_spend': hist_spend,
                    'customer_invoice_count': hist_count,
                    'customer_avg_invoice_value': hist_avg,
                    
                    'current_product_id': current_product_id,
                    'candidate_product_id': cand_id,
                    'candidate_price': cand['selling_price'],
                    'candidate_margin': cand['margin'],
                    'candidate_normalized_margin': cand['normalized_margin'],
                    
                    'support': cand.get('support', 0),
                    'confidence': cand.get('confidence', 0),
                    'lift': cand.get('lift', 0),
                    'association_score': cand.get('association_score', 0),
                    
                    'feature_improvement': 0.0, # N/A for cross-sell
                    'price_difference': 0.0,
                    'price_increase_percentage': 0.0,
                    
                    'customer_category_affinity': c_aff,
                    'customer_brand_affinity': b_aff,
                    'candidate_popularity': pop,
                    
                    'invoice_item_count': len(purchased_product_ids),
                    'invoice_total': inv_total,
                    
                    'target': target
                })
                
        # ==================================================
        # 3. Generate UPSELL EXAMPLES
        # ==================================================
        for actual_purchased_id in purchased_product_ids:
            actual_prod = products[products['product_id'] == actual_purchased_id].iloc[0]
            cat = actual_prod['category']
            price = actual_prod['selling_price']
            
            # Find a cheaper product in the same category to act as the "base" consideration
            cheaper_prods = products[(products['category'] == cat) & (products['selling_price'] < price)]
            
            if cheaper_prods.empty:
                continue
                
            # Pick one cheaper product randomly as the assumed starting point to keep data balanced
            base_prod = cheaper_prods.sample(1).iloc[0]
            
            # Generate upsell candidates from this base product
            candidates_df = recommend_upsell(
                customer_id=cust_id,
                current_product_ids=[base_prod['product_id']],
                products=products,
                customers=customers,
                top_n=10
            )
            
            if candidates_df.empty:
                continue
                
            # If the actual purchased product is among the candidates, it's a positive example
            # Other candidates are negatives. If actual is NOT in candidates, skip to avoid fake positives.
            if actual_purchased_id not in candidates_df['recommended_product_id'].values:
                continue
                
            for _, cand in candidates_df.iterrows():
                cand_id = cand['recommended_product_id']
                target = 1 if cand_id == actual_purchased_id else 0
                
                pop = product_popularity.get(cand_id, 0)
                
                cand_cat = products[products['product_id'] == cand_id].iloc[0].get('category', '')
                cand_brand = products[products['product_id'] == cand_id].iloc[0].get('brand', '')
                c_aff = cat_affinity.get(cand_cat, 0)
                b_aff = brand_affinity.get(cand_brand, 0)
                
                examples.append({
                    'recommendation_type': 'upsell',
                    'customer_id': cust_id,
                    'customer_tier': customer_tier,
                    'customer_total_spend': hist_spend,
                    'customer_invoice_count': hist_count,
                    'customer_avg_invoice_value': hist_avg,
                    
                    'current_product_id': base_prod['product_id'],
                    'candidate_product_id': cand_id,
                    'candidate_price': cand['recommended_price'],
                    'candidate_margin': cand['normalized_margin'], 
                    'candidate_normalized_margin': cand['normalized_margin'],
                    
                    'support': 0.0,
                    'confidence': 0.0,
                    'lift': 0.0,
                    'association_score': 0.0,
                    
                    'feature_improvement': cand.get('feature_improvement', 0),
                    'price_difference': cand.get('price_difference', 0),
                    'price_increase_percentage': cand.get('price_increase_percentage', 0),
                    
                    'customer_category_affinity': c_aff,
                    'customer_brand_affinity': b_aff,
                    'candidate_popularity': pop,
                    
                    'invoice_item_count': len(purchased_product_ids),
                    'invoice_total': inv_total,
                    
                    'target': target
                })
                
        # ==================================================
        # 4. UPDATE HISTORICAL STATE
        # ==================================================
        customer_spend[cust_id] = customer_spend.get(cust_id, 0.0) + inv_total
        customer_invoice_count[cust_id] = customer_invoice_count.get(cust_id, 0) + 1
        
        for item_idx, item in items.iterrows():
            pid = item['product_id']
            qty = item['quantity']
            product_popularity[pid] = product_popularity.get(pid, 0) + qty
            
            p_cat = products[products['product_id'] == pid].iloc[0].get('category', '')
            p_brand = products[products['product_id'] == pid].iloc[0].get('brand', '')
            
            if cust_id not in customer_category_affinity:
                customer_category_affinity[cust_id] = {}
            if cust_id not in customer_brand_affinity:
                customer_brand_affinity[cust_id] = {}
                
            customer_category_affinity[cust_id][p_cat] = customer_category_affinity[cust_id].get(p_cat, 0) + qty
            customer_brand_affinity[cust_id][p_brand] = customer_brand_affinity[cust_id].get(p_brand, 0) + qty

    df = pd.DataFrame(examples)
    
    if df.empty:
        logger.warning("No training examples generated.")
        return
        
    logger.info(f"Generated {len(df)} total examples.")
    
    # We generated them chronologically, so split 80/20 directly by order
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx]
    val_df = df.iloc[split_idx:]
    
    train_df.to_csv(os.path.join(data_dir, 'ml_training.csv'), index=False)
    val_df.to_csv(os.path.join(data_dir, 'ml_validation.csv'), index=False)
    
    logger.info(f"Saved {len(train_df)} training rows and {len(val_df)} validation rows.")
    
if __name__ == "__main__":
    build_training_data()
