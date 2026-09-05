import pandas as pd
import numpy as np
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Constants
TIER_MULTIPLIERS = {
    'Gold': 1.2,
    'Silver': 1.0,
    'Bronze': 0.8
}

WEIGHT_ASSOCIATION = 0.6
WEIGHT_TIER = 0.2
WEIGHT_BUSINESS = 0.2

def recommend_cross_sell(
    customer_id: int,
    invoice_product_ids: List[int],
    rules: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    top_n: int = 3
) -> pd.DataFrame:
    """
    Convert Apriori candidates into personalized, business-aware cross-sell recommendations.
    """
    if rules.empty or products.empty or customers.empty or not invoice_product_ids:
        return pd.DataFrame()
        
    # Get current invoice product names
    invoice_products = products[products['product_id'].isin(invoice_product_ids)]
    if invoice_products.empty:
        return pd.DataFrame()
        
    invoice_product_names = invoice_products['product_name'].tolist()
    
    # Get customer tier
    customer_row = customers[customers['customer_id'] == customer_id]
    customer_tier = 'Silver' # Default
    if not customer_row.empty:
        customer_tier = customer_row['tier'].values[0]
        
    tier_multiplier = TIER_MULTIPLIERS.get(customer_tier, 1.0)
    
    # Candidate Generation
    # Find rules where source product is in invoice
    matching_rules = rules[rules['source_product'].isin(invoice_product_names)].copy()
    
    if matching_rules.empty:
        return pd.DataFrame()
        
    # If multiple current products recommend the same candidate, 
    # keep the one with the strongest association_score and collect the sources.
    
    # Sort by association_score descending so that groupby.first() gets the max score
    matching_rules = matching_rules.sort_values(by='association_score', ascending=False)
    
    # Collect all sources that recommended this product
    sources_agg = matching_rules.groupby('recommended_product')['source_product'].apply(list).reset_index()
    sources_agg.rename(columns={'source_product': 'source_products'}, inplace=True)
    
    # Keep highest association score
    candidates = matching_rules.groupby('recommended_product').first().reset_index()
    candidates = candidates.merge(sources_agg, on='recommended_product')
    
    # Hard Filters
    # 1. products already present in the invoice
    candidates = candidates[~candidates['recommended_product'].isin(invoice_product_names)]
    
    # Join with products catalog to get details and apply other hard filters
    candidates = candidates.merge(products, left_on='recommended_product', right_on='product_name', how='inner')
    
    # 2. inactive products
    candidates = candidates[candidates['active'] == True]
    
    # 3. products with stock_quantity <= 0
    candidates = candidates[candidates['stock_quantity'] > 0]
    
    # 4. missing/invalid products (already handled by inner join)
    
    # 5. source product itself (handled by condition #1 since source products are in the invoice)
    
    if candidates.empty:
        return pd.DataFrame()
        
    # Customer Tier Adjustment
    candidates['tier_multiplier'] = tier_multiplier
    candidates['tier_score'] = candidates['association_score'] * tier_multiplier
    
    # Margin Adjustment
    # Calculate margin from selling_price and cost_price just in case
    candidates['computed_margin'] = candidates['selling_price'] - candidates['cost_price']
    
    # Normalize across the entire product catalog
    # Recompute all margins
    all_margins = products['selling_price'] - products['cost_price']
    min_margin = all_margins.min()
    max_margin = all_margins.max()
    
    if max_margin == min_margin:
        candidates['normalized_margin'] = 0.0
    else:
        candidates['normalized_margin'] = (candidates['computed_margin'] - min_margin) / (max_margin - min_margin)
        
    # Business Score
    candidates['business_score'] = candidates['association_score'] * candidates['normalized_margin']
    
    # Final Score
    candidates['final_score'] = (
        WEIGHT_ASSOCIATION * candidates['association_score'] + 
        WEIGHT_TIER * candidates['tier_score'] + 
        WEIGHT_BUSINESS * candidates['business_score']
    )
    
    # Recommendation Reason
    def generate_reason(row, tier):
        sources = row['source_products']
        # Distinct sources, preserve order
        unique_sources = []
        for s in sources:
            if s not in unique_sources:
                unique_sources.append(s)
                
        if tier == 'Gold' and row['tier_score'] > row['association_score']:
            # Example heuristic for deterministic Gold reason
            # If the user is Gold and it's a top candidate, we can use this reason.
            # But let's only use it if it's the strongest reason. The prompt gave it as an example.
            # Let's say if the association_score is moderate but tier boosts it heavily.
            pass # We'll just stick to a unified deterministic pattern below
            
        if len(unique_sources) == 1:
            if tier == 'Gold':
                return f"Popular cross-sell for Gold customers"
            return f"Frequently purchased with {unique_sources[0]}"
        elif len(unique_sources) == 2:
            return f"Frequently purchased with {unique_sources[0]} and {unique_sources[1]}"
        else:
            return f"Frequently purchased with {unique_sources[0]} and {len(unique_sources)-1} others"

    candidates['reason'] = candidates.apply(lambda row: generate_reason(row, customer_tier), axis=1)
    
    # Output columns
    candidates['margin'] = candidates['computed_margin']
    
    columns_to_return = [
        'product_id',
        'product_name',
        'category',
        'selling_price',
        'margin',
        'association_score',
        'tier_multiplier',
        'tier_score',
        'normalized_margin',
        'business_score',
        'final_score',
        'reason'
    ]
    
    # Ranking
    candidates = candidates.sort_values(by='final_score', ascending=False)
    
    # Ensure distinct product names by taking the best variant of each
    candidates = candidates.drop_duplicates(subset=['product_name'], keep='first')
    
    result = candidates[columns_to_return].head(top_n).reset_index(drop=True)
    return result

def run_tests():
    # Load data for tests
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'data')
    
    products_path = os.path.join(data_dir, 'products.csv')
    customers_path = os.path.join(data_dir, 'customers.csv')
    rules_path = os.path.join(data_dir, 'cross_sell_rules.csv')
    
    products = pd.read_csv(products_path)
    customers = pd.read_csv(customers_path)
    rules = pd.read_csv(rules_path)
    
    # Pick a popular product to ensure we get enough candidates
    # Let's find the source product with the most recommendations in rules
    source_counts = rules['source_product'].value_counts()
    best_source = source_counts.index[0]
    laptop_products = products[products['product_name'] == best_source]
    laptop_product_id = laptop_products['product_id'].values[0]
    laptop_name = laptop_products['product_name'].values[0]
    
    gold_customers = customers[customers['tier'] == 'Gold']
    if not gold_customers.empty:
        gold_customer_id = gold_customers['customer_id'].values[0]
    else:
        gold_customer_id = 99999
        customers = pd.concat([customers, pd.DataFrame({'customer_id': [gold_customer_id], 'tier': ['Gold']})], ignore_index=True)
        
    print("\n" + "="*50)
    print("TEST CASE 1")
    print("="*50)
    print(f"Customer:\nID: {gold_customer_id} / Tier: Gold")
    print(f"\nCurrent invoice:\n{laptop_name}")
    
    # Calculate candidates before filtering for reporting
    candidates_before = len(rules[rules['source_product'] == laptop_name]['recommended_product'].unique())
    
    recs = recommend_cross_sell(
        customer_id=gold_customer_id,
        invoice_product_ids=[laptop_product_id],
        rules=rules,
        products=products,
        customers=customers,
        top_n=3
    )
    
    candidates_after = len(recs)
    
    print(f"\nCandidates before filtering:\n{candidates_before}")
    print(f"\nCandidates after filtering:\n{candidates_after}")
    print("\nFinal recommendations:")
    for i, row in recs.iterrows():
        print(f"\n{i+1}. {row['product_name']}")
        print(f"   Association Score: {row['association_score']:.4f}")
        print(f"   Tier Score: {row['tier_score']:.4f}")
        print(f"   Margin: {row['margin']:.2f}")
        print(f"   Final Score: {row['final_score']:.4f}")
        print(f"   Reason: {row['reason']}")
        
    # TEST CASE 2
    # Find a recommended product to add to the invoice
    mouse_name = rules[rules['source_product'] == laptop_name]['recommended_product'].values[0]
    mouse_product_id = products[products['product_name'] == mouse_name]['product_id'].values[0]
        
    print("\n" + "="*50)
    print("TEST CASE 2")
    print("="*50)
    print(f"Customer:\nID: {gold_customer_id} / Tier: Gold")
    print(f"\nCurrent invoice:\n{laptop_name}\n{mouse_name}")
    
    candidates_before_2 = len(rules[rules['source_product'].isin([laptop_name, mouse_name])]['recommended_product'].unique())
    
    recs2 = recommend_cross_sell(
        customer_id=gold_customer_id,
        invoice_product_ids=[laptop_product_id, mouse_product_id],
        rules=rules,
        products=products,
        customers=customers,
        top_n=3
    )
    
    candidates_after_2 = len(recs2)
    
    print(f"\nCandidates before filtering:\n{candidates_before_2}")
    print(f"\nCandidates after filtering:\n{candidates_after_2}")
    print("\nFinal recommendations:")
    for i, row in recs2.iterrows():
        print(f"\n{i+1}. {row['product_name']}")
        print(f"   Association Score: {row['association_score']:.4f}")
        print(f"   Tier Score: {row['tier_score']:.4f}")
        print(f"   Margin: {row['margin']:.2f}")
        print(f"   Final Score: {row['final_score']:.4f}")
        print(f"   Reason: {row['reason']}")

if __name__ == "__main__":
    run_tests()
