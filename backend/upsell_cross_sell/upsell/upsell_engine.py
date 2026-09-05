import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Configurable constants
MAX_UPSELL_PRICE_INCREASE = 0.20

WEIGHT_FEATURE_IMPROVEMENT = 0.50
WEIGHT_CUSTOMER_AFFORDABILITY = 0.25
WEIGHT_MARGIN = 0.15
WEIGHT_PRICE_VALUE = 0.10

TIER_MULTIPLIERS = {
    'Gold': 1.2,
    'Silver': 1.0,
    'Bronze': 0.8
}

PROCESSOR_MAP = {
    'i3': 1,
    'Ryzen 5': 2,
    'i5': 2,
    'Ryzen 7': 3,
    'i7': 3,
    'M1': 4
}

def calculate_feature_improvement(current_product: pd.Series, candidate_product: pd.Series) -> float:
    """
    Compares product attributes and returns a normalized score from 0 to 1.
    """
    features_to_compare = [
        'quality_score', 'performance_score', 'ram_gb', 'storage_gb', 'warranty_months'
    ]
    
    score = 0.0
    max_score = 0.0
    improvements = []
    
    for feature in features_to_compare:
        cur_val = current_product.get(feature)
        cand_val = candidate_product.get(feature)
        
        if pd.notnull(cur_val) and pd.notnull(cand_val):
            try:
                cur_val = float(cur_val)
                cand_val = float(cand_val)
                max_score += 1.0
                if cand_val > cur_val:
                    score += 1.0
                    improvements.append(feature)
                elif cand_val == cur_val:
                    # Partial credit for maintaining good specs
                    score += 0.5
            except ValueError:
                pass
                
    # Processor tier logic
    cur_proc = current_product.get('processor_tier')
    cand_proc = candidate_product.get('processor_tier')
    
    if pd.notnull(cur_proc) and pd.notnull(cand_proc):
        cur_proc_score = PROCESSOR_MAP.get(str(cur_proc).strip(), 0)
        cand_proc_score = PROCESSOR_MAP.get(str(cand_proc).strip(), 0)
        
        if cur_proc_score > 0 and cand_proc_score > 0:
            max_score += 1.0
            if cand_proc_score > cur_proc_score:
                score += 1.0
                improvements.append('processor_tier')
            elif cand_proc_score == cur_proc_score:
                score += 0.5

    if max_score == 0:
        return 0.0, []
        
    return score / max_score, improvements

def recommend_upsell(
    customer_id: int,
    current_product_ids: List[int],
    products: pd.DataFrame,
    customers: pd.DataFrame,
    top_n: int = 1
) -> pd.DataFrame:
    """
    Given a list of currently selected products, identify better versions 
    that the customer could reasonably upgrade to.
    """
    if products.empty or customers.empty or not current_product_ids:
        return pd.DataFrame()
        
    # Get customer info
    customer_row = customers[customers['customer_id'] == customer_id]
    if customer_row.empty:
        # Defaults if customer not found
        customer_tier = 'Silver'
        tier_multiplier = 1.0
        avg_invoice_value = customers['avg_invoice_value'].mean() if 'avg_invoice_value' in customers else 1.0
    else:
        customer_row = customer_row.iloc[0]
        customer_tier = customer_row.get('tier', 'Silver')
        tier_multiplier = TIER_MULTIPLIERS.get(customer_tier, 1.0)
        avg_invoice_value = customer_row.get('avg_invoice_value', customers['avg_invoice_value'].mean())
        
    # Calculate Customer Affordability Score
    # Normalize avg_invoice_value safely
    global_avg = customers['avg_invoice_value'].mean()
    if global_avg == 0 or pd.isna(global_avg):
        spend_ratio = 1.0
    else:
        spend_ratio = avg_invoice_value / global_avg
        
    # Cap spend_ratio to prevent extreme values dominating
    spend_ratio = min(spend_ratio, 2.0) 
    
    # Base affordability on tier (0.8 - 1.2) multiplied by historical spend ratio, then normalize to 0-1 approx.
    # Max possible = 1.2 * 2.0 = 2.4. Divide by 2.4 to normalize.
    customer_affordability = (tier_multiplier * spend_ratio) / 2.4
    customer_affordability = min(max(customer_affordability, 0.0), 1.0)
    
    # Pre-calculate margins for all products
    products = products.copy()
    products['margin'] = products['selling_price'] - products['cost_price']
    
    min_margin = products['margin'].min()
    max_margin = products['margin'].max()
    
    if max_margin > min_margin:
        products['normalized_margin'] = (products['margin'] - min_margin) / (max_margin - min_margin)
    else:
        products['normalized_margin'] = 0.0
        
    results = []
    
    for current_product_id in current_product_ids:
        current_product_df = products[products['product_id'] == current_product_id]
        if current_product_df.empty:
            continue
            
        current_product = current_product_df.iloc[0]
        cur_price = current_product['selling_price']
        cur_category = current_product['category']
        
        # Hard Filters
        candidates = products[
            (products['category'] == cur_category) &
            (products['active'] == True) &
            (products['stock_quantity'] > 0) &
            (products['product_id'] != current_product_id) &
            (products['selling_price'] > cur_price)
        ].copy()
        
        if candidates.empty:
            continue
            
        # Price increase filter
        candidates['price_difference'] = candidates['selling_price'] - cur_price
        candidates['price_increase_percentage'] = candidates['price_difference'] / cur_price
        
        candidates = candidates[candidates['price_increase_percentage'] <= MAX_UPSELL_PRICE_INCREASE].copy()
        
        if candidates.empty:
            continue
            
        # Scoring
        scored_candidates = []
        for _, candidate in candidates.iterrows():
            feat_imp_score, improvements = calculate_feature_improvement(current_product, candidate)
            
            # If no feature data could be compared or score is 0, they aren't a meaningful upgrade
            if feat_imp_score == 0:
                continue
                
            # Price value score (smaller reasonable increases score better)
            # 1.0 minus the percentage of the max allowed increase
            price_value_score = 1.0 - (candidate['price_increase_percentage'] / MAX_UPSELL_PRICE_INCREASE)
            price_value_score = max(0.0, price_value_score)
            
            upsell_score = (
                WEIGHT_FEATURE_IMPROVEMENT * feat_imp_score +
                WEIGHT_CUSTOMER_AFFORDABILITY * customer_affordability +
                WEIGHT_MARGIN * candidate['normalized_margin'] +
                WEIGHT_PRICE_VALUE * price_value_score
            )
            
            # Reason generation
            reason_parts = []
            if 'ram_gb' in improvements:
                reason_parts.append(f"{int(candidate.get('ram_gb', 0))}GB RAM")
            if 'processor_tier' in improvements:
                reason_parts.append("better processor")
            if 'storage_gb' in improvements:
                reason_parts.append("more storage")
            if 'performance_score' in improvements or 'quality_score' in improvements:
                reason_parts.append("better performance")
            if 'warranty_months' in improvements:
                reason_parts.append("longer warranty")
                
            diff_fmt = f"₹{candidate['price_difference']:,.0f}"
            
            if reason_parts:
                reason_str = " and ".join(reason_parts[:2]) # keep it concise
                reason = f"Upgrade for {diff_fmt} more — {reason_str}."
            else:
                reason = f"Upgrade for {diff_fmt} more with higher tier specifications."
                
            scored_candidates.append({
                'current_product_id': current_product_id,
                'current_product_name': current_product['product_name'],
                'current_price': cur_price,
                'recommended_product_id': candidate['product_id'],
                'recommended_product_name': candidate['product_name'],
                'recommended_price': candidate['selling_price'],
                'price_difference': candidate['price_difference'],
                'price_increase_percentage': candidate['price_increase_percentage'],
                'feature_improvement': feat_imp_score,
                'customer_affordability': customer_affordability,
                'normalized_margin': candidate['normalized_margin'],
                'price_value_score': price_value_score,
                'upsell_score': upsell_score,
                'reason': reason
            })
            
        if not scored_candidates:
            continue
            
        # Rank candidates for this product
        cand_df = pd.DataFrame(scored_candidates)
        cand_df = cand_df.sort_values(by='upsell_score', ascending=False)
        best_cands = cand_df.head(top_n)
        results.append(best_cands)
        
    if not results:
        return pd.DataFrame()
        
    return pd.concat(results, ignore_index=True)

def run_tests():
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, '..', 'data')
    
    products_path = os.path.join(data_dir, 'products.csv')
    customers_path = os.path.join(data_dir, 'customers.csv')
    
    products = pd.read_csv(products_path)
    customers = pd.read_csv(customers_path)
    
    gold_customers = customers[customers['tier'] == 'Gold']
    if not gold_customers.empty:
        gold_customer = gold_customers.iloc[0]
        gold_customer_id = gold_customer['customer_id']
    else:
        gold_customer_id = 1
        
    # Find a product that has viable upgrades
    laptops = products[products['category'] == 'Laptops'].sort_values('selling_price')
    base_laptop = laptops.iloc[0]
    laptop_product_id = base_laptop['product_id']
    
    print("\n" + "="*50)
    print("TEST CASE: UPSELL")
    print("="*50)
    print(f"Customer:\nID: {gold_customer_id} / Tier: Gold")
    print(f"\nCurrent product:\n{base_laptop['product_name']} (₹{base_laptop['selling_price']:,.2f})")
    
    cur_price = base_laptop['selling_price']
    eligible_count = len(products[
        (products['category'] == base_laptop['category']) &
        (products['active'] == True) &
        (products['stock_quantity'] > 0) &
        (products['product_id'] != laptop_product_id) &
        (products['selling_price'] > cur_price) &
        ((products['selling_price'] - cur_price) / cur_price <= MAX_UPSELL_PRICE_INCREASE)
    ])
    
    print(f"\nEligible candidates before scoring:\n{eligible_count}")
    
    recs = recommend_upsell(
        customer_id=gold_customer_id,
        current_product_ids=[laptop_product_id],
        products=products,
        customers=customers,
        top_n=1
    )
    
    print(f"\nCandidates after filtering:\n{len(recs)}")
    print("\nFinal recommended upgrade:")
    for i, row in recs.iterrows():
        print(f"\nCurrent product: {row['current_product_name']}")
        print(f"Current price: ₹{row['current_price']:,.2f}")
        print(f"Upgrade price: ₹{row['recommended_price']:,.2f}")
        print(f"Additional amount: ₹{row['price_difference']:,.2f}")
        print(f"Feature improvement: {row['feature_improvement']:.4f}")
        print(f"Customer affordability: {row['customer_affordability']:.4f}")
        print(f"Margin (Normalized): {row['normalized_margin']:.4f}")
        print(f"Final score: {row['upsell_score']:.4f}")
        print(f"Reason: {row['reason']}\n")

if __name__ == "__main__":
    run_tests()
